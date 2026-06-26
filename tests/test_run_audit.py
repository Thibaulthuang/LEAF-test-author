import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tools.leaf_author.authoring import advance_run, confirm_plan, start_new_case
from tools.leaf_author.batch_registry import create_batch
from tools.leaf_author.device_probe import ProbeCommandResult, select_real_device
from tools.leaf_author.reports import report_run
from tools.leaf_author.run_audit import audit_batch, audit_run
from tools.leaf_author.workflow_diagnostics import inspect_workflow_state


class RunAuditTests(unittest.TestCase):
    def test_audit_run_passes_completed_real_device_direct_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _complete_direct_smoke(root, "audit-pass")

            result = audit_run(root, "audit-pass")

            self.assertEqual(result["manifest_kind"], "leaf_run_audit")
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["latest_quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")
            self.assertIn("real_device_preflight", result["evidence"])
            self.assertEqual(result["evidence"]["context_manifest"], ".leaf/runs/audit-pass/context_manifest.json")
            self.assertEqual(result["audit_path"], ".leaf/runs/audit-pass/run_audit.json")
            self.assertTrue((root / result["audit_path"]).is_file())
            workflow = json.loads((root / ".leaf" / "runs" / "audit-pass" / "workflow.json").read_text(encoding="utf-8"))
            self.assertEqual(workflow["artifacts"]["run_audit"], ".leaf/runs/audit-pass/run_audit.json")
            self.assertEqual(report_run(root, "audit-pass")["evidence"]["run_audit"], ".leaf/runs/audit-pass/run_audit.json")
            passed_checks = [check["name"] for check in result["checks"] if check["passed"]]
            self.assertIn("context_manifest_ready", passed_checks)
            self.assertIn("handoff_ready", passed_checks)
            self.assertIn("user_loop_ready", passed_checks)
            self.assertTrue(all(check["passed"] for check in result["checks"]))

    def test_audit_run_includes_workflow_diagnostics_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _complete_direct_smoke(root, "audit-diag")
            inspect_workflow_state(root, "audit-diag")

            result = audit_run(root, "audit-diag")

            self.assertEqual(result["evidence"]["workflow_diagnostics"], ".leaf/runs/audit-diag/workflow_diagnostics.json")
            passed_checks = [check["name"] for check in result["checks"] if check["passed"]]
            self.assertIn("workflow_diagnostics_ready", passed_checks)

    def test_audit_run_checks_device_selection_matches_preflight_serial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="audit-selection")
            confirm_plan(root, "audit-selection")
            layout_path = "/data/local/tmp/layout_123.json"

            def runner(args, timeout_s):
                if args == ["/sdk/hdc", "list", "targets"]:
                    return ProbeCommandResult(0, "SERIAL123\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "aa", "start", "-a", "com.huawei.hmos.camera.MainAbility", "-b", "com.huawei.hmos.camera", "-m", "phone"]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    return ProbeCommandResult(0, '{"attributes":{"bundleName":"com.huawei.hmos.camera","abilityName":"com.huawei.hmos.camera.MainAbility","text":"相机"},"children":[]}\n', "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            select_real_device(root, "audit-selection", hdc_runner=runner, hdc_path="/sdk/hdc")
            advance_run(root, "audit-selection", hdc_runner=runner, run_real=True, runtime_mode="direct_smoke", hdc_path="/sdk/hdc")

            result = audit_run(root, "audit-selection")

            self.assertEqual(result["evidence"]["device_selection"], ".leaf/runs/audit-selection/device_selection.json")
            self.assertEqual(result["evidence"]["real_device_input"], ".leaf/runs/audit-selection/real_device_input.json")
            passed_checks = [check["name"] for check in result["checks"] if check["passed"]]
            self.assertIn("device_selection_ready", passed_checks)
            self.assertIn("device_selection_matches_preflight", passed_checks)
            self.assertIn("real_device_input_artifact_ready", passed_checks)
            self.assertIn("real_device_input_matches_preflight", passed_checks)
            self.assertIn("real_device_input_source_matches_selection", passed_checks)
            self.assertIn("real_device_preflight_source_matches_selection", passed_checks)
            self.assertEqual(result["real_device_trace"]["serial"], "SERIAL123")
            self.assertEqual(result["real_device_trace"]["serial_source"], "device_selection")
            self.assertEqual(result["real_device_trace"]["runtime_mode"], "direct_smoke")
            self.assertEqual(result["real_device_trace"]["latest_quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")
            self.assertEqual(result["real_device_trace"]["artifacts"]["device_selection"], ".leaf/runs/audit-selection/device_selection.json")
            self.assertEqual(result["real_device_trace"]["artifacts"]["real_device_input"], ".leaf/runs/audit-selection/real_device_input.json")
            self.assertEqual(result["real_device_trace"]["artifacts"]["real_device_preflight"], ".leaf/runs/audit-selection/real_device_preflight.json")

    def test_audit_run_fails_incomplete_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="audit-incomplete")

            result = audit_run(root, "audit-incomplete")

            self.assertEqual(result["status"], "failed")
            failed_checks = [check["name"] for check in result["checks"] if not check["passed"]]
            self.assertIn("workflow_complete", failed_checks)
            self.assertIn("real_device_preflight_ready", failed_checks)

    def test_audit_run_reports_unreadable_workflow_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "坏 workflow", run_id="audit-unreadable")
            workflow_path = root / ".leaf" / "runs" / "audit-unreadable" / "workflow.json"
            workflow_path.write_text("", encoding="utf-8")

            result = audit_run(root, "audit-unreadable")

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["current_phase"], "unreadable")
            self.assertEqual(result["next_action"], "repair_workflow")
            self.assertEqual(result["audit_path"], ".leaf/runs/audit-unreadable/run_audit.json")
            self.assertTrue((root / result["audit_path"]).is_file())
            self.assertEqual(workflow_path.read_text(encoding="utf-8"), "")
            failed_checks = [check["name"] for check in result["checks"] if not check["passed"]]
            self.assertIn("workflow_complete", failed_checks)
            self.assertIn("workflow_readable", failed_checks)

    def test_audit_run_fails_when_context_manifest_handoff_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _complete_direct_smoke(root, "audit-no-handoff")
            manifest_path = root / ".leaf" / "runs" / "audit-no-handoff" / "context_manifest.json"
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload.pop("handoff", None)
            manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            with patch("tools.leaf_author.run_audit.report_run", return_value=_completed_report_for_corrupt_manifest()):
                result = audit_run(root, "audit-no-handoff")

            self.assertEqual(result["status"], "failed")
            failed_checks = [check["name"] for check in result["checks"] if not check["passed"]]
            self.assertIn("handoff_ready", failed_checks)

    def test_cli_audit_run_outputs_json_and_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _complete_direct_smoke(root, "audit-cli")

            from tools.leaf_author.__main__ import main

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["audit-run", "audit-cli", "--root", str(root)])

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "passed")

    def test_audit_batch_summarizes_passed_and_failed_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _complete_direct_smoke(root, "audit-batch-pass")
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="audit-batch-fail")
            create_batch(root, "audit-batch", ["audit-batch-pass", "audit-batch-fail"])

            result = audit_batch(root, "audit-batch")

            self.assertEqual(result["manifest_kind"], "leaf_batch_audit")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["summary"]["total_runs"], 2)
            self.assertEqual(result["summary"]["passed"], 1)
            self.assertEqual(result["summary"]["failed"], 1)
            self.assertEqual(result["audit_path"], ".leaf/batches/audit-batch/batch_audit.json")
            self.assertTrue((root / result["audit_path"]).is_file())
            failed = [run for run in result["runs"] if run["status"] == "failed"][0]
            self.assertIn("workflow_complete", failed["failed_checks"])

    def test_audit_batch_checks_resume_focus_plan_for_incomplete_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _complete_direct_smoke(root, "audit-focus-pass")
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="audit-focus-wait")
            create_batch(root, "audit-focus-batch", ["audit-focus-pass", "audit-focus-wait"])

            result = audit_batch(root, "audit-focus-batch")

            self.assertEqual(result["focus_plan"]["selected_run_id"], "audit-focus-wait")
            self.assertEqual(result["focus_plan"]["attention_boundary"], "one_active_run")
            failed_checks = [check["name"] for check in result["batch_checks"] if not check["passed"]]
            self.assertNotIn("batch_resume_focus_present", failed_checks)
            self.assertNotIn("batch_resume_attention_boundary", failed_checks)
            self.assertNotIn("batch_resume_focus_handoff", failed_checks)

    def test_audit_batch_allows_empty_focus_plan_when_every_run_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _complete_direct_smoke(root, "audit-focus-complete")
            create_batch(root, "audit-focus-complete-batch", ["audit-focus-complete"])

            result = audit_batch(root, "audit-focus-complete-batch")

            self.assertEqual(result["status"], "passed")
            self.assertIsNone(result["focus_plan"])
            passed_checks = [check["name"] for check in result["batch_checks"] if check["passed"]]
            self.assertIn("batch_resume_focus_complete", passed_checks)
            self.assertIn("batch_resume_attention_boundary", passed_checks)

    def test_audit_batch_isolates_unreadable_run_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _complete_direct_smoke(root, "audit-batch-good")
            start_new_case(root, "camera", "坏 workflow", run_id="audit-batch-bad")
            create_batch(root, "audit-batch-isolated", ["audit-batch-good", "audit-batch-bad"])
            workflow_path = root / ".leaf" / "runs" / "audit-batch-bad" / "workflow.json"
            workflow_path.write_text("", encoding="utf-8")

            result = audit_batch(root, "audit-batch-isolated")

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["summary"]["total_runs"], 2)
            self.assertEqual(result["summary"]["passed"], 1)
            self.assertEqual(result["summary"]["failed"], 1)
            bad = [run for run in result["runs"] if run["run_id"] == "audit-batch-bad"][0]
            self.assertEqual(bad["status"], "failed")
            self.assertIn("workflow_readable", bad["failed_checks"])
            self.assertEqual(result["context_policy"]["load_strategy"], "summaries_first_then_audit_one_run")

    def test_cli_audit_batch_outputs_json_and_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _complete_direct_smoke(root, "audit-batch-cli")
            create_batch(root, "audit-batch-cli", ["audit-batch-cli"])

            from tools.leaf_author.__main__ import main

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["audit-batch", "audit-batch-cli", "--root", str(root)])

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "passed")
            self.assertEqual(payload["summary"]["passed"], 1)


