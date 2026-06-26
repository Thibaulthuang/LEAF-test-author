import json
import unittest
from contextlib import redirect_stdout
from io import StringIO

from tools.leaf_author.phase_guard import build_agent_handoff_contract, validate_phase_contract


class PhaseGuardTests(unittest.TestCase):
    def test_phase_guard_validates_stable_trigger_context_agent_and_user_loop_contract(self):
        result = validate_phase_contract()

        self.assertEqual(result["status"], "stable")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["trigger_source"], "workflow.json")
        self.assertEqual(result["attention_boundary"], "one_active_run")
        self.assertIn("leaf-test-author", result["agent_owners"])
        self.assertIn("leaf-gui-agent", result["agent_owners"])
        self.assertEqual(result["user_checkpoints"]["first_plan_confirmation"], ["plan"])
        self.assertEqual(result["user_checkpoints"]["real_device_confirmation"], ["e2e_ready"])

    def test_agent_handoff_contract_summarizes_context_slices_and_auto_safe_boundaries(self):
        contract = build_agent_handoff_contract()

        self.assertEqual(contract["manifest_kind"], "leaf_agent_handoff_contract")
        self.assertEqual(contract["trigger_stability"]["authoritative_source"], "workflow.json")
        self.assertIn("pytest_ran", contract["agents"]["leaf-gui-agent"])
        self.assertIn("ui_tree", contract["context_slices"]["pytest_ran"])
        self.assertIn("hypium_draft", contract["auto_safe_phases"])
        self.assertIn("first_plan_confirmation", contract["resume_policy"]["never_auto_cross"])

    def test_cli_phase_guard_and_agent_handoff_contract_output_json(self):
        from tools.leaf_author.__main__ import main

        guard_output = StringIO()
        with redirect_stdout(guard_output):
            guard_exit = main(["phase-guard"])

        handoff_output = StringIO()
        with redirect_stdout(handoff_output):
            handoff_exit = main(["agent-handoff-contract"])

        self.assertEqual(guard_exit, 0)
        self.assertEqual(json.loads(guard_output.getvalue())["status"], "stable")
        self.assertEqual(handoff_exit, 0)
        self.assertEqual(json.loads(handoff_output.getvalue())["manifest_kind"], "leaf_agent_handoff_contract")


if __name__ == "__main__":
    unittest.main()
