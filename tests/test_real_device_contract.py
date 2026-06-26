import unittest
from contextlib import redirect_stdout
from io import StringIO

from tools.leaf_author.real_device_contract import build_real_device_contract, real_device_decision_contract, real_device_user_loop


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

    def test_real_device_contract_manifest_is_machine_readable(self):
        manifest = build_real_device_contract()

        self.assertEqual(manifest["manifest_kind"], "leaf_real_device_gate_contract")
        self.assertEqual(manifest["trigger_stability"]["authoritative_source"], "workflow.json")
        self.assertEqual(manifest["execution_preflight"]["artifact"], "real_device_preflight")
        self.assertEqual(manifest["gates"]["approval"]["user_loop"]["position"], "approve_real_device")
        self.assertEqual(manifest["gates"]["preflight"]["decision_contract"]["agent_owner"], "leaf-test-author")

    def test_cli_real_device_contract_outputs_json(self):
        from tools.leaf_author.__main__ import main

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["real-device-contract"])

        self.assertEqual(exit_code, 0)
        payload = __import__("json").loads(output.getvalue())
        self.assertEqual(payload["manifest_kind"], "leaf_real_device_gate_contract")
        self.assertIn("preflight", payload["gates"])


if __name__ == "__main__":
    unittest.main()
