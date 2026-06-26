import json
import tempfile
import unittest
from pathlib import Path

from tools.leaf_author.runtime.evidence import write_ui_snapshot
from tools.leaf_author.runtime.ui_tree import build_index, diff_indexes, find_candidates, parse_layout


class RuntimeUiTreeTests(unittest.TestCase):
    def test_parse_layout_builds_searchable_index(self):
        layout = json.dumps(
            {
                "attributes": {"bundleName": "com.huawei.hmos.camera", "abilityName": "CameraAbility"},
                "children": [
                    {
                        "attributes": {
                            "id": "COMPONENT_ID_SHUTTER_PHOTO_1",
                            "type": "Button",
                            "text": "",
                            "clickable": "true",
                            "bounds": "[440,1966][640,2166]",
                        },
                        "children": [],
                    },
                    {
                        "attributes": {
                            "id": "COMPONENT_ID_CONTROL_PHOTO_2",
                            "text": "拍照",
                            "clickable": "false",
                            "bounds": "[496,1775][584,1850]",
                        },
                        "children": [],
                    },
                ],
            }
        )

        tree = parse_layout(layout)
        index = build_index(tree)

        self.assertEqual(index["foreground"]["bundle"], "com.huawei.hmos.camera")
        self.assertEqual(index["foreground"]["ability"], "CameraAbility")
        self.assertEqual(index["node_count"], 3)
        self.assertEqual(index["clickable_count"], 1)
        self.assertEqual(index["nodes"][1]["id"], "COMPONENT_ID_SHUTTER_PHOTO_1")
        self.assertEqual(index["nodes"][1]["bounds"], [440, 1966, 640, 2166])
        self.assertEqual(index["nodes"][1]["center"], {"x": 540, "y": 2066})

    def test_find_candidates_scores_selector_matches(self):
        tree = parse_layout(
            json.dumps(
                {
                    "attributes": {},
                    "children": [
                        {"attributes": {"id": "shutter", "text": "", "clickable": "true", "bounds": "[0,0][10,10]"}},
                        {"attributes": {"id": "label", "text": "拍照", "clickable": "false", "bounds": "[20,0][50,10]"}},
                    ],
                }
            )
        )
        index = build_index(tree)

        candidates = find_candidates(index, selectors=[{"id": "missing"}, {"text": "拍照"}, {"clickable": True}])

        self.assertEqual(candidates[0]["id"], "shutter")
        self.assertEqual(candidates[0]["score"], 1)
        self.assertIn("clickable", candidates[0]["matched"])
        self.assertEqual(candidates[1]["id"], "label")
        self.assertIn("text", candidates[1]["matched"])

    def test_diff_indexes_summarizes_foreground_and_node_changes(self):
        before = build_index(parse_layout(json.dumps({"attributes": {"bundleName": "camera"}, "children": []})))
        after = build_index(
            parse_layout(
                json.dumps(
                    {
                        "attributes": {"bundleName": "gallery"},
                        "children": [{"attributes": {"id": "done", "text": "完成", "clickable": "true"}}],
                    }
                )
            )
        )

        diff = diff_indexes(before, after)

        self.assertEqual(diff["foreground_changed"], True)
        self.assertEqual(diff["before_foreground"]["bundle"], "camera")
        self.assertEqual(diff["after_foreground"]["bundle"], "gallery")
        self.assertEqual(diff["node_count_delta"], 1)
        self.assertIn("done", diff["added_node_ids"])

    def test_write_ui_snapshot_persists_raw_layout_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = json.dumps({"attributes": {"bundleName": "camera"}, "children": []})

            result = write_ui_snapshot(root, "run-ui", phase="before_action", action_id="launch", raw_layout=raw)

            raw_path = root / result["raw_path"]
            index_path = root / result["index_path"]
            self.assertTrue(raw_path.is_file())
            self.assertTrue(index_path.is_file())
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["kind"], "ui_snapshot")
            self.assertEqual(payload["phase"], "before_action")
            self.assertEqual(payload["action_id"], "launch")
            self.assertEqual(payload["index"]["foreground"]["bundle"], "camera")


if __name__ == "__main__":
    unittest.main()
