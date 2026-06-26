from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.agent_handoff import AGENT_MODES, HANDOFF_RULES
from tools.leaf_author.device_probe import HdcProbe, ProbeRunner
from tools.leaf_author.phase_guard import validate_phase_contract
from tools.leaf_author.real_device_contract import real_device_runtime_evidence_schema, validate_real_device_contract
from tools.leaf_author.reports import report_run
from tools.leaf_author.runtime_registry import runtime_quality_gates, runtime_safety_profile, validate_runtime_registry
from tools.leaf_author.workflow import load_workflow, save_workflow
from tools.leaf_author.batch_registry import resume_batch


def audit_run(
    root: Path,
    run_id: str,
    *,
    live_device: bool = False,
    hdc_runner: ProbeRunner | None = None,
    hdc_path: str = "hdc",
) -> dict[str, object]:
    initial_workflow_phase_state = _load_workflow_phase_state(root, run_id)
    initial_context_manifest = _load_context_manifest_from_workflow(root, run_id)
    report = report_run(root, run_id)
    domain = str(report.get("domain", ""))
    checks = [
        _check("phase_guard", validate_phase_contract().get("status") == "stable", "Phase contract and guard checks are stable."),
        _check("real_device_gate_guard", validate_real_device_contract().get("status") == "stable", "Real-device gate contract is stable."),
        _check("runtime_registry_guard", validate_runtime_registry().get("status") == "stable", "Runtime registry contract is stable."),
        _check("workflow_readable", report.get("current_phase") != "unreadable", "Workflow state is readable."),
        _check("workflow_complete", report.get("current_phase") == "complete", "Workflow current_phase is complete."),
        _check("no_user_action_required", report.get("user_action_required") is False, "No user checkpoint is pending."),
    ]
    latest_quality_gate = str(report.get("latest_quality_gate", ""))
    accepted_gates = runtime_quality_gates(domain)
    if accepted_gates:
        checks.append(_check("runtime_quality_gate", latest_quality_gate in accepted_gates, f"Latest quality gate {latest_quality_gate} is a registered runtime gate."))
    else:
        checks.append(_check("runtime_quality_gate", latest_quality_gate != "UNKNOWN", f"Latest quality gate {latest_quality_gate} is present."))

    device_selection = report.get("device_selection")
    preflight = report.get("real_device_preflight")
    checks.extend(_real_device_preflight_checks(domain, preflight if isinstance(preflight, dict) else None, device_selection if isinstance(device_selection, dict) else None))
    live_device_result = _live_device_result(preflight if isinstance(preflight, dict) else None, live_device=live_device, hdc_runner=hdc_runner, hdc_path=hdc_path)
    checks.extend(_live_device_checks(live_device_result, enabled=live_device))
    checks.extend(_device_selection_checks(device_selection if isinstance(device_selection, dict) else None, preflight if isinstance(preflight, dict) else None))
    evidence = report.get("evidence", {})
    real_device_approval = _load_real_device_approval(root, evidence if isinstance(evidence, dict) else {})
    checks.extend(_real_device_approval_checks(real_device_approval, preflight if isinstance(preflight, dict) else None))
    real_device_input = _load_real_device_input(root, evidence if isinstance(evidence, dict) else {})
    checks.extend(
        _real_device_input_checks(
            real_device_input,
            preflight if isinstance(preflight, dict) else None,
            device_selection if isinstance(device_selection, dict) else None,
        )
    )
    runtime_evidence = _load_runtime_evidence(root, evidence if isinstance(evidence, dict) else {}, domain, preflight if isinstance(preflight, dict) else None)
    checks.extend(_runtime_evidence_checks(root, runtime_evidence, latest_quality_gate))
    checks.extend(_real_device_plan_confirmation_checks(report, preflight if isinstance(preflight, dict) else None, real_device_input, runtime_evidence))
    refreshed_context_manifest = _load_context_manifest_from_workflow(root, run_id) or _load_context_manifest(root, evidence if isinstance(evidence, dict) else {})
    context_manifest = _auditable_context_manifest(initial_context_manifest, refreshed_context_manifest)
    checks.extend(_context_manifest_checks(context_manifest, report))
    workflow_phase_state = initial_workflow_phase_state if _has_phase_state_snapshot(initial_workflow_phase_state) else _load_workflow_phase_state(root, run_id)
    checks.extend(_workflow_phase_state_checks(workflow_phase_state, context_manifest, report))
    workflow_diagnostics = _load_workflow_diagnostics(root, evidence if isinstance(evidence, dict) else {})
    checks.extend(_workflow_diagnostics_checks(workflow_diagnostics))
    ui_tree_diagnostics = _load_ui_tree_diagnostics(root, evidence if isinstance(evidence, dict) else {})
    checks.extend(_ui_tree_diagnostics_checks(root, ui_tree_diagnostics, runtime_evidence, run_id))
    real_device_trace = _real_device_trace(
        latest_quality_gate=latest_quality_gate,
        device_selection=device_selection if isinstance(device_selection, dict) else None,
        real_device_approval=real_device_approval,
        real_device_input=real_device_input,
        preflight=preflight if isinstance(preflight, dict) else None,
        live_device_result=live_device_result,
    )
    runtime_evidence_trace = _runtime_evidence_trace(runtime_evidence, checks)

    passed = all(bool(check["passed"]) for check in checks)
    payload = {
        "schema_version": "1.0",
        "manifest_kind": "leaf_run_audit",
        "run_id": run_id,
        "domain": report.get("domain"),
        "platform": report.get("platform"),
        "status": "passed" if passed else "failed",
        "current_phase": report.get("current_phase"),
        "next_action": report.get("next_action"),
        "latest_quality_gate": latest_quality_gate,
        "real_device_trace": real_device_trace,
        "runtime_evidence_trace": runtime_evidence_trace,
        "checks": checks,
        "evidence": {
            "report": "report-run",
            "device_selection": device_selection.get("artifact") if isinstance(device_selection, dict) else None,
            "real_device_approval": real_device_approval.get("artifact") if isinstance(real_device_approval, dict) else None,
            "real_device_input": real_device_input.get("artifact") if isinstance(real_device_input, dict) else None,
            "real_device_preflight": preflight.get("artifact") if isinstance(preflight, dict) else None,
            "runtime_evidence": runtime_evidence.get("artifact") if isinstance(runtime_evidence, dict) else None,
            "context_manifest": context_manifest.get("artifact") if isinstance(context_manifest, dict) else None,
            "workflow_phase_state": workflow_phase_state.get("artifact") if isinstance(workflow_phase_state, dict) else None,
            "workflow_diagnostics": workflow_diagnostics.get("artifact") if isinstance(workflow_diagnostics, dict) else None,
            "ui_tree_diagnostics": ui_tree_diagnostics.get("artifact") if isinstance(ui_tree_diagnostics, dict) else None,
        },
    }
    return _write_run_audit(root, run_id, payload)


