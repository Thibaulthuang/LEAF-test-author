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
        self.assertEqual(result["target_policy"], "system_app_only")
        self.assertEqual(result["real_device_gate_status"], "stable")
        self.assertEqual(result["runtime_registry_status"], "stable")
        self.assertIn("leaf-test-author", result["agent_owners"])
        self.assertIn("leaf-gui-agent", result["agent_owners"])
        self.assertEqual(result["user_checkpoints"]["first_plan_confirmation"], ["plan"])
        self.assertEqual(result["user_checkpoints"]["real_device_confirmation"], ["e2e_ready"])

    def test_agent_handoff_contract_summarizes_context_slices_and_auto_safe_boundaries(self):
        contract = build_agent_handoff_contract()

        self.assertEqual(contract["manifest_kind"], "leaf_agent_handoff_contract")
        self.assertEqual(contract["trigger_stability"]["authoritative_source"], "workflow.json")
        self.assertEqual(contract["target_policy"]["scope"], "system_app_only")
        self.assertIn("pytest_ran", contract["agents"]["leaf-gui-agent"])
        self.assertIn("ui_tree", contract["context_slices"]["pytest_ran"])
        self.assertIn("hypium_draft", contract["auto_safe_phases"])
        self.assertIn("first_plan_confirmation", contract["resume_policy"]["never_auto_cross"])
        self.assertEqual(contract["real_device_gates"]["approval"]["user_loop"]["position"], "approve_real_device")
        self.assertEqual(contract["real_device_gates"]["approval"]["user_loop"]["required_input"], "<approval-token>")
        self.assertEqual(contract["real_device_gates"]["preflight"]["decision_contract"]["agent_owner"], "leaf-test-author")
        self.assertEqual(contract["runtime_registry"]["camera"]["default_real_device_runtime_mode"], "direct_smoke")
        self.assertEqual(contract["agent_modes"]["leaf-test-author"], "orchestrator")
        self.assertEqual(contract["agent_modes"]["tools.leaf_author"], "deterministic_tool")
        self.assertEqual(contract["agent_modes"]["leaf-gui-agent"], "focused_subagent")
        self.assertEqual(contract["handoff_rules"]["leaf-gui-agent"]["handoff_required"], True)
        self.assertIn("run_id", contract["handoff_rules"]["leaf-gui-agent"]["required_inputs"])
        self.assertIn("context_manifest", contract["handoff_rules"]["leaf-gui-agent"]["required_inputs"])
        self.assertIn("specific_question", contract["handoff_rules"]["leaf-gui-agent"]["required_inputs"])
        self.assertEqual(contract["handoff_rules"]["tools.leaf_author"]["handoff_required"], False)
        self.assertIn("first_plan_confirmation", contract["user_loop_rules"]["blocking_checkpoints"])
        self.assertIn("real_device_confirmation", contract["user_loop_rules"]["blocking_checkpoints"])
        self.assertEqual(contract["user_loop_rules"]["checkpoint_owner"], "user")
        self.assertEqual(contract["user_loop_rules"]["auto_continue_requires"], ["confirmed_plan", "auto_safe", "no_user_checkpoint"])
        self.assertEqual(contract["action_routes"]["plan"]["next_action"], "present_plan_for_confirmation")
        self.assertEqual(contract["action_routes"]["plan"]["agent_owner"], "leaf-test-author")
        self.assertEqual(contract["action_routes"]["plan"]["agent_mode"], "orchestrator")
        self.assertEqual(contract["action_routes"]["plan"]["user_loop"]["position"], "approve_plan")
        self.assertEqual(contract["action_routes"]["plan"]["command"], "python3 -m tools.leaf_author report-run <run_id>")
        self.assertEqual(contract["action_routes"]["pytest_ran"]["next_action"], "collect_gui_context")
        self.assertEqual(contract["action_routes"]["pytest_ran"]["agent_owner"], "leaf-gui-agent")
        self.assertEqual(contract["action_routes"]["pytest_ran"]["agent_mode"], "focused_subagent")
        self.assertIn("ui_tree", contract["action_routes"]["pytest_ran"]["context_slice"])
        self.assertEqual(contract["action_routes"]["pytest_ran"]["command"], "python3 -m tools.leaf_author inspect-ui-tree <run_id>")
        self.assertEqual(contract["action_routes"]["e2e_ready"]["next_action"], "run_real_hypium")
        self.assertEqual(contract["action_routes"]["e2e_ready"]["user_checkpoint"], "real_device_confirmation")
        self.assertEqual(contract["action_routes"]["e2e_ready"]["user_loop"]["position"], "approve_real_device")
        self.assertEqual(contract["action_routes"]["e2e_ready"]["command"], "python3 -m tools.leaf_author report-run <run_id>")
        self.assertEqual(contract["action_routes"]["complete"]["next_action"], "complete")
        self.assertEqual(contract["action_routes"]["complete"]["command"], "")

    def test_phase_guard_rejects_hap_or_install_oriented_contract_language(self):
        contract = {
            "context_policy": {"attention_boundary": "one_active_run"},
            "resume_policy": {},
            "target_policy": {
                "scope": "system_app_only",
                "forbidden_terms": ["hap"],
            },
            "phases": {
                "plan": {
                    "user_checkpoint": "first_plan_confirmation",
                    "auto_safe": False,
                    "agent_owner": "leaf-test-author",
                    "trigger_source": "workflow.json",
                    "context_slice": ["workflow", "plan"],
                    "user_loop": {"position": "approve_plan", "required_input": "confirm or revise plan"},
                    "allowed_artifacts": ["workflow", "plan"],
                    "next_action": "prepare_test_hap",
                    "batch_focus_priority": 60,
                },
                "e2e_ready": {
                    "user_checkpoint": "real_device_confirmation",
                    "auto_safe": False,
                    "agent_owner": "leaf-test-author",
                    "trigger_source": "workflow.json",
                    "context_slice": ["workflow", "target_diagnostics"],
                    "user_loop": {"position": "approve_real_device", "required_input": "explicit real-device approval"},
                    "allowed_artifacts": ["target_diagnostics"],
                    "next_action": "install_hap_and_run",
                    "batch_focus_priority": 80,
                },
                "complete": {
                    "user_checkpoint": None,
                    "auto_safe": False,
                    "agent_owner": "leaf-test-author",
                    "trigger_source": "workflow.json",
                    "context_slice": ["workflow"],
                    "user_loop": {"position": "done", "required_input": ""},
                    "allowed_artifacts": [],
                    "next_action": "complete",
                    "batch_focus_priority": 1000,
                },
            },
        }

        result = validate_phase_contract(contract=contract, include_external_guards=False)

        self.assertEqual(result["status"], "unstable")
        self.assertIn("target_policy_forbidden_terms", result)
        self.assertIn("hap", result["target_policy_forbidden_terms"])
        self.assertTrue(any("forbidden system_app_only term" in issue for issue in result["issues"]))

    def test_cli_phase_guard_and_agent_handoff_contract_output_json(self):
        from tools.leaf_author.__main__ import main

        guard_output = StringIO()
        with redirect_stdout(guard_output):
            guard_exit = main(["phase-guard"])

        handoff_output = StringIO()
        with redirect_stdout(handoff_output):
            handoff_exit = main(["agent-handoff-contract"])

        real_device_output = StringIO()
        with redirect_stdout(real_device_output):
            real_device_exit = main(["real-device-contract"])

        runtime_output = StringIO()
        with redirect_stdout(runtime_output):
            runtime_exit = main(["runtime-registry-contract"])

        self.assertEqual(guard_exit, 0)
        self.assertEqual(json.loads(guard_output.getvalue())["status"], "stable")
        self.assertEqual(handoff_exit, 0)
        self.assertEqual(json.loads(handoff_output.getvalue())["manifest_kind"], "leaf_agent_handoff_contract")
        self.assertEqual(real_device_exit, 0)
        self.assertEqual(json.loads(real_device_output.getvalue())["manifest_kind"], "leaf_real_device_gate_contract")
        self.assertEqual(runtime_exit, 0)
        self.assertEqual(json.loads(runtime_output.getvalue())["manifest_kind"], "leaf_runtime_registry_contract")


if __name__ == "__main__":
    unittest.main()
