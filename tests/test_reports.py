import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Optional

from tools.leaf_author.authoring import advance_run, confirm_plan, start_new_case
from tools.leaf_author.batch_registry import create_batch
from tools.leaf_author.device_probe import ProbeCommandResult, select_real_device
from tools.leaf_author.run_audit import audit_batch
from tools.leaf_author.reports import report_batch, report_run
from tools.leaf_author.ui_tree_diagnostics import inspect_ui_tree
from tools.leaf_author.workflow_diagnostics import inspect_workflow_state


class ReportTests(unittest.TestCase):
    def test_report_run_summarizes_phase_quality_gate_and_next_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-run")
            confirm_plan(root, "report-run")
            advance_run(root, "report-run")

            result = report_run(root, "report-run")

            self.assertEqual(result["run_id"], "report-run")
            self.assertEqual(result["current_phase"], "complete")
            self.assertEqual(result["latest_quality_gate"], "DRAFT_STATIC_PASS")
            self.assertEqual(result["user_action_required"], False)
            self.assertEqual(result["next_command"], "")
            self.assertIsNone(result["real_device_preflight"])
            self.assertIn("pytest_result", result["evidence"])
            self.assertIn("team_export_manifest", result["evidence"])

    def test_report_run_marks_plan_confirmation_needed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-wait")

            result = report_run(root, "report-wait")

            self.assertEqual(result["current_phase"], "plan")
            self.assertEqual(result["user_action_required"], True)
            self.assertEqual(result["user_checkpoint"], "first_plan_confirmation")
            self.assertIn("confirm", result["operator_message"].lower())
            self.assertEqual(result["decision_contract"]["target_policy"]["scope"], "system_app_only")
            self.assertIn("test hap", result["decision_contract"]["target_policy"]["forbidden_terms"])
            self.assertEqual(result["decision_contract"]["agent_mode"], "orchestrator")
            self.assertEqual(result["action_route"]["phase"], "plan")
            self.assertEqual(result["action_route"]["next_action"], "present_plan_for_confirmation")
            self.assertEqual(result["action_route"]["agent_owner"], "leaf-test-author")
            self.assertEqual(result["action_route"]["agent_mode"], "orchestrator")
            self.assertEqual(result["action_route"]["user_checkpoint"], "first_plan_confirmation")
            self.assertEqual(result["action_route"]["user_loop"]["position"], "approve_plan")
            self.assertEqual(result["action_route"]["command"], "python3 -m tools.leaf_author report-run <run_id>")

    def test_report_run_includes_workflow_diagnostics_evidence_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机", run_id="report-diag")
            inspect_workflow_state(root, "report-diag")

            result = report_run(root, "report-diag")

            self.assertEqual(result["evidence"]["workflow_diagnostics"], ".leaf/runs/report-diag/workflow_diagnostics.json")

    def test_report_run_returns_repair_prompt_for_unreadable_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "坏 workflow", run_id="report-unreadable")
            (root / ".leaf" / "runs" / "report-unreadable" / "workflow.json").write_text("", encoding="utf-8")
            inspect_workflow_state(root, "report-unreadable")

            result = report_run(root, "report-unreadable")

            self.assertEqual(result["current_phase"], "unreadable")
            self.assertEqual(result["next_action"], "repair_workflow")
            self.assertEqual(result["user_checkpoint"], "manual_operator_decision")
            self.assertEqual(result["user_loop"]["position"], "manual_triage")
            self.assertEqual(result["decision_contract"]["context_slice"], ["workflow"])
            self.assertEqual(result["evidence"]["workflow_diagnostics"], ".leaf/runs/report-unreadable/workflow_diagnostics.json")
            self.assertIn("error", result)

    def test_report_run_uses_domain_runtime_quality_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-runtime")
            confirm_plan(root, "report-runtime")
            run_dir = root / ".leaf" / "runs" / "report-runtime"
            (run_dir / "pytest_result.json").write_text(json.dumps({"quality_gate": "DRAFT_STATIC_PASS"}) + "\n", encoding="utf-8")
            (run_dir / "camera_direct_smoke.json").write_text(json.dumps({"quality_gate": "CAMERA_DIRECT_SMOKE_PASS"}) + "\n", encoding="utf-8")
            workflow = json.loads((run_dir / "workflow.json").read_text(encoding="utf-8"))
            workflow["artifacts"]["pytest_result"] = ".leaf/runs/report-runtime/pytest_result.json"
            workflow["artifacts"]["camera_direct_smoke"] = ".leaf/runs/report-runtime/camera_direct_smoke.json"
            workflow["current_phase"] = "complete"
            (run_dir / "workflow.json").write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            result = report_run(root, "report-runtime")

            self.assertEqual(result["latest_quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")

    def test_report_run_real_device_checkpoint_recommends_runtime_mode_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-real")
            confirm_plan(root, "report-real")
            run_dir = root / ".leaf" / "runs" / "report-real"
            workflow = json.loads((run_dir / "workflow.json").read_text(encoding="utf-8"))
            workflow["current_phase"] = "e2e_ready"
            (run_dir / "workflow.json").write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            result = report_run(root, "report-real")

            self.assertEqual(result["user_checkpoint"], "real_device_confirmation")
            self.assertEqual(
                result["next_command"],
                "python3 -m tools.leaf_author advance report-real --run-real --runtime-mode direct_smoke --serial <serial>",
            )

    def test_report_run_surfaces_real_device_approval_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-approval")
            confirm_plan(root, "report-approval")

            blocked = advance_run(root, "report-approval", run_real=True, runtime_mode="capture_e2e", serial="SERIAL123")
            result = report_run(root, "report-approval")

            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(result["user_checkpoint"], "real_device_confirmation")
            self.assertEqual(result["user_action_required"], True)
            self.assertEqual(result["user_loop"]["position"], "approve_real_device")
            self.assertEqual(result["user_loop"]["required_input"], "approve_camera_capture_e2e")
            self.assertEqual(result["decision_contract"]["agent_owner"], "leaf-test-author")
            self.assertEqual(result["decision_contract"]["context_slice"], ["workflow", "real_device_approval"])
            self.assertEqual(result["decision_contract"]["target_policy"]["scope"], "system_app_only")
            self.assertIn("install_hap", result["decision_contract"]["target_policy"]["forbidden_terms"])
            self.assertEqual(result["operator_message"], result["approval_required"]["operator_message"])
            self.assertIn("real_device_approval", result["evidence"])
            self.assertEqual(result["approval_required"]["required_approval_token"], "approve_camera_capture_e2e")
            self.assertEqual(result["approval_required"]["decision_contract"]["agent_mode"], "orchestrator")
            self.assertEqual(result["approval_required"]["decision_contract"]["handoff_required"], False)
            self.assertEqual(result["approval_required"]["user_loop"]["position"], "approve_real_device")
            self.assertIn("--approval-token approve_camera_capture_e2e", result["next_command"])

    def test_report_run_clears_real_device_approval_after_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-approved")
            confirm_plan(root, "report-approved")
            advance_run(root, "report-approved", run_real=True, runtime_mode="capture_e2e", serial="SERIAL123")
            approval_path = root / ".leaf" / "runs" / "report-approved" / "real_device_approval.json"
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
            approval["status"] = "approved"
            approval["next_action"] = "run_real_device_runtime"
            approval_path.write_text(json.dumps(approval, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            result = report_run(root, "report-approved")

            self.assertIsNone(result["approval_required"])
            self.assertNotIn("--approval-token", result["next_command"])

    def test_report_run_ignores_stale_approval_blocker_after_run_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-stale-approval")
            confirm_plan(root, "report-stale-approval")
            advance_run(root, "report-stale-approval", run_real=True, runtime_mode="capture_e2e", serial="SERIAL123")
            workflow_path = root / ".leaf" / "runs" / "report-stale-approval" / "workflow.json"
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
            team_manifest = root / ".leaf" / "runs" / "report-stale-approval" / "team_export_manifest.json"
            team_manifest.write_text(json.dumps({"status": "exported"}) + "\n", encoding="utf-8")
            workflow["current_phase"] = "complete"
            workflow["artifacts"]["team_export_manifest"] = ".leaf/runs/report-stale-approval/team_export_manifest.json"
            workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            result = report_run(root, "report-stale-approval")

            self.assertEqual(result["current_phase"], "complete")
            self.assertFalse(result["user_action_required"])
            self.assertIsNone(result["approval_required"])
            self.assertEqual(result["next_command"], "")

    def test_report_run_surfaces_real_device_input_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-input")
            confirm_plan(root, "report-input")
            blocked = advance_run(root, "report-input", run_real=True, runtime_mode="direct_smoke")

            result = report_run(root, "report-input")

            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(result["user_action_required"], True)
            self.assertEqual(result["user_loop"]["position"], "provide_target_inputs")
            self.assertEqual(result["input_required"]["missing"], ["serial"])
            self.assertEqual(result["input_required"]["decision_contract"]["agent_mode"], "orchestrator")
            self.assertEqual(result["input_required"]["decision_contract"]["handoff_required"], False)
            self.assertEqual(result["input_required"]["user_loop"]["required_input"], "--serial <serial>")
            self.assertIn("real_device_input", result["evidence"])
            self.assertIn("--serial <serial>", result["next_command"])
            self.assertNotIn("--approval-token", result["next_command"])

    def test_report_run_surfaces_gui_subagent_mode_for_gui_context_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-agent-mode")
            confirm_plan(root, "report-agent-mode")
            run_dir = root / ".leaf" / "runs" / "report-agent-mode"
            (run_dir / "pytest_result.json").write_text(json.dumps({"quality_gate": "DRAFT_STATIC_PASS"}) + "\n", encoding="utf-8")
            workflow = json.loads((run_dir / "workflow.json").read_text(encoding="utf-8"))
            workflow["current_phase"] = "pytest_ran"
            workflow["artifacts"]["pytest_result"] = ".leaf/runs/report-agent-mode/pytest_result.json"
            (run_dir / "workflow.json").write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            result = report_run(root, "report-agent-mode")

            self.assertEqual(result["decision_contract"]["agent_owner"], "leaf-gui-agent")
            self.assertEqual(result["decision_contract"]["agent_mode"], "focused_subagent")
            self.assertEqual(result["context_manifest"]["agent_owner"], "leaf-gui-agent")
            self.assertEqual(result["context_manifest"]["agent_mode"], "focused_subagent")
            self.assertEqual(result["context_manifest"]["handoff_required"], True)

    def test_report_run_surfaces_real_device_preflight_after_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-preflight")
            confirm_plan(root, "report-preflight")
            layout_path = "/data/local/tmp/layout_123.json"

            def runner(args, timeout_s):
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == [
                    "/sdk/hdc",
                    "-t",
                    "SERIAL123",
                    "shell",
                    "aa",
                    "start",
                    "-a",
                    "com.huawei.hmos.camera.MainAbility",
                    "-b",
                    "com.huawei.hmos.camera",
                    "-m",
                    "phone",
                ]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    return ProbeCommandResult(0, '{"attributes":{"bundleName":"com.huawei.hmos.camera","abilityName":"com.huawei.hmos.camera.MainAbility","text":"相机"},"children":[]}\n', "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            advance_run(root, "report-preflight", hdc_runner=runner, serial="SERIAL123", run_real=True, runtime_mode="direct_smoke", hdc_path="/sdk/hdc")

            result = report_run(root, "report-preflight")

            self.assertEqual(result["current_phase"], "complete")
            self.assertEqual(result["real_device_preflight"]["status"], "ready")
            self.assertEqual(result["real_device_preflight"]["runtime_mode"], "direct_smoke")
            self.assertEqual(result["real_device_preflight"]["serial"], "SERIAL123")
            self.assertEqual(result["real_device_preflight"]["approval_status"], "not_required")
            self.assertEqual(result["real_device_preflight"]["input_status"], "ready")
            self.assertEqual(result["real_device_preflight"]["decision_contract"]["agent_owner"], "leaf-test-author")
            self.assertEqual(result["real_device_preflight"]["decision_contract"]["agent_mode"], "orchestrator")
            self.assertEqual(result["real_device_preflight"]["decision_contract"]["handoff_required"], False)
            self.assertEqual(result["real_device_preflight"]["decision_contract"]["required_inputs"], ["run_id", "workflow", "decision_contract"])
            self.assertEqual(result["real_device_preflight"]["decision_contract"]["subagent_boundary"], "workflow_orchestration")
            self.assertEqual(result["real_device_preflight"]["decision_contract"]["target_policy"]["scope"], "system_app_only")
            self.assertIn("app hap", result["real_device_preflight"]["decision_contract"]["target_policy"]["forbidden_terms"])
            self.assertEqual(result["real_device_preflight"]["user_loop"]["position"], "observe_real_device_execution")
            self.assertEqual(result["runtime_evidence_summary"]["artifact"], ".leaf/runs/report-preflight/camera_direct_smoke.json")
            self.assertEqual(result["runtime_evidence_summary"]["quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")
            self.assertEqual(result["runtime_evidence_summary"]["schema_status"], "complete")
            self.assertEqual(result["runtime_evidence_summary"]["missing_required_fields"], [])
            self.assertEqual(result["runtime_evidence_summary"]["ui_snapshot_ref_count"], 1)
            self.assertEqual(result["runtime_evidence_summary"]["ui_snapshots"][0]["phase"], "after_launch")
            self.assertTrue((root / result["runtime_evidence_summary"]["ui_snapshots"][0]["raw_path"]).is_file())
            self.assertTrue((root / result["runtime_evidence_summary"]["ui_snapshots"][0]["index_path"]).is_file())
            self.assertIn("real_device_preflight", result["evidence"])
            self.assertIn("camera_direct_smoke", result["evidence"])

    def test_report_run_includes_gui_handoff_summary_when_ui_tree_diagnostics_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-gui-handoff")
            confirm_plan(root, "report-gui-handoff")
            layout_path = "/data/local/tmp/layout_123.json"

            def runner(args, timeout_s):
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "aa", "start", "-a", "com.huawei.hmos.camera.MainAbility", "-b", "com.huawei.hmos.camera", "-m", "phone"]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    return ProbeCommandResult(0, '{"attributes":{"bundleName":"com.huawei.hmos.camera","abilityName":"com.huawei.hmos.camera.MainAbility","text":"相机"},"children":[]}\n', "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            advance_run(root, "report-gui-handoff", hdc_runner=runner, serial="SERIAL123", run_real=True, runtime_mode="direct_smoke", hdc_path="/sdk/hdc")
            inspect_ui_tree(root, "report-gui-handoff", text="相机")

            result = report_run(root, "report-gui-handoff")

            self.assertEqual(result["gui_handoff"]["artifact"], ".leaf/runs/report-gui-handoff/ui_tree_diagnostics.json")
            self.assertEqual(result["gui_handoff"]["agent_owner"], "leaf-gui-agent")
            self.assertEqual(result["gui_handoff"]["agent_mode"], "focused_subagent")
            self.assertEqual(result["gui_handoff"]["handoff_required"], True)
            self.assertEqual(result["gui_handoff"]["subagent_boundary"], "read_only_gui_context")
            self.assertEqual(result["gui_handoff"]["attention_boundary"], "one_active_run")
            self.assertEqual(result["gui_handoff"]["context_slice"], ["workflow", "runtime_evidence", "ui_tree"])
            self.assertEqual(result["gui_handoff"]["snapshot_count"], 1)
            self.assertEqual(result["gui_handoff"]["target_policy"]["scope"], "system_app_only")
            self.assertEqual(result["gui_handoff"]["contract_status"], "ready")
            self.assertEqual(result["gui_handoff"]["contract_issues"], [])
            self.assertEqual(result["gui_handoff"]["ui_tree_summary"]["snapshot_count"], 1)
            self.assertEqual(result["gui_handoff"]["ui_tree_summary"]["total_candidates"], 1)
            candidate = result["gui_handoff"]["ui_tree_summary"]["candidate_previews"][0]
            self.assertEqual(candidate["phase"], "after_launch")
            self.assertEqual(candidate["text"], "相机")
            self.assertIn("id", candidate)
            self.assertIn("type", candidate)
            self.assertIn("clickable", candidate)
            self.assertEqual(result["gui_handoff"]["ui_tree_summary"]["index_statuses"], ["ready"])
            self.assertEqual(result["gui_handoff"]["ui_tree_summary"]["foregrounds"][0]["bundle"], "com.huawei.hmos.camera")
            self.assertEqual(result["gui_handoff"]["ui_tree_summary"]["snapshots"][0]["phase"], "after_launch")
            self.assertEqual(result["gui_handoff"]["ui_tree_summary"]["snapshots"][0]["node_count"], 1)
            snapshot_candidate = result["gui_handoff"]["ui_tree_summary"]["snapshots"][0]["candidate_previews"][0]
            self.assertEqual(snapshot_candidate["text"], "相机")
            self.assertEqual(result["evidence"]["ui_tree_diagnostics"], ".leaf/runs/report-gui-handoff/ui_tree_diagnostics.json")

    def test_report_run_marks_gui_handoff_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-gui-drift")
            confirm_plan(root, "report-gui-drift")
            layout_path = "/data/local/tmp/layout_123.json"

            def runner(args, timeout_s):
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "aa", "start", "-a", "com.huawei.hmos.camera.MainAbility", "-b", "com.huawei.hmos.camera", "-m", "phone"]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    return ProbeCommandResult(0, '{"attributes":{"bundleName":"com.huawei.hmos.camera","abilityName":"com.huawei.hmos.camera.MainAbility","text":"相机"},"children":[]}\n', "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            advance_run(root, "report-gui-drift", hdc_runner=runner, serial="SERIAL123", run_real=True, runtime_mode="direct_smoke", hdc_path="/sdk/hdc")
            diagnostics = inspect_ui_tree(root, "report-gui-drift")
            diagnostics["handoff"]["context_slice"] = ["workflow"]
            (root / diagnostics["artifact"]).write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            result = report_run(root, "report-gui-drift")

            self.assertEqual(result["gui_handoff"]["contract_status"], "drift")
            self.assertIn("context_slice must include ui_tree", result["gui_handoff"]["contract_issues"])

    def test_report_run_surfaces_missing_runtime_evidence_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-runtime-evidence-missing")
            confirm_plan(root, "report-runtime-evidence-missing")
            run_dir = root / ".leaf" / "runs" / "report-runtime-evidence-missing"
            (run_dir / "real_device_preflight.json").write_text(
                json.dumps(
                    {
                        "status": "ready",
                        "runtime_mode": "direct_smoke",
                        "serial": "SERIAL123",
                        "approval_status": "not_required",
                        "input_status": "ready",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "camera_direct_smoke.json").write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "quality_gate": "CAMERA_DIRECT_SMOKE_PASS",
                        "evidence": {"layout_verified": True},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            workflow_path = run_dir / "workflow.json"
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
            workflow["current_phase"] = "complete"
            workflow["artifacts"]["real_device_preflight"] = ".leaf/runs/report-runtime-evidence-missing/real_device_preflight.json"
            workflow["artifacts"]["camera_direct_smoke"] = ".leaf/runs/report-runtime-evidence-missing/camera_direct_smoke.json"
            workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            result = report_run(root, "report-runtime-evidence-missing")

            self.assertEqual(result["runtime_evidence_summary"]["schema_status"], "missing_fields")
            self.assertEqual(result["runtime_evidence_summary"]["missing_required_fields"], ["bundle_verified", "ability_verified", "ui_snapshot_refs"])

    def test_report_run_includes_device_selection_evidence_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-selection")

            def runner(args, timeout_s):
                if args == ["hdc", "list", "targets"]:
                    return ProbeCommandResult(0, "SERIAL123\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "MateTest\n", "")
                if args == ["hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "14\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            select_real_device(root, "report-selection", hdc_runner=runner)

            result = report_run(root, "report-selection")

            self.assertEqual(result["device_selection"]["status"], "selected")
            self.assertEqual(result["device_selection"]["serial"], "SERIAL123")
            self.assertEqual(result["evidence"]["device_selection"], ".leaf/runs/report-selection/device_selection.json")

    def test_report_batch_summarizes_runs_and_next_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-wait")
            start_new_case(root, "camera", "打开相机；切拍照模式；点击拍照", run_id="report-safe")
            confirm_plan(root, "report-safe")
            create_batch(root, "report-batch", ["report-wait", "report-safe"])

            result = report_batch(root, "report-batch")

            self.assertEqual(result["batch_id"], "report-batch")
            self.assertEqual(result["total_runs"], 2)
            self.assertEqual(result["summary"]["waiting_for_user"], 1)
            self.assertEqual(result["summary"]["safe_to_auto_continue"], 1)
            self.assertEqual(result["next_run_focus"]["run_id"], "report-safe")
            self.assertEqual(result["runs"][0]["run_id"], "report-wait")
            self.assertEqual(result["runs"][0]["decision_contract"]["target_policy"]["scope"], "system_app_only")
            self.assertIn("test hap", result["runs"][0]["decision_contract"]["target_policy"]["forbidden_terms"])

    def test_report_batch_isolates_unreadable_run_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机", run_id="report-good")
            start_new_case(root, "camera", "坏 workflow", run_id="report-bad")
            create_batch(root, "report-batch-unreadable", ["report-good", "report-bad"])
            (root / ".leaf" / "runs" / "report-bad" / "workflow.json").write_text("", encoding="utf-8")

            result = report_batch(root, "report-batch-unreadable")

            self.assertEqual(result["total_runs"], 2)
            self.assertEqual(result["summary"]["blocked_or_inspect"], 1)
            bad = [run for run in result["runs"] if run["run_id"] == "report-bad"][0]
            self.assertEqual(bad["current_phase"], "unreadable")
            self.assertEqual(bad["next_action"], "repair_workflow")
            self.assertEqual(bad["user_checkpoint"], "manual_operator_decision")
            self.assertIn("error", bad)
            self.assertEqual(result["next_run_focus"]["run_id"], "report-bad")

    def test_report_batch_includes_lightweight_real_device_preflight_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="batch-preflight")
            confirm_plan(root, "batch-preflight")
            layout_path = "/data/local/tmp/layout_123.json"

            def runner(args, timeout_s):
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "aa", "start", "-a", "com.huawei.hmos.camera.MainAbility", "-b", "com.huawei.hmos.camera", "-m", "phone"]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    return ProbeCommandResult(0, '{"attributes":{"bundleName":"com.huawei.hmos.camera","abilityName":"com.huawei.hmos.camera.MainAbility","text":"相机"},"children":[]}\n', "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            advance_run(root, "batch-preflight", hdc_runner=runner, serial="SERIAL123", run_real=True, runtime_mode="direct_smoke", hdc_path="/sdk/hdc")
            create_batch(root, "batch-preflight-report", ["batch-preflight"])

            result = report_batch(root, "batch-preflight-report")

            self.assertEqual(result["real_device_summary"]["total_preflights"], 1)
            self.assertEqual(result["real_device_summary"]["serials"], ["SERIAL123"])
            self.assertEqual(result["real_device_summary"]["runtime_modes"], ["direct_smoke"])
            self.assertEqual(result["real_device_summary"]["statuses"], ["ready"])
            self.assertEqual(result["runtime_evidence_summary"]["total"], 1)
            self.assertEqual(result["runtime_evidence_summary"]["schema_statuses"], {"complete": 1})
            self.assertEqual(result["runtime_evidence_summary"]["quality_gates"], ["CAMERA_DIRECT_SMOKE_PASS"])
            self.assertEqual(result["runtime_evidence_summary"]["ui_snapshot_ref_count"], 1)
            preflight = result["runs"][0]["real_device_preflight"]
            self.assertEqual(preflight["runtime_mode"], "direct_smoke")
            self.assertEqual(preflight["status"], "ready")
            self.assertEqual(preflight["risk_level"], "read_only_probe")
            self.assertEqual(preflight["approval_status"], "not_required")
            self.assertEqual(preflight["input_status"], "ready")
            self.assertEqual(result["runs"][0]["runtime_evidence"]["schema_status"], "complete")
            self.assertEqual(result["runs"][0]["runtime_evidence"]["ui_snapshot_ref_count"], 1)
            self.assertEqual(result["runs"][0]["runtime_evidence"]["ui_snapshots"][0]["phase"], "after_launch")
            self.assertEqual(result["runs"][0]["action_route"]["phase"], "complete")
            self.assertEqual(result["runs"][0]["action_route"]["next_action"], "complete")
            self.assertEqual(result["runs"][0]["action_route"]["command"], "")

    def test_report_batch_summarizes_real_device_risk_and_approval_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_report_preflight(root, "report-batch-direct-risk", runtime_mode="direct_smoke")
            _write_report_preflight(
                root,
                "report-batch-capture-risk",
                runtime_mode="capture_e2e",
                required_approval_token="approve_camera_capture_e2e",
            )
            create_batch(root, "report-batch-risk", ["report-batch-direct-risk", "report-batch-capture-risk"])

            result = report_batch(root, "report-batch-risk")

            self.assertEqual(result["real_device_summary"]["total_preflights"], 2)
            self.assertEqual(result["real_device_summary"]["runtime_modes"], ["capture_e2e", "direct_smoke"])
            self.assertEqual(result["real_device_summary"]["risk_levels"], ["device_state_mutation", "read_only_probe"])
            self.assertEqual(result["real_device_summary"]["mutates_device_state"], 1)
            self.assertEqual(result["real_device_summary"]["read_only"], 1)
            self.assertEqual(result["real_device_summary"]["approval_statuses"], ["approved", "not_required"])
            self.assertEqual(result["real_device_summary"]["approval_required"], 1)
            self.assertEqual(result["real_device_summary"]["approval_approved"], 1)
            self.assertEqual(result["real_device_summary"]["approval_tokens"], ["approve_camera_capture_e2e"])

    def test_report_batch_includes_gui_handoff_summary_from_batch_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-batch-gui")
            confirm_plan(root, "report-batch-gui")
            layout_path = "/data/local/tmp/layout_123.json"

            def runner(args, timeout_s):
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.product.model"]:
                    return ProbeCommandResult(0, "ohos\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "param", "get", "const.ohos.apiversion"]:
                    return ProbeCommandResult(0, "26\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "bm", "dump", "-n", "com.huawei.hmos.camera"]:
                    return ProbeCommandResult(0, '"bundleName": "com.huawei.hmos.camera",\n"moduleName": "phone",\n', "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "aa", "start", "-a", "com.huawei.hmos.camera.MainAbility", "-b", "com.huawei.hmos.camera", "-m", "phone"]:
                    return ProbeCommandResult(0, "start ability successfully\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "uitest", "dumpLayout"]:
                    return ProbeCommandResult(0, f"DumpLayout saved to:{layout_path}\n", "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "cat", layout_path]:
                    return ProbeCommandResult(0, '{"attributes":{"bundleName":"com.huawei.hmos.camera","abilityName":"com.huawei.hmos.camera.MainAbility","text":"相机"},"children":[]}\n', "")
                if args == ["/sdk/hdc", "-t", "SERIAL123", "shell", "hilog", "-x"]:
                    return ProbeCommandResult(0, "camera foreground log\n", "")
                return ProbeCommandResult(1, "", f"unexpected {args}")

            advance_run(root, "report-batch-gui", hdc_runner=runner, serial="SERIAL123", run_real=True, runtime_mode="direct_smoke", hdc_path="/sdk/hdc")
            inspect_ui_tree(root, "report-batch-gui")
            create_batch(root, "report-batch-gui", ["report-batch-gui"])
            audit_batch(root, "report-batch-gui")

            result = report_batch(root, "report-batch-gui")

            self.assertEqual(result["gui_handoff_summary"]["total_artifacts"], 1)
            self.assertEqual(result["gui_handoff_summary"]["ready"], 1)
            self.assertEqual(result["gui_handoff_summary"]["failed"], 0)
            self.assertEqual(result["gui_handoff_summary"]["attention_boundary"], "one_active_run")
            self.assertEqual(result["ui_tree_summary"]["total_snapshots"], 1)
            self.assertEqual(result["ui_tree_summary"]["total_candidates"], 0)
            self.assertEqual(result["ui_tree_summary"]["index_statuses"], ["ready"])
            self.assertEqual(result["ui_tree_summary"]["foreground_bundles"], ["com.huawei.hmos.camera"])
            self.assertEqual(result["evidence"]["batch_audit"], ".leaf/batches/report-batch-gui/batch_audit.json")

    def test_cli_report_commands_output_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            start_new_case(root, "camera", "打开相机；点击拍照", run_id="report-cli")
            create_batch(root, "report-batch", ["report-cli"])

            from tools.leaf_author.__main__ import main

            run_output = StringIO()
            with redirect_stdout(run_output):
                run_exit = main(["report-run", "report-cli", "--root", str(root)])
            run_payload = json.loads(run_output.getvalue())

            batch_output = StringIO()
            with redirect_stdout(batch_output):
                batch_exit = main(["report-batch", "report-batch", "--root", str(root)])
            batch_payload = json.loads(batch_output.getvalue())

            self.assertEqual(run_exit, 0)
            self.assertEqual(batch_exit, 0)
            self.assertEqual(run_payload["run_id"], "report-cli")
            self.assertEqual(batch_payload["batch_id"], "report-batch")


def _write_report_preflight(
    root: Path,
    run_id: str,
    *,
    runtime_mode: str,
    required_approval_token: Optional[str] = None,
) -> None:
    start_new_case(root, "camera", "打开相机；点击拍照", run_id=run_id)
    confirm_plan(root, run_id)
    run_dir = root / ".leaf" / "runs" / run_id
    risk_level = "device_state_mutation" if required_approval_token else "read_only_probe"
    preflight_path = run_dir / "real_device_preflight.json"
    preflight_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "artifact_kind": "real_device_runtime_preflight",
                "run_id": run_id,
                "domain": "camera",
                "runtime_mode": runtime_mode,
                "status": "ready",
                "serial": "SERIAL123",
                "serial_source": "explicit_arg",
                "risk_level": risk_level,
                "mutates_device_state": bool(required_approval_token),
                "approval_status": "approved" if required_approval_token else "not_required",
                "required_approval_token": required_approval_token,
                "approval_token": required_approval_token,
                "input_status": "ready",
                "next_action": "run_real_device_runtime",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    workflow_path = run_dir / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["artifacts"]["real_device_preflight"] = str(preflight_path.relative_to(root))
    workflow["current_phase"] = "complete"
    workflow_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
