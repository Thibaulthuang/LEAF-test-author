from __future__ import annotations

from collections import defaultdict

from tools.leaf_author.agent_handoff import AGENT_MODES, HANDOFF_RULES, USER_LOOP_RULES
from tools.leaf_author.phase_contract import load_phase_contract
from tools.leaf_author.real_device_contract import build_real_device_contract, validate_real_device_contract
from tools.leaf_author.runtime_registry import build_runtime_registry_contract, validate_runtime_registry
from tools.leaf_author.target_policy import target_policy_forbidden_terms, target_policy_from_contract


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


def validate_phase_contract(contract: dict[str, object] | None = None, *, include_external_guards: bool = True) -> dict[str, object]:
    contract = contract or load_phase_contract()
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
        route = _action_route(str(phase_name), phase, contract)
        if route.get("trigger_source") != "workflow.json":
            issues.append(f"{phase_name}: action route trigger_source must be workflow.json")
        if phase.get("next_action") != route.get("next_action"):
            issues.append(f"{phase_name}: action route next_action must match phase next_action")
        if phase.get("agent_owner") != route.get("agent_owner"):
            issues.append(f"{phase_name}: action route agent_owner must match phase agent_owner")
        if phase.get("user_loop") != route.get("user_loop"):
            issues.append(f"{phase_name}: action route user_loop must match phase user_loop")
        if phase.get("agent_owner") == "leaf-gui-agent" and route.get("command") != _entrypoint(contract, "inspect_ui_tree"):
            issues.append(f"{phase_name}: leaf-gui-agent action route must use inspect-ui-tree")

    target_policy = target_policy_from_contract(contract)
    forbidden_terms = target_policy_forbidden_terms(target_policy)
    issues.extend(_target_policy_issues(phases, forbidden_terms))
    _expect_phase_value(phases, "plan", "user_checkpoint", "first_plan_confirmation", issues)
    _expect_phase_value(phases, "plan", "auto_safe", False, issues)
    _expect_phase_value(phases, "e2e_ready", "user_checkpoint", "real_device_confirmation", issues)
    _expect_phase_value(phases, "complete", "next_action", "complete", issues)
    _expect_phase_value(phases, "complete", "batch_focus_priority", 1000, issues)
    real_device_guard = validate_real_device_contract() if include_external_guards else {"status": "skipped"}
    if include_external_guards:
        issues.extend(str(issue) for issue in real_device_guard.get("issues", []) if isinstance(issue, str))
    runtime_guard = validate_runtime_registry() if include_external_guards else {"status": "skipped"}
    if include_external_guards:
        issues.extend(str(issue) for issue in runtime_guard.get("issues", []) if isinstance(issue, str))

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
        "target_policy": target_policy.get("scope"),
        "target_policy_forbidden_terms": forbidden_terms,
        "agent_owners": sorted(summary["agents"]),
        "user_checkpoints": summary["user_checkpoints"],
        "real_device_gate_status": real_device_guard.get("status"),
        "runtime_registry_status": runtime_guard.get("status"),
    }


def build_agent_handoff_contract(contract: dict[str, object] | None = None) -> dict[str, object]:
    contract = contract or load_phase_contract()
    phases = contract.get("phases", {})
    agent_phases: dict[str, list[str]] = defaultdict(list)
    checkpoint_phases: dict[str, list[str]] = defaultdict(list)
    auto_safe_phases: list[str] = []
    context_slices: dict[str, list[str]] = {}
    action_routes: dict[str, dict[str, object]] = {}

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
            action_routes[str(phase_name)] = _action_route(str(phase_name), phase, contract)

    context_policy = contract.get("context_policy", {})
    resume_policy = contract.get("resume_policy", {})
    target_policy = target_policy_from_contract(contract)
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
        "target_policy": target_policy,
        "agent_modes": AGENT_MODES,
        "handoff_rules": HANDOFF_RULES,
        "user_loop_rules": USER_LOOP_RULES,
        "agents": {owner: phases for owner, phases in sorted(agent_phases.items())},
        "context_slices": context_slices,
        "action_routes": action_routes,
        "user_checkpoints": {checkpoint: phases for checkpoint, phases in sorted(checkpoint_phases.items())},
        "auto_safe_phases": auto_safe_phases,
        "real_device_gates": build_real_device_contract()["gates"],
        "runtime_registry": build_runtime_registry_contract()["domains"],
    }


