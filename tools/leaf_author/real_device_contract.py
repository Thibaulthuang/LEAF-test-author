from __future__ import annotations


_REAL_DEVICE_GATE_KINDS = ["approval", "input", "preflight"]


def build_real_device_contract() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "manifest_kind": "leaf_real_device_gate_contract",
        "trigger_stability": {
            "authoritative_source": "workflow.json",
            "runtime_safety_source": "tools.leaf_author.runtime_registry.runtime_safety_profile",
            "decision_contract_source": "tools.leaf_author.real_device_contract",
        },
        "gates": {
            kind: {
                "decision_contract": real_device_decision_contract(kind),
                "user_loop": real_device_user_loop(kind),
            }
            for kind in _REAL_DEVICE_GATE_KINDS
        },
        "execution_preflight": {
            "required_before_runtime": ["approval", "input", "preflight"],
            "artifact": "real_device_preflight",
            "status_for_execution": "ready",
        },
    }


def real_device_decision_contract(kind: str) -> dict[str, object]:
    if kind == "approval":
        return {
            "trigger_source": "workflow.json",
            "agent_owner": "leaf-test-author",
            "context_slice": ["workflow", "real_device_approval"],
            "allowed_artifacts": ["workflow", "real_device_approval"],
        }
    if kind == "input":
        return {
            "trigger_source": "workflow.json",
            "agent_owner": "leaf-test-author",
            "context_slice": ["workflow", "real_device_input"],
            "allowed_artifacts": ["workflow", "real_device_input"],
        }
    if kind == "preflight":
        return {
            "trigger_source": "workflow.json",
            "agent_owner": "leaf-test-author",
            "context_slice": ["workflow", "runtime_safety", "real_device_input", "real_device_approval"],
            "allowed_artifacts": ["workflow", "real_device_input", "real_device_approval"],
        }
    raise ValueError(f"unsupported real-device contract kind: {kind}")


def real_device_user_loop(kind: str, required_input: str = "") -> dict[str, str]:
    if kind == "approval":
        return {
            "position": "approve_real_device",
            "required_input": required_input,
        }
    if kind == "input":
        return {
            "position": "provide_target_inputs",
            "required_input": required_input or "--serial <serial>",
        }
    if kind == "preflight":
        return {
            "position": "observe_real_device_execution",
            "required_input": "",
        }
    raise ValueError(f"unsupported real-device user-loop kind: {kind}")
