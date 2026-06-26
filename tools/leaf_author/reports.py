from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tools.leaf_author.agent_handoff import AGENT_MODES, HANDOFF_RULES
from tools.leaf_author.batch_registry import inspect_batch
from tools.leaf_author.phase_guard import build_agent_handoff_contract
from tools.leaf_author.real_device_contract import real_device_decision_contract, real_device_runtime_evidence_schema, real_device_user_loop
from tools.leaf_author.run_registry import inspect_run
from tools.leaf_author.runtime_registry import approved_real_device_next_command, quality_artifact_priority, real_device_next_command
from tools.leaf_author.target_policy import default_target_policy, normalize_target_policy, with_target_policy


def report_run(root: Path, run_id: str) -> dict[str, object]:
    run = inspect_run(root, run_id)
    if run.get("current_phase") == "unreadable" or isinstance(run.get("error"), dict):
        return _unreadable_run_report(root, run)
    resume_summary = run.get("resume_summary", {})
    artifacts = run.get("artifacts", {})
    evidence = _existing_artifacts(root, artifacts if isinstance(artifacts, dict) else {})
    _add_conventional_evidence(root, run_id, evidence)
    context_manifest_summary = _context_manifest_summary(root, evidence)
    approval_required = None if run.get("current_phase") == "complete" else _real_device_approval(root, artifacts if isinstance(artifacts, dict) else {})
    input_required = None if run.get("current_phase") == "complete" else _real_device_input(root, artifacts if isinstance(artifacts, dict) else {})
    device_selection = _device_selection(root, artifacts if isinstance(artifacts, dict) else {})
    real_device_preflight = _real_device_preflight(root, artifacts if isinstance(artifacts, dict) else {})
    latest_quality_gate = _latest_quality_gate(root, str(run.get("domain", "")), artifacts if isinstance(artifacts, dict) else {})
    runtime_evidence_summary = _runtime_evidence_summary(
        root,
        str(run.get("domain", "")),
        artifacts if isinstance(artifacts, dict) else {},
        real_device_preflight,
        latest_quality_gate,
    )
    gui_handoff = _gui_handoff_summary(root, evidence)
    safe_to_auto_continue = bool(isinstance(resume_summary, dict) and resume_summary.get("safe_to_auto_continue")) and not approval_required and not input_required
    user_action_required = bool(isinstance(resume_summary, dict) and resume_summary.get("requires_user_confirmation")) or bool(approval_required) or bool(input_required)
    user_checkpoint = "real_device_confirmation" if approval_required else _user_checkpoint(run, user_action_required)
    user_loop = _report_user_loop(resume_summary, approval_required, input_required)
    decision_contract = _report_decision_contract(resume_summary, approval_required, input_required)
    operator_message = _report_operator_message(resume_summary, approval_required, input_required)
    action_route = _report_action_route(run)
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "domain": run.get("domain"),
        "platform": run.get("platform"),
        "current_phase": run.get("current_phase"),
        "confirmed_plan": run.get("confirmed_plan"),
        "next_action": run.get("next_action"),
        "latest_quality_gate": latest_quality_gate,
        "safe_to_auto_continue": safe_to_auto_continue,
        "user_action_required": user_action_required,
        "user_checkpoint": user_checkpoint,
        "user_loop": user_loop,
        "decision_contract": decision_contract,
        "action_route": action_route,
        "context_manifest": context_manifest_summary,
        "operator_message": operator_message,
        "next_command": _next_command(run_id, run, safe_to_auto_continue, user_checkpoint, approval_required, input_required),
        "approval_required": approval_required,
        "input_required": input_required,
        "device_selection": device_selection,
        "real_device_preflight": real_device_preflight,
        "runtime_evidence_summary": runtime_evidence_summary,
        "gui_handoff": gui_handoff,
        "evidence": evidence,
        "context_policy": {
            "scope": "run_report",
            "load_strategy": "summary_plus_existing_evidence_paths",
            "artifact_loading": "on_demand",
        },
    }


