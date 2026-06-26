import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.leaf_author.extension_contract import build_extension_contract, export_extension_contract, validate_extension_contract


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

    def test_export_extension_contract_writes_manifest_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "camera-extension.json"

            result = export_extension_contract("camera", output_path)

            self.assertEqual(result["output_path"], str(output_path))
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["domain"], "camera")
            self.assertEqual(payload["readiness"]["status"], "ready")

    def test_validate_extension_contract_reports_ready_and_incomplete_status(self):
        ready = validate_extension_contract("camera")
        incomplete = validate_extension_contract("display")

        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["exit_code"], 0)
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertEqual(incomplete["exit_code"], 1)

    def test_cli_export_and_validate_extension_contract(self):
        from tools.leaf_author.__main__ import main

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "camera-extension.json"
            export_output = StringIO()
            with redirect_stdout(export_output):
                export_exit = main(["export-extension-contract", "camera", "--output", str(output_path)])

            validate_output = StringIO()
            with redirect_stdout(validate_output):
                validate_exit = main(["validate-extension-contract", "camera"])

            incomplete_output = StringIO()
            with redirect_stdout(incomplete_output):
                incomplete_exit = main(["validate-extension-contract", "display"])

            self.assertEqual(export_exit, 0)
            self.assertTrue(output_path.exists())
            self.assertEqual(json.loads(export_output.getvalue())["output_path"], str(output_path))
            self.assertEqual(validate_exit, 0)
            self.assertEqual(json.loads(validate_output.getvalue())["status"], "ready")
            self.assertEqual(incomplete_exit, 1)
            self.assertEqual(json.loads(incomplete_output.getvalue())["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
