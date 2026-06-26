from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.authoring import resume_run


def list_runs(root: Path, limit: int | None = None, domain: str | None = None) -> dict[str, object]:
    runs = [_summary_from_workflow(root, path) for path in _workflow_paths(root)]
    if domain:
        runs = [run for run in runs if run.get("domain") == domain]
    runs.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    if limit is not None:
        runs = runs[:limit]
    return {
        "schema_version": "1.0",
        "total": len(runs),
        "runs": runs,
        "context_policy": {
            "load_strategy": "inspect_one_run_at_a_time",
            "summary_fields": ["run_id", "domain", "platform", "current_phase", "confirmed_plan", "next_action", "created_at"],
        },
    }


def inspect_run(root: Path, run_id: str) -> dict[str, object]:
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    resume = resume_run(root, run_id)
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "domain": workflow.get("domain"),
        "platform": workflow.get("platform"),
        "teststep": workflow.get("teststep"),
        "current_phase": resume.get("current_phase"),
        "confirmed_plan": resume.get("confirmed_plan"),
        "next_action": resume.get("next_action"),
        "resume_summary": resume.get("resume_summary"),
        "artifacts": workflow.get("artifacts", {}),
        "created_at": workflow.get("created_at"),
        "context_policy": {
            "scope": "single_run",
            "load_strategy": "load_artifacts_on_demand",
        },
    }


def _workflow_paths(root: Path) -> list[Path]:
    runs_dir = root / ".leaf" / "runs"
    if not runs_dir.is_dir():
        return []
    return sorted(path for path in runs_dir.glob("*/workflow.json") if path.is_file())


def _summary_from_workflow(root: Path, workflow_path: Path) -> dict[str, object]:
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    run_id = str(workflow.get("run_id", workflow_path.parent.name))
    resume = resume_run(root, run_id)
    return {
        "run_id": run_id,
        "domain": workflow.get("domain"),
        "platform": workflow.get("platform"),
        "current_phase": resume.get("current_phase"),
        "confirmed_plan": resume.get("confirmed_plan"),
        "next_action": resume.get("next_action"),
        "created_at": workflow.get("created_at"),
    }