def audit_batch(
    root: Path,
    batch_id: str,
    *,
    live_device: bool = False,
    hdc_runner: ProbeRunner | None = None,
    hdc_path: str = "hdc",
) -> dict[str, object]:
    batch = _load_batch_manifest(root, batch_id)
    run_ids = [str(run_id) for run_id in batch.get("run_ids", [])] if isinstance(batch.get("run_ids"), list) else []
    runs = [_audit_batch_run(root, run_id, live_device=live_device, hdc_runner=hdc_runner, hdc_path=hdc_path) for run_id in run_ids]
    passed_count = sum(1 for run in runs if run.get("status") == "passed")
    failed_count = len(runs) - passed_count
    resume_view = _load_batch_resume_view(root, batch_id)
    batch_checks = _batch_resume_checks(resume_view)
    batch_failed_count = sum(1 for check in batch_checks if not check.get("passed"))
    payload = {
        "schema_version": "1.0",
        "manifest_kind": "leaf_batch_audit",
        "batch_id": batch_id,
        "title": batch.get("title", batch_id),
        "status": "passed" if failed_count == 0 and batch_failed_count == 0 else "failed",
        "summary": {
            "total_runs": len(runs),
            "passed": passed_count,
            "failed": failed_count,
        },
        "real_device_summary": _batch_real_device_summary(runs),
        "runtime_evidence_summary": _batch_runtime_evidence_summary(runs),
        "batch_checks": batch_checks,
        "focus_plan": resume_view.get("focus_plan") if isinstance(resume_view, dict) else None,
        "runs": [
            {
                "run_id": run.get("run_id"),
                "domain": run.get("domain"),
                "status": run.get("status"),
                "latest_quality_gate": run.get("latest_quality_gate"),
                "real_device_trace": run.get("real_device_trace") if isinstance(run.get("real_device_trace"), dict) else None,
                "runtime_evidence_trace": run.get("runtime_evidence_trace") if isinstance(run.get("runtime_evidence_trace"), dict) else None,
                "failed_checks": [check["name"] for check in run.get("checks", []) if isinstance(check, dict) and not check.get("passed")],
                **({"error": run["error"]} if isinstance(run.get("error"), dict) else {}),
            }
            for run in runs
        ],
        "context_policy": {
            "scope": "batch_audit",
            "load_strategy": "summaries_first_then_audit_one_run",
            "artifact_loading": "on_demand",
            "attention_boundary": _batch_resume_attention_boundary(resume_view),
        },
    }
    return _write_batch_audit(root, batch_id, payload)


def _real_device_preflight_checks(domain: str, preflight: dict[str, object] | None, device_selection: dict[str, object] | None = None) -> list[dict[str, object]]:
    if not preflight:
        return [_check("real_device_preflight_ready", False, "Real-device preflight artifact is missing.")]
    safety_matches = _preflight_safety_matches_registry(domain, preflight)
    checks = [
        _check("real_device_preflight_ready", preflight.get("status") == "ready", "Real-device preflight status is ready."),
        _check("real_device_input_ready", preflight.get("input_status") == "ready", "Real-device serial/input gate is ready."),
        _check("real_device_approval_ready", preflight.get("approval_status") in {"approved", "not_required"}, "Real-device approval gate is approved or not required."),
        _check("real_device_safety_profile", safety_matches, "Real-device preflight safety fields match the runtime registry profile."),
    ]
    if device_selection and preflight.get("serial_source") == "device_selection":
        checks.append(
            _check(
                "real_device_preflight_source_matches_selection",
                preflight.get("device_selection_artifact") == device_selection.get("artifact")
                and preflight.get("serial") == device_selection.get("serial"),
                "Real-device preflight source points to the selected device artifact.",
            )
        )
    return checks


def _preflight_safety_matches_registry(domain: str, preflight: dict[str, object]) -> bool:
    runtime_mode = preflight.get("runtime_mode")
    if not isinstance(runtime_mode, str) or not runtime_mode:
        return False
    safety = runtime_safety_profile(domain, runtime_mode)
    required_token = safety.get("requires_approval_token")
    expected_approval_status = "approved" if required_token else "not_required"
    return (
        preflight.get("risk_level") == safety.get("risk_level")
        and preflight.get("mutates_device_state") == safety.get("mutates_device_state")
        and preflight.get("required_approval_token") == required_token
        and preflight.get("approval_status") == expected_approval_status
        and (not required_token or preflight.get("approval_token") == required_token)
    )


def _live_device_result(
    preflight: dict[str, object] | None,
    *,
    live_device: bool,
    hdc_runner: ProbeRunner | None,
    hdc_path: str,
) -> dict[str, object] | None:
    if not live_device:
        return None
    serial = preflight.get("serial") if isinstance(preflight, dict) else None
    if not isinstance(serial, str) or not serial.strip():
        return {
            "status": "unavailable",
            "serial": serial,
            "reason": "preflight serial is missing",
        }
    selection = HdcProbe(runner=hdc_runner, hdc_path=hdc_path).select_device(serial=serial.strip())
    if selection.get("status") != "selected":
        return {
            "status": "unavailable",
            "serial": serial.strip(),
            "reason": selection.get("reason"),
            "targets": selection.get("targets", []),
        }
    return {
        "status": "connected",
        "serial": selection.get("serial"),
        "targets": selection.get("targets", []),
        "device": selection.get("device") if isinstance(selection.get("device"), dict) else {},
    }


def _live_device_checks(live_device_result: dict[str, object] | None, *, enabled: bool) -> list[dict[str, object]]:
    if not enabled:
        return []
    return [
        _check(
            "real_device_live_connected",
            isinstance(live_device_result, dict) and live_device_result.get("status") == "connected",
            "Preflight serial is currently connected through hdc.",
        )
    ]


