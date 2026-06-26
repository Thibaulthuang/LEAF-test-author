import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tools.leaf_author.device_probe import ProbeCommandResult
from tools.leaf_author.workflow import create_workflow, load_workflow


class CameraSmokeTests(unittest.TestCase):
    def test_camera_smoke_preflight_wraps_builtin_camera_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.camera_smoke import write_camera_smoke_preflight

            with patch(
                "tools.leaf_author.camera_smoke.write_e2e_preflight_report",
                return_value={
                    "run_id": "camera-smoke",
                    "status": "not_ready",
                    "quality_gate": "E2E_PREFLIGHT_NOT_READY",
                    "selected_target": {"bundle_name": "com.huawei.hmos.camera", "module_name": "phone"},
                    "test_hap": None,
                    "test_bundle_name": None,
                    "test_module_name": None,
                    "missing": ["HAP_ARTIFACTS_MISSING"],
                    "next_command": ".venv/bin/python -m tools.leaf_author run-e2e camera-smoke --serial SERIAL123 --target-filter camera",
                },
            ) as report:
                result = write_camera_smoke_preflight(root, "camera-smoke", serial="SERIAL123", discover_root=root)

            self.assertEqual(result["domain"], "camera")
            self.assertEqual(result["target_app"]["kind"], "builtin")
            self.assertEqual(result["target_app"]["requires_app_hap"], False)
            self.assertEqual(result["target_app"]["bundle_name"], "com.huawei.hmos.camera")
            self.assertEqual(result["runner"]["kind"], "python_hdc_uitest")
            self.assertEqual(result["runner"]["requires_test_hap"], False)
            self.assertEqual(result["missing"], [])
            self.assertEqual(result["readiness_summary"]["device"], "unknown")
            self.assertEqual(result["readiness_summary"]["target_app"], "ready")
            self.assertEqual(result["readiness_summary"]["executor"], "ready")
            self.assertEqual(result["blocking_reason"], None)
            self.assertEqual(result["quality_gate"], "CAMERA_SMOKE_READY")
            self.assertIn("system Camera", result["quality_gate_description"])
            self.assertIn("camera-direct", result["recommended_actions"][0])
            self.assertIn("camera-direct", result["next_command"])
            report.assert_called_once()
            self.assertEqual(report.call_args.kwargs["target_filter"], "camera")
            self.assertEqual(report.call_args.kwargs["app_hap"], None)

    def test_camera_smoke_preflight_explains_missing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.camera_smoke import write_camera_smoke_preflight

            with patch(
                "tools.leaf_author.camera_smoke.write_e2e_preflight_report",
                return_value={
                    "run_id": "camera-smoke",
                    "status": "not_ready",
                    "quality_gate": "E2E_PREFLIGHT_NOT_READY",
                    "serial": "SERIAL123",
                    "selected_target": None,
                    "target_discovery": {"quality_gate": "TARGET_CANDIDATES_EMPTY", "candidates": []},
                    "test_hap": "/tmp/entry-ohosTest.hap",
                    "missing": ["TARGET_CANDIDATES_EMPTY"],
                    "next_command": "",
                },
            ):
                result = write_camera_smoke_preflight(root, "camera-smoke", serial="SERIAL123")

            self.assertEqual(result["quality_gate"], "CAMERA_SMOKE_TARGET_MISSING")
            self.assertEqual(result["readiness_summary"]["target_app"], "missing")
            self.assertEqual(result["blocking_reason"], "TARGET_CANDIDATES_EMPTY")
            self.assertEqual(result["quality_gate_description"], "No Camera bundle candidate was found on the connected device.")
            self.assertIn("Verify the device has the built-in Camera app", result["recommended_actions"][0])

    def test_camera_smoke_preflight_explains_device_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.camera_smoke import write_camera_smoke_preflight

            with patch(
                "tools.leaf_author.camera_smoke.write_e2e_preflight_report",
                return_value={
                    "run_id": "camera-smoke",
                    "status": "not_ready",
                    "quality_gate": "E2E_PREFLIGHT_NOT_READY",
                    "serial": "SERIAL123",
                    "selected_target": None,
                    "target_discovery": {"quality_gate": "HDC_DEVICE_UNAVAILABLE", "candidates": []},
                    "missing": ["HDC_DEVICE_UNAVAILABLE"],
                    "next_command": "",
                },
            ):
                result = write_camera_smoke_preflight(root, "camera-smoke", serial="SERIAL123")

            self.assertEqual(result["quality_gate"], "CAMERA_SMOKE_DEVICE_UNAVAILABLE")
            self.assertEqual(result["readiness_summary"]["device"], "missing")
            self.assertEqual(result["blocking_reason"], "HDC_DEVICE_UNAVAILABLE")
            self.assertIn("Connect an OpenHarmony device", result["recommended_actions"][0])

    def test_camera_smoke_preflight_ignores_project_missing_for_builtin_direct_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.camera_smoke import write_camera_smoke_preflight

            with patch(
                "tools.leaf_author.camera_smoke.write_e2e_preflight_report",
                return_value={
                    "run_id": "camera-smoke",
                    "status": "not_ready",
                    "quality_gate": "E2E_PREFLIGHT_NOT_READY",
                    "serial": "SERIAL123",
                    "selected_target": {"bundle_name": "com.huawei.hmos.camera", "module_name": "phone"},
                    "missing": ["OPENHARMONY_PROJECT_MISSING"],
                    "test_hap": None,
                    "package_dir": None,
                    "next_command": "",
                },
            ):
                result = write_camera_smoke_preflight(root, "camera-smoke", serial="SERIAL123")

            self.assertEqual(result["quality_gate"], "CAMERA_SMOKE_READY")
            self.assertEqual(result["blocking_reason"], None)
            self.assertEqual(result["missing"], [])
            self.assertIn("camera-direct", result["recommended_actions"][0])

    def test_run_camera_smoke_wraps_e2e_without_app_hap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_hap = root / "entry-ohosTest.hap"

            from tools.leaf_author.camera_smoke import run_camera_smoke

            with patch(
                "tools.leaf_author.camera_smoke.run_e2e",
                return_value={
                    "run_id": "camera-smoke",
                    "status": "complete",
                    "quality_gate": "E2E_REAL_PASS",
                    "selected_target": {"bundle_name": "com.huawei.hmos.camera", "module_name": "phone"},
                },
            ) as run_e2e:
                result = run_camera_smoke(root, "camera-smoke", serial="SERIAL123", test_hap=test_hap)

            self.assertEqual(result["domain"], "camera")
            self.assertEqual(result["target_app"]["kind"], "builtin")
            self.assertEqual(result["target_app"]["requires_app_hap"], False)
            run_e2e.assert_called_once()
            self.assertEqual(run_e2e.call_args.kwargs["target_filter"], "camera")
            self.assertEqual(run_e2e.call_args.kwargs["bundle_name"], None)
            self.assertEqual(run_e2e.call_args.kwargs["app_hap"], None)
            self.assertEqual(run_e2e.call_args.kwargs["test_hap"], test_hap)

    def test_cli_camera_smoke_preflight_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = StringIO()

            from tools.leaf_author.__main__ import main

            with patch(
                "tools.leaf_author.__main__.write_camera_smoke_preflight",
                return_value={"run_id": "camera-smoke", "domain": "camera", "quality_gate": "CAMERA_SMOKE_NOT_READY"},
            ) as preflight, redirect_stdout(output):
                exit_code = main(
                    [
                        "camera-smoke-preflight",
                        "camera-smoke",
                        "--root",
                        str(root),
                        "--serial",
                        "SERIAL123",
                        "--discover-root",
                        str(root),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["domain"], "camera")
            preflight.assert_called_once()
            self.assertEqual(preflight.call_args.kwargs["serial"], "SERIAL123")

    def test_cli_run_camera_smoke_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_hap = root / "entry-ohosTest.hap"
            output = StringIO()

            from tools.leaf_author.__main__ import main

            with patch(
                "tools.leaf_author.__main__.run_camera_smoke",
                return_value={"run_id": "camera-smoke", "domain": "camera", "quality_gate": "E2E_REAL_PASS"},
            ) as run_smoke, redirect_stdout(output):
                exit_code = main(
                    [
                        "run-camera-smoke",
                        "camera-smoke",
                        "--root",
                        str(root),
                        "--serial",
                        "SERIAL123",
                        "--test-hap",
                        str(test_hap),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "E2E_REAL_PASS")
            run_smoke.assert_called_once()
            self.assertEqual(run_smoke.call_args.kwargs["test_hap"], test_hap)

    def test_run_camera_direct_smoke_launches_builtin_camera_and_collects_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机", run_id="camera-direct")
            calls = []
            media_queries = 0

            def runner(args, timeout_s):
                nonlocal media_queries
                calls.append(args)
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == [
                    "hdc",
                    "-t",
                    "SERIAL123",
                    "shell",
                    "aa",
                    "start",
                    "-a",
                    "com.huawei.hmos.camera.MainAbility",
                    "-b",
                    "com.huawei.hmos.camera",
                    "-m",
                    "phone",
                ]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(
                        0,
                        '{"attributes":{"bundleName":"com.huawei.hmos.camera","abilityName":"com.huawei.hmos.camera.MainAbility","text":"Camera"},"children":[]}\n',
                        "",
                    )
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.camera_smoke import run_camera_direct_smoke

            result = run_camera_direct_smoke(root, "camera-direct", serial="SERIAL123", hdc_runner=runner)

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")
            self.assertEqual(result["target_app"]["bundle_name"], "com.huawei.hmos.camera")
            self.assertEqual(result["launch"]["exit_code"], 0)
            self.assertEqual(result["evidence"]["layout_verified"], True)
            self.assertEqual(result["evidence"]["bundle_verified"], True)
            self.assertEqual(result["evidence"]["ability_verified"], True)
            self.assertEqual(result["evidence"]["ui_snapshots"]["after_launch"]["kind"], "ui_snapshot")
            self.assertTrue((root / result["evidence"]["ui_snapshots"]["after_launch"]["index_path"]).is_file())
            self.assertIn("Camera", result["evidence"]["ui_tree_excerpt"])
            self.assertIn("camera foreground", result["evidence"]["hilog_excerpt"])
            self.assertIn(
                [
                    "hdc",
                    "-t",
                    "SERIAL123",
                    "shell",
                    "aa",
                    "start",
                    "-a",
                    "com.huawei.hmos.camera.MainAbility",
                    "-b",
                    "com.huawei.hmos.camera",
                    "-m",
                    "phone",
                ],
                calls,
            )
            workflow = load_workflow(root, "camera-direct")
            self.assertEqual(workflow["current_phase"], "camera_direct_smoke_complete")
            self.assertEqual(workflow["artifacts"]["camera_direct_smoke"], ".leaf/runs/camera-direct/camera_direct_smoke.json")

    def test_run_camera_direct_smoke_reads_dump_layout_file_when_uitest_returns_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机", run_id="camera-direct-layout-file")
            layout_path = "/data/local/tmp/layout_123.json"

            def runner(args, timeout_s):
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == [
                    "hdc",
                    "-t",
                    "SERIAL123",
                    "shell",
                    "aa",
                    "start",
                    "-a",
                    "com.huawei.hmos.camera.MainAbility",
                    "-b",
                    "com.huawei.hmos.camera",
                    "-m",
                    "phone",
                ]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    return ProbeCommandResult(
                        0,
                        '{"attributes":{"bundleName":"com.huawei.hmos.camera","abilityName":"com.huawei.hmos.camera.MainAbility","text":"相机"},"children":[]}\n',
                        "",
                    )
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.camera_smoke import run_camera_direct_smoke

            result = run_camera_direct_smoke(root, "camera-direct-layout-file", serial="SERIAL123", hdc_runner=runner)

            self.assertEqual(result["quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")
            self.assertEqual(result["evidence"]["layout_path"], layout_path)
            self.assertTrue((root / result["evidence"]["ui_snapshots"]["after_launch"]["raw_path"]).is_file())
            self.assertIn("相机", result["evidence"]["ui_tree_excerpt"])

    def test_run_camera_direct_smoke_requires_camera_layout_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机", run_id="camera-direct-wrong-layout")
            layout_path = "/data/local/tmp/layout_123.json"

            def runner(args, timeout_s):
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == [
                    "hdc",
                    "-t",
                    "SERIAL123",
                    "shell",
                    "aa",
                    "start",
                    "-a",
                    "com.huawei.hmos.camera.MainAbility",
                    "-b",
                    "com.huawei.hmos.camera",
                    "-m",
                    "phone",
                ]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    return ProbeCommandResult(0, '{"attributes":{"bundleName":"com.ohos.sceneboard"},"children":[]}\n', "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.camera_smoke import run_camera_direct_smoke

            result = run_camera_direct_smoke(root, "camera-direct-wrong-layout", serial="SERIAL123", hdc_runner=runner)

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["quality_gate"], "CAMERA_DIRECT_SMOKE_FAILED")
            self.assertEqual(result["evidence"]["layout_verified"], False)

    def test_run_camera_direct_smoke_treats_aa_error_output_as_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机", run_id="camera-direct-failed")

            def runner(args, timeout_s):
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == [
                    "hdc",
                    "-t",
                    "SERIAL123",
                    "shell",
                    "aa",
                    "start",
                    "-a",
                    "com.huawei.hmos.camera.MainAbility",
                    "-b",
                    "com.huawei.hmos.camera",
                    "-m",
                    "phone",
                ]:
                    return ProbeCommandResult(
                        0,
                        "error: failed to start ability.\nError Code:10103101  Error Message:Failed to find a matching application for implicit launch.\n",
                        "",
                    )
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, "DumpLayout saved to:/data/local/tmp/layout.json\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.camera_smoke import run_camera_direct_smoke

            result = run_camera_direct_smoke(root, "camera-direct-failed", serial="SERIAL123", hdc_runner=runner)

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["quality_gate"], "CAMERA_DIRECT_SMOKE_FAILED")
            self.assertIn("failed to start ability", result["launch"]["stdout"])
            workflow = load_workflow(root, "camera-direct-failed")
            self.assertEqual(workflow["current_phase"], "camera_direct_smoke_failed")

    def test_cli_run_camera_direct_smoke_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = StringIO()

            from tools.leaf_author.__main__ import main

            with patch(
                "tools.leaf_author.__main__.run_camera_direct_smoke",
                return_value={"run_id": "camera-direct", "domain": "camera", "quality_gate": "CAMERA_DIRECT_SMOKE_PASS"},
            ) as direct_smoke, redirect_stdout(output):
                exit_code = main(
                    [
                        "run-camera-direct-smoke",
                        "camera-direct",
                        "--root",
                        str(root),
                        "--serial",
                        "SERIAL123",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")
            direct_smoke.assert_called_once()
            self.assertEqual(direct_smoke.call_args.kwargs["serial"], "SERIAL123")

    def test_run_camera_direct_smoke_uses_configured_hdc_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机", run_id="camera-direct-hdc-path")
            calls = []

            def runner(args, timeout_s):
                calls.append(args)
                if args[:3] == ["/sdk/toolchains/hdc", "-t", "SERIAL123"] and args[-3:] == ["get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args[:3] == ["/sdk/toolchains/hdc", "-t", "SERIAL123"] and args[-3:] == ["get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["/sdk/toolchains/hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == [
                    "/sdk/toolchains/hdc",
                    "-t",
                    "SERIAL123",
                    "shell",
                    "aa",
                    "start",
                    "-a",
                    "com.huawei.hmos.camera.MainAbility",
                    "-b",
                    "com.huawei.hmos.camera",
                    "-m",
                    "phone",
                ]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["/sdk/toolchains/hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(
                        0,
                        '{"attributes":{"bundleName":"com.huawei.hmos.camera","abilityName":"com.huawei.hmos.camera.MainAbility","text":"Camera"},"children":[]}\n',
                        "",
                    )
                if args == ["/sdk/toolchains/hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.camera_smoke import run_camera_direct_smoke

            result = run_camera_direct_smoke(root, "camera-direct-hdc-path", serial="SERIAL123", hdc_path="/sdk/toolchains/hdc", hdc_runner=runner)

            self.assertEqual(result["quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")
            self.assertTrue(calls)
            self.assertTrue(all(call[0] == "/sdk/toolchains/hdc" for call in calls))

    def test_run_camera_capture_e2e_clicks_verified_shutter_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机；点击拍照", run_id="camera-capture")
            calls = []
            media_queries = 0
            layout_path = "/data/local/tmp/layout_123.json"
            after_layout_path = "/data/local/tmp/layout_456.json"
            layout = json.dumps(
                {
                    "attributes": {},
                    "children": [
                        {
                            "attributes": {
                                "bundleName": "com.huawei.hmos.camera",
                                "abilityName": "com.huawei.hmos.camera.MainAbility",
                                "bounds": "[0,0][1080,2444]",
                            },
                            "children": [
                                {
                                    "attributes": {
                                        "id": "COMPONENT_ID_CONTROL_PHOTO_2",
                                        "text": "拍照",
                                        "bounds": "[496,1775][584,1850]",
                                        "visible": "true",
                                    },
                                    "children": [],
                                },
                                {
                                    "attributes": {
                                        "id": "COMPONENT_ID_SHUTTER_PHOTO_1",
                                        "clickable": "true",
                                        "bounds": "[440,1966][640,2166]",
                                        "visible": "true",
                                    },
                                    "children": [],
                                },
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            )

            def runner(args, timeout_s):
                nonlocal media_queries
                calls.append(args)
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == [
                    "hdc",
                    "-t",
                    "SERIAL123",
                    "shell",
                    "aa",
                    "start",
                    "-a",
                    "com.huawei.hmos.camera.MainAbility",
                    "-b",
                    "com.huawei.hmos.camera",
                    "-m",
                    "phone",
                ]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"] and calls.count(args) == 1:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    return ProbeCommandResult(0, layout + "\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "find", "/storage/media/100/local/files/Photo", "-maxdepth", "3", "-type", "f"]:
                    media_queries += 1
                    if media_queries == 1:
                        return ProbeCommandResult(0, "/storage/media/100/local/files/Photo/16/IMG_100.heic\n", "")
                    return ProbeCommandResult(
                        0,
                        "/storage/media/100/local/files/Photo/16/IMG_100.heic\n/storage/media/100/local/files/Photo/16/IMG_101.heic\n",
                        "",
                    )
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "uiInput", "click", "540", "2066"]:
                    return ProbeCommandResult(0, "click success\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{after_layout_path}\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "cat", after_layout_path]:
                    return ProbeCommandResult(0, layout + "\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera capture log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.camera_smoke import run_camera_capture_e2e

            result = run_camera_capture_e2e(root, "camera-capture", serial="SERIAL123", hdc_runner=runner)

            self.assertEqual(result["quality_gate"], "CAMERA_CAPTURE_E2E_PASS")
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["evidence_schema_version"], "1.0")
            self.assertEqual(result["quality_gate_description"], "Camera capture passed with real UiTest shutter control and new media-file evidence.")
            self.assertEqual(result["evidence_summary"]["before_layout"]["verified"], True)
            self.assertEqual(result["evidence_summary"]["after_layout"]["verified"], True)
            self.assertEqual(result["evidence_summary"]["controls"]["photo_mode_found"], True)
            self.assertEqual(result["evidence_summary"]["controls"]["shutter_found"], True)
            self.assertEqual(result["evidence_summary"]["media"]["new_count"], 1)
            self.assertEqual(result["evidence"]["layout_verified"], True)
            self.assertEqual(result["evidence"]["capture_triggered"], True)
            self.assertEqual(result["evidence"]["media_delta_detected"], True)
            self.assertEqual(result["evidence"]["shutter_node"]["id"], "COMPONENT_ID_SHUTTER_PHOTO_1")
            self.assertEqual(result["evidence"]["shutter_tap"], {"x": 540, "y": 2066})
            self.assertEqual(result["evidence"]["new_media_files"], ["/storage/media/100/local/files/Photo/16/IMG_101.heic"])
            self.assertEqual(result["evidence"]["ui_snapshots"]["before_capture"]["kind"], "ui_snapshot")
            self.assertEqual(result["evidence"]["ui_snapshots"]["after_capture"]["kind"], "ui_snapshot")
            self.assertTrue((root / result["evidence"]["ui_snapshots"]["before_capture"]["index_path"]).is_file())
            self.assertTrue((root / result["evidence"]["ui_snapshots"]["after_capture"]["index_path"]).is_file())
            self.assertEqual(result["evidence"]["ui_diff"]["node_count_delta"], 0)
            self.assertIn(["hdc", "-t", "SERIAL123", "shell", "uitest", "uiInput", "click", "540", "2066"], calls)
            workflow = load_workflow(root, "camera-capture")
            self.assertEqual(workflow["current_phase"], "camera_capture_e2e_complete")
            self.assertEqual(workflow["artifacts"]["camera_capture_e2e"], ".leaf/runs/camera-capture/camera_capture_e2e.json")

    def test_run_camera_capture_e2e_fails_without_shutter_node_before_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机；点击拍照", run_id="camera-capture-no-shutter")
            calls = []
            layout_path = "/data/local/tmp/layout_123.json"
            layout = json.dumps(
                {
                    "attributes": {},
                    "children": [
                        {
                            "attributes": {
                                "bundleName": "com.huawei.hmos.camera",
                                "abilityName": "com.huawei.hmos.camera.MainAbility",
                            },
                            "children": [
                                {
                                    "attributes": {
                                        "id": "COMPONENT_ID_CONTROL_PHOTO_2",
                                        "text": "拍照",
                                        "bounds": "[496,1775][584,1850]",
                                    },
                                    "children": [],
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            )

            def runner(args, timeout_s):
                calls.append(args)
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "start"]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    return ProbeCommandResult(0, layout + "\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera capture log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.camera_smoke import run_camera_capture_e2e

            result = run_camera_capture_e2e(root, "camera-capture-no-shutter", serial="SERIAL123", hdc_runner=runner)

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["quality_gate"], "CAMERA_CAPTURE_E2E_FAILED")
            self.assertEqual(result["failure_reason"], "SHUTTER_NODE_MISSING")
            self.assertEqual(result["evidence_summary"]["failure_reason"], "SHUTTER_NODE_MISSING")
            self.assertIsNone(result["evidence"]["shutter_node"])
            self.assertFalse(any(args[:7] == ["hdc", "-t", "SERIAL123", "shell", "uitest", "uiInput", "click"] for args in calls))

    def test_run_camera_capture_e2e_requires_new_media_file_after_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机；点击拍照", run_id="camera-capture-no-media")
            layout_path = "/data/local/tmp/layout_123.json"
            after_layout_path = "/data/local/tmp/layout_456.json"
            layout = json.dumps(
                {
                    "attributes": {
                        "bundleName": "com.huawei.hmos.camera",
                        "abilityName": "com.huawei.hmos.camera.MainAbility",
                    },
                    "children": [
                        {
                            "attributes": {"id": "COMPONENT_ID_CONTROL_PHOTO_2", "text": "拍照", "bounds": "[496,1775][584,1850]"},
                            "children": [],
                        },
                        {
                            "attributes": {"id": "COMPONENT_ID_SHUTTER_PHOTO_1", "clickable": "true", "bounds": "[440,1966][640,2166]"},
                            "children": [],
                        },
                    ],
                },
                ensure_ascii=False,
            )

            def runner(args, timeout_s):
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args[:6] == ["hdc", "-t", "SERIAL123", "shell", "aa", "start"]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path if not hasattr(runner, 'dumped') else after_layout_path}\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    runner.dumped = True
                    return ProbeCommandResult(0, layout + "\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "cat", after_layout_path]:
                    return ProbeCommandResult(0, layout + "\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "find", "/storage/media/100/local/files/Photo", "-maxdepth", "3", "-type", "f"]:
                    return ProbeCommandResult(0, "/storage/media/100/local/files/Photo/16/IMG_100.heic\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "uiInput", "click", "540", "2066"]:
                    return ProbeCommandResult(0, "click success\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera capture log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.camera_smoke import run_camera_capture_e2e

            result = run_camera_capture_e2e(root, "camera-capture-no-media", serial="SERIAL123", hdc_runner=runner)

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["quality_gate"], "CAMERA_CAPTURE_E2E_FAILED")
            self.assertEqual(result["failure_reason"], "NEW_MEDIA_FILE_MISSING")
            self.assertEqual(result["evidence_summary"]["failure_reason"], "NEW_MEDIA_FILE_MISSING")
            self.assertEqual(result["evidence"]["new_media_files"], [])

    def test_cli_run_camera_capture_e2e_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = StringIO()

            from tools.leaf_author.__main__ import main

            with patch(
                "tools.leaf_author.__main__.run_camera_capture_e2e",
                return_value={"run_id": "camera-capture", "domain": "camera", "quality_gate": "CAMERA_CAPTURE_E2E_PASS"},
            ) as capture, redirect_stdout(output):
                exit_code = main(
                    [
                        "run-camera-capture-e2e",
                        "camera-capture",
                        "--root",
                        str(root),
                        "--serial",
                        "SERIAL123",
                        "--hdc-path",
                        "/sdk/hdc",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "CAMERA_CAPTURE_E2E_PASS")
            capture.assert_called_once()
            self.assertEqual(capture.call_args.kwargs["serial"], "SERIAL123")
            self.assertEqual(capture.call_args.kwargs["hdc_path"], "/sdk/hdc")


if __name__ == "__main__":
    unittest.main()
