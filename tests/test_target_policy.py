import unittest
import json
from contextlib import redirect_stdout
from io import StringIO

from tools.leaf_author.target_policy import (
    default_target_policy,
    target_policy_forbidden_terms,
    target_policy_from_contract,
    with_target_policy,
)


class TargetPolicyTests(unittest.TestCase):
    def test_default_target_policy_is_system_app_only_and_copied(self):
        first = default_target_policy()
        second = default_target_policy()

        self.assertEqual(first["scope"], "system_app_only")
        self.assertIn("test hap", first["forbidden_terms"])
        self.assertIn("build_app_and_test", first["forbidden_terms"])
        self.assertIsNot(first, second)
        self.assertIsNot(first["forbidden_terms"], second["forbidden_terms"])

    def test_contract_target_policy_is_normalized(self):
        policy = target_policy_from_contract(
            {
                "target_policy": {
                    "scope": "system_app_only",
                    "forbidden_terms": ["HAP", "test hap", ""],
                }
            }
        )

        self.assertEqual(policy["scope"], "system_app_only")
        self.assertEqual(policy["forbidden_terms"], ["hap", "test hap"])
        self.assertEqual(target_policy_forbidden_terms(policy), ["hap", "test hap"])

    def test_missing_or_incomplete_policy_falls_back_to_default_terms(self):
        missing = target_policy_from_contract({})
        incomplete = target_policy_from_contract({"target_policy": {"scope": "system_app_only"}})

        self.assertEqual(missing, default_target_policy())
        self.assertEqual(incomplete, default_target_policy())

    def test_with_target_policy_adds_normalized_copy(self):
        decision = {"trigger_source": "workflow.json"}
        result = with_target_policy(decision, {"scope": "system_app_only", "forbidden_terms": ["HAP"]})

        self.assertEqual(result["trigger_source"], "workflow.json")
        self.assertEqual(result["target_policy"], {"scope": "system_app_only", "forbidden_terms": ["hap"]})
        self.assertNotIn("target_policy", decision)

    def test_cli_target_policy_outputs_shared_contract(self):
        from tools.leaf_author.__main__ import main

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["target-policy"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["manifest_kind"], "leaf_target_policy")
        self.assertEqual(payload["target_policy"]["scope"], "system_app_only")
        self.assertIn("test hap", payload["target_policy"]["forbidden_terms"])
        self.assertEqual(payload["usage"]["phase_decisions"], "tools.leaf_author.phase_contract")


if __name__ == "__main__":
    unittest.main()
