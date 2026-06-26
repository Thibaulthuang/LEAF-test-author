from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.phase_guard import validate_phase_contract
from tools.leaf_author.real_device_contract import real_device_runtime_evidence_schema, validate_real_device_contract
from tools.leaf_author.reports import report_run
from tools.leaf_author.runtime_registry import runtime_quality_gates, validate_runtime_registry
from tools.leaf_author.workflow import load_workflow, save_workflow
from tools.leaf_author.batch_registry import resume_batch


def audit_run(root: Path, run_id: str) -> dict[str, object]:
    initial_workflow_phase_state = _load_workflow_phase_state(root, run_id)
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
    checks.extend(_real_device_preflight_checks(preflight if isinstance(preflight, dict) else None, device_selection if isinstance(device_selection, dict) else None))
    checks.extend(_device_selection_checks(device_selection if isinstance(device_selection, dict) else None, preflight if isinstance(preflight, dict) else None))
    evidence = report.get("evidence", {})
    real_device_input = _load_real_device_input(root, evidence if isinstance(evidence, dict) else {})
    checks.extend(
        _real_device_input_checks(
            real_device_input,
            preflight if isinstance(preflight, dict) else None,
            device_selection if isinstance(device_selection, dict) else None,
        )
    )
    runtime_evidence = _load_runtime_evidence(root, evidence if isinstance(evidence, dict) else {}, domain, preflight if isinstance(preflight, dict) else None)
    checks.extend(_runtime_evidence_checks(runtime_evidence, latest_quality_gate))
    context_manifest = _load_context_manifest(root, evidence if isinstance(evidence, dict) else {})
    checks.extend(_context_manifest_checks(context_manifest, report))
    workflow_phase_state = initial_workflow_phase_state if _has_phase_state_snapshot(initial_workflow_phase_state) else _load_workflow_phase_state(root, run_id)
    checks.extend(_workflow_phase_state_checks(workflow_phase_state, context_manifest, report))
    workflow_diagnostics = _load_workflow_diagnostics(root, evidence if isinstance(evidence, dict) else {})
    checks.extend(_workflow_diagnostics_checks(workflow_diagnostics))
    real_device_trace = _real_device_trace(
        latest_quality_gate=latest_quality_gate,
        device_selection=device_selection if isinstance(device_selection, dict) else None,
        real_device_input=real_device_input,
        preflight=preflight if isinstance(preflight, dict) else None,
    )

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
        "checks": checks,
        "evidence": {
            "report": "report-run",
            "device_selection": device_selection.get("artifact") if isinstance(device_selection, dict) else None,
            "real_device_input": real_device_input.get("artifact") if isinstance(real_device_input, dict) else None,
            "real_device_preflight": preflight.get("artifact") if isinstance(preflight, dict) else None,
            "runtime_evidence": runtime_evidence.get("artifact") if isinstance(runtime_evidence, dict) else None,
            "context_manifest": context_manifest.get("artifact") if isinstance(context_manifest, dict) else None,
            "workflow_phase_state": workflow_phase_state.get("artifact") if isinstance(workflow_phase_state, dict) else None,
            "workflow_diagnostics": workflow_diagnostics.get("artifact") if isinstance(workflow_diagnostics, dict) else None,
        },
    }
    return _write_run_audit(root, run_id, payload)


def audit_batch(root: Path, batch_id: str) -> dict[str, object]:
    batch = _load_batch_manifest(root, batch_id)
    run_ids = [str(run_id) for run_id in batch.get("run_ids", [])] if isinstance(batch.get("run_ids"), list) else []
    runs = [_audit_batch_run(root, run_id) for run_id in run_ids]
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
        "batch_checks": batch_checks,
        "focus_plan": resume_view.get("focus_plan") if isinstance(resume_view, dict) else None,
        "runs": [
            {
                "run_id": run.get("run_id"),
                "domain": run.get("domain"),
                "status": run.get("status"),
                "latest_quality_gate": run.get("latest_quality_gate"),
                "real_device_trace": run.get("real_device_trace") if isinstance(run.get("real_device_trace"), dict) else None,
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


def _real_device_preflight_checks(preflight: dict[str, object] | None, device_selection: dict[str, object] | None = None) -> list[dict[str, object]]:
    if not preflight:
        return [_check("real_device_preflight_ready", False, "Real-device preflight artifact is missing.")]
    checks = [
        _check("real_device_preflight_ready", preflight.get("status") == "ready", "Real-device preflight status is ready."),
        _check("real_device_input_ready", preflight.get("input_status") == "ready", "Real-device serial/input gate is ready."),
        _check("real_device_approval_ready", preflight.get("approval_status") in {"approved", "not_required"}, "Real-device approval gate is approved or not required."),
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


def _runtime_evidence_checks(runtime_evidence: dict[str, object] | None, latest_quality_gate: str) -> list[dict[str, object]]:
    if not runtime_evidence:
        return []
    schema = runtime_evidence.get("schema")
    if not isinstance(schema, dict):
        return [_check("runtime_evidence_schema_ready", False, "Runtime evidence schema is registered for the preflight runtime mode.")]
    evidence = runtime_evidence.get("evidence", {})
    evidence = evidence if isinstance(evidence, dict) else {}
    required_fields = [str(field) for field in schema.get("required_evidence_fields", [])] if isinstance(schema.get("required_evidence_fields"), list) else []
    missing_fields = [field for field in required_fields if field not in evidence]
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
    ]


def _real_device_trace(
    *,
    latest_quality_gate: str,
    device_selection: dict[str, object] | None,
    real_device_input: dict[str, object] | None,
    preflight: dict[str, object] | None,
) -> dict[str, object]:
    artifacts = {
        "device_selection": device_selection.get("artifact") if isinstance(device_selection, dict) else None,
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


def _context_manifest_checks(context_manifest: dict[str, object] | None, report: dict[str, object]) -> list[dict[str, object]]:
    if not context_manifest:
        return [
            _check("context_manifest_ready", False, "Context manifest artifact is missing or unreadable."),
            _check("handoff_ready", False, "Context manifest handoff snapshot is missing."),
            _check("user_loop_ready", False, "Context manifest user_loop snapshot is missing."),
        ]
    handoff = context_manifest.get("handoff")
    user_loop = context_manifest.get("user_loop")
    handoff_ready = (
        isinstance(handoff, dict)
        and handoff.get("to_agent") == report.get("decision_contract", {}).get("agent_owner")
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
    ]


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
        and isinstance(focus_plan.get("user_loop"), dict)
    )
    return [
        _check("batch_resume_attention_boundary", attention_boundary, "Batch resume context policy uses one active run boundary."),
        _check("batch_resume_focus_present", focus_present, "Incomplete batches expose one selected focus run."),
        _check("batch_resume_focus_handoff", focus_handoff, "Batch focus plan includes agent, context, artifacts, and user loop metadata."),
    ]


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
    return {
        "total_traces": len(traces),
        "serials": serials,
        "runtime_modes": runtime_modes,
        "quality_gates": quality_gates,
    }


def _audit_batch_run(root: Path, run_id: str) -> dict[str, object]:
    try:
        return audit_run(root, run_id)
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
