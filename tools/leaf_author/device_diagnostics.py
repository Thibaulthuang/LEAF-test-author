from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.device_probe import HdcProbe, ProbeRunner


def inspect_e2e_readiness(
    root: Path,
    run_id: str,
    serial: str,
    bundle_name: str,
    package_dir: Path | None = None,
    hdc_runner: ProbeRunner | None = None,
    hdc_path: str = "hdc",
    allow_install: bool = False,
) -> dict[str, object]:
    probe = HdcProbe(runner=hdc_runner, hdc_path=hdc_path)
    device = probe.probe(serial=serial)
    packages = inspect_package_dir(root, run_id, package_dir) if package_dir is not None else {
        "status": "unchecked",
        "quality_gate": "HAP_PACKAGE_DIR_UNSPECIFIED",
        "reason": "package_dir was not provided",
    }
    target = inspect_test_target(root, run_id, serial, bundle_name, hdc_runner=hdc_runner, hdc_path=hdc_path) if device.get("status") == "connected" else {
        "status": "unavailable",
        "quality_gate": "TARGET_UNCHECKED_DEVICE_UNAVAILABLE",
        "reason": device.get("reason", "device unavailable"),
    }
    export = _inspect_openharmony_export(root, run_id)
    if (
        allow_install
        and packages.get("quality_gate") == "HAP_PACKAGE_READY"
        and target.get("quality_gate") == "TARGET_BUNDLE_MISSING"
    ):
        target = {
            **target,
            "status": "install_required",
            "quality_gate": "TARGET_BUNDLE_INSTALL_REQUIRED",
            "install_source": "hap_package_dir",
            "reason": f"{target.get('reason', '')}; ready HAPs will be installed before Hypium execution",
        }
    missing = [
        str(item["quality_gate"])
        for item in (device, packages, target, export)
        if str(item.get("status")) not in {"connected", "ready", "available", "install_required"}
    ]
    status = "ready" if not missing else "not_ready"
    payload = {
        "run_id": run_id,
        "status": status,
        "quality_gate": "E2E_READY" if status == "ready" else "E2E_NOT_READY",
        "device": device,
        "packages": packages,
        "target": target,
        "export": export,
        "missing": missing,
    }
    _write_json_artifact(root, run_id, "e2e_readiness.json", payload, artifact_name="e2e_readiness", phase="e2e_ready" if status == "ready" else "e2e_not_ready")
    return payload


def inspect_package_dir(root: Path, run_id: str, package_dir: Path) -> dict[str, object]:
    package_path = Path(package_dir)
    if package_path.is_symlink():
        payload = {
            "run_id": run_id,
            "status": "invalid",
            "quality_gate": "HAP_PACKAGE_DIR_INVALID",
            "package_dir": str(package_path),
            "reason": f"package directory must not be a symlink: {package_path}",
        }
    elif not package_path.is_dir():
        payload = {
            "run_id": run_id,
            "status": "missing",
            "quality_gate": "HAP_PACKAGE_DIR_MISSING",
            "package_dir": str(package_path),
            "reason": f"package directory does not exist: {package_path}",
        }
    else:
        haps = sorted(package_path.rglob("*.hap"), key=lambda item: item.as_posix())
        symlink_haps = [hap for hap in haps if hap.is_symlink()]
        app_haps = [hap for hap in haps if not hap.is_symlink() and not _is_test_hap(hap)]
        test_haps = [hap for hap in haps if not hap.is_symlink() and _is_test_hap(hap)]
        if symlink_haps:
            payload = {
                "run_id": run_id,
                "status": "invalid",
                "quality_gate": "HAP_PACKAGE_INVALID",
                "package_dir": str(package_path),
                "hap_files": [str(hap) for hap in haps],
                "reason": f"package path must not be a symlink: {symlink_haps[0]}",
            }
        elif not haps:
            payload = {
                "run_id": run_id,
                "status": "empty",
                "quality_gate": "HAP_PACKAGE_EMPTY",
                "package_dir": str(package_path),
                "hap_files": [],
                "reason": f"no .hap files found in package directory: {package_path}",
            }
        elif not test_haps:
            payload = {
                "run_id": run_id,
                "status": "incomplete",
                "quality_gate": "HAP_TEST_PACKAGE_MISSING",
                "package_dir": str(package_path),
                "hap_files": [str(hap) for hap in haps],
                "app_haps": [str(hap) for hap in app_haps],
                "test_haps": [],
                "reason": "test HAP is missing; expected a .hap filename containing ohosTest or test",
            }
        elif not app_haps:
            payload = {
                "run_id": run_id,
                "status": "ready",
                "quality_gate": "HAP_TEST_PACKAGE_READY",
                "package_dir": str(package_path),
                "hap_files": [str(hap) for hap in haps],
                "app_haps": [],
                "test_haps": [str(hap) for hap in test_haps],
                "reason": "test HAP is ready; app HAP is not required when the target bundle is already installed",
            }
        else:
            payload = {
                "run_id": run_id,
                "status": "ready",
                "quality_gate": "HAP_PACKAGE_READY",
                "package_dir": str(package_path),
                "hap_files": [str(hap) for hap in haps],
                "app_haps": [str(hap) for hap in app_haps],
                "test_haps": [str(hap) for hap in test_haps],
                "reason": "",
            }
    _write_json_artifact(root, run_id, "package_inventory.json", payload, artifact_name="package_inventory", phase="package_inspected")
    return payload