def report_batch(root: Path, batch_id: str) -> dict[str, object]:
    batch = inspect_batch(root, batch_id)
    runs = [_report_batch_run(root, run) for run in batch["runs"]]
    status_counts = Counter(_report_status(run) for run in runs)
    batch_audit = _batch_audit_summary(root, batch_id)
    return {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "title": batch.get("title", batch_id),
        "total_runs": len(runs),
        "summary": {
            "waiting_for_user": status_counts.get("waiting_for_user", 0),
            "safe_to_auto_continue": status_counts.get("safe_to_auto_continue", 0),
            "complete": status_counts.get("complete", 0),
            "blocked_or_inspect": status_counts.get("blocked_or_inspect", 0),
        },
        "real_device_summary": _batch_real_device_summary(runs),
        "runtime_evidence_summary": _batch_runtime_evidence_summary(runs),
        "gui_handoff_summary": batch_audit["gui_handoff_summary"],
        "ui_tree_summary": _batch_ui_tree_summary(runs),
        "next_run_focus": _next_report_focus(runs),
        "runs": [_batch_report_summary(run) for run in runs],
        "evidence": batch_audit["evidence"],
        "context_policy": {
            "scope": "batch_report",
            "load_strategy": "summaries_first_then_one_run_report",
            "artifact_loading": "on_demand",
        },
    }


def _existing_artifacts(root: Path, artifacts: dict[str, object]) -> dict[str, str]:
    evidence = {}
    for key, value in artifacts.items():
        if not isinstance(value, str) or not value:
            continue
        path = root / value
        if path.exists():
            evidence[key] = value
    return evidence


def _batch_audit_summary(root: Path, batch_id: str) -> dict[str, object]:
    audit_path = root / ".leaf" / "batches" / batch_id / "batch_audit.json"
    default = {
        "gui_handoff_summary": _empty_gui_handoff_summary(),
        "evidence": {},
    }
    if not audit_path.is_file():
        return default
    try:
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    if not isinstance(payload, dict):
        return default
    summary = payload.get("gui_handoff_summary")
    evidence = {"batch_audit": str(audit_path.relative_to(root))}
    return {
        "gui_handoff_summary": summary if isinstance(summary, dict) else _empty_gui_handoff_summary(),
        "evidence": evidence,
    }


def _empty_gui_handoff_summary() -> dict[str, object]:
    return {
        "total_artifacts": 0,
        "ready": 0,
        "failed": 0,
        "ready_runs": [],
        "failed_runs": [],
        "artifacts": [],
        "attention_boundary": "one_active_run",
    }


def _add_conventional_evidence(root: Path, run_id: str, evidence: dict[str, str]) -> None:
    diagnostics = root / ".leaf" / "runs" / run_id / "workflow_diagnostics.json"
    if diagnostics.is_file():
        evidence["workflow_diagnostics"] = str(diagnostics.relative_to(root))
    ui_tree_diagnostics = root / ".leaf" / "runs" / run_id / "ui_tree_diagnostics.json"
    if ui_tree_diagnostics.is_file():
        evidence["ui_tree_diagnostics"] = str(ui_tree_diagnostics.relative_to(root))


def _latest_quality_gate(root: Path, domain: str, artifacts: dict[str, object]) -> str:
    for key in quality_artifact_priority(domain):
        value = artifacts.get(key)
        if not isinstance(value, str) or not value:
            continue
        path = root / value
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        quality_gate = payload.get("quality_gate")
        if isinstance(quality_gate, str) and quality_gate:
            return quality_gate
    return "UNKNOWN"


def _gui_handoff_summary(root: Path, evidence: dict[str, str]) -> dict[str, object] | None:
    value = evidence.get("ui_tree_diagnostics")
    if not isinstance(value, str) or not value:
        return None
    path = root / value
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    handoff = payload.get("handoff")
    handoff = handoff if isinstance(handoff, dict) else {}
    user_loop = payload.get("user_loop")
    target_policy = payload.get("target_policy")
    contract_issues = _gui_handoff_contract_issues(payload, handoff)
    return {
        "artifact": value,
        "agent_owner": payload.get("agent_owner"),
        "agent_mode": payload.get("agent_mode"),
        "handoff_required": handoff.get("handoff_required"),
        "subagent_boundary": handoff.get("subagent_boundary"),
        "attention_boundary": handoff.get("attention_boundary"),
        "artifact_loading": handoff.get("artifact_loading"),
        "context_slice": handoff.get("context_slice") if isinstance(handoff.get("context_slice"), list) else [],
        "allowed_artifacts": handoff.get("allowed_artifacts") if isinstance(handoff.get("allowed_artifacts"), list) else [],
        "specific_question": handoff.get("specific_question"),
        "user_loop": user_loop if isinstance(user_loop, dict) else {},
        "target_policy": normalize_target_policy(target_policy),
        "snapshot_count": payload.get("snapshot_count"),
        "diff_count": payload.get("diff_count"),
        "contract_status": "ready" if not contract_issues else "drift",
        "contract_issues": contract_issues,
        "ui_tree_summary": _ui_tree_diagnostics_summary(payload),
    }


