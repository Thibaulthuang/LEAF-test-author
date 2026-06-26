from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tools.leaf_author.batch_registry import inspect_batch
from tools.leaf_author.real_device_contract import real_device_decision_contract, real_device_user_loop
from tools.leaf_author.run_registry import inspect_run
from tools.leaf_author.runtime_registry import approved_real_device_next_command, quality_artifact_priority, real_device_next_command


def report_run(root: Path, run_id: str) -> dict[str, object]:
    run = inspect_run(root, run_id)
    resume_summary = run.get("resume_summary", {})
    artifacts = run.get("artifacts", {})
    evidence = _existing_artifacts(root, artifacts if isinstance(artifacts, dict) else {})
    approval_required = None if run.get("current_phase") == "complete" else _real_device_approval(root, artifacts if isinstance(artifacts, dict) else {})
    input_required = None if run.get("current_phase") == "complete" else _real_device_input(root, artifacts if isinstance(artifacts, dict) else {})
    real_device_preflight = _real_device_preflight(root, artifacts if isinstance(artifacts, dict) else {})
    latest_quality_gate = _latest_quality_gate(root, str(run.get("domain", "")), artifacts if isinstance(artifacts, dict) else {})
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
        "real_device_preflight": real_device_preflight,
        "evidence": evidence,
        "context_policy": {
            "scope": "run_report",
            "load_strategy": "summary_plus_existing_evidence_paths",
            "artifact_loading": "on_demand",
        },
    }


def report_batch(root: Path, batch_id: str) -> dict[str, object]:
    batch = inspect_batch(root, batch_id)
    runs = [report_run(root, str(run["run_id"])) for run in batch["runs"]]
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
        "risk_level": payload.get("risk_level"),
        "mutates_device_state": payload.get("mutates_device_state"),
        "approval_status": payload.get("approval_status"),
        "input_status": payload.get("input_status"),
        "next_action": payload.get("next_action"),
        "decision_contract": decision_contract if isinstance(decision_contract, dict) else {},
        "user_loop": user_loop if isinstance(user_loop, dict) else {},
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
    if run.get("safe_to_auto_continue"):
        return "safe_to_auto_continue"
    if run.get("user_action_required"):
        return "waiting_for_user"
    return "blocked_or_inspect"


def _next_report_focus(runs: list[dict[str, object]]) -> dict[str, object] | None:
    for status in ("safe_to_auto_continue", "waiting_for_user", "blocked_or_inspect"):
        for run in runs:
            if _report_status(run) == status:
                return _batch_report_summary(run)
    return None


def _batch_report_summary(run: dict[str, object]) -> dict[str, object]:
    real_device_preflight = run.get("real_device_preflight")
    return {
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
    }


def _batch_preflight_summary(preflight: dict[str, object] | None) -> dict[str, object] | None:
    if not preflight:
        return None
    return {
        "runtime_mode": preflight.get("runtime_mode"),
        "status": preflight.get("status"),
        "risk_level": preflight.get("risk_level"),
        "mutates_device_state": preflight.get("mutates_device_state"),
        "approval_status": preflight.get("approval_status"),
        "input_status": preflight.get("input_status"),
    }
