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
        self.assertIn("--run-real --runtime-mode capture_e2e", combined)
        self.assertIn("approve_camera_capture_e2e", combined)
        self.assertIn("second confirmation", combined)
        self.assertIn("must not run", combined)

    def test_leaf_author_documents_case_json_as_final_case_spec(self):
        root = Path(__file__).resolve().parents[1]
        command = (root / ".opencode" / "commands" / "leaf-new-case.md").read_text(encoding="utf-8")
        skill = (root / ".opencode" / "skills" / "leaf-test-author" / "SKILL.md").read_text(encoding="utf-8")
        combined = command + "\n" + skill

        self.assertIn("case.json", combined)
        self.assertIn("final case spec", combined)
        self.assertIn("system-app execution", combined)

    def test_leaf_resume_documents_auto_safe_resume(self):
        root = Path(__file__).resolve().parents[1]
        command = (root / ".opencode" / "commands" / "leaf-resume.md").read_text(encoding="utf-8")

        self.assertIn("--auto-safe", command)
        self.assertIn("safe_to_auto_continue", command)
        self.assertIn("must still stop", command)

    def test_leaf_batch_documents_multi_case_entrypoint(self):
        root = Path(__file__).resolve().parents[1]
        command = (root / ".opencode" / "commands" / "leaf-batch.md").read_text(encoding="utf-8")

        self.assertIn("/leaf-batch", command)
        self.assertIn("create-batch", command)
        self.assertIn("resume-batch", command)
        self.assertIn("report-batch", command)
        self.assertIn("one run at a time", command)
        self.assertIn("must still stop", command)

    def test_leaf_report_documents_operator_decision_entrypoint(self):
        root = Path(__file__).resolve().parents[1]
        command = (root / ".opencode" / "commands" / "leaf-report.md").read_text(encoding="utf-8")

        self.assertIn("/leaf-report", command)
        self.assertIn("report-run", command)
        self.assertIn("report-batch", command)
        self.assertIn("audit-run", command)
        self.assertIn("audit-batch", command)
        self.assertIn("workflow-diagnostics", command)
        self.assertIn("repair_workflow", command)
        self.assertIn("failed checks", command)
        self.assertIn("user_checkpoint", command)
        self.assertIn("user_loop", command)
        self.assertIn("decision_contract", command)
        self.assertIn("--runtime-mode <mode>", command)
        self.assertIn("latest_quality_gate", command)
        self.assertIn("evidence", command)

    def test_workflow_contract_documents_phase_quality_gate_and_user_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads((root / "docs" / "workflow-contract.json").read_text(encoding="utf-8"))

        self.assertEqual(contract["schema_version"], "1.0")
        self.assertIn("plan", contract["phases"])
        self.assertEqual(contract["phases"]["plan"]["user_checkpoint"], "first_plan_confirmation")
        self.assertEqual(contract["phases"]["e2e_ready"]["user_checkpoint"], "real_device_confirmation")
        self.assertEqual(contract["phases"]["plan"]["auto_safe"], False)
        self.assertEqual(contract["phases"]["plan"]["batch_focus_priority"], 60)
        self.assertLess(contract["phases"]["hypium_draft"]["batch_focus_priority"], contract["phases"]["plan"]["batch_focus_priority"])
        self.assertEqual(contract["phases"]["hypium_draft"]["auto_safe"], True)
        self.assertEqual(contract["phases"]["pytest_ran"]["agent_owner"], "leaf-gui-agent")
        self.assertIn("ui_tree", contract["phases"]["pytest_ran"]["context_slice"])
        self.assertEqual(contract["phases"]["e2e_ready"]["user_loop"]["position"], "approve_real_device")
        self.assertIn("DRAFT_STATIC_PASS", contract["quality_gates"])
        self.assertIn("CAMERA_CAPTURE_E2E_PASS", contract["quality_gates"])
        self.assertEqual(contract["resume_policy"]["auto_safe_flag"], "--auto-safe")
        self.assertEqual(contract["context_policy"]["run_listing"], "lightweight_summaries")
        self.assertEqual(contract["context_policy"]["run_inspection"], "single_run_context_slice")
        self.assertEqual(contract["context_policy"]["run_report"], "summary_plus_existing_evidence_paths")
        self.assertEqual(contract["context_policy"]["batch_listing"], "lightweight_batch_summaries")
        self.assertEqual(contract["context_policy"]["batch_inspection"], "batch_summary_without_artifact_duplication")
        self.assertEqual(contract["context_policy"]["batch_report"], "batch_summary_then_one_run_report")
        self.assertIn("resume_batch", contract["entrypoints"])
        self.assertIn("report_run", contract["entrypoints"])
        self.assertIn("report_batch", contract["entrypoints"])
        self.assertEqual(contract["entrypoints"]["batch"], "/leaf-batch <batch_id> [--run-id <run_id>...]")
        self.assertEqual(contract["entrypoints"]["report"], "/leaf-report <run_id|batch_id>")
        self.assertNotIn("test HAP", json.dumps(contract))
        self.assertNotIn("test-runner HAP", json.dumps(contract))

    def test_domain_template_documents_required_extension_points(self):
        root = Path(__file__).resolve().parents[1]
        template = (root / ".opencode" / "skills" / "leaf-domain-template" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Semantic Step Expansion", template)
        self.assertIn("Plan Input Contract", template)
        self.assertIn("Quality Gates", template)
        self.assertIn("Required Python Touchpoints", template)
        self.assertIn("extension-contract <domain>", template)
        self.assertIn("validate-extension-contract <domain>", template)
        self.assertIn("--strict-real-device", template)
        self.assertIn("tools/leaf_author/domain_registry.py", template)
        self.assertIn("tools/leaf_author/runtime_registry.py", template)
        self.assertIn("Avoid adding new domain branches", template)

    def test_readme_documents_multi_run_context_management(self):
        root = Path(__file__).resolve().parents[1]
        readme = (root / "README.md").read_text(encoding="utf-8")

        self.assertIn("Multi-Run Context Management", readme)
        self.assertIn("list-runs", readme)
        self.assertIn("inspect-run", readme)
        self.assertIn("create-batch", readme)
        self.assertIn("inspect-batch", readme)
        self.assertIn("resume-batch", readme)
        self.assertIn("report-run", readme)
        self.assertIn("report-batch", readme)
        self.assertIn("audit-run", readme)
        self.assertIn("audit-batch", readme)
        self.assertIn("workflow-diagnostics", readme)
        self.assertIn("repair_workflow", readme)
        self.assertIn("/leaf-batch", readme)
        self.assertIn("/leaf-report", readme)
        self.assertIn("one run at a time", readme)
        self.assertIn("tools/leaf_author/domain_registry.py", readme)
        self.assertIn("tools/leaf_author/runtime_registry.py", readme)
        self.assertIn("extension-contract camera", readme)
        self.assertIn("export-extension-contract camera", readme)
        self.assertIn("validate-extension-contract camera", readme)
        self.assertIn("validate-extension-contract camera --strict-real-device", readme)
        self.assertIn("real-device gate status", readme)
        self.assertIn("runtime registry status", readme)
        self.assertIn("phase-guard", readme)
        self.assertIn("agent-handoff-contract", readme)
        self.assertIn("real-device-contract", readme)
        self.assertIn("runtime-registry-contract", readme)
        self.assertIn("--runtime-mode direct_smoke", readme)
        self.assertIn("approve_camera_capture_e2e", readme)
        self.assertIn("Report `next_command`", readme)
        self.assertNotIn("test HAP", readme)
        self.assertNotIn("test package", readme)

    def test_opencode_docs_do_not_suggest_test_hap_for_camera_main_path(self):
        root = Path(__file__).resolve().parents[1]
        paths = [
            root / ".opencode" / "commands" / "leaf-new-case.md",
            root / ".opencode" / "skills" / "leaf-test-author" / "SKILL.md",
            root / ".opencode" / "skills" / "leaf-camera" / "SKILL.md",
            root / ".opencode" / "skills" / "leaf-domain-template" / "SKILL.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        self.assertIn("system Camera", combined)
        self.assertIn("Python/HDC/UiTest", combined)
        self.assertIn("--runtime-mode direct_smoke", combined)
        self.assertNotIn("test HAP", combined)
        self.assertNotIn("test-runner HAP", combined)
        self.assertNotIn("@ohos/hypium", combined)

    def test_leaf_author_documents_stable_triggers_context_agents_and_user_loop(self):
        root = Path(__file__).resolve().parents[1]
        skill = (root / ".opencode" / "skills" / "leaf-test-author" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Stable Phase Triggers", skill)
        self.assertIn("workflow.json is authoritative", skill)
        self.assertIn("Context Control", skill)
        self.assertIn("load one run", skill)
        self.assertIn("Subagent Boundaries", skill)
        self.assertIn("docs/workflow-contract.json", skill)
        self.assertIn("context_manifest.json", skill)
        self.assertIn("handoff", skill)
        self.assertIn("from_agent", skill)
        self.assertIn("to_agent", skill)
        self.assertIn("requires_user_confirmation", skill)
        self.assertIn("safe_to_auto_continue", skill)
        self.assertIn("phase-guard", skill)
        self.assertIn("agent-handoff-contract", skill)
        self.assertIn("real-device-contract", skill)
        self.assertIn("runtime-registry-contract", skill)
        self.assertIn("agent_owner", skill)
        self.assertIn("context_slice", skill)
        self.assertIn("leaf-test-author", skill)
        self.assertIn("leaf-gui-agent", skill)
        self.assertIn("User-In-Loop", skill)
        self.assertIn("first_plan_confirmation", skill)
        self.assertIn("real_device_confirmation", skill)
        self.assertIn("must stop", skill)


if __name__ == "__main__":
    unittest.main()
