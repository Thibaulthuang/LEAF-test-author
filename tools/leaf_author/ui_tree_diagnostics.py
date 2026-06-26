from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.reports import report_run
from tools.leaf_author.runtime.ui_tree import diff_indexes, find_candidates


def inspect_ui_tree(
    root: Path,
    run_id: str,
    *,
    phase: str | None = None,
    action_id: str | None = None,
    node_id: str | None = None,
    text: str | None = None,
    node_type: str | None = None,
    clickable: bool | None = None,
    limit: int = 10,
    include_diffs: bool = True,
) -> dict[str, object]:
    report = report_run(root, run_id)
    runtime_summary = report.get("runtime_evidence_summary")
    ui_snapshots = runtime_summary.get("ui_snapshots", []) if isinstance(runtime_summary, dict) else []
    if not ui_snapshots:
        ui_snapshots = _snapshot_refs_from_artifacts(root, report)
    snapshots = []
    for snapshot in ui_snapshots if isinstance(ui_snapshots, list) else []:
        if not isinstance(snapshot, dict):
            continue
        if phase and snapshot.get("phase") != phase:
            continue
        if action_id and snapshot.get("action_id") != action_id:
            continue
        snapshots.append(_inspect_snapshot(root, snapshot, _selectors(node_id, text, node_type, clickable), limit))
    diffs = _snapshot_diffs(root, snapshots) if include_diffs else []
    payload = {
        "schema_version": "1.0",
        "manifest_kind": "leaf_ui_tree_diagnostics",
        "run_id": run_id,
        "phase_filter": phase,
        "action_id_filter": action_id,
        "selector": {
            "id": node_id,
            "text": text,
            "type": node_type,
            "clickable": clickable,
        },
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "diff_count": len(diffs),
        "context_policy": {
            "scope": "ui_tree_diagnostics",
            "load_strategy": "runtime_evidence_summary_then_selected_indexes",
            "artifact_loading": "on_demand",
            "attention_boundary": "one_active_run",
        },
    }
    if include_diffs:
        payload["diffs"] = diffs
    return payload


def _inspect_snapshot(root: Path, snapshot: dict[str, object], selectors: list[dict[str, object]], limit: int) -> dict[str, object]:
    index_path = snapshot.get("index_path")
    index_payload = _load_index(root, str(index_path)) if isinstance(index_path, str) else {}
    index = index_payload.get("index") if isinstance(index_payload, dict) else {}
    index = index if isinstance(index, dict) else {}
    candidates = find_candidates(index, selectors) if selectors else []
    return {
        "phase": snapshot.get("phase"),
        "action_id": snapshot.get("action_id"),
        "raw_path": snapshot.get("raw_path"),
        "index_path": snapshot.get("index_path"),
        "foreground": index.get("foreground", snapshot.get("foreground", {})),
        "node_count": index.get("node_count", snapshot.get("node_count")),
        "clickable_count": index.get("clickable_count", snapshot.get("clickable_count")),
        "candidate_count": len(candidates),
        "candidates": candidates[: max(0, limit)],
        "index_status": "ready" if index else "missing_or_invalid",
    }


def _load_index(root: Path, index_path: str) -> dict[str, object]:
    path = root / index_path
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _snapshot_diffs(root: Path, snapshots: list[dict[str, object]]) -> list[dict[str, object]]:
    diffs = []
    for before, after in zip(snapshots, snapshots[1:]):
        before_index = _index_from_snapshot(root, before)
        after_index = _index_from_snapshot(root, after)
        if not before_index or not after_index:
            continue
        diff = diff_indexes(before_index, after_index)
        diffs.append(
            {
                "from_phase": before.get("phase"),
                "from_action_id": before.get("action_id"),
                "to_phase": after.get("phase"),
                "to_action_id": after.get("action_id"),
                **diff,
            }
        )
    return diffs


def _index_from_snapshot(root: Path, snapshot: dict[str, object]) -> dict[str, object]:
    index_path = snapshot.get("index_path")
    if not isinstance(index_path, str):
        return {}
    payload = _load_index(root, index_path)
    index = payload.get("index") if isinstance(payload, dict) else {}
    return index if isinstance(index, dict) else {}


def _snapshot_refs_from_artifacts(root: Path, report: dict[str, object]) -> list[dict[str, object]]:
    evidence = report.get("evidence")
    if not isinstance(evidence, dict):
        return []
    snapshots: list[dict[str, object]] = []
    for key, value in evidence.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if not key.endswith("_smoke") and not key.endswith("_e2e"):
            continue
        path = root / value
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        artifact_evidence = payload.get("evidence") if isinstance(payload, dict) else {}
        refs = artifact_evidence.get("ui_snapshot_refs") if isinstance(artifact_evidence, dict) else []
        if isinstance(refs, list):
            snapshots.extend(ref for ref in refs if isinstance(ref, dict))
    return snapshots


def _selectors(node_id: str | None, text: str | None, node_type: str | None, clickable: bool | None) -> list[dict[str, object]]:
    selector: dict[str, object] = {}
    if node_id:
        selector["id"] = node_id
    if text:
        selector["text"] = text
    if node_type:
        selector["type"] = node_type
    if clickable is not None:
        selector["clickable"] = clickable
    return [selector] if selector else []
