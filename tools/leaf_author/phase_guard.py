from __future__ import annotations

from collections import defaultdict

from tools.leaf_author.phase_contract import load_phase_contract


REQUIRED_PHASE_FIELDS = {
    "user_checkpoint",
    "auto_safe",
    "agent_owner",
    "trigger_source",
    "context_slice",
    "user_loop",
    "allowed_artifacts",
    "next_action",
    "batch_focus_priority",
}


def validate_phase_contract() -> dict[str, object]:
    contract = load_phase_contract()
    phases = contract.get("phases", {})
    issues: list[str] = []
    if not isinstance(phases, dict) or not phases:
        issues.append("phases: workflow-contract.json must define at least one phase")
        phases = {}

    for phase_name, phase in phases.items():
        if not isinstance(phase, dict):
            issues.append(f"{phase_name}: phase definition must be an object")
            continue
        missing_fields = sorted(REQUIRED_PHASE_FIELDS - set(phase))
        for field in missing_fields:
            issues.append(f"{phase_name}: missing required field {field}")
        if phase.get("trigger_source") != "workflow.json":
            issues.append(f"{phase_name}: trigger_source must be workflow.json")
        if "workflow" not in _string_list(phase.get("context_slice")):
            issues.append(f"{phase_name}: context_slice must include workflow")
        if bool(phase.get("auto_safe")) and phase.get("user_checkpoint"):
            issues.append(f"{phase_name}: auto_safe phase cannot require a user_checkpoint")
        user_loop = phase.get("user_loop")
        if not isinstance(user_loop, dict):
            issues.append(f"{phase_name}: user_loop must be an object")
        elif phase.get("user_checkpoint") and not str(user_loop.get("required_input", "")):
            issues.append(f"{phase_name}: user checkpoint phases must name required_input")
        if phase.get("agent_owner") == "leaf-gui-agent" and "ui_tree" not in _string_list(phase.get("context_slice")):
            issues.append(f"{phase_name}: leaf-gui-agent phases must include ui_tree in context_slice")
        if not isinstance(phase.get("batch_focus_priority"), int):
            issues.append(f"{phase_name}: batch_focus_priority must be an integer")

    _expect_phase_value(phases, "plan", "user_checkpoint", "first_plan_confirmation", issues)
    _expect_phase_value(phases, "plan", "auto_safe", False, issues)
    _expect_phase_value(phases, "e2e_ready", "user_checkpoint", "real_device_confirmation", issues)
    _expect_phase_value(phases, "complete", "next_action", "complete", issues)
    _expect_phase_value(phases, "complete", "batch_focus_priority", 1000, issues)

    summary = build_agent_handoff_contract(contract)
    return {
        "schema_version": "1.0",
        "manifest_kind": "leaf_phase_guard",
        "status": "stable" if not issues else "unstable",
        "issues": issues,
        "exit_code": 0 if not issues else 1,
        "phase_count": len(phases),
        "trigger_source": "workflow.json",
        "attention_boundary": summary["context_policy"].get("attention_boundary"),
        "agent_owners": sorted(summary["agents"]),
        "user_checkpoints": summary["user_checkpoints"],
    }


def build_agent_handoff_contract(contract: dict[str, object] | None = None) -> dict[str, object]:
    contract = contract or load_phase_contract()
    phases = contract.get("phases", {})
    agent_phases: dict[str, list[str]] = defaultdict(list)
    checkpoint_phases: dict[str, list[str]] = defaultdict(list)
    auto_safe_phases: list[str] = []
    context_slices: dict[str, list[str]] = {}

    if isinstance(phases, dict):
        for phase_name, phase in phases.items():
            if not isinstance(phase, dict):
                continue
            owner = str(phase.get("agent_owner", "leaf-test-author"))
            agent_phases[owner].append(str(phase_name))
            checkpoint = phase.get("user_checkpoint")
            if isinstance(checkpoint, str) and checkpoint:
                checkpoint_phases[checkpoint].append(str(phase_name))
            if bool(phase.get("auto_safe")):
                auto_safe_phases.append(str(phase_name))
            context_slices[str(phase_name)] = _string_list(phase.get("context_slice"))

    context_policy = contract.get("context_policy", {})
    resume_policy = contract.get("resume_policy", {})
    return {
        "schema_version": "1.0",
        "manifest_kind": "leaf_agent_handoff_contract",
        "trigger_stability": {
            "authoritative_source": "workflow.json",
            "phase_table": "docs/workflow-contract.json",
            "decision_function": "tools.leaf_author.phase_contract.decide_next_step",
        },
        "context_policy": context_policy if isinstance(context_policy, dict) else {},
        "resume_policy": resume_policy if isinstance(resume_policy, dict) else {},
        "agents": {owner: phases for owner, phases in sorted(agent_phases.items())},
        "context_slices": context_slices,
        "user_checkpoints": {checkpoint: phases for checkpoint, phases in sorted(checkpoint_phases.items())},
        "auto_safe_phases": auto_safe_phases,
    }


def _expect_phase_value(phases: dict[str, object], phase_name: str, field: str, expected: object, issues: list[str]) -> None:
    phase = phases.get(phase_name)
    if not isinstance(phase, dict):
        issues.append(f"{phase_name}: required phase is missing")
        return
    if phase.get(field) != expected:
        issues.append(f"{phase_name}: {field} must be {expected!r}")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
