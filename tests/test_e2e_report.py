import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tools.leaf_author.authoring import confirm_plan, start_new_case


class E2EReportTests(unittest.TestCase):
    def test_write_e2e_preflight_report_records_gap_and_next_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-001")
            confirm_plan(root, "report-001")
            test_hap = root / "entry-ohosTest.hap"

            from tools.leaf_author.e2e_report import write_e2e_preflight_report

            with patch(
                "tools.leaf_author.e2e_report.discover_test_targets",
                return_value={
                    "status": "found",
                    "quality_gate": "TARGET_CANDIDATES_FOUND",
                    "candidates": [{"bundle_name": "com.huawei.hmos.camera", "module_name": "phone"}],
                },
            ), patch(
                "tools.leaf_author.e2e_report.discover_openharmony_project",
                return_value={"status": "missing", "quality_gate": "OPENHARMONY_PROJECT_MISSING"},
            ), patch(
                "tools.leaf_author.e2e_report.inspect_e2e_readiness",
                return_value={
                    "status": "not_ready",
                    "quality_gate": "E2E_NOT_READY",
                    "missing": ["HAP_PACKAGE_EMPTY"],
                },
            ):
                result = write_e2e_preflight_report(
                    root,
                    "report-001",
                    serial="SERIAL123",
                    target_filter="camera",
                    package_dir=root / "packages",
                    test_hap=test_hap,
                    discover_root=root,
                    build_command=["./hvigorw", "assembleOhosTest"],
                    test_bundle_name="com.example.leaf.test",
                    test_module_name="ohosTest",
                )

            self.assertEqual(result["quality_gate"], "E2E_PREFLIGHT_NOT_READY")
            self.assertEqual(result["selected_target"]["bundle_name"], "com.huawei.hmos.camera")
            self.assertIn("HAP_PACKAGE_EMPTY", result["missing"])
            self.assertIn("--target-filter camera", result["next_command"])
            self.assertIn("--package-dir", result["next_command"])
            self.assertIn("--test-hap", result["next_command"])
            self.assertIn(str(test_hap), result["next_command"])
            self.assertIn("--build-command ./hvigorw assembleOhosTest", result["next_command"])
            self.assertIn("--test-bundle-name com.example.leaf.test", result["next_command"])
            self.assertIn("--test-module-name ohosTest", result["next_command"])
            report_path = root / ".leaf" / "runs" / "report-001" / "e2e_preflight_report.json"
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["next_action"], "provide_test_hap_or_openharmony_project")

    def test_write_e2e_preflight_report_marks_explicit_test_hap_ready_when_target_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-test-hap")
            confirm_plan(root, "report-test-hap")
            test_hap = root / "entry-ohosTest.hap"
            with zipfile.ZipFile(test_hap, "w") as hap:
                hap.writestr(
                    "module.json",
                    json.dumps(
                        {
                            "app": {"bundleName": "com.example.explicit.test"},
                            "module": {"name": "explicit_test"},
                        }
                    ),
                )

            from tools.leaf_author.e2e_report import write_e2e_preflight_report

            with patch(
                "tools.leaf_author.e2e_report.discover_test_targets",
                return_value={
                    "status": "found",
                    "quality_gate": "TARGET_CANDIDATES_FOUND",
                    "candidates": [{"bundle_name": "com.huawei.hmos.camera", "module_name": "phone"}],
                },
            ), patch(
                "tools.leaf_author.e2e_report.discover_openharmony_project",
                return_value={"status": "missing", "quality_gate": "OPENHARMONY_PROJECT_MISSING"},
            ), patch(
                "tools.leaf_author.e2e_report.inspect_e2e_readiness",
                return_value={
                    "status": "not_ready",
                    "quality_gate": "E2E_NOT_READY",
                    "target": {"quality_gate": "TARGET_BUNDLE_AVAILABLE"},
                    "export": {"quality_gate": "OPENHARMONY_EXPORT_READY"},
                    "missing": ["HAP_PACKAGE_DIR_UNSPECIFIED"],
                },
            ) as readiness:
                result = write_e2e_preflight_report(
                    root,
                    "report-test-hap",
                    serial="SERIAL123",
                    target_filter="camera",
                    test_hap=test_hap,
                )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["quality_gate"], "E2E_PREFLIGHT_READY")
            self.assertEqual(result["missing"], [])
            self.assertEqual(result["next_action"], "run_e2e")
            self.assertEqual(result["test_bundle_name"], "com.example.explicit.test")
            self.assertEqual(result["test_module_name"], "explicit_test")
            self.assertIn("--test-hap", result["next_command"])
            self.assertIn("--test-bundle-name com.example.explicit.test", result["next_command"])
            self.assertIn("--test-module-name explicit_test", result["next_command"])
            self.assertEqual(readiness.call_args.kwargs["package_dir"], None)

    def test_write_e2e_preflight_report_auto_discovers_test_hap_from_search_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-auto-hap")
            confirm_plan(root, "report-auto-hap")
            output_dir = root / "artifacts"
            output_dir.mkdir()
            test_hap = output_dir / "entry-ohosTest.hap"
            with zipfile.ZipFile(test_hap, "w") as hap:
                hap.writestr(
                    "module.json",
                    json.dumps(
                        {
                            "app": {"bundleName": "com.example.leaf.test"},
                            "module": {"name": "entry_test"},
                        }
                    ),
                )

            from tools.leaf_author.e2e_report import write_e2e_preflight_report

            with patch(
                "tools.leaf_author.e2e_report.discover_test_targets",
                return_value={
                    "status": "found",
                    "quality_gate": "TARGET_CANDIDATES_FOUND",
                    "candidates": [{"bundle_name": "com.huawei.hmos.camera", "module_name": "phone"}],
                },
            ), patch(
                "tools.leaf_author.e2e_report.discover_openharmony_project",
                return_value={"status": "missing", "quality_gate": "OPENHARMONY_PROJECT_MISSING"},
            ), patch(
                "tools.leaf_author.e2e_report.inspect_e2e_readiness",
                return_value={
                    "status": "not_ready",
                    "quality_gate": "E2E_NOT_READY",
                    "target": {"quality_gate": "TARGET_BUNDLE_AVAILABLE"},
                    "export": {"quality_gate": "OPENHARMONY_EXPORT_READY"},
                    "missing": ["HAP_PACKAGE_DIR_UNSPECIFIED"],
                },
            ):
                result = write_e2e_preflight_report(
                    root,
                    "report-auto-hap",
                    serial="SERIAL123",
                    target_filter="camera",
                    discover_root=root,
                )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["test_hap"], str(test_hap))
            self.assertEqual(result["test_bundle_name"], "com.example.leaf.test")
            self.assertEqual(result["test_module_name"], "entry_test")
            self.assertEqual(result["package_dir"], str(output_dir))
            self.assertIn(str(test_hap), result["next_command"])
            self.assertIn("--test-bundle-name com.example.leaf.test", result["next_command"])
            self.assertIn("--test-module-name entry_test", result["next_command"])

    def test_write_e2e_preflight_report_reports_missing_hap_artifact_when_none_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-no-hap")
            confirm_plan(root, "report-no-hap")

            from tools.leaf_author.e2e_report import write_e2e_preflight_report

            with patch(
                "tools.leaf_author.e2e_report.discover_test_targets",
                return_value={
                    "status": "found",
                    "quality_gate": "TARGET_CANDIDATES_FOUND",
                    "candidates": [{"bundle_name": "com.huawei.hmos.camera", "module_name": "phone"}],
                },
            ), patch(
                "tools.leaf_author.e2e_report.discover_openharmony_project",
                return_value={"status": "missing", "quality_gate": "OPENHARMONY_PROJECT_MISSING"},
            ), patch(
                "tools.leaf_author.e2e_report.inspect_e2e_readiness",
                return_value={
                    "status": "not_ready",
                    "quality_gate": "E2E_NOT_READY",
                    "target": {"quality_gate": "TARGET_BUNDLE_AVAILABLE"},
                    "export": {"quality_gate": "OPENHARMONY_EXPORT_READY"},
                    "missing": ["HAP_PACKAGE_DIR_UNSPECIFIED"],
                },
            ):
                result = write_e2e_preflight_report(
                    root,
                    "report-no-hap",
                    serial="SERIAL123",
                    target_filter="camera",
                    discover_root=root,
                )

            self.assertEqual(result["status"], "not_ready")
            self.assertIn("HAP_ARTIFACTS_MISSING", result["missing"])
            self.assertNotIn("HAP_PACKAGE_DIR_UNSPECIFIED", result["missing"])

    def test_cli_e2e_preflight_report_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = StringIO()

            from tools.leaf_author.__main__ import main

            with patch(
                "tools.leaf_author.__main__.write_e2e_preflight_report",
                return_value={"run_id": "report-cli", "quality_gate": "E2E_PREFLIGHT_NOT_READY"},
            ) as report, redirect_stdout(output):
                exit_code = main(
                    [
                        "e2e-preflight-report",
                        "report-cli",
                        "--root",
                        str(root),
                        "--serial",
                        "SERIAL123",
                        "--target-filter",
                        "camera",
                        "--package-dir",
                        str(root / "packages"),
                        "--test-hap",
                        str(root / "entry-ohosTest.hap"),
                        "--discover-root",
                        str(root),
                        "--build-command",
                        "./hvigorw",
                        "assembleOhosTest",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "E2E_PREFLIGHT_NOT_READY")
            self.assertEqual(report.call_args.kwargs["target_filter"], "camera")
            self.assertEqual(report.call_args.kwargs["test_hap"], root / "entry-ohosTest.hap")
            self.assertEqual(report.call_args.kwargs["build_command"], ["./hvigorw", "assembleOhosTest"])


if __name__ == "__main__":
    unittest.main()
