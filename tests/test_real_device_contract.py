import unittest

from tools.leaf_author.real_device_contract import real_device_decision_contract, real_device_user_loop


class RealDeviceContractTests(unittest.TestCase):
    def test_real_device_gate_contracts_are_stable_for_agents_and_context(self):
        approval = real_device_decision_contract("approval")
        self.assertEqual(approval["trigger_source"], "workflow.json")
        self.assertEqual(approval["agent_owner"], "leaf-test-author")
        self.assertEqual(approval["context_slice"], ["workflow", "real_device_approval"])
        self.assertEqual(approval["allowed_artifacts"], ["workflow", "real_device_approval"])

        device_input = real_device_decision_contract("input")
        self.assertEqual(device_input["context_slice"], ["workflow", "real_device_input"])
        self.assertEqual(device_input["allowed_artifacts"], ["workflow", "real_device_input"])

        preflight = real_device_decision_contract("preflight")
        self.assertEqual(preflight["agent_owner"], "leaf-test-author")
        self.assertIn("runtime_safety", preflight["context_slice"])
        self.assertIn("real_device_approval", preflight["allowed_artifacts"])
        self.assertIn("real_device_input", preflight["allowed_artifacts"])

    def test_real_device_user_loop_positions_are_stable(self):
        self.assertEqual(real_device_user_loop("approval", "approve_camera_capture_e2e")["position"], "approve_real_device")
        self.assertEqual(real_device_user_loop("approval", "approve_camera_capture_e2e")["required_input"], "approve_camera_capture_e2e")
        self.assertEqual(real_device_user_loop("input")["position"], "provide_target_inputs")
        self.assertEqual(real_device_user_loop("input")["required_input"], "--serial <serial>")
        self.assertEqual(real_device_user_loop("preflight")["position"], "observe_real_device_execution")
        self.assertEqual(real_device_user_loop("preflight")["required_input"], "")


if __name__ == "__main__":
    unittest.main()
