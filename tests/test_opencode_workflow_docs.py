from pathlib import Path
import json
import unittest


class OpenCodeWorkflowDocsTests(unittest.TestCase):
    def test_leaf_new_case_documents_two_stage_confirmation_flow(self):
        root = Path(__file__).resolve().parents[1]
        command = (root / ".opencode" / "commands" / "leaf-new-case.md").read_text(encoding="utf-8")
        skill = (root / ".opencode" / "skills" / "leaf-test-author" / "SKILL.md").read_text(encoding="utf-8")
        combined = command + "\n" + skill

        self.assertIn("Two-Stage Confirmation", combined)
        self.assertIn("confirm-plan", combined)
        self.assertIn("advance <run_id>", combined)
        self.assertIn("--run-real --camera-capture", combined)
        self.assertIn("second confirmation", combined)
        self.assertIn("must not run", combined)

    def test_leaf_author_documents_case_json_as_final_case_spec(self):
        root = Path(__file__).resolve().parents[1]
        command = (root / ".opencode" / "commands" / "leaf-new-case.md").read_text(encoding="utf-8")
        skill = (root / ".opencode" / "skills" / "leaf-test-author" / "SKILL.md").read_text(encoding="utf-8")
        combined = command + "\n" + skill

        self.assertIn("case.json", combined)
        self.assertIn("final case spec", combined)
        self.assertIn("Hypium", combined)

    def test_leaf_resume_documents_auto_safe_resume(self):
        root = Path(__file__).resolve().parents[1]
        command = (root / ".opencode" / "commands" / "leaf-resume.md").read_text(encoding="utf-8")

        self.assertIn("--auto-safe", command)
        self.assertIn("safe_to_auto_continue", command)
        self.assertIn("must still stop", command)

    def test_workflow_contract_documents_phase_quality_gate_and_user_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads((root / "docs" / "workflow-contract.json").read_text(encoding="utf-8"))

        self.assertEqual(contract["schema_version"], "1.0")
        self.assertIn("plan", contract["phases"])
        self.assertEqual(contract["phases"]["plan"]["user_checkpoint"], "first_plan_confirmation")
        self.assertEqual(contract["phases"]["e2e_ready"]["user_checkpoint"], "real_device_confirmation")
        self.assertIn("DRAFT_STATIC_PASS", contract["quality_gates"])
        self.assertIn("CAMERA_CAPTURE_E2E_PASS", contract["quality_gates"])
        self.assertEqual(contract["resume_policy"]["auto_safe_flag"], "--auto-safe")
        self.assertEqual(contract["context_policy"]["run_listing"], "lightweight_summaries")
        self.assertEqual(contract["context_policy"]["run_inspection"], "single_run_context_slice")

    def test_domain_template_documents_required_extension_points(self):
        root = Path(__file__).resolve().parents[1]
        template = (root / ".opencode" / "skills" / "leaf-domain-template" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Semantic Step Expansion", template)
        self.assertIn("Plan Input Contract", template)
        self.assertIn("Quality Gates", template)
        self.assertIn("Required Python Touchpoints", template)

    def test_readme_documents_multi_run_context_management(self):
        root = Path(__file__).resolve().parents[1]
        readme = (root / "README.md").read_text(encoding="utf-8")

        self.assertIn("Multi-Run Context Management", readme)
        self.assertIn("list-runs", readme)
        self.assertIn("inspect-run", readme)
        self.assertIn("one run at a time", readme)


if __name__ == "__main__":
    unittest.main()