def _ui_tree_diagnostics_summary(payload: dict[str, object]) -> dict[str, object]:
    snapshots = payload.get("snapshots")
    snapshots = snapshots if isinstance(snapshots, list) else []
    snapshot_summaries = []
    foregrounds = []
    index_statuses = set()
    total_candidates = 0
    candidate_previews = []
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        foreground = snapshot.get("foreground")
        foreground = foreground if isinstance(foreground, dict) else {}
        if foreground:
            foregrounds.append(foreground)
        index_status = snapshot.get("index_status")
        if isinstance(index_status, str) and index_status:
            index_statuses.add(index_status)
        candidate_count = int(snapshot.get("candidate_count") or 0)
        total_candidates += candidate_count
        snapshot_candidate_previews = _ui_tree_candidate_previews(snapshot)
        candidate_previews.extend(
            {
                "phase": snapshot.get("phase"),
                "action_id": snapshot.get("action_id"),
                **candidate,
            }
            for candidate in snapshot_candidate_previews
        )
        snapshot_summaries.append(
            {
                "phase": snapshot.get("phase"),
                "action_id": snapshot.get("action_id"),
                "foreground": foreground,
                "node_count": snapshot.get("node_count"),
                "clickable_count": snapshot.get("clickable_count"),
                "candidate_count": candidate_count,
                "candidate_previews": snapshot_candidate_previews,
                "index_status": index_status,
            }
        )
    return {
        "snapshot_count": len(snapshot_summaries),
        "total_candidates": total_candidates,
        "candidate_previews": candidate_previews[:5],
        "index_statuses": sorted(index_statuses),
        "foregrounds": foregrounds,
        "snapshots": snapshot_summaries,
    }


def _ui_tree_candidate_previews(snapshot: dict[str, object]) -> list[dict[str, object]]:
    candidates = snapshot.get("candidates")
    candidates = candidates if isinstance(candidates, list) else []
    previews = []
    for candidate in candidates[:5]:
        if not isinstance(candidate, dict):
            continue
        previews.append(
            {
                "id": candidate.get("id"),
                "text": candidate.get("text"),
                "type": candidate.get("type"),
                "clickable": candidate.get("clickable"),
            }
        )
    return previews


def _gui_handoff_contract_issues(payload: dict[str, object], handoff: dict[str, object]) -> list[str]:
    issues: list[str] = []
    rule = HANDOFF_RULES["leaf-gui-agent"]
    if payload.get("agent_owner") != "leaf-gui-agent":
        issues.append("agent_owner must be leaf-gui-agent")
    if payload.get("agent_mode") != AGENT_MODES["leaf-gui-agent"]:
        issues.append("agent_mode must be focused_subagent")
    if handoff.get("handoff_required") != rule.get("handoff_required"):
        issues.append("handoff_required must match leaf-gui-agent rule")
    if handoff.get("required_inputs") != rule.get("required_inputs"):
        issues.append("required_inputs must match leaf-gui-agent rule")
    if handoff.get("subagent_boundary") != rule.get("subagent_boundary"):
        issues.append("subagent_boundary must be read_only_gui_context")
    if handoff.get("attention_boundary") != "one_active_run":
        issues.append("attention_boundary must be one_active_run")
    if handoff.get("artifact_loading") != "on_demand":
        issues.append("artifact_loading must be on_demand")
    context_slice = handoff.get("context_slice")
    context_slice = context_slice if isinstance(context_slice, list) else []
    if "ui_tree" not in context_slice:
        issues.append("context_slice must include ui_tree")
    if "runtime_evidence" not in context_slice:
        issues.append("context_slice must include runtime_evidence")
    target_policy = normalize_target_policy(payload.get("target_policy"))
    handoff_target_policy = normalize_target_policy(handoff.get("target_policy"))
    if target_policy.get("scope") != "system_app_only" or handoff_target_policy.get("scope") != "system_app_only":
        issues.append("target_policy scope must be system_app_only")
    return issues


def _real_device_approval(root: Path, artifacts: dict[str, object]) -> dict[str, object] | None:
    value = artifacts.get("real_device_approval")
    if not isinstance(value, str) or not value:
        return None
    path = root / value
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if payload.get("status") != "blocked":
        return None
    decision_contract = payload.get("decision_contract", {})
    user_loop = payload.get("user_loop", {})
    return {
        "artifact": value,
        "runtime_mode": payload.get("runtime_mode"),
        "required_approval_token": payload.get("required_approval_token"),
        "risk_level": payload.get("risk_level"),
        "mutates_device_state": payload.get("mutates_device_state"),
        "operator_message": payload.get("operator_message"),
        "decision_contract": _with_target_policy(decision_contract if isinstance(decision_contract, dict) else {}),
        "user_loop": user_loop if isinstance(user_loop, dict) else {},
    }


