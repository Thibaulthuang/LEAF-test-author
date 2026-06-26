from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tools.leaf_author.batch_registry import inspect_batch
from tools.leaf_author.real_device_contract import real_device_decision_contract, real_device_runtime_evidence_schema, real_device_user_loop
from tools.leaf_author.run_registry import inspect_run
from tools.leaf_author.runtime_registry import approved_real_device_next_command, quality_artifact_priority, real_device_next_command


def report_run(root: Path, run_id: str) -> dict[str, object]:
    run = inspect_run(root, run_id)
    if run.get("current_phase") == "unreadable" or isinstance(run.get("error"), dict):
        return _unreadable_run_report(root, run)
    resume_summary = run.get("resume_summary", {})
    artifacts = run.get("artifacts", {})
    evidence = _existing_artifacts(root, artifacts if isinstance(artifacts, dict) else {})
    _add_conventional_evidence(root, run_id, evidence)
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
    safe_to_auto_continue = bool(isinstance(resume_summary, dict) and resume_summary.get("safe_to_auto_continue")) and not approval_required and not input_required
    user_action_required = bool(isinstance(resume_summary, dict) and resume_summary.get("requires_user_confirmation")) or bool(approval_required) or bool(input_required)
    user_checkpoint = "real_device_confirmation" if approval_required else _user_checkpoint(run, user_action_required)
    user_loop = _report_user_loop(resume_summary, approval_required, input_required)
    decision_contract = _report_decision_contract(resume_summary, approval_required, input_required)
    operator_message = _report_operator_message(resume_summary, approval_required, input_required)
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
        "operator_message": operator_message,
        "next_command": _next_command(run_id, run, safe_to_auto_continue, user_checkpoint, approval_required, input_required),
        "approval_required": approval_required,
        "input_required": input_required,
        "device_selection": device_selection,
        "real_device_preflight": real_device_preflight,
        "runtime_evidence_summary": runtime_evidence_summary,
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
        "next_run_focus": _next_report_focus(runs),
        "runs": [_batch_report_summary(run) for run in runs],
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


def _add_conventional_evidence(root: Path, run_id: str, evidence: dict[str, str]) -> None:
    diagnostics = root / ".leaf" / "runs" / run_id / "workflow_diagnostics.json"
    if diagnostics.is_file():
        evidence["workflow_diagnostics"] = str(diagnostics.relative_to(root))


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
    return {
        "artifact": value,
        "runtime_mode": payload.get("runtime_mode"),
        "required_approval_token": payload.get("required_approval_token"),
        "risk_level": payload.get("risk_level"),
        "mutates_device_state": payload.get("mutates_device_state"),
        "operator_message": payload.get("operator_message"),
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
    return {
        "artifact": value,
        "runtime_mode": payload.get("runtime_mode"),
        "missing": missing if isinstance(missing, list) else [],
        "required_input": payload.get("required_input"),
        "operator_message": payload.get("operator_message"),
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
        "input_status": payload.get("input_status"),
        "next_action": payload.get("next_action"),
        "decision_contract": decision_contract if isinstance(decision_contract, dict) else {},
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


def _approval_user_loop(approval_required: dict[str, object]) -> dict[str, str]:
    required_input = approval_required.get("required_approval_token")
    return real_device_user_loop("approval", str(required_input) if isinstance(required_input, str) else "")


def _approval_decision_contract() -> dict[str, object]:
    return real_device_decision_contract("approval")


def _input_user_loop(input_required: dict[str, object]) -> dict[str, str]:
    required_input = input_required.get("required_input")
    return real_device_user_loop("input", str(required_input) if isinstance(required_input, str) else "")


def _input_decision_contract() -> dict[str, object]:
    return real_device_decision_contract("input")


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
    return {
        "trigger_source": resume_summary.get("trigger_source", "") if isinstance(resume_summary, dict) else "",
        "agent_owner": resume_summary.get("agent_owner", "") if isinstance(resume_summary, dict) else "",
        "context_slice": resume_summary.get("context_slice", []) if isinstance(resume_summary, dict) else [],
        "allowed_artifacts": resume_summary.get("allowed_artifacts", []) if isinstance(resume_summary, dict) else [],
    }


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
            "context_slice": ["workflow"],
            "allowed_artifacts": ["workflow"],
        },
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
        "real_device_preflight": _batch_preflight_summary(real_device_preflight if isinstance(real_device_preflight, dict) else None),
        "runtime_evidence": _batch_runtime_evidence_detail(runtime_evidence if isinstance(runtime_evidence, dict) else None),
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
        "input_status": preflight.get("input_status"),
    }


def _batch_real_device_summary(runs: list[dict[str, object]]) -> dict[str, object]:
    preflights = [run.get("real_device_preflight") for run in runs if isinstance(run.get("real_device_preflight"), dict)]
    serials = sorted({str(preflight.get("serial")) for preflight in preflights if preflight.get("serial")})
    runtime_modes = sorted({str(preflight.get("runtime_mode")) for preflight in preflights if preflight.get("runtime_mode")})
    statuses = sorted({str(preflight.get("status")) for preflight in preflights if preflight.get("status")})
    return {
        "total_preflights": len(preflights),
        "serials": serials,
        "runtime_modes": runtime_modes,
        "statuses": statuses,
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
