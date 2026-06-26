from __future__ import annotations

AGENT_MODES = {
    "leaf-test-author": "orchestrator",
    "tools.leaf_author": "deterministic_tool",
    "leaf-gui-agent": "focused_subagent",
}

HANDOFF_RULES = {
    "leaf-test-author": {
        "handoff_required": False,
        "required_inputs": ["run_id", "workflow", "decision_contract"],
        "subagent_boundary": "workflow_orchestration",
    },
    "tools.leaf_author": {
        "handoff_required": False,
        "required_inputs": ["run_id", "workflow", "allowed_artifacts"],
        "subagent_boundary": "deterministic_file_and_runtime_tools",
    },
    "leaf-gui-agent": {
        "handoff_required": True,
        "required_inputs": ["run_id", "context_manifest", "referenced_artifacts", "specific_question"],
        "subagent_boundary": "read_only_gui_context",
    },
}

USER_LOOP_RULES = {
    "checkpoint_owner": "user",
    "blocking_checkpoints": ["first_plan_confirmation", "real_device_confirmation", "manual_operator_decision"],
    "auto_continue_requires": ["confirmed_plan", "auto_safe", "no_user_checkpoint"],
}