def _real_device_input(root: Path, artifacts: dict[str, object]) -> dict[str, object] | None:
    value = artifacts.get("real_device_input")
    if not isinstance(value, str) or not value:
        return None
    path = root / value
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if payload.get("status") != "blocked":
        return None
    missing = payload.get("missing", [])
    decision_contract = payload.get("decision_contract", {})
    user_loop = payload.get("user_loop", {})
    return {
        "artifact": value,
        "runtime_mode": payload.get("runtime_mode"),
        "missing": missing if isinstance(missing, list) else [],
        "required_input": payload.get("required_input"),
        "operator_message": payload.get("operator_message"),
        "decision_contract": _with_target_policy(decision_contract if isinstance(decision_contract, dict) else {}),
        "user_loop": user_loop if isinstance(user_loop, dict) else {},
    }


def _real_device_preflight(root: Path, artifacts: dict[str, object]) -> dict[str, object] | None:
    value = artifacts.get("real_device_preflight")
    if not isinstance(value, str) or not value:
        return None
    path = root / value
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    decision_contract = payload.get("decision_contract", {})
    user_loop = payload.get("user_loop", {})
    return {
        "artifact": value,
        "runtime_mode": payload.get("runtime_mode"),
        "status": payload.get("status"),
        "serial": payload.get("serial"),
        "serial_source": payload.get("serial_source"),
        "device_selection_artifact": payload.get("device_selection_artifact"),
        "risk_level": payload.get("risk_level"),
        "mutates_device_state": payload.get("mutates_device_state"),
        "approval_status": payload.get("approval_status"),
        "required_approval_token": payload.get("required_approval_token"),
        "approval_token": payload.get("approval_token"),
        "input_status": payload.get("input_status"),
        "next_action": payload.get("next_action"),
        "decision_contract": _with_target_policy(decision_contract if isinstance(decision_contract, dict) else {}),
        "user_loop": user_loop if isinstance(user_loop, dict) else {},
    }


def _runtime_evidence_summary(
    root: Path,
    domain: str,
    artifacts: dict[str, object],
    preflight: dict[str, object] | None,
    latest_quality_gate: str,
) -> dict[str, object] | None:
    if not preflight:
        return None
    runtime_mode = preflight.get("runtime_mode")
    if not isinstance(runtime_mode, str) or not runtime_mode:
        return None
    try:
        schema = real_device_runtime_evidence_schema(domain, runtime_mode)
    except ValueError:
        return {
            "schema_status": "missing_schema",
            "domain": domain,
            "runtime_mode": runtime_mode,
            "artifact": None,
            "quality_gate": latest_quality_gate,
            "required_evidence_fields": [],
            "missing_required_fields": [],
        }
    artifact_key = str(schema.get("artifact", ""))
    artifact = artifacts.get(artifact_key)
    required_fields = [str(field) for field in schema.get("required_evidence_fields", [])] if isinstance(schema.get("required_evidence_fields"), list) else []
    if not isinstance(artifact, str) or not artifact:
        return {
            "schema_status": "missing_artifact",
            "domain": domain,
            "runtime_mode": runtime_mode,
            "artifact": None,
            "quality_gate": latest_quality_gate,
            "expected_quality_gate": schema.get("quality_gate"),
            "required_evidence_fields": required_fields,
            "missing_required_fields": required_fields,
        }
    path = root / artifact
    if not path.is_file():
        return {
            "schema_status": "missing_artifact",
            "domain": domain,
            "runtime_mode": runtime_mode,
            "artifact": artifact,
            "quality_gate": latest_quality_gate,
            "expected_quality_gate": schema.get("quality_gate"),
            "required_evidence_fields": required_fields,
            "missing_required_fields": required_fields,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "schema_status": "invalid_artifact",
            "domain": domain,
            "runtime_mode": runtime_mode,
            "artifact": artifact,
            "quality_gate": latest_quality_gate,
            "expected_quality_gate": schema.get("quality_gate"),
            "required_evidence_fields": required_fields,
            "missing_required_fields": required_fields,
        }
    evidence = payload.get("evidence", {}) if isinstance(payload, dict) else {}
    evidence = evidence if isinstance(evidence, dict) else {}
    missing_fields = [field for field in required_fields if field not in evidence]
    ui_snapshots = _ui_snapshot_summaries(evidence.get("ui_snapshot_refs"))
    quality_gate = payload.get("quality_gate") if isinstance(payload, dict) else None
    quality_matches = quality_gate == schema.get("quality_gate") == latest_quality_gate
    schema_status = "complete" if not missing_fields and quality_matches else "missing_fields" if missing_fields else "quality_gate_mismatch"
    return {
        "schema_status": schema_status,
        "domain": domain,
        "runtime_mode": runtime_mode,
        "artifact": artifact,
        "artifact_key": artifact_key,
        "quality_gate": quality_gate,
        "expected_quality_gate": schema.get("quality_gate"),
        "required_evidence_fields": required_fields,
        "missing_required_fields": missing_fields,
        "quality_gate_matches_report": quality_matches,
        "ui_snapshot_ref_count": len(ui_snapshots),
        "ui_snapshots": ui_snapshots,
    }


