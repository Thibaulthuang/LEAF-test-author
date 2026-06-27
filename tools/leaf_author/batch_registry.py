from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tools.leaf_author.authoring import resume_run
from tools.leaf_author.agent_handoff import AGENT_MODES, HANDOFF_RULES
from tools.leaf_author.phase_contract import batch_focus_priority_for_run
from tools.leaf_author.run_registry import inspect_run
from tools.leaf_author.target_policy import default_target_policy, normalize_target_policy


def create_batch(root: Path, batch_id: str, run_ids: list[str], title: str | None = None) -> dict[str, object]:
    if not run_ids:
        raise ValueError("batch must include at least one run_id")
    for run_id in run_ids:
        workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
        if not workflow_path.is_file():
            raise FileNotFoundError(f"workflow.json not found for run {run_id}: {workflow_path}")
    batch_dir = root / ".leaf" / "batches" / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "title": title or batch_id,
        "run_ids": run_ids,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "context_policy": {
            "scope": "batch",
            "load_strategy": "inspect_batch_then_inspect_one_run",
            "artifact_loading": "on_demand",
        },
    }
    batch_path = batch_dir / "batch.json"
    batch_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**inspect_batch(root, batch_id), "batch_path": str(batch_path)}


def inspect_batch(root: Path, batch_id: str) -> dict[str, object]:
    batch = _load_batch(root, batch_id)
    runs = [_inspect_batch_run(root, run_id) for run_id in batch["run_ids"]]
    phase_counts = Counter(str(run.get("current_phase", "unknown")) for run in runs)
    next_run_focus = _next_run_focus(runs)
    return {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "title": batch.get("title", batch_id),
        "total_runs": len(runs),
        "phase_counts": dict(sorted(phase_counts.items())),
        "next_run_focus": next_run_focus,
        "runs": [_run_batch_summary(run) for run in runs],
        "created_at": batch.get("created_at"),
        "context_policy": {
            "scope": "batch_summary",
            "load_strategy": "inspect_one_run_for_details",
        },
    }


def list_batches(root: Path) -> dict[str, object]:
    batches = []
    for path in _batch_paths(root):
        batch = json.loads(path.read_text(encoding="utf-8"))
        batches.append(
            {
                "batch_id": batch.get("batch_id", path.parent.name),
                "title": batch.get("title", path.parent.name),
                "total_runs": len(batch.get("run_ids", [])),
                "created_at": batch.get("created_at"),
            }
        )
    batches.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return {
        "schema_version": "1.0",
        "total": len(batches),
        "batches": batches,
        "context_policy": {
            "load_strategy": "inspect_one_batch_at_a_time",
        },
    }


def resume_batch(root: Path, batch_id: str, auto_safe: bool = False) -> dict[str, object]:
    batch = _load_batch(root, batch_id)
    audit_summary = _batch_audit_summary(root, batch_id) if auto_safe else None
    if audit_summary and audit_summary.get("failed_checks"):
        runs = [_resume_batch_run(root, run_id, auto_safe=False) for run_id in batch["run_ids"]]
        statuses = Counter(str(run.get("status", "in_progress")) for run in runs)
        return {
            "schema_version": "1.0",
            "batch_id": batch_id,
            "title": batch.get("title", batch_id),
            "auto_safe": auto_safe,
            "status": "blocked",
            "block_reason": "batch_audit_failed",
            "operator_message": "batch audit failed; inspect batch_audit_summary.failed_checks before resuming this batch.",
            "user_checkpoint": "manual_operator_decision",
            "user_loop": {
                "position": "audit_failure_triage",
                "required_input": "inspect batch_audit_summary.failed_checks",
            },
            "batch_audit_summary": audit_summary,
            "summary": {
                "advanced": 0,
                "waiting_for_confirmation": sum(1 for run in runs if run.get("status") == "waiting_for_confirmation"),
                "complete": statuses.get("complete", 0),
                "in_progress": statuses.get("in_progress", 0),
                "failed": statuses.get("failed", 0),
            },
            "focus_plan": audit_summary.get("focus_plan") if isinstance(audit_summary.get("focus_plan"), dict) else _batch_resume_focus_plan(runs),
            "runs": runs,
            "context_policy": {
                "scope": "batch_resume",
                "load_strategy": "one_run_resume_summary_at_a_time",
                "artifact_loading": "on_demand",
                "attention_boundary": "one_active_run",
            },
        }
    runs = [_resume_batch_run(root, run_id, auto_safe=auto_safe) for run_id in batch["run_ids"]]
    statuses = Counter(str(run.get("status", "in_progress")) for run in runs)
    focus_plan = _batch_resume_focus_plan(runs)
    payload = {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "title": batch.get("title", batch_id),
        "auto_safe": auto_safe,
        "summary": {
            "advanced": sum(1 for run in runs if run.get("auto_advanced") is True),
            "waiting_for_confirmation": sum(1 for run in runs if run.get("status") == "waiting_for_confirmation"),
            "complete": statuses.get("complete", 0),
            "in_progress": statuses.get("in_progress", 0),
            "failed": statuses.get("failed", 0),
        },
        "focus_plan": focus_plan,
        "runs": runs,
        "context_policy": {
            "scope": "batch_resume",
            "load_strategy": "one_run_resume_summary_at_a_time",
            "artifact_loading": "on_demand",
            "attention_boundary": "one_active_run",
        },
    }
    if audit_summary:
        payload["batch_audit_summary"] = audit_summary
    return payload


