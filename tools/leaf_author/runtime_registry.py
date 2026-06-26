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


def runtime_quality_gates(domain: str) -> list[str]:
    gates_by_artifact = _DOMAIN_RUNTIME_QUALITY_GATES.get(domain, {})
    return [gate for key in quality_artifact_priority(domain) if (gate := gates_by_artifact.get(key))]


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
