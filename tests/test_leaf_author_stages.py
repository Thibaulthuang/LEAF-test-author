import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tools.leaf_author.authoring import confirm_plan, start_new_case
from tools.leaf_author.device_probe import ProbeCommandResult
from tools.leaf_author.experience import export_team_knowledge, record_experience
from tools.leaf_author.gui_context import collect_gui_context
from tools.leaf_author.runner import run_pytest_draft
from tools.leaf_author.validator import validate_pytest_draft
from tools.leaf_author.workflow import load_workflow, save_workflow


class LeafAuthorStageTests(unittest.TestCase):
    def _confirmed_case(self, root: Path, run_id: str = "stage-001") -> Path:
        start_new_case(root, "camera", "打开相机；点击拍照", run_id=run_id)
        confirm_plan(root, run_id)
        return root / "tests" / "generated" / f"test_{run_id.replace('-', '_')}_camera.py"

    def test_validate_pytest_draft_writes_validation_artifact_and_advances_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root)

            result = validate_pytest_draft(root, "stage-001")

            validation_path = root / ".leaf" / "runs" / "stage-001" / "validation.json"
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["next_action"], "run_pytest_draft")
            self.assertTrue(validation_path.exists())
            self.assertEqual(load_workflow(root, "stage-001")["current_phase"], "validated")
            payload = json.loads(validation_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["checks"]["has_run_id"], True)
            self.assertEqual(payload["checks"]["has_metadata_assertions"], True)

    def test_validate_pytest_draft_rejects_legacy_skip_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pytest_path = self._confirmed_case(root)
            content = pytest_path.read_text(encoding="utf-8")
            pytest_path.write_text(content + "\n    pytest.skip(\"legacy draft\")\n", encoding="utf-8")

            result = validate_pytest_draft(root, "stage-001")

            validation_path = root / ".leaf" / "runs" / "stage-001" / "validation.json"
            payload = json.loads(validation_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["next_action"], "repair_pytest_draft")
            self.assertEqual(payload["checks"]["has_no_pytest_skip"], False)
            self.assertEqual(load_workflow(root, "stage-001")["current_phase"], "validation_failed")

    def test_run_pytest_draft_records_executable_draft_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root)
            validate_pytest_draft(root, "stage-001")

            result = run_pytest_draft(root, "stage-001")

            run_path = root / ".leaf" / "runs" / "stage-001" / "pytest_result.json"
            self.assertEqual(result["status"], "draft_passed")
            self.assertEqual(result["quality_gate"], "DRAFT_STATIC_PASS")
            self.assertEqual(result["next_action"], "collect_gui_context")
            self.assertTrue(run_path.exists())
            self.assertEqual(load_workflow(root, "stage-001")["current_phase"], "pytest_ran")

    def test_run_pytest_draft_uses_current_python_pytest_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root)
            validate_pytest_draft(root, "stage-001")

            class Completed:
                returncode = 0
                stdout = "1 passed\n"
                stderr = ""

            with patch("tools.leaf_author.runner._pytest_available", return_value=True), patch("tools.leaf_author.runner.subprocess.run", return_value=Completed()) as run:
                result = run_pytest_draft(root, "stage-001")

            self.assertEqual(result["runner"], "pytest")
            self.assertEqual(result["command"][1:3], ["-m", "pytest"])
            run.assert_called_once()

    def test_collect_gui_context_uses_read_only_hdc_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root)

            def runner(args, timeout_s):
                if args == ["hdc", "list", "targets"]:
                    return ProbeCommandResult(0, "SERIAL123\n", "")
                if "dumpLayout" in args:
                    return ProbeCommandResult(0, '{"windows":[]}\n', "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera log line\n", "")
                return ProbeCommandResult(0, "ok\n", "")

            result = collect_gui_context(root, "stage-001", hdc_runner=runner)

            context_path = root / ".leaf" / "runs" / "stage-001" / "gui_context.json"
            self.assertEqual(result["status"], "collected")
            self.assertEqual(result["serial"], "SERIAL123")
            self.assertEqual(result["next_action"], "record_experience")
            self.assertTrue(context_path.exists())
            payload = json.loads(context_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["ui_tree_excerpt"], '{"windows":[]}')
            self.assertEqual(payload["hilog_excerpt"], "camera log line")

    def test_record_experience_writes_platform_scoped_knowledge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root)
            validate_pytest_draft(root, "stage-001")
            run_pytest_draft(root, "stage-001")

            result = record_experience(root, "stage-001")

            knowledge_path = root / ".leaf" / "knowledge" / "camera" / "openharmony" / "experience" / "stage-001.json"
            self.assertEqual(result["status"], "recorded")
            self.assertEqual(result["next_action"], "export_team_knowledge")
            self.assertTrue(knowledge_path.exists())
            payload = json.loads(knowledge_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["domain"], "camera")
            self.assertEqual(payload["platform"], "openharmony")
            self.assertEqual(payload["run_status"], "draft_passed")
            self.assertEqual(load_workflow(root, "stage-001")["current_phase"], "experience_recorded")

    def test_export_team_knowledge_writes_reviewable_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root)
            validate_pytest_draft(root, "stage-001")
            run_pytest_draft(root, "stage-001")
            record_experience(root, "stage-001")

            result = export_team_knowledge(root, "stage-001")

            manifest_path = root / ".leaf" / "runs" / "stage-001" / "team_export_manifest.json"
            self.assertEqual(result["status"], "exported")
            self.assertEqual(result["next_action"], "complete")
            self.assertTrue(manifest_path.exists())
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["manifest_kind"], "reviewable_team_knowledge")
            self.assertEqual(payload["artifacts"]["experience"], ".leaf/knowledge/camera/openharmony/experience/stage-001.json")
            self.assertEqual(load_workflow(root, "stage-001")["current_phase"], "complete")

    def test_advance_after_confirmation_runs_safe_local_stages_to_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root, run_id="stage-002")

            from tools.leaf_author.authoring import advance_run

            result = advance_run(root, "stage-002")

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["current_phase"], "complete")
            self.assertEqual(result["stages"], ["validation", "pytest_result", "gui_context", "experience", "team_export_manifest"])
            self.assertTrue((root / ".leaf" / "runs" / "stage-002" / "team_export_manifest.json").exists())
            self.assertEqual(load_workflow(root, "stage-002")["current_phase"], "complete")

    def test_advance_camera_direct_real_smoke_records_real_device_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root, run_id="stage-camera-direct")
            calls = []
            layout_path = "/data/local/tmp/layout_123.json"

            def runner(args, timeout_s):
                calls.append(args)
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == [
                    "/sdk/hdc",
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
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    return ProbeCommandResult(
                        0,
                        '{"attributes":{"bundleName":"com.huawei.hmos.camera","abilityName":"com.huawei.hmos.camera.MainAbility","text":"相机"},"children":[]}\n',
                        "",
                    )
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            from tools.leaf_author.authoring import advance_run

            result = advance_run(root, "stage-camera-direct", hdc_runner=runner, serial="SERIAL123", run_real=True, camera_direct=True, hdc_path="/sdk/hdc")

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["stages"], ["validation", "pytest_result", "camera_direct_smoke", "experience", "team_export_manifest"])
            self.assertIn(
                [
                    "/sdk/hdc",
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
            smoke = json.loads((root / ".leaf" / "runs" / "stage-camera-direct" / "camera_direct_smoke.json").read_text(encoding="utf-8"))
            self.assertEqual(smoke["quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")
            self.assertEqual(smoke["evidence"]["layout_verified"], True)
            preflight = json.loads((root / ".leaf" / "runs" / "stage-camera-direct" / "real_device_preflight.json").read_text(encoding="utf-8"))
            self.assertEqual(preflight["status"], "ready")
            self.assertEqual(preflight["runtime_mode"], "direct_smoke")
            self.assertEqual(preflight["serial"], "SERIAL123")
            self.assertEqual(preflight["approval_status"], "not_required")
            self.assertEqual(preflight["input_status"], "ready")
            self.assertEqual(preflight["decision_contract"]["agent_owner"], "leaf-test-author")
            self.assertIn("runtime_safety", preflight["decision_contract"]["context_slice"])
            self.assertEqual(preflight["user_loop"]["position"], "observe_real_device_execution")
            experience = json.loads((root / ".leaf" / "knowledge" / "camera" / "openharmony" / "experience" / "stage-camera-direct.json").read_text(encoding="utf-8"))
            self.assertEqual(experience["quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")
            manifest = json.loads((root / ".leaf" / "runs" / "stage-camera-direct" / "team_export_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["camera_direct_smoke"], ".leaf/runs/stage-camera-direct/camera_direct_smoke.json")
            self.assertEqual(manifest["artifacts"]["real_device_preflight"], ".leaf/runs/stage-camera-direct/real_device_preflight.json")
            self.assertEqual(load_workflow(root, "stage-camera-direct")["current_phase"], "complete")

    def test_advance_real_runtime_requires_confirmed_plan_before_any_real_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="stage-real-before-confirm")

            from tools.leaf_author.authoring import advance_run

            with patch("tools.leaf_author.authoring.run_domain_runtime") as runtime:
                result = advance_run(
                    root,
                    "stage-real-before-confirm",
                    run_real=True,
                    runtime_mode="direct_smoke",
                    serial="SERIAL123",
                    hdc_path="/sdk/hdc",
                )

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["block_reason"], "plan_confirmation_required")
            self.assertEqual(result["next_action"], "present_plan_for_confirmation")
            self.assertEqual(result["stages"], [])
            self.assertEqual(result["resume_summary"]["user_checkpoint"], "first_plan_confirmation")
            runtime.assert_not_called()
            run_dir = root / ".leaf" / "runs" / "stage-real-before-confirm"
            self.assertFalse((run_dir / "case.json").exists())
            self.assertFalse((run_dir / "real_device_input.json").exists())
            self.assertFalse((run_dir / "real_device_preflight.json").exists())
            workflow = load_workflow(root, "stage-real-before-confirm")
            self.assertEqual(workflow["current_phase"], "plan")
            self.assertEqual(workflow["confirmed_plan"], False)

    def test_advance_camera_capture_real_e2e_requires_approval_token_before_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root, run_id="stage-camera-capture-blocked")

            from tools.leaf_author.authoring import advance_run

            with patch("tools.leaf_author.camera_smoke.run_camera_capture_e2e") as capture:
                result = advance_run(root, "stage-camera-capture-blocked", serial="SERIAL123", run_real=True, camera_capture=True, hdc_path="/sdk/hdc")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["block_reason"], "real_device_approval_required")
            self.assertEqual(result["required_approval_token"], "approve_camera_capture_e2e")
            self.assertEqual(result["runtime_safety"]["mutates_device_state"], True)
            capture.assert_not_called()
            approval_path = root / ".leaf" / "runs" / "stage-camera-capture-blocked" / "real_device_approval.json"
            self.assertTrue(approval_path.exists())
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
            self.assertEqual(approval["status"], "blocked")
            self.assertEqual(approval["required_approval_token"], "approve_camera_capture_e2e")
            self.assertEqual(approval["runtime_mode"], "capture_e2e")
            workflow = load_workflow(root, "stage-camera-capture-blocked")
            self.assertEqual(workflow["current_phase"], "hypium_draft")
            self.assertEqual(workflow["artifacts"]["real_device_approval"], ".leaf/runs/stage-camera-capture-blocked/real_device_approval.json")

    def test_advance_real_runtime_requires_serial_before_local_or_device_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root, run_id="stage-runtime-missing-serial")

            from tools.leaf_author.authoring import advance_run

            with patch("tools.leaf_author.authoring.run_domain_runtime") as runtime:
                result = advance_run(root, "stage-runtime-missing-serial", run_real=True, runtime_mode="direct_smoke")

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["block_reason"], "real_device_serial_required")
            self.assertEqual(result["next_action"], "provide_real_device_serial")
            self.assertEqual(result["stages"], [])
            self.assertEqual(result["resume_summary"]["user_loop"]["position"], "provide_target_inputs")
            runtime.assert_not_called()
            run_dir = root / ".leaf" / "runs" / "stage-runtime-missing-serial"
            input_path = run_dir / "real_device_input.json"
            self.assertTrue(input_path.exists())
            input_payload = json.loads(input_path.read_text(encoding="utf-8"))
            self.assertEqual(input_payload["status"], "blocked")
            self.assertEqual(input_payload["missing"], ["serial"])
            self.assertEqual(input_payload["runtime_mode"], "direct_smoke")
            self.assertFalse((run_dir / "validation.json").exists())
            workflow = load_workflow(root, "stage-runtime-missing-serial")
            self.assertEqual(workflow["current_phase"], "hypium_draft")
            self.assertEqual(workflow["artifacts"]["real_device_input"], ".leaf/runs/stage-runtime-missing-serial/real_device_input.json")

    def test_advance_real_runtime_uses_selected_device_serial_when_serial_is_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root, run_id="stage-runtime-selected-device")
            run_dir = root / ".leaf" / "runs" / "stage-runtime-selected-device"
            selection_path = run_dir / "device_selection.json"
            selection_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "artifact_kind": "real_device_selection",
                        "run_id": "stage-runtime-selected-device",
                        "status": "selected",
                        "serial": "SERIAL123",
                        "targets": ["SERIAL123"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            workflow = load_workflow(root, "stage-runtime-selected-device")
            workflow["artifacts"]["device_selection"] = ".leaf/runs/stage-runtime-selected-device/device_selection.json"
            save_workflow(root, workflow)

            from tools.leaf_author.authoring import advance_run

            def fake_runtime(root_arg, run_id_arg, domain_arg, runtime_mode_arg, **kwargs):
                self.assertEqual(kwargs["serial"], "SERIAL123")
                from tools.leaf_author.workflow import load_workflow, save_workflow

                smoke_path = root_arg / ".leaf" / "runs" / run_id_arg / "camera_direct_smoke.json"
                smoke_path.write_text(json.dumps({"status": "complete", "quality_gate": "CAMERA_DIRECT_SMOKE_PASS"}) + "\n", encoding="utf-8")
                workflow = load_workflow(root_arg, run_id_arg)
                artifacts = dict(workflow.get("artifacts", {}))
                artifacts["camera_direct_smoke"] = str(smoke_path.relative_to(root_arg))
                workflow["artifacts"] = artifacts
                workflow["current_phase"] = "camera_direct_smoke_complete"
                save_workflow(root_arg, workflow)
                return {
                    "stage": "camera_direct_smoke",
                    "pass_quality_gate": "CAMERA_DIRECT_SMOKE_PASS",
                    "inspect_action": "inspect_camera_direct_smoke",
                    "result": {"status": "complete", "quality_gate": "CAMERA_DIRECT_SMOKE_PASS"},
                }

            with patch("tools.leaf_author.authoring.run_domain_runtime", side_effect=fake_runtime):
                result = advance_run(root, "stage-runtime-selected-device", run_real=True, runtime_mode="direct_smoke")

            self.assertEqual(result["status"], "complete")
            input_payload = json.loads((run_dir / "real_device_input.json").read_text(encoding="utf-8"))
            self.assertEqual(input_payload["status"], "ready")
            self.assertEqual(input_payload["serial"], "SERIAL123")
            self.assertEqual(input_payload["serial_source"], "device_selection")
            preflight_payload = json.loads((run_dir / "real_device_preflight.json").read_text(encoding="utf-8"))
            self.assertEqual(preflight_payload["serial"], "SERIAL123")
            self.assertEqual(preflight_payload["serial_source"], "device_selection")

    def test_advance_real_runtime_updates_existing_input_artifact_after_serial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root, run_id="stage-runtime-serial-ready")

            from tools.leaf_author.authoring import advance_run

            blocked = advance_run(root, "stage-runtime-serial-ready", run_real=True, runtime_mode="direct_smoke")
            self.assertEqual(blocked["status"], "blocked")

            def fake_runtime(root_arg, run_id_arg, domain_arg, runtime_mode_arg, **kwargs):
                from tools.leaf_author.workflow import load_workflow, save_workflow

                smoke_path = root_arg / ".leaf" / "runs" / run_id_arg / "camera_direct_smoke.json"
                smoke_path.write_text(json.dumps({"status": "complete", "quality_gate": "CAMERA_DIRECT_SMOKE_PASS"}) + "\n", encoding="utf-8")
                workflow = load_workflow(root_arg, run_id_arg)
                artifacts = dict(workflow.get("artifacts", {}))
                artifacts["camera_direct_smoke"] = str(smoke_path.relative_to(root_arg))
                workflow["artifacts"] = artifacts
                workflow["current_phase"] = "camera_direct_smoke_complete"
                save_workflow(root_arg, workflow)
                return {
                    "stage": "camera_direct_smoke",
                    "pass_quality_gate": "CAMERA_DIRECT_SMOKE_PASS",
                    "inspect_action": "inspect_camera_direct_smoke",
                    "result": {"status": "complete", "quality_gate": "CAMERA_DIRECT_SMOKE_PASS"},
                }

            with patch("tools.leaf_author.authoring.run_domain_runtime", side_effect=fake_runtime):
                result = advance_run(root, "stage-runtime-serial-ready", run_real=True, runtime_mode="direct_smoke", serial="SERIAL123")

            self.assertEqual(result["status"], "complete")
            input_payload = json.loads((root / ".leaf" / "runs" / "stage-runtime-serial-ready" / "real_device_input.json").read_text(encoding="utf-8"))
            self.assertEqual(input_payload["status"], "ready")
            self.assertEqual(input_payload["missing"], [])
            self.assertEqual(input_payload["next_action"], "run_real_device_runtime")

    def test_advance_camera_capture_real_e2e_records_capture_gate_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root, run_id="stage-camera-capture")

            from tools.leaf_author.authoring import advance_run

            def fake_capture(root_arg, run_id_arg, **kwargs):
                run_dir = root_arg / ".leaf" / "runs" / run_id_arg
                capture_path = run_dir / "camera_capture_e2e.json"
                capture_path.write_text(
                    json.dumps({"run_id": run_id_arg, "status": "complete", "quality_gate": "CAMERA_CAPTURE_E2E_PASS"}, indent=2)
                    + "\n",
                    encoding="utf-8",
                )
                from tools.leaf_author.workflow import load_workflow, save_workflow

                workflow = load_workflow(root_arg, run_id_arg)
                artifacts = dict(workflow.get("artifacts", {}))
                artifacts["camera_capture_e2e"] = str(capture_path.relative_to(root_arg))
                workflow["artifacts"] = artifacts
                workflow["current_phase"] = "camera_capture_e2e_complete"
                save_workflow(root_arg, workflow)
                return {
                    "run_id": run_id_arg,
                    "status": "complete",
                    "quality_gate": "CAMERA_CAPTURE_E2E_PASS",
                    "camera_capture_e2e_path": str(capture_path),
                }

            with patch(
                "tools.leaf_author.camera_smoke.run_camera_capture_e2e",
                side_effect=fake_capture,
            ) as capture:
                result = advance_run(
                    root,
                    "stage-camera-capture",
                    serial="SERIAL123",
                    run_real=True,
                    camera_capture=True,
                    hdc_path="/sdk/hdc",
                    approval_token="approve_camera_capture_e2e",
                )

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["stages"], ["validation", "pytest_result", "camera_capture_e2e", "experience", "team_export_manifest"])
            capture.assert_called_once()
            self.assertEqual(capture.call_args.kwargs["hdc_path"], "/sdk/hdc")
            workflow = load_workflow(root, "stage-camera-capture")
            self.assertEqual(workflow["current_phase"], "complete")
            self.assertEqual(workflow["artifacts"]["camera_capture_e2e"], ".leaf/runs/stage-camera-capture/camera_capture_e2e.json")
            self.assertEqual(workflow["artifacts"]["real_device_preflight"], ".leaf/runs/stage-camera-capture/real_device_preflight.json")
            preflight = json.loads((root / ".leaf" / "runs" / "stage-camera-capture" / "real_device_preflight.json").read_text(encoding="utf-8"))
            self.assertEqual(preflight["runtime_mode"], "capture_e2e")
            self.assertEqual(preflight["approval_status"], "approved")
            self.assertEqual(preflight["approval_token"], "approve_camera_capture_e2e")
            self.assertEqual(preflight["decision_contract"]["agent_owner"], "leaf-test-author")
            self.assertIn("real_device_approval", preflight["decision_contract"]["allowed_artifacts"])
            experience = json.loads((root / ".leaf" / "knowledge" / "camera" / "openharmony" / "experience" / "stage-camera-capture.json").read_text(encoding="utf-8"))
            self.assertEqual(experience["quality_gate"], "CAMERA_CAPTURE_E2E_PASS")
            manifest = json.loads((root / ".leaf" / "runs" / "stage-camera-capture" / "team_export_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"]["camera_capture_e2e"], ".leaf/runs/stage-camera-capture/camera_capture_e2e.json")
            self.assertEqual(manifest["artifacts"]["real_device_preflight"], ".leaf/runs/stage-camera-capture/real_device_preflight.json")

    def test_advance_camera_capture_updates_existing_approval_artifact_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root, run_id="stage-camera-capture-approved")

            from tools.leaf_author.authoring import advance_run

            blocked = advance_run(root, "stage-camera-capture-approved", serial="SERIAL123", run_real=True, camera_capture=True, hdc_path="/sdk/hdc")
            self.assertEqual(blocked["status"], "blocked")

            def fake_capture(root_arg, run_id_arg, **kwargs):
                run_dir = root_arg / ".leaf" / "runs" / run_id_arg
                capture_path = run_dir / "camera_capture_e2e.json"
                capture_path.write_text(json.dumps({"status": "complete", "quality_gate": "CAMERA_CAPTURE_E2E_PASS"}) + "\n", encoding="utf-8")
                from tools.leaf_author.workflow import load_workflow, save_workflow

                workflow = load_workflow(root_arg, run_id_arg)
                artifacts = dict(workflow.get("artifacts", {}))
                artifacts["camera_capture_e2e"] = str(capture_path.relative_to(root_arg))
                workflow["artifacts"] = artifacts
                workflow["current_phase"] = "camera_capture_e2e_complete"
                save_workflow(root_arg, workflow)
                return {"status": "complete", "quality_gate": "CAMERA_CAPTURE_E2E_PASS"}

            with patch("tools.leaf_author.camera_smoke.run_camera_capture_e2e", side_effect=fake_capture):
                result = advance_run(
                    root,
                    "stage-camera-capture-approved",
                    serial="SERIAL123",
                    run_real=True,
                    camera_capture=True,
                    hdc_path="/sdk/hdc",
                    approval_token="approve_camera_capture_e2e",
                )

            self.assertEqual(result["status"], "complete")
            approval = json.loads((root / ".leaf" / "runs" / "stage-camera-capture-approved" / "real_device_approval.json").read_text(encoding="utf-8"))
            self.assertEqual(approval["status"], "approved")
            self.assertEqual(approval["next_action"], "run_real_device_runtime")
            self.assertEqual(approval["approval_token"], "approve_camera_capture_e2e")

    def test_cli_advance_accepts_camera_direct_real_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = StringIO()

            from contextlib import redirect_stdout
            from tools.leaf_author.__main__ import main

            with patch(
                "tools.leaf_author.__main__.advance_run",
                return_value={"run_id": "stage-camera-direct-cli", "status": "complete", "stages": ["camera_direct_smoke"]},
            ) as advance, redirect_stdout(output):
                exit_code = main(
                    [
                        "advance",
                        "stage-camera-direct-cli",
                        "--root",
                        str(root),
                        "--serial",
                        "SERIAL123",
                        "--run-real",
                        "--camera-direct",
                        "--hdc-path",
                        "/sdk/hdc",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["stages"], ["camera_direct_smoke"])
            advance.assert_called_once()
            self.assertEqual(advance.call_args.kwargs["run_real"], True)
            self.assertEqual(advance.call_args.kwargs["camera_direct"], True)
            self.assertEqual(advance.call_args.kwargs["hdc_path"], "/sdk/hdc")

    def test_cli_advance_accepts_generic_runtime_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = StringIO()

            from contextlib import redirect_stdout
            from tools.leaf_author.__main__ import main

            with patch(
                "tools.leaf_author.__main__.advance_run",
                return_value={"run_id": "stage-runtime-mode-cli", "status": "complete", "stages": ["camera_direct_smoke"]},
            ) as advance, redirect_stdout(output):
                exit_code = main(
                    [
                        "advance",
                        "stage-runtime-mode-cli",
                        "--root",
                        str(root),
                        "--serial",
                        "SERIAL123",
                        "--run-real",
                        "--runtime-mode",
                        "direct_smoke",
                        "--hdc-path",
                        "/sdk/hdc",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["stages"], ["camera_direct_smoke"])
            advance.assert_called_once()
            self.assertEqual(advance.call_args.kwargs["run_real"], True)
            self.assertEqual(advance.call_args.kwargs["runtime_mode"], "direct_smoke")
            self.assertEqual(advance.call_args.kwargs["hdc_path"], "/sdk/hdc")

    def test_cli_advance_accepts_camera_capture_real_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = StringIO()

            from contextlib import redirect_stdout
            from tools.leaf_author.__main__ import main

            with patch(
                "tools.leaf_author.__main__.advance_run",
                return_value={"run_id": "stage-camera-capture-cli", "status": "complete", "stages": ["camera_capture_e2e"]},
            ) as advance, redirect_stdout(output):
                exit_code = main(
                    [
                        "advance",
                        "stage-camera-capture-cli",
                        "--root",
                        str(root),
                        "--serial",
                        "SERIAL123",
                        "--run-real",
                        "--camera-capture",
                        "--approval-token",
                        "approve_camera_capture_e2e",
                        "--hdc-path",
                        "/sdk/hdc",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["stages"], ["camera_capture_e2e"])
            advance.assert_called_once()
            self.assertEqual(advance.call_args.kwargs["run_real"], True)
            self.assertEqual(advance.call_args.kwargs["camera_capture"], True)
            self.assertEqual(advance.call_args.kwargs["approval_token"], "approve_camera_capture_e2e")
            self.assertEqual(advance.call_args.kwargs["hdc_path"], "/sdk/hdc")

    def test_resume_maps_later_phases_to_next_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root, run_id="stage-003")

            from tools.leaf_author.authoring import resume_run

            self.assertEqual(resume_run(root, "stage-003")["next_action"], "validate_pytest_draft")
            validate_pytest_draft(root, "stage-003")
            self.assertEqual(resume_run(root, "stage-003")["next_action"], "run_pytest_draft")
            run_pytest_draft(root, "stage-003")
            self.assertEqual(resume_run(root, "stage-003")["next_action"], "collect_gui_context")

    def test_resume_maps_e2e_readiness_phases_to_next_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._confirmed_case(root, run_id="stage-e2e")

            from tools.leaf_author.authoring import resume_run
            from tools.leaf_author.workflow import load_workflow, save_workflow

            workflow = load_workflow(root, "stage-e2e")
            workflow["current_phase"] = "e2e_not_ready"
            save_workflow(root, workflow)
            self.assertEqual(resume_run(root, "stage-e2e")["next_action"], "provide_system_app_target")

            workflow["current_phase"] = "e2e_ready"
            save_workflow(root, workflow)
            self.assertEqual(resume_run(root, "stage-e2e")["next_action"], "run_real_hypium")

            workflow["current_phase"] = "openharmony_synced"
            save_workflow(root, workflow)
            self.assertEqual(resume_run(root, "stage-e2e")["next_action"], "inspect_system_app_target")

            workflow["current_phase"] = "openharmony_built"
            save_workflow(root, workflow)
            self.assertEqual(resume_run(root, "stage-e2e")["next_action"], "inspect_e2e_readiness")

            workflow["current_phase"] = "openharmony_build_failed"
            save_workflow(root, workflow)
            self.assertEqual(resume_run(root, "stage-e2e")["next_action"], "inspect_openharmony_build")


if __name__ == "__main__":
    unittest.main()
