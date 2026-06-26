from __future__ import annotations

import json
from pathlib import Path


_DEFAULT_MESSAGES = {
    "present_plan_for_confirmation": "Present plan.json for the first user confirmation before generating drafts.",
    "validate_pytest_draft": "Continue safe local authoring: validate the generated draft.",
    "run_pytest_draft": "Continue safe local authoring: run the draft quality gate.",
    "collect_gui_context": "Collect read-only GUI context before writing reviewable experience.",
    "record_experience": "Write reviewable experience from the latest quality gate.",
    "export_team_knowledge": "Export the reviewable team manifest.",
    "prepare_haps_or_target_bundle": "Prepare the target system-app execution inputs before real E2E.",
    "run_real_hypium": "Real-device execution is ready; require explicit user approval before running it.",
    "build_app_and_test_haps": "Legacy OpenHarmony project state detected; inspect before using this path.",
    "inspect_e2e_readiness": "Inspect readiness before real-device execution.",
    "inspect_openharmony_build": "Inspect the OpenHarmony build failure artifact.",
    "complete": "Workflow is complete.",
}


def load_phase_contract(root: Path | None = None) -> dict[str, object]:
    repo_root = root or Path(__file__).resolve().parents[2]
    contract_path = repo_root / "docs" / "workflow-contract.json"
    return json.loads(contract_path.read_text(encoding="utf-8"))


def decide_next_step(workflow: dict[str, object], contract: dict[str, object] | None = None) -> dict[str, object]:
    contract = contract or load_phase_contract()
    current_phase = str(workflow.get("current_phase", ""))
    confirmed = bool(workflow.get("confirmed_plan", False))
    phases = contract.get("phases", {})
    phase = phases.get(current_phase) if isinstance(phases, dict) else None
    if not isinstance(phase, dict):
        phase = _unknown_phase(current_phase)

    next_action = str(phase.get("next_action", "inspect_workflow_state"))
    user_checkpoint = _effective_user_checkpoint(current_phase, confirmed, phase)
    requires_user_confirmation = user_checkpoint is not None
    auto_safe = bool(phase.get("auto_safe", False))
    safe_to_auto_continue = confirmed and auto_safe and not requires_user_confirmation and current_phase != "complete"
    user_loop = phase.get("user_loop") if isinstance(phase.get("user_loop"), dict) else {}
    return {
        "current_phase": current_phase,
        "confirmed_plan": confirmed,
        "next_action": next_action,
        "user_checkpoint": user_checkpoint,
        "requires_user_confirmation": requires_user_confirmation,
        "safe_to_auto_continue": safe_to_auto_continue,
        "operator_message": str(phase.get("operator_message") or _DEFAULT_MESSAGES.get(next_action, "Inspect workflow state before continuing.")),
        "agent_owner": str(phase.get("agent_owner", "leaf-test-author")),
        "context_slice": [str(item) for item in phase.get("context_slice", [])] if isinstance(phase.get("context_slice"), list) else [],
        "trigger_source": str(phase.get("trigger_source", "workflow.json")),
        "allowed_artifacts": [str(item) for item in phase.get("allowed_artifacts", [])] if isinstance(phase.get("allowed_artifacts"), list) else [],
        "batch_focus_priority": _batch_focus_priority(phase),
        "user_loop": {
            "position": str(user_loop.get("position", "observe_safe_local_progress")),
            "required_input": str(user_loop.get("required_input", "")),
        },
    }


def batch_focus_priority_for_run(run: dict[str, object], contract: dict[str, object] | None = None) -> int:
    if str(run.get("next_action", "")) == "complete" or str(run.get("current_phase", "")) == "complete":
        return 1000
    contract = contract or load_phase_contract()
    phases = contract.get("phases", {})
    phase = phases.get(str(run.get("current_phase", ""))) if isinstance(phases, dict) else None
    if isinstance(phase, dict):
        return _batch_focus_priority(phase)
    return 90


