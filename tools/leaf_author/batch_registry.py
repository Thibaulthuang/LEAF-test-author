from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tools.leaf_author.run_registry import inspect_run


def create_batch(root: Path, batch_id: str, run_ids: list[str], title: str | None = None) -> dict[str, object]:
    if not run_ids:
        raise ValueError("batch must include at least one run_id")
    for run_id in run_ids:
        workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
        if not workflow_path.is_file():
            raise FileNotFoundError(f"workflow.json not found for run {run_id}: {workflow_path}")
    batch_dir = root / ".leaf" / "batches" / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "title": title or batch_id,
        "run_ids": run_ids,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "context_policy": {
            "scope": "batch",
            "load_strategy": "inspect_batch_then_inspect_one_run",
            "artifact_loading": "on_demand",
        },
    }
    batch_path = batch_dir / "batch.json"
    batch_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**inspect_batch(root, batch_id), "batch_path": str(batch_path)}


def inspect_batch(root: Path, batch_id: str) -> dict[str, object]:
    batch = _load_batch(root, batch_id)
    runs = [inspect_run(root, run_id) for run_id in batch["run_ids"]]
    phase_counts = Counter(str(run.get("current_phase", "unknown")) for run in runs)
    next_run_focus = _next_run_focus(runs)
    return {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "title": batch.get("title", batch_id),
        "total_runs": len(runs),
        "phase_counts": dict(sorted(phase_counts.items())),
        "next_run_focus": next_run_focus,
        "runs": [_run_batch_summary(run) for run in runs],
        "created_at": batch.get("created_at"),
        "context_policy": {
            "scope": "batch_summary",
            "load_strategy": "inspect_one_run_for_details",
        },
    }


def list_batches(root: Path) -> dict[str, object]:
    batches = []
    for path in _batch_paths(root):
        batch = json.loads(path.read_text(encoding="utf-8"))
        batches.append(
            {
                "batch_id": batch.get("batch_id", path.parent.name),
                "title": batch.get("title", path.parent.name),
                "total_runs": len(batch.get("run_ids", [])),
                "created_at": batch.get("created_at"),
            }
        )
    batches.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return {
        "schema_version": "1.0",
        "total": len(batches),
        "batches": batches,
        "context_policy": {
            "load_strategy": "inspect_one_batch_at_a_time",
        },
    }


def _load_batch(root: Path, batch_id: str) -> dict[str, object]:
    batch_path = root / ".leaf" / "batches" / batch_id / "batch.json"
    return json.loads(batch_path.read_text(encoding="utf-8"))


def _batch_paths(root: Path) -> list[Path]:
    batches_dir = root / ".leaf" / "batches"
    if not batches_dir.is_dir():
        return []
    return sorted(path for path in batches_dir.glob("*/batch.json") if path.is_file())


def _run_batch_summary(run: dict[str, object]) -> dict[str, object]:
    return {
        "run_id": run.get("run_id"),
        "domain": run.get("domain"),
        "platform": run.get("platform"),
        "current_phase": run.get("current_phase"),
        "confirmed_plan": run.get("confirmed_plan"),
        "next_action": run.get("next_action"),
    }


def _next_run_focus(runs: list[dict[str, object]]) -> dict[str, object] | None:
    priority = {
        "validate_pytest_draft": 10,
        "run_pytest_draft": 20,
        "collect_gui_context": 30,
        "record_experience": 40,
        "export_team_knowledge": 50,
        "present_plan_for_confirmation": 60,
        "prepare_haps_or_target_bundle": 70,
        "run_real_hypium": 80,
        "inspect_workflow_state": 90,
        "complete": 100,
    }
    candidates = [_run_batch_summary(run) for run in runs if run.get("next_action") != "complete"]
    if not candidates:
        return None
    candidates.sort(key=lambda run: priority.get(str(run.get("next_action")), 99))
    return candidates[0]
