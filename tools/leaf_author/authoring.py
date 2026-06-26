from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.case_spec import generate_case_spec
from tools.leaf_author.device_probe import HdcProbe, ProbeRunner
from tools.leaf_author.experience import export_team_knowledge, record_experience
from tools.leaf_author.generator import generate_pytest_case
from tools.leaf_author.gui_context import collect_gui_context
from tools.leaf_author.hypium import export_openharmony_test_project, generate_hypium_case, run_hypium_case
from tools.leaf_author.phase_contract import decide_next_step, write_context_manifest
from tools.leaf_author.phase_guard import build_agent_handoff_contract, validate_phase_contract
from tools.leaf_author.planner import build_plan
from tools.leaf_author.real_device_contract import real_device_decision_contract, real_device_user_loop
from tools.leaf_author.runner import run_pytest_draft
from tools.leaf_author.runtime_registry import resolve_runtime_mode, run_domain_runtime, runtime_safety_profile
from tools.leaf_author.validator import validate_pytest_draft
from tools.leaf_author.workflow import create_workflow, load_workflow, save_workflow


def start_new_case(
    root: Path,
    domain: str,
    teststep: str,
    run_id: str,
    probe_device: bool = False,
    hdc_runner: ProbeRunner | None = None,
    serial: str | None = None,
    plan_input: dict[str, object] | None = None,
) -> dict[str, object]:
    workflow = create_workflow(root, domain, teststep, run_id)
    plan = build_plan(workflow, plan_input=plan_input)
    run_dir = root / ".leaf" / "runs" / run_id
    plan_path = run_dir / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = {
        "run_id": run_id,
        "workflow_path": str(run_dir / "workflow.json"),
        "plan_path": str(plan_path),
        "pytest_path": None,
        "device_probe_path": None,
        "plan_summary": _plan_summary(plan),
    }
    if probe_device:
        probe = HdcProbe(runner=hdc_runner).probe(serial=serial)
        probe_path = run_dir / "device_probe.json"
        probe_path.write_text(json.dumps(probe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["device_probe_path"] = str(probe_path)
    context_manifest = write_context_manifest(root, run_id)
    result["context_manifest"] = context_manifest
    return result


def confirm_plan(root: Path, run_id: str) -> dict[str, object]:
    run_dir = root / ".leaf" / "runs" / run_id
    plan_path = run_dir / "plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"plan.json not found for run {run_id}: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    case_path = generate_case_spec(root, plan)
    case_spec = json.loads(case_path.read_text(encoding="utf-8"))
    pytest_path = generate_pytest_case(root, case_spec)
    hypium_path = generate_hypium_case(root, case_spec)
    export_dir = export_openharmony_test_project(root, case_spec, hypium_path)

    workflow = load_workflow(root, run_id)
    workflow["confirmed_plan"] = True
    workflow["current_phase"] = "hypium_draft"
    artifacts = dict(workflow.get("artifacts", {}))
    artifacts["case"] = str(case_path.relative_to(root))
    artifacts["pytest"] = str(pytest_path.relative_to(root))
    artifacts["hypium"] = str(hypium_path.relative_to(root))
    artifacts["openharmony_test_project"] = str(export_dir.relative_to(root))
    workflow["artifacts"] = artifacts
    save_workflow(root, workflow)
    context_manifest = write_context_manifest(root, run_id)

    return {
        "run_id": run_id,
        "workflow_path": str(run_dir / "workflow.json"),
        "plan_path": str(plan_path),
        "case_path": str(case_path),
        "pytest_path": str(pytest_path),
        "hypium_path": str(hypium_path),
        "openharmony_test_project": str(export_dir),
        "current_phase": "hypium_draft",
        "next_action": "validate_pytest_draft",
        "context_manifest": context_manifest,
    }


def resume_run(root: Path, run_id: str, auto_safe: bool = False) -> dict[str, object]:
    guard = validate_phase_contract()
    if guard.get("status") != "stable":
        return _blocked_by_phase_guard(root, run_id, guard)
    workflow = load_workflow(root, run_id)
    approval_blocker = _load_real_device_approval_blocker(root, workflow)
    if approval_blocker:
        decision = _approval_blocker_decision(workflow, approval_blocker)
        context_manifest = write_context_manifest(root, run_id, decision=decision)
        payload = _resume_payload(root, run_id, decision, context_manifest)
        if not auto_safe:
            return payload
        return {**payload, "auto_advanced": False, "status": "waiting_for_confirmation"}
    input_blocker = _load_real_device_input_blocker(root, workflow)
    if input_blocker:
        decision = _input_blocker_decision(workflow, input_blocker)
        context_manifest = write_context_manifest(root, run_id, decision=decision)
        payload = _resume_payload(root, run_id, decision, context_manifest)
        if not auto_safe:
            return payload
        return {**payload, "auto_advanced": False, "status": "waiting_for_confirmation"}
    decision = decide_next_step(workflow)
    context_manifest = write_context_manifest(root, run_id, decision=decision)
    payload = _resume_payload(root, run_id, decision, context_manifest)
    if not auto_safe:
        return payload
    if not payload["resume_summary"]["safe_to_auto_continue"]:
        return {**payload, "auto_advanced": False, "status": "waiting_for_confirmation" if payload["resume_summary"]["requires_user_confirmation"] else "in_progress"}
    advance_result = advance_run(root, run_id)
    final = load_workflow(root, run_id)
    return {
        **payload,
        "auto_advanced": True,
        "status": advance_result.get("status", "in_progress"),
        "current_phase": final.get("current_phase"),
        "next_action": advance_result.get("next_action"),
        "advance_result": advance_result,
        "resume_summary": resume_run(root, run_id)["resume_summary"],
    }


def advance_run(
    root: Path,
    run_id: str,
    hdc_runner: ProbeRunner | None = None,
    serial: str | None = None,
    run_real: bool = False,
    bundle_name: str | None = None,
    module_name: str | None = None,
    test_bundle_name: str | None = None,
    test_module_name: str | None = None,
    test_runner: str = "OpenHarmonyTestRunner",
    app_hap: Path | None = None,
    test_hap: Path | None = None,
    package_dir: Path | None = None,
    runtime_mode: str | None = None,
    camera_direct: bool = False,
    camera_capture: bool = False,
    approval_token: str | None = None,
    hdc_path: str = "hdc",
) -> dict[str, object]:
    stages: list[str] = []
    guard = validate_phase_contract()
    if guard.get("status") != "stable":
        return {
            **_blocked_by_phase_guard(root, run_id, guard),
            "stages": stages,
        }
    workflow = load_workflow(root, run_id)
    selected_runtime_mode = resolve_runtime_mode(runtime_mode, camera_direct=camera_direct, camera_capture=camera_capture)
    domain = str(workflow.get("domain", ""))
    effective_serial = serial or ""
    if run_real and selected_runtime_mode:
        if not bool(workflow.get("confirmed_plan", False)):
            decision = decide_next_step(workflow)
            context_manifest = write_context_manifest(root, run_id, decision=decision)
            return {
                "run_id": run_id,
                "status": "blocked",
                "block_reason": "plan_confirmation_required",
                "current_phase": workflow.get("current_phase"),
                "stages": stages,
                "next_action": decision.get("next_action"),
                "resume_summary": _resume_summary(decision),
                "context_manifest": context_manifest,
            }
        approval = _real_device_approval_decision(domain, selected_runtime_mode, approval_token)
        if not approval["approved"]:
            approval_artifact = _write_real_device_approval_artifact(root, run_id, workflow, selected_runtime_mode, approval)
            approval_contract = real_device_decision_contract("approval")
            decision = {
                "current_phase": workflow.get("current_phase"),
                "confirmed_plan": bool(workflow.get("confirmed_plan", False)),
                "next_action": "request_real_device_approval",
                "requires_user_confirmation": True,
                "safe_to_auto_continue": False,
                "operator_message": approval["runtime_safety"].get("operator_message", "Explicit real-device approval is required."),
                "user_checkpoint": "real_device_confirmation",
                "agent_owner": approval_contract["agent_owner"],
                "context_slice": ["workflow", "real_device_approval"],
                "trigger_source": approval_contract["trigger_source"],
                "allowed_artifacts": ["workflow", "real_device_approval"],
                "user_loop": real_device_user_loop("approval", str(approval["required_approval_token"])),
            }
            context_manifest = write_context_manifest(root, run_id, decision=decision)
            return {
                "run_id": run_id,
                "status": "blocked",
                "block_reason": "real_device_approval_required",
                "current_phase": workflow.get("current_phase"),
                "stages": stages,
                "next_action": "request_real_device_approval",
                "required_approval_token": approval["required_approval_token"],
                "runtime_safety": approval["runtime_safety"],
                "real_device_approval_path": approval_artifact["path"],
                "resume_summary": _resume_summary(decision),
                "context_manifest": context_manifest,
            }
        if approval["required_approval_token"]:
            _write_real_device_approval_artifact(root, run_id, workflow, selected_runtime_mode, approval, approval_token=approval_token)
            workflow = load_workflow(root, run_id)
        serial_decision = _real_device_serial_decision(root, workflow, serial)
        if not serial_decision["ready"]:
            input_artifact = _write_real_device_input_artifact(root, run_id, workflow, selected_runtime_mode, serial_decision)
            input_contract = real_device_decision_contract("input")
            decision = {
                "current_phase": workflow.get("current_phase"),
                "confirmed_plan": bool(workflow.get("confirmed_plan", False)),
                "next_action": "provide_real_device_serial",
                "requires_user_confirmation": True,
                "safe_to_auto_continue": False,
                "operator_message": "Real-device runtime requires an explicit --serial value before local or device stages run.",
                "user_checkpoint": "manual_operator_decision",
                "agent_owner": input_contract["agent_owner"],
                "context_slice": ["workflow", "real_device_input"],
                "trigger_source": input_contract["trigger_source"],
                "allowed_artifacts": ["workflow", "real_device_input"],
                "user_loop": real_device_user_loop("input"),
            }
            context_manifest = write_context_manifest(root, run_id, decision=decision)
            return {
                "run_id": run_id,
                "status": "blocked",
                "block_reason": "real_device_serial_required",
                "current_phase": workflow.get("current_phase"),
                "stages": stages,
                "next_action": "provide_real_device_serial",
                "real_device_input_path": input_artifact["path"],
                "resume_summary": _resume_summary(decision),
                "context_manifest": context_manifest,
            }
        effective_serial = str(serial_decision["serial"]).strip()
        _write_real_device_input_artifact(root, run_id, workflow, selected_runtime_mode, serial_decision)
        workflow = load_workflow(root, run_id)
        _write_real_device_preflight_artifact(
            root,
            run_id,
            workflow,
            selected_runtime_mode,
            serial=effective_serial,
            approval=approval,
            approval_token=approval_token,
            serial_decision=serial_decision,
        )
        workflow = load_workflow(root, run_id)
    current_phase = str(workflow.get("current_phase", ""))
    if current_phase == "hypium_ran" and run_real:
        current_phase = "pytest_ran"
    if current_phase in {"e2e_ready", "openharmony_built"} and run_real:
        current_phase = "pytest_ran"
    if current_phase in {"pytest_draft", "hypium_draft"}:
        validate_pytest_draft(root, run_id)
        stages.append("validation")
        current_phase = "validated"
    if current_phase == "validated":
        run_pytest_draft(root, run_id)
        stages.append("pytest_result")
        current_phase = "pytest_ran"
    if current_phase == "pytest_ran":
        if run_real and selected_runtime_mode:
            runtime_result = run_domain_runtime(
                root,
                run_id,
                domain,
                selected_runtime_mode,
                serial=effective_serial,
                hdc_path=hdc_path,
                hdc_runner=hdc_runner,
            )
            domain_result = runtime_result["result"]
            stages.append(str(runtime_result["stage"]))
            current_phase = str(load_workflow(root, run_id).get("current_phase"))
            if domain_result.get("quality_gate") != runtime_result["pass_quality_gate"]:
                final = load_workflow(root, run_id)
                return {
                    "run_id": run_id,
                    "status": "failed",
                    "current_phase": final.get("current_phase"),
                    "stages": stages,
                    "next_action": runtime_result["inspect_action"],
                }
            record_experience(root, run_id)
            stages.append("experience")
            current_phase = "experience_recorded"
        elif run_real:
            hypium_result = run_hypium_case(
                root,
                run_id,
                serial=serial,
                hdc_runner=hdc_runner,
                bundle_name=bundle_name,
                module_name=module_name,
                test_bundle_name=test_bundle_name,
                test_module_name=test_module_name,
                test_runner=test_runner,
                app_hap=app_hap,
                test_hap=test_hap,
                package_dir=package_dir,
            )
            stages.append("hypium_result")
            current_phase = str(load_workflow(root, run_id).get("current_phase"))
            if hypium_result.get("status") != "PASSED_REAL":
                final = load_workflow(root, run_id)
                return {
                    "run_id": run_id,
                    "status": "failed",
                    "current_phase": final.get("current_phase"),
                    "stages": stages,
                    "next_action": "inspect_hypium_result",
                }
        if current_phase in {"pytest_ran", "hypium_ran"}:
            collect_gui_context(root, run_id, hdc_runner=hdc_runner, serial=serial)
            stages.append("gui_context")
            current_phase = "gui_context_collected"
    if current_phase == "gui_context_collected":
        record_experience(root, run_id)
        stages.append("experience")
        current_phase = "experience_recorded"
    if current_phase == "experience_recorded":
        export_team_knowledge(root, run_id)
        stages.append("team_export_manifest")
        current_phase = "complete"
    final = load_workflow(root, run_id)
    return {
        "run_id": run_id,
        "status": "complete" if final.get("current_phase") == "complete" else "in_progress",
        "current_phase": final.get("current_phase"),
        "stages": stages,
        "next_action": resume_run(root, run_id)["next_action"],
    }


def _plan_summary(plan: dict[str, object]) -> dict[str, object]:
    target_feature = str(plan.get("target_feature", ""))
    steps = [str(step) for step in plan.get("steps", [])] if isinstance(plan.get("steps"), list) else []
    real_capture = str(plan.get("domain", "")) == "camera" and target_feature == "camera.capture"
    summary = {
        "domain": str(plan.get("domain", "")),
        "platform": str(plan.get("platform", "openharmony")),
        "target_feature": target_feature,
        "steps": steps,
        "risk": plan.get("risk"),
        "writes_after_confirmation": [str(item) for item in plan.get("writes", [])] if isinstance(plan.get("writes"), list) else [],
        "requires_device_probe": bool(plan.get("requires_device_probe", False)),
        "confirmation_required": bool(plan.get("confirmation_required", True)),
        "first_confirmation_scope": "plan_only_safe_local_authoring",
        "after_confirmation_actions": ["confirm-plan", "advance_safe_local"],
        "real_device_capture_requires_second_confirmation": real_capture,
    }
    if real_capture:
        summary["second_confirmation_reason"] = "Camera capture mutates device state by taking a photo and creating a media file."
    return summary


def _resume_summary(decision: dict[str, object]) -> dict[str, object]:
    return {
        "requires_user_confirmation": bool(decision.get("requires_user_confirmation", False)),
        "safe_to_auto_continue": bool(decision.get("safe_to_auto_continue", False)),
        "operator_message": str(decision.get("operator_message", "Inspect workflow state before continuing.")),
        "user_checkpoint": decision.get("user_checkpoint"),
        "agent_owner": decision.get("agent_owner"),
        "agent_mode": decision.get("agent_mode"),
        "context_slice": decision.get("context_slice", []),
        "trigger_source": decision.get("trigger_source", "workflow.json"),
        "allowed_artifacts": decision.get("allowed_artifacts", []),
        "target_policy": decision.get("target_policy", {}),
        "user_loop": decision.get("user_loop", {}),
        "action_route": _action_route_for_decision(decision),
    }


def _action_route_for_decision(decision: dict[str, object]) -> dict[str, object]:
    phase = str(decision.get("current_phase", ""))
    routes = build_agent_handoff_contract().get("action_routes")
    if isinstance(routes, dict):
        route = routes.get(phase)
        if isinstance(route, dict):
            return dict(route)
    return {
        "phase": phase,
        "next_action": str(decision.get("next_action", "inspect_workflow_state")),
        "trigger_source": "workflow.json",
        "agent_owner": "leaf-test-author",
        "agent_mode": "orchestrator",
        "handoff_required": False,
        "subagent_boundary": "workflow_orchestration",
        "context_slice": ["workflow"],
        "allowed_artifacts": ["workflow"],
        "user_checkpoint": "manual_operator_decision",
        "auto_safe": False,
        "user_loop": {"position": "manual_triage", "required_input": "operator_decision"},
        "command": "python3 -m tools.leaf_author report-run <run_id>",
    }


def _resume_payload(root: Path, run_id: str, decision: dict[str, object], context_manifest: dict[str, object]) -> dict[str, object]:
    return {
        "run_id": run_id,
        "current_phase": str(decision.get("current_phase", "")),
        "confirmed_plan": bool(decision.get("confirmed_plan", False)),
        "next_action": str(decision.get("next_action", "inspect_workflow_state")),
        "resume_summary": _resume_summary(decision),
        "context_manifest": context_manifest,
        "workflow_path": str(root / ".leaf" / "runs" / run_id / "workflow.json"),
    }


def _blocked_by_phase_guard(root: Path, run_id: str, guard: dict[str, object]) -> dict[str, object]:
    workflow = load_workflow(root, run_id)
    return {
        "run_id": run_id,
        "status": "blocked",
        "block_reason": "phase_contract_unstable",
        "current_phase": workflow.get("current_phase"),
        "confirmed_plan": bool(workflow.get("confirmed_plan", False)),
        "next_action": "fix_phase_contract",
        "phase_guard": guard,
        "resume_summary": {
            "requires_user_confirmation": True,
            "safe_to_auto_continue": False,
            "operator_message": "Phase contract is unstable; fix docs/workflow-contract.json before resuming workflow actions.",
            "user_checkpoint": "manual_operator_decision",
            "agent_owner": "leaf-test-author",
            "agent_mode": "orchestrator",
            "context_slice": ["workflow", "phase_guard"],
            "trigger_source": "workflow.json",
            "allowed_artifacts": ["workflow"],
            "user_loop": {
                "position": "manual_triage",
                "required_input": "fix phase contract",
            },
        },
        "workflow_path": str(root / ".leaf" / "runs" / run_id / "workflow.json"),
    }


def _real_device_approval_decision(domain: str, runtime_mode: str, approval_token: str | None) -> dict[str, object]:
    safety = runtime_safety_profile(domain, runtime_mode)
    required = safety.get("requires_approval_token")
    approved = required is None or approval_token == required
    return {
        "approved": approved,
        "required_approval_token": required,
        "runtime_safety": safety,
    }


def _real_device_serial_decision(root: Path, workflow: dict[str, object], serial: str | None) -> dict[str, object]:
    if serial and serial.strip():
        return {
            "ready": True,
            "serial": serial.strip(),
            "source": "explicit_arg",
        }
    selection = _load_selected_device_artifact(root, workflow)
    selected_serial = selection.get("serial") if isinstance(selection, dict) else None
    if isinstance(selected_serial, str) and selected_serial.strip():
        return {
            "ready": True,
            "serial": selected_serial.strip(),
            "source": "device_selection",
            "device_selection_artifact": selection.get("artifact"),
        }
    return {
        "ready": False,
        "serial": None,
        "source": "missing",
    }


def _load_real_device_approval_blocker(root: Path, workflow: dict[str, object]) -> dict[str, object] | None:
    if workflow.get("current_phase") == "complete":
        return None
    artifacts = workflow.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return None
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
    return payload if payload.get("status") == "blocked" else None


def _has_artifact(workflow: dict[str, object], artifact_key: str) -> bool:
    artifacts = workflow.get("artifacts", {})
    return isinstance(artifacts, dict) and isinstance(artifacts.get(artifact_key), str)


def _load_real_device_input_blocker(root: Path, workflow: dict[str, object]) -> dict[str, object] | None:
    if workflow.get("current_phase") == "complete":
        return None
    artifacts = workflow.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return None
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
    return payload if payload.get("status") == "blocked" else None


def _load_selected_device_artifact(root: Path, workflow: dict[str, object]) -> dict[str, object] | None:
    artifacts = workflow.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return None
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
    if payload.get("status") != "selected":
        return None
    payload["artifact"] = value
    return payload


def _approval_blocker_decision(workflow: dict[str, object], blocker: dict[str, object]) -> dict[str, object]:
    required_token = blocker.get("required_approval_token")
    operator_message = blocker.get("operator_message")
    contract = real_device_decision_contract("approval")
    return {
        "current_phase": workflow.get("current_phase"),
        "confirmed_plan": bool(workflow.get("confirmed_plan", False)),
        "next_action": "request_real_device_approval",
        "user_checkpoint": "real_device_confirmation",
        "requires_user_confirmation": True,
        "safe_to_auto_continue": False,
        "operator_message": str(operator_message or "Explicit real-device approval is required."),
        **contract,
        "batch_focus_priority": 80,
        "user_loop": real_device_user_loop("approval", str(required_token) if isinstance(required_token, str) else ""),
    }


def _input_blocker_decision(workflow: dict[str, object], blocker: dict[str, object]) -> dict[str, object]:
    required_input = blocker.get("required_input")
    operator_message = blocker.get("operator_message")
    contract = real_device_decision_contract("input")
    return {
        "current_phase": workflow.get("current_phase"),
        "confirmed_plan": bool(workflow.get("confirmed_plan", False)),
        "next_action": "provide_real_device_serial",
        "user_checkpoint": "manual_operator_decision",
        "requires_user_confirmation": True,
        "safe_to_auto_continue": False,
        "operator_message": str(operator_message or "Real-device runtime requires an explicit --serial value."),
        **contract,
        "batch_focus_priority": 75,
        "user_loop": real_device_user_loop("input", str(required_input) if isinstance(required_input, str) else ""),
    }


def _write_real_device_approval_artifact(
    root: Path,
    run_id: str,
    workflow: dict[str, object],
    runtime_mode: str,
    approval: dict[str, object],
    approval_token: str | None = None,
) -> dict[str, object]:
    path = root / ".leaf" / "runs" / run_id / "real_device_approval.json"
    safety = approval["runtime_safety"] if isinstance(approval.get("runtime_safety"), dict) else {}
    required_token = approval.get("required_approval_token")
    payload = {
        "schema_version": "1.0",
        "artifact_kind": "real_device_approval_decision",
        "run_id": run_id,
        "domain": workflow.get("domain"),
        "runtime_mode": runtime_mode,
        "status": "approved" if approval.get("approved") else "blocked",
        "required_approval_token": approval.get("required_approval_token"),
        "approval_token": approval_token if approval.get("approved") else None,
        "risk_level": safety.get("risk_level"),
        "mutates_device_state": bool(safety.get("mutates_device_state", True)),
        "operator_message": safety.get("operator_message", "Explicit real-device approval is required."),
        "user_checkpoint": "real_device_confirmation",
        "next_action": "request_real_device_approval" if not approval.get("approved") else "run_real_device_runtime",
        "decision_contract": real_device_decision_contract("approval"),
        "user_loop": real_device_user_loop("approval", str(required_token) if isinstance(required_token, str) else ""),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    workflow_payload = dict(workflow)
    artifacts = dict(workflow_payload.get("artifacts", {}))
    artifacts["real_device_approval"] = str(path.relative_to(root))
    workflow_payload["artifacts"] = artifacts
    save_workflow(root, workflow_payload)
    return {"path": str(path), "payload": payload}


def _write_real_device_input_artifact(
    root: Path,
    run_id: str,
    workflow: dict[str, object],
    runtime_mode: str,
    serial_decision: dict[str, object],
) -> dict[str, object]:
    path = root / ".leaf" / "runs" / run_id / "real_device_input.json"
    payload = {
        "schema_version": "1.0",
        "artifact_kind": "real_device_input_decision",
        "run_id": run_id,
        "domain": workflow.get("domain"),
        "runtime_mode": runtime_mode,
        "status": "ready" if serial_decision.get("ready") else "blocked",
        "serial": serial_decision.get("serial"),
        "serial_source": serial_decision.get("source"),
        "device_selection_artifact": serial_decision.get("device_selection_artifact"),
        "missing": [] if serial_decision.get("ready") else ["serial"],
        "required_input": "--serial <serial>",
        "operator_message": "Real-device runtime requires an explicit --serial value before local or device stages run.",
        "user_checkpoint": "manual_operator_decision",
        "next_action": "provide_real_device_serial" if not serial_decision.get("ready") else "run_real_device_runtime",
        "decision_contract": real_device_decision_contract("input"),
        "user_loop": real_device_user_loop("input"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    workflow_payload = dict(workflow)
    artifacts = dict(workflow_payload.get("artifacts", {}))
    artifacts["real_device_input"] = str(path.relative_to(root))
    workflow_payload["artifacts"] = artifacts
    save_workflow(root, workflow_payload)
    return {"path": str(path), "payload": payload}


def _write_real_device_preflight_artifact(
    root: Path,
    run_id: str,
    workflow: dict[str, object],
    runtime_mode: str,
    serial: str,
    approval: dict[str, object],
    approval_token: str | None,
    serial_decision: dict[str, object],
) -> dict[str, object]:
    safety = approval["runtime_safety"] if isinstance(approval.get("runtime_safety"), dict) else {}
    required_approval = approval.get("required_approval_token")
    path = root / ".leaf" / "runs" / run_id / "real_device_preflight.json"
    payload = {
        "schema_version": "1.0",
        "artifact_kind": "real_device_runtime_preflight",
        "run_id": run_id,
        "domain": workflow.get("domain"),
        "runtime_mode": runtime_mode,
        "status": "ready",
        "serial": serial,
        "serial_source": serial_decision.get("source"),
        "device_selection_artifact": serial_decision.get("device_selection_artifact"),
        "risk_level": safety.get("risk_level"),
        "mutates_device_state": bool(safety.get("mutates_device_state", True)),
        "approval_status": "approved" if required_approval else "not_required",
        "required_approval_token": required_approval,
        "approval_token": approval_token if required_approval else None,
        "input_status": "ready" if serial_decision.get("ready") else "blocked",
        "next_action": "run_real_device_runtime",
        "decision_contract": real_device_decision_contract("preflight"),
        "user_loop": real_device_user_loop("preflight"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    workflow_payload = dict(workflow)
    artifacts = dict(workflow_payload.get("artifacts", {}))
    artifacts["real_device_preflight"] = str(path.relative_to(root))
    workflow_payload["artifacts"] = artifacts
    save_workflow(root, workflow_payload)
    return {"path": str(path), "payload": payload}
