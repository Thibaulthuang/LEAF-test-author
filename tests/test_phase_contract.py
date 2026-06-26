import json
import tempfile
import unittest
from pathlib import Path

from tools.leaf_author.authoring import confirm_plan, resume_run, start_new_case
from tools.leaf_author.phase_contract import batch_focus_priority_for_run, decide_next_step, load_phase_contract, write_context_manifest
from tools.leaf_author.reports import report_run
from tools.leaf_author.workflow import load_workflow, save_workflow


class PhaseContractTests(unittest.TestCase):
    def test_contract_contains_agent_context_and_user_loop_metadata(self):
        contract = load_phase_contract()

        plan_phase = contract["phases"]["plan"]
        self.assertEqual(plan_phase["user_checkpoint"], "first_plan_confirmation")
        self.assertEqual(plan_phase["agent_owner"], "leaf-test-author")
        self.assertIn("workflow", plan_phase["context_slice"])
        self.assertEqual(plan_phase["auto_safe"], False)

        gui_phase = contract["phases"]["pytest_ran"]
        self.assertEqual(gui_phase["agent_owner"], "leaf-gui-agent")
        self.assertIn("ui_tree", gui_phase["context_slice"])

    def test_decision_uses_contract_instead_of_prompt_context(self):
        workflow = {
            "run_id": "contract-001",
            "current_phase": "hypium_draft",
            "confirmed_plan": True,
        }

        decision = decide_next_step(workflow)

        self.assertEqual(decision["next_action"], "validate_pytest_draft")
        self.assertEqual(decision["user_checkpoint"], None)
        self.assertEqual(decision["requires_user_confirmation"], False)
        self.assertEqual(decision["safe_to_auto_continue"], True)
        self.assertEqual(decision["agent_owner"], "tools.leaf_author")
        self.assertEqual(decision["trigger_source"], "workflow.json")

    def test_batch_focus_priority_comes_from_phase_contract(self):
        self.assertLess(
            batch_focus_priority_for_run({"current_phase": "hypium_draft", "next_action": "validate_pytest_draft"}),
            batch_focus_priority_for_run({"current_phase": "plan", "next_action": "present_plan_for_confirmation"}),
        )
        self.assertEqual(batch_focus_priority_for_run({"current_phase": "complete", "next_action": "complete"}), 1000)

    def test_decision_stops_at_user_checkpoint_even_with_auto_safe(self):
        workflow = {
            "run_id": "contract-002",
            "current_phase": "e2e_ready",
            "confirmed_plan": True,
        }

        decision = decide_next_step(workflow)

        self.assertEqual(decision["next_action"], "run_real_hypium")
        self.assertEqual(decision["user_checkpoint"], "real_device_confirmation")
        self.assertEqual(decision["requires_user_confirmation"], True)
        self.assertEqual(decision["safe_to_auto_continue"], False)
        self.assertEqual(decision["user_loop"]["position"], "approve_real_device")

    def test_resume_and_report_expose_contract_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机", run_id="contract-run")
            confirm_plan(root, "contract-run")
            workflow = load_workflow(root, "contract-run")
            workflow["current_phase"] = "pytest_ran"
            save_workflow(root, workflow)

            resume = resume_run(root, "contract-run")
            report = report_run(root, "contract-run")

            self.assertEqual(resume["next_action"], "collect_gui_context")
            self.assertEqual(resume["resume_summary"]["agent_owner"], "leaf-gui-agent")
            self.assertIn("ui_tree", resume["resume_summary"]["context_slice"])
            self.assertEqual(report["decision_contract"]["agent_owner"], "leaf-gui-agent")
            self.assertEqual(report["user_loop"]["position"], "observe_safe_local_progress")
            self.assertEqual(report["evidence"]["context_manifest"], ".leaf/runs/contract-run/context_manifest.json")

    def test_context_manifest_records_attention_boundary_and_artifact_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机", run_id="manifest-run")
            confirm_plan(root, "manifest-run")

            result = write_context_manifest(root, "manifest-run")
            payload = (root / result["context_manifest_path"]).read_text(encoding="utf-8")

            self.assertIn('"manifest_kind": "run_context_manifest"', payload)
            self.assertIn('"attention_boundary": "one_active_run"', payload)
            self.assertIn('"agent_owner": "tools.leaf_author"', payload)
            self.assertIn('"context_manifest"', payload)
            workflow = load_workflow(root, "manifest-run")
            self.assertEqual(workflow["artifacts"]["context_manifest"], ".leaf/runs/manifest-run/context_manifest.json")

    def test_context_manifest_contains_agent_handoff_and_user_loop_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机", run_id="handoff-manifest")
            confirm_plan(root, "handoff-manifest")
            workflow = load_workflow(root, "handoff-manifest")
            workflow["current_phase"] = "pytest_ran"
            workflow["artifacts"]["pytest_result"] = ".leaf/runs/handoff-manifest/pytest_result.json"
            result_path = root / ".leaf" / "runs" / "handoff-manifest" / "pytest_result.json"
            result_path.write_text('{"quality_gate": "DRAFT_STATIC_PASS"}\n', encoding="utf-8")
            save_workflow(root, workflow)

            result = write_context_manifest(root, "handoff-manifest")
            payload = json.loads((root / result["context_manifest_path"]).read_text(encoding="utf-8"))

            self.assertEqual(payload["handoff"]["from_agent"], "tools.leaf_author")
            self.assertEqual(payload["handoff"]["to_agent"], "leaf-gui-agent")
            self.assertEqual(payload["handoff"]["next_action"], "collect_gui_context")
            self.assertEqual(payload["handoff"]["attention_boundary"], "one_active_run")
            self.assertEqual(payload["handoff"]["artifact_loading"], "on_demand")
            self.assertEqual(payload["handoff"]["context_slice"], ["workflow", "pytest_result", "ui_tree"])
            self.assertEqual(payload["handoff"]["allowed_artifacts"], ["pytest_result"])
            self.assertEqual(payload["handoff"]["referenced_artifacts"]["pytest_result"], ".leaf/runs/handoff-manifest/pytest_result.json")
            self.assertEqual(payload["user_loop"]["position"], "observe_safe_local_progress")
            self.assertEqual(payload["user_loop"]["required_input"], "")
            self.assertEqual(payload["user_loop"]["user_checkpoint"], None)
            self.assertEqual(payload["user_loop"]["requires_user_confirmation"], False)
            self.assertEqual(payload["user_loop"]["safe_to_auto_continue"], True)

    def test_context_manifest_only_exposes_current_phase_context_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机", run_id="bounded-manifest")
            confirm_plan(root, "bounded-manifest")
            run_dir = root / ".leaf" / "runs" / "bounded-manifest"
            large_log = run_dir / "hilog.txt"
            large_log.write_text("large log", encoding="utf-8")
            workflow = load_workflow(root, "bounded-manifest")
            artifacts = dict(workflow["artifacts"])
            artifacts["hilog"] = ".leaf/runs/bounded-manifest/hilog.txt"
            workflow["artifacts"] = artifacts
            save_workflow(root, workflow)

            result = write_context_manifest(root, "bounded-manifest")
            payload = json.loads((root / result["context_manifest_path"]).read_text(encoding="utf-8"))

            self.assertIn("hypium", payload["referenced_artifacts"])
            self.assertNotIn("hilog", payload["referenced_artifacts"])


if __name__ == "__main__":
    unittest.main()
