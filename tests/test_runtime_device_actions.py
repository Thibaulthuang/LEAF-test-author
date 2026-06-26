import tempfile
import unittest
from pathlib import Path

from tools.leaf_author.device_probe import ProbeCommandResult
from tools.leaf_author.runtime.actions import ActionRunner
from tools.leaf_author.runtime.device import DeviceSession, HdcClient, command_succeeded, command_text


class RuntimeDeviceActionTests(unittest.TestCase):
    def test_hdc_client_normalizes_shell_command_results(self):
        calls = []

        def runner(args, timeout_s):
            calls.append((args, timeout_s))
            return ProbeCommandResult(0, "ok\n", "")

        client = HdcClient(serial="SERIAL123", runner=runner, hdc_path="/sdk/hdc")

        result = client.shell(["param", "get", "const.product.model"], timeout_s=7)

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "ok")
        self.assertEqual(calls[0], (["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"], 7))
        self.assertTrue(command_succeeded(result))
        self.assertEqual(command_text(result), "ok")

    def test_hdc_client_dump_layout_reads_dump_file_when_reported(self):
        layout_path = "/data/local/tmp/layout_123.json"
        calls = []

        def runner(args, timeout_s):
            calls.append(args)
            if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
            if args == ["hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                return ProbeCommandResult(0, '{"attributes":{"bundleName":"camera"},"children":[]}\n', "")
            return ProbeCommandResult(1, "", f"unexpected {args}")

        result = HdcClient(serial="SERIAL123", runner=runner).dump_layout()

        self.assertEqual(result["path"], layout_path)
        self.assertIn("bundleName", result["raw_layout"])
        self.assertEqual(result["layout"]["exit_code"], 0)
        self.assertEqual(len(calls), 2)

    def test_device_session_captures_ui_snapshot_with_run_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def runner(args, timeout_s):
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, '{"attributes":{"bundleName":"camera"},"children":[]}\n', "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            session = DeviceSession(root=root, run_id="run-device", serial="SERIAL123", runner=runner)

            result = session.capture_ui_snapshot(phase="before_action", action_id="launch")

            self.assertEqual(result["snapshot"]["kind"], "ui_snapshot")
            self.assertEqual(result["snapshot"]["foreground"]["bundle"], "camera")
            self.assertTrue((root / result["snapshot"]["index_path"]).is_file())
            self.assertIn("bundleName", result["raw_layout"])

    def test_action_runner_executes_launch_and_click_actions(self):
        calls = []

        def runner(args, timeout_s):
            calls.append((args, timeout_s))
            return ProbeCommandResult(0, "ok\n", "")

        session = DeviceSession(root=Path("."), run_id="run-action", serial="SERIAL123", runner=runner)
        action_runner = ActionRunner(session)

        launch = action_runner.execute(
            {
                "id": "launch_camera",
                "action": "system_app.launch",
                "params": {
                    "bundle": "com.huawei.hmos.camera",
                    "ability": "com.huawei.hmos.camera.MainAbility",
                    "module": "phone",
                },
            }
        )
        click = action_runner.execute({"id": "tap", "action": "ui.click", "params": {"x": 10, "y": 20}})

        self.assertEqual(launch["status"], "passed")
        self.assertEqual(click["status"], "passed")
        self.assertEqual(calls[0][0][-9:], ["shell", "aa", "start", "-a", "com.huawei.hmos.camera.MainAbility", "-b", "com.huawei.hmos.camera", "-m", "phone"])
        self.assertEqual(calls[1][0][-5:], ["uitest", "uiInput", "click", "10", "20"])

    def test_action_runner_can_attach_before_after_ui_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dump_count = 0

            def runner(args, timeout_s):
                nonlocal dump_count
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    dump_count += 1
                    if dump_count == 1:
                        return ProbeCommandResult(0, '{"attributes":{"bundleName":"camera"},"children":[]}\n', "")
                    return ProbeCommandResult(0, '{"attributes":{"bundleName":"camera"},"children":[{"attributes":{"id":"done"}}]}\n', "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "uitest", "uiInput", "click", "10", "20"]:
                    return ProbeCommandResult(0, "click ok\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            session = DeviceSession(root=root, run_id="run-evidence", serial="SERIAL123", runner=runner)
            action_runner = ActionRunner(session)

            result = action_runner.execute(
                {
                    "id": "tap_done",
                    "action": "ui.click",
                    "params": {"x": 10, "y": 20},
                    "capture_ui": {"before": True, "after": True},
                }
            )

            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["ui_snapshots"]["before"]["kind"], "ui_snapshot")
            self.assertEqual(result["ui_snapshots"]["after"]["kind"], "ui_snapshot")
            self.assertTrue((root / result["ui_snapshots"]["before"]["index_path"]).is_file())
            self.assertEqual(result["ui_diff"]["node_count_delta"], 1)
            self.assertIn("done", result["ui_diff"]["added_node_ids"])


if __name__ == "__main__":
    unittest.main()
