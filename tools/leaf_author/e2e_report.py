from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.device_diagnostics import discover_test_targets, inspect_e2e_readiness
from tools.leaf_author.device_probe import ProbeRunner
from tools.leaf_author.openharmony_discovery import discover_hap_artifacts, discover_openharmony_project, inspect_hap_profile
from tools.leaf_author.workflow import load_workflow, save_workflow


def write_e2e_preflight_report(
    root: Path,
    run_id: str,
    serial: str,
    target_filter: str = "camera",
    package_dir: Path | None = None,
    app_hap: Path | None = None,
    test_hap: Path | None = None,
    discover_root: Path | None = None,
    build_command: list[str] | None = None,
    test_bundle_name: str | None = None,
    test_module_name: str | None = None,
    hdc_runner: ProbeRunner | None = None,
) -> dict[str, object]:
    target_discovery = discover_test_targets(root, run_id, serial, hdc_runner=hdc_runner, bundle_filter=target_filter)
    selected_target = _first_candidate(target_discovery)
    project_discovery = discover_openharmony_project(discover_root or root)
    hap_discovery = discover_hap_artifacts(discover_root or root)
    resolved_app_hap = app_hap or _optional_path(hap_discovery.get("app_hap"))
    resolved_test_hap = test_hap or _optional_path(hap_discovery.get("test_hap"))
    explicit_test_profile = inspect_hap_profile(test_hap)
    resolved_test_bundle_name = (
        test_bundle_name
        or _optional_str(explicit_test_profile.get("bundle_name"))
        or _optional_str(hap_discovery.get("test_bundle_name"))
    )
    resolved_test_module_name = (
        test_module_name
        or _optional_str(explicit_test_profile.get("module_name"))
        or _optional_str(hap_discovery.get("test_module_name"))
    )
    resolved_package_dir = package_dir or _optional_path(project_discovery.get("package_dir")) or _optional_path(hap_discovery.get("package_dir"))
    bundle_name = str(selected_target.get("bundle_name", "")) if selected_target else ""
    explicit_haps = [Path(hap) for hap in (resolved_app_hap, resolved_test_hap) if hap is not None]
    readiness = inspect_e2e_readiness(
        root,
        run_id,
        serial=serial,
        bundle_name=bundle_name,
        package_dir=None if explicit_haps else resolved_package_dir,
        hdc_runner=hdc_runner,
        allow_install=True,
    ) if bundle_name else {
        "status": "not_ready",
        "quality_gate": "E2E_NOT_READY",
        "missing": ["TARGET_CANDIDATES_EMPTY"],
    }
    explicit_hap_error = _explicit_hap_error(app_hap=resolved_app_hap, test_hap=resolved_test_hap)
    if explicit_haps and _target_available(readiness) and _export_ready(readiness) and not explicit_hap_error:
        missing = []
        status = "ready"
    else:
        missing = [str(item) for item in readiness.get("missing", [])]
        if "HAP_PACKAGE_DIR_UNSPECIFIED" in missing and hap_discovery.get("quality_gate") != "HAP_ARTIFACTS_DISCOVERED":
            missing = [item for item in missing if item != "HAP_PACKAGE_DIR_UNSPECIFIED"]
            missing.append(str(hap_discovery.get("quality_gate", "HAP_ARTIFACTS_MISSING")))
        if explicit_hap_error:
            missing.append(explicit_hap_error)
        status = "ready" if readiness.get("status") == "ready" and not explicit_hap_error else "not_ready"
    payload = {
        "run_id": run_id,
        "status": status,
        "quality_gate": "E2E_PREFLIGHT_READY" if status == "ready" else "E2E_PREFLIGHT_NOT_READY",
        "serial": serial,
        "target_filter": target_filter,
        "selected_target": selected_target,
        "target_discovery": target_discovery,
        "openharmony_discovery": project_discovery,
        "hap_discovery": hap_discovery,
        "package_dir": str(resolved_package_dir) if resolved_package_dir is not None else None,
        "app_hap": str(resolved_app_hap) if resolved_app_hap is not None else None,
        "test_hap": str(resolved_test_hap) if resolved_test_hap is not None else None,
        "test_bundle_name": resolved_test_bundle_name,
        "test_module_name": resolved_test_module_name,
        "readiness": readiness,
        "missing": missing,
        "next_command": _next_command(
            run_id,
            serial,
            target_filter,
            resolved_package_dir,
            resolved_app_hap,
            resolved_test_hap,
            discover_root,
            build_command,
            resolved_test_bundle_name,
            resolved_test_module_name,
        ),
        "next_action": "run_e2e" if status == "ready" else "provide_test_hap_or_openharmony_project",
    }
    report_path = root / ".leaf" / "runs" / run_id / "e2e_preflight_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _attach_report(root, run_id, report_path, phase="e2e_ready" if status == "ready" else "e2e_not_ready")
    return {**payload, "report_path": str(report_path)}


def _first_candidate(discovery: dict[str, object]) -> dict[str, object] | None:
    candidates = discovery.get("candidates", [])
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
        return candidates[0]
    return None


def _optional_path(value: object) -> Path | None:
    if not value:
        return None
    return Path(str(value))


def _optional_str(value: object) -> str | None:
    if not value:
        return None
    return str(value)


def _target_available(readiness: dict[str, object]) -> bool:
    target = readiness.get("target", {})
    return isinstance(target, dict) and target.get("quality_gate") == "TARGET_BUNDLE_AVAILABLE"


def _export_ready(readiness: dict[str, object]) -> bool:
    export = readiness.get("export", {})
    return not isinstance(export, dict) or export.get("quality_gate") == "OPENHARMONY_EXPORT_READY"


def _explicit_hap_error(app_hap: Path | None, test_hap: Path | None) -> str:
    if app_hap is not None and test_hap is None:
        return "HAP_TEST_PACKAGE_MISSING"
    for hap in (app_hap, test_hap):
        if hap is None:
            continue
        path = Path(hap)
        if path.is_symlink():
            return "HAP_PACKAGE_INVALID"
        if path.suffix != ".hap":
            return "HAP_PACKAGE_INVALID"
        if not path.is_file():
            return "HAP_PACKAGE_MISSING"
    return ""


def _next_command(
    run_id: str,
    serial: str,
    target_filter: str,
    package_dir: Path | None,
    app_hap: Path | None,
    test_hap: Path | None,
    discover_root: Path | None,
    build_command: list[str] | None,
    test_bundle_name: str | None,
    test_module_name: str | None,
) -> str:
    parts = [
        ".venv/bin/python",
        "-m",
        "tools.leaf_author",
        "run-e2e",
        run_id,
        "--serial",
        serial,
        "--target-filter",
        target_filter,
    ]
    if package_dir is not None:
        parts.extend(["--package-dir", str(package_dir)])
    if app_hap is not None:
        parts.extend(["--app-hap", str(app_hap)])
    if test_hap is not None:
        parts.extend(["--test-hap", str(test_hap)])
    if discover_root is not None:
        parts.extend(["--discover-root", str(discover_root)])
    if test_bundle_name:
        parts.extend(["--test-bundle-name", test_bundle_name])
    if test_module_name:
        parts.extend(["--test-module-name", test_module_name])
    if build_command:
        parts.append("--build-command")
        parts.extend(build_command)
    return " ".join(parts)


def _attach_report(root: Path, run_id: str, report_path: Path, phase: str) -> None:
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    if not workflow_path.exists():
        return
    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    artifacts["e2e_preflight_report"] = str(report_path.relative_to(root))
    workflow["artifacts"] = artifacts
    workflow["current_phase"] = phase
    save_workflow(root, workflow)
