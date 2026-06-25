import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tools.leaf_author.build import BuildCommandResult
from tools.leaf_author.device_probe import ProbeCommandResult
from tools.leaf_author.authoring import confirm_plan, start_new_case


class E2EOrchestrationTests(unittest.TestCase):
    def test_run_e2e_syncs_builds_allows_install_and_executes_real_hypium(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="e2e-pass")
            confirm_plan(root, "e2e-pass")
            target_module = root / "oh_project" / "entry"
            project_dir = root / "oh_project"
            project_dir.mkdir()
            (project_dir / "hvigorw").write_text("#!/bin/sh\n", encoding="utf-8")
            output_dir = project_dir / "build" / "outputs"
            output_dir.mkdir(parents=True)
            (output_dir / "entry-default.hap").write_text("app", encoding="utf-8")
            test_hap = output_dir / "entry-ohosTest.hap"
            with zipfile.ZipFile(test_hap, "w") as hap:
                hap.writestr(
                    "pack.info",
                    json.dumps(
                        {
                            "summary": {
                                "app": {"bundleName": "com.example.leaf.test"},
                                "modules": [{"name": "ohosTest"}],
                            },
                            "packages": [{"moduleName": "ohosTest"}],
                        }
                    ),
                )
            calls = []
            bm_dump_count = 0

            def build_runner(args, cwd, timeout_s):
                calls.append(("build", args, cwd, timeout_s))
                return BuildCommandResult(0, "build success\n", "")

            def hdc_runner(args, timeout_s):
                nonlocal bm_dump_count
                calls.append(("hdc", args, timeout_s))
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.example.leaf"]:
                    bm_dump_count += 1
                    if bm_dump_count == 1:
                        return ProbeCommandResult(0, "bundle not exist -n com.example.leaf\n", "")
                    return ProbeCommandResult(0, "bundleName: com.example.leaf\nmoduleName: entry\n", "")
                if args[:3] == ["hdc", "-t", "SERIAL123"] and args[3:5] == ["file", "send"]:
                    return ProbeCommandResult(0, "sent\n", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] == ["mkdir", "-p"]:
                    return ProbeCommandResult(0, "", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] == ["bm", "install"]:
                    return ProbeCommandResult(0, "install success\n", "")
                if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]:
                    return ProbeCommandResult(0, "OHOS_REPORT_STATUS: passed; total=1; failures=0\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "hypium passed\n", "")
                if "dumpLayout" in args:
                    return ProbeCommandResult(0, "layout\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.e2e import run_e2e

            result = run_e2e(
                root,
                "e2e-pass",
                serial="SERIAL123",
                bundle_name="com.example.leaf",
                module_name="entry",
                target_module_dir=target_module,
                project_dir=project_dir,
                package_dir=output_dir,
                build_command=["./hvigorw", "assembleOhosTest"],
                hdc_runner=hdc_runner,
                build_runner=build_runner,
            )

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["quality_gate"], "E2E_REAL_PASS")
            self.assertEqual(result["readiness"]["target"]["quality_gate"], "TARGET_BUNDLE_INSTALL_REQUIRED")
            self.assertIn("openharmony_sync", result["stages"])
            self.assertIn("openharmony_build", result["stages"])
            self.assertIn("hypium_result", result["stages"])
            self.assertEqual(calls[0], ("build", ["./hvigorw", "assembleOhosTest"], project_dir, 600))
            self.assertEqual(result["build"]["command"], ["./hvigorw", "assembleOhosTest"])
            aa_call = [
                call[1]
                for call in calls
                if call[0] == "hdc" and call[1][3:6] == ["shell", "aa", "test"]
            ][0]
            self.assertIn("com.example.leaf.test", aa_call)
            self.assertIn("ohosTest", aa_call)
            self.assertTrue((target_module / "src" / "ohosTest" / "ets" / "test" / "e2e_pass_camera.test.ets").exists())
            hypium_result = json.loads((root / ".leaf" / "runs" / "e2e-pass" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(hypium_result["status"], "PASSED_REAL")

    def test_run_e2e_discovers_project_paths_when_not_provided(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="e2e-discover")
            confirm_plan(root, "e2e-discover")
            project_dir = root / "DemoApp"
            module_dir = project_dir / "entry"
            output_dir = module_dir / "build" / "default" / "outputs"
            output_dir.mkdir(parents=True)
            (project_dir / "hvigorw").write_text("#!/bin/sh\n", encoding="utf-8")
            (project_dir / "build-profile.json5").write_text("{}", encoding="utf-8")
            (module_dir / "module.json5").write_text("{}", encoding="utf-8")
            (output_dir / "entry-default.hap").write_text("app", encoding="utf-8")
            (output_dir / "entry-ohosTest.hap").write_text("test", encoding="utf-8")
            bm_dump_count = 0

            def build_runner(args, cwd, timeout_s):
                return BuildCommandResult(0, "build success\n", "")

            def hdc_runner(args, timeout_s):
                nonlocal bm_dump_count
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.example.leaf"]:
                    bm_dump_count += 1
                    if bm_dump_count == 1:
                        return ProbeCommandResult(0, "bundle not exist -n com.example.leaf\n", "")
                    return ProbeCommandResult(0, "bundleName: com.example.leaf\nmoduleName: entry\n", "")
                if args[:3] == ["hdc", "-t", "SERIAL123"] and args[3:5] == ["file", "send"]:
                    return ProbeCommandResult(0, "sent\n", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] in (["mkdir", "-p"], ["bm", "install"]):
                    return ProbeCommandResult(0, "ok\n", "")
                if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]:
                    return ProbeCommandResult(0, "OHOS_REPORT_STATUS: passed; total=1; failures=0\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "ok\n", "")
                if "dumpLayout" in args:
                    return ProbeCommandResult(0, "layout\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.e2e import run_e2e

            result = run_e2e(
                root,
                "e2e-discover",
                serial="SERIAL123",
                bundle_name="com.example.leaf",
                module_name="entry",
                discover_root=root,
                hdc_runner=hdc_runner,
                build_runner=build_runner,
            )

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["discovery"]["project_dir"], str(project_dir))
            self.assertEqual(result["discovery"]["target_module_dir"], str(module_dir))
            self.assertEqual(result["discovery"]["package_dir"], str(output_dir))
            self.assertTrue((module_dir / "src" / "ohosTest" / "ets" / "test" / "e2e_discover_camera.test.ets").exists())

    def test_run_e2e_discovers_target_bundle_when_not_provided(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="e2e-target")
            confirm_plan(root, "e2e-target")
            target_module = root / "oh_project" / "entry"
            project_dir = root / "oh_project"
            project_dir.mkdir()
            (project_dir / "hvigorw").write_text("#!/bin/sh\n", encoding="utf-8")
            output_dir = project_dir / "build" / "outputs"
            output_dir.mkdir(parents=True)
            (output_dir / "entry-default.hap").write_text("app", encoding="utf-8")
            (output_dir / "entry-ohosTest.hap").write_text("test", encoding="utf-8")

            def build_runner(args, cwd, timeout_s):
                return BuildCommandResult(0, "build success\n", "")

            def hdc_runner(args, timeout_s):
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-a"]:
                    return ProbeCommandResult(0, "bundleName: com.example.camera\nmoduleName: entry\n", "")
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.example.camera"]:
                    return ProbeCommandResult(0, "bundleName: com.example.camera\nmoduleName: entry\n", "")
                if args[:3] == ["hdc", "-t", "SERIAL123"] and args[3:5] == ["file", "send"]:
                    return ProbeCommandResult(0, "sent\n", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] in (["mkdir", "-p"], ["bm", "install"]):
                    return ProbeCommandResult(0, "ok\n", "")
                if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]:
                    return ProbeCommandResult(0, "OHOS_REPORT_STATUS: passed; total=1; failures=0\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "ok\n", "")
                if "dumpLayout" in args:
                    return ProbeCommandResult(0, "layout\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.e2e import run_e2e

            result = run_e2e(
                root,
                "e2e-target",
                serial="SERIAL123",
                bundle_name=None,
                target_filter="camera",
                target_module_dir=target_module,
                project_dir=project_dir,
                package_dir=output_dir,
                hdc_runner=hdc_runner,
                build_runner=build_runner,
            )

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["target_discovery"]["candidates"][0]["bundle_name"], "com.example.camera")
            self.assertEqual(result["readiness"]["target"]["bundle_name"], "com.example.camera")
            self.assertEqual(result["real_result"]["status"], "complete")

    def test_run_e2e_accepts_explicit_test_hap_without_package_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="e2e-test-hap")
            confirm_plan(root, "e2e-test-hap")
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
            calls = []

            def hdc_runner(args, timeout_s):
                calls.append(args)
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-a"]:
                    return ProbeCommandResult(0, "ID: 100:\n\tcom.huawei.hmos.camera\n", "")
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args[:3] == ["hdc", "-t", "SERIAL123"] and args[3:5] == ["file", "send"]:
                    return ProbeCommandResult(0, "sent\n", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] in (["mkdir", "-p"], ["bm", "install"]):
                    return ProbeCommandResult(0, "ok\n", "")
                if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]:
                    return ProbeCommandResult(0, "OHOS_REPORT_STATUS: passed; total=1; failures=0\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "ok\n", "")
                if "dumpLayout" in args:
                    return ProbeCommandResult(0, "layout\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.e2e import run_e2e

            result = run_e2e(
                root,
                "e2e-test-hap",
                serial="SERIAL123",
                bundle_name=None,
                target_filter="camera",
                test_hap=test_hap,
                hdc_runner=hdc_runner,
            )

            self.assertEqual(result["status"], "complete")
            self.assertIn(["hdc", "-t", "SERIAL123", "file", "send", str(test_hap), "/data/local/tmp/leaf/packages/entry-ohosTest.hap"], calls)
            aa_call = [args for args in calls if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]][0]
            self.assertIn("com.example.explicit.test", aa_call)
            self.assertIn("explicit_test", aa_call)
            payload = json.loads((root / ".leaf" / "runs" / "e2e-test-hap" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["installed_packages"], ["entry-ohosTest.hap"])
            self.assertEqual(payload["test_bundle_name"], "com.example.explicit.test")
            self.assertEqual(payload["test_module_name"], "explicit_test")

    def test_run_e2e_auto_discovers_test_hap_from_discover_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="e2e-auto-hap")
            confirm_plan(root, "e2e-auto-hap")
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
            calls = []

            def hdc_runner(args, timeout_s):
                calls.append(args)
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-a"]:
                    return ProbeCommandResult(0, "ID: 100:\n\tcom.huawei.hmos.camera\n", "")
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args[:3] == ["hdc", "-t", "SERIAL123"] and args[3:5] == ["file", "send"]:
                    return ProbeCommandResult(0, "sent\n", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] in (["mkdir", "-p"], ["bm", "install"]):
                    return ProbeCommandResult(0, "ok\n", "")
                if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]:
                    return ProbeCommandResult(0, "OHOS_REPORT_STATUS: passed; total=1; failures=0\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "ok\n", "")
                if "dumpLayout" in args:
                    return ProbeCommandResult(0, "layout\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.e2e import run_e2e

            result = run_e2e(
                root,
                "e2e-auto-hap",
                serial="SERIAL123",
                bundle_name=None,
                target_filter="camera",
                discover_root=root,
                hdc_runner=hdc_runner,
            )

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["hap_discovery"]["test_hap"], str(test_hap))
            self.assertEqual(result["hap_discovery"]["test_bundle_name"], "com.example.leaf.test")
            self.assertIn(["hdc", "-t", "SERIAL123", "file", "send", str(test_hap), "/data/local/tmp/leaf/packages/entry-ohosTest.hap"], calls)
            aa_call = [args for args in calls if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]][0]
            self.assertIn("com.example.leaf.test", aa_call)
            self.assertIn("entry_test", aa_call)

    def test_run_e2e_records_not_ready_attempt_as_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="e2e-no-hap")
            confirm_plan(root, "e2e-no-hap")

            def hdc_runner(args, timeout_s):
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-a"]:
                    return ProbeCommandResult(0, "ID: 100:\n\tcom.huawei.hmos.camera\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.e2e import run_e2e

            result = run_e2e(
                root,
                "e2e-no-hap",
                serial="SERIAL123",
                bundle_name=None,
                target_filter="camera",
                discover_root=root,
                hdc_runner=hdc_runner,
            )

            self.assertEqual(result["status"], "not_ready")
            e2e_run_path = root / ".leaf" / "runs" / "e2e-no-hap" / "e2e_run.json"
            self.assertTrue(e2e_run_path.exists())
            payload = json.loads(e2e_run_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["quality_gate"], "HAP_ARTIFACTS_MISSING")
            workflow = json.loads((root / ".leaf" / "runs" / "e2e-no-hap" / "workflow.json").read_text(encoding="utf-8"))
            self.assertEqual(workflow["artifacts"]["e2e_run"], ".leaf/runs/e2e-no-hap/e2e_run.json")
            self.assertEqual(workflow["current_phase"], "e2e_not_ready")

    def test_cli_run_e2e_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "oh_project"
            package_dir = project_dir / "build" / "outputs"
            target_module = project_dir / "entry"
            test_hap = root / "entry-ohosTest.hap"
            output = StringIO()

            from tools.leaf_author.__main__ import main

            with patch("tools.leaf_author.__main__.run_e2e", return_value={"run_id": "e2e-cli", "quality_gate": "E2E_READY"}) as run_e2e, redirect_stdout(output):
                exit_code = main(
                    [
                        "run-e2e",
                        "e2e-cli",
                        "--root",
                        str(root),
                        "--serial",
                        "SERIAL123",
                        "--bundle-name",
                        "com.example.leaf",
                        "--module-name",
                        "entry",
                        "--test-bundle-name",
                        "com.example.leaf.test",
                        "--test-module-name",
                        "ohosTest",
                        "--target-filter",
                        "camera",
                        "--target-module-dir",
                        str(target_module),
                        "--project-dir",
                        str(project_dir),
                        "--package-dir",
                        str(package_dir),
                        "--test-hap",
                        str(test_hap),
                        "--discover-root",
                        str(root),
                        "--build-command",
                        "./hvigorw",
                        "assembleOhosTest",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "E2E_READY")
            run_e2e.assert_called_once()
            self.assertEqual(run_e2e.call_args.kwargs["discover_root"], root)
            self.assertEqual(run_e2e.call_args.kwargs["target_filter"], "camera")
            self.assertEqual(run_e2e.call_args.kwargs["test_hap"], test_hap)
            self.assertEqual(run_e2e.call_args.kwargs["build_command"], ["./hvigorw", "assembleOhosTest"])
            self.assertEqual(run_e2e.call_args.kwargs["test_bundle_name"], "com.example.leaf.test")
            self.assertEqual(run_e2e.call_args.kwargs["test_module_name"], "ohosTest")


if __name__ == "__main__":
    unittest.main()
