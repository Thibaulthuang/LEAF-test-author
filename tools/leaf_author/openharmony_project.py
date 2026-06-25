from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools.leaf_author.workflow import load_workflow, save_workflow


def scaffold_openharmony_test_project(root: Path, run_id: str) -> dict[str, object]:
    run_dir = root / ".leaf" / "runs" / run_id
    export_ohos_test = run_dir / "openharmony_test_project" / "src" / "ohosTest"
    project_dir = run_dir / "openharmony_smoke_project"
    module_dir = project_dir / "entry"
    target_ohos_test = module_dir / "src" / "ohosTest"
    if not export_ohos_test.is_dir():
        payload = {
            "run_id": run_id,
            "status": "missing",
            "quality_gate": "OPENHARMONY_EXPORT_MISSING",
            "reason": f"ohosTest export not found: {export_ohos_test}",
        }
        _write_artifact(root, run_id, payload, phase="openharmony_project_missing")
        return payload

    project_dir.mkdir(parents=True, exist_ok=True)
    module_dir.mkdir(parents=True, exist_ok=True)
    if target_ohos_test.exists():
        shutil.rmtree(target_ohos_test)
    shutil.copytree(export_ohos_test, target_ohos_test)
    (project_dir / "hvigorfile.ts").write_text(_root_hvigorfile(), encoding="utf-8")
    (module_dir / "hvigorfile.ts").write_text(_module_hvigorfile(), encoding="utf-8")
    (project_dir / "hvigor").mkdir(parents=True, exist_ok=True)
    (project_dir / "AppScope").mkdir(parents=True, exist_ok=True)
    (project_dir / "hvigor" / "hvigor-config.json5").write_text(_hvigor_config(), encoding="utf-8")
    (project_dir / "AppScope" / "app.json5").write_text(_app_scope_json5(), encoding="utf-8")
    (project_dir / "local.properties").write_text(_local_properties(), encoding="utf-8")
    (project_dir / "build-profile.json5").write_text(_root_build_profile(), encoding="utf-8")
    (module_dir / "build-profile.json5").write_text(_module_build_profile(), encoding="utf-8")
    (project_dir / "oh-package.json5").write_text(_root_oh_package(), encoding="utf-8")
    (module_dir / "oh-package.json5").write_text(_module_oh_package(), encoding="utf-8")
    hvigorw = project_dir / "hvigorw"
    hvigorw.write_text("#!/bin/sh\nexec /Users/huangbozhang/command-line-tools/hvigor/bin/hvigorw \"$@\"\n", encoding="utf-8")
    hvigorw.chmod(0o755)
    payload = {
        "run_id": run_id,
        "status": "ready",
        "quality_gate": "OPENHARMONY_TEST_PROJECT_READY",
        "project_dir": str(project_dir),
        "target_module_dir": str(module_dir),
        "ohos_test_dir": str(target_ohos_test),
        "next_command": f".venv/bin/python -m tools.leaf_author build-openharmony-haps {run_id} --project-dir {project_dir} --output-dir {module_dir / 'build'} --build-command ./hvigorw assembleOhosTest",
    }
    _write_artifact(root, run_id, payload, phase="openharmony_project_scaffolded")
    return payload


def _root_hvigorfile() -> str:
    return """import { appTasks } from '@ohos/hvigor-ohos-plugin';

export default {
  system: appTasks,
  plugins: [],
};
"""


def _hvigor_config() -> str:
    return """{
  "modelVersion": "26.0.0"
}
"""


def _local_properties() -> str:
    return "sdk.dir=/Users/huangbozhang/command-line-tools/sdk/default\n"


def _app_scope_json5() -> str:
    return """{
  "app": {
    "bundleName": "com.example.leaf",
    "vendor": "leaf",
    "versionCode": 1,
    "versionName": "1.0.0",
    "icon": "$media:app_icon",
    "label": "$string:app_name"
  }
}
"""


def _module_hvigorfile() -> str:
    return """import { hapTasks } from '@ohos/hvigor-ohos-plugin';

export default {
  system: hapTasks,
  plugins: [],
};
"""


def _root_build_profile() -> str:
    return """{
  "app": {
    "signingConfigs": [],
    "products": [
      {
        "name": "default",
        "compileSdkVersion": "26.0.0",
        "compatibleSdkVersion": "26.0.0",
        "targetSdkVersion": "26.0.0",
        "runtimeOS": "OpenHarmony",
        "bundleName": "com.example.leaf"
      }
    ]
  },
  "modules": [
    {
      "name": "entry",
      "srcPath": "./entry",
      "targets": [
        {
          "name": "default",
          "applyToProducts": [
            "default"
          ]
        }
      ]
    }
  ]
}
"""


def _module_build_profile() -> str:
    return """{
  "apiType": "stageMode",
  "buildOption": {},
  "targets": [
    {
      "name": "default"
    },
    {
      "name": "ohosTest"
    }
  ]
}
"""


def _root_oh_package() -> str:
    return """{
  "name": "leaf_camera_smoke_project",
  "version": "1.0.0",
  "modelVersion": "26.0.0",
  "description": "Generated LEAF Camera smoke OpenHarmony project",
  "dependencies": {}
}
"""


def _module_oh_package() -> str:
    return """{
  "name": "entry",
  "version": "1.0.0",
  "description": "Generated LEAF Camera smoke module",
  "dependencies": {}
}
"""


def _write_artifact(root: Path, run_id: str, payload: dict[str, object], phase: str) -> None:
    path = root / ".leaf" / "runs" / run_id / "openharmony_project.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    if not workflow_path.exists():
        return
    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    if payload.get("status") == "ready":
        artifacts["openharmony_project"] = str(Path(str(payload["project_dir"])).relative_to(root))
    artifacts["openharmony_project_report"] = str(path.relative_to(root))
    workflow["artifacts"] = artifacts
    workflow["current_phase"] = phase
    save_workflow(root, workflow)