def _device_selection(root: Path, artifacts: dict[str, object]) -> dict[str, object] | None:
    value = artifacts.get("device_selection")
    if not isinstance(value, str) or not value:
        return None
    path = root / value
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    context_policy = payload.get("context_policy", {})
    user_loop = payload.get("user_loop", {})
    device = payload.get("device", {})
    return {
        "artifact": value,
        "status": payload.get("status"),
        "serial": payload.get("serial"),
        "targets": payload.get("targets") if isinstance(payload.get("targets"), list) else [],
        "selection_reason": payload.get("selection_reason"),
        "context_policy": context_policy if isinstance(context_policy, dict) else {},
        "user_loop": user_loop if isinstance(user_loop, dict) else {},
        "device": device if isinstance(device, dict) else {},
    }


def _context_manifest_summary(root: Path, evidence: dict[str, str]) -> dict[str, object] | None:
    value = evidence.get("context_manifest")
    if not isinstance(value, str) or not value:
        return None
    path = root / value
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    handoff = payload.get("handoff")
    handoff = handoff if isinstance(handoff, dict) else {}
    return {
        "artifact": value,
        "agent_owner": payload.get("agent_owner"),
        "agent_mode": payload.get("agent_mode"),
        "handoff_required": handoff.get("handoff_required"),
        "subagent_boundary": handoff.get("subagent_boundary"),
        "required_inputs": handoff.get("required_inputs") if isinstance(handoff.get("required_inputs"), list) else [],
    }


def _approval_user_loop(approval_required: dict[str, object]) -> dict[str, str]:
    required_input = approval_required.get("required_approval_token")
    return real_device_user_loop("approval", str(required_input) if isinstance(required_input, str) else "")


def _approval_decision_contract() -> dict[str, object]:
    return _with_target_policy(real_device_decision_contract("approval"))


def _input_user_loop(input_required: dict[str, object]) -> dict[str, str]:
    required_input = input_required.get("required_input")
    return real_device_user_loop("input", str(required_input) if isinstance(required_input, str) else "")


def _input_decision_contract() -> dict[str, object]:
    return _with_target_policy(real_device_decision_contract("input"))


def _report_user_loop(
    resume_summary: object,
    approval_required: dict[str, object] | None,
    input_required: dict[str, object] | None,
) -> dict[str, object]:
    if approval_required:
        return _approval_user_loop(approval_required)
    if input_required:
        return _input_user_loop(input_required)
    if isinstance(resume_summary, dict):
        user_loop = resume_summary.get("user_loop", {})
        return user_loop if isinstance(user_loop, dict) else {}
    return {}


def _report_decision_contract(
    resume_summary: object,
    approval_required: dict[str, object] | None,
    input_required: dict[str, object] | None,
) -> dict[str, object]:
    if approval_required:
        return _approval_decision_contract()
    if input_required:
        return _input_decision_contract()
    decision_contract = {
        "trigger_source": resume_summary.get("trigger_source", "") if isinstance(resume_summary, dict) else "",
        "agent_owner": resume_summary.get("agent_owner", "") if isinstance(resume_summary, dict) else "",
        "agent_mode": _agent_mode_from_summary(resume_summary),
        "context_slice": resume_summary.get("context_slice", []) if isinstance(resume_summary, dict) else [],
        "allowed_artifacts": resume_summary.get("allowed_artifacts", []) if isinstance(resume_summary, dict) else [],
        "target_policy": resume_summary.get("target_policy", default_target_policy()) if isinstance(resume_summary, dict) else default_target_policy(),
    }
    return with_target_policy(decision_contract)


def _agent_mode_from_summary(resume_summary: object) -> str:
    if isinstance(resume_summary, dict) and isinstance(resume_summary.get("agent_mode"), str):
        return str(resume_summary.get("agent_mode"))
    owner = resume_summary.get("agent_owner", "") if isinstance(resume_summary, dict) else ""
    return AGENT_MODES.get(str(owner), "orchestrator")


