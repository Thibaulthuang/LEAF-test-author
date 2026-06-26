from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class DomainContract:
    domain: str
    target_feature: Callable[[list[str]], str]
    validate_plan: Callable[[str, list[str]], None]
    action_for_step: Callable[[str], str]


def domain_contract(domain: str) -> DomainContract:
    if domain == "camera":
        return DomainContract(
            domain="camera",
            target_feature=_camera_target_feature,
            validate_plan=_validate_camera_plan,
            action_for_step=_camera_action,
        )
    return DomainContract(
        domain=domain,
        target_feature=lambda steps: f"{domain}.generated",
        validate_plan=lambda target_feature, steps: None,
        action_for_step=lambda title: "GenericAW.performStep",
    )


def target_feature_for_steps(domain: str, steps: list[str]) -> str:
    return domain_contract(domain).target_feature(steps)


def validate_plan_input(domain: str, target_feature: str, steps: list[str]) -> None:
    domain_contract(domain).validate_plan(target_feature, steps)


def action_for_step(domain: str, title: str) -> str:
    return domain_contract(domain).action_for_step(title)


def _camera_target_feature(steps: list[str]) -> str:
    joined = " ".join(steps)
    if any(keyword in joined for keyword in ("拍照", "照片", "相机")):
        return "camera.capture"
    return "camera.generated"


def _validate_camera_plan(target_feature: str, steps: list[str]) -> None:
    if target_feature != "camera.capture":
        return
    joined = " ".join(steps)
    required_groups = [
        ("打开", "相机"),
        ("拍照模式", "快门"),
        ("新照片", "照片"),
    ]
    if not all(any(keyword in joined for keyword in group) for group in required_groups):
        raise ValueError("camera.capture semantic plan must include opening Camera, capture action, and new-photo verification")


def _camera_action(title: str) -> str:
    if "打开" in title and "相机" in title:
        return "CameraAW.launch"
    if "拍照模式" in title:
        return "CameraAW.switchToPhotoMode"
    if "快门" in title or ("拍照" in title and "模式" not in title):
        return "CameraAW.capture"
    if "照片" in title or "相册" in title:
        return "GalleryAW.assertLatestPhotoCreatedAfter"
    return "CameraAW.performStep"