def inspect_test_target(
    root: Path,
    run_id: str,
    serial: str,
    bundle_name: str,
    hdc_runner: ProbeRunner | None = None,
    hdc_path: str = "hdc",
) -> dict[str, object]:
    probe = HdcProbe(runner=hdc_runner, hdc_path=hdc_path)
    result = probe.runner([probe.hdc_path, "-t", serial, "shell", "bm", "dump", "-n", bundle_name], 30)
    output = (result.stdout or result.stderr).strip()
    lowered = output.lower()
    if "connect server failed" in lowered or "not connect to server" in lowered:
        payload = {
            "run_id": run_id,
            "status": "unavailable",
            "quality_gate": "HDC_UNAVAILABLE",
            "serial": serial,
            "bundle_name": bundle_name,
            "reason": output,
        }
    elif result.exit_code != 0 or "bundle not exist" in lowered or "not installed" in lowered or "failed to get information" in lowered:
        payload = {
            "run_id": run_id,
            "status": "missing",
            "quality_gate": "TARGET_BUNDLE_MISSING",
            "serial": serial,
            "bundle_name": bundle_name,
            "reason": output,
        }
    else:
        payload = {
            "run_id": run_id,
            "status": "available",
            "quality_gate": "TARGET_BUNDLE_AVAILABLE",
            "serial": serial,
            "bundle_name": bundle_name,
            "module_name": _extract_field(output, "moduleName") or "unknown",
            "raw_output_excerpt": output[:2000],
        }
    _write_json_artifact(root, run_id, "target_diagnostics.json", payload, artifact_name="target_diagnostics", phase="target_inspected")
    return payload


def discover_test_targets(
    root: Path,
    run_id: str,
    serial: str,
    hdc_runner: ProbeRunner | None = None,
    hdc_path: str = "hdc",
    bundle_filter: str | None = None,
) -> dict[str, object]:
    probe = HdcProbe(runner=hdc_runner, hdc_path=hdc_path)
    result = probe.runner([probe.hdc_path, "-t", serial, "shell", "bm", "dump", "-a"], 30)
    output = (result.stdout or result.stderr).strip()
    lowered = output.lower()
    if "connect server failed" in lowered or "not connect to server" in lowered:
        payload = {
            "run_id": run_id,
            "status": "unavailable",
            "quality_gate": "HDC_UNAVAILABLE",
            "serial": serial,
            "reason": output,
            "candidates": [],
        }
    elif result.exit_code != 0:
        payload = {
            "run_id": run_id,
            "status": "failed",
            "quality_gate": "TARGET_DISCOVERY_FAILED",
            "serial": serial,
            "reason": output,
            "candidates": [],
        }
    else:
        candidates = _parse_bundle_candidates(output, bundle_filter=bundle_filter)
        candidates = _enrich_unknown_modules(probe, serial, candidates)
        payload = {
            "run_id": run_id,
            "status": "found" if candidates else "empty",
            "quality_gate": "TARGET_CANDIDATES_FOUND" if candidates else "TARGET_CANDIDATES_EMPTY",
            "serial": serial,
            "bundle_filter": bundle_filter,
            "candidates": candidates,
            "raw_output_excerpt": output[:2000],
        }
    _write_json_artifact(root, run_id, "target_discovery.json", payload, artifact_name="target_discovery", phase="target_discovered")
    return payload


