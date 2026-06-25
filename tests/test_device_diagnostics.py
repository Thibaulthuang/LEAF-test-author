import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tools.leaf_author.device_diagnostics import discover_test_targets, inspect_e2e_readiness, inspect_package_dir, inspect_test_target
from tools.leaf_author.device_probe import ProbeCommandResult


class DeviceDiagnosticsTests(unittest.TestCase):
    def test_inspect_test_target_reports_installed_bundle(self):
        calls = []

        def runner(args, timeout_s):
            calls.append(args)
            if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.example.leaf"]:
                return ProbeCommandResult(0, "bundleName: com.example.leaf\nmoduleName: entry\n", "")
            return ProbeCommandResult(1, "", f"unexpected {args}")

        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_test_target(Path(tmp), "diag-001", "SERIAL123", "com.example.leaf", hdc_runner=runner)

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["bundle_name"], "com.example.leaf")
        self.assertEqual(result["module_name"], "entry")
        self.assertEqual(calls, [["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.example.leaf"]])

    def test_inspect_test_target_extracts_json_style_module_name(self):
        def runner(args, timeout_s):
            return ProbeCommandResult(0, '"bundleName": "com.example.leaf",\n"moduleName": "entry",\n', "")

        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_test_target(Path(tmp), "diag-json", "SERIAL123", "com.example.leaf", hdc_runner=runner)

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["module_name"], "entry")

    def test_inspect_test_target_reports_missing_bundle(self):
        def runner(args, timeout_s):
            return ProbeCommandResult(0, "bundle not exist -n com.example.leaf\n", "")

        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_test_target(Path(tmp), "diag-002", "SERIAL123", "com.example.leaf", hdc_runner=runner)

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["quality_gate"], "TARGET_BUNDLE_MISSING")
        self.assertIn("bundle not exist", result["reason"])

    def test_inspect_test_target_reports_bm_error_text_as_missing(self):
        def runner(args, timeout_s):
            return ProbeCommandResult(0, "error: failed to get information and the parameters may be wrong.\n", "")

        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_test_target(Path(tmp), "diag-004", "SERIAL123", "com.example.leaf", hdc_runner=runner)

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["quality_gate"], "TARGET_BUNDLE_MISSING")

    def test_inspect_test_target_treats_hdc_transport_text_as_unavailable(self):
        def runner(args, timeout_s):
            return ProbeCommandResult(0, "Connect server failed\n", "")

        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_test_target(Path(tmp), "diag-003", "SERIAL123", "com.example.leaf", hdc_runner=runner)

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["quality_gate"], "HDC_UNAVAILABLE")
        self.assertIn("Connect server failed", result["reason"])

    def test_discover_test_targets_parses_bundle_and_module_candidates(self):
        calls = []

        def runner(args, timeout_s):
            calls.append(args)
            if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-a"]:
                return ProbeCommandResult(
                    0,
                    "bundleName: com.example.camera\nmoduleName: entry\n"
                    "bundleName: com.example.gallery\nmoduleName: photos\n",
                    "",
                )
            return ProbeCommandResult(1, "", f"unexpected {args}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from tools.leaf_author.workflow import create_workflow, load_workflow

            create_workflow(root, "camera", "打开相机；点击拍照", "targets-001")
            result = discover_test_targets(root, "targets-001", "SERIAL123", hdc_runner=runner, bundle_filter="camera")

            self.assertEqual(result["status"], "found")
            self.assertEqual(result["quality_gate"], "TARGET_CANDIDATES_FOUND")
            self.assertEqual(result["candidates"], [{"bundle_name": "com.example.camera", "module_name": "entry"}])
            self.assertEqual(calls, [["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-a"]])
            self.assertTrue((root / ".leaf" / "runs" / "targets-001" / "target_discovery.json").exists())
            workflow = load_workflow(root, "targets-001")
            self.assertEqual(workflow["artifacts"]["target_discovery"], ".leaf/runs/targets-001/target_discovery.json")
            self.assertEqual(workflow["current_phase"], "target_discovered")

    def test_discover_test_targets_parses_bm_dump_a_package_list_format(self):
        def runner(args, timeout_s):
            if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-a"]:
                return ProbeCommandResult(
                    0,
                    "ID: 100:\n"
                    "\tcom.huawei.hmos.browser\n"
                    "\tcom.huawei.hmos.camera\n"
                    "\tcom.huawei.hmos.gallery\n",
                    "",
                )
            return ProbeCommandResult(1, "", f"unexpected {args}")

        with tempfile.TemporaryDirectory() as tmp:
            result = discover_test_targets(Path(tmp), "targets-list", "SERIAL123", hdc_runner=runner, bundle_filter="camera")

        self.assertEqual(result["status"], "found")
        self.assertEqual(result["candidates"], [{"bundle_name": "com.huawei.hmos.camera", "module_name": "unknown"}])

    def test_discover_test_targets_enriches_unknown_module_from_bundle_dump(self):
        calls = []

        def runner(args, timeout_s):
            calls.append(args)
            if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-a"]:
                return ProbeCommandResult(0, "ID: 100:\n\tcom.huawei.hmos.camera\n", "")
            if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
            return ProbeCommandResult(1, "", f"unexpected {args}")

        with tempfile.TemporaryDirectory() as tmp:
            result = discover_test_targets(Path(tmp), "targets-enrich", "SERIAL123", hdc_runner=runner, bundle_filter="camera")

        self.assertEqual(result["candidates"], [{"bundle_name": "com.huawei.hmos.camera", "module_name": "phone"}])
        self.assertEqual(
            calls,
            [
                ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-a"],
                ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"],
            ],
        )

    def test_inspect_package_dir_identifies_app_and_test_hap_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from tools.leaf_author.workflow import create_workflow

            create_workflow(root, "camera", "打开相机；点击拍照", "pkg-001")
            package_dir = root / "packages"
            package_dir.mkdir()
            (package_dir / "entry-default.hap").write_text("app", encoding="utf-8")
            (package_dir / "entry-ohosTest.hap").write_text("test", encoding="utf-8")

            result = inspect_package_dir(root, "pkg-001", package_dir)

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["quality_gate"], "HAP_PACKAGE_READY")
            self.assertEqual(result["app_haps"], [str(package_dir / "entry-default.hap")])
            self.assertEqual(result["test_haps"], [str(package_dir / "entry-ohosTest.hap")])
            self.assertTrue((root / ".leaf" / "runs" / "pkg-001" / "package_inventory.json").exists())
            from tools.leaf_author.workflow import load_workflow

            workflow = load_workflow(root, "pkg-001")
            self.assertEqual(workflow["current_phase"], "package_inspected")
            self.assertEqual(workflow["artifacts"]["package_inventory"], ".leaf/runs/pkg-001/package_inventory.json")

    def test_inspect_package_dir_reports_missing_test_hap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "packages"
            package_dir.mkdir()
            (package_dir / "entry-default.hap").write_text("app", encoding="utf-8")

            result = inspect_package_dir(root, "pkg-002", package_dir)

            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["quality_gate"], "HAP_TEST_PACKAGE_MISSING")
            self.assertIn("test HAP", result["reason"])

    def test_inspect_package_dir_allows_test_only_hap_for_installed_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "packages"
            package_dir.mkdir()
            test_hap = package_dir / "entry-ohosTest.hap"
            test_hap.write_text("test", encoding="utf-8")

            result = inspect_package_dir(root, "pkg-test-only", package_dir)

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["quality_gate"], "HAP_TEST_PACKAGE_READY")
            self.assertEqual(result["app_haps"], [])
            self.assertEqual(result["test_haps"], [str(test_hap)])

    def test_inspect_package_dir_recursively_finds_nested_haps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "build"
            app_dir = package_dir / "default" / "outputs"
            test_dir = package_dir / "ohosTest" / "outputs"
            app_dir.mkdir(parents=True)
            test_dir.mkdir(parents=True)
            app_hap = app_dir / "entry-default.hap"
            test_hap = test_dir / "entry-ohosTest.hap"
            app_hap.write_text("app", encoding="utf-8")
            test_hap.write_text("test", encoding="utf-8")

            result = inspect_package_dir(root, "pkg-nested", package_dir)

            self.assertEqual(result["quality_gate"], "HAP_PACKAGE_READY")
            self.assertEqual(result["app_haps"], [str(app_hap)])
            self.assertEqual(result["test_haps"], [str(test_hap)])

    def test_cli_inspect_packages_outputs_inventory_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "packages"
            package_dir.mkdir()
            (package_dir / "entry-default.hap").write_text("app", encoding="utf-8")
            (package_dir / "entry-ohosTest.hap").write_text("test", encoding="utf-8")
            output = StringIO()

            from tools.leaf_author.__main__ import main

            with redirect_stdout(output):
                exit_code = main(["inspect-packages", "pkg-cli", "--root", str(root), "--package-dir", str(package_dir)])

            self.assertEqual(exit_code, 0)
            payload = __import__("json").loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "HAP_PACKAGE_READY")

    def test_cli_discover_targets_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = StringIO()

            from tools.leaf_author.__main__ import main

            with patch(
                "tools.leaf_author.__main__.discover_test_targets",
                return_value={"run_id": "targets-cli", "quality_gate": "TARGET_CANDIDATES_FOUND"},
            ) as discover, redirect_stdout(output):
                exit_code = main(
                    [
                        "discover-targets",
                        "targets-cli",
                        "--root",
                        str(root),
                        "--serial",
                        "SERIAL123",
                        "--bundle-filter",
                        "camera",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = __import__("json").loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "TARGET_CANDIDATES_FOUND")
            discover.assert_called_once()

    def test_inspect_e2e_readiness_reports_all_missing_real_execution_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from tools.leaf_author.workflow import create_workflow

            create_workflow(root, "camera", "打开相机；点击拍照", "ready-001")
            package_dir = root / "packages"
            package_dir.mkdir()
            export_dir = root / ".leaf" / "runs" / "ready-001" / "openharmony_test_project"
            case_dir = export_dir / "src" / "ohosTest" / "ets" / "test"
            aw_dir = export_dir / "src" / "ohosTest" / "ets" / "aw"
            case_dir.mkdir(parents=True)
            aw_dir.mkdir(parents=True)
            (case_dir / "ready_001_camera.test.ets").write_text("test", encoding="utf-8")
            (aw_dir / "CameraAW.ets").write_text("aw", encoding="utf-8")
            (export_dir / "src" / "ohosTest" / "module.json5").write_text("{}", encoding="utf-8")
            (export_dir / "src" / "ohosTest" / "oh-package.json5").write_text("{}", encoding="utf-8")

            def runner(args, timeout_s):
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.example.leaf"]:
                    return ProbeCommandResult(0, "bundle not exist -n com.example.leaf\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            result = inspect_e2e_readiness(
                root,
                "ready-001",
                serial="SERIAL123",
                bundle_name="com.example.leaf",
                package_dir=package_dir,
                hdc_runner=runner,
            )

            self.assertEqual(result["status"], "not_ready")
            self.assertEqual(result["quality_gate"], "E2E_NOT_READY")
            self.assertEqual(result["device"]["status"], "connected")
            self.assertEqual(result["packages"]["quality_gate"], "HAP_PACKAGE_EMPTY")
            self.assertEqual(result["target"]["quality_gate"], "TARGET_BUNDLE_MISSING")
            self.assertEqual(result["export"]["quality_gate"], "OPENHARMONY_EXPORT_ENTRY_MISSING")
            self.assertIn("HAP_PACKAGE_EMPTY", result["missing"])
            self.assertIn("TARGET_BUNDLE_MISSING", result["missing"])
            self.assertIn("OPENHARMONY_EXPORT_ENTRY_MISSING", result["missing"])
            self.assertTrue((root / ".leaf" / "runs" / "ready-001" / "e2e_readiness.json").exists())
            from tools.leaf_author.workflow import load_workflow

            workflow = load_workflow(root, "ready-001")
            self.assertEqual(workflow["current_phase"], "e2e_not_ready")
            self.assertEqual(workflow["artifacts"]["e2e_readiness"], ".leaf/runs/ready-001/e2e_readiness.json")

    def test_inspect_e2e_readiness_allows_installing_ready_haps_before_target_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from tools.leaf_author.authoring import confirm_plan, start_new_case
            from tools.leaf_author.workflow import load_workflow

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="ready-install")
            confirm_plan(root, "ready-install")
            package_dir = root / "packages"
            package_dir.mkdir()
            (package_dir / "entry-default.hap").write_text("app", encoding="utf-8")
            (package_dir / "entry-ohosTest.hap").write_text("test", encoding="utf-8")

            def runner(args, timeout_s):
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.example.leaf"]:
                    return ProbeCommandResult(0, "bundle not exist -n com.example.leaf\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            result = inspect_e2e_readiness(
                root,
                "ready-install",
                serial="SERIAL123",
                bundle_name="com.example.leaf",
                package_dir=package_dir,
                hdc_runner=runner,
                allow_install=True,
            )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["quality_gate"], "E2E_READY")
            self.assertEqual(result["target"]["quality_gate"], "TARGET_BUNDLE_INSTALL_REQUIRED")
            self.assertEqual(result["target"]["status"], "install_required")
            self.assertNotIn("TARGET_BUNDLE_MISSING", result["missing"])
            self.assertEqual(load_workflow(root, "ready-install")["current_phase"], "e2e_ready")

    def test_inspect_e2e_readiness_allows_test_only_hap_when_target_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            from tools.leaf_author.authoring import confirm_plan, start_new_case

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="ready-test-only")
            confirm_plan(root, "ready-test-only")
            package_dir = root / "packages"
            package_dir.mkdir()
            (package_dir / "entry-ohosTest.hap").write_text("test", encoding="utf-8")

            def runner(args, timeout_s):
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            result = inspect_e2e_readiness(
                root,
                "ready-test-only",
                serial="SERIAL123",
                bundle_name="com.huawei.hmos.camera",
                package_dir=package_dir,
                hdc_runner=runner,
            )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["quality_gate"], "E2E_READY")
            self.assertEqual(result["packages"]["quality_gate"], "HAP_TEST_PACKAGE_READY")
            self.assertEqual(result["target"]["quality_gate"], "TARGET_BUNDLE_AVAILABLE")
            self.assertEqual(result["missing"], [])

    def test_cli_inspect_e2e_readiness_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "packages"
            package_dir.mkdir()
            output = StringIO()

            from tools.leaf_author.__main__ import main

            with patch(
                "tools.leaf_author.__main__.inspect_e2e_readiness",
                return_value={"run_id": "ready-cli", "quality_gate": "E2E_NOT_READY"},
            ) as readiness, redirect_stdout(output):
                exit_code = main(
                    [
                        "inspect-e2e-readiness",
                        "ready-cli",
                        "--root",
                        str(root),
                        "--serial",
                        "SERIAL123",
                        "--bundle-name",
                        "com.example.leaf",
                        "--package-dir",
                        str(package_dir),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = __import__("json").loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "E2E_NOT_READY")
            readiness.assert_called_once()


if __name__ == "__main__":
    unittest.main()