def _load_batch(root: Path, batch_id: str) -> dict[str, object]:
    batch_path = root / ".leaf" / "batches" / batch_id / "batch.json"
    return json.loads(batch_path.read_text(encoding="utf-8"))


def _batch_audit_summary(root: Path, batch_id: str) -> dict[str, object] | None:
    audit_path = root / ".leaf" / "batches" / batch_id / "batch_audit.json"
    if not audit_path.is_file():
        return None
    try:
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    checks = payload.get("batch_checks")
    if not isinstance(checks, list):
        return None
    normalized_checks = [check for check in checks if isinstance(check, dict)]
    failed = [str(check.get("name")) for check in normalized_checks if check.get("name") and not check.get("passed")]
    return {
        "artifact": str(audit_path.relative_to(root)),
        "total_checks": len(normalized_checks),
        "passed_checks": sum(1 for check in normalized_checks if check.get("passed") is True),
        "failed_checks": failed,
        "focus_plan": payload.get("focus_plan") if isinstance(payload.get("focus_plan"), dict) else None,
    }


def _batch_paths(root: Path) -> list[Path]:
    batches_dir = root / ".leaf" / "batches"
    if not batches_dir.is_dir():
        return []
    return sorted(path for path in batches_dir.glob("*/batch.json") if path.is_file())


def _run_batch_summary(run: dict[str, object]) -> dict[str, object]:
    summary = {
        "run_id": run.get("run_id"),
        "domain": run.get("domain"),
        "platform": run.get("platform"),
        "current_phase": run.get("current_phase"),
        "confirmed_plan": run.get("confirmed_plan"),
        "next_action": run.get("next_action"),
        "focus_source": "workflow-contract",
    }
    if isinstance(run.get("error"), dict):
        summary["focus_source"] = "workflow-read-error"
        summary["error"] = run["error"]
    return summary


def _inspect_batch_run(root: Path, run_id: str) -> dict[str, object]:
    try:
        return inspect_run(root, run_id)
    except Exception as exc:
        return {
            "run_id": run_id,
            "domain": None,
            "platform": None,
            "current_phase": "unreadable",
            "confirmed_plan": False,
            "next_action": "repair_workflow",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }


