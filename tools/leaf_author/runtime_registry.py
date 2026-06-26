from __future__ import annotations

from pathlib import Path

from tools.leaf_author.device_probe import ProbeRunner


_GENERIC_EXPERIENCE_KEYS = ["hypium_result", "pytest_result"]
_DOMAIN_RUNTIME_ARTIFACTS = {
    "camera": ["camera_capture_e2e", "camera_direct_smoke"],
}
_DOMAIN_RUNTIME_QUALITY_GATES = {
    "camera": {
        "camera_capture_e2e": "CAMERA_CAPTURE_E2E_PASS",
        "camera_direct_smoke": "CAMERA_DIRECT_SMOKE_PASS",
    },
}
_GENERIC_QUALITY_ARTIFACTS = [
    "hypium_result",
    "e2e_run",
    "pytest_result",
    "validation",
    "e2e_preflight_report",
    "e2e_readiness",
    "openharmony_build",
]
_DOMAIN_QUALITY_ARTIFACTS = {
    "camera": ["camera_capture_e2e", "camera_direct_smoke"],
}
_DOMAIN_DIAGNOSTIC_ARTIFACTS = {
    "camera": ["camera_smoke_preflight"],
}
_DEFAULT_REAL_DEVICE_RUNTIME_MODE = {
    "camera": "direct_smoke",
}
_DOMAIN_RUNTIME_MODES = {
    "camera": ["direct_smoke", "capture_e2e"],
}
_DOMAIN_RUNTIME_SAFETY = {
    ("camera", "direct_smoke"): {
        "risk_level": "read_only_probe",
        "mutates_device_state": False,
        "requires_approval_token": None,
        "operator_message": "Camera direct smoke starts the system Camera and collects UI/log evidence; it does not tap shutter or create media.",
    },
    ("camera", "capture_e2e"): {
        "risk_level": "device_state_mutation",
        "mutates_device_state": True,
        "requires_approval_token": "approve_camera_capture_e2e",
        "operator_message": "Camera capture E2E taps the shutter and creates a new media file; explicit approval is required for this run.",
    },
}
_RUNTIME_EXPERIENCE_RULES = {
    "HYPIUM_REAL_PASS": {
        "status": "PASSED_REAL",
        "confidence": 0.8,
        "notes": ["Hypium execution passed on a real device."],
    },
    "CAMERA_CAPTURE_E2E_PASS": {
        "status": "complete",
        "confidence": 0.65,
        "notes": ["Camera capture e2e passed on a real device through UiTest shutter control and new media-file evidence; full Hypium business e2e is still pending."],
    },
    "CAMERA_DIRECT_SMOKE_PASS": {
        "status": "complete",
        "confidence": 0.5,
        "notes": ["Camera direct smoke passed on a real device; full Hypium business e2e is still pending."],
    },
}


def build_runtime_registry_contract() -> dict[str, object]:
    domains = sorted(set(_DOMAIN_RUNTIME_MODES) | set(_DEFAULT_REAL_DEVICE_RUNTIME_MODE))
    return {
        "schema_version": "1.0",
        "manifest_kind": "leaf_runtime_registry_contract",
        "domains": {
            domain: {
                "default_real_device_runtime_mode": _DEFAULT_REAL_DEVICE_RUNTIME_MODE.get(domain),
                "runtime_modes": list(_DOMAIN_RUNTIME_MODES.get(domain, [])),
                "runtime_artifacts": list(_DOMAIN_RUNTIME_ARTIFACTS.get(domain, [])),
                "runtime_quality_gates": dict(_DOMAIN_RUNTIME_QUALITY_GATES.get(domain, {})),
                "safety_profiles": {
                    mode: runtime_safety_profile(domain, mode)
                    for mode in _DOMAIN_RUNTIME_MODES.get(domain, [])
                },
            }
            for domain in domains
        },
    }