def _device_selection_checks(device_selection: dict[str, object] | None, preflight: dict[str, object] | None) -> list[dict[str, object]]:
    if not device_selection:
        return []
    checks = [
        _check("device_selection_ready", device_selection.get("status") == "selected", "Device selection artifact selected a concrete hdc target."),
    ]
    if preflight:
        checks.append(
            _check(
                "device_selection_matches_preflight",
                device_selection.get("serial") == preflight.get("serial"),
                "Device selection serial matches real-device preflight serial.",
            )
        )
    return checks


def _load_real_device_approval(root: Path, evidence: dict[str, object]) -> dict[str, object] | None:
    value = evidence.get("real_device_approval")
    if not isinstance(value, str) or not value:
        return None
    path = root / value
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"artifact": value, "status": "invalid", "error": {"type": "JSONDecodeError", "message": "real_device_approval is not valid JSON"}}
    if not isinstance(payload, dict):
        return {"artifact": value, "status": "invalid", "error": {"type": "TypeError", "message": "real_device_approval must be a JSON object"}}
    payload["artifact"] = value
    return payload


def _real_device_approval_checks(
    real_device_approval: dict[str, object] | None,
    preflight: dict[str, object] | None,
) -> list[dict[str, object]]:
    if not preflight or not preflight.get("required_approval_token"):
        return []
    checks = [
        _check(
            "real_device_approval_artifact_ready",
            isinstance(real_device_approval, dict) and real_device_approval.get("status") == "approved",
            "Real-device approval artifact records approved operator consent.",
        )
    ]
    checks.append(
        _check(
            "real_device_approval_matches_preflight",
            _approval_matches_preflight(real_device_approval, preflight),
            "Real-device approval artifact matches preflight runtime mode and approval token.",
        )
    )
    return checks


def _approval_matches_preflight(real_device_approval: dict[str, object] | None, preflight: dict[str, object]) -> bool:
    if not isinstance(real_device_approval, dict):
        return False
    return (
        real_device_approval.get("runtime_mode") == preflight.get("runtime_mode")
        and real_device_approval.get("required_approval_token") == preflight.get("required_approval_token")
        and real_device_approval.get("approval_token") == preflight.get("approval_token")
        and real_device_approval.get("status") == "approved"
        and preflight.get("approval_status") == "approved"
    )


def _load_real_device_input(root: Path, evidence: dict[str, object]) -> dict[str, object] | None:
    value = evidence.get("real_device_input")
    if not isinstance(value, str) or not value:
        return None
    path = root / value
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"artifact": value, "status": "invalid", "error": {"type": "JSONDecodeError", "message": "real_device_input is not valid JSON"}}
    if not isinstance(payload, dict):
        return {"artifact": value, "status": "invalid", "error": {"type": "TypeError", "message": "real_device_input must be a JSON object"}}
    payload["artifact"] = value
    return payload


def _real_device_input_checks(
    real_device_input: dict[str, object] | None,
    preflight: dict[str, object] | None,
    device_selection: dict[str, object] | None,
) -> list[dict[str, object]]:
    if not real_device_input:
        return []
    checks = [
        _check("real_device_input_artifact_ready", real_device_input.get("status") == "ready", "Real-device input artifact records ready serial input."),
    ]
    if preflight:
        checks.append(
            _check(
                "real_device_input_matches_preflight",
                real_device_input.get("serial") == preflight.get("serial"),
                "Real-device input serial matches preflight serial.",
            )
        )
    if device_selection and real_device_input.get("serial_source") == "device_selection":
        checks.append(
            _check(
                "real_device_input_source_matches_selection",
                real_device_input.get("device_selection_artifact") == device_selection.get("artifact")
                and real_device_input.get("serial") == device_selection.get("serial"),
                "Real-device input source points to the selected device artifact.",
            )
        )
    return checks


def _load_runtime_evidence(
    root: Path,
    evidence: dict[str, object],
    domain: str,
    preflight: dict[str, object] | None,
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
            "status": "invalid",
            "schema": None,
            "artifact": None,
            "error": {"type": "ValueError", "message": f"runtime evidence schema is missing for {domain}.{runtime_mode}"},
        }
    artifact_key = schema.get("artifact")
    value = evidence.get(str(artifact_key))
    if not isinstance(value, str) or not value:
        return {"status": "missing", "schema": schema, "artifact": None}
    path = root / value
    if not path.is_file():
        return {"status": "missing", "schema": schema, "artifact": value}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "invalid", "schema": schema, "artifact": value, "error": {"type": "JSONDecodeError", "message": "runtime evidence is not valid JSON"}}
    if not isinstance(payload, dict):
        return {"status": "invalid", "schema": schema, "artifact": value, "error": {"type": "TypeError", "message": "runtime evidence must be a JSON object"}}
    payload["artifact"] = value
    payload["schema"] = schema
    payload["status"] = payload.get("status")
    return payload


def _runtime_evidence_checks(root: Path, runtime_evidence: dict[str, object] | None, latest_quality_gate: str) -> list[dict[str, object]]:
    if not runtime_evidence:
        return []
    schema = runtime_evidence.get("schema")
    if not isinstance(schema, dict):
        return [_check("runtime_evidence_schema_ready", False, "Runtime evidence schema is registered for the preflight runtime mode.")]
    evidence = runtime_evidence.get("evidence", {})
    evidence = evidence if isinstance(evidence, dict) else {}
    required_fields = [str(field) for field in schema.get("required_evidence_fields", [])] if isinstance(schema.get("required_evidence_fields"), list) else []
    missing_fields = [field for field in required_fields if field not in evidence]
    ui_snapshot_refs = evidence.get("ui_snapshot_refs")
    return [
        _check("runtime_evidence_artifact_ready", runtime_evidence.get("artifact") is not None and runtime_evidence.get("status") == "complete", "Runtime evidence artifact is present and complete."),
        _check(
            "runtime_evidence_quality_gate",
            runtime_evidence.get("quality_gate") == schema.get("quality_gate") == latest_quality_gate,
            "Runtime evidence quality gate matches the registered schema and latest report gate.",
        ),
        _check(
            "runtime_evidence_required_fields",
            not missing_fields,
            "Runtime evidence includes required schema fields." if not missing_fields else f"Runtime evidence missing fields: {', '.join(missing_fields)}.",
        ),
        _check(
            "runtime_evidence_ui_snapshots_ready",
            _ui_snapshot_refs_ready(root, ui_snapshot_refs),
            "Runtime evidence links parseable UI snapshot raw and index artifacts.",
        ),
    ]


