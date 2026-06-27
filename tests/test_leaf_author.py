import json
import tempfile
import unittest
from pathlib import Path

from tools.leaf_author.device_probe import HdcProbe, ProbeCommandResult
from tools.leaf_author.generator import generate_pytest_case
from tools.leaf_author.planner import build_plan
from tools.leaf_author.workflow import create_workflow, load_workflow, save_workflow


class LeafAuthorWorkflowTests(unittest.TestCase):
    def test_create_workflow_records_subagent_owned_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            workflow = create_workflow(root, "camera", "打开相机；点击拍照", run_id="run-001")

            workflow_path = root / ".leaf" / "runs" / "run-001" / "workflow.json"
            self.assertTrue(workflow_path.exists())
            self.assertEqual(workflow["run_id"], "run-001")
            self.assertEqual(workflow["domain"], "camera")
            self.assertEqual(workflow["platform"], "openharmony")
            self.assertEqual(workflow["current_phase"], "plan")
            self.assertEqual(workflow["owner"], "leaf-test-author")
            self.assertEqual(workflow["confirmed_plan"], False)
            self.assertEqual(workflow["artifacts"]["run_dir"], ".leaf/runs/run-001")
            self.assertEqual(workflow["phase_state"]["current_phase"], "plan")
            self.assertEqual(workflow["phase_state"]["trigger_source"], "workflow.json")
            self.assertEqual(workflow["phase_state"]["agent_owner"], "leaf-test-author")
            self.assertEqual(workflow["phase_state"]["user_checkpoint"], "first_plan_confirmation")
            self.assertEqual(workflow["phase_state"]["user_loop"]["position"], "approve_plan")
            self.assertEqual(workflow["phase_state"]["safe_to_auto_continue"], False)

            loaded = load_workflow(root, "run-001")
            self.assertEqual(loaded, workflow)

    def test_save_workflow_uses_complete_json_without_temp_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow = create_workflow(root, "camera", "打开相机", run_id="run-atomic")
            workflow["current_phase"] = "complete"
            workflow["confirmed_plan"] = True

            save_workflow(root, workflow)

            workflow_path = root / ".leaf" / "runs" / "run-atomic" / "workflow.json"
            self.assertEqual(json.loads(workflow_path.read_text(encoding="utf-8"))["current_phase"], "complete")
            self.assertEqual(list(workflow_path.parent.glob("workflow.json.*.tmp")), [])

    def test_build_plan_splits_steps_and_points_to_generated_pytest(self):
        workflow = {
            "run_id": "run-002",
            "domain": "camera",
            "platform": "openharmony",
            "teststep": "打开相机；切拍照模式；点击拍照",
        }

        plan = build_plan(workflow)

        self.assertEqual(plan["run_id"], "run-002")
        self.assertEqual(plan["owner"], "leaf-test-author")
        self.assertEqual(plan["domain_skill"], "leaf-camera")
        self.assertEqual(plan["target_feature"], "camera.capture")
        self.assertEqual(plan["steps"], ["打开相机", "切拍照模式", "点击拍照"])
        self.assertEqual(plan["writes"], ["tests/generated/test_run_002_camera.py"])
        self.assertTrue(plan["requires_device_probe"])

    def test_build_plan_accepts_semantic_plan_input_from_opencode(self):
        workflow = {
            "run_id": "run-semantic",
            "domain": "camera",
            "platform": "openharmony",
            "teststep": "打开相机拍照",
        }
        plan_input = {
            "target_feature": "camera.capture",
            "steps": [
                "打开系统相机",
                "确认处于拍照模式",
                "点击快门拍照",
                "检查产生新照片",
            ],
            "risk": "真实执行时会在设备中新增一张照片",
            "confirmation_required": True,
        }

        plan = build_plan(workflow, plan_input=plan_input)

        self.assertEqual(
            plan["steps"],
            [
                "打开系统相机",
                "确认处于拍照模式",
                "点击快门拍照",
                "检查产生新照片",
            ],
        )
        self.assertEqual(plan["target_feature"], "camera.capture")
        self.assertEqual(plan["risk"], "真实执行时会在设备中新增一张照片")
        self.assertTrue(plan["confirmation_required"])

    def test_build_plan_rejects_incomplete_camera_capture_plan_input(self):
        workflow = {
            "run_id": "run-bad-semantic",
            "domain": "camera",
            "platform": "openharmony",
            "teststep": "打开相机拍照",
        }
        plan_input = {
            "target_feature": "camera.capture",
            "steps": ["打开系统相机", "点击快门拍照"],
            "confirmation_required": True,
        }

        with self.assertRaisesRegex(ValueError, "camera.capture semantic plan"):
            build_plan(workflow, plan_input=plan_input)

    def test_generate_pytest_case_writes_traceable_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = {
                "run_id": "run-003",
                "domain": "camera",
                "platform": "openharmony",
                "target_feature": "camera.capture",
                "steps": ["打开相机", "点击拍照"],
            }

            output_path = generate_pytest_case(root, plan)

            self.assertEqual(output_path, root / "tests" / "generated" / "test_run_003_camera.py")
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("Generated by leaf-test-author", content)
            self.assertIn("RUN_ID = \"run-003\"", content)
            self.assertIn("TARGET_FEATURE = \"camera.capture\"", content)
            self.assertIn("def test_run_003_camera", content)
            self.assertIn("# Step 1: 打开相机", content)
            self.assertIn("assert RUN_ID == \"run-003\"", content)
            self.assertIn("assert DOMAIN == \"camera\"", content)
            self.assertNotIn("pytest.skip", content)

    def test_hdc_probe_reports_connected_device_with_metadata(self):
        commands = []

        def runner(args, timeout_s):
            commands.append((args, timeout_s))
            if args == ["hdc", "list", "targets"]:
                return ProbeCommandResult(0, "SERIAL123\n", "")
            if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                return ProbeCommandResult(0, "MateTest\n", "")
            if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                return ProbeCommandResult(0, "14\n", "")
            return ProbeCommandResult(1, "", "unexpected")

        result = HdcProbe(runner=runner).probe()

        self.assertEqual(result["status"], "connected")
        self.assertEqual(result["tool"], "hdc")
        self.assertEqual(result["serial"], "SERIAL123")
        self.assertEqual(result["model"], "MateTest")
        self.assertEqual(result["os_version"], "14")
        self.assertEqual(commands[0], (["hdc", "list", "targets"], 5))

    def test_hdc_probe_reports_unavailable_when_server_fails(self):
        def runner(args, timeout_s):
            return ProbeCommandResult(1, "", "Connect server failed")

        result = HdcProbe(runner=runner).probe()

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["tool"], "hdc")
        self.assertEqual(result["reason"], "Connect server failed")

    def test_hdc_subprocess_runner_replaces_non_utf8_bytes(self):
        class Completed:
            returncode = 0
            stdout = b"ok\xc6bad"
            stderr = b""

        from unittest.mock import patch

        with patch("tools.leaf_author.device_probe.subprocess.run", return_value=Completed()):
            result = HdcProbe._run_subprocess(["hdc", "fake"], 5)

        self.assertEqual(result.exit_code, 0)
        self.assertIn("ok", result.stdout)
        self.assertIn("bad", result.stdout)

    def test_hdc_probe_treats_connect_server_failed_output_as_unavailable(self):
        def runner(args, timeout_s):
            return ProbeCommandResult(0, "Connect server failed\n", "")

        result = HdcProbe(runner=runner).probe()

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "Connect server failed")

    def test_hdc_probe_selects_single_connected_device(self):
        def runner(args, timeout_s):
            if args == ["hdc", "list", "targets"]:
                return ProbeCommandResult(0, "SERIAL123\n", "")
            if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                return ProbeCommandResult(0, "MateTest\n", "")
            if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                return ProbeCommandResult(0, "14\n", "")
            return ProbeCommandResult(1, "", f"unexpected {args}")

        result = HdcProbe(runner=runner).select_device()

        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["selection_reason"], "single_connected_target")
        self.assertEqual(result["serial"], "SERIAL123")
        self.assertEqual(result["targets"], ["SERIAL123"])
        self.assertEqual(result["device"]["model"], "MateTest")
        self.assertEqual(result["device"]["os_version"], "14")
        self.assertEqual(result["user_loop"]["required_input"], "")

    def test_hdc_probe_requires_serial_when_multiple_devices_are_connected(self):
        def runner(args, timeout_s):
            if args == ["hdc", "list", "targets"]:
                return ProbeCommandResult(0, "SERIAL123\nSERIAL456\n", "")
            return ProbeCommandResult(1, "", f"unexpected {args}")

        result = HdcProbe(runner=runner).select_device()

        self.assertEqual(result["status"], "needs_user_input")
        self.assertEqual(result["selection_reason"], "multiple_connected_targets")
        self.assertEqual(result["targets"], ["SERIAL123", "SERIAL456"])
        self.assertEqual(result["user_loop"]["position"], "provide_target_inputs")
        self.assertEqual(result["user_loop"]["required_input"], "--serial <serial>")

    def test_hdc_probe_selects_requested_serial_from_multiple_devices(self):
        def runner(args, timeout_s):
            if args == ["hdc", "list", "targets"]:
                return ProbeCommandResult(0, "SERIAL123\nSERIAL456\n", "")
            if args == ["hdc", "-t", "SERIAL456", "shell", "param", "get", "const.product.model"]:
                return ProbeCommandResult(0, "MateOther\n", "")
            if args == ["hdc", "-t", "SERIAL456", "shell", "param", "get", "const.ohos.apiversion"]:
                return ProbeCommandResult(0, "15\n", "")
            return ProbeCommandResult(1, "", f"unexpected {args}")

        result = HdcProbe(runner=runner).select_device(serial="SERIAL456")

        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["selection_reason"], "requested_serial")
        self.assertEqual(result["serial"], "SERIAL456")
        self.assertEqual(result["device"]["model"], "MateOther")

    def test_hdc_probe_reports_requested_serial_not_connected(self):
        def runner(args, timeout_s):
            if args == ["hdc", "list", "targets"]:
                return ProbeCommandResult(0, "SERIAL123\n", "")
            return ProbeCommandResult(1, "", f"unexpected {args}")

        result = HdcProbe(runner=runner).select_device(serial="SERIAL456")

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["selection_reason"], "requested_serial_not_connected")
        self.assertEqual(result["targets"], ["SERIAL123"])
        self.assertIn("SERIAL456", result["reason"])

    def test_cli_select_device_outputs_selection_json(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from tools.leaf_author.__main__ import main

        output = StringIO()
        with patch(
            "tools.leaf_author.__main__.HdcProbe",
        ) as probe_cls, redirect_stdout(output):
            probe_cls.return_value.select_device.return_value = {
                "status": "selected",
                "serial": "SERIAL123",
                "targets": ["SERIAL123"],
                "selection_reason": "single_connected_target",
            }
            exit_code = main(["select-device", "--serial", "SERIAL123"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "selected")
        self.assertEqual(payload["serial"], "SERIAL123")
        probe_cls.return_value.select_device.assert_called_once_with(serial="SERIAL123")

    def test_select_real_device_writes_run_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机；点击拍照", run_id="select-run")

            def runner(args, timeout_s):
                if args == ["hdc", "list", "targets"]:
                    return ProbeCommandResult(0, "SERIAL123\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "14\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.device_probe import select_real_device

            result = select_real_device(root, "select-run", hdc_runner=runner)

            self.assertEqual(result["status"], "selected")
            self.assertEqual(result["device_selection_path"], ".leaf/runs/select-run/device_selection.json")
            payload = json.loads((root / result["device_selection_path"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["artifact_kind"], "real_device_selection")
            self.assertEqual(payload["serial"], "SERIAL123")
            workflow = load_workflow(root, "select-run")
            self.assertEqual(workflow["artifacts"]["device_selection"], ".leaf/runs/select-run/device_selection.json")

    def test_cli_select_device_for_run_writes_selection_artifact(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from tools.leaf_author.__main__ import main

        output = StringIO()
        with patch(
            "tools.leaf_author.__main__.select_real_device",
            return_value={"status": "selected", "device_selection_path": ".leaf/runs/run-123/device_selection.json"},
        ) as select_device, redirect_stdout(output):
            exit_code = main(["select-device-for-run", "run-123", "--serial", "SERIAL123"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "selected")
        select_device.assert_called_once()
        self.assertEqual(select_device.call_args.kwargs["serial"], "SERIAL123")

    def test_authoring_tool_creates_plan_case_and_probe_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import start_new_case

            def runner(args, timeout_s):
                if args == ["hdc", "list", "targets"]:
                    return ProbeCommandResult(0, "SERIAL123\n", "")
                if "const.product.model" in args:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if "const.ohos.apiversion" in args:
                    return ProbeCommandResult(0, "14\n", "")
                return ProbeCommandResult(1, "", "unexpected")

            result = start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-004", probe_device=True, hdc_runner=runner)

            run_dir = root / ".leaf" / "runs" / "run-004"
            self.assertEqual(result["run_id"], "run-004")
            self.assertEqual(result["workflow_path"], str(run_dir / "workflow.json"))
            self.assertEqual(result["plan_path"], str(run_dir / "plan.json"))
            self.assertIsNone(result["pytest_path"])
            self.assertEqual(result["device_probe_path"], str(run_dir / "device_probe.json"))
            self.assertEqual(json.loads((run_dir / "device_probe.json").read_text(encoding="utf-8"))["status"], "connected")
            self.assertFalse((root / "tests" / "generated" / "test_run_004_camera.py").exists())

    def test_authoring_tool_uses_semantic_plan_input_without_generating_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import start_new_case

            result = start_new_case(
                root,
                "camera",
                "打开相机拍照",
                run_id="run-semantic-author",
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

            run_dir = root / ".leaf" / "runs" / "run-semantic-author"
            plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["steps"][0], "打开系统相机")
            self.assertEqual(plan["steps"][-1], "检查产生新照片")
            self.assertEqual(result["plan_path"], str(run_dir / "plan.json"))
            self.assertIsNone(result["pytest_path"])
            self.assertFalse((root / "tests" / "generated" / "test_run_semantic_author_camera.py").exists())

    def test_new_case_result_includes_confirmation_summary_for_opencode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import start_new_case

            result = start_new_case(
                root,
                "camera",
                "打开相机拍照",
                run_id="run-summary",
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

            summary = result["plan_summary"]
            self.assertEqual(summary["target_feature"], "camera.capture")
            self.assertEqual(summary["steps"][0], "打开系统相机")
            self.assertEqual(summary["writes_after_confirmation"], ["tests/generated/test_run_summary_camera.py"])
            self.assertEqual(summary["first_confirmation_scope"], "plan_only_safe_local_authoring")
            self.assertIn("confirm-plan", summary["after_confirmation_actions"])
            self.assertIn("advance_safe_local", summary["after_confirmation_actions"])
            self.assertEqual(summary["real_device_capture_requires_second_confirmation"], True)

    def test_confirm_plan_generates_json_case_spec_before_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import confirm_plan, start_new_case

            start_new_case(
                root,
                "camera",
                "打开相机拍照",
                run_id="run-json-case",
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

            result = confirm_plan(root, "run-json-case")

            case_path = root / ".leaf" / "runs" / "run-json-case" / "case.json"
            case_spec = json.loads(case_path.read_text(encoding="utf-8"))
            self.assertEqual(result["case_path"], str(case_path))
            self.assertEqual(case_spec["run_id"], "run-json-case")
            self.assertEqual(case_spec["target_feature"], "camera.capture")
            self.assertEqual(
                [step["action"] for step in case_spec["steps"]],
                [
                    "CameraAW.launch",
                    "CameraAW.switchToPhotoMode",
                    "CameraAW.capture",
                    "GalleryAW.assertLatestPhotoCreatedAfter",
                ],
            )
            self.assertEqual(case_spec["steps"][0]["title"], "打开系统相机")
            workflow = load_workflow(root, "run-json-case")
            self.assertEqual(workflow["artifacts"]["case"], ".leaf/runs/run-json-case/case.json")

    def test_new_case_cli_accepts_plan_input_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan_input_path = root / "plan_input.json"
            plan_input_path.write_text(
                json.dumps(
                    {
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
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            from tools.leaf_author.__main__ import main

            exit_code = main(
                [
                    "new-case",
                    "camera",
                    "打开相机拍照",
                    "--run-id",
                    "run-semantic-cli",
                    "--root",
                    str(root),
                    "--plan-input",
                    str(plan_input_path),
                ]
            )

            plan = json.loads((root / ".leaf" / "runs" / "run-semantic-cli" / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(plan["steps"][0], "打开系统相机")
            self.assertEqual(plan["steps"][-1], "检查产生新照片")

    def test_confirm_plan_generates_pytest_and_updates_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import confirm_plan, start_new_case

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-005")
            result = confirm_plan(root, "run-005")

            workflow = load_workflow(root, "run-005")
            self.assertEqual(workflow["confirmed_plan"], True)
            self.assertEqual(workflow["current_phase"], "hypium_draft")
            self.assertEqual(workflow["artifacts"]["pytest"], "tests/generated/test_run_005_camera.py")
            self.assertEqual(workflow["artifacts"]["hypium"], ".leaf/runs/run-005/hypium/run_005_camera.test.ets")
            self.assertEqual(result["pytest_path"], str(root / "tests" / "generated" / "test_run_005_camera.py"))
            self.assertEqual(result["hypium_path"], str(root / ".leaf" / "runs" / "run-005" / "hypium" / "run_005_camera.test.ets"))
            self.assertTrue((root / "tests" / "generated" / "test_run_005_camera.py").exists())
            self.assertTrue((root / ".leaf" / "runs" / "run-005" / "hypium" / "run_005_camera.test.ets").exists())

    def test_confirm_plan_rejects_missing_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机", run_id="run-006")

            from tools.leaf_author.authoring import confirm_plan

            with self.assertRaisesRegex(FileNotFoundError, "plan.json"):
                confirm_plan(root, "run-006")

    def test_resume_run_returns_next_action_before_and_after_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import confirm_plan, resume_run, start_new_case

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-007")
            before = resume_run(root, "run-007")
            self.assertEqual(before["next_action"], "present_plan_for_confirmation")
            self.assertEqual(before["current_phase"], "plan")
            self.assertEqual(before["resume_summary"]["requires_user_confirmation"], True)
            self.assertEqual(before["resume_summary"]["safe_to_auto_continue"], False)
            self.assertIn("Present plan", before["resume_summary"]["operator_message"])
            self.assertEqual(before["resume_summary"]["action_route"]["phase"], "plan")
            self.assertEqual(before["resume_summary"]["action_route"]["next_action"], "present_plan_for_confirmation")
            self.assertEqual(before["resume_summary"]["action_route"]["agent_owner"], "leaf-test-author")
            self.assertEqual(before["resume_summary"]["action_route"]["command"], "python3 -m tools.leaf_author report-run <run_id>")

            confirm_plan(root, "run-007")
            after = resume_run(root, "run-007")
            self.assertEqual(after["next_action"], "validate_pytest_draft")
            self.assertEqual(after["current_phase"], "hypium_draft")
            self.assertEqual(after["resume_summary"]["requires_user_confirmation"], False)
            self.assertEqual(after["resume_summary"]["safe_to_auto_continue"], True)
            self.assertEqual(after["resume_summary"]["action_route"]["phase"], "hypium_draft")
            self.assertEqual(after["resume_summary"]["action_route"]["agent_owner"], "tools.leaf_author")
            self.assertEqual(after["resume_summary"]["action_route"]["command"], "python3 -m tools.leaf_author resume <run_id> --auto-safe")
            workflow = load_workflow(root, "run-007")
            self.assertEqual(workflow["phase_state"]["current_phase"], "hypium_draft")
            self.assertEqual(workflow["phase_state"]["next_action"], "validate_pytest_draft")
            self.assertEqual(workflow["phase_state"]["agent_owner"], "tools.leaf_author")
            self.assertEqual(workflow["phase_state"]["context_slice"], ["workflow", "case", "pytest", "hypium"])
            self.assertEqual(workflow["phase_state"]["user_loop"]["position"], "observe_safe_local_progress")
            self.assertEqual(workflow["phase_state"]["safe_to_auto_continue"], True)
            self.assertEqual(workflow["artifacts"]["context_manifest"], ".leaf/runs/run-007/context_manifest.json")

    def test_resume_run_auto_safe_advances_confirmed_local_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import confirm_plan, resume_run, start_new_case

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-auto-resume")
            confirm_plan(root, "run-auto-resume")

            result = resume_run(root, "run-auto-resume", auto_safe=True)

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["auto_advanced"], True)
            self.assertEqual(result["current_phase"], "complete")
            self.assertEqual(result["advance_result"]["stages"], ["validation", "pytest_result", "gui_context", "experience", "team_export_manifest"])
            self.assertTrue((root / ".leaf" / "runs" / "run-auto-resume" / "team_export_manifest.json").exists())
            workflow = load_workflow(root, "run-auto-resume")
            self.assertEqual(workflow["phase_state"]["current_phase"], "complete")
            self.assertEqual(workflow["phase_state"]["next_action"], "complete")
            self.assertEqual(workflow["phase_state"]["safe_to_auto_continue"], False)

    def test_resume_run_auto_safe_blocks_when_run_audit_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import confirm_plan, resume_run, start_new_case

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-audit-block")
            confirm_plan(root, "run-audit-block")
            audit_path = root / ".leaf" / "runs" / "run-audit-block" / "run_audit.json"
            audit_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "checks": [
                            {"name": "context_manifest_matches_phase_contract", "passed": False},
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            workflow = load_workflow(root, "run-audit-block")
            workflow["artifacts"]["run_audit"] = ".leaf/runs/run-audit-block/run_audit.json"
            save_workflow(root, workflow)

            result = resume_run(root, "run-audit-block", auto_safe=True)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["block_reason"], "run_audit_failed")
            self.assertEqual(result["auto_advanced"], False)
            self.assertEqual(result["next_action"], "inspect_run_audit")
            self.assertEqual(result["next_command"], "python3 -m tools.leaf_author report-run <run_id>")
            self.assertEqual(result["action_route"]["next_action"], "inspect_run_audit")
            self.assertEqual(result["action_route"]["command"], "python3 -m tools.leaf_author report-run <run_id>")
            self.assertEqual(result["action_route"]["agent_owner"], "leaf-test-author")
            self.assertEqual(result["action_route"]["agent_mode"], "orchestrator")
            self.assertEqual(result["action_route"]["handoff_required"], False)
            self.assertEqual(result["action_route"]["subagent_boundary"], "run_audit_triage")
            self.assertEqual(result["action_route"]["context_slice"], ["run_audit_summary", "workflow"])
            self.assertEqual(result["action_route"]["user_checkpoint"], "manual_operator_decision")
            self.assertEqual(result["user_checkpoint"], "manual_operator_decision")
            self.assertEqual(result["user_loop"]["position"], "audit_failure_triage")
            self.assertEqual(result["run_audit_summary"]["failed_checks"], ["context_manifest_matches_phase_contract"])
            self.assertEqual(load_workflow(root, "run-audit-block")["current_phase"], "hypium_draft")

    def test_resume_run_auto_safe_does_not_cross_confirmation_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import resume_run, start_new_case

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-auto-waits")

            result = resume_run(root, "run-auto-waits", auto_safe=True)

            self.assertEqual(result["auto_advanced"], False)
            self.assertEqual(result["next_action"], "present_plan_for_confirmation")
            self.assertEqual(result["resume_summary"]["requires_user_confirmation"], True)

    def test_resume_run_auto_safe_stops_at_real_device_approval_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import advance_run, confirm_plan, resume_run, start_new_case

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-approval-waits")
            confirm_plan(root, "run-approval-waits")
            blocked = advance_run(root, "run-approval-waits", run_real=True, runtime_mode="capture_e2e", serial="SERIAL123")

            result = resume_run(root, "run-approval-waits", auto_safe=True)

            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(result["auto_advanced"], False)
            self.assertEqual(result["status"], "waiting_for_confirmation")
            self.assertEqual(result["next_action"], "request_real_device_approval")
            self.assertEqual(result["resume_summary"]["user_checkpoint"], "real_device_confirmation")
            self.assertEqual(result["resume_summary"]["user_loop"]["position"], "approve_real_device")
            self.assertEqual(result["resume_summary"]["user_loop"]["required_input"], "approve_camera_capture_e2e")
            self.assertEqual(result["resume_summary"]["agent_owner"], "leaf-test-author")
            self.assertEqual(result["resume_summary"]["context_slice"], ["workflow", "real_device_approval"])
            manifest_path = root / result["context_manifest"]["context_manifest_path"]
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["context_slice"], ["workflow", "real_device_approval"])
            self.assertIn("real_device_approval", manifest["referenced_artifacts"])
            self.assertNotIn("pytest", manifest["referenced_artifacts"])
            self.assertEqual(load_workflow(root, "run-approval-waits")["current_phase"], "hypium_draft")

    def test_resume_run_ignores_stale_real_device_approval_after_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import advance_run, confirm_plan, resume_run, start_new_case
            from tools.leaf_author.workflow import save_workflow

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-stale-approval")
            confirm_plan(root, "run-stale-approval")
            advance_run(root, "run-stale-approval", run_real=True, runtime_mode="capture_e2e", serial="SERIAL123")
            workflow = load_workflow(root, "run-stale-approval")
            workflow["current_phase"] = "complete"
            save_workflow(root, workflow)

            result = resume_run(root, "run-stale-approval", auto_safe=True)

            self.assertEqual(result["current_phase"], "complete")
            self.assertEqual(result["next_action"], "complete")
            self.assertEqual(result["auto_advanced"], False)
            self.assertEqual(result["status"], "in_progress")
            self.assertNotEqual(result["resume_summary"]["user_checkpoint"], "real_device_confirmation")

    def test_resume_run_auto_safe_stops_at_real_device_input_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from tools.leaf_author.authoring import advance_run, confirm_plan, resume_run, start_new_case

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-input-waits")
            confirm_plan(root, "run-input-waits")
            blocked = advance_run(root, "run-input-waits", run_real=True, runtime_mode="direct_smoke")

            result = resume_run(root, "run-input-waits", auto_safe=True)

            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(result["auto_advanced"], False)
            self.assertEqual(result["next_action"], "provide_real_device_serial")
            self.assertEqual(result["resume_summary"]["user_loop"]["position"], "provide_target_inputs")
            self.assertEqual(result["resume_summary"]["user_loop"]["required_input"], "--serial <serial>")
            self.assertEqual(result["resume_summary"]["context_slice"], ["workflow", "real_device_input"])
            manifest = json.loads((root / result["context_manifest"]["context_manifest_path"]).read_text(encoding="utf-8"))
            self.assertIn("real_device_input", manifest["referenced_artifacts"])
            self.assertNotIn("pytest", manifest["referenced_artifacts"])

    def test_resume_run_blocks_when_phase_guard_is_unstable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from unittest.mock import patch

            from tools.leaf_author.authoring import confirm_plan, resume_run, start_new_case

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-guard-block")
            confirm_plan(root, "run-guard-block")

            with patch(
                "tools.leaf_author.authoring.validate_phase_contract",
                return_value={"status": "unstable", "issues": ["hypium_draft: missing trigger_source"], "exit_code": 1},
            ):
                result = resume_run(root, "run-guard-block", auto_safe=True)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["block_reason"], "phase_contract_unstable")
            self.assertEqual(result["action_route"]["next_action"], "fix_phase_contract")
            self.assertEqual(result["action_route"]["command"], "python3 -m tools.leaf_author phase-guard")
            self.assertEqual(result["action_route"]["agent_owner"], "leaf-test-author")
            self.assertEqual(result["action_route"]["agent_mode"], "orchestrator")
            self.assertEqual(result["action_route"]["handoff_required"], False)
            self.assertEqual(result["action_route"]["subagent_boundary"], "phase_contract_triage")
            self.assertEqual(result["action_route"]["context_slice"], ["workflow", "phase_guard"])
            self.assertEqual(result["action_route"]["user_checkpoint"], "manual_operator_decision")
            self.assertEqual(result["phase_guard"]["issues"], ["hypium_draft: missing trigger_source"])
            self.assertEqual(load_workflow(root, "run-guard-block")["current_phase"], "hypium_draft")

    def test_advance_run_blocks_when_phase_guard_is_unstable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from unittest.mock import patch

            from tools.leaf_author.authoring import advance_run, confirm_plan, start_new_case

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-advance-guard-block")
            confirm_plan(root, "run-advance-guard-block")

            with patch(
                "tools.leaf_author.authoring.validate_phase_contract",
                return_value={"status": "unstable", "issues": ["plan: auto_safe must be false"], "exit_code": 1},
            ):
                result = advance_run(root, "run-advance-guard-block")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["block_reason"], "phase_contract_unstable")
            self.assertEqual(result["action_route"]["next_action"], "fix_phase_contract")
            self.assertEqual(result["action_route"]["command"], "python3 -m tools.leaf_author phase-guard")
            self.assertEqual(result["action_route"]["subagent_boundary"], "phase_contract_triage")
            self.assertEqual(result["stages"], [])
            self.assertEqual(load_workflow(root, "run-advance-guard-block")["current_phase"], "hypium_draft")

    def test_cli_resume_auto_safe_outputs_advanced_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from contextlib import redirect_stdout
            from io import StringIO
            from tools.leaf_author.authoring import confirm_plan, start_new_case
            from tools.leaf_author.__main__ import main

            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-auto-cli")
            confirm_plan(root, "run-auto-cli")
            output = StringIO()

            with redirect_stdout(output):
                exit_code = main(["resume", "run-auto-cli", "--root", str(root), "--auto-safe"])

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["auto_advanced"], True)
            self.assertEqual(payload["current_phase"], "complete")


if __name__ == "__main__":
    unittest.main()
