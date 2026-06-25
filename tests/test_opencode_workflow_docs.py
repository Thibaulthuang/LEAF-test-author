from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