def validate_runtime_registry(contract: dict[str, object] | None = None) -> dict[str, object]:
    contract = contract or build_runtime_registry_contract()
    issues: list[str] = []
    domains = contract.get("domains")
    if not isinstance(domains, dict) or not domains:
        issues.append("runtime_registry: contract must define domains")
        domains = {}

    for domain, domain_contract in domains.items():
        if not isinstance(domain_contract, dict):
            issues.append(f"runtime_registry.{domain}: domain contract must be an object")
            continue
        modes = _string_list(domain_contract.get("runtime_modes"))
        default_mode = domain_contract.get("default_real_device_runtime_mode")
        artifacts = _string_list(domain_contract.get("runtime_artifacts"))
        quality_gates = domain_contract.get("runtime_quality_gates")
        safety_profiles = domain_contract.get("safety_profiles")
        if not modes:
            issues.append(f"runtime_registry.{domain}: runtime_modes must not be empty")
        if isinstance(default_mode, str) and default_mode and default_mode not in modes:
            issues.append(f"runtime_registry.{domain}: default_real_device_runtime_mode must be registered")
        if not isinstance(quality_gates, dict):
            issues.append(f"runtime_registry.{domain}: runtime_quality_gates must be an object")
            quality_gates = {}
        if not isinstance(safety_profiles, dict):
            issues.append(f"runtime_registry.{domain}: safety_profiles must be an object")
            safety_profiles = {}
        if len(artifacts) < len(modes):
            issues.append(f"runtime_registry.{domain}: runtime_artifacts must cover registered modes")
        for mode in modes:
            artifact = _mode_artifact_name(domain, mode)
            if artifact not in artifacts:
                issues.append(f"runtime_registry.{domain}.{mode}: runtime artifact {artifact} must be exported")
            quality_gate = quality_gates.get(artifact)
            if not isinstance(quality_gate, str) or not quality_gate:
                issues.append(f"runtime_registry.{domain}.{mode}: quality gate must be defined for {artifact}")
            elif quality_gate not in _RUNTIME_EXPERIENCE_RULES:
                issues.append(f"runtime_registry.{domain}.{mode}: experience rule must exist for {quality_gate}")
            safety = safety_profiles.get(mode)
            if not isinstance(safety, dict):
                issues.append(f"runtime_registry.{domain}.{mode}: safety profile must be defined")
                continue
            for field in ["risk_level", "mutates_device_state", "requires_approval_token", "operator_message"]:
                if field not in safety:
                    issues.append(f"runtime_registry.{domain}.{mode}: safety profile missing {field}")
            if not isinstance(safety.get("mutates_device_state"), bool):
                issues.append(f"runtime_registry.{domain}.{mode}: mutates_device_state must be boolean")
            if safety.get("mutates_device_state") and not isinstance(safety.get("requires_approval_token"), str):
                issues.append(f"runtime_registry.{domain}.{mode}: mutating mode must require approval token")

    return {
        "schema_version": "1.0",
        "manifest_kind": "leaf_runtime_registry_guard",
        "status": "stable" if not issues else "unstable",
        "issues": issues,
        "exit_code": 0 if not issues else 1,
        "domain_count": len(domains),
    }


def resolve_runtime_mode(
    runtime_mode: str | None = None,
    camera_direct: bool = False,
    camera_capture: bool = False,
) -> str | None:
    legacy_modes = []
    if camera_direct:
        legacy_modes.append("direct_smoke")
    if camera_capture:
        legacy_modes.append("capture_e2e")
    explicit_modes = [runtime_mode] if runtime_mode else []
    modes = explicit_modes + legacy_modes
    if len(modes) > 1:
        raise ValueError("only one runtime mode may be selected")
    return modes[0] if modes else None


def registered_runtime_modes(domain: str) -> list[str]:
    return list(_DOMAIN_RUNTIME_MODES.get(domain, []))


def experience_candidate_keys(domain: str) -> list[str]:
    runtime_keys = _DOMAIN_RUNTIME_ARTIFACTS.get(domain, [])
    return ["hypium_result", *runtime_keys, "pytest_result"]


def runtime_artifact_keys(domain: str) -> list[str]:
    return list(_DOMAIN_RUNTIME_ARTIFACTS.get(domain, []))