def _real_device_plan_confirmation_checks(
    report: dict[str, object],
    preflight: dict[str, object] | None,
    real_device_input: dict[str, object] | None,
    runtime_evidence: dict[str, object] | None,
) -> list[dict[str, object]]:
    has_real_device_artifacts = any(
        [
            isinstance(preflight, dict) and bool(preflight.get("artifact")),
            isinstance(real_device_input, dict) and bool(real_device_input.get("artifact")),
            isinstance(runtime_evidence, dict) and bool(runtime_evidence.get("artifact")),
        ]
    )
    return [
        _check(
            "real_device_requires_confirmed_plan",
            not has_real_device_artifacts or report.get("confirmed_plan") is True,
            "Real-device input, preflight, and runtime evidence must not exist before first plan confirmation.",
        )
    ]


def _runtime_evidence_trace(runtime_evidence: dict[str, object] | None, checks: list[dict[str, object]]) -> dict[str, object] | None:
    if not runtime_evidence:
        return None
    schema = runtime_evidence.get("schema")
    schema = schema if isinstance(schema, dict) else {}
    evidence = runtime_evidence.get("evidence", {})
    evidence = evidence if isinstance(evidence, dict) else {}
    required_fields = [str(field) for field in schema.get("required_evidence_fields", [])] if isinstance(schema.get("required_evidence_fields"), list) else []
    runtime_check_names = {
        "runtime_evidence_schema_ready",
        "runtime_evidence_artifact_ready",
        "runtime_evidence_quality_gate",
        "runtime_evidence_required_fields",
        "runtime_evidence_ui_snapshots_ready",
    }
    failed_checks = [
        str(check.get("name"))
        for check in checks
        if isinstance(check, dict) and check.get("name") in runtime_check_names and not check.get("passed")
    ]
    return {
        "artifact": runtime_evidence.get("artifact"),
        "quality_gate": runtime_evidence.get("quality_gate"),
        "expected_quality_gate": schema.get("quality_gate"),
        "required_evidence_fields": required_fields,
        "missing_required_fields": [field for field in required_fields if field not in evidence],
        "ui_snapshot_ref_count": len(evidence.get("ui_snapshot_refs", [])) if isinstance(evidence.get("ui_snapshot_refs"), list) else 0,
        "failed_checks": failed_checks,
    }


def _ui_snapshot_refs_ready(root: Path, ui_snapshot_refs: object) -> bool:
    if not isinstance(ui_snapshot_refs, list) or not ui_snapshot_refs:
        return False
    for item in ui_snapshot_refs:
        if not isinstance(item, dict):
            return False
        raw_path = item.get("raw_path")
        index_path = item.get("index_path")
        if not isinstance(raw_path, str) or not isinstance(index_path, str):
            return False
        if not (root / raw_path).is_file() or not (root / index_path).is_file():
            return False
        try:
            index_payload = json.loads((root / index_path).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        if not isinstance(index_payload, dict) or index_payload.get("kind") != "ui_snapshot":
            return False
    return True


def _real_device_trace(
    *,
    latest_quality_gate: str,
    device_selection: dict[str, object] | None,
    real_device_approval: dict[str, object] | None,
    real_device_input: dict[str, object] | None,
    preflight: dict[str, object] | None,
    live_device_result: dict[str, object] | None = None,
) -> dict[str, object]:
    artifacts = {
        "device_selection": device_selection.get("artifact") if isinstance(device_selection, dict) else None,
        "real_device_approval": real_device_approval.get("artifact") if isinstance(real_device_approval, dict) else None,
        "real_device_input": real_device_input.get("artifact") if isinstance(real_device_input, dict) else None,
        "real_device_preflight": preflight.get("artifact") if isinstance(preflight, dict) else None,
    }
    serial = None
    serial_source = None
    runtime_mode = None
    if isinstance(preflight, dict):
        serial = preflight.get("serial")
        serial_source = preflight.get("serial_source")
        runtime_mode = preflight.get("runtime_mode")
    if serial is None and isinstance(real_device_input, dict):
        serial = real_device_input.get("serial")
    if serial_source is None and isinstance(real_device_input, dict):
        serial_source = real_device_input.get("serial_source")
    if runtime_mode is None and isinstance(real_device_input, dict):
        runtime_mode = real_device_input.get("runtime_mode")
    if serial is None and isinstance(device_selection, dict):
        serial = device_selection.get("serial")
    return {
        "serial": serial,
        "serial_source": serial_source,
        "runtime_mode": runtime_mode,
        "risk_level": preflight.get("risk_level") if isinstance(preflight, dict) else None,
        "mutates_device_state": preflight.get("mutates_device_state") if isinstance(preflight, dict) else None,
        "required_approval_token": preflight.get("required_approval_token") if isinstance(preflight, dict) else None,
        "approval_status": preflight.get("approval_status") if isinstance(preflight, dict) else None,
        "live_device": live_device_result,
        "latest_quality_gate": latest_quality_gate,
        "artifacts": artifacts,
    }


def _load_context_manifest(root: Path, evidence: dict[str, object]) -> dict[str, object] | None:
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
    if not isinstance(payload, dict):
        return None
    payload["artifact"] = value
    return payload


def _load_context_manifest_from_workflow(root: Path, run_id: str) -> dict[str, object] | None:
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    if not workflow_path.is_file():
        return None
    try:
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(workflow, dict):
        return None
    artifacts = workflow.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    return _load_context_manifest(root, artifacts)


def _auditable_context_manifest(
    initial_context_manifest: dict[str, object] | None,
    refreshed_context_manifest: dict[str, object] | None,
) -> dict[str, object] | None:
    if not isinstance(initial_context_manifest, dict):
        return refreshed_context_manifest
    if not isinstance(refreshed_context_manifest, dict):
        return initial_context_manifest
    if not _legacy_context_manifest_can_refresh(initial_context_manifest):
        return initial_context_manifest
    return refreshed_context_manifest


def _legacy_context_manifest_can_refresh(context_manifest: dict[str, object]) -> bool:
    handoff = context_manifest.get("handoff")
    if not isinstance(handoff, dict):
        return False
    target_policy = context_manifest.get("target_policy")
    handoff_target_policy = handoff.get("target_policy")
    if target_policy is not None or handoff_target_policy is not None:
        return False
    return True


def _load_workflow_diagnostics(root: Path, evidence: dict[str, object]) -> dict[str, object] | None:
    value = evidence.get("workflow_diagnostics")
    if not isinstance(value, str) or not value:
        return None
    path = root / value
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"artifact": value, "status": "failed", "error": {"type": "JSONDecodeError", "message": "workflow diagnostics is not valid JSON"}}
    if not isinstance(payload, dict):
        return {"artifact": value, "status": "failed", "error": {"type": "TypeError", "message": "workflow diagnostics must be a JSON object"}}
    payload["artifact"] = value
    return payload


