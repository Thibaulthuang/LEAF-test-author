from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.domain_registry import is_domain_registered
from tools.leaf_author.phase_contract import load_phase_contract
from tools.leaf_author.phase_guard import build_agent_handoff_contract, validate_phase_contract
from tools.leaf_author.real_device_contract import build_real_device_contract, validate_real_device_contract
from tools.leaf_author.runtime_registry import (
    build_runtime_registry_contract,
    default_real_device_runtime_mode,
    quality_artifact_priority,
    registered_runtime_modes,
    runtime_artifact_keys,
    runtime_quality_gates,
    runtime_safety_profile,
    validate_runtime_registry,
)


def build_extension_contract(domain: str) -> dict[str, object]:
    phase_contract = load_phase_contract()
    handoff_contract = build_agent_handoff_contract(phase_contract)
    phase_guard = validate_phase_contract()
    real_device_contract = build_real_device_contract()
    real_device_guard = validate_real_device_contract(real_device_contract)
    runtime_registry_contract = build_runtime_registry_contract()
    runtime_registry_guard = validate_runtime_registry(runtime_registry_contract)
    runtime_modes = registered_runtime_modes(domain)
    missing = []
    if not is_domain_registered(domain):
        missing.append("domain_registry: register target feature inference, semantic validation, and action mapping")
    if not runtime_modes:
        missing.append("runtime_registry: register runtime modes and quality gates when real-device evidence is required")
    if phase_guard["status"] != "stable":
        missing.append("phase_guard: workflow-contract.json must pass trigger, context, agent, and user-loop validation")
    if real_device_guard["status"] != "stable":
        missing.append("real_device_contract: approval/input/preflight gates must pass stability validation")
    if runtime_registry_guard["status"] != "stable":
        missing.append("runtime_registry: registered runtime modes, artifacts, quality gates, and safety profiles must pass validation")
    status = "ready" if not missing else "incomplete"
    return {
        "schema_version": "1.0",
        "manifest_kind": "leaf_framework_extension_contract",
        "domain": domain,
        "domain_contract": {
            "registered": is_domain_registered(domain),
            "skill": f"leaf-{domain}",
            "required_hooks": [
                "target_feature",
                "validate_plan",
                "action_for_step",
            ],
        },
        "runtime_contract": {
            "registered_modes": runtime_modes,
            "default_real_device_mode": default_real_device_runtime_mode(domain),
            "artifact_keys": runtime_artifact_keys(domain),
            "quality_artifact_priority": quality_artifact_priority(domain),
            "quality_gates": runtime_quality_gates(domain),
            "safety_profiles": {mode: runtime_safety_profile(domain, mode) for mode in runtime_modes},
            "runtime_evidence": _runtime_evidence_for_domain(real_device_contract, domain),
            "runtime_registry_status": runtime_registry_guard["status"],
            "registry_manifest_kind": runtime_registry_contract["manifest_kind"],
        },
        "real_device_gate_contract": {
            "status": real_device_guard["status"],
            "manifest_kind": real_device_contract["manifest_kind"],
            "gates": real_device_contract["gates"],
            "execution_preflight": real_device_contract["execution_preflight"],
        },
        "phase_contract": {
            "source": "docs/workflow-contract.json",
            "trigger_source": "workflow.json",
            "decision_function": "tools.leaf_author.phase_contract.decide_next_step",
            "phase_guard_status": phase_guard["status"],
            "real_device_gate_status": phase_guard.get("real_device_gate_status"),
            "runtime_registry_status": phase_guard.get("runtime_registry_status"),
            "real_device_checkpoint_phases": _checkpoint_phases(phase_contract, "real_device_confirmation"),
            "user_loop_positions": _user_loop_positions(phase_contract),
            "batch_focus_priorities": _batch_focus_priorities(phase_contract),
        },
        "agent_handoff_contract": {
            "attention_boundary": handoff_contract["context_policy"].get("attention_boundary"),
            "artifact_loading": handoff_contract["context_policy"].get("artifact_loading"),
            "agents": handoff_contract["agents"],
            "auto_safe_phases": handoff_contract["auto_safe_phases"],
            "user_checkpoints": handoff_contract["user_checkpoints"],
        },
        "readiness": {
            "status": status,
            "missing": missing,
        },
    }