def _resume_batch_run(root: Path, run_id: str, auto_safe: bool) -> dict[str, object]:
    try:
        resume = resume_run(root, str(run_id), auto_safe=auto_safe)
    except Exception as exc:
        return {
            "run_id": run_id,
            "current_phase": "unreadable",
            "confirmed_plan": False,
            "next_action": "repair_workflow",
            "auto_advanced": False,
            "status": "failed",
            "resume_summary": {
                "requires_user_confirmation": True,
                "safe_to_auto_continue": False,
                "operator_message": "Workflow state is unreadable; repair workflow.json before resuming this run.",
                "user_checkpoint": "manual_operator_decision",
                "agent_owner": "leaf-test-author",
                "agent_mode": "orchestrator",
                "context_slice": ["workflow"],
                "trigger_source": "workflow.json",
                "allowed_artifacts": ["workflow"],
                "target_policy": default_target_policy(),
                "user_loop": {
                    "position": "manual_triage",
                    "required_input": "repair workflow.json",
                },
            },
            "real_device_preflight": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
    resume_summary = resume.get("resume_summary", {})
    status = str(resume.get("status", "in_progress"))
    if status == "in_progress" and isinstance(resume_summary, dict) and resume_summary.get("requires_user_confirmation"):
        status = "waiting_for_confirmation"
    if resume.get("current_phase") == "complete":
        status = "complete"
    return {
        "run_id": run_id,
        "current_phase": resume.get("current_phase"),
        "confirmed_plan": resume.get("confirmed_plan"),
        "next_action": resume.get("next_action"),
        "auto_advanced": bool(resume.get("auto_advanced", False)),
        "status": status,
        "resume_summary": resume_summary,
        "real_device_preflight": _real_device_preflight_summary(root, str(run_id)),
    }


def _batch_resume_focus_plan(runs: list[dict[str, object]]) -> dict[str, object] | None:
    active_runs = [run for run in runs if str(run.get("status")) != "complete"]
    if not active_runs:
        return None
    candidates = sorted(active_runs, key=_resume_focus_sort_key)
    selected = candidates[0]
    summary = selected.get("resume_summary", {})
    if not isinstance(summary, dict):
        summary = {}
    user_loop = summary.get("user_loop", {})
    if not isinstance(user_loop, dict):
        user_loop = {}
    agent_owner = str(summary.get("agent_owner", "leaf-test-author"))
    agent_mode = str(summary.get("agent_mode") or AGENT_MODES.get(agent_owner, "orchestrator"))
    handoff_rule = HANDOFF_RULES.get(agent_owner, HANDOFF_RULES["leaf-test-author"])
    return {
        "selected_run_id": selected.get("run_id"),
        "selection_reason": _resume_focus_selection_reason(selected, summary),
        "attention_boundary": "one_active_run",
        "artifact_loading": "on_demand",
        "agent_owner": agent_owner,
        "agent_mode": agent_mode,
        "handoff_required": bool(handoff_rule.get("handoff_required", False)),
        "required_inputs": list(handoff_rule.get("required_inputs", [])) if isinstance(handoff_rule.get("required_inputs"), list) else [],
        "subagent_boundary": str(handoff_rule.get("subagent_boundary", "")),
        "current_phase": selected.get("current_phase"),
        "next_action": selected.get("next_action"),
        "context_slice": summary.get("context_slice", []),
        "allowed_artifacts": summary.get("allowed_artifacts", []),
        "target_policy": normalize_target_policy(summary.get("target_policy")),
        "user_checkpoint": summary.get("user_checkpoint"),
        "user_loop": {
            "position": str(user_loop.get("position", "")),
            "required_input": str(user_loop.get("required_input", "")),
        },
        "action_route": summary.get("action_route") if isinstance(summary.get("action_route"), dict) else {},
        "safe_to_auto_continue": bool(summary.get("safe_to_auto_continue", False)),
        "requires_user_confirmation": bool(summary.get("requires_user_confirmation", False)),
    }


def _resume_focus_sort_key(run: dict[str, object]) -> tuple[int, int]:
    summary = run.get("resume_summary", {})
    requires_user = bool(isinstance(summary, dict) and summary.get("requires_user_confirmation"))
    status = str(run.get("status", "in_progress"))
    if status == "failed":
        return (0, batch_focus_priority_for_run(run))
    if requires_user:
        return (1, batch_focus_priority_for_run(run))
    return (2, batch_focus_priority_for_run(run))


def _resume_focus_selection_reason(run: dict[str, object], summary: dict[str, object]) -> str:
    if str(run.get("status")) == "failed":
        return "run_failed_or_unreadable"
    if bool(summary.get("requires_user_confirmation")):
        return "requires_user_confirmation"
    if bool(summary.get("safe_to_auto_continue")):
        return "safe_to_auto_continue"
    return "in_progress"


def _next_run_focus(runs: list[dict[str, object]]) -> dict[str, object] | None:
    unreadable = [_run_batch_summary(run) for run in runs if run.get("current_phase") == "unreadable"]
    if unreadable:
        return unreadable[0]
    candidates = [_run_batch_summary(run) for run in runs if run.get("next_action") != "complete"]
    if not candidates:
        return None
    candidates.sort(key=batch_focus_priority_for_run)
    return candidates[0]


def _real_device_preflight_summary(root: Path, run_id: str) -> dict[str, object] | None:
    workflow = inspect_run(root, run_id)
    artifacts = workflow.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return None
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
    return {
        "runtime_mode": payload.get("runtime_mode"),
        "status": payload.get("status"),
        "risk_level": payload.get("risk_level"),
        "mutates_device_state": payload.get("mutates_device_state"),
        "approval_status": payload.get("approval_status"),
        "input_status": payload.get("input_status"),
    }