def _workflow_diagnostics_checks(workflow_diagnostics: dict[str, object] | None) -> list[dict[str, object]]:
    if not workflow_diagnostics:
        return []
    checks = workflow_diagnostics.get("checks", {})
    return [
        _check("workflow_diagnostics_ready", workflow_diagnostics.get("status") == "passed", "Workflow diagnostics artifact reports a readable workflow."),
        _check("workflow_diagnostics_parseable", bool(isinstance(checks, dict) and checks.get("json_parseable")), "Workflow diagnostics confirms workflow.json parses as JSON."),
    ]


def _load_ui_tree_diagnostics(root: Path, evidence: dict[str, object]) -> dict[str, object] | None:
    value = evidence.get("ui_tree_diagnostics")
    if not isinstance(value, str) or not value:
        return None
    path = root / value
    if not path.is_file():
        return {"artifact": value, "status": "failed", "error": {"type": "FileNotFoundError", "message": "ui tree diagnostics artifact is missing"}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"artifact": value, "status": "failed", "error": {"type": "JSONDecodeError", "message": "ui tree diagnostics is not valid JSON"}}
    if not isinstance(payload, dict):
        return {"artifact": value, "status": "failed", "error": {"type": "TypeError", "message": "ui tree diagnostics must be a JSON object"}}
    payload["artifact"] = value
    return payload


def _ui_tree_diagnostics_checks(
    root: Path,
    ui_tree_diagnostics: dict[str, object] | None,
    runtime_evidence: dict[str, object] | None,
    run_id: str,
) -> list[dict[str, object]]:
    if not ui_tree_diagnostics:
        return []
    snapshots = ui_tree_diagnostics.get("snapshots")
    snapshots = snapshots if isinstance(snapshots, list) else []
    diffs = ui_tree_diagnostics.get("diffs")
    diff_count_matches = not isinstance(diffs, list) or ui_tree_diagnostics.get("diff_count") == len(diffs)
    ready = (
        ui_tree_diagnostics.get("manifest_kind") == "leaf_ui_tree_diagnostics"
        and ui_tree_diagnostics.get("run_id") == run_id
        and isinstance(ui_tree_diagnostics.get("snapshot_count"), int)
        and ui_tree_diagnostics.get("snapshot_count") == len(snapshots)
        and diff_count_matches
    )
    return [
        _check("ui_tree_diagnostics_ready", ready, "UI tree diagnostics artifact is typed and internally consistent."),
        _check(
            "ui_tree_diagnostics_indexes_ready",
            _ui_tree_diagnostics_indexes_ready(root, snapshots),
            "UI tree diagnostics references parseable raw and indexed UI snapshots.",
        ),
        _check(
            "ui_tree_diagnostics_matches_runtime_evidence",
            _ui_tree_diagnostics_matches_runtime_evidence(snapshots, runtime_evidence),
            "UI tree diagnostics snapshots are a subset of runtime evidence UI snapshot refs.",
        ),
    ]