def export_extension_contract(domain: str, output_path: Path) -> dict[str, object]:
    contract = build_extension_contract(domain)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "domain": domain,
        "status": contract["readiness"]["status"],
        "output_path": str(output_path),
    }


def validate_extension_contract(domain: str, strict_real_device: bool = False) -> dict[str, object]:
    contract = build_extension_contract(domain)
    status = str(contract.get("readiness", {}).get("status", "incomplete"))
    missing = contract.get("readiness", {}).get("missing", [])
    missing_items = list(missing) if isinstance(missing, list) else []
    runtime_contract = contract.get("runtime_contract", {})
    real_device_contract = contract.get("real_device_gate_contract", {})
    if strict_real_device and isinstance(runtime_contract, dict):
        if not runtime_contract.get("default_real_device_mode"):
            missing_items.append("runtime_registry: register a default real-device runtime mode")
        if not runtime_contract.get("quality_gates"):
            missing_items.append("runtime_registry: register real-device quality gates")
        if runtime_contract.get("runtime_registry_status") != "stable":
            missing_items.append("runtime_registry: runtime registry guard must be stable")
        runtime_modes = runtime_contract.get("registered_modes", [])
        runtime_evidence = runtime_contract.get("runtime_evidence", {})
        if not isinstance(runtime_evidence, dict) or not runtime_evidence:
            missing_items.append("real_device_contract: register runtime evidence schema")
        elif isinstance(runtime_modes, list):
            for mode in runtime_modes:
                if str(mode) not in runtime_evidence:
                    missing_items.append(f"real_device_contract: register runtime evidence schema for {mode}")
        if isinstance(real_device_contract, dict) and real_device_contract.get("status") != "stable":
            missing_items.append("real_device_contract: real-device gate guard must be stable")
    if missing_items:
        status = "incomplete"
    return {
        "domain": domain,
        "status": status,
        "strict_real_device": strict_real_device,
        "missing": missing_items,
        "exit_code": 0 if status == "ready" else 1,
    }


def _checkpoint_phases(contract: dict[str, object], checkpoint: str) -> list[str]:
    phases = contract.get("phases", {})
    if not isinstance(phases, dict):
        return []
    return [name for name, phase in phases.items() if isinstance(phase, dict) and phase.get("user_checkpoint") == checkpoint]


def _runtime_evidence_for_domain(real_device_contract: dict[str, object], domain: str) -> dict[str, object]:
    runtime_evidence = real_device_contract.get("runtime_evidence", {})
    if not isinstance(runtime_evidence, dict):
        return {}
    domain_evidence = runtime_evidence.get(domain, {})
    if not isinstance(domain_evidence, dict):
        return {}
    return {
        str(mode): schema
        for mode, schema in domain_evidence.items()
        if isinstance(schema, dict)
    }


def _user_loop_positions(contract: dict[str, object]) -> dict[str, str]:
    phases = contract.get("phases", {})
    if not isinstance(phases, dict):
        return {}
    return {
        name: str(phase.get("user_loop", {}).get("position", ""))
        for name, phase in phases.items()
        if isinstance(phase, dict) and isinstance(phase.get("user_loop"), dict)
    }


def _batch_focus_priorities(contract: dict[str, object]) -> dict[str, int]:
    phases = contract.get("phases", {})
    if not isinstance(phases, dict):
        return {}
    return {
        name: int(phase.get("batch_focus_priority", 90))
        for name, phase in phases.items()
        if isinstance(phase, dict) and isinstance(phase.get("batch_focus_priority", 90), int)
    }
