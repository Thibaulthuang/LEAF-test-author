from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.leaf_author.authoring import advance_run, confirm_plan, resume_run, start_new_case
from tools.leaf_author.batch_registry import create_batch, inspect_batch, list_batches, resume_batch
from tools.leaf_author.build import build_openharmony_haps
from tools.leaf_author.camera_smoke import run_camera_capture_e2e, run_camera_direct_smoke, run_camera_smoke, write_camera_smoke_preflight
from tools.leaf_author.device_diagnostics import discover_test_targets, inspect_e2e_readiness, inspect_package_dir, inspect_test_target
from tools.leaf_author.device_probe import HdcProbe, select_real_device
from tools.leaf_author.e2e import run_e2e
from tools.leaf_author.e2e_report import write_e2e_preflight_report
from tools.leaf_author.extension_contract import build_extension_contract, export_extension_contract, validate_extension_contract
from tools.leaf_author.hypium import sync_openharmony_export
from tools.leaf_author.openharmony_discovery import discover_hap_artifacts
from tools.leaf_author.openharmony_project import scaffold_openharmony_test_project
from tools.leaf_author.phase_guard import build_agent_handoff_contract, validate_phase_contract
from tools.leaf_author.real_device_contract import build_real_device_contract, build_runtime_evidence_contract
from tools.leaf_author.reports import report_batch, report_run
from tools.leaf_author.run_audit import audit_batch, audit_run
from tools.leaf_author.run_registry import inspect_run, list_runs
from tools.leaf_author.runtime_registry import build_runtime_registry_contract
from tools.leaf_author.ui_tree_diagnostics import inspect_ui_tree
from tools.leaf_author.workflow_diagnostics import inspect_workflow_state


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="python -m tools.leaf_author")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_case = subparsers.add_parser("new-case")
    new_case.add_argument("domain")
    new_case.add_argument("teststep")
    new_case.add_argument("--run-id", required=True)
    new_case.add_argument("--probe-device", action="store_true")
    new_case.add_argument("--serial", default=None)
    new_case.add_argument("--root", type=Path, default=Path("."))
    new_case.add_argument("--plan-input", type=Path, default=None)

    probe = subparsers.add_parser("probe-device")
    probe.add_argument("--serial", default=None)

    select_device = subparsers.add_parser("select-device")
    select_device.add_argument("--serial", default=None)

    select_device_for_run = subparsers.add_parser("select-device-for-run")
    select_device_for_run.add_argument("run_id")
    select_device_for_run.add_argument("--root", type=Path, default=Path("."))
    select_device_for_run.add_argument("--serial", default=None)
    select_device_for_run.add_argument("--hdc-path", default="hdc")

    confirm = subparsers.add_parser("confirm-plan")
    confirm.add_argument("run_id")
    confirm.add_argument("--root", type=Path, default=Path("."))

    resume = subparsers.add_parser("resume")
    resume.add_argument("run_id")
    resume.add_argument("--root", type=Path, default=Path("."))
    resume.add_argument("--auto-safe", action="store_true")

    list_runs_parser = subparsers.add_parser("list-runs")
    list_runs_parser.add_argument("--root", type=Path, default=Path("."))
    list_runs_parser.add_argument("--limit", type=int, default=None)
    list_runs_parser.add_argument("--domain", default=None)

    inspect_run_parser = subparsers.add_parser("inspect-run")
    inspect_run_parser.add_argument("run_id")
    inspect_run_parser.add_argument("--root", type=Path, default=Path("."))

    workflow_diagnostics_parser = subparsers.add_parser("workflow-diagnostics")
    workflow_diagnostics_parser.add_argument("run_id")
    workflow_diagnostics_parser.add_argument("--root", type=Path, default=Path("."))

    create_batch_parser = subparsers.add_parser("create-batch")
    create_batch_parser.add_argument("batch_id")
    create_batch_parser.add_argument("--root", type=Path, default=Path("."))
    create_batch_parser.add_argument("--title", default=None)
    create_batch_parser.add_argument("--run-id", action="append", required=True)

    list_batches_parser = subparsers.add_parser("list-batches")
    list_batches_parser.add_argument("--root", type=Path, default=Path("."))

    inspect_batch_parser = subparsers.add_parser("inspect-batch")
    inspect_batch_parser.add_argument("batch_id")
    inspect_batch_parser.add_argument("--root", type=Path, default=Path("."))

    resume_batch_parser = subparsers.add_parser("resume-batch")
    resume_batch_parser.add_argument("batch_id")
    resume_batch_parser.add_argument("--root", type=Path, default=Path("."))
    resume_batch_parser.add_argument("--auto-safe", action="store_true")

    report_run_parser = subparsers.add_parser("report-run")
    report_run_parser.add_argument("run_id")
    report_run_parser.add_argument("--root", type=Path, default=Path("."))

    report_batch_parser = subparsers.add_parser("report-batch")
    report_batch_parser.add_argument("batch_id")
    report_batch_parser.add_argument("--root", type=Path, default=Path("."))

    inspect_ui_tree_parser = subparsers.add_parser("inspect-ui-tree")
    inspect_ui_tree_parser.add_argument("run_id")
    inspect_ui_tree_parser.add_argument("--root", type=Path, default=Path("."))
    inspect_ui_tree_parser.add_argument("--phase", default=None)
    inspect_ui_tree_parser.add_argument("--action-id", default=None)
    inspect_ui_tree_parser.add_argument("--id", dest="node_id", default=None)
    inspect_ui_tree_parser.add_argument("--text", default=None)
    inspect_ui_tree_parser.add_argument("--type", dest="node_type", default=None)
    clickable_group = inspect_ui_tree_parser.add_mutually_exclusive_group()
    clickable_group.add_argument("--clickable", dest="clickable", action="store_true")
    clickable_group.add_argument("--not-clickable", dest="clickable", action="store_false")
    inspect_ui_tree_parser.set_defaults(clickable=None)
    inspect_ui_tree_parser.add_argument("--limit", type=int, default=10)

    audit_run_parser = subparsers.add_parser("audit-run")
    audit_run_parser.add_argument("run_id")
    audit_run_parser.add_argument("--root", type=Path, default=Path("."))

    audit_batch_parser = subparsers.add_parser("audit-batch")
    audit_batch_parser.add_argument("batch_id")
    audit_batch_parser.add_argument("--root", type=Path, default=Path("."))

    extension_contract_parser = subparsers.add_parser("extension-contract")
    extension_contract_parser.add_argument("domain")

    export_extension_contract_parser = subparsers.add_parser("export-extension-contract")
    export_extension_contract_parser.add_argument("domain")
    export_extension_contract_parser.add_argument("--output", type=Path, required=True)

    validate_extension_contract_parser = subparsers.add_parser("validate-extension-contract")
    validate_extension_contract_parser.add_argument("domain")
    validate_extension_contract_parser.add_argument("--strict-real-device", action="store_true")

    subparsers.add_parser("phase-guard")
    subparsers.add_parser("agent-handoff-contract")
    subparsers.add_parser("real-device-contract")
    runtime_evidence_contract_parser = subparsers.add_parser("runtime-evidence-contract")
    runtime_evidence_contract_parser.add_argument("domain", nargs="?")
    subparsers.add_parser("runtime-registry-contract")

    advance = subparsers.add_parser("advance")
    advance.add_argument("run_id")
    advance.add_argument("--root", type=Path, default=Path("."))
    advance.add_argument("--serial", default=None)
    advance.add_argument("--run-real", action="store_true")
    advance.add_argument("--bundle-name", default=None)
    advance.add_argument("--module-name", default=None)
    advance.add_argument("--test-bundle-name", default=None)
    advance.add_argument("--test-module-name", default=None)
    advance.add_argument("--test-runner", default="OpenHarmonyTestRunner")
    advance.add_argument("--app-hap", type=Path, default=None)
    advance.add_argument("--test-hap", type=Path, default=None)
    advance.add_argument("--package-dir", type=Path, default=None)
    advance.add_argument("--runtime-mode", choices=["direct_smoke", "capture_e2e"], default=None)
    advance.add_argument("--camera-direct", action="store_true")
    advance.add_argument("--camera-capture", action="store_true")
    advance.add_argument("--approval-token", default=None)
    advance.add_argument("--hdc-path", default="hdc")

    inspect = subparsers.add_parser("inspect-target")
    inspect.add_argument("run_id")
    inspect.add_argument("--root", type=Path, default=Path("."))
    inspect.add_argument("--serial", required=True)
    inspect.add_argument("--bundle-name", required=True)

    discover_targets = subparsers.add_parser("discover-targets")
    discover_targets.add_argument("run_id")
    discover_targets.add_argument("--root", type=Path, default=Path("."))
    discover_targets.add_argument("--serial", required=True)
    discover_targets.add_argument("--bundle-filter", default=None)

    packages = subparsers.add_parser("inspect-packages")
    packages.add_argument("run_id")
    packages.add_argument("--root", type=Path, default=Path("."))
    packages.add_argument("--package-dir", type=Path, required=True)

    readiness = subparsers.add_parser("inspect-e2e-readiness")
    readiness.add_argument("run_id")
    readiness.add_argument("--root", type=Path, default=Path("."))
    readiness.add_argument("--serial", required=True)
    readiness.add_argument("--bundle-name", required=True)
    readiness.add_argument("--package-dir", type=Path, default=None)

    sync = subparsers.add_parser("sync-openharmony-export")
    sync.add_argument("run_id")
    sync.add_argument("--root", type=Path, default=Path("."))
    sync.add_argument("--target-module-dir", type=Path, required=True)

    build = subparsers.add_parser("build-openharmony-haps")
    build.add_argument("run_id")
    build.add_argument("--root", type=Path, default=Path("."))
    build.add_argument("--project-dir", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, default=None)
    build.add_argument("--build-command", nargs="+", default=None)
    build.add_argument("--build-arg", action="append", default=[])

    scaffold_project = subparsers.add_parser("scaffold-openharmony-test-project")
    scaffold_project.add_argument("run_id")
    scaffold_project.add_argument("--root", type=Path, default=Path("."))

    e2e = subparsers.add_parser("run-e2e")
    e2e.add_argument("run_id")
    e2e.add_argument("--root", type=Path, default=Path("."))
    e2e.add_argument("--serial", required=True)
    e2e.add_argument("--bundle-name", default=None)
    e2e.add_argument("--module-name", default=None)
    e2e.add_argument("--test-bundle-name", default=None)
    e2e.add_argument("--test-module-name", default=None)
    e2e.add_argument("--target-filter", default=None)
    e2e.add_argument("--test-runner", default="OpenHarmonyTestRunner")
    e2e.add_argument("--target-module-dir", type=Path, default=None)
    e2e.add_argument("--project-dir", type=Path, default=None)
    e2e.add_argument("--package-dir", type=Path, default=None)
    e2e.add_argument("--app-hap", type=Path, default=None)
    e2e.add_argument("--test-hap", type=Path, default=None)
    e2e.add_argument("--discover-root", type=Path, default=None)
    e2e.add_argument("--build-command", nargs="+", default=None)

    e2e_report = subparsers.add_parser("e2e-preflight-report")
    e2e_report.add_argument("run_id")
    e2e_report.add_argument("--root", type=Path, default=Path("."))
    e2e_report.add_argument("--serial", required=True)
    e2e_report.add_argument("--target-filter", default="camera")
    e2e_report.add_argument("--test-bundle-name", default=None)
    e2e_report.add_argument("--test-module-name", default=None)
    e2e_report.add_argument("--package-dir", type=Path, default=None)
    e2e_report.add_argument("--app-hap", type=Path, default=None)
    e2e_report.add_argument("--test-hap", type=Path, default=None)
    e2e_report.add_argument("--discover-root", type=Path, default=None)
    e2e_report.add_argument("--build-command", nargs="+", default=None)

    camera_preflight = subparsers.add_parser("camera-smoke-preflight")
    camera_preflight.add_argument("run_id")
    camera_preflight.add_argument("--root", type=Path, default=Path("."))
    camera_preflight.add_argument("--serial", required=True)
    camera_preflight.add_argument("--test-hap", type=Path, default=None)
    camera_preflight.add_argument("--package-dir", type=Path, default=None)
    camera_preflight.add_argument("--project-dir", type=Path, default=None)
    camera_preflight.add_argument("--target-module-dir", type=Path, default=None)
    camera_preflight.add_argument("--discover-root", type=Path, default=None)
    camera_preflight.add_argument("--build-command", nargs="+", default=None)

    camera_smoke = subparsers.add_parser("run-camera-smoke")
    camera_smoke.add_argument("run_id")
    camera_smoke.add_argument("--root", type=Path, default=Path("."))
    camera_smoke.add_argument("--serial", required=True)
    camera_smoke.add_argument("--test-hap", type=Path, default=None)
    camera_smoke.add_argument("--package-dir", type=Path, default=None)
    camera_smoke.add_argument("--project-dir", type=Path, default=None)
    camera_smoke.add_argument("--target-module-dir", type=Path, default=None)
    camera_smoke.add_argument("--discover-root", type=Path, default=None)
    camera_smoke.add_argument("--build-command", nargs="+", default=None)

    camera_direct_smoke = subparsers.add_parser("run-camera-direct-smoke")
    camera_direct_smoke.add_argument("run_id")
    camera_direct_smoke.add_argument("--root", type=Path, default=Path("."))
    camera_direct_smoke.add_argument("--serial", required=True)
    camera_direct_smoke.add_argument("--bundle-name", default="com.huawei.hmos.camera")
    camera_direct_smoke.add_argument("--module-name", default=None)
    camera_direct_smoke.add_argument("--ability-name", default="com.huawei.hmos.camera.MainAbility")
    camera_direct_smoke.add_argument("--hdc-path", default="hdc")

    camera_capture = subparsers.add_parser("run-camera-capture-e2e")
    camera_capture.add_argument("run_id")
    camera_capture.add_argument("--root", type=Path, default=Path("."))
    camera_capture.add_argument("--serial", required=True)
    camera_capture.add_argument("--bundle-name", default="com.huawei.hmos.camera")
    camera_capture.add_argument("--module-name", default=None)
    camera_capture.add_argument("--ability-name", default="com.huawei.hmos.camera.MainAbility")
    camera_capture.add_argument("--hdc-path", default="hdc")

    find_haps = subparsers.add_parser("find-haps")
    find_haps.add_argument("--search-root", type=Path, default=Path("."))

    args = parser.parse_args(argv)
    if args.command == "probe-device":
        print(json.dumps(HdcProbe().probe(serial=args.serial), ensure_ascii=False, indent=2))
        return 0
    if args.command == "select-device":
        result = HdcProbe().select_device(serial=args.serial)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "selected" else 1
    if args.command == "select-device-for-run":
        result = select_real_device(args.root, args.run_id, serial=args.serial, hdc_path=args.hdc_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "selected" else 1
    if args.command == "confirm-plan":
        print(json.dumps(confirm_plan(args.root, args.run_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "resume":
        print(json.dumps(resume_run(args.root, args.run_id, auto_safe=args.auto_safe), ensure_ascii=False, indent=2))
        return 0
    if args.command == "list-runs":
        print(json.dumps(list_runs(args.root, limit=args.limit, domain=args.domain), ensure_ascii=False, indent=2))
        return 0
    if args.command == "inspect-run":
        print(json.dumps(inspect_run(args.root, args.run_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "workflow-diagnostics":
        result = inspect_workflow_state(args.root, args.run_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "passed" else 1
    if args.command == "create-batch":
        print(json.dumps(create_batch(args.root, args.batch_id, args.run_id, title=args.title), ensure_ascii=False, indent=2))
        return 0
    if args.command == "list-batches":
        print(json.dumps(list_batches(args.root), ensure_ascii=False, indent=2))
        return 0
    if args.command == "inspect-batch":
        print(json.dumps(inspect_batch(args.root, args.batch_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "resume-batch":
        print(json.dumps(resume_batch(args.root, args.batch_id, auto_safe=args.auto_safe), ensure_ascii=False, indent=2))
        return 0
    if args.command == "report-run":
        print(json.dumps(report_run(args.root, args.run_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "report-batch":
        print(json.dumps(report_batch(args.root, args.batch_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "inspect-ui-tree":
        print(
            json.dumps(
                inspect_ui_tree(
                    args.root,
                    args.run_id,
                    phase=args.phase,
                    action_id=args.action_id,
                    node_id=args.node_id,
                    text=args.text,
                    node_type=args.node_type,
                    clickable=args.clickable,
                    limit=args.limit,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "audit-run":
        result = audit_run(args.root, args.run_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "passed" else 1
    if args.command == "audit-batch":
        result = audit_batch(args.root, args.batch_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "passed" else 1
    if args.command == "extension-contract":
        print(json.dumps(build_extension_contract(args.domain), ensure_ascii=False, indent=2))
        return 0
    if args.command == "export-extension-contract":
        print(json.dumps(export_extension_contract(args.domain, args.output), ensure_ascii=False, indent=2))
        return 0
    if args.command == "validate-extension-contract":
        result = validate_extension_contract(args.domain, strict_real_device=args.strict_real_device)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(result["exit_code"])
    if args.command == "phase-guard":
        result = validate_phase_contract()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(result["exit_code"])
    if args.command == "agent-handoff-contract":
        print(json.dumps(build_agent_handoff_contract(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "real-device-contract":
        print(json.dumps(build_real_device_contract(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "runtime-evidence-contract":
        print(json.dumps(build_runtime_evidence_contract(args.domain), ensure_ascii=False, indent=2))
        return 0
    if args.command == "runtime-registry-contract":
        print(json.dumps(build_runtime_registry_contract(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "advance":
        print(
            json.dumps(
                advance_run(
                    args.root,
                    args.run_id,
                    serial=args.serial,
                    run_real=args.run_real,
                    bundle_name=args.bundle_name,
                    module_name=args.module_name,
                    test_bundle_name=args.test_bundle_name,
                    test_module_name=args.test_module_name,
                    test_runner=args.test_runner,
                    app_hap=args.app_hap,
                    test_hap=args.test_hap,
                    package_dir=args.package_dir,
                    runtime_mode=args.runtime_mode,
                    camera_direct=args.camera_direct,
                    camera_capture=args.camera_capture,
                    approval_token=args.approval_token,
                    hdc_path=args.hdc_path,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "inspect-target":
        print(json.dumps(inspect_test_target(args.root, args.run_id, args.serial, args.bundle_name), ensure_ascii=False, indent=2))
        return 0
    if args.command == "discover-targets":
        print(json.dumps(discover_test_targets(args.root, args.run_id, args.serial, bundle_filter=args.bundle_filter), ensure_ascii=False, indent=2))
        return 0
    if args.command == "inspect-packages":
        print(json.dumps(inspect_package_dir(args.root, args.run_id, args.package_dir), ensure_ascii=False, indent=2))
        return 0
    if args.command == "inspect-e2e-readiness":
        print(
            json.dumps(
                inspect_e2e_readiness(
                    args.root,
                    args.run_id,
                    serial=args.serial,
                    bundle_name=args.bundle_name,
                    package_dir=args.package_dir,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "sync-openharmony-export":
        print(json.dumps(sync_openharmony_export(args.root, args.run_id, args.target_module_dir), ensure_ascii=False, indent=2))
        return 0
    if args.command == "build-openharmony-haps":
        print(
            json.dumps(
                build_openharmony_haps(
                    args.root,
                    args.run_id,
                    args.project_dir,
                    output_dir=args.output_dir,
                    build_command=(args.build_command + args.build_arg) if args.build_command else None,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "scaffold-openharmony-test-project":
        print(json.dumps(scaffold_openharmony_test_project(args.root, args.run_id), ensure_ascii=False, indent=2))
        return 0
    if args.command == "run-e2e":
        print(
            json.dumps(
                run_e2e(
                    args.root,
                    args.run_id,
                    serial=args.serial,
                    bundle_name=args.bundle_name,
                    module_name=args.module_name,
                    test_bundle_name=args.test_bundle_name,
                    test_module_name=args.test_module_name,
                    target_filter=args.target_filter,
                    test_runner=args.test_runner,
                    target_module_dir=args.target_module_dir,
                    project_dir=args.project_dir,
                    package_dir=args.package_dir,
                    app_hap=args.app_hap,
                    test_hap=args.test_hap,
                    discover_root=args.discover_root,
                    build_command=args.build_command,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "e2e-preflight-report":
        print(
            json.dumps(
                write_e2e_preflight_report(
                    args.root,
                    args.run_id,
                    serial=args.serial,
                    target_filter=args.target_filter,
                    test_bundle_name=args.test_bundle_name,
                    test_module_name=args.test_module_name,
                    package_dir=args.package_dir,
                    app_hap=args.app_hap,
                    test_hap=args.test_hap,
                    discover_root=args.discover_root,
                    build_command=args.build_command,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "camera-smoke-preflight":
        print(
            json.dumps(
                write_camera_smoke_preflight(
                    args.root,
                    args.run_id,
                    serial=args.serial,
                    test_hap=args.test_hap,
                    package_dir=args.package_dir,
                    project_dir=args.project_dir,
                    target_module_dir=args.target_module_dir,
                    discover_root=args.discover_root,
                    build_command=args.build_command,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "run-camera-smoke":
        print(
            json.dumps(
                run_camera_smoke(
                    args.root,
                    args.run_id,
                    serial=args.serial,
                    test_hap=args.test_hap,
                    package_dir=args.package_dir,
                    project_dir=args.project_dir,
                    target_module_dir=args.target_module_dir,
                    discover_root=args.discover_root,
                    build_command=args.build_command,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "run-camera-direct-smoke":
        print(
            json.dumps(
                run_camera_direct_smoke(
                    args.root,
                    args.run_id,
                    serial=args.serial,
                    bundle_name=args.bundle_name,
                    module_name=args.module_name,
                    ability_name=args.ability_name,
                    hdc_path=args.hdc_path,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "run-camera-capture-e2e":
        print(
            json.dumps(
                run_camera_capture_e2e(
                    args.root,
                    args.run_id,
                    serial=args.serial,
                    bundle_name=args.bundle_name,
                    module_name=args.module_name,
                    ability_name=args.ability_name,
                    hdc_path=args.hdc_path,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "find-haps":
        print(json.dumps(discover_hap_artifacts(args.search_root), ensure_ascii=False, indent=2))
        return 0
    plan_input = None
    if args.plan_input is not None:
        plan_input = json.loads(args.plan_input.read_text(encoding="utf-8"))
    result = start_new_case(
        args.root,
        args.domain,
        args.teststep,
        args.run_id,
        probe_device=args.probe_device,
        serial=args.serial,
        plan_input=plan_input,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
