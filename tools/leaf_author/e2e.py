from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.authoring import advance_run
from tools.leaf_author.build import BuildRunner, build_openharmony_haps
from tools.leaf_author.device_diagnostics import discover_test_targets, inspect_e2e_readiness
from tools.leaf_author.device_probe import ProbeRunner
from tools.leaf_author.hypium import sync_openharmony_export
from tools.leaf_author.openharmony_discovery import discover_hap_artifacts, discover_openharmony_project, inspect_hap_profile
from tools.leaf_author.workflow import load_workflow, save_workflow


def run_e2e(
    root: Path,
    run_id: str,
    serial: str,
    bundle_name: str | None,
    module_name: str | None = None,
    test_bundle_name: str | None = None,
    test_module_name: str | None = None,
    test_runner: str = "OpenHarmonyTestRunner",
    target_filter: str | None = None,
    target_module_dir: Path | None = None,
    project_dir: Path | None = None,
    package_dir: Path | None = None,
    app_hap: Path | None = None,
    test_hap: Path | None = None,
    discover_root: Path | None = None,
    build_command: list[str] | None = None,
    hdc_runner: ProbeRunner | None = None,
    build_runner: BuildRunner | None = None,
) -> dict[str, object]:
    stages: list[str] = []
    sync_result: dict[str, object] | None = None
    build_result: dict[str, object] | None = None
    discovery: dict[str, object] | None = None
    hap_discovery: dict[str, object] | None = None
    target_discovery: dict[str, object] | None = None
    resolved_package_dir = package_dir
    resolved_app_hap = app_hap
    resolved_test_hap = test_hap
    explicit_test_profile = inspect_hap_profile(resolved_test_hap)
    test_bundle_name = test_bundle_name or _optional_str(explicit_test_profile.get("bundle_name"))
    test_module_name = test_module_name or _optional_str(explicit_test_profile.get("module_name"))

    if not bundle_name:
        target_discovery = discover_test_targets(root, run_id, serial, hdc_runner=hdc_runner, bundle_filter=target_filter)
        stages.append("target_discovery")
        candidates = target_discovery.get("candidates", [])
        if not candidates:
            return _finish(root, run_id, {
                "run_id": run_id,
                "status": "not_ready",
                "quality_gate": str(target_discovery.get("quality_gate", "TARGET_CANDIDATES_EMPTY")),
                "stages": stages,
                "target_discovery": target_discovery,
                "next_action": "provide_bundle_name",
            })
        selected = candidates[0]
        if isinstance(selected, dict):
            bundle_name = str(selected.get("bundle_name", ""))
            module_name = module_name or str(selected.get("module_name", ""))

    has_explicit_haps = resolved_app_hap is not None or resolved_test_hap is not None

    if target_module_dir is None or project_dir is None or (resolved_package_dir is None and not has_explicit_haps):
        discovery = discover_openharmony_project(discover_root or root)
        stages.append("openharmony_discovery")
        if discovery.get("status") == "found":
            target_module_dir = target_module_dir or _optional_path(discovery.get("target_module_dir"))
            project_dir = project_dir or _optional_path(discovery.get("project_dir"))
            resolved_package_dir = resolved_package_dir or _optional_path(discovery.get("package_dir"))
        if resolved_package_dir is None and not has_explicit_haps:
            hap_discovery = discover_hap_artifacts(discover_root or root)
            stages.append("hap_discovery")
            if hap_discovery.get("status") == "found":
                resolved_package_dir = _optional_path(hap_discovery.get("package_dir"))
                resolved_app_hap = _optional_path(hap_discovery.get("app_hap"))
                resolved_test_hap = _optional_path(hap_discovery.get("test_hap"))
                test_bundle_name = test_bundle_name or _optional_str(hap_discovery.get("test_bundle_name"))
                test_module_name = test_module_name or _optional_str(hap_discovery.get("test_module_name"))
                has_explicit_haps = resolved_app_hap is not None or resolved_test_hap is not None
            elif project_dir is None and resolved_package_dir is None:
                return _finish(root, run_id, {
                    "run_id": run_id,
                    "status": "not_ready",
                    "quality_gate": str(hap_discovery.get("quality_gate", discovery.get("quality_gate", "OPENHARMONY_PROJECT_MISSING"))),
                    "stages": stages,
                    "target_discovery": target_discovery,
                    "discovery": discovery,
                    "hap_discovery": hap_discovery,
                    "next_action": "provide_openharmony_project_or_haps",
                })

    if target_module_dir is not None:
        sync_result = sync_openharmony_export(root, run_id, target_module_dir)
        stages.append("openharmony_sync")

    if project_dir is not None:
        build_result = build_openharmony_haps(
            root,
            run_id,
            project_dir,
            output_dir=resolved_package_dir,
            build_command=build_command,
            runner=build_runner,
        )
        stages.append("openharmony_build")
        if build_result.get("status") != "built":
            return _finish(root, run_id, {
                "run_id": run_id,
                "status": "failed",
                "quality_gate": str(build_result.get("quality_gate", "OPENHARMONY_BUILD_FAILED")),
                "stages": stages,
                "target_discovery": target_discovery,
                "discovery": discovery,
                "hap_discovery": hap_discovery,
                "sync": sync_result,
                "build": build_result,
                "next_action": "inspect_openharmony_build",
            })
        resolved_package_dir = Path(str(build_result["package_dir"]))
        package_test_profile = inspect_hap_profile(_find_test_hap(resolved_package_dir))
        test_bundle_name = test_bundle_name or _optional_str(package_test_profile.get("bundle_name"))
        test_module_name = test_module_name or _optional_str(package_test_profile.get("module_name"))

    readiness = inspect_e2e_readiness(
        root,
        run_id,
        serial=serial,
        bundle_name=bundle_name,
        package_dir=resolved_package_dir if not has_explicit_haps else None,
        hdc_runner=hdc_runner,
        allow_install=True,
    )
    stages.append("e2e_readiness")
    target_ready_for_explicit_haps = has_explicit_haps and readiness.get("target", {}).get("quality_gate") == "TARGET_BUNDLE_AVAILABLE"
    if readiness.get("status") != "ready" and not target_ready_for_explicit_haps:
        return _finish(root, run_id, {
            "run_id": run_id,
            "status": "not_ready",
            "quality_gate": str(readiness.get("quality_gate", "E2E_NOT_READY")),
            "stages": stages,
            "target_discovery": target_discovery,
            "discovery": discovery,
            "hap_discovery": hap_discovery,
            "sync": sync_result,
            "build": build_result,
            "readiness": readiness,
            "next_action": "prepare_haps_or_target_bundle",
        })
    if target_ready_for_explicit_haps:
        workflow = load_workflow(root, run_id)
        workflow["current_phase"] = "pytest_ran"
        save_workflow(root, workflow)

    real_result = advance_run(
        root,
        run_id,
        hdc_runner=hdc_runner,
        serial=serial,
        run_real=True,
        bundle_name=bundle_name,
        module_name=module_name,
        test_bundle_name=test_bundle_name,
        test_module_name=test_module_name,
        test_runner=test_runner,
        package_dir=None if has_explicit_haps else resolved_package_dir,
        app_hap=resolved_app_hap,
        test_hap=resolved_test_hap,
    )
    stages.extend(str(stage) for stage in real_result.get("stages", []))
    passed = real_result.get("status") == "complete"
    return _finish(root, run_id, {
        "run_id": run_id,
        "status": "complete" if passed else "failed",
        "quality_gate": "E2E_REAL_PASS" if passed else "E2E_REAL_FAILED",
        "stages": stages,
        "target_discovery": target_discovery,
        "discovery": discovery,
        "hap_discovery": hap_discovery,
        "sync": sync_result,
        "build": build_result,
        "readiness": readiness,
        "real_result": real_result,
        "next_action": real_result.get("next_action", "inspect_hypium_result"),
    })


