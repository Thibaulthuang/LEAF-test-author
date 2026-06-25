from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tools.leaf_author.device_diagnostics import inspect_package_dir
from tools.leaf_author.workflow import load_workflow, save_workflow


@dataclass
class BuildCommandResult:
    exit_code: int
    stdout: str
    stderr: str


BuildRunner = Callable[[list[str], Path, int], BuildCommandResult]


def build_openharmony_haps(
    root: Path,
    run_id: str,
    project_dir: Path,
    output_dir: Path | None = None,
    build_command: list[str] | None = None,
    runner: BuildRunner | None = None,
    timeout_s: int = 600,
) -> dict[str, object]:
    project_path = Path(project_dir)
    hvigorw = project_path / "hvigorw"
    if not hvigorw.is_file():
        payload = {
            "run_id": run_id,
            "status": "failed",
            "quality_gate": "OPENHARMONY_BUILD_TOOL_MISSING",
            "project_dir": str(project_path),
            "reason": f"hvigorw not found: {hvigorw}",
            "exit_code": None,
            "stdout": "",
            "stderr": "",
        }
        _write_build_artifact(root, run_id, payload, phase="openharmony_build_failed")
        return payload

    command = build_command or ["./hvigorw", "assembleHap"]
    runner = runner or _run_subprocess
    result = runner(command, project_path, timeout_s)
    package_dir = Path(output_dir) if output_dir is not None else project_path / "build" / "outputs"
    inventory = inspect_package_dir(root, run_id, package_dir)
    passed = result.exit_code == 0 and inventory.get("quality_gate") == "HAP_PACKAGE_READY"
    payload = {
        "run_id": run_id,
        "status": "built" if passed else "failed",
        "quality_gate": "OPENHARMONY_BUILD_PASS" if passed else "OPENHARMONY_BUILD_FAILED",
        "project_dir": str(project_path),
        "command": command,
        "exit_code": result.exit_code,
        "stdout": result.stdout[:4000],
        "stderr": result.stderr[:4000],
        "package_dir": str(package_dir),
        "package_inventory": inventory,
    }
    _write_build_artifact(root, run_id, payload, phase="openharmony_built" if passed else "openharmony_build_failed")
    return payload


def _run_subprocess(args: list[str], cwd: Path, timeout_s: int) -> BuildCommandResult:
    completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout_s)
    return BuildCommandResult(completed.returncode, completed.stdout, completed.stderr)


def _write_build_artifact(root: Path, run_id: str, payload: dict[str, object], phase: str) -> None:
    path = root / ".leaf" / "runs" / run_id / "openharmony_build.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    if not workflow_path.exists():
        return
    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    artifacts["openharmony_build"] = str(path.relative_to(root))
    workflow["artifacts"] = artifacts
    workflow["current_phase"] = phase
    save_workflow(root, workflow)
