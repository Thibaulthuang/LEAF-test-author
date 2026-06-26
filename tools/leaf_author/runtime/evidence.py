from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tools.leaf_author.runtime.ui_tree import build_index, parse_layout


def write_ui_snapshot(root: Path, run_id: str, phase: str, action_id: str, raw_layout: str) -> dict[str, object]:
    evidence_dir = root / ".leaf" / "runs" / run_id / "evidence" / "ui"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    safe_action = _safe_name(action_id)
    safe_phase = _safe_name(phase)
    raw_path = evidence_dir / f"{safe_action}.{safe_phase}.raw.json"
    index_path = evidence_dir / f"{safe_action}.{safe_phase}.index.json"
    tree = parse_layout(raw_layout)
    index = build_index(tree)
    raw_path.write_text(raw_layout if raw_layout.endswith("\n") else raw_layout + "\n", encoding="utf-8")
    payload = {
        "schema_version": "1.0",
        "kind": "ui_snapshot",
        "phase": phase,
        "action_id": action_id,
        "source": "uitest dumpLayout",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "raw_path": str(raw_path.relative_to(root)),
        "index": index,
    }
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "kind": "ui_snapshot",
        "phase": phase,
        "action_id": action_id,
        "raw_path": str(raw_path.relative_to(root)),
        "index_path": str(index_path.relative_to(root)),
        "foreground": index["foreground"],
        "node_count": index["node_count"],
        "clickable_count": index["clickable_count"],
    }


def _safe_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return safe or "snapshot"
