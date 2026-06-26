from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.runtime_registry import classify_experience_result, experience_candidate_keys, runtime_artifact_keys
from tools.leaf_author.workflow import load_workflow, save_workflow


def record_experience(root: Path, run_id: str) -> dict[str, object]:
    workflow = load_workflow(root, run_id)
    domain = str(workflow["domain"])
    platform = str(workflow.get("platform", "openharmony"))
    artifacts = dict(workflow.get("artifacts", {}))
    run_result = _latest_run_result(root, artifacts, domain)
    classification = classify_experience_result(domain, run_result)
    payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "domain": domain,
        "platform": platform,
        "target_feature": _target_feature(root, run_id),
        "run_status": run_result.get("status", "unknown"),
        "quality_gate": run_result.get("quality_gate", "UNKNOWN"),
        "confidence": classification["confidence"],
        "auto_applicable": False,
        "notes": classification["notes"],
    }
    knowledge_path = root / ".leaf" / "knowledge" / domain / platform / "experience" / f"{run_id}.json"
    knowledge_path.parent.mkdir(parents=True, exist_ok=True)
    knowledge_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts["experience"] = str(knowledge_path.relative_to(root))
    workflow["artifacts"] = artifacts
    workflow["current_phase"] = "experience_recorded"
    save_workflow(root, workflow)
    return {"run_id": run_id, "status": "recorded", "experience_path": str(knowledge_path), "next_action": "export_team_knowledge"}


def export_team_knowledge(root: Path, run_id: str) -> dict[str, object]:
    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    runtime_artifacts = {key: str(artifacts.get(key, "")) for key in runtime_artifact_keys(str(workflow.get("domain", "")))}
    payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "manifest_kind": "reviewable_team_knowledge",
        "status": "exported",
        "artifacts": {
            "workflow": str(artifacts.get("workflow", "")),
            "plan": str(artifacts.get("plan", "")),
            "pytest": str(artifacts.get("pytest", "")),
            "hypium": str(artifacts.get("hypium", "")),
            "validation": str(artifacts.get("validation", "")),
            "pytest_result": str(artifacts.get("pytest_result", "")),
            "hypium_result": str(artifacts.get("hypium_result", "")),
            **runtime_artifacts,
            "experience": str(artifacts.get("experience", "")),
        },
        "review_required": True,
    }
    manifest_path = root / ".leaf" / "runs" / run_id / "team_export_manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts["team_export_manifest"] = str(manifest_path.relative_to(root))
    workflow["artifacts"] = artifacts
    workflow["current_phase"] = "complete"
    save_workflow(root, workflow)
    return {"run_id": run_id, "status": "exported", "manifest_path": str(manifest_path), "next_action": "complete"}


def _target_feature(root: Path, run_id: str) -> str:
    plan_path = root / ".leaf" / "runs" / run_id / "plan.json"
    if not plan_path.exists():
        return "unknown"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    return str(plan.get("target_feature", "unknown"))


def _latest_run_result(root: Path, artifacts: dict[str, object], domain: str) -> dict[str, object]:
    for key in experience_candidate_keys(domain):
        result = _load_result(root, artifacts, key)
        if result:
            return result
    return {}


def _load_result(root: Path, artifacts: dict[str, object], key: str) -> dict[str, object] | None:
    rel = str(artifacts.get(key, ""))
    if not rel:
        return None
    path = root / rel
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
