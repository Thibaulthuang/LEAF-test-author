from __future__ import annotations

from pathlib import Path

from tools.leaf_author.phase_guard import validate_phase_contract
from tools.leaf_author.real_device_contract import validate_real_device_contract
from tools.leaf_author.reports import report_run
from tools.leaf_author.runtime_registry import runtime_quality_gates, validate_runtime_registry


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
    return {
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
