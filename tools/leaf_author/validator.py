from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.workflow import load_workflow, save_workflow


def validate_pytest_draft(root: Path, run_id: str) -> dict[str, object]:
    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    pytest_rel = str(artifacts.get("pytest", ""))
    if not pytest_rel:
        raise ValueError(f"workflow has no pytest artifact for run {run_id}")
    pytest_path = root / pytest_rel
    content = pytest_path.read_text(encoding="utf-8")
    checks = {
        "has_run_id": f'RUN_ID = "{run_id}"' in content,
        "has_domain": f'DOMAIN = "{workflow["domain"]}"' in content,
        "has_target_feature": "TARGET_FEATURE =" in content,
        "has_steps": "# Step 1:" in content,
        "has_metadata_assertions": f'assert RUN_ID == "{run_id}"' in content and f'assert DOMAIN == "{workflow["domain"]}"' in content,
        "has_no_pytest_skip": "pytest.skip" not in content,
    }
    status = "passed" if all(checks.values()) else "failed"
    payload = {
        "run_id": run_id,
        "status": status,
        "checks": checks,
        "quality_gate": "DRAFT_VALIDATED" if status == "passed" else "DRAFT_INVALID",
    }
    validation_path = root / ".leaf" / "runs" / run_id / "validation.json"
    validation_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts["validation"] = str(validation_path.relative_to(root))
    workflow["artifacts"] = artifacts
    workflow["current_phase"] = "validated" if status == "passed" else "validation_failed"
    save_workflow(root, workflow)
    return {**payload, "validation_path": str(validation_path), "next_action": "run_pytest_draft" if status == "passed" else "repair_pytest_draft"}