def _optional_path(value: object) -> Path | None:
    if not value:
        return None
    return Path(str(value))


def _optional_str(value: object) -> str | None:
    if not value:
        return None
    return str(value)


def _find_test_hap(package_dir: Path | None) -> Path | None:
    if package_dir is None or not package_dir.is_dir():
        return None
    test_haps = sorted(
        [
            hap
            for hap in package_dir.rglob("*.hap")
            if hap.is_file() and not hap.is_symlink() and ("ohostest" in hap.name.lower() or "test" in hap.name.lower())
        ],
        key=lambda item: (len(item.parts), item.as_posix()),
    )
    return test_haps[0] if test_haps else None


def _finish(root: Path, run_id: str, payload: dict[str, object]) -> dict[str, object]:
    path = root / ".leaf" / "runs" / run_id / "e2e_run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    if workflow_path.exists():
        workflow = load_workflow(root, run_id)
        artifacts = dict(workflow.get("artifacts", {}))
        artifacts["e2e_run"] = str(path.relative_to(root))
        workflow["artifacts"] = artifacts
        status = str(payload.get("status", ""))
        if status == "complete":
            workflow["current_phase"] = "e2e_complete"
        elif status == "not_ready":
            workflow["current_phase"] = "e2e_not_ready"
        else:
            workflow["current_phase"] = "e2e_failed"
        save_workflow(root, workflow)
    return {**payload, "e2e_run_path": str(path)}
