from __future__ import annotations


def build_plan(workflow: dict[str, object], plan_input: dict[str, object] | None = None) -> dict[str, object]:
    run_id = str(workflow["run_id"])
    domain = str(workflow["domain"])
    platform = str(workflow.get("platform", "openharmony"))
    teststep = str(workflow["teststep"])
    if plan_input is None:
        steps = [part.strip() for part in teststep.replace("\n", "；").split("；") if part.strip()]
        target_feature = _target_feature(domain, steps)
        confirmation_required = True
        risk = None
    else:
        steps = _validated_steps(plan_input)
        target_feature = str(plan_input.get("target_feature") or _target_feature(domain, steps))
        confirmation_required = bool(plan_input.get("confirmation_required", True))
        risk = plan_input.get("risk")
        _validate_domain_plan(domain, target_feature, steps)
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


def _target_feature(domain: str, steps: list[str]) -> str:
    joined = " ".join(steps)
    if domain == "camera" and any(keyword in joined for keyword in ("拍照", "照片", "相机")):
        return "camera.capture"
    return f"{domain}.generated"


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


def _validate_domain_plan(domain: str, target_feature: str, steps: list[str]) -> None:
    if domain == "camera" and target_feature == "camera.capture":
        joined = " ".join(steps)
        required_groups = [
            ("打开", "相机"),
            ("拍照模式", "快门"),
            ("新照片", "照片"),
        ]
        if not all(any(keyword in joined for keyword in group) for group in required_groups):
            raise ValueError("camera.capture semantic plan must include opening Camera, capture action, and new-photo verification")
