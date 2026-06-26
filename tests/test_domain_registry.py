import unittest

from tools.leaf_author.domain_registry import action_for_step, domain_contract, target_feature_for_steps, validate_plan_input


class DomainRegistryTests(unittest.TestCase):
    def test_camera_contract_owns_target_feature_validation_and_action_mapping(self):
        steps = ["打开系统相机", "确认处于拍照模式", "点击快门拍照", "检查产生新照片"]

        self.assertEqual(target_feature_for_steps("camera", steps), "camera.capture")
        validate_plan_input("camera", "camera.capture", steps)
        self.assertEqual(action_for_step("camera", "打开系统相机"), "CameraAW.launch")
        self.assertEqual(action_for_step("camera", "点击快门拍照"), "CameraAW.capture")

    def test_camera_contract_rejects_incomplete_capture_plan(self):
        with self.assertRaisesRegex(ValueError, "camera.capture semantic plan"):
            validate_plan_input("camera", "camera.capture", ["打开系统相机", "点击快门拍照"])

    def test_unknown_domain_uses_generic_contract_without_core_changes(self):
        steps = ["打开目标功能", "执行核心动作"]

        contract = domain_contract("display")

        self.assertEqual(contract.domain, "display")
        self.assertEqual(target_feature_for_steps("display", steps), "display.generated")
        validate_plan_input("display", "display.generated", steps)
        self.assertEqual(action_for_step("display", "执行核心动作"), "GenericAW.performStep")


if __name__ == "__main__":
    unittest.main()
