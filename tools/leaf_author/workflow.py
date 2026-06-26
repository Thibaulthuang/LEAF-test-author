from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def create_workflow(root: Path, domain: str, teststep: str, run_id: str) -> dict[str, object]:
    run_dir = Path(".leaf") / "runs" / run_id
    workflow = {
        "schema_version": "1.0",
        "run_id": run_id,
        "owner": "leaf-test-author",
        "domain": domain,
        "platform": "openharmony",
        "teststep": teststep,
        "current_phase": "plan",
        "confirmed_plan": False,
        "debug_attempts": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {
            "run_dir": run_dir.as_posix(),
            "workflow": (run_dir / "workflow.json").as_posix(),
            "plan": (run_dir / "plan.json").as_posix(),
        },
    }
    workflow_path = root / run_dir / "workflow.json"
    _write_json_atomic(workflow_path, workflow)
    return workflow


def load_workflow(root: Path, run_id: str) -> dict[str, object]:
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    return json.loads(workflow_path.read_text(encoding="utf-8"))


def save_workflow(root: Path, workflow: dict[str, object]) -> None:
    run_id = str(workflow["run_id"])
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    _write_json_atomic(workflow_path, workflow)


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
    tmp_path.replace(path)
