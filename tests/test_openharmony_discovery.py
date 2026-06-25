import tempfile
import unittest
import json
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


class OpenHarmonyDiscoveryTests(unittest.TestCase):
    def test_discover_openharmony_project_finds_project_module_and_hap_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "DemoApp"
            module_dir = project_dir / "entry"
            output_dir = project_dir / "entry" / "build" / "default" / "outputs"
            output_dir.mkdir(parents=True)
            (project_dir / "hvigorw").write_text("#!/bin/sh\n", encoding="utf-8")
            (project_dir / "build-profile.json5").write_text("{}", encoding="utf-8")
            (module_dir / "module.json5").write_text("{}", encoding="utf-8")
            (output_dir / "entry-default.hap").write_text("app", encoding="utf-8")
            (output_dir / "entry-ohosTest.hap").write_text("test", encoding="utf-8")

            from tools.leaf_author.openharmony_discovery import discover_openharmony_project

            result = discover_openharmony_project(root)

            self.assertEqual(result["status"], "found")
            self.assertEqual(result["quality_gate"], "OPENHARMONY_PROJECT_DISCOVERED")
            self.assertEqual(result["project_dir"], str(project_dir))
            self.assertEqual(result["target_module_dir"], str(module_dir))
            self.assertEqual(result["package_dir"], str(output_dir))
            self.assertEqual(result["hap_count"], 2)

    def test_discover_openharmony_project_reports_missing_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            from tools.leaf_author.openharmony_discovery import discover_openharmony_project

            result = discover_openharmony_project(Path(tmp))

            self.assertEqual(result["status"], "missing")
            self.assertEqual(result["quality_gate"], "OPENHARMONY_PROJECT_MISSING")

    def test_discover_openharmony_project_ignores_standalone_hvigor_tool_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool_dir = root / "command-line-tools" / "bin"
            tool_dir.mkdir(parents=True)
            (tool_dir / "hvigorw").write_text("#!/bin/sh\n", encoding="utf-8")

            from tools.leaf_author.openharmony_discovery import discover_openharmony_project

            result = discover_openharmony_project(root)

            self.assertEqual(result["status"], "missing")
            self.assertEqual(result["quality_gate"], "OPENHARMONY_PROJECT_MISSING")

    def test_discover_hap_artifacts_finds_test_hap_without_openharmony_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "artifacts" / "phone"
            output_dir.mkdir(parents=True)
            test_hap = output_dir / "entry-ohosTest.hap"
            test_hap.write_text("test", encoding="utf-8")

            from tools.leaf_author.openharmony_discovery import discover_hap_artifacts

            result = discover_hap_artifacts(root)

            self.assertEqual(result["status"], "found")
            self.assertEqual(result["quality_gate"], "HAP_ARTIFACTS_DISCOVERED")
            self.assertEqual(result["package_dir"], str(output_dir))
            self.assertEqual(result["test_hap"], str(test_hap))
            self.assertEqual(result["app_hap"], None)

    def test_discover_hap_artifacts_extracts_test_bundle_and_module_from_hap_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_hap = root / "entry-ohosTest.hap"
            with zipfile.ZipFile(test_hap, "w") as hap:
                hap.writestr(
                    "module.json",
                    json.dumps(
                        {
                            "app": {"bundleName": "com.example.leaf.test"},
                            "module": {"name": "entry_test"},
                        }
                    ),
                )

            from tools.leaf_author.openharmony_discovery import discover_hap_artifacts

            result = discover_hap_artifacts(root)

            self.assertEqual(result["status"], "found")
            self.assertEqual(result["test_bundle_name"], "com.example.leaf.test")
            self.assertEqual(result["test_module_name"], "entry_test")

    def test_discover_hap_artifacts_extracts_test_bundle_and_module_from_pack_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_hap = root / "entry-ohosTest.hap"
            with zipfile.ZipFile(test_hap, "w") as hap:
                hap.writestr(
                    "pack.info",
                    json.dumps(
                        {
                            "summary": {
                                "app": {"bundleName": "com.example.pack.test"},
                                "modules": [{"name": "pack_test"}],
                            },
                            "packages": [{"moduleName": "pack_test"}],
                        }
                    ),
                )

            from tools.leaf_author.openharmony_discovery import discover_hap_artifacts

            result = discover_hap_artifacts(root)

            self.assertEqual(result["status"], "found")
            self.assertEqual(result["test_bundle_name"], "com.example.pack.test")
            self.assertEqual(result["test_module_name"], "pack_test")

    def test_cli_find_haps_outputs_discovered_test_hap_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            test_hap = root / "entry-ohosTest.hap"
            test_hap.write_text("test", encoding="utf-8")
            output = StringIO()

            from tools.leaf_author.__main__ import main

            with redirect_stdout(output):
                exit_code = main(["find-haps", "--search-root", str(root)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["quality_gate"], "HAP_ARTIFACTS_DISCOVERED")
            self.assertEqual(payload["test_hap"], str(test_hap))


if __name__ == "__main__":
    unittest.main()
