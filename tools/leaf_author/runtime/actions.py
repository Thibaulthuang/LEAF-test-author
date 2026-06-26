from __future__ import annotations

from tools.leaf_author.runtime.device import DeviceSession, command_succeeded
from tools.leaf_author.runtime.ui_tree import diff_indexes


class ActionRunner:
    def __init__(self, session: DeviceSession):
        self.session = session

    def execute(self, action: dict[str, object]) -> dict[str, object]:
        action_type = str(action.get("action", ""))
        action_id = str(action.get("id", action_type or "action"))
        params = action.get("params", {})
        if not isinstance(params, dict):
            params = {}
        capture_ui = action.get("capture_ui", {})
        if not isinstance(capture_ui, dict):
            capture_ui = {}
        before_ui = self.session.capture_ui_snapshot(phase="before", action_id=action_id) if capture_ui.get("before") else None
        if action_type == "system_app.launch":
            result = self.session.client.start_ability(
                bundle=str(params.get("bundle", "")),
                ability=str(params.get("ability", "")),
                module=str(params.get("module") or "") or None,
            )
        elif action_type == "ui.click":
            result = self.session.client.click(x=int(params.get("x", 0)), y=int(params.get("y", 0)))
        elif action_type == "shell":
            command = params.get("command", [])
            if not isinstance(command, list):
                command = []
            result = self.session.client.shell([str(item) for item in command], timeout_s=int(params.get("timeout_s", 10)))
        else:
            return {
                "id": action_id,
                "action": action_type,
                "status": "failed",
                "reason": "UNSUPPORTED_ACTION",
                "result": {"args": [], "exit_code": 1, "stdout": "", "stderr": f"unsupported action: {action_type}"},
            }
        after_ui = self.session.capture_ui_snapshot(phase="after", action_id=action_id) if capture_ui.get("after") else None
        payload = {
            "id": action_id,
            "action": action_type,
            "status": "passed" if command_succeeded(result) else "failed",
            "result": result,
        }
        if before_ui or after_ui:
            snapshots = {}
            if before_ui:
                snapshots["before"] = before_ui["snapshot"]
            if after_ui:
                snapshots["after"] = after_ui["snapshot"]
            payload["ui_snapshots"] = snapshots
        if before_ui and after_ui:
            payload["ui_diff"] = diff_indexes(before_ui["index"], after_ui["index"])
        return payload
