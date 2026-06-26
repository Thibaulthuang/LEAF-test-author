from __future__ import annotations

from pathlib import Path

from tools.leaf_author.device_probe import ProbeRunner


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
