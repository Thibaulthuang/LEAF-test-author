import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.leaf_author.authoring import advance_run
from tools.leaf_author.runtime_registry import (
    classify_experience_result,
    experience_candidate_keys,
    quality_artifact_priority,
    real_device_next_command,
    resolve_runtime_mode,
    runtime_artifact_keys,
    run_domain_runtime,
)


class RuntimeRegistryTests(unittest.TestCase):
    def test_resolve_runtime_mode_keeps_legacy_camera_flags_compatible(self):
        self.assertEqual(resolve_runtime_mode(camera_direct=True, camera_capture=False), "direct_smoke")
        self.assertEqual(resolve_runtime_mode(camera_direct=False, camera_capture=True), "capture_e2e")
        self.assertIsNone(resolve_runtime_mode(camera_direct=False, camera_capture=False))

        with self.assertRaisesRegex(ValueError, "only one runtime mode"):
            resolve_runtime_mode(runtime_mode="direct_smoke", camera_direct=False, camera_capture=True)

    def test_run_domain_runtime_dispatches_camera_direct_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with patch(
                "tools.leaf_author.camera_smoke.run_camera_direct_smoke",
                return_value={"run_id": "runtime-direct", "quality_gate": "CAMERA_DIRECT_SMOKE_PASS"},
            ) as direct:
                result = run_domain_runtime(root, "runtime-direct", "camera", "direct_smoke", serial="SERIAL123", hdc_path="/sdk/hdc")

            self.assertEqual(result["stage"], "camera_direct_smoke")
            self.assertEqual(result["pass_quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")
            self.assertEqual(result["inspect_action"], "inspect_camera_direct_smoke")
            self.assertEqual(result["result"]["quality_gate"], "CAMERA_DIRECT_SMOKE_PASS")
            direct.assert_called_once()

    def test_run_domain_runtime_rejects_unknown_domain_mode_pair(self):
        with self.assertRaisesRegex(ValueError, "unsupported runtime mode"):
            run_domain_runtime(Path("."), "runtime-unknown", "display", "direct_smoke", serial="SERIAL123")

    def test_runtime_registry_classifies_camera_experience_without_core_camera_branch(self):
        direct = classify_experience_result("camera", {"status": "complete", "quality_gate": "CAMERA_DIRECT_SMOKE_PASS"})
        capture = classify_experience_result("camera", {"status": "complete", "quality_gate": "CAMERA_CAPTURE_E2E_PASS"})
        draft = classify_experience_result("camera", {"status": "draft_passed", "quality_gate": "DRAFT_STATIC_PASS"})

        self.assertEqual(direct["confidence"], 0.5)
        self.assertIn("direct smoke", direct["notes"][0])
        self.assertEqual(capture["confidence"], 0.65)
        self.assertIn("capture e2e", capture["notes"][0])
        self.assertEqual(draft["confidence"], 0.0)

    def test_runtime_registry_exposes_artifact_priority_for_experience_and_manifest(self):
        self.assertEqual(
            experience_candidate_keys("camera"),
            ["hypium_result", "camera_capture_e2e", "camera_direct_smoke", "pytest_result"],
        )
        self.assertIn("camera_direct_smoke", runtime_artifact_keys("camera"))
        self.assertEqual(experience_candidate_keys("display"), ["hypium_result", "pytest_result"])

    def test_runtime_registry_exposes_report_quality_priority(self):
        self.assertEqual(
            quality_artifact_priority("camera")[:4],
            ["camera_capture_e2e", "camera_direct_smoke", "hypium_result", "e2e_run"],
        )
        self.assertNotIn("camera_direct_smoke", quality_artifact_priority("display"))
        self.assertIn("pytest_result", quality_artifact_priority("display"))

    def test_runtime_registry_builds_real_device_next_command(self):
        self.assertEqual(
            real_device_next_command("run-123", "camera"),
            "python3 -m tools.leaf_author advance run-123 --run-real --runtime-mode direct_smoke --serial <serial>",
        )
        self.assertEqual(
            real_device_next_command("run-123", "display"),
            "python3 -m tools.leaf_author advance run-123 --run-real --serial <serial>",
        )

    def test_advance_run_can_use_generic_runtime_mode_for_camera_direct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / ".leaf" / "runs" / "runtime-mode"
            run_dir.mkdir(parents=True)
            workflow = {
                "schema_version": "1.0",
                "run_id": "runtime-mode",
                "owner": "leaf-test-author",
                "domain": "camera",
                "platform": "openharmony",
                "teststep": "打开相机",
                "current_phase": "pytest_ran",
                "confirmed_plan": True,
                "artifacts": {"run_dir": ".leaf/runs/runtime-mode"},
            }
            (run_dir / "workflow.json").write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            def fake_runtime(root_arg, run_id_arg, domain_arg, runtime_mode_arg, **kwargs):
                from tools.leaf_author.workflow import load_workflow, save_workflow

                smoke_path = root_arg / ".leaf" / "runs" / run_id_arg / "camera_direct_smoke.json"
                smoke_path.write_text(json.dumps({"status": "complete", "quality_gate": "CAMERA_DIRECT_SMOKE_PASS"}) + "\n", encoding="utf-8")
                workflow_payload = load_workflow(root_arg, run_id_arg)
                artifacts = dict(workflow_payload.get("artifacts", {}))
                artifacts["camera_direct_smoke"] = str(smoke_path.relative_to(root_arg))
                workflow_payload["artifacts"] = artifacts
                workflow_payload["current_phase"] = "camera_direct_smoke_complete"
                save_workflow(root_arg, workflow_payload)
                return {
                    "stage": "camera_direct_smoke",
                    "pass_quality_gate": "CAMERA_DIRECT_SMOKE_PASS",
                    "inspect_action": "inspect_camera_direct_smoke",
                    "result": {"status": "complete", "quality_gate": "CAMERA_DIRECT_SMOKE_PASS"},
                }

            with patch("tools.leaf_author.authoring.run_domain_runtime", side_effect=fake_runtime) as runtime:
                result = advance_run(root, "runtime-mode", run_real=True, runtime_mode="direct_smoke", serial="SERIAL123")

            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["stages"], ["camera_direct_smoke", "experience", "team_export_manifest"])
            runtime.assert_called_once()
            self.assertEqual(runtime.call_args.args[2], "camera")
            self.assertEqual(runtime.call_args.args[3], "direct_smoke")


if __name__ == "__main__":
    unittest.main()
