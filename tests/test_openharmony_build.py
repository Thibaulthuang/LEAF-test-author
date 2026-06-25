import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.leaf_author.build import BuildCommandResult, build_openharmony_haps
from tools.leaf_author.openharmony_project import scaffold_openharmony_test_project
from tools.leaf_author.workflow import create_workflow, load_workflow


class OpenHarmonyBuildTests(unittest.TestCase):
    def test_scaffold_openharmony_test_project_creates_buildable_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机；点击拍照", "build-scaffold")
            export_dir = root / ".leaf" / "runs" / "build-scaffold" / "openharmony_test_project"
            source_dir = export_dir / "src" / "ohosTest"
            (source_dir / "ets" / "test").mkdir(parents=True)
            (source_dir / "ets" / "aw").mkdir(parents=True)
            (source_dir / "module.json5").write_text('{"module":{"name":"leaf_camera_ohosTest"}}\n', encoding="utf-8")
            (source_dir / "oh-package.json5").write_text('{"name":"leaf_camera_ohosTest"}\n', encoding="utf-8")
            (source_dir / "ets" / "test" / "List.test.ets").write_text("export default [];\n", encoding="utf-8")
            (source_dir / "ets" / "test" / "case.test.ets").write_text("export default function testsuite() {}\n", encoding="utf-8")
            (source_dir / "ets" / "aw" / "CameraAW.ets").write_text("export class CameraAW {}\n", encoding="utf-8")

            result = scaffold_openharmony_test_project(root, "build-scaffold")

            project_dir = Path(result["project_dir"])
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["quality_gate"], "OPENHARMONY_TEST_PROJECT_READY")
            self.assertTrue((project_dir / "hvigorfile.ts").is_file())
            self.assertTrue((project_dir / "hvigor" / "hvigor-config.json5").is_file())
            self.assertTrue((project_dir / "local.properties").is_file())
            self.assertTrue((project_dir / "AppScope" / "app.json5").is_file())
            self.assertTrue((project_dir / "build-profile.json5").is_file())
            self.assertTrue((project_dir / "oh-package.json5").is_file())
            self.assertTrue((project_dir / "entry" / "hvigorfile.ts").is_file())
            self.assertTrue((project_dir / "entry" / "build-profile.json5").is_file())
            self.assertTrue((project_dir / "entry" / "oh-package.json5").is_file())
            self.assertTrue((project_dir / "entry" / "src" / "ohosTest" / "ets" / "test" / "case.test.ets").is_file())
            self.assertIn("hapTasks", (project_dir / "entry" / "hvigorfile.ts").read_text(encoding="utf-8"))
            self.assertIn('"modelVersion": "26.0.0"', (project_dir / "hvigor" / "hvigor-config.json5").read_text(encoding="utf-8"))
            self.assertIn('"modelVersion": "26.0.0"', (project_dir / "oh-package.json5").read_text(encoding="utf-8"))
            self.assertIn("sdk.dir=/Users/huangbozhang/command-line-tools/sdk/default", (project_dir / "local.properties").read_text(encoding="utf-8"))
            self.assertIn('"bundleName": "com.example.leaf"', (project_dir / "AppScope" / "app.json5").read_text(encoding="utf-8"))
            self.assertIn("assembleOhosTest", result["next_command"])
            workflow = load_workflow(root, "build-scaffold")
            self.assertEqual(workflow["current_phase"], "openharmony_project_scaffolded")
            self.assertEqual(workflow["artifacts"]["openharmony_project"], ".leaf/runs/build-scaffold/openharmony_smoke_project")

    def test_build_openharmony_haps_records_result_and_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机；点击拍照", "build-001")
            project_dir = root / "oh_project"
            project_dir.mkdir()
            (project_dir / "hvigorw").write_text("#!/bin/sh\n", encoding="utf-8")
            output_dir = project_dir / "build" / "outputs"
            output_dir.mkdir(parents=True)
            (output_dir / "entry-default.hap").write_text("app", encoding="utf-8")
            (output_dir / "entry-ohosTest.hap").write_text("test", encoding="utf-8")
            calls = []

            def runner(args, cwd, timeout_s):
                calls.append((args, cwd, timeout_s))
                return BuildCommandResult(0, "build success\n", "")

            result = build_openharmony_haps(root, "build-001", project_dir, output_dir=output_dir, runner=runner)

            self.assertEqual(result["status"], "built")
            self.assertEqual(result["quality_gate"], "OPENHARMONY_BUILD_PASS")
            self.assertEqual(result["package_inventory"]["quality_gate"], "HAP_PACKAGE_READY")
            self.assertEqual(calls[0][0], ["./hvigorw", "assembleHap"])
            self.assertEqual(calls[0][1], project_dir)
            build_path = root / ".leaf" / "runs" / "build-001" / "openharmony_build.json"
            self.assertTrue(build_path.exists())
            payload = json.loads(build_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["exit_code"], 0)
            workflow = load_workflow(root, "build-001")
            self.assertEqual(workflow["current_phase"], "openharmony_built")
            self.assertEqual(workflow["artifacts"]["openharmony_build"], ".leaf/runs/build-001/openharmony_build.json")
            self.assertEqual(workflow["artifacts"]["package_inventory"], ".leaf/runs/build-001/package_inventory.json")

    def test_build_openharmony_haps_accepts_custom_build_command_for_test_hap_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机；点击拍照", "build-test-command")
            project_dir = root / "oh_project"
            project_dir.mkdir()
            (project_dir / "hvigorw").write_text("#!/bin/sh\n", encoding="utf-8")
            output_dir = project_dir / "build" / "outputs"
            output_dir.mkdir(parents=True)
            (output_dir / "entry-default.hap").write_text("app", encoding="utf-8")
            (output_dir / "entry-ohosTest.hap").write_text("test", encoding="utf-8")
            calls = []

            def runner(args, cwd, timeout_s):
                calls.append((args, cwd, timeout_s))
                return BuildCommandResult(0, "build test hap success\n", "")

            result = build_openharmony_haps(
                root,
                "build-test-command",
                project_dir,
                output_dir=output_dir,
                runner=runner,
                build_command=["./hvigorw", "assembleOhosTest"],
            )

            self.assertEqual(result["status"], "built")
            self.assertEqual(calls[0][0], ["./hvigorw", "assembleOhosTest"])
            self.assertEqual(result["command"], ["./hvigorw", "assembleOhosTest"])

    def test_build_openharmony_haps_reports_missing_hvigor_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_workflow(root, "camera", "打开相机；点击拍照", "build-missing")
            project_dir = root / "oh_project"
            project_dir.mkdir()

            result = build_openharmony_haps(root, "build-missing", project_dir)

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["quality_gate"], "OPENHARMONY_BUILD_TOOL_MISSING")
            self.assertIn("hvigorw", result["reason"])

    def test_cli_scaffold_openharmony_test_project_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            from contextlib import redirect_stdout
            from io import StringIO
            from tools.leaf_author.__main__ import main

            output = StringIO()
            with patch(
                "tools.leaf_author.__main__.scaffold_openharmony_test_project",
                return_value={"run_id": "scaffold-cli", "quality_gate": "OPENHARMONY_TEST_PROJECT_READY"},
            ) as scaffold, redirect_stdout(output):
                exit_code = main(
                    [
                        "scaffold-openharmony-test-project",
                        "scaffold-cli",
                        "--root",
                        str(root),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "OPENHARMONY_TEST_PROJECT_READY")
            scaffold.assert_called_once_with(root, "scaffold-cli")

    def test_cli_build_openharmony_haps_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "oh_project"
            output_dir = project_dir / "build" / "outputs"
            project_dir.mkdir()
            output_dir.mkdir(parents=True)

            from contextlib import redirect_stdout
            from io import StringIO
            from tools.leaf_author.__main__ import main

            output = StringIO()
            with patch(
                "tools.leaf_author.__main__.build_openharmony_haps",
                return_value={"run_id": "build-cli", "quality_gate": "OPENHARMONY_BUILD_PASS"},
            ) as build, redirect_stdout(output):
                exit_code = main(
                    [
                        "build-openharmony-haps",
                        "build-cli",
                        "--root",
                        str(root),
                        "--project-dir",
                        str(project_dir),
                        "--output-dir",
                        str(output_dir),
                        "--build-command",
                        "./hvigorw",
                        "assembleOhosTest",
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "OPENHARMONY_BUILD_PASS")
            build.assert_called_once()
            self.assertEqual(build.call_args.kwargs["build_command"], ["./hvigorw", "assembleOhosTest"])

    def test_cli_build_openharmony_haps_accepts_extra_build_args(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "oh_project"
            project_dir.mkdir()

            from contextlib import redirect_stdout
            from io import StringIO
            from tools.leaf_author.__main__ import main

            output = StringIO()
            with patch(
                "tools.leaf_author.__main__.build_openharmony_haps",
                return_value={"run_id": "build-cli", "quality_gate": "OPENHARMONY_BUILD_FAILED"},
            ) as build, redirect_stdout(output):
                exit_code = main(
                    [
                        "build-openharmony-haps",
                        "build-cli",
                        "--root",
                        str(root),
                        "--project-dir",
                        str(project_dir),
                        "--build-arg=--no-daemon",
                        "--build-arg=--stacktrace",
                        "--build-command",
                        "./hvigorw",
                        "assembleOhosTest",
                    ]
                )

            self.assertEqual(exit_code, 0)
            build.assert_called_once()
            self.assertEqual(build.call_args.kwargs["build_command"], ["./hvigorw", "assembleOhosTest", "--no-daemon", "--stacktrace"])


if __name__ == "__main__":
    unittest.main()
