import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.leaf_author.authoring import start_new_case
from tools.leaf_author.workflow_diagnostics import inspect_workflow_state


class WorkflowDiagnosticsTests(unittest.TestCase):
    def test_inspect_workflow_state_passes_for_readable_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机", run_id="diag-good")

            result = inspect_workflow_state(root, "diag-good")

            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["run_id"], "diag-good")
            self.assertEqual(result["current_phase"], "plan")
            self.assertTrue(result["checks"]["exists"])
            self.assertTrue(result["checks"]["json_parseable"])
            self.assertEqual(result["diagnostics_path"], ".leaf/runs/diag-good/workflow_diagnostics.json")
            self.assertTrue((root / result["diagnostics_path"]).is_file())

    def test_inspect_workflow_state_reports_unreadable_empty_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "坏 workflow", run_id="diag-bad")
            workflow_path = root / ".leaf" / "runs" / "diag-bad" / "workflow.json"
            workflow_path.write_text("", encoding="utf-8")

            result = inspect_workflow_state(root, "diag-bad")

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["next_action"], "repair_workflow")
            self.assertEqual(result["workflow_path"], ".leaf/runs/diag-bad/workflow.json")
            self.assertFalse(result["checks"]["non_empty"])
            self.assertFalse(result["checks"]["json_parseable"])
            self.assertIn("error", result)
            self.assertEqual(workflow_path.read_text(encoding="utf-8"), "")
            self.assertTrue((root / result["diagnostics_path"]).is_file())

    def test_cli_workflow_diagnostics_outputs_json_and_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机", run_id="diag-cli")

            from tools.leaf_author.__main__ import main

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["workflow-diagnostics", "diag-cli", "--root", str(root)])

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "passed")


if __name__ == "__main__":
    unittest.main()
