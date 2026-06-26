import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.leaf_author.authoring import advance_run, confirm_plan, start_new_case
from tools.leaf_author.batch_registry import create_batch
from tools.leaf_author.reports import report_batch, report_run


class ReportTests(unittest.TestCase):
    def test_report_run_summarizes_phase_quality_gate_and_next_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-run")
            confirm_plan(root, "report-run")
            advance_run(root, "report-run")

            result = report_run(root, "report-run")

            self.assertEqual(result["run_id"], "report-run")
            self.assertEqual(result["current_phase"], "complete")
            self.assertEqual(result["latest_quality_gate"], "DRAFT_STATIC_PASS")
            self.assertEqual(result["user_action_required"], False)
            self.assertEqual(result["next_command"], "")
            self.assertIn("pytest_result", result["evidence"])
            self.assertIn("team_export_manifest", result["evidence"])

    def test_report_run_marks_plan_confirmation_needed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-wait")

            result = report_run(root, "report-wait")

            self.assertEqual(result["current_phase"], "plan")
            self.assertEqual(result["user_action_required"], True)
            self.assertEqual(result["user_checkpoint"], "first_plan_confirmation")
            self.assertIn("confirm", result["operator_message"].lower())

    def test_report_run_uses_domain_runtime_quality_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-runtime")
            confirm_plan(root, "report-runtime")
            run_dir = root / ".leaf" / "runs" / "report-runtime"
            (run_dir / "pytest_result.json").write_text(json.dumps({"quality_gate": "DRAFT_STATIC_PASS"}) + "\n", encoding="utf-8")
            (run_dir / "camera_direct_smoke.json").write_text(json.dumps({"quality_gate": "CAMERA_DIRECT_SMOKE_PASS"}) + "\n", encoding="utf-8")
            workflow = json.loads((run_dir / "workflow.json").read_text(encoding="utf-8"))
            workflow["artifacts"]["pytest_result"] = ".leaf/runs/report-runtime/pytest_result.json"
            workflow["artifacts"]["camera_direct_smoke"] = ".leaf/runs/report-runtime/camera_direct_smoke.json"
            workflow["current_phase"] = "complete"
            (run_dir / "workflow.json").write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            result = report_run(root, "report-runtime")

            self.assertEqual(result["latest_quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")

    def test_report_run_real_device_checkpoint_recommends_runtime_mode_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-real")
            confirm_plan(root, "report-real")
            run_dir = root / ".leaf" / "runs" / "report-real"
            workflow = json.loads((run_dir / "workflow.json").read_text(encoding="utf-8"))
            workflow["current_phase"] = "e2e_ready"
            (run_dir / "workflow.json").write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            result = report_run(root, "report-real")

            self.assertEqual(result["user_checkpoint"], "real_device_confirmation")
            self.assertEqual(
                result["next_command"],
                "python3 -m tools.leaf_author advance report-real --run-real --runtime-mode direct_smoke --serial <serial>",
            )

    def test_report_run_surfaces_real_device_approval_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-approval")
            confirm_plan(root, "report-approval")

            blocked = advance_run(root, "report-approval", run_real=True, runtime_mode="capture_e2e", serial="SERIAL123")
            result = report_run(root, "report-approval")

            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(result["user_checkpoint"], "real_device_confirmation")
            self.assertEqual(result["user_action_required"], True)
            self.assertIn("real_device_approval", result["evidence"])
            self.assertEqual(result["approval_required"]["required_approval_token"], "approve_camera_capture_e2e")
            self.assertIn("--approval-token approve_camera_capture_e2e", result["next_command"])

    def test_report_batch_summarizes_runs_and_next_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-wait")
            start_new_case(root, "camera", "打开相机；切拍照模式；点击拍照", run_id="report-safe")
            confirm_plan(root, "report-safe")
            create_batch(root, "report-batch", ["report-wait", "report-safe"])

            result = report_batch(root, "report-batch")

            self.assertEqual(result["batch_id"], "report-batch")
            self.assertEqual(result["total_runs"], 2)
            self.assertEqual(result["summary"]["waiting_for_user"], 1)
            self.assertEqual(result["summary"]["safe_to_auto_continue"], 1)
            self.assertEqual(result["next_run_focus"]["run_id"], "report-safe")
            self.assertEqual(result["runs"][0]["run_id"], "report-wait")

    def test_cli_report_commands_output_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-cli")
            create_batch(root, "report-batch", ["report-cli"])

            from tools.leaf_author.__main__ import main

            run_output = StringIO()
            with redirect_stdout(run_output):
                run_exit = main(["report-run", "report-cli", "--root", str(root)])
            run_payload = json.loads(run_output.getvalue())

            batch_output = StringIO()
            with redirect_stdout(batch_output):
                batch_exit = main(["report-batch", "report-batch", "--root", str(root)])
            batch_payload = json.loads(batch_output.getvalue())

            self.assertEqual(run_exit, 0)
            self.assertEqual(batch_exit, 0)
            self.assertEqual(run_payload["run_id"], "report-cli")
            self.assertEqual(batch_payload["batch_id"], "report-batch")


if __name__ == "__main__":
    unittest.main()