def _complete_direct_smoke(root: Path, run_id: str) -> None:
    start_new_case(root, "camera", "打开相机；点击拍照", run_id=run_id)
    confirm_plan(root, run_id)
    layout_path = "/data/local/tmp/layout_123.json"

    def runner(args, timeout_s):
        if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
            return ProbeCommandResult(0, "ohos\n", "")
        if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
            return ProbeCommandResult(0, "26\n", "")
        if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
            return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
        if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "aa", "start", "-a", "com.huawei.hmos.camera.MainAbility", "-b", "com.huawei.hmos.camera", "-m", "phone"]:
            return ProbeCommandResult(0, "start ability successfully\n", "")
        if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
            return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
        if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
            return ProbeCommandResult(0, '{"attributes":{"bundleName":"com.huawei.hmos.camera","abilityName":"com.huawei.hmos.camera.MainAbility","text":"相机"},"children":[]}\n', "")
        if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
            return ProbeCommandResult(0, "camera foreground log\n", "")
        return ProbeCommandResult(1, "", f"unexpected {args}")

    advance_run(root, run_id, hdc_runner=runner, serial="SERIAL123", run_real=True, runtime_mode="direct_smoke", hdc_path="/sdk/hdc")


def _completed_report_for_corrupt_manifest() -> dict[str, object]:
    return {
        "domain": "camera",
        "platform": "openharmony",
        "current_phase": "complete",
        "next_action": "complete",
        "latest_quality_gate": "CAMERA_DIRECT_SMOKE_PASS",
        "safe_to_auto_continue": False,
        "user_action_required": False,
        "decision_contract": {
            "agent_owner": "leaf-test-author",
        },
        "real_device_preflight": {
            "artifact": ".leaf/runs/audit-no-handoff/real_device_preflight.json",
            "status": "ready",
            "input_status": "ready",
            "approval_status": "not_required",
        },
        "evidence": {
            "context_manifest": ".leaf/runs/audit-no-handoff/context_manifest.json",
        },
    }


if __name__ == "__main__":
    unittest.main()