def _action_route(phase_name: str, phase: dict[str, object], contract: dict[str, object]) -> dict[str, object]:
    owner = str(phase.get("agent_owner", "leaf-test-author"))
    user_loop = phase.get("user_loop") if isinstance(phase.get("user_loop"), dict) else {}
    return {
        "phase": phase_name,
        "next_action": str(phase.get("next_action", "inspect_workflow_state")),
        "trigger_source": str(phase.get("trigger_source", "workflow.json")),
        "agent_owner": owner,
        "agent_mode": AGENT_MODES.get(owner, "orchestrator"),
        "handoff_required": bool(HANDOFF_RULES.get(owner, {}).get("handoff_required", False)),
        "subagent_boundary": str(HANDOFF_RULES.get(owner, {}).get("subagent_boundary", "")),
        "context_slice": _string_list(phase.get("context_slice")),
        "allowed_artifacts": _string_list(phase.get("allowed_artifacts")),
        "user_checkpoint": phase.get("user_checkpoint"),
        "auto_safe": bool(phase.get("auto_safe", False)),
        "user_loop": user_loop,
        "command": _command_for_phase(phase_name, phase, contract),
    }


def _command_for_phase(phase_name: str, phase: dict[str, object], contract: dict[str, object]) -> str:
    next_action = str(phase.get("next_action", ""))
    if next_action == "complete" or phase_name == "complete":
        return ""
    if phase.get("user_checkpoint"):
        return _entrypoint(contract, "report_run")
    if phase.get("agent_owner") == "leaf-gui-agent" or next_action == "collect_gui_context":
        return _entrypoint(contract, "inspect_ui_tree")
    if next_action in {"validate_pytest_draft", "run_pytest_draft", "record_experience", "export_team_knowledge"}:
        return "python3 -m tools.leaf_author resume <run_id> --auto-safe"
    if next_action in {"provide_system_app_target", "inspect_system_app_target"}:
        return "python3 -m tools.leaf_author inspect-target <run_id> --serial <serial> --bundle-name <bundle>"
    if next_action == "run_real_hypium":
        return "python3 -m tools.leaf_author advance <run_id> --run-real --runtime-mode <mode> --serial <serial> --approval-token <token>"
    if next_action == "inspect_e2e_readiness":
        return "python3 -m tools.leaf_author inspect-e2e-readiness <run_id> --serial <serial> --bundle-name <bundle>"
    if next_action == "inspect_openharmony_build":
        return "python3 -m tools.leaf_author build-openharmony-haps <run_id> --project-dir <dir>"
    return _entrypoint(contract, "report_run")


def _entrypoint(contract: dict[str, object], name: str) -> str:
    entrypoints = contract.get("entrypoints")
    if not isinstance(entrypoints, dict):
        entrypoints = {}
    value = entrypoints.get(name)
    return str(value) if isinstance(value, str) else ""


def _expect_phase_value(phases: dict[str, object], phase_name: str, field: str, expected: object, issues: list[str]) -> None:
    phase = phases.get(phase_name)
    if not isinstance(phase, dict):
        issues.append(f"{phase_name}: required phase is missing")
        return
    if phase.get(field) != expected:
        issues.append(f"{phase_name}: {field} must be {expected!r}")


def _target_policy_issues(phases: dict[str, object], forbidden_terms: list[str]) -> list[str]:
    if not forbidden_terms:
        return []
    issues = []
    for phase_name, phase in phases.items():
        if not isinstance(phase, dict):
            continue
        fields = {
            "next_action": phase.get("next_action"),
            "user_loop.required_input": (phase.get("user_loop") or {}).get("required_input") if isinstance(phase.get("user_loop"), dict) else None,
            "allowed_artifacts": phase.get("allowed_artifacts"),
            "context_slice": phase.get("context_slice"),
        }
        for field, value in fields.items():
            haystack = " ".join(str(item) for item in value) if isinstance(value, list) else str(value or "")
            lowered = haystack.lower()
            for term in forbidden_terms:
                if term in lowered:
                    issues.append(f"{phase_name}: {field} contains forbidden system_app_only term {term!r}")
    return issues


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
