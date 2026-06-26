import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.leaf_author.authoring import confirm_plan, start_new_case
from tools.leaf_author.batch_registry import create_batch, inspect_batch, list_batches, resume_batch


class BatchRegistryTests(unittest.TestCase):
    def test_create_batch_records_lightweight_run_membership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="batch-run-a")
            start_new_case(root, "camera", "打开相机；切拍照模式；点击拍照", run_id="batch-run-b")
            confirm_plan(root, "batch-run-b")

            result = create_batch(root, "camera-batch", ["batch-run-a", "batch-run-b"], title="Camera smoke suite")

            batch_path = root / ".leaf" / "batches" / "camera-batch" / "batch.json"
            payload = json.loads(batch_path.read_text(encoding="utf-8"))
            self.assertEqual(result["batch_id"], "camera-batch")
            self.assertEqual(result["total_runs"], 2)
            self.assertEqual(payload["title"], "Camera smoke suite")
            self.assertEqual(payload["run_ids"], ["batch-run-a", "batch-run-b"])
            self.assertEqual(payload["context_policy"]["load_strategy"], "inspect_batch_then_inspect_one_run")
            self.assertNotIn("artifacts", payload)

    def test_inspect_batch_returns_summary_and_next_run_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="batch-run-a")
            start_new_case(root, "camera", "打开相机；切拍照模式；点击拍照", run_id="batch-run-b")
            confirm_plan(root, "batch-run-b")
            create_batch(root, "camera-batch", ["batch-run-a", "batch-run-b"])

            result = inspect_batch(root, "camera-batch")

            self.assertEqual(result["batch_id"], "camera-batch")
            self.assertEqual(result["total_runs"], 2)
            self.assertEqual(result["phase_counts"]["plan"], 1)
            self.assertEqual(result["phase_counts"]["hypium_draft"], 1)
            self.assertEqual(result["next_run_focus"]["run_id"], "batch-run-b")
            self.assertEqual(result["next_run_focus"]["next_action"], "validate_pytest_draft")
            self.assertEqual(result["context_policy"]["scope"], "batch_summary")

    def test_inspect_batch_focus_priority_uses_phase_contract_not_action_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="batch-plan")
            start_new_case(root, "camera", "打开相机；切拍照模式；点击拍照", run_id="batch-safe")
            confirm_plan(root, "batch-safe")
            create_batch(root, "camera-batch", ["batch-plan", "batch-safe"])

            result = inspect_batch(root, "camera-batch")

            self.assertEqual(result["next_run_focus"]["run_id"], "batch-safe")
            self.assertEqual(result["next_run_focus"]["focus_source"], "workflow-contract")

    def test_inspect_batch_isolates_unreadable_run_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机", run_id="batch-good")
            start_new_case(root, "camera", "坏 workflow", run_id="batch-bad")
            create_batch(root, "camera-batch", ["batch-good", "batch-bad"])
            (root / ".leaf" / "runs" / "batch-bad" / "workflow.json").write_text("", encoding="utf-8")

            result = inspect_batch(root, "camera-batch")

            self.assertEqual(result["total_runs"], 2)
            self.assertEqual(result["phase_counts"]["plan"], 1)
            self.assertEqual(result["phase_counts"]["unreadable"], 1)
            bad = [run for run in result["runs"] if run["run_id"] == "batch-bad"][0]
            self.assertEqual(bad["current_phase"], "unreadable")
            self.assertEqual(bad["next_action"], "repair_workflow")
            self.assertIn("error", bad)
            self.assertEqual(result["next_run_focus"]["run_id"], "batch-bad")
            self.assertEqual(result["next_run_focus"]["focus_source"], "workflow-read-error")

    def test_create_batch_returns_summary_even_when_member_workflow_is_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "坏 workflow", run_id="batch-create-bad")
            (root / ".leaf" / "runs" / "batch-create-bad" / "workflow.json").write_text("", encoding="utf-8")

            result = create_batch(root, "camera-batch", ["batch-create-bad"])

            self.assertEqual(result["batch_id"], "camera-batch")
            self.assertEqual(result["phase_counts"]["unreadable"], 1)
            self.assertEqual(result["runs"][0]["next_action"], "repair_workflow")
            self.assertIn("error", result["runs"][0])

    def test_list_batches_returns_lightweight_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="batch-run-a")
            create_batch(root, "camera-batch", ["batch-run-a"], title="Camera smoke suite")

            result = list_batches(root)

            self.assertEqual(result["total"], 1)
            self.assertEqual(result["batches"][0]["batch_id"], "camera-batch")
            self.assertEqual(result["batches"][0]["total_runs"], 1)
            self.assertNotIn("runs", result["batches"][0])

    def test_cli_batch_commands_output_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="batch-run-a")

            from tools.leaf_author.__main__ import main

            create_output = StringIO()
            with redirect_stdout(create_output):
                create_exit = main(
                    [
                        "create-batch",
                        "camera-batch",
                        "--root",
                        str(root),
                        "--title",
                        "Camera smoke suite",
                        "--run-id",
                        "batch-run-a",
                    ]
                )
            create_payload = json.loads(create_output.getvalue())

            inspect_output = StringIO()
            with redirect_stdout(inspect_output):
                inspect_exit = main(["inspect-batch", "camera-batch", "--root", str(root)])
            inspect_payload = json.loads(inspect_output.getvalue())

            list_output = StringIO()
            with redirect_stdout(list_output):
                list_exit = main(["list-batches", "--root", str(root)])
            list_payload = json.loads(list_output.getvalue())

            self.assertEqual(create_exit, 0)
            self.assertEqual(inspect_exit, 0)
            self.assertEqual(list_exit, 0)
            self.assertEqual(create_payload["batch_id"], "camera-batch")
            self.assertEqual(inspect_payload["runs"][0]["run_id"], "batch-run-a")
            self.assertEqual(list_payload["batches"][0]["batch_id"], "camera-batch")

    def test_resume_batch_auto_safe_advances_only_safe_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="batch-run-wait")
            start_new_case(root, "camera", "打开相机；切拍照模式；点击拍照", run_id="batch-run-safe")
            confirm_plan(root, "batch-run-safe")
            create_batch(root, "camera-batch", ["batch-run-wait", "batch-run-safe"])

            result = resume_batch(root, "camera-batch", auto_safe=True)

            self.assertEqual(result["batch_id"], "camera-batch")
            self.assertEqual(result["auto_safe"], True)
            self.assertEqual(result["summary"]["advanced"], 1)
            self.assertEqual(result["summary"]["waiting_for_confirmation"], 1)
            self.assertEqual(result["runs"][0]["run_id"], "batch-run-wait")
            self.assertEqual(result["runs"][0]["auto_advanced"], False)
            self.assertEqual(result["runs"][1]["run_id"], "batch-run-safe")
            self.assertEqual(result["runs"][1]["auto_advanced"], True)
            self.assertEqual(result["runs"][1]["current_phase"], "complete")

    def test_resume_batch_returns_single_run_focus_plan_for_agent_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="batch-run-wait")
            start_new_case(root, "camera", "打开相机；切拍照模式；点击拍照", run_id="batch-run-safe")
            confirm_plan(root, "batch-run-safe")
            create_batch(root, "camera-batch", ["batch-run-wait", "batch-run-safe"])

            result = resume_batch(root, "camera-batch", auto_safe=True)

            self.assertEqual(result["focus_plan"]["attention_boundary"], "one_active_run")
            self.assertEqual(result["focus_plan"]["selected_run_id"], "batch-run-wait")
            self.assertEqual(result["focus_plan"]["selection_reason"], "requires_user_confirmation")
            self.assertEqual(result["focus_plan"]["agent_owner"], "leaf-test-author")
            self.assertEqual(result["focus_plan"]["agent_mode"], "orchestrator")
            self.assertEqual(result["focus_plan"]["handoff_required"], False)
            self.assertEqual(result["focus_plan"]["required_inputs"], ["run_id", "workflow", "decision_contract"])
            self.assertEqual(result["focus_plan"]["subagent_boundary"], "workflow_orchestration")
            self.assertEqual(result["focus_plan"]["context_slice"], ["workflow", "plan"])
            self.assertEqual(result["focus_plan"]["allowed_artifacts"], ["workflow", "plan", "device_probe"])
            self.assertEqual(result["focus_plan"]["target_policy"]["scope"], "system_app_only")
            self.assertEqual(result["focus_plan"]["user_loop"]["position"], "approve_plan")
            self.assertEqual(result["focus_plan"]["user_loop"]["required_input"], "confirm or revise plan")
            self.assertEqual(result["focus_plan"]["safe_to_auto_continue"], False)
            self.assertEqual(result["focus_plan"]["action_route"]["phase"], "plan")
            self.assertEqual(result["focus_plan"]["action_route"]["agent_owner"], "leaf-test-author")
            self.assertEqual(result["focus_plan"]["action_route"]["user_checkpoint"], "first_plan_confirmation")
            self.assertEqual(result["focus_plan"]["action_route"]["command"], "python3 -m tools.leaf_author report-run <run_id>")

    def test_resume_batch_isolates_unreadable_run_and_continues_safe_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "坏 workflow", run_id="batch-resume-bad")
            start_new_case(root, "camera", "打开相机；切拍照模式；点击拍照", run_id="batch-resume-safe")
            confirm_plan(root, "batch-resume-safe")
            create_batch(root, "camera-batch", ["batch-resume-bad", "batch-resume-safe"])
            (root / ".leaf" / "runs" / "batch-resume-bad" / "workflow.json").write_text("", encoding="utf-8")

            result = resume_batch(root, "camera-batch", auto_safe=True)

            self.assertEqual(result["summary"]["failed"], 1)
            self.assertEqual(result["summary"]["advanced"], 1)
            bad = [run for run in result["runs"] if run["run_id"] == "batch-resume-bad"][0]
            safe = [run for run in result["runs"] if run["run_id"] == "batch-resume-safe"][0]
            self.assertEqual(bad["status"], "failed")
            self.assertEqual(bad["current_phase"], "unreadable")
            self.assertEqual(bad["next_action"], "repair_workflow")
            self.assertEqual(bad["auto_advanced"], False)
            self.assertIn("error", bad)
            self.assertEqual(safe["status"], "complete")
            self.assertEqual(safe["auto_advanced"], True)
            self.assertEqual(result["focus_plan"]["selected_run_id"], "batch-resume-bad")
            self.assertEqual(result["focus_plan"]["selection_reason"], "run_failed_or_unreadable")
            self.assertEqual(result["focus_plan"]["attention_boundary"], "one_active_run")
            self.assertEqual(result["focus_plan"]["agent_mode"], "orchestrator")
            self.assertEqual(result["focus_plan"]["handoff_required"], False)
            self.assertEqual(result["focus_plan"]["context_slice"], ["workflow"])
            self.assertIn("test hap", result["focus_plan"]["target_policy"]["forbidden_terms"])
            self.assertEqual(result["focus_plan"]["user_loop"]["position"], "manual_triage")

    def test_resume_batch_includes_lightweight_real_device_preflight_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="batch-real-device")
            run_dir = root / ".leaf" / "runs" / "batch-real-device"
            preflight_path = run_dir / "real_device_preflight.json"
            preflight_path.write_text(
                json.dumps(
                    {
                        "runtime_mode": "direct_smoke",
                        "status": "ready",
                        "risk_level": "read_only_probe",
                        "mutates_device_state": False,
                        "approval_status": "not_required",
                        "input_status": "ready",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            workflow_path = run_dir / "workflow.json"
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
            workflow["current_phase"] = "complete"
            workflow["confirmed_plan"] = True
            workflow["artifacts"]["real_device_preflight"] = ".leaf/runs/batch-real-device/real_device_preflight.json"
            workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            create_batch(root, "camera-batch", ["batch-real-device"])

            result = resume_batch(root, "camera-batch", auto_safe=True)

            self.assertEqual(result["runs"][0]["status"], "complete")
            self.assertEqual(result["runs"][0]["real_device_preflight"]["runtime_mode"], "direct_smoke")
            self.assertEqual(result["runs"][0]["real_device_preflight"]["status"], "ready")
            self.assertEqual(result["runs"][0]["real_device_preflight"]["approval_status"], "not_required")

    def test_cli_resume_batch_auto_safe_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="batch-run-safe")
            confirm_plan(root, "batch-run-safe")
            create_batch(root, "camera-batch", ["batch-run-safe"])

            from tools.leaf_author.__main__ import main

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["resume-batch", "camera-batch", "--root", str(root), "--auto-safe"])
            payload = json.loads(output.getvalue())

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["summary"]["advanced"], 1)
            self.assertEqual(payload["runs"][0]["current_phase"], "complete")


if __name__ == "__main__":
    unittest.main()
