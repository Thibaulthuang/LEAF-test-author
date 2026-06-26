from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.domain_registry import action_for_step


def generate_case_spec(root: Path, plan: dict[str, object]) -> Path:
    run_id = str(plan["run_id"])
    run_dir = root / ".leaf" / "runs" / run_id
    case_path = run_dir / "case.json"
    case_path.write_text(json.dumps(build_case_spec(plan), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return case_path


def build_case_spec(plan: dict[str, object]) -> dict[str, object]:
    domain = str(plan["domain"])
    steps = [_build_step(domain, str(step), index) for index, step in enumerate(plan.get("steps", []), start=1)]
    case_spec = {
        "schema_version": "1.0",
        "run_id": str(plan["run_id"]),
        "owner": "leaf-test-author",
        "domain": domain,
        "platform": str(plan.get("platform", "openharmony")),
        "target_feature": str(plan["target_feature"]),
        "steps": steps,
        "confirmation_required": bool(plan.get("confirmation_required", True)),
    }
    if plan.get("risk"):
        case_spec["risk"] = str(plan["risk"])
    return case_spec


def _build_step(domain: str, title: str, index: int) -> dict[str, object]:
    action = action_for_step(domain, title)
    step = {
        "id": _step_id(action, index),
        "title": title,
        "action": action,
    }
    if action.endswith("performStep"):
        step["args"] = [title]
    return step
def _step_id(action: str, index: int) -> str:
    names = {
        "CameraAW.launch": "open_camera",
        "CameraAW.switchToPhotoMode": "ensure_photo_mode",
        "CameraAW.capture": "capture_photo",
        "GalleryAW.assertLatestPhotoCreatedAfter": "assert_new_photo",
    }
    return names.get(action, f"step_{index}")
