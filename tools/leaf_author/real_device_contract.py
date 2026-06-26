from __future__ import annotations


_REAL_DEVICE_GATE_KINDS = ["approval", "input", "preflight"]
_REQUIRED_DECISION_FIELDS = {"trigger_source", "agent_owner", "context_slice", "allowed_artifacts"}
_REQUIRED_USER_LOOP_FIELDS = {"position", "required_input"}
_RUNTIME_EVIDENCE = {
    "camera": {
        "direct_smoke": {
            "artifact": "camera_direct_smoke",
            "quality_gate": "CAMERA_DIRECT_SMOKE_PASS",
            "required_evidence_fields": ["layout_verified", "bundle_verified", "ability_verified", "ui_snapshot_refs"],
            "requires_real_device_preflight": True,
        },
        "capture_e2e": {
            "artifact": "camera_capture_e2e",
            "quality_gate": "CAMERA_CAPTURE_E2E_PASS",
            "required_evidence_fields": ["capture_triggered", "media_delta_detected", "layout_verified", "ui_snapshot_refs"],
            "requires_real_device_preflight": True,
        },
    },
}


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
        "runtime_evidence": _runtime_evidence_contract(),
    }


def build_runtime_evidence_contract(domain: str | None = None) -> dict[str, object]:
    runtime_evidence = _runtime_evidence_contract()
    if domain:
        domain_evidence = runtime_evidence.get(domain, {})
        return {
            "schema_version": "1.0",
            "manifest_kind": "leaf_runtime_evidence_contract",
            "domain": domain,
            "runtime_evidence": domain_evidence if isinstance(domain_evidence, dict) else {},
        }
    return {
        "schema_version": "1.0",
        "manifest_kind": "leaf_runtime_evidence_contract",
        "domain": None,
        "runtime_evidence": runtime_evidence,
    }


def validate_real_device_contract(contract: dict[str, object] | None = None) -> dict[str, object]:
    contract = contract or build_real_device_contract()
    issues: list[str] = []
    gates = contract.get("gates")
    if not isinstance(gates, dict):
        issues.append("real_device_gates: contract must define gates")
        gates = {}

    for kind in _REAL_DEVICE_GATE_KINDS:
        gate = gates.get(kind)
        if not isinstance(gate, dict):
            issues.append(f"real_device_gates.{kind}: gate is missing")
            continue
        decision = gate.get("decision_contract")
        user_loop = gate.get("user_loop")
        if not isinstance(decision, dict):
            issues.append(f"real_device_gates.{kind}: decision_contract must be an object")
            decision = {}
        if not isinstance(user_loop, dict):
            issues.append(f"real_device_gates.{kind}: user_loop must be an object")
            user_loop = {}
        missing_decision = sorted(_REQUIRED_DECISION_FIELDS - set(decision))
        for field in missing_decision:
            issues.append(f"real_device_gates.{kind}: missing decision_contract field {field}")
        missing_user_loop = sorted(_REQUIRED_USER_LOOP_FIELDS - set(user_loop))
        for field in missing_user_loop:
            issues.append(f"real_device_gates.{kind}: missing user_loop field {field}")
        if decision.get("trigger_source") != "workflow.json":
            issues.append(f"real_device_gates.{kind}: trigger_source must be workflow.json")
        if decision.get("agent_owner") != "leaf-test-author":
            issues.append(f"real_device_gates.{kind}: agent_owner must be leaf-test-author")
        context_slice = _string_list(decision.get("context_slice"))
        if "workflow" not in context_slice:
            issues.append(f"real_device_gates.{kind}: context_slice must include workflow")
        if kind in {"approval", "preflight"} and "real_device_approval" not in context_slice:
            issues.append(f"real_device_gates.{kind}: context_slice must include real_device_approval")
        if kind in {"input", "preflight"} and "real_device_input" not in context_slice:
            issues.append(f"real_device_gates.{kind}: context_slice must include real_device_input")
        if kind == "preflight" and "runtime_safety" not in context_slice:
            issues.append("real_device_gates.preflight: context_slice must include runtime_safety")
        if not _string_list(decision.get("allowed_artifacts")):
            issues.append(f"real_device_gates.{kind}: allowed_artifacts must not be empty")
        if kind in {"approval", "input"} and not str(user_loop.get("required_input", "")):
            issues.append(f"real_device_gates.{kind}: user_loop.required_input must be explicit")

    preflight = contract.get("execution_preflight")
    if not isinstance(preflight, dict):
        issues.append("real_device_gates.execution_preflight: must be an object")
    else:
        required = _string_list(preflight.get("required_before_runtime"))
        for kind in _REAL_DEVICE_GATE_KINDS:
            if kind not in required:
                issues.append(f"real_device_gates.execution_preflight: required_before_runtime must include {kind}")
        if preflight.get("artifact") != "real_device_preflight":
            issues.append("real_device_gates.execution_preflight: artifact must be real_device_preflight")
        if preflight.get("status_for_execution") != "ready":
            issues.append("real_device_gates.execution_preflight: status_for_execution must be ready")

    _validate_runtime_evidence(contract.get("runtime_evidence"), issues)

    return {
        "schema_version": "1.0",
        "manifest_kind": "leaf_real_device_gate_guard",
        "status": "stable" if not issues else "unstable",
        "issues": issues,
        "exit_code": 0 if not issues else 1,
        "gate_count": len(gates),
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
            "required_input": required_input or "<approval-token>",
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


def real_device_runtime_evidence_schema(domain: str, runtime_mode: str) -> dict[str, object]:
    schema = _RUNTIME_EVIDENCE.get(domain, {}).get(runtime_mode)
    if not schema:
        raise ValueError(f"unsupported real-device runtime evidence schema: {domain}.{runtime_mode}")
    return dict(schema)


def _runtime_evidence_contract() -> dict[str, object]:
    return {
        domain: {mode: dict(schema) for mode, schema in modes.items()}
        for domain, modes in _RUNTIME_EVIDENCE.items()
    }


def _validate_runtime_evidence(runtime_evidence: object, issues: list[str]) -> None:
    if not isinstance(runtime_evidence, dict) or not runtime_evidence:
        issues.append("real_device_runtime_evidence: contract must define runtime evidence schemas")
        return
    for domain, modes in runtime_evidence.items():
        if not isinstance(modes, dict) or not modes:
            issues.append(f"real_device_runtime_evidence.{domain}: domain must define runtime modes")
            continue
        for mode, schema in modes.items():
            prefix = f"real_device_runtime_evidence.{domain}.{mode}"
            if not isinstance(schema, dict):
                issues.append(f"{prefix}: schema must be an object")
                continue
            if not isinstance(schema.get("artifact"), str) or not schema.get("artifact"):
                issues.append(f"{prefix}: artifact must be defined")
            if not isinstance(schema.get("quality_gate"), str) or not schema.get("quality_gate"):
                issues.append(f"{prefix}: quality_gate must be defined")
            if not _string_list(schema.get("required_evidence_fields")):
                issues.append(f"{prefix}: required_evidence_fields must not be empty")
            if schema.get("requires_real_device_preflight") is not True:
                issues.append(f"{prefix}: requires_real_device_preflight must be true")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
