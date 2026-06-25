from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProbeCommandResult:
    exit_code: int
    stdout: str
    stderr: str


ProbeRunner = Callable[[list[str], int], ProbeCommandResult]


class HdcProbe:
    def __init__(self, runner: ProbeRunner | None = None, hdc_path: str = "hdc"):
        self.runner = runner or self._run_subprocess
        self.hdc_path = hdc_path
        self._last_error = ""

    def probe(self, serial: str | None = None) -> dict[str, object]:
        target = serial or self._first_target()
        if not target:
            return {
                "status": "unavailable",
                "tool": "hdc",
                "reason": self._last_error or "no hdc target is available",
            }
        return {
            "status": "connected",
            "tool": "hdc",
            "serial": target,
            "model": self._shell_text(target, ["param", "get", "const.product.model"]),
            "os_version": self._shell_text(target, ["param", "get", "const.ohos.apiversion"]),
        }

    def _first_target(self) -> str:
        result = self.runner([self.hdc_path, "list", "targets"], 5)
        transport_error = _hdc_transport_error(result)
        if result.exit_code != 0 or transport_error:
            self._last_error = (result.stderr or result.stdout).strip()
            return ""
        first = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if not first:
            self._last_error = "no hdc target is available"
        return first

    def _shell_text(self, serial: str, command: list[str]) -> str:
        result = self.runner([self.hdc_path, "-t", serial, "shell", *command], 5)
        if result.exit_code != 0 or _hdc_transport_error(result):
            return "unknown"
        return result.stdout.strip() or "unknown"

    @staticmethod
    def _run_subprocess(args: list[str], timeout_s: int) -> ProbeCommandResult:
        try:
            completed = subprocess.run(args, capture_output=True, text=False, timeout=timeout_s, check=False)
        except FileNotFoundError as exc:
            return ProbeCommandResult(127, "", str(exc))
        except subprocess.TimeoutExpired as exc:
            stdout = _decode_bytes(exc.stdout)
            stderr = _decode_bytes(exc.stderr) or f"command timed out after {timeout_s}s"
            return ProbeCommandResult(124, stdout, stderr)
        return ProbeCommandResult(completed.returncode, _decode_bytes(completed.stdout), _decode_bytes(completed.stderr))


def _decode_bytes(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def _hdc_transport_error(result: ProbeCommandResult) -> bool:
    output = f"{result.stdout}\n{result.stderr}".lower()
    return "connect server failed" in output or "not connect to server" in output
