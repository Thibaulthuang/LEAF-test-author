import json
import unittest
from contextlib import redirect_stdout
from io import StringIO

from tools.leaf_author.extension_contract import build_extension_contract


class ExtensionContractTests(unittest.TestCase):
    def test_camera_extension_contract_summarizes_domain_runtime_and_phase_hooks(self):
        contract = build_extension_contract("camera")

        self.assertEqual(contract["domain"], "camera")
        self.assertEqual(contract["domain_contract"]["registered"], True)
        self.assertEqual(contract["domain_contract"]["skill"], "leaf-camera")
        self.assertIn("direct_smoke", contract["runtime_contract"]["registered_modes"])
        self.assertEqual(contract["runtime_contract"]["default_real_device_mode"], "direct_smoke")
        self.assertIn("camera_direct_smoke", contract["runtime_contract"]["artifact_keys"])
        self.assertIn("CAMERA_DIRECT_SMOKE_PASS", contract["runtime_contract"]["quality_gates"])
        self.assertIn("e2e_ready", contract["phase_contract"]["real_device_checkpoint_phases"])
        self.assertEqual(contract["readiness"]["status"], "ready")

    def test_unknown_domain_contract_marks_runtime_gaps(self):
        contract = build_extension_contract("display")

        self.assertEqual(contract["domain"], "display")
        self.assertEqual(contract["domain_contract"]["registered"], False)
        self.assertEqual(contract["runtime_contract"]["registered_modes"], [])
        self.assertEqual(contract["readiness"]["status"], "incomplete")
        self.assertIn("runtime_registry", " ".join(contract["readiness"]["missing"]))

    def test_cli_extension_contract_outputs_json(self):
        from tools.leaf_author.__main__ import main

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["extension-contract", "camera"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["domain"], "camera")
        self.assertEqual(payload["manifest_kind"], "leaf_framework_extension_contract")


if __name__ == "__main__":
    unittest.main()
