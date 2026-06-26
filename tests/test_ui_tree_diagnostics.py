import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.leaf_author.runtime.evidence import write_ui_snapshot
from tools.leaf_author.ui_tree_diagnostics import inspect_ui_tree
from tools.leaf_author.workflow import create_workflow, load_workflow


class UiTreeDiagnosticsTests(unittest.TestCase):
    def test_inspect_ui_tree_summarizes_run_snapshots_and_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run_with_ui_snapshots(root)

            result = inspect_ui_tree(root, "ui-diag", text="拍照", clickable=True)

            self.assertEqual(result["manifest_kind"], "leaf_ui_tree_diagnostics")
            self.assertEqual(result["run_id"], "ui-diag")
            self.assertEqual(result["snapshot_count"], 1)
            self.assertEqual(result["snapshots"][0]["phase"], "after_launch")
            self.assertEqual(result["snapshots"][0]["foreground"]["bundle"], "com.huawei.hmos.camera")
            self.assertEqual(result["snapshots"][0]["node_count"], 3)
            self.assertEqual(result["snapshots"][0]["candidate_count"], 2)
            candidate_texts = {candidate["text"] for candidate in result["snapshots"][0]["candidates"]}
            self.assertIn("拍照", candidate_texts)
            self.assertTrue(result["snapshots"][0]["raw_path"].endswith(".raw.json"))
            self.assertTrue(result["snapshots"][0]["index_path"].endswith(".index.json"))
            self.assertEqual(result["artifact"], ".leaf/runs/ui-diag/ui_tree_diagnostics.json")
            self.assertTrue((root / result["artifact"]).is_file())
            workflow = load_workflow(root, "ui-diag")
            self.assertEqual(workflow["artifacts"]["ui_tree_diagnostics"], ".leaf/runs/ui-diag/ui_tree_diagnostics.json")

    def test_inspect_ui_tree_records_gui_subagent_handoff_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run_with_ui_snapshots(root)

            result = inspect_ui_tree(root, "ui-diag", text="拍照", clickable=True)

            self.assertEqual(result["agent_owner"], "leaf-gui-agent")
            self.assertEqual(result["agent_mode"], "focused_subagent")
            self.assertEqual(result["handoff"]["handoff_required"], True)
            self.assertEqual(result["handoff"]["subagent_boundary"], "read_only_gui_context")
            self.assertEqual(result["handoff"]["attention_boundary"], "one_active_run")
            self.assertEqual(result["handoff"]["artifact_loading"], "on_demand")
            self.assertEqual(result["handoff"]["context_slice"], ["workflow", "runtime_evidence", "ui_tree"])
            self.assertEqual(result["handoff"]["allowed_artifacts"], ["camera_direct_smoke"])
            self.assertEqual(result["handoff"]["specific_question"], "find ui tree candidates")
            self.assertEqual(result["user_loop"]["position"], "observe_gui_context")
            self.assertEqual(result["user_loop"]["required_input"], "")
            self.assertEqual(result["target_policy"]["scope"], "system_app_only")

    def test_inspect_ui_tree_can_skip_artifact_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run_with_ui_snapshots(root)

            result = inspect_ui_tree(root, "ui-diag", write_artifact=False)

            self.assertNotIn("artifact", result)
            self.assertFalse((root / ".leaf" / "runs" / "ui-diag" / "ui_tree_diagnostics.json").exists())

    def test_inspect_ui_tree_filters_phase_and_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run_with_ui_snapshots(root)

            matched = inspect_ui_tree(root, "ui-diag", phase="after_launch", action_id="camera_direct")
            missing = inspect_ui_tree(root, "ui-diag", phase="before_capture")

            self.assertEqual(matched["snapshot_count"], 1)
            self.assertEqual(missing["snapshot_count"], 0)

    def test_cli_inspect_ui_tree_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run_with_ui_snapshots(root)

            from tools.leaf_author.__main__ import main

            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["inspect-ui-tree", "ui-diag", "--root", str(root), "--id", "shutter"])

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["snapshot_count"], 1)
            self.assertEqual(payload["snapshots"][0]["candidates"][0]["id"], "shutter")

    def test_inspect_ui_tree_summarizes_adjacent_snapshot_diffs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run_with_ui_snapshots(root, include_after=True)

            result = inspect_ui_tree(root, "ui-diag")

            self.assertEqual(result["snapshot_count"], 2)
            self.assertEqual(result["diff_count"], 1)
            self.assertEqual(result["diffs"][0]["from_phase"], "after_launch")
            self.assertEqual(result["diffs"][0]["to_phase"], "after_click")
            self.assertEqual(result["diffs"][0]["node_count_delta"], 1)
            self.assertIn("done", result["diffs"][0]["added_node_ids"])

    def test_inspect_ui_tree_can_disable_diffs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_run_with_ui_snapshots(root, include_after=True)

            result = inspect_ui_tree(root, "ui-diag", include_diffs=False)

            self.assertNotIn("diffs", result)
            self.assertEqual(result["diff_count"], 0)


def _write_run_with_ui_snapshots(root: Path, include_after: bool = False) -> None:
    create_workflow(root, "camera", "打开相机", run_id="ui-diag")
    raw = json.dumps(
        {
            "attributes": {"bundleName": "com.huawei.hmos.camera", "abilityName": "com.huawei.hmos.camera.MainAbility"},
            "children": [
                {"attributes": {"id": "shutter", "type": "Button", "clickable": "true", "bounds": "[0,0][10,10]"}, "children": []},
                {"attributes": {"id": "label", "text": "拍照", "clickable": "false", "bounds": "[20,0][50,10]"}, "children": []},
            ],
        },
        ensure_ascii=False,
    )
    snapshot = write_ui_snapshot(root, "ui-diag", phase="after_launch", action_id="camera_direct", raw_layout=raw)
    snapshots = [snapshot]
    if include_after:
        after_raw = json.dumps(
            {
                "attributes": {"bundleName": "com.huawei.hmos.camera", "abilityName": "com.huawei.hmos.camera.MainAbility"},
                "children": [
                    {"attributes": {"id": "shutter", "type": "Button", "clickable": "true", "bounds": "[0,0][10,10]"}, "children": []},
                    {"attributes": {"id": "label", "text": "拍照", "clickable": "false", "bounds": "[20,0][50,10]"}, "children": []},
                    {"attributes": {"id": "done", "text": "完成", "clickable": "true", "bounds": "[60,0][90,10]"}, "children": []},
                ],
            },
            ensure_ascii=False,
        )
        snapshots.append(write_ui_snapshot(root, "ui-diag", phase="after_click", action_id="camera_tap", raw_layout=after_raw))
    run_dir = root / ".leaf" / "runs" / "ui-diag"
    artifact = run_dir / "camera_direct_smoke.json"
    artifact.write_text(
        json.dumps(
            {
                "status": "complete",
                "quality_gate": "CAMERA_DIRECT_SMOKE_PASS",
                "evidence": {
                    "layout_verified": True,
                    "bundle_verified": True,
                    "ability_verified": True,
                    "ui_snapshot_refs": [
                        {
                            "phase": item["phase"],
                            "action_id": item["action_id"],
                            "raw_path": item["raw_path"],
                            "index_path": item["index_path"],
                            "foreground": item["foreground"],
                            "node_count": item["node_count"],
                            "clickable_count": item["clickable_count"],
                        }
                        for item in snapshots
                    ],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    workflow_path = run_dir / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["artifacts"]["camera_direct_smoke"] = ".leaf/runs/ui-diag/camera_direct_smoke.json"
    workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