def _report_operator_message(
    resume_summary: object,
    approval_required: dict[str, object] | None,
    input_required: dict[str, object] | None,
) -> str:
    if approval_required:
        return str(approval_required.get("operator_message", ""))
    if input_required:
        return str(input_required.get("operator_message", ""))
    if isinstance(resume_summary, dict):
        return str(resume_summary.get("operator_message", ""))
    return ""


def _user_checkpoint(run: dict[str, object], user_action_required: bool) -> str | None:
    resume_summary = run.get("resume_summary", {})
    if isinstance(resume_summary, dict):
        checkpoint = resume_summary.get("user_checkpoint")
        if isinstance(checkpoint, str) and checkpoint:
            return checkpoint
    if not user_action_required:
        return None
    if run.get("current_phase") == "plan" and not run.get("confirmed_plan"):
        return "first_plan_confirmation"
    if run.get("next_action") == "run_real_hypium":
        return "real_device_confirmation"
    return "manual_operator_decision"


def _next_command(
    run_id: str,
    run: dict[str, object],
    safe_to_auto_continue: bool,
    user_checkpoint: str | None,
    approval_required: dict[str, object] | None = None,
    input_required: dict[str, object] | None = None,
) -> str:
    if safe_to_auto_continue:
        return f"python3 -m tools.leaf_author resume {run_id} --auto-safe"
    if approval_required:
        runtime_mode = approval_required.get("runtime_mode")
        approval_token = approval_required.get("required_approval_token")
        if isinstance(runtime_mode, str) and runtime_mode and isinstance(approval_token, str) and approval_token:
            return approved_real_device_next_command(run_id, runtime_mode, approval_token)
    if input_required:
        runtime_mode = input_required.get("runtime_mode")
        if isinstance(runtime_mode, str) and runtime_mode:
            return approved_real_device_next_command(run_id, runtime_mode)
    if user_checkpoint == "first_plan_confirmation":
        return f"python3 -m tools.leaf_author confirm-plan {run_id}"
    if user_checkpoint == "real_device_confirmation":
        return real_device_next_command(run_id, str(run.get("domain", "")))
    if run.get("next_action") == "complete":
        return ""
    return ""


def _report_status(run: dict[str, object]) -> str:
    if run.get("current_phase") == "complete":
        return "complete"
    if run.get("current_phase") == "unreadable" or run.get("next_action") == "repair_workflow":
        return "blocked_or_inspect"
    if run.get("safe_to_auto_continue"):
        return "safe_to_auto_continue"
    if run.get("user_action_required"):
        return "waiting_for_user"
    return "blocked_or_inspect"


def _report_batch_run(root: Path, run_summary: dict[str, object]) -> dict[str, object]:
    if run_summary.get("current_phase") == "unreadable" or isinstance(run_summary.get("error"), dict):
        return _unreadable_run_report(root, run_summary)
    return report_run(root, str(run_summary["run_id"]))


def _unreadable_run_report(root: Path, run_summary: dict[str, object]) -> dict[str, object]:
    run_id = str(run_summary.get("run_id", ""))
    evidence: dict[str, str] = {}
    if run_id:
        _add_conventional_evidence(root, run_id, evidence)
    return {
        "schema_version": "1.0",
        "run_id": run_summary.get("run_id"),
        "domain": run_summary.get("domain"),
        "platform": run_summary.get("platform"),
        "current_phase": "unreadable",
        "confirmed_plan": False,
        "next_action": "repair_workflow",
        "latest_quality_gate": "UNKNOWN",
        "safe_to_auto_continue": False,
        "user_action_required": True,
        "user_checkpoint": "manual_operator_decision",
        "user_loop": {
            "position": "manual_triage",
            "required_input": "repair workflow.json",
        },
        "decision_contract": {
            "trigger_source": "workflow.json",
            "agent_owner": "leaf-test-author",
            "agent_mode": "orchestrator",
            "context_slice": ["workflow"],
            "allowed_artifacts": ["workflow"],
            "target_policy": default_target_policy(),
        },
        "action_route": _repair_action_route(),
        "operator_message": "Workflow state is unreadable; repair workflow.json before reporting or resuming this run.",
        "next_command": "",
        "approval_required": None,
        "input_required": None,
        "real_device_preflight": None,
        "evidence": evidence,
        "error": run_summary.get("error"),
        "context_policy": {
            "scope": "run_report",
            "load_strategy": "summary_plus_existing_evidence_paths",
            "artifact_loading": "on_demand",
        },
    }