def write_context_manifest(root: Path, run_id: str, decision: dict[str, object] | None = None) -> dict[str, object]:
    from tools.leaf_author.workflow import load_workflow, save_workflow, with_phase_state

    workflow = load_workflow(root, run_id)
    decision = decision or decide_next_step(workflow)
    artifacts = dict(workflow.get("artifacts", {}))
    manifest_path = root / ".leaf" / "runs" / run_id / "context_manifest.json"
    artifacts["context_manifest"] = str(manifest_path.relative_to(root))
    allowed_artifacts = set(str(item) for item in decision.get("allowed_artifacts", []) if isinstance(item, str))
    context_slice = set(str(item) for item in decision.get("context_slice", []) if isinstance(item, str))
    exposed_artifacts = allowed_artifacts | context_slice | {"workflow", "context_manifest"}
    referenced_artifacts = {}
    for key, value in artifacts.items():
        if not isinstance(value, str):
            continue
        if key in exposed_artifacts and (key == "context_manifest" or (root / value).exists()):
            referenced_artifacts[key] = value
    user_loop = decision.get("user_loop", {})
    if not isinstance(user_loop, dict):
        user_loop = {}
    user_loop_snapshot = {
        "position": str(user_loop.get("position", "observe_safe_local_progress")),
        "required_input": str(user_loop.get("required_input", "")),
        "user_checkpoint": decision.get("user_checkpoint"),
        "requires_user_confirmation": bool(decision.get("requires_user_confirmation", False)),
        "safe_to_auto_continue": bool(decision.get("safe_to_auto_continue", False)),
    }
    handoff = {
        "from_agent": _previous_agent_for_phase(str(decision.get("current_phase", "")), contract=None),
        "to_agent": decision.get("agent_owner"),
        "trigger_source": decision.get("trigger_source"),
        "current_phase": decision.get("current_phase"),
        "next_action": decision.get("next_action"),
        "attention_boundary": "one_active_run",
        "artifact_loading": "on_demand",
        "context_slice": decision.get("context_slice", []),
        "allowed_artifacts": decision.get("allowed_artifacts", []),
        "referenced_artifacts": referenced_artifacts,
        "user_loop": user_loop_snapshot,
    }
    payload = {
        "schema_version": "1.0",
        "manifest_kind": "run_context_manifest",
        "run_id": run_id,
        "current_phase": decision.get("current_phase"),
        "next_action": decision.get("next_action"),
        "agent_owner": decision.get("agent_owner"),
        "trigger_source": decision.get("trigger_source"),
        "context_slice": decision.get("context_slice", []),
        "attention_boundary": "one_active_run",
        "artifact_loading": "on_demand",
        "user_checkpoint": decision.get("user_checkpoint"),
        "user_loop": user_loop_snapshot,
        "safe_to_auto_continue": decision.get("safe_to_auto_continue"),
        "referenced_artifacts": referenced_artifacts,
        "handoff": handoff,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    workflow["artifacts"] = artifacts
    workflow = with_phase_state(workflow, decision=decision)
    save_workflow(root, workflow)
    return {
        "run_id": run_id,
        "context_manifest_path": str(manifest_path.relative_to(root)),
        "agent_owner": payload["agent_owner"],
        "context_slice": payload["context_slice"],
    }


def _effective_user_checkpoint(current_phase: str, confirmed: bool, phase: dict[str, object]) -> str | None:
    checkpoint = phase.get("user_checkpoint")
    if current_phase == "plan" and confirmed:
        return None
    if isinstance(checkpoint, str) and checkpoint:
        return checkpoint
    return None


def _previous_agent_for_phase(current_phase: str, contract: dict[str, object] | None = None) -> str:
    local_authoring_phases = {"pytest_draft", "hypium_draft", "validated", "pytest_ran", "hypium_ran"}
    if current_phase in local_authoring_phases:
        return "tools.leaf_author"
    if current_phase in {"gui_context_collected", "experience_recorded"}:
        return "leaf-gui-agent"
    phases = (contract or load_phase_contract()).get("phases", {})
    phase = phases.get(current_phase) if isinstance(phases, dict) else None
    if isinstance(phase, dict):
        return str(phase.get("agent_owner", "leaf-test-author"))
    return "leaf-test-author"


def _unknown_phase(current_phase: str) -> dict[str, object]:
    return {
        "next_action": "inspect_workflow_state",
        "user_checkpoint": "manual_operator_decision",
        "auto_safe": False,
        "agent_owner": "leaf-test-author",
        "context_slice": ["workflow"],
        "trigger_source": "workflow.json",
        "batch_focus_priority": 90,
        "operator_message": f"Unknown phase {current_phase}; inspect workflow.json before continuing.",
        "user_loop": {
            "position": "manual_triage",
            "required_input": "operator_decision",
        },
    }


def _batch_focus_priority(phase: dict[str, object]) -> int:
    value = phase.get("batch_focus_priority", 90)
    return value if isinstance(value, int) else 90
