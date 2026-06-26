import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools.leaf_author.opencode_contract import validate_opencode_contract


class OpenCodeContractTests(unittest.TestCase):
    def test_opencode_contract_validates_entrypoints_and_skill_boundaries(self):
        result = validate_opencode_contract(Path("."))

        self.assertEqual(result["status"], "stable")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["command_count"], 4)
        self.assertEqual(result["skill_count"], 4)
        self.assertIn("leaf-test-author", result["required_skills"])
        self.assertIn("leaf-gui-agent", result["required_skills"])
        self.assertEqual(result["target_policy"]["scope"], "system_app_only")
        self.assertIn("workflow.json", result["contract_sources"])
        self.assertIn("target-policy", result["contract_sources"])

    def test_opencode_contract_rejects_command_that_skips_author_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = root / ".opencode" / "commands"
            skills = root / ".opencode" / "skills" / "leaf-test-author"
            commands.mkdir(parents=True)
            skills.mkdir(parents=True)
            (commands / "leaf-new-case.md").write_text("# /leaf-new-case\n\nCall python directly.\n", encoding="utf-8")
            (skills / "SKILL.md").write_text("workflow.json target-policy user_loop context_manifest\n", encoding="utf-8")

            result = validate_opencode_contract(root)

            self.assertEqual(result["status"], "unstable")
            self.assertIn(".opencode/commands/leaf-new-case.md: must invoke leaf-test-author", result["issues"])

    def test_cli_opencode_contract_outputs_json(self):
        from tools.leaf_author.__main__ import main

        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["opencode-contract"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["manifest_kind"], "leaf_opencode_contract_guard")
        self.assertEqual(payload["status"], "stable")


if __name__ == "__main__":
    unittest.main()