def _next_report_focus(runs: list[dict[str, object]]) -> dict[str, object] | None:
    for run in runs:
        if run.get("current_phase") == "unreadable" or run.get("next_action") == "repair_workflow":
            return _batch_report_summary(run)
    for status in ("safe_to_auto_continue", "waiting_for_user", "blocked_or_inspect"):
        for run in runs:
            if _report_status(run) == status:
                return _batch_report_summary(run)
    return None


def _batch_report_summary(run: dict[str, object]) -> dict[str, object]:
    real_device_preflight = run.get("real_device_preflight")
    runtime_evidence = run.get("runtime_evidence_summary")
    gui_handoff = run.get("gui_handoff")
    summary = {
        "run_id": run.get("run_id"),
        "domain": run.get("domain"),
        "platform": run.get("platform"),
        "current_phase": run.get("current_phase"),
        "next_action": run.get("next_action"),
        "latest_quality_gate": run.get("latest_quality_gate"),
        "safe_to_auto_continue": run.get("safe_to_auto_continue"),
        "user_action_required": run.get("user_action_required"),
        "user_checkpoint": run.get("user_checkpoint"),
        "next_command": run.get("next_command"),
        "decision_contract": run.get("decision_contract") if isinstance(run.get("decision_contract"), dict) else {},
        "action_route": run.get("action_route") if isinstance(run.get("action_route"), dict) else {},
        "real_device_preflight": _batch_preflight_summary(real_device_preflight if isinstance(real_device_preflight, dict) else None),
        "runtime_evidence": _batch_runtime_evidence_detail(runtime_evidence if isinstance(runtime_evidence, dict) else None),
        "gui_handoff": _batch_gui_handoff_detail(gui_handoff if isinstance(gui_handoff, dict) else None),
    }
    if isinstance(run.get("error"), dict):
        summary["error"] = run["error"]
    return summary


def _batch_preflight_summary(preflight: dict[str, object] | None) -> dict[str, object] | None:
    if not preflight:
        return None
    return {
        "runtime_mode": preflight.get("runtime_mode"),
        "status": preflight.get("status"),
        "serial": preflight.get("serial"),
        "risk_level": preflight.get("risk_level"),
        "mutates_device_state": preflight.get("mutates_device_state"),
        "approval_status": preflight.get("approval_status"),
        "required_approval_token": preflight.get("required_approval_token"),
        "input_status": preflight.get("input_status"),
    }


def _batch_real_device_summary(runs: list[dict[str, object]]) -> dict[str, object]:
    preflights = [run.get("real_device_preflight") for run in runs if isinstance(run.get("real_device_preflight"), dict)]
    serials = sorted({str(preflight.get("serial")) for preflight in preflights if preflight.get("serial")})
    runtime_modes = sorted({str(preflight.get("runtime_mode")) for preflight in preflights if preflight.get("runtime_mode")})
    statuses = sorted({str(preflight.get("status")) for preflight in preflights if preflight.get("status")})
    risk_levels = sorted({str(preflight.get("risk_level")) for preflight in preflights if preflight.get("risk_level")})
    approval_statuses = sorted({str(preflight.get("approval_status")) for preflight in preflights if preflight.get("approval_status")})
    approval_tokens = sorted({str(preflight.get("required_approval_token")) for preflight in preflights if preflight.get("required_approval_token")})
    return {
        "total_preflights": len(preflights),
        "serials": serials,
        "runtime_modes": runtime_modes,
        "statuses": statuses,
        "risk_levels": risk_levels,
        "mutates_device_state": sum(1 for preflight in preflights if preflight.get("mutates_device_state") is True),
        "read_only": sum(1 for preflight in preflights if preflight.get("mutates_device_state") is False),
        "approval_statuses": approval_statuses,
        "approval_required": sum(1 for preflight in preflights if preflight.get("required_approval_token")),
        "approval_approved": sum(1 for preflight in preflights if preflight.get("approval_status") == "approved"),
        "approval_tokens": approval_tokens,
    }


def _batch_runtime_evidence_summary(runs: list[dict[str, object]]) -> dict[str, object]:
    summaries = [run.get("runtime_evidence_summary") for run in runs if isinstance(run.get("runtime_evidence_summary"), dict)]
    schema_statuses = Counter(str(summary.get("schema_status")) for summary in summaries if summary.get("schema_status"))
    quality_gates = sorted({str(summary.get("quality_gate")) for summary in summaries if summary.get("quality_gate")})
    missing_fields = sorted({field for summary in summaries for field in _string_list(summary.get("missing_required_fields"))})
    ui_snapshot_ref_count = sum(int(summary.get("ui_snapshot_ref_count") or 0) for summary in summaries)
    return {
        "total": len(summaries),
        "schema_statuses": dict(schema_statuses),
        "quality_gates": quality_gates,
        "missing_required_fields": missing_fields,
        "ui_snapshot_ref_count": ui_snapshot_ref_count,
    }


