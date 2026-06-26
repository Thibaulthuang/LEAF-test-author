from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tools.leaf_author.batch_registry import inspect_batch
from tools.leaf_author.run_registry import inspect_run
from tools.leaf_author.runtime_registry import quality_artifact_priority


def report_run(root: Path, run_id: str) -> dict[str, object]:
    run = inspect_run(root, run_id)
    resume_summary = run.get("resume_summary", {})
    artifacts = run.get("artifacts", {})
    evidence = _existing_artifacts(root, artifacts if isinstance(artifacts, dict) else {})
    latest_quality_gate = _latest_quality_gate(root, str(run.get("domain", "")), artifacts if isinstance(artifacts, dict) else {})
    safe_to_auto_continue = bool(isinstance(resume_summary, dict) and resume_summary.get("safe_to_auto_continue"))
    user_action_required = bool(isinstance(resume_summary, dict) and resume_summary.get("requires_user_confirmation"))
    user_checkpoint = _user_checkpoint(run, user_action_required)
    user_loop = resume_summary.get("user_loop", {}) if isinstance(resume_summary, dict) else {}
    decision_contract = {
        "trigger_source": resume_summary.get("trigger_source", "") if isinstance(resume_summary, dict) else "",
        "agent_owner": resume_summary.get("agent_owner", "") if isinstance(resume_summary, dict) else "",
        "context_slice": resume_summary.get("context_slice", []) if isinstance(resume_summary, dict) else [],
        "allowed_artifacts": resume_summary.get("allowed_artifacts", []) if isinstance(resume_summary, dict) else [],
    }
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
        "operator_message": resume_summary.get("operator_message", "") if isinstance(resume_summary, dict) else "",
        "next_command": _next_command(run_id, run, safe_to_auto_continue, user_checkpoint),
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


def _next_command(run_id: str, run: dict[str, object], safe_to_auto_continue: bool, user_checkpoint: str | None) -> str:
    if safe_to_auto_continue:
        return f"python3 -m tools.leaf_author resume {run_id} --auto-safe"
    if user_checkpoint == "first_plan_confirmation":
        return f"python3 -m tools.leaf_author confirm-plan {run_id}"
    if user_checkpoint == "real_device_confirmation":
        return f"python3 -m tools.leaf_author advance {run_id} --run-real --serial <serial>"
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
    }
