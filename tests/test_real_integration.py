import json
import os
import tempfile
import unittest
from pathlib import Path

from tools.leaf_author.authoring import advance_run, confirm_plan, start_new_case
from tools.leaf_author.device_probe import HdcProbe
from tools.leaf_author.workflow import load_workflow


class RealIntegrationTests(unittest.TestCase):
    def test_real_pytest_and_real_hdc_complete_safe_local_flow(self):
        serial = os.environ.get("LEAF_HDC_SERIAL")
        if not serial:
            self.skipTest("set LEAF_HDC_SERIAL to run real-device integration")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            device = HdcProbe().probe(serial=serial)
            self.assertEqual(device["status"], "connected", device)

            start = start_new_case(root, "camera", "打开相机；点击拍照", run_id="real-integration", probe_device=True, serial=serial)
            self.assertIsNone(start["pytest_path"])
            self.assertEqual(json.loads((root / ".leaf" / "runs" / "real-integration" / "device_probe.json").read_text(encoding="utf-8"))["status"], "connected")

            confirm = confirm_plan(root, "real-integration")
            self.assertTrue(Path(confirm["pytest_path"]).exists())

            result = advance_run(root, "real-integration", serial=serial)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["next_action"], "complete")

            run_dir = root / ".leaf" / "runs" / "real-integration"
            pytest_result = json.loads((run_dir / "pytest_result.json").read_text(encoding="utf-8"))
            self.assertEqual(pytest_result["runner"], "pytest")
            self.assertEqual(pytest_result["status"], "draft_passed")
            self.assertEqual(pytest_result["quality_gate"], "DRAFT_STATIC_PASS")

            gui_context = json.loads((run_dir / "gui_context.json").read_text(encoding="utf-8"))
            self.assertEqual(gui_context["status"], "collected")
            self.assertEqual(gui_context["device"]["status"], "connected")

            workflow = load_workflow(root, "real-integration")
            self.assertEqual(workflow["current_phase"], "complete")
            self.assertEqual(workflow["confirmed_plan"], True)


if __name__ == "__main__":
    unittest.main()
