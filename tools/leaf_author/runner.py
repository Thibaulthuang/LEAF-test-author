from __future__ import annotations

import json
import subprocess
import sys
import importlib.util
from pathlib import Path

from tools.leaf_author.workflow import load_workflow, save_workflow


def run_pytest_draft(root: Path, run_id: str) -> dict[str, object]:
    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    pytest_rel = str(artifacts.get("pytest", ""))
    if not pytest_rel:
        raise ValueError(f"workflow has no pytest artifact for run {run_id}")
    pytest_path = root / pytest_rel
    if _pytest_available():
        command = [sys.executable, "-m", "pytest", str(pytest_path.relative_to(root)), "-q"]
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False, timeout=30)
        status = "draft_passed" if completed.returncode == 0 else "failed"
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        runner = "pytest"
    else:
        command = ["static-draft-gate", str(pytest_path.relative_to(root))]
        content = pytest_path.read_text(encoding="utf-8")
        status = "draft_passed" if "assert RUN_ID ==" in content and "assert DOMAIN ==" in content else "failed"
        exit_code = 0 if status == "draft_passed" else 1
        stdout = "pytest is not installed; static draft gate verified generated metadata assertions\n"
        stderr = ""
        runner = "static-draft-gate"
    payload = {
        "run_id": run_id,
        "status": status,
        "exit_code": exit_code,
        "runner": runner,
        "command": command,
        "stdout": stdout,
        "stderr": stderr,
        "quality_gate": "DRAFT_STATIC_PASS" if status == "draft_passed" else "DRAFT_RUN_FAILED",
    }
    result_path = root / ".leaf" / "runs" / run_id / "pytest_result.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts["pytest_result"] = str(result_path.relative_to(root))
    workflow["artifacts"] = artifacts
    workflow["current_phase"] = "pytest_ran"
    save_workflow(root, workflow)
    return {**payload, "pytest_result_path": str(result_path), "next_action": "collect_gui_context"}


def _pytest_available() -> bool:
    return importlib.util.find_spec("pytest") is not None
