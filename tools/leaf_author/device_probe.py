from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
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

    def select_device(self, serial: str | None = None) -> dict[str, object]:
        targets_result = self.runner([self.hdc_path, "list", "targets"], 5)
        targets = _parse_targets(targets_result.stdout)
        transport_error = _hdc_transport_error(targets_result)
        if targets_result.exit_code != 0 or transport_error:
            reason = (targets_result.stderr or targets_result.stdout).strip()
            return _device_selection_result(
                status="unavailable",
                reason=reason or "hdc list targets failed",
                targets=targets,
                selection_reason="hdc_unavailable",
            )
        requested = serial.strip() if isinstance(serial, str) else ""
        if requested:
            if requested not in targets:
                return _device_selection_result(
                    status="unavailable",
                    reason=f"requested serial is not connected: {requested}",
                    targets=targets,
                    selection_reason="requested_serial_not_connected",
                    serial=requested,
                )
            return _device_selection_result(
                status="selected",
                reason="",
                targets=targets,
                selection_reason="requested_serial",
                serial=requested,
                device=self.probe(serial=requested),
            )
        if not targets:
            return _device_selection_result(
                status="unavailable",
                reason="no hdc target is available",
                targets=[],
                selection_reason="no_connected_targets",
            )
        if len(targets) > 1:
            return _device_selection_result(
                status="needs_user_input",
                reason="multiple hdc targets are connected; provide --serial to select one",
                targets=targets,
                selection_reason="multiple_connected_targets",
            )
        selected = targets[0]
        return _device_selection_result(
            status="selected",
            reason="",
            targets=targets,
            selection_reason="single_connected_target",
            serial=selected,
            device=self.probe(serial=selected),
        )

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


def select_real_device(
    root: Path,
    run_id: str,
    serial: str | None = None,
    hdc_runner: ProbeRunner | None = None,
    hdc_path: str = "hdc",
) -> dict[str, object]:
    selection = HdcProbe(runner=hdc_runner, hdc_path=hdc_path).select_device(serial=serial)
    payload = {
        **selection,
        "schema_version": "1.0",
        "artifact_kind": "real_device_selection",
        "run_id": run_id,
    }
    path = root / ".leaf" / "runs" / run_id / "device_selection.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _attach_device_selection_artifact(root, run_id, path)
    return {**payload, "device_selection_path": str(path.relative_to(root))}


def _decode_bytes(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="replace")


def _attach_device_selection_artifact(root: Path, run_id: str, path: Path) -> None:
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    if not workflow_path.is_file():
        return
    from tools.leaf_author.workflow import load_workflow, save_workflow

    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    artifacts["device_selection"] = str(path.relative_to(root))
    workflow["artifacts"] = artifacts
    save_workflow(root, workflow)


def _parse_targets(output: str) -> list[str]:
    targets: list[str] = []
    for line in output.splitlines():
        target = line.strip()
        if not target:
            continue
        if target.lower().startswith("[empty]"):
            continue
        targets.append(target.split()[0])
    return targets


def _device_selection_result(
    *,
    status: str,
    reason: str,
    targets: list[str],
    selection_reason: str,
    serial: str | None = None,
    device: dict[str, object] | None = None,
) -> dict[str, object]:
    needs_input = status == "needs_user_input"
    payload: dict[str, object] = {
        "status": status,
        "tool": "hdc",
        "targets": targets,
        "serial": serial,
        "selection_reason": selection_reason,
        "reason": reason,
        "trigger_source": "hdc list targets",
        "context_policy": {
            "scope": "real_device_input",
            "load_strategy": "target_list_then_single_device_probe",
            "artifact_loading": "on_demand",
            "attention_boundary": "one_active_run",
        },
        "user_loop": {
            "position": "provide_target_inputs" if needs_input else "observe_real_device_execution",
            "required_input": "--serial <serial>" if needs_input else "",
        },
    }
    if device is not None:
        payload["device"] = device
    return payload


def _hdc_transport_error(result: ProbeCommandResult) -> bool:
    output = f"{result.stdout}\n{result.stderr}".lower()
    return "connect server failed" in output or "not connect to server" in output
