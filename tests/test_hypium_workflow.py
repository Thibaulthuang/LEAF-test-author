import json
import tempfile
import unittest
from pathlib import Path

from tools.leaf_author.authoring import advance_run, confirm_plan, start_new_case
from tools.leaf_author.device_probe import ProbeCommandResult
from tools.leaf_author.experience import export_team_knowledge, record_experience
from tools.leaf_author.workflow import load_workflow


class HypiumWorkflowTests(unittest.TestCase):
    def test_confirm_plan_generates_hypium_camera_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；切拍照模式；点击拍照；检查相册出现新照片", run_id="hypium-001")

            result = confirm_plan(root, "hypium-001")

            hypium_path = Path(result["hypium_path"])
            self.assertEqual(hypium_path, root / ".leaf" / "runs" / "hypium-001" / "hypium" / "hypium_001_camera.test.ets")
            content = hypium_path.read_text(encoding="utf-8")
            self.assertIn("import { describe, it, expect } from '@ohos/hypium';", content)
            self.assertIn("import { configureCameraAW } from '../aw/CameraAWConfig';", content)
            self.assertIn("describe('hypium-001_camera'", content)
            self.assertIn("configureCameraAW();", content)
            self.assertIn("await CameraAW.launch();", content)
            self.assertIn("await CameraAW.switchToPhotoMode();", content)
            self.assertIn("await CameraAW.capture();", content)
            self.assertIn("await GalleryAW.assertLatestPhotoCreatedAfter(testStartedAt);", content)
            self.assertNotIn("expect(true).assertTrue()", content)
            workflow = load_workflow(root, "hypium-001")
            self.assertEqual(workflow["current_phase"], "hypium_draft")
            self.assertEqual(workflow["artifacts"]["hypium"], ".leaf/runs/hypium-001/hypium/hypium_001_camera.test.ets")

    def test_hypium_camera_draft_uses_case_actions_for_semantic_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(
                root,
                "camera",
                "打开相机拍照",
                run_id="hypium-semantic",
                plan_input={
                    "target_feature": "camera.capture",
                    "steps": [
                        "打开系统相机",
                        "确认处于拍照模式",
                        "点击快门拍照",
                        "检查产生新照片",
                    ],
                    "risk": "真实执行时会在设备中新增一张照片",
                    "confirmation_required": True,
                },
            )

            result = confirm_plan(root, "hypium-semantic")

            content = Path(result["hypium_path"]).read_text(encoding="utf-8")
            self.assertIn("// Step 1: 打开系统相机", content)
            self.assertIn("await CameraAW.launch();", content)
            self.assertIn("await CameraAW.switchToPhotoMode();", content)
            self.assertIn("await CameraAW.capture();", content)
            self.assertIn("await GalleryAW.assertLatestPhotoCreatedAfter(testStartedAt);", content)
            self.assertNotIn('await CameraAW.performStep("打开系统相机");', content)

    def test_confirm_plan_exports_hypium_sources_for_openharmony_test_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-export")

            confirm_plan(root, "hypium-export")

            export_dir = root / ".leaf" / "runs" / "hypium-export" / "openharmony_test_project"
            case_path = export_dir / "src" / "ohosTest" / "ets" / "test" / "hypium_export_camera.test.ets"
            aw_path = export_dir / "src" / "ohosTest" / "ets" / "aw" / "CameraAW.ets"
            config_path = export_dir / "src" / "ohosTest" / "ets" / "aw" / "CameraAWConfig.ets"
            list_path = export_dir / "src" / "ohosTest" / "ets" / "test" / "List.test.ets"
            module_path = export_dir / "src" / "ohosTest" / "module.json5"
            package_path = export_dir / "src" / "ohosTest" / "oh-package.json5"
            readme_path = export_dir / "README.md"
            self.assertTrue(case_path.exists())
            self.assertTrue(aw_path.exists())
            self.assertTrue(config_path.exists())
            self.assertTrue(list_path.exists())
            self.assertTrue(module_path.exists())
            self.assertTrue(package_path.exists())
            self.assertTrue(readme_path.exists())
            self.assertIn("export class CameraAW", aw_path.read_text(encoding="utf-8"))
            self.assertIn("import { Driver, ON } from '@ohos.UiTest';", aw_path.read_text(encoding="utf-8"))
            self.assertIn("abilityDelegatorRegistry", aw_path.read_text(encoding="utf-8"))
            self.assertIn("CameraAW.configure", aw_path.read_text(encoding="utf-8"))
            self.assertIn("startAbility", aw_path.read_text(encoding="utf-8"))
            self.assertIn("tapByText", aw_path.read_text(encoding="utf-8"))
            self.assertIn("LEAF_CAMERA_AW_CONFIG_REQUIRED", aw_path.read_text(encoding="utf-8"))
            self.assertNotIn("CameraAW.launch requires project binding", aw_path.read_text(encoding="utf-8"))
            self.assertNotIn("expect(true).assertTrue()", aw_path.read_text(encoding="utf-8"))
            self.assertIn("export function configureCameraAW", config_path.read_text(encoding="utf-8"))
            self.assertIn("CameraAW.configure", config_path.read_text(encoding="utf-8"))
            self.assertIn("bundleName: 'com.huawei.hmos.camera'", config_path.read_text(encoding="utf-8"))
            self.assertIn("moduleName: 'phone'", config_path.read_text(encoding="utf-8"))
            self.assertIn("abilityName: 'com.huawei.hmos.camera.MainAbility'", config_path.read_text(encoding="utf-8"))
            self.assertIn("<capture-button-text>", config_path.read_text(encoding="utf-8"))
            self.assertIn("CameraAW.configure", readme_path.read_text(encoding="utf-8"))
            self.assertIn("OpenHarmonyTestRunner", readme_path.read_text(encoding="utf-8"))
            self.assertIn("built-in Camera app", readme_path.read_text(encoding="utf-8"))
            self.assertIn("test HAP only", readme_path.read_text(encoding="utf-8"))
            self.assertNotIn("installing app and test HAP", readme_path.read_text(encoding="utf-8"))
            self.assertIn("hypium_export_camera.test", list_path.read_text(encoding="utf-8"))
            self.assertIn("ohosTest", module_path.read_text(encoding="utf-8"))
            self.assertIn("@ohos/hypium", package_path.read_text(encoding="utf-8"))
            workflow = load_workflow(root, "hypium-export")
            self.assertEqual(workflow["artifacts"]["openharmony_test_project"], ".leaf/runs/hypium-export/openharmony_test_project")

    def test_sync_openharmony_export_copies_sources_into_target_test_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_module = root / "target" / "entry"
            target_module.mkdir(parents=True)
            (target_module / "module.json5").write_text('{"module":{"name":"entry"}}\n', encoding="utf-8")
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-sync")
            confirm_plan(root, "hypium-sync")

            from tools.leaf_author.hypium import sync_openharmony_export

            result = sync_openharmony_export(root, "hypium-sync", target_module)

            target_case = target_module / "src" / "ohosTest" / "ets" / "test" / "hypium_sync_camera.test.ets"
            target_list = target_module / "src" / "ohosTest" / "ets" / "test" / "List.test.ets"
            target_aw = target_module / "src" / "ohosTest" / "ets" / "aw" / "CameraAW.ets"
            target_config = target_module / "src" / "ohosTest" / "ets" / "aw" / "CameraAWConfig.ets"
            target_module_json = target_module / "src" / "ohosTest" / "module.json5"
            target_package_json = target_module / "src" / "ohosTest" / "oh-package.json5"
            self.assertEqual(result["status"], "synced")
            self.assertEqual(result["quality_gate"], "OPENHARMONY_EXPORT_SYNCED")
            self.assertTrue(target_case.exists())
            self.assertTrue(target_list.exists())
            self.assertTrue(target_aw.exists())
            self.assertTrue(target_config.exists())
            self.assertTrue(target_module_json.exists())
            self.assertTrue(target_package_json.exists())
            self.assertEqual((target_module / "module.json5").read_text(encoding="utf-8"), '{"module":{"name":"entry"}}\n')
            workflow = load_workflow(root, "hypium-sync")
            self.assertEqual(workflow["artifacts"]["openharmony_sync"], ".leaf/runs/hypium-sync/openharmony_sync.json")

    def test_cli_sync_openharmony_export_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_module = root / "target" / "entry"
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-sync-cli")
            confirm_plan(root, "hypium-sync-cli")
            from contextlib import redirect_stdout
            from io import StringIO
            from tools.leaf_author.__main__ import main

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["sync-openharmony-export", "hypium-sync-cli", "--root", str(root), "--target-module-dir", str(target_module)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "OPENHARMONY_EXPORT_SYNCED")
            self.assertTrue((target_module / "src" / "ohosTest" / "ets" / "test" / "hypium_sync_cli_camera.test.ets").exists())

    def test_advance_run_executes_real_hypium_with_explicit_serial_and_records_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-real")
            confirm_plan(root, "hypium-real")
            calls = []

            def runner(args, timeout_s):
                calls.append((args, timeout_s))
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "14\n", "")
                if args[:3] == ["hdc", "-t", "SERIAL123"] and args[3:5] == ["file", "send"]:
                    return ProbeCommandResult(0, "FileTransfer finish\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "mkdir", "-p", "/data/local/tmp/leaf/hypium/hypium-real"]:
                    return ProbeCommandResult(0, "", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.example.leaf"]:
                    return ProbeCommandResult(0, "bundleName: com.example.leaf\nmoduleName: entry\n", "")
                if args == [
                    "hdc",
                    "-t",
                    "SERIAL123",
                    "shell",
                    "aa",
                    "test",
                    "-b",
                    "com.example.leaf",
                    "-m",
                    "entry",
                    "-s",
                    "unittest",
                    "OpenHarmonyTestRunner",
                    "-s",
                    "class",
                    "hypium-real_camera",
                    "-w",
                    "120",
                ]:
                    return ProbeCommandResult(0, "OHOS_REPORT_STATUS: passed; total=1; failures=0\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera hypium passed\n", "")
                return ProbeCommandResult(1, "", f"unexpected: {args}")

            result = advance_run(
                root,
                "hypium-real",
                hdc_runner=runner,
                serial="SERIAL123",
                run_real=True,
                bundle_name="com.example.leaf",
                module_name="entry",
                test_runner="OpenHarmonyTestRunner",
            )

            self.assertEqual(result["status"], "complete")
            self.assertIn("hypium_result", result["stages"])
            self.assertFalse(any(call[0] == ["hdc", "list", "targets"] for call in calls))
            self.assertEqual(calls[0][0], ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"])
            result_path = root / ".leaf" / "runs" / "hypium-real" / "hypium_result.json"
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "PASSED_REAL")
            self.assertEqual(payload["quality_gate"], "HYPIUM_REAL_PASS")
            self.assertEqual(payload["device"]["serial"], "SERIAL123")
            self.assertEqual(load_workflow(root, "hypium-real")["artifacts"]["hypium_result"], ".leaf/runs/hypium-real/hypium_result.json")

    def test_real_hypium_result_becomes_experience_quality_gate_and_manifest_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-exp")
            confirm_plan(root, "hypium-exp")
            run_dir = root / ".leaf" / "runs" / "hypium-exp"
            result_path = run_dir / "hypium_result.json"
            result_path.write_text(
                json.dumps(
                    {
                        "run_id": "hypium-exp",
                        "status": "PASSED_REAL",
                        "quality_gate": "HYPIUM_REAL_PASS",
                        "passed": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            workflow = load_workflow(root, "hypium-exp")
            workflow["artifacts"]["hypium_result"] = ".leaf/runs/hypium-exp/hypium_result.json"
            from tools.leaf_author.workflow import save_workflow

            save_workflow(root, workflow)

            record_experience(root, "hypium-exp")
            export_team_knowledge(root, "hypium-exp")

            experience_path = root / ".leaf" / "knowledge" / "camera" / "openharmony" / "experience" / "hypium-exp.json"
            experience = json.loads(experience_path.read_text(encoding="utf-8"))
            self.assertEqual(experience["run_status"], "PASSED_REAL")
            self.assertEqual(experience["quality_gate"], "HYPIUM_REAL_PASS")
            self.assertGreater(experience["confidence"], 0.0)
            manifest = json.loads((run_dir / "team_export_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["hypium_result"], ".leaf/runs/hypium-exp/hypium_result.json")
            self.assertEqual(manifest["artifacts"]["hypium"], ".leaf/runs/hypium-exp/hypium/hypium_exp_camera.test.ets")

    def test_advance_run_can_rerun_failed_hypium_phase_when_real_execution_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-rerun")
            confirm_plan(root, "hypium-rerun")
            workflow = load_workflow(root, "hypium-rerun")
            workflow["current_phase"] = "hypium_ran"
            from tools.leaf_author.workflow import save_workflow

            save_workflow(root, workflow)
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args[:3] == ["hdc", "-t", "SERIAL123"] and args[3:5] == ["file", "send"]:
                    return ProbeCommandResult(0, "sent\n", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:7] == ["mkdir", "-p", "/data/local/tmp/leaf/hypium/hypium-rerun"]:
                    return ProbeCommandResult(0, "", "")
                if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]:
                    return ProbeCommandResult(0, "OHOS_REPORT_STATUS: passed; total=1; failures=0\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "ok\n", "")
                if "dumpLayout" in args:
                    return ProbeCommandResult(0, "layout\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            result = advance_run(root, "hypium-rerun", hdc_runner=runner, serial="SERIAL123", run_real=True)

            self.assertEqual(result["status"], "complete")
            self.assertIn("hypium_result", result["stages"])
            self.assertTrue(any(args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"] for args in calls))

    def test_real_hypium_execution_installs_provided_haps_before_aa_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_hap = root / "entry-default.hap"
            test_hap = root / "entry-ohosTest.hap"
            app_hap.write_text("app", encoding="utf-8")
            test_hap.write_text("test", encoding="utf-8")
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-install")
            confirm_plan(root, "hypium-install")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args[:3] == ["hdc", "-t", "SERIAL123"] and args[3:5] == ["file", "send"]:
                    return ProbeCommandResult(0, "sent\n", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] == ["bm", "install"]:
                    return ProbeCommandResult(0, "install success\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.example.leaf"]:
                    return ProbeCommandResult(0, "bundleName: com.example.leaf\nmoduleName: entry\n", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] == ["mkdir", "-p"]:
                    return ProbeCommandResult(0, "", "")
                if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]:
                    return ProbeCommandResult(0, "OHOS_REPORT_STATUS: passed; total=1; failures=0\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "ok\n", "")
                if "dumpLayout" in args:
                    return ProbeCommandResult(0, "layout\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            result = advance_run(
                root,
                "hypium-install",
                hdc_runner=runner,
                serial="SERIAL123",
                run_real=True,
                bundle_name="com.example.leaf",
                module_name="entry",
                app_hap=app_hap,
                test_hap=test_hap,
            )

            self.assertEqual(result["status"], "complete")
            app_remote = "/data/local/tmp/leaf/packages/entry-default.hap"
            test_remote = "/data/local/tmp/leaf/packages/entry-ohosTest.hap"
            self.assertIn(["hdc", "-t", "SERIAL123", "file", "send", str(app_hap), app_remote], calls)
            self.assertIn(["hdc", "-t", "SERIAL123", "file", "send", str(test_hap), test_remote], calls)
            self.assertLess(calls.index(["hdc", "-t", "SERIAL123", "shell", "bm", "install", "-p", app_remote]), calls.index([args for args in calls if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]][0]))
            payload = json.loads((root / ".leaf" / "runs" / "hypium-install" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["installed_packages"], ["entry-default.hap", "entry-ohosTest.hap"])

    def test_real_hypium_uses_test_bundle_for_aa_test_after_target_readiness_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_hap = root / "entry-ohosTest.hap"
            test_hap.write_text("test", encoding="utf-8")
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-test-bundle")
            confirm_plan(root, "hypium-test-bundle")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
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

            result = advance_run(
                root,
                "hypium-test-bundle",
                hdc_runner=runner,
                serial="SERIAL123",
                run_real=True,
                bundle_name="com.huawei.hmos.camera",
                module_name="phone",
                test_bundle_name="com.example.leaf.test",
                test_module_name="entry",
                test_hap=test_hap,
            )

            self.assertEqual(result["status"], "complete")
            self.assertIn(["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"], calls)
            aa_call = [args for args in calls if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]][0]
            self.assertIn("com.example.leaf.test", aa_call)
            self.assertIn("entry", aa_call)
            self.assertNotIn("com.huawei.hmos.camera", aa_call)
            payload = json.loads((root / ".leaf" / "runs" / "hypium-test-bundle" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["bundle_name"], "com.huawei.hmos.camera")
            self.assertEqual(payload["test_bundle_name"], "com.example.leaf.test")

    def test_real_hypium_stops_when_hdc_reports_transport_failure_with_zero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-transport")
            confirm_plan(root, "hypium-transport")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] == ["mkdir", "-p"]:
                    return ProbeCommandResult(0, "Connect server failed\n", "")
                return ProbeCommandResult(0, "should not run\n", "")

            result = advance_run(root, "hypium-transport", hdc_runner=runner, serial="SERIAL123", run_real=True)

            self.assertEqual(result["status"], "failed")
            self.assertFalse(any(args[:5] == ["hdc", "-t", "SERIAL123", "file", "send"] for args in calls))
            self.assertFalse(any(args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"] for args in calls))
            payload = json.loads((root / ".leaf" / "runs" / "hypium-transport" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["steps"][0]["exit_code"], 1)
            self.assertIn("Connect server failed", payload["steps"][0]["stdout"])

    def test_real_hypium_rejects_missing_hap_before_device_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-missing-hap")
            confirm_plan(root, "hypium-missing-hap")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                return ProbeCommandResult(0, "unexpected\n", "")

            result = advance_run(
                root,
                "hypium-missing-hap",
                hdc_runner=runner,
                serial="SERIAL123",
                run_real=True,
                app_hap=root / "missing.hap",
            )

            self.assertEqual(result["status"], "failed")
            self.assertFalse(any(args[:4] == ["hdc", "-t", "SERIAL123", "file"] for args in calls))
            payload = json.loads((root / ".leaf" / "runs" / "hypium-missing-hap" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["quality_gate"], "HYPIUM_PACKAGE_INVALID")
            self.assertIn("missing.hap", payload["reason"])

    def test_real_hypium_rejects_partial_explicit_hap_set_before_device_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_hap = root / "entry-default.hap"
            app_hap.write_text("app", encoding="utf-8")
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-partial-haps")
            confirm_plan(root, "hypium-partial-haps")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                return ProbeCommandResult(0, "unexpected\n", "")

            result = advance_run(root, "hypium-partial-haps", hdc_runner=runner, serial="SERIAL123", run_real=True, app_hap=app_hap)

            self.assertEqual(result["status"], "failed")
            self.assertFalse(any(args[:4] == ["hdc", "-t", "SERIAL123", "file"] for args in calls))
            payload = json.loads((root / ".leaf" / "runs" / "hypium-partial-haps" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["quality_gate"], "HYPIUM_PACKAGE_INVALID")
            self.assertIn("test_hap", payload["reason"])

    def test_real_hypium_stops_before_aa_test_when_target_bundle_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-target-missing")
            confirm_plan(root, "hypium-target-missing")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.example.leaf"]:
                    return ProbeCommandResult(0, "error: failed to get information and the parameters may be wrong.\n", "")
                return ProbeCommandResult(0, "unexpected\n", "")

            result = advance_run(
                root,
                "hypium-target-missing",
                hdc_runner=runner,
                serial="SERIAL123",
                run_real=True,
                bundle_name="com.example.leaf",
                module_name="entry",
            )

            self.assertEqual(result["status"], "failed")
            self.assertFalse(any(args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"] for args in calls))
            payload = json.loads((root / ".leaf" / "runs" / "hypium-target-missing" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["quality_gate"], "HYPIUM_TARGET_NOT_READY")
            self.assertEqual(payload["readiness"]["status"], "missing")
            self.assertIn("com.example.leaf", payload["reason"])

    def test_real_hypium_auto_discovers_haps_from_package_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "packages"
            package_dir.mkdir()
            (package_dir / "a-ohosTest.hap").write_text("test", encoding="utf-8")
            (package_dir / "z-default.hap").write_text("app", encoding="utf-8")
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-package-dir")
            confirm_plan(root, "hypium-package-dir")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args[:3] == ["hdc", "-t", "SERIAL123"] and args[3:5] == ["file", "send"]:
                    return ProbeCommandResult(0, "sent\n", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] == ["mkdir", "-p"]:
                    return ProbeCommandResult(0, "", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] == ["bm", "install"]:
                    return ProbeCommandResult(0, "install success\n", "")
                if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]:
                    return ProbeCommandResult(0, "OHOS_REPORT_STATUS: passed; total=1; failures=0\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "ok\n", "")
                if "dumpLayout" in args:
                    return ProbeCommandResult(0, "layout\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            result = advance_run(root, "hypium-package-dir", hdc_runner=runner, serial="SERIAL123", run_real=True, package_dir=package_dir)

            self.assertEqual(result["status"], "complete")
            payload = json.loads((root / ".leaf" / "runs" / "hypium-package-dir" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["installed_packages"], ["z-default.hap", "a-ohosTest.hap"])

    def test_real_hypium_auto_discovers_nested_haps_from_package_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "build"
            app_dir = package_dir / "outputs" / "default"
            test_dir = package_dir / "outputs" / "ohosTest"
            app_dir.mkdir(parents=True)
            test_dir.mkdir(parents=True)
            app_hap = app_dir / "entry-default.hap"
            test_hap = test_dir / "entry-ohosTest.hap"
            app_hap.write_text("app", encoding="utf-8")
            test_hap.write_text("test", encoding="utf-8")
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-nested-package-dir")
            confirm_plan(root, "hypium-nested-package-dir")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                if args[:3] == ["hdc", "-t", "SERIAL123"] and args[3:5] == ["file", "send"]:
                    return ProbeCommandResult(0, "sent\n", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] == ["mkdir", "-p"]:
                    return ProbeCommandResult(0, "", "")
                if args[:4] == ["hdc", "-t", "SERIAL123", "shell"] and args[4:6] == ["bm", "install"]:
                    return ProbeCommandResult(0, "install success\n", "")
                if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "test"]:
                    return ProbeCommandResult(0, "OHOS_REPORT_STATUS: passed; total=1; failures=0\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "ok\n", "")
                if "dumpLayout" in args:
                    return ProbeCommandResult(0, "layout\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            result = advance_run(root, "hypium-nested-package-dir", hdc_runner=runner, serial="SERIAL123", run_real=True, package_dir=package_dir)

            self.assertEqual(result["status"], "complete")
            payload = json.loads((root / ".leaf" / "runs" / "hypium-nested-package-dir" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["installed_packages"], ["entry-default.hap", "entry-ohosTest.hap"])
            self.assertIn(["hdc", "-t", "SERIAL123", "file", "send", str(app_hap), "/data/local/tmp/leaf/packages/entry-default.hap"], calls)
            self.assertIn(["hdc", "-t", "SERIAL123", "file", "send", str(test_hap), "/data/local/tmp/leaf/packages/entry-ohosTest.hap"], calls)

    def test_real_hypium_allows_test_only_hap_when_target_bundle_is_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "packages"
            package_dir.mkdir()
            test_hap = package_dir / "entry-ohosTest.hap"
            test_hap.write_text("test", encoding="utf-8")
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-test-only")
            confirm_plan(root, "hypium-test-only")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
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

            result = advance_run(
                root,
                "hypium-test-only",
                hdc_runner=runner,
                serial="SERIAL123",
                run_real=True,
                bundle_name="com.huawei.hmos.camera",
                module_name="phone",
                package_dir=package_dir,
            )

            self.assertEqual(result["status"], "complete")
            payload = json.loads((root / ".leaf" / "runs" / "hypium-test-only" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["installed_packages"], ["entry-ohosTest.hap"])
            self.assertIn(["hdc", "-t", "SERIAL123", "file", "send", str(test_hap), "/data/local/tmp/leaf/packages/entry-ohosTest.hap"], calls)

    def test_real_hypium_allows_explicit_test_hap_only_when_target_bundle_is_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_hap = root / "entry-ohosTest.hap"
            test_hap.write_text("test", encoding="utf-8")
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-explicit-test-only")
            confirm_plan(root, "hypium-explicit-test-only")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
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

            result = advance_run(
                root,
                "hypium-explicit-test-only",
                hdc_runner=runner,
                serial="SERIAL123",
                run_real=True,
                bundle_name="com.huawei.hmos.camera",
                module_name="phone",
                test_hap=test_hap,
            )

            self.assertEqual(result["status"], "complete")
            payload = json.loads((root / ".leaf" / "runs" / "hypium-explicit-test-only" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["installed_packages"], ["entry-ohosTest.hap"])
            self.assertIn(["hdc", "-t", "SERIAL123", "file", "send", str(test_hap), "/data/local/tmp/leaf/packages/entry-ohosTest.hap"], calls)

    def test_real_hypium_rejects_incomplete_package_dir_before_device_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "packages"
            package_dir.mkdir()
            (package_dir / "entry-default.hap").write_text("app", encoding="utf-8")
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-incomplete-packages")
            confirm_plan(root, "hypium-incomplete-packages")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                return ProbeCommandResult(0, "unexpected\n", "")

            result = advance_run(root, "hypium-incomplete-packages", hdc_runner=runner, serial="SERIAL123", run_real=True, package_dir=package_dir)

            self.assertEqual(result["status"], "failed")
            self.assertFalse(any(args[:4] == ["hdc", "-t", "SERIAL123", "file"] for args in calls))
            payload = json.loads((root / ".leaf" / "runs" / "hypium-incomplete-packages" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["quality_gate"], "HYPIUM_PACKAGE_INVALID")
            self.assertIn("test HAP is missing", payload["reason"])

    def test_real_hypium_rejects_symlinked_hap_from_package_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "packages"
            package_dir.mkdir()
            outside = root / "outside.hap"
            outside.write_text("outside", encoding="utf-8")
            (package_dir / "entry-ohosTest.hap").symlink_to(outside)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="hypium-symlink")
            confirm_plan(root, "hypium-symlink")

            def runner(args, timeout_s):
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                return ProbeCommandResult(0, "unexpected\n", "")

            result = advance_run(root, "hypium-symlink", hdc_runner=runner, serial="SERIAL123", run_real=True, package_dir=package_dir)

            self.assertEqual(result["status"], "failed")
            payload = json.loads((root / ".leaf" / "runs" / "hypium-symlink" / "hypium_result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["quality_gate"], "HYPIUM_PACKAGE_INVALID")
            self.assertIn("must not be a symlink", payload["reason"])


if __name__ == "__main__":
    unittest.main()