def quality_artifact_priority(domain: str) -> list[str]:
    domain_keys = _DOMAIN_QUALITY_ARTIFACTS.get(domain, [])
    diagnostic_keys = _DOMAIN_DIAGNOSTIC_ARTIFACTS.get(domain, [])
    priority = []
    for key in [*domain_keys, *_GENERIC_QUALITY_ARTIFACTS, *diagnostic_keys]:
        if key not in priority:
            priority.append(key)
    return priority


def default_real_device_runtime_mode(domain: str) -> str | None:
    return _DEFAULT_REAL_DEVICE_RUNTIME_MODE.get(domain)


def real_device_next_command(run_id: str, domain: str) -> str:
    runtime_mode = default_real_device_runtime_mode(domain)
    if runtime_mode:
        return f"python3 -m tools.leaf_author advance {run_id} --run-real --runtime-mode {runtime_mode} --serial <serial>"
    return f"python3 -m tools.leaf_author advance {run_id} --run-real --serial <serial>"


def approved_real_device_next_command(run_id: str, runtime_mode: str, approval_token: str | None = None) -> str:
    command = f"python3 -m tools.leaf_author advance {run_id} --run-real --runtime-mode {runtime_mode} --serial <serial>"
    if approval_token:
        command += f" --approval-token {approval_token}"
    return command


def runtime_quality_gates(domain: str) -> list[str]:
    gates_by_artifact = _DOMAIN_RUNTIME_QUALITY_GATES.get(domain, {})
    return [gate for key in quality_artifact_priority(domain) if (gate := gates_by_artifact.get(key))]


def runtime_safety_profile(domain: str, runtime_mode: str) -> dict[str, object]:
    profile = _DOMAIN_RUNTIME_SAFETY.get((domain, runtime_mode))
    if profile:
        return dict(profile)
    return {
        "risk_level": "unknown_real_device_action",
        "mutates_device_state": True,
        "requires_approval_token": "approve_real_device_action",
        "operator_message": f"Runtime mode {runtime_mode} for domain {domain} has no safety profile; explicit approval is required.",
    }


def classify_experience_result(domain: str, run_result: dict[str, object]) -> dict[str, object]:
    quality_gate = str(run_result.get("quality_gate", ""))
    status = str(run_result.get("status", ""))
    rule = _RUNTIME_EXPERIENCE_RULES.get(quality_gate)
    if rule and status == rule["status"]:
        return {
            "confidence": rule["confidence"],
            "notes": rule["notes"],
        }
    return {
        "confidence": 0.0,
        "notes": ["Draft execution is not a real device pass."],
    }


def run_domain_runtime(
    root: Path,
    run_id: str,
    domain: str,
    runtime_mode: str,
    serial: str | None = None,
    hdc_path: str = "hdc",
    hdc_runner: ProbeRunner | None = None,
) -> dict[str, object]:
    if domain == "camera" and runtime_mode == "direct_smoke":
        from tools.leaf_author.camera_smoke import run_camera_direct_smoke

        result = run_camera_direct_smoke(root, run_id, serial=serial or "", hdc_path=hdc_path, hdc_runner=hdc_runner)
        return {
            "stage": "camera_direct_smoke",
            "pass_quality_gate": "CAMERA_DIRECT_SMOKE_PASS",
            "inspect_action": "inspect_camera_direct_smoke",
            "result": result,
        }
    if domain == "camera" and runtime_mode == "capture_e2e":
        from tools.leaf_author.camera_smoke import run_camera_capture_e2e

        result = run_camera_capture_e2e(root, run_id, serial=serial or "", hdc_path=hdc_path, hdc_runner=hdc_runner)
        return {
            "stage": "camera_capture_e2e",
            "pass_quality_gate": "CAMERA_CAPTURE_E2E_PASS",
            "inspect_action": "inspect_camera_capture_e2e",
            "result": result,
        }
    raise ValueError(f"unsupported runtime mode for domain {domain}: {runtime_mode}")


def _mode_artifact_name(domain: str, runtime_mode: str) -> str:
    if domain == "camera" and runtime_mode == "direct_smoke":
        return "camera_direct_smoke"
    if domain == "camera" and runtime_mode == "capture_e2e":
        return "camera_capture_e2e"
    return f"{domain}_{runtime_mode}"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
