from __future__ import annotations

from tools.leaf_author.domain_registry import target_feature_for_steps, validate_plan_input


def build_plan(workflow: dict[str, object], plan_input: dict[str, object] | None = None) -> dict[str, object]:
    run_id = str(workflow["run_id"])
    domain = str(workflow["domain"])
    platform = str(workflow.get("platform", "openharmony"))
    teststep = str(workflow["teststep"])
    if plan_input is None:
        steps = [part.strip() for part in teststep.replace("\n", "；").split("；") if part.strip()]
        target_feature = target_feature_for_steps(domain, steps)
        confirmation_required = True
        risk = None
    else:
        steps = _validated_steps(plan_input)
        target_feature = str(plan_input.get("target_feature") or target_feature_for_steps(domain, steps))
        confirmation_required = bool(plan_input.get("confirmation_required", True))
        risk = plan_input.get("risk")
        validate_plan_input(domain, target_feature, steps)
    safe_run_id = run_id.replace("-", "_")
    plan = {
        "schema_version": "1.0",
        "run_id": run_id,
        "owner": "leaf-test-author",
        "domain": domain,
        "platform": platform,
        "domain_skill": f"leaf-{domain}",
        "target_feature": target_feature,
        "steps": steps,
        "writes": [f"tests/generated/test_{safe_run_id}_{domain}.py"],
        "requires_device_probe": platform == "openharmony",
        "confirmation_required": confirmation_required,
    }
    if risk:
        plan["risk"] = str(risk)
    return plan


def _validated_steps(plan_input: dict[str, object]) -> list[str]:
    raw_steps = plan_input.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("plan_input.steps must be a non-empty list")
    steps = []
    for index, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, str) or not raw_step.strip():
            raise ValueError(f"plan_input.steps[{index}] must be a non-empty string")
        steps.append(raw_step.strip())
    return steps
