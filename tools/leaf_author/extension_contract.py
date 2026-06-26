from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.domain_registry import is_domain_registered
from tools.leaf_author.phase_contract import load_phase_contract
from tools.leaf_author.runtime_registry import (
    default_real_device_runtime_mode,
    quality_artifact_priority,
    registered_runtime_modes,
    runtime_artifact_keys,
    runtime_quality_gates,
)


def build_extension_contract(domain: str) -> dict[str, object]:
    phase_contract = load_phase_contract()
    runtime_modes = registered_runtime_modes(domain)
    missing = []
    if not is_domain_registered(domain):
        missing.append("domain_registry: register target feature inference, semantic validation, and action mapping")
    if not runtime_modes:
        missing.append("runtime_registry: register runtime modes and quality gates when real-device evidence is required")
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
        },
        "phase_contract": {
            "source": "docs/workflow-contract.json",
            "real_device_checkpoint_phases": _checkpoint_phases(phase_contract, "real_device_confirmation"),
            "user_loop_positions": _user_loop_positions(phase_contract),
            "batch_focus_priorities": _batch_focus_priorities(phase_contract),
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


def validate_extension_contract(domain: str) -> dict[str, object]:
    contract = build_extension_contract(domain)
    status = str(contract.get("readiness", {}).get("status", "incomplete"))
    missing = contract.get("readiness", {}).get("missing", [])
    return {
        "domain": domain,
        "status": status,
        "missing": missing if isinstance(missing, list) else [],
        "exit_code": 0 if status == "ready" else 1,
    }


def _checkpoint_phases(contract: dict[str, object], checkpoint: str) -> list[str]:
    phases = contract.get("phases", {})
    if not isinstance(phases, dict):
        return []
    return [name for name, phase in phases.items() if isinstance(phase, dict) and phase.get("user_checkpoint") == checkpoint]


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
