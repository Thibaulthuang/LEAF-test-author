from __future__ import annotations

import json
from pathlib import Path


def inspect_workflow_state(root: Path, run_id: str) -> dict[str, object]:
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    relative_workflow_path = str(workflow_path.relative_to(root))
    checks = {
        "exists": workflow_path.is_file(),
        "non_empty": False,
        "json_parseable": False,
        "schema_version_present": False,
        "run_id_matches": False,
        "current_phase_present": False,
    }
    payload: dict[str, object] | None = None
    error: dict[str, str] | None = None
    size_bytes = workflow_path.stat().st_size if workflow_path.is_file() else 0
    if checks["exists"]:
        checks["non_empty"] = size_bytes > 0
        try:
            loaded = json.loads(workflow_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
                checks["json_parseable"] = True
                checks["schema_version_present"] = bool(loaded.get("schema_version"))
                checks["run_id_matches"] = loaded.get("run_id") == run_id
                checks["current_phase_present"] = bool(loaded.get("current_phase"))
            else:
                error = {"type": "TypeError", "message": "workflow.json must contain a JSON object"}
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
    else:
        error = {"type": "FileNotFoundError", "message": f"workflow.json not found for run {run_id}"}

    passed = all(checks.values())
    result: dict[str, object] = {
        "schema_version": "1.0",
        "manifest_kind": "leaf_workflow_diagnostics",
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "workflow_path": relative_workflow_path,
        "size_bytes": size_bytes,
        "current_phase": payload.get("current_phase") if payload else "unreadable",
        "next_action": "inspect_workflow_state" if passed else "repair_workflow",
        "checks": checks,
        "context_policy": {
            "scope": "workflow_diagnostics",
            "load_strategy": "workflow_file_only",
            "artifact_loading": "on_demand",
        },
    }
    if error:
        result["error"] = error
    return _write_diagnostics(root, run_id, result)


def _write_diagnostics(root: Path, run_id: str, payload: dict[str, object]) -> dict[str, object]:
    path = root / ".leaf" / "runs" / run_id / "workflow_diagnostics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["diagnostics_path"] = str(path.relative_to(root))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
