from __future__ import annotations

from pathlib import Path

from tools.leaf_author.device_probe import ProbeRunner


_GENERIC_EXPERIENCE_KEYS = ["hypium_result", "pytest_result"]
_DOMAIN_RUNTIME_ARTIFACTS = {
    "camera": ["camera_capture_e2e", "camera_direct_smoke"],
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


def experience_candidate_keys(domain: str) -> list[str]:
    runtime_keys = _DOMAIN_RUNTIME_ARTIFACTS.get(domain, [])
    return ["hypium_result", *runtime_keys, "pytest_result"]


def runtime_artifact_keys(domain: str) -> list[str]:
    return list(_DOMAIN_RUNTIME_ARTIFACTS.get(domain, []))


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
