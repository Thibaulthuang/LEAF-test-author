from __future__ import annotations

from pathlib import Path

from tools.leaf_author.device_probe import HdcProbe, ProbeCommandResult, ProbeRunner
from tools.leaf_author.runtime.evidence import write_ui_snapshot


class HdcClient:
    def __init__(self, serial: str, runner: ProbeRunner | None = None, hdc_path: str = "hdc"):
        self.serial = serial
        self.hdc_path = hdc_path
        self.runner = runner or HdcProbe._run_subprocess

    def shell(self, command: list[str], timeout_s: int = 10) -> dict[str, object]:
        return self.run([self.hdc_path, "-t", self.serial, "shell", *command], timeout_s=timeout_s)

    def run(self, args: list[str], timeout_s: int = 10) -> dict[str, object]:
        result = self.runner(args, timeout_s)
        return normalize_result(args, result)

    def dump_layout(self, timeout_s: int = 10) -> dict[str, object]:
        dump = self.shell(["uitest", "dumpLayout"], timeout_s=timeout_s)
        layout_path = layout_path_from_text(command_text(dump))
        layout_file = self.shell(["cat", layout_path], timeout_s=timeout_s) if layout_path else None
        layout = layout_file if layout_file and command_succeeded(layout_file) else dump
        return {
            "path": layout_path,
            "dump": dump,
            "layout": layout,
            "raw_layout": command_text(layout),
        }

    def hilog(self, timeout_s: int = 10) -> dict[str, object]:
        return self.shell(["hilog", "-x"], timeout_s=timeout_s)

    def click(self, x: int, y: int, timeout_s: int = 10) -> dict[str, object]:
        return self.shell(["uitest", "uiInput", "click", str(x), str(y)], timeout_s=timeout_s)

    def start_ability(self, bundle: str, ability: str, module: str | None = None, timeout_s: int = 30) -> dict[str, object]:
        command = ["aa", "start", "-a", ability, "-b", bundle]
        if module:
            command.extend(["-m", module])
        return self.shell(command, timeout_s=timeout_s)

    def list_files(self, path: str, maxdepth: int = 3, timeout_s: int = 10) -> list[str]:
        result = self.shell(["find", path, "-maxdepth", str(maxdepth), "-type", "f"], timeout_s=timeout_s)
        if not command_succeeded(result):
            return []
        return sorted(line.strip() for line in command_text(result).splitlines() if line.strip())


class DeviceSession:
    def __init__(self, root: Path, run_id: str, serial: str, runner: ProbeRunner | None = None, hdc_path: str = "hdc"):
        self.root = root
        self.run_id = run_id
        self.serial = serial
        self.client = HdcClient(serial=serial, runner=runner, hdc_path=hdc_path)

    def capture_ui_snapshot(self, phase: str, action_id: str) -> dict[str, object]:
        layout = self.client.dump_layout()
        snapshot = write_ui_snapshot(self.root, self.run_id, phase=phase, action_id=action_id, raw_layout=str(layout["raw_layout"]))
        return {**layout, "snapshot": snapshot}


def normalize_result(args: list[str], result: ProbeCommandResult) -> dict[str, object]:
    return {
        "args": args,
        "exit_code": result.exit_code,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def command_text(result: dict[str, object]) -> str:
    return str(result.get("stdout") or result.get("stderr") or "")


def command_succeeded(result: dict[str, object]) -> bool:
    if result.get("exit_code") != 0:
        return False
    text = command_text(result).lower()
    failure_markers = ("failed", "error code", "not connect to server", "connect server failed")
    return not any(marker in text for marker in failure_markers)


def layout_path_from_text(text: str) -> str | None:
    marker = "DumpLayout saved to:"
    if marker not in text:
        return None
    return text.split(marker, 1)[1].strip().splitlines()[0].strip() or None