def _ui_tree_diagnostics_indexes_ready(root: Path, snapshots: list[object]) -> bool:
    if not snapshots:
        return False
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            return False
        raw_path = snapshot.get("raw_path")
        index_path = snapshot.get("index_path")
        if not isinstance(raw_path, str) or not isinstance(index_path, str):
            return False
        if snapshot.get("index_status") != "ready":
            return False
        if not (root / raw_path).is_file() or not (root / index_path).is_file():
            return False
        try:
            index_payload = json.loads((root / index_path).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        if not isinstance(index_payload, dict) or index_payload.get("kind") != "ui_snapshot":
            return False
    return True


def _ui_tree_diagnostics_matches_runtime_evidence(snapshots: list[object], runtime_evidence: dict[str, object] | None) -> bool:
    if not snapshots or not isinstance(runtime_evidence, dict):
        return False
    evidence = runtime_evidence.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    refs = evidence.get("ui_snapshot_refs")
    if not isinstance(refs, list) or not refs:
        return False
    runtime_pairs = {
        (ref.get("raw_path"), ref.get("index_path"))
        for ref in refs
        if isinstance(ref, dict) and isinstance(ref.get("raw_path"), str) and isinstance(ref.get("index_path"), str)
    }
    if not runtime_pairs:
        return False
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            return False
        pair = (snapshot.get("raw_path"), snapshot.get("index_path"))
        if pair not in runtime_pairs:
            return False
    return True


def _context_manifest_checks(context_manifest: dict[str, object] | None, report: dict[str, object]) -> list[dict[str, object]]:
    if not context_manifest:
        return [
            _check("context_manifest_ready", False, "Context manifest artifact is missing or unreadable."),
            _check("handoff_ready", False, "Context manifest handoff snapshot is missing."),
            _check("user_loop_ready", False, "Context manifest user_loop snapshot is missing."),
            _check("context_slice_bounded", False, "Context manifest context slice is missing."),
            _check("referenced_artifacts_bounded", False, "Context manifest referenced artifacts are missing."),
            _check("context_manifest_matches_phase_contract", False, "Context manifest phase decision is missing."),
            _check("trigger_source_stable", False, "Context manifest trigger source is missing."),
            _check("target_policy_handoff_ready", False, "Context manifest target policy is missing."),
            _check("agent_mode_handoff_ready", False, "Context manifest agent mode handoff rule is missing."),
            _check("user_checkpoint_auto_boundary", False, "Context manifest user checkpoint boundary is missing."),
            _check("gui_agent_ui_tree_context", False, "Context manifest GUI agent context is missing."),
        ]
    handoff = context_manifest.get("handoff")
    user_loop = context_manifest.get("user_loop")
    decision_contract = report.get("decision_contract", {})
    if not isinstance(decision_contract, dict):
        decision_contract = {}
    context_slice = _string_list(context_manifest.get("context_slice"))
    handoff_context_slice = _string_list(handoff.get("context_slice") if isinstance(handoff, dict) else None)
    contract_context_slice = _string_list(decision_contract.get("context_slice"))
    allowed_artifacts = _string_list(handoff.get("allowed_artifacts") if isinstance(handoff, dict) else None)
    contract_allowed_artifacts = _string_list(decision_contract.get("allowed_artifacts"))
    referenced_artifacts = context_manifest.get("referenced_artifacts")
    referenced_artifacts = referenced_artifacts if isinstance(referenced_artifacts, dict) else {}
    exposed_artifacts = set(context_slice) | set(allowed_artifacts) | {"workflow", "context_manifest"}
    referenced_artifacts_bounded = all(str(key) in exposed_artifacts for key in referenced_artifacts)
    trigger_source = context_manifest.get("trigger_source")
    handoff_trigger_source = handoff.get("trigger_source") if isinstance(handoff, dict) else None
    contract_trigger_source = decision_contract.get("trigger_source")
    target_policy = context_manifest.get("target_policy")
    handoff_target_policy = handoff.get("target_policy") if isinstance(handoff, dict) else None
    user_checkpoint = context_manifest.get("user_checkpoint")
    requires_user_confirmation = isinstance(user_loop, dict) and bool(user_loop.get("requires_user_confirmation"))
    safe_to_auto_continue = isinstance(user_loop, dict) and bool(user_loop.get("safe_to_auto_continue"))
    agent_owner = str(context_manifest.get("agent_owner", ""))
    expected_agent_mode = AGENT_MODES.get(agent_owner)
    expected_handoff_rule = HANDOFF_RULES.get(agent_owner, {})
    agent_mode_handoff_ready = (
        isinstance(handoff, dict)
        and expected_agent_mode is not None
        and context_manifest.get("agent_mode") == expected_agent_mode
        and handoff.get("agent_mode") == expected_agent_mode
        and handoff.get("handoff_required") == expected_handoff_rule.get("handoff_required")
        and handoff.get("required_inputs") == expected_handoff_rule.get("required_inputs")
        and handoff.get("subagent_boundary") == expected_handoff_rule.get("subagent_boundary")
    )
    manifest_matches_phase_contract = (
        context_manifest.get("current_phase") == report.get("current_phase")
        and context_manifest.get("next_action") == report.get("next_action")
        and agent_owner == decision_contract.get("agent_owner")
        and context_slice == contract_context_slice
        and context_manifest.get("user_checkpoint") == report.get("user_checkpoint")
        and bool(context_manifest.get("safe_to_auto_continue")) == bool(report.get("safe_to_auto_continue"))
        and isinstance(user_loop, dict)
        and user_loop.get("position") == report.get("user_loop", {}).get("position")
        and user_loop.get("required_input") == report.get("user_loop", {}).get("required_input")
    )
    handoff_ready = (
        isinstance(handoff, dict)
        and handoff.get("to_agent") == decision_contract.get("agent_owner")
        and handoff.get("current_phase") == report.get("current_phase")
        and handoff.get("next_action") == report.get("next_action")
        and handoff.get("attention_boundary") == "one_active_run"
        and handoff.get("artifact_loading") == "on_demand"
    )
    user_loop_ready = (
        isinstance(user_loop, dict)
        and "requires_user_confirmation" in user_loop
        and "safe_to_auto_continue" in user_loop
        and user_loop.get("requires_user_confirmation") == report.get("user_action_required")
        and user_loop.get("safe_to_auto_continue") == report.get("safe_to_auto_continue")
    )
    return [
        _check("context_manifest_ready", context_manifest.get("manifest_kind") == "run_context_manifest", "Context manifest artifact is present and typed."),
        _check("handoff_ready", handoff_ready, "Context manifest handoff matches the report decision contract."),
        _check("user_loop_ready", user_loop_ready, "Context manifest user_loop matches report checkpoint and auto-continue state."),
        _check(
            "context_slice_bounded",
            context_slice == handoff_context_slice == contract_context_slice,
            "Context manifest loads exactly the phase decision context slice.",
        ),
        _check(
            "allowed_artifacts_bounded",
            allowed_artifacts == contract_allowed_artifacts,
            "Context manifest allowed artifacts match the phase decision contract.",
        ),
        _check(
            "referenced_artifacts_bounded",
            referenced_artifacts_bounded,
            "Context manifest references only workflow, context manifest, context-slice artifacts, or allowed artifacts.",
        ),
        _check(
            "context_manifest_matches_phase_contract",
            manifest_matches_phase_contract,
            "Context manifest top-level decision matches the current phase contract.",
        ),
        _check(
            "trigger_source_stable",
            trigger_source == handoff_trigger_source == contract_trigger_source == "workflow.json",
            "Context manifest, handoff, and decision contract all use workflow.json as the trigger source.",
        ),
        _check(
            "target_policy_handoff_ready",
            _target_policy_handoff_ready(target_policy, handoff_target_policy),
            "Context manifest and handoff keep the system-app-only target policy stable.",
        ),
        _check(
            "agent_mode_handoff_ready",
            agent_mode_handoff_ready,
            "Context manifest and handoff keep the expected agent mode and subagent handoff rule stable.",
        ),
        _check(
            "user_checkpoint_auto_boundary",
            not ((user_checkpoint or requires_user_confirmation) and safe_to_auto_continue),
            "Context manifest never marks a user checkpoint safe for automatic continuation.",
        ),
        _check(
            "gui_agent_ui_tree_context",
            agent_owner != "leaf-gui-agent" or "ui_tree" in context_slice,
            "GUI agent handoffs include ui_tree in the bounded context slice.",
        ),
    ]


def _target_policy_handoff_ready(target_policy: object, handoff_target_policy: object) -> bool:
    if not isinstance(target_policy, dict) or not isinstance(handoff_target_policy, dict):
        return False
    return target_policy == handoff_target_policy and target_policy.get("scope") == "system_app_only"


def _load_workflow_phase_state(root: Path, run_id: str) -> dict[str, object] | None:
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    if not workflow_path.is_file():
        return None
    try:
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(workflow, dict):
        return None
    phase_state = workflow.get("phase_state")
    if not isinstance(phase_state, dict):
        return {"artifact": str(workflow_path.relative_to(root)), "phase_state": None}
    return {"artifact": str(workflow_path.relative_to(root)), "phase_state": phase_state}


def _has_phase_state_snapshot(workflow_phase_state: dict[str, object] | None) -> bool:
    return isinstance(workflow_phase_state, dict) and isinstance(workflow_phase_state.get("phase_state"), dict)


def _workflow_phase_state_checks(
    workflow_phase_state: dict[str, object] | None,
    context_manifest: dict[str, object] | None,
    report: dict[str, object],
) -> list[dict[str, object]]:
    if not workflow_phase_state:
        return [_check("workflow_phase_state_ready", False, "Workflow phase_state snapshot is missing or unreadable.")]
    phase_state = workflow_phase_state.get("phase_state")
    if not isinstance(phase_state, dict):
        return [_check("workflow_phase_state_ready", False, "Workflow phase_state snapshot is missing or not an object.")]
    ready = (
        phase_state.get("current_phase") == report.get("current_phase")
        and phase_state.get("next_action") == report.get("next_action")
        and phase_state.get("agent_owner") == report.get("decision_contract", {}).get("agent_owner")
        and phase_state.get("safe_to_auto_continue") == report.get("safe_to_auto_continue")
        and isinstance(phase_state.get("user_loop"), dict)
    )
    manifest_match = _phase_state_matches_manifest(phase_state, context_manifest)
    return [
        _check("workflow_phase_state_ready", ready, "Workflow phase_state matches the report decision contract and user loop."),
        _check("workflow_phase_state_matches_manifest", manifest_match, "Workflow phase_state matches context_manifest handoff and user_loop snapshot."),
    ]


def _phase_state_matches_manifest(phase_state: dict[str, object], context_manifest: dict[str, object] | None) -> bool:
    if not isinstance(context_manifest, dict):
        return False
    handoff = context_manifest.get("handoff")
    user_loop = context_manifest.get("user_loop")
    if not isinstance(handoff, dict) or not isinstance(user_loop, dict):
        return False
    return (
        phase_state.get("current_phase") == handoff.get("current_phase")
        and phase_state.get("next_action") == handoff.get("next_action")
        and phase_state.get("agent_owner") == handoff.get("to_agent")
        and phase_state.get("context_slice") == handoff.get("context_slice")
        and phase_state.get("allowed_artifacts") == handoff.get("allowed_artifacts")
        and phase_state.get("user_loop") == {
            "position": user_loop.get("position"),
            "required_input": user_loop.get("required_input"),
        }
        and phase_state.get("safe_to_auto_continue") == user_loop.get("safe_to_auto_continue")
    )


def _load_batch_manifest(root: Path, batch_id: str) -> dict[str, object]:
    batch_path = root / ".leaf" / "batches" / batch_id / "batch.json"
    return json.loads(batch_path.read_text(encoding="utf-8"))


def _load_batch_resume_view(root: Path, batch_id: str) -> dict[str, object]:
    try:
        return resume_batch(root, batch_id, auto_safe=False)
    except Exception as exc:
        return {
            "focus_plan": None,
            "context_policy": {},
            "summary": {},
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }


def _batch_resume_checks(resume_view: dict[str, object]) -> list[dict[str, object]]:
    focus_plan = resume_view.get("focus_plan")
    context_policy = resume_view.get("context_policy")
    summary = resume_view.get("summary")
    active_count = 0
    if isinstance(summary, dict):
        active_count = int(summary.get("waiting_for_confirmation", 0) or 0) + int(summary.get("in_progress", 0) or 0) + int(summary.get("failed", 0) or 0)
    attention_boundary = isinstance(context_policy, dict) and context_policy.get("attention_boundary") == "one_active_run"
    if active_count == 0:
        return [
            _check("batch_resume_attention_boundary", attention_boundary, "Batch resume context policy uses one active run boundary."),
            _check("batch_resume_focus_complete", focus_plan is None, "Completed batches do not select an active focus run."),
        ]
    focus_present = isinstance(focus_plan, dict)
    focus_handoff = (
        focus_present
        and focus_plan.get("attention_boundary") == "one_active_run"
        and bool(focus_plan.get("selected_run_id"))
        and bool(focus_plan.get("agent_owner"))
        and isinstance(focus_plan.get("context_slice"), list)
        and isinstance(focus_plan.get("allowed_artifacts"), list)
        and isinstance(focus_plan.get("target_policy"), dict)
        and isinstance(focus_plan.get("user_loop"), dict)
    )
    focus_matches_run = focus_present and _batch_focus_matches_selected_run(focus_plan, resume_view)
    focus_user_boundary = focus_present and _batch_focus_respects_user_boundary(focus_plan)
    focus_gui_context = focus_present and (
        focus_plan.get("agent_owner") != "leaf-gui-agent" or "ui_tree" in _string_list(focus_plan.get("context_slice"))
    )
    focus_target_policy = focus_present and _target_policy_handoff_ready(focus_plan.get("target_policy"), focus_plan.get("target_policy"))
    return [
        _check("batch_resume_attention_boundary", attention_boundary, "Batch resume context policy uses one active run boundary."),
        _check("batch_resume_focus_present", focus_present, "Incomplete batches expose one selected focus run."),
        _check("batch_resume_focus_handoff", focus_handoff, "Batch focus plan includes agent, context, artifacts, and user loop metadata."),
        _check("batch_resume_focus_matches_run", focus_matches_run, "Batch focus plan matches the selected run resume contract."),
        _check("batch_resume_focus_user_boundary", focus_user_boundary, "Batch focus plan never marks a user checkpoint safe for automatic continuation."),
        _check("batch_resume_focus_gui_context", focus_gui_context, "Batch GUI-agent focus includes ui_tree in the bounded context slice."),
        _check("batch_resume_focus_target_policy", focus_target_policy, "Batch focus plan preserves the system-app-only target policy."),
    ]


def _batch_focus_matches_selected_run(focus_plan: object, resume_view: dict[str, object]) -> bool:
    if not isinstance(focus_plan, dict):
        return False
    selected_run_id = focus_plan.get("selected_run_id")
    runs = resume_view.get("runs")
    if not isinstance(runs, list):
        return False
    selected = None
    for run in runs:
        if isinstance(run, dict) and run.get("run_id") == selected_run_id:
            selected = run
            break
    if not isinstance(selected, dict):
        return False
    summary = selected.get("resume_summary")
    if not isinstance(summary, dict):
        return False
    summary_user_loop = summary.get("user_loop")
    focus_user_loop = focus_plan.get("user_loop")
    if not isinstance(summary_user_loop, dict) or not isinstance(focus_user_loop, dict):
        return False
    return (
        focus_plan.get("current_phase") == selected.get("current_phase")
        and focus_plan.get("next_action") == selected.get("next_action")
        and focus_plan.get("agent_owner") == summary.get("agent_owner")
        and _string_list(focus_plan.get("context_slice")) == _string_list(summary.get("context_slice"))
        and _string_list(focus_plan.get("allowed_artifacts")) == _string_list(summary.get("allowed_artifacts"))
        and focus_plan.get("target_policy") == summary.get("target_policy")
        and focus_plan.get("user_checkpoint") == summary.get("user_checkpoint")
        and bool(focus_plan.get("requires_user_confirmation")) == bool(summary.get("requires_user_confirmation"))
        and bool(focus_plan.get("safe_to_auto_continue")) == bool(summary.get("safe_to_auto_continue"))
        and focus_user_loop.get("position") == summary_user_loop.get("position")
        and focus_user_loop.get("required_input") == summary_user_loop.get("required_input")
    )


def _batch_focus_respects_user_boundary(focus_plan: object) -> bool:
    if not isinstance(focus_plan, dict):
        return False
    has_user_checkpoint = bool(focus_plan.get("user_checkpoint")) or bool(focus_plan.get("requires_user_confirmation"))
    return not (has_user_checkpoint and bool(focus_plan.get("safe_to_auto_continue")))


def _batch_resume_attention_boundary(resume_view: dict[str, object]) -> object:
    context_policy = resume_view.get("context_policy")
    if isinstance(context_policy, dict):
        return context_policy.get("attention_boundary")
    return None


def _batch_real_device_summary(runs: list[dict[str, object]]) -> dict[str, object]:
    traces = [run.get("real_device_trace") for run in runs if isinstance(run.get("real_device_trace"), dict)]
    serials = sorted({str(trace.get("serial")) for trace in traces if trace.get("serial")})
    runtime_modes = sorted({str(trace.get("runtime_mode")) for trace in traces if trace.get("runtime_mode")})
    quality_gates = sorted({str(trace.get("latest_quality_gate")) for trace in traces if trace.get("latest_quality_gate")})
    risk_levels = sorted({str(trace.get("risk_level")) for trace in traces if trace.get("risk_level")})
    approval_statuses = sorted({str(trace.get("approval_status")) for trace in traces if trace.get("approval_status")})
    approval_tokens = sorted({str(trace.get("required_approval_token")) for trace in traces if trace.get("required_approval_token")})
    live_devices = [trace.get("live_device") for trace in traces if isinstance(trace.get("live_device"), dict)]
    return {
        "total_traces": len(traces),
        "serials": serials,
        "runtime_modes": runtime_modes,
        "quality_gates": quality_gates,
        "risk_levels": risk_levels,
        "mutates_device_state": sum(1 for trace in traces if trace.get("mutates_device_state") is True),
        "read_only": sum(1 for trace in traces if trace.get("mutates_device_state") is False),
        "approval_statuses": approval_statuses,
        "approval_required": sum(1 for trace in traces if trace.get("required_approval_token")),
        "approval_approved": sum(1 for trace in traces if trace.get("approval_status") == "approved"),
        "approval_tokens": approval_tokens,
        "live_connected": sum(1 for item in live_devices if isinstance(item, dict) and item.get("status") == "connected"),
        "live_unavailable": sum(1 for item in live_devices if isinstance(item, dict) and item.get("status") != "connected"),
    }


def _batch_runtime_evidence_summary(runs: list[dict[str, object]]) -> dict[str, object]:
    traces = [run.get("runtime_evidence_trace") for run in runs if isinstance(run.get("runtime_evidence_trace"), dict)]
    artifacts = sorted({str(trace.get("artifact")) for trace in traces if trace.get("artifact")})
    quality_gates = sorted({str(trace.get("quality_gate")) for trace in traces if trace.get("quality_gate")})
    failed_checks = sorted({check for trace in traces for check in _string_list(trace.get("failed_checks"))})
    missing_required_fields = sorted({field for trace in traces for field in _string_list(trace.get("missing_required_fields"))})
    return {
        "total_traces": len(traces),
        "artifacts": artifacts,
        "quality_gates": quality_gates,
        "failed_checks": failed_checks,
        "missing_required_fields": missing_required_fields,
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _audit_batch_run(
    root: Path,
    run_id: str,
    *,
    live_device: bool,
    hdc_runner: ProbeRunner | None,
    hdc_path: str,
) -> dict[str, object]:
    try:
        return audit_run(root, run_id, live_device=live_device, hdc_runner=hdc_runner, hdc_path=hdc_path)
    except Exception as exc:
        return {
            "schema_version": "1.0",
            "manifest_kind": "leaf_run_audit",
            "run_id": run_id,
            "domain": None,
            "platform": None,
            "status": "failed",
            "latest_quality_gate": "UNKNOWN",
            "checks": [
                _check("run_audit_exception", False, f"{type(exc).__name__}: {exc}"),
            ],
            "evidence": {},
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }


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
    try:
        workflow = load_workflow(root, run_id)
    except Exception as exc:
        payload["workflow_artifact_update"] = {
            "status": "skipped",
            "reason": "workflow_unreadable",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload
    artifacts = dict(workflow.get("artifacts", {}))
    artifacts["run_audit"] = str(path.relative_to(root))
    workflow["artifacts"] = artifacts
    save_workflow(root, workflow)
    payload["workflow_artifact_update"] = {
        "status": "updated",
        "artifact_key": "run_audit",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _write_batch_audit(root: Path, batch_id: str, payload: dict[str, object]) -> dict[str, object]:
    path = root / ".leaf" / "batches" / batch_id / "batch_audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["audit_path"] = str(path.relative_to(root))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
