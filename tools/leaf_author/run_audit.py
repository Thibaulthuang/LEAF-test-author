from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.batch_registry import inspect_batch
from tools.leaf_author.phase_guard import validate_phase_contract
from tools.leaf_author.real_device_contract import validate_real_device_contract
from tools.leaf_author.reports import report_run
from tools.leaf_author.runtime_registry import runtime_quality_gates, validate_runtime_registry
from tools.leaf_author.workflow import load_workflow, save_workflow


def audit_run(root: Path, run_id: str) -> dict[str, object]:
    report = report_run(root, run_id)
    domain = str(report.get("domain", ""))
    checks = [
        _check("phase_guard", validate_phase_contract().get("status") == "stable", "Phase contract and guard checks are stable."),
        _check("real_device_gate_guard", validate_real_device_contract().get("status") == "stable", "Real-device gate contract is stable."),
        _check("runtime_registry_guard", validate_runtime_registry().get("status") == "stable", "Runtime registry contract is stable."),
        _check("workflow_complete", report.get("current_phase") == "complete", "Workflow current_phase is complete."),
        _check("no_user_action_required", report.get("user_action_required") is False, "No user checkpoint is pending."),
    ]
    latest_quality_gate = str(report.get("latest_quality_gate", ""))
    accepted_gates = runtime_quality_gates(domain)
    if accepted_gates:
        checks.append(_check("runtime_quality_gate", latest_quality_gate in accepted_gates, f"Latest quality gate {latest_quality_gate} is a registered runtime gate."))
    else:
        checks.append(_check("runtime_quality_gate", latest_quality_gate != "UNKNOWN", f"Latest quality gate {latest_quality_gate} is present."))

    preflight = report.get("real_device_preflight")
    checks.extend(_real_device_preflight_checks(preflight if isinstance(preflight, dict) else None))

    passed = all(bool(check["passed"]) for check in checks)
    payload = {
        "schema_version": "1.0",
        "manifest_kind": "leaf_run_audit",
        "run_id": run_id,
        "domain": report.get("domain"),
        "platform": report.get("platform"),
        "status": "passed" if passed else "failed",
        "latest_quality_gate": latest_quality_gate,
        "checks": checks,
        "evidence": {
            "report": "report-run",
            "real_device_preflight": preflight.get("artifact") if isinstance(preflight, dict) else None,
        },
    }
    return _write_run_audit(root, run_id, payload)


def audit_batch(root: Path, batch_id: str) -> dict[str, object]:
    batch = inspect_batch(root, batch_id)
    runs = [audit_run(root, str(run["run_id"])) for run in batch["runs"]]
    passed_count = sum(1 for run in runs if run.get("status") == "passed")
    failed_count = len(runs) - passed_count
    payload = {
        "schema_version": "1.0",
        "manifest_kind": "leaf_batch_audit",
        "batch_id": batch_id,
        "title": batch.get("title", batch_id),
        "status": "passed" if failed_count == 0 else "failed",
        "summary": {
            "total_runs": len(runs),
            "passed": passed_count,
            "failed": failed_count,
        },
        "runs": [
            {
                "run_id": run.get("run_id"),
                "domain": run.get("domain"),
                "status": run.get("status"),
                "latest_quality_gate": run.get("latest_quality_gate"),
                "failed_checks": [check["name"] for check in run.get("checks", []) if isinstance(check, dict) and not check.get("passed")],
            }
            for run in runs
        ],
        "context_policy": {
            "scope": "batch_audit",
            "load_strategy": "summaries_first_then_audit_one_run",
            "artifact_loading": "on_demand",
        },
    }
    return _write_batch_audit(root, batch_id, payload)


def _real_device_preflight_checks(preflight: dict[str, object] | None) -> list[dict[str, object]]:
    if not preflight:
        return [_check("real_device_preflight_ready", False, "Real-device preflight artifact is missing.")]
    return [
        _check("real_device_preflight_ready", preflight.get("status") == "ready", "Real-device preflight status is ready."),
        _check("real_device_input_ready", preflight.get("input_status") == "ready", "Real-device serial/input gate is ready."),
        _check("real_device_approval_ready", preflight.get("approval_status") in {"approved", "not_required"}, "Real-device approval gate is approved or not required."),
    ]


def _check(name: str, passed: bool, message: str) -> dict[str, object]:
    return {
        "name": name,
        "passed": bool(passed),
        "message": message,
    }


def _write_run_audit(root: Path, run_id: str, payload: dict[str, object]) -> dict[str, object]:
    path = root / ".leaf" / "runs" / run_id / "run_audit.json"
    payload["audit_path"] = str(path.relative_to(root))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    artifacts["run_audit"] = str(path.relative_to(root))
    workflow["artifacts"] = artifacts
    save_workflow(root, workflow)
    return payload


def _write_batch_audit(root: Path, batch_id: str, payload: dict[str, object]) -> dict[str, object]:
    path = root / ".leaf" / "batches" / batch_id / "batch_audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["audit_path"] = str(path.relative_to(root))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
