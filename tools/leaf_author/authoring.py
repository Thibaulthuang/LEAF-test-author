from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.case_spec import generate_case_spec
from tools.leaf_author.device_probe import HdcProbe, ProbeRunner
from tools.leaf_author.experience import export_team_knowledge, record_experience
from tools.leaf_author.generator import generate_pytest_case
from tools.leaf_author.gui_context import collect_gui_context
from tools.leaf_author.hypium import export_openharmony_test_project, generate_hypium_case, run_hypium_case
from tools.leaf_author.planner import build_plan
from tools.leaf_author.runner import run_pytest_draft
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
    }


def resume_run(root: Path, run_id: str) -> dict[str, object]:
    workflow = load_workflow(root, run_id)
    current_phase = str(workflow.get("current_phase", ""))
    confirmed = bool(workflow.get("confirmed_plan", False))
    if current_phase == "plan" and not confirmed:
        next_action = "present_plan_for_confirmation"
    elif current_phase in {"pytest_draft", "hypium_draft"} and confirmed:
        next_action = "validate_pytest_draft"
    elif current_phase == "validated":
        next_action = "run_pytest_draft"
    elif current_phase == "pytest_ran":
        next_action = "collect_gui_context"
    elif current_phase == "gui_context_collected":
        next_action = "record_experience"
    elif current_phase == "experience_recorded":
        next_action = "export_team_knowledge"
    elif current_phase == "e2e_not_ready":
        next_action = "prepare_haps_or_target_bundle"
    elif current_phase == "e2e_ready":
        next_action = "run_real_hypium"
    elif current_phase == "openharmony_synced":
        next_action = "build_app_and_test_haps"
    elif current_phase == "openharmony_built":
        next_action = "inspect_e2e_readiness"
    elif current_phase == "openharmony_build_failed":
        next_action = "inspect_openharmony_build"
    elif current_phase == "complete":
        next_action = "complete"
    else:
        next_action = "inspect_workflow_state"
    return {
        "run_id": run_id,
        "current_phase": current_phase,
        "confirmed_plan": confirmed,
        "next_action": next_action,
        "resume_summary": _resume_summary(current_phase, confirmed, next_action),
        "workflow_path": str(root / ".leaf" / "runs" / run_id / "workflow.json"),
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
    camera_direct: bool = False,
    camera_capture: bool = False,
    hdc_path: str = "hdc",
) -> dict[str, object]:
    stages: list[str] = []
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
        if run_real and camera_capture:
            from tools.leaf_author.camera_smoke import run_camera_capture_e2e

            capture_result = run_camera_capture_e2e(
                root,
                run_id,
                serial=serial or "",
                hdc_path=hdc_path,
                hdc_runner=hdc_runner,
            )
            stages.append("camera_capture_e2e")
            current_phase = str(load_workflow(root, run_id).get("current_phase"))
            if capture_result.get("quality_gate") != "CAMERA_CAPTURE_E2E_PASS":
                final = load_workflow(root, run_id)
                return {
                    "run_id": run_id,
                    "status": "failed",
                    "current_phase": final.get("current_phase"),
                    "stages": stages,
                    "next_action": "inspect_camera_capture_e2e",
                }
            record_experience(root, run_id)
            stages.append("experience")
            current_phase = "experience_recorded"
        elif run_real and camera_direct:
            from tools.leaf_author.camera_smoke import run_camera_direct_smoke

            direct_result = run_camera_direct_smoke(
                root,
                run_id,
                serial=serial or "",
                hdc_path=hdc_path,
                hdc_runner=hdc_runner,
            )
            stages.append("camera_direct_smoke")
            current_phase = str(load_workflow(root, run_id).get("current_phase"))
            if direct_result.get("quality_gate") != "CAMERA_DIRECT_SMOKE_PASS":
                final = load_workflow(root, run_id)
                return {
                    "run_id": run_id,
                    "status": "failed",
                    "current_phase": final.get("current_phase"),
                    "stages": stages,
                    "next_action": "inspect_camera_direct_smoke",
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


def _resume_summary(current_phase: str, confirmed: bool, next_action: str) -> dict[str, object]:
    requires_confirmation = current_phase == "plan" and not confirmed
    unsafe_real_actions = {"run_real_hypium"}
    safe_to_auto_continue = confirmed and next_action not in unsafe_real_actions and current_phase not in {"complete", "e2e_ready"}
    messages = {
        "present_plan_for_confirmation": "Present plan.json for the first user confirmation before generating drafts.",
        "validate_pytest_draft": "Continue safe local authoring: validate the generated draft.",
        "run_pytest_draft": "Continue safe local authoring: run the draft quality gate.",
        "collect_gui_context": "Collect read-only GUI context before writing reviewable experience.",
        "record_experience": "Write reviewable experience from the latest quality gate.",
        "export_team_knowledge": "Export the reviewable team manifest.",
        "prepare_haps_or_target_bundle": "Prepare a test HAP or OpenHarmony project before real E2E.",
        "run_real_hypium": "Real-device execution is ready; require explicit user approval before running it.",
        "complete": "Workflow is complete.",
    }
    return {
        "requires_user_confirmation": requires_confirmation or next_action == "run_real_hypium",
        "safe_to_auto_continue": safe_to_auto_continue,
        "operator_message": messages.get(next_action, "Inspect workflow state before continuing."),
    }