def _batch_ui_tree_summary(runs: list[dict[str, object]]) -> dict[str, object]:
    summaries = []
    for run in runs:
        gui_handoff = run.get("gui_handoff")
        if not isinstance(gui_handoff, dict):
            continue
        ui_tree = gui_handoff.get("ui_tree_summary")
        if isinstance(ui_tree, dict):
            summaries.append(ui_tree)
    foreground_bundles = sorted(
        {
            str(foreground.get("bundle"))
            for summary in summaries
            for foreground in summary.get("foregrounds", [])
            if isinstance(foreground, dict) and foreground.get("bundle")
        }
    )
    index_statuses = sorted({status for summary in summaries for status in _string_list(summary.get("index_statuses"))})
    return {
        "total_runs_with_ui_tree": len(summaries),
        "total_snapshots": sum(int(summary.get("snapshot_count") or 0) for summary in summaries),
        "total_candidates": sum(int(summary.get("total_candidates") or 0) for summary in summaries),
        "index_statuses": index_statuses,
        "foreground_bundles": foreground_bundles,
    }


def _batch_gui_handoff_detail(gui_handoff: dict[str, object] | None) -> dict[str, object] | None:
    if not gui_handoff:
        return None
    return {
        "artifact": gui_handoff.get("artifact"),
        "agent_owner": gui_handoff.get("agent_owner"),
        "agent_mode": gui_handoff.get("agent_mode"),
        "contract_status": gui_handoff.get("contract_status"),
        "contract_issues": _string_list(gui_handoff.get("contract_issues")),
        "ui_tree_summary": gui_handoff.get("ui_tree_summary") if isinstance(gui_handoff.get("ui_tree_summary"), dict) else {},
    }


def _batch_runtime_evidence_detail(summary: dict[str, object] | None) -> dict[str, object] | None:
    if not summary:
        return None
    return {
        "schema_status": summary.get("schema_status"),
        "runtime_mode": summary.get("runtime_mode"),
        "artifact": summary.get("artifact"),
        "quality_gate": summary.get("quality_gate"),
        "missing_required_fields": _string_list(summary.get("missing_required_fields")),
        "ui_snapshot_ref_count": int(summary.get("ui_snapshot_ref_count") or 0),
        "ui_snapshots": summary.get("ui_snapshots", []) if isinstance(summary.get("ui_snapshots"), list) else [],
    }


def _ui_snapshot_summaries(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    snapshots = []
    for item in value:
        if not isinstance(item, dict):
            continue
        snapshots.append(
            {
                "phase": item.get("phase"),
                "action_id": item.get("action_id"),
                "raw_path": item.get("raw_path"),
                "index_path": item.get("index_path"),
                "foreground": item.get("foreground") if isinstance(item.get("foreground"), dict) else {},
                "node_count": item.get("node_count"),
                "clickable_count": item.get("clickable_count"),
            }
        )
    return snapshots


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _with_target_policy(decision_contract: dict[str, object]) -> dict[str, object]:
    return with_target_policy(decision_contract, normalize_target_policy(decision_contract.get("target_policy")))


def _report_action_route(run: dict[str, object]) -> dict[str, object]:
    phase = str(run.get("current_phase", ""))
    routes = build_agent_handoff_contract().get("action_routes")
    if isinstance(routes, dict):
        route = routes.get(phase)
        if isinstance(route, dict):
            return dict(route)
    return _repair_action_route(phase)


def _repair_action_route(phase: str = "unreadable") -> dict[str, object]:
    return {
        "phase": phase,
        "next_action": "repair_workflow",
        "trigger_source": "workflow.json",
        "agent_owner": "leaf-test-author",
        "agent_mode": "orchestrator",
        "handoff_required": False,
        "subagent_boundary": "workflow_orchestration",
        "context_slice": ["workflow"],
        "allowed_artifacts": ["workflow"],
        "user_checkpoint": "manual_operator_decision",
        "auto_safe": False,
        "user_loop": {
            "position": "manual_triage",
            "required_input": "repair workflow.json",
        },
        "command": "python3 -m tools.leaf_author workflow-diagnostics <run_id>",
    }
