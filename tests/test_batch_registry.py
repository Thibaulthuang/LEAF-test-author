import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.leaf_author.authoring import confirm_plan, start_new_case
from tools.leaf_author.batch_registry import create_batch, inspect_batch, list_batches


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


if __name__ == "__main__":
    unittest.main()