def _enrich_unknown_modules(probe: HdcProbe, serial: str, candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    enriched: list[dict[str, str]] = []
    for candidate in candidates:
        if candidate.get("module_name") != "unknown":
            enriched.append(candidate)
            continue
        bundle_name = candidate["bundle_name"]
        result = probe.runner([probe.hdc_path, "-t", serial, "shell", "bm", "dump", "-n", bundle_name], 30)
        output = (result.stdout or result.stderr).strip()
        module_name = _extract_field(output, "moduleName")
        enriched.append({**candidate, "module_name": module_name or "unknown"})
    return enriched


def _write_json_artifact(root: Path, run_id: str, file_name: str, payload: dict[str, object], artifact_name: str | None = None, phase: str | None = None) -> None:
    path = root / ".leaf" / "runs" / run_id / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _attach_workflow_artifact(root, run_id, artifact_name, phase, path)


def _attach_workflow_artifact(root: Path, run_id: str, artifact_name: str | None, phase: str | None, path: Path) -> None:
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    if artifact_name is None or not workflow_path.exists():
        return
    from tools.leaf_author.workflow import load_workflow, save_workflow

    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    artifacts[artifact_name] = str(path.relative_to(root))
    workflow["artifacts"] = artifacts
    if phase:
        workflow["current_phase"] = phase
    save_workflow(root, workflow)


def _inspect_openharmony_export(root: Path, run_id: str) -> dict[str, object]:
    export_dir = root / ".leaf" / "runs" / run_id / "openharmony_test_project"
    case_dir = export_dir / "src" / "ohosTest" / "ets" / "test"
    aw_path = export_dir / "src" / "ohosTest" / "ets" / "aw" / "CameraAW.ets"
    entry_path = case_dir / "List.test.ets"
    module_path = export_dir / "src" / "ohosTest" / "module.json5"
    package_path = export_dir / "src" / "ohosTest" / "oh-package.json5"
    case_files = sorted(case_dir.glob("*.test.ets")) if case_dir.is_dir() else []
    if not export_dir.is_dir():
        return {
            "status": "missing",
            "quality_gate": "OPENHARMONY_EXPORT_MISSING",
            "export_dir": str(export_dir),
            "reason": "openharmony test project export is missing",
        }
    if not case_files:
        return {
            "status": "incomplete",
            "quality_gate": "OPENHARMONY_EXPORT_CASE_MISSING",
            "export_dir": str(export_dir),
            "reason": "no Hypium .test.ets file found under export test directory",
        }
    if not aw_path.is_file():
        return {
            "status": "incomplete",
            "quality_gate": "OPENHARMONY_EXPORT_AW_MISSING",
            "export_dir": str(export_dir),
            "case_files": [str(path) for path in case_files],
            "reason": "CameraAW.ets export is missing",
        }
    if not entry_path.is_file():
        return {
            "status": "incomplete",
            "quality_gate": "OPENHARMONY_EXPORT_ENTRY_MISSING",
            "export_dir": str(export_dir),
            "case_files": [str(path) for path in case_files],
            "aw_path": str(aw_path),
            "entry_path": str(entry_path),
            "reason": "OpenHarmony Hypium List.test.ets entry file is missing",
        }
    missing_metadata = [str(path) for path in (module_path, package_path) if not path.is_file()]
    if missing_metadata:
        return {
            "status": "incomplete",
            "quality_gate": "OPENHARMONY_EXPORT_METADATA_MISSING",
            "export_dir": str(export_dir),
            "case_files": [str(path) for path in case_files],
            "aw_path": str(aw_path),
            "missing_metadata": missing_metadata,
            "reason": "OpenHarmony test module metadata is missing",
        }
    return {
        "status": "ready",
        "quality_gate": "OPENHARMONY_EXPORT_READY",
        "export_dir": str(export_dir),
        "case_files": [str(path) for path in case_files],
        "aw_path": str(aw_path),
        "entry_path": str(entry_path),
        "module_path": str(module_path),
        "package_path": str(package_path),
        "reason": "",
    }


def _is_test_hap(path: Path) -> bool:
    name = path.name.lower()
    return "ohostest" in name or "test" in name


def _extract_field(output: str, field: str) -> str:
    prefix = f"{field}:"
    json_prefix = f'"{field}":'
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
        if stripped.startswith(json_prefix):
            value = stripped[len(json_prefix) :].strip().rstrip(",")
            return value.strip('"')
    return ""


def _parse_bundle_candidates(output: str, bundle_filter: str | None = None) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    current_bundle = ""
    current_module = ""
    lowered_filter = bundle_filter.lower() if bundle_filter else ""
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("bundleName:"):
            if current_bundle:
                _append_candidate(candidates, current_bundle, current_module, lowered_filter)
            current_bundle = stripped[len("bundleName:") :].strip()
            current_module = ""
        elif stripped.startswith("moduleName:"):
            current_module = stripped[len("moduleName:") :].strip()
        elif _looks_like_bundle_name(stripped):
            if current_bundle:
                _append_candidate(candidates, current_bundle, current_module, lowered_filter)
            current_bundle = stripped
            current_module = ""
    if current_bundle:
        _append_candidate(candidates, current_bundle, current_module, lowered_filter)
    return candidates


def _append_candidate(candidates: list[dict[str, str]], bundle_name: str, module_name: str, lowered_filter: str) -> None:
    if lowered_filter and lowered_filter not in bundle_name.lower() and lowered_filter not in module_name.lower():
        return
    candidates.append({"bundle_name": bundle_name, "module_name": module_name or "unknown"})


def _looks_like_bundle_name(value: str) -> bool:
    if not value or value.startswith("ID:") or " " in value or ":" in value:
        return False
    parts = value.split(".")
    return len(parts) >= 3 and all(part.replace("_", "").isalnum() for part in parts)
