import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.leaf_author.authoring import confirm_plan, start_new_case
from tools.leaf_author.run_registry import inspect_run, list_runs


class RunRegistryTests(unittest.TestCase):
    def test_list_runs_returns_lightweight_summaries_for_multiple_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-a")
            start_new_case(root, "camera", "打开相机；切拍照模式；点击拍照", run_id="run-b")
            confirm_plan(root, "run-b")

            result = list_runs(root)

            self.assertEqual(result["schema_version"], "1.0")
            self.assertEqual(result["total"], 2)
            self.assertEqual([item["run_id"] for item in result["runs"]], ["run-b", "run-a"])
            self.assertEqual(result["runs"][0]["current_phase"], "hypium_draft")
            self.assertEqual(result["runs"][0]["next_action"], "validate_pytest_draft")
            self.assertNotIn("teststep", result["runs"][0])
            self.assertNotIn("artifacts", result["runs"][0])
            self.assertEqual(result["context_policy"]["load_strategy"], "inspect_one_run_at_a_time")

    def test_inspect_run_returns_single_run_context_slice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-inspect")
            confirm_plan(root, "run-inspect")

            result = inspect_run(root, "run-inspect")

            self.assertEqual(result["run_id"], "run-inspect")
            self.assertEqual(result["current_phase"], "hypium_draft")
            self.assertEqual(result["next_action"], "validate_pytest_draft")
            self.assertEqual(result["resume_summary"]["safe_to_auto_continue"], True)
            self.assertIn("workflow", result["artifacts"])
            self.assertIn("plan", result["artifacts"])
            self.assertIn("case", result["artifacts"])
            self.assertEqual(result["context_policy"]["scope"], "single_run")

    def test_cli_list_and_inspect_runs_output_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="run-cli")

            from tools.leaf_author.__main__ import main

            list_output = StringIO()
            with redirect_stdout(list_output):
                list_exit = main(["list-runs", "--root", str(root)])
            list_payload = json.loads(list_output.getvalue())

            inspect_output = StringIO()
            with redirect_stdout(inspect_output):
                inspect_exit = main(["inspect-run", "run-cli", "--root", str(root)])
            inspect_payload = json.loads(inspect_output.getvalue())

            self.assertEqual(list_exit, 0)
            self.assertEqual(inspect_exit, 0)
            self.assertEqual(list_payload["runs"][0]["run_id"], "run-cli")
            self.assertEqual(inspect_payload["run_id"], "run-cli")


if __name__ == "__main__":
    unittest.main()
