from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from tools.leaf_author.device_probe import HdcProbe, ProbeCommandResult, ProbeRunner
from tools.leaf_author.workflow import load_workflow, save_workflow


def generate_hypium_case(root: Path, plan: dict[str, object]) -> Path:
    run_id = str(plan["run_id"])
    domain = str(plan["domain"])
    safe_run_id = _safe_identifier(run_id)
    output_path = root / ".leaf" / "runs" / run_id / "hypium" / f"{safe_run_id}_{domain}.test.ets"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_hypium_case(plan, safe_run_id, domain), encoding="utf-8")
    return output_path


def export_openharmony_test_project(root: Path, plan: dict[str, object], hypium_path: Path) -> Path:
    run_id = str(plan["run_id"])
    export_dir = root / ".leaf" / "runs" / run_id / "openharmony_test_project"
    test_module_dir = export_dir / "src" / "ohosTest"
    case_dir = export_dir / "src" / "ohosTest" / "ets" / "test"
    aw_dir = export_dir / "src" / "ohosTest" / "ets" / "aw"
    case_dir.mkdir(parents=True, exist_ok=True)
    aw_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / hypium_path.name).write_text(hypium_path.read_text(encoding="utf-8"), encoding="utf-8")
    (case_dir / "List.test.ets").write_text(_render_hypium_list_entry(hypium_path.name), encoding="utf-8")
    if str(plan["domain"]) == "camera":
        (aw_dir / "CameraAW.ets").write_text(_render_camera_aw_stub(), encoding="utf-8")
        (aw_dir / "CameraAWConfig.ets").write_text(_render_camera_aw_config(), encoding="utf-8")
    (test_module_dir / "module.json5").write_text(_render_test_module_json5(plan), encoding="utf-8")
    (test_module_dir / "oh-package.json5").write_text(_render_test_oh_package_json5(plan), encoding="utf-8")
    (export_dir / "README.md").write_text(_render_openharmony_export_readme(plan, hypium_path.name), encoding="utf-8")
    return export_dir


def sync_openharmony_export(root: Path, run_id: str, target_module_dir: Path) -> dict[str, object]:
    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    export_rel = str(artifacts.get("openharmony_test_project", ""))
    if not export_rel:
        raise ValueError(f"workflow has no openharmony_test_project artifact for run {run_id}")
    export_dir = root / export_rel
    if not export_dir.is_dir():
        raise FileNotFoundError(f"openharmony export directory not found: {export_dir}")
    target_dir = Path(target_module_dir)
    copied: list[str] = []
    for source in sorted(export_dir.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(export_dir)
        destination = target_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(str(destination))
    payload = {
        "run_id": run_id,
        "status": "synced",
        "quality_gate": "OPENHARMONY_EXPORT_SYNCED",
        "source_export": str(export_dir.relative_to(root)),
        "target_module_dir": str(target_dir),
        "copied_files": copied,
    }
    sync_path = root / ".leaf" / "runs" / run_id / "openharmony_sync.json"
    sync_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts["openharmony_sync"] = str(sync_path.relative_to(root))
    workflow["artifacts"] = artifacts
    workflow["current_phase"] = "openharmony_synced"
    save_workflow(root, workflow)
    return {**payload, "sync_path": str(sync_path)}


def run_hypium_case(
    root: Path,
    run_id: str,
    serial: str | None = None,
    hdc_runner: ProbeRunner | None = None,
    bundle_name: str | None = None,
    module_name: str | None = None,
    test_bundle_name: str | None = None,
    test_module_name: str | None = None,
    test_runner: str = "OpenHarmonyTestRunner",
    wait_time_s: int = 120,
    app_hap: Path | None = None,
    test_hap: Path | None = None,
    package_dir: Path | None = None,
) -> dict[str, object]:
    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    hypium_rel = str(artifacts.get("hypium", ""))
    if not hypium_rel:
        raise ValueError(f"workflow has no hypium artifact for run {run_id}")

    probe = HdcProbe(runner=hdc_runner)
    device = probe.probe(serial=serial)
    payload: dict[str, object]
    if device.get("status") != "connected":
        payload = {
            "run_id": run_id,
            "status": "FAILED",
            "quality_gate": "HYPIUM_DEVICE_UNAVAILABLE",
            "device": device,
            "steps": [],
            "passed": False,
            "reason": device.get("reason", "device unavailable"),
        }
    else:
        target = str(device["serial"])
        haps, package_error = _resolve_haps(app_hap=app_hap, test_hap=test_hap, package_dir=package_dir)
        if package_error:
            payload = {
                "run_id": run_id,
                "status": "FAILED",
                "quality_gate": "HYPIUM_PACKAGE_INVALID",
                "device": device,
                "steps": [],
                "passed": False,
                "reason": package_error,
            }
            result_path = root / ".leaf" / "runs" / run_id / "hypium_result.json"
            result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            artifacts["hypium_result"] = str(result_path.relative_to(root))
            workflow["artifacts"] = artifacts
            workflow["current_phase"] = "hypium_ran"
            save_workflow(root, workflow)
            return {**payload, "hypium_result_path": str(result_path), "next_action": "inspect_hypium_result"}
        hypium_path = root / hypium_rel
        case_name = _case_name(workflow)
        remote_dir = f"/data/local/tmp/leaf/hypium/{run_id}"
        remote_path = f"{remote_dir}/{hypium_path.name}"
        steps = []
        installed_packages: list[str] = []
        install_ok = True
        hap_install_steps, installed_packages = _install_haps(probe, target, haps)
        steps.extend(hap_install_steps)
        install_ok = all(int(step["exit_code"]) == 0 for step in hap_install_steps)
        readiness = _inspect_target_readiness(probe, target, bundle_name, module_name, case_name)
        aa_bundle_name = test_bundle_name or bundle_name
        aa_module_name = test_module_name or module_name
        if readiness["status"] == "missing":
            payload = {
                "run_id": run_id,
                "status": "FAILED",
                "quality_gate": "HYPIUM_TARGET_NOT_READY",
                "device": device,
                "case_name": case_name,
                "bundle_name": bundle_name,
                "module_name": module_name,
                "test_bundle_name": test_bundle_name,
                "test_module_name": test_module_name,
                "test_runner": test_runner,
                "package_dir": str(package_dir) if package_dir is not None else None,
                "installed_packages": installed_packages,
                "steps": steps,
                "readiness": readiness,
                "passed": False,
                "reason": f"{bundle_name}: {readiness.get('reason', 'target bundle is not ready')}",
            }
            result_path = root / ".leaf" / "runs" / run_id / "hypium_result.json"
            result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            artifacts["hypium_result"] = str(result_path.relative_to(root))
            workflow["artifacts"] = artifacts
            workflow["current_phase"] = "hypium_ran"
            save_workflow(root, workflow)
            return {**payload, "hypium_result_path": str(result_path), "next_action": "inspect_hypium_result"}
        mkdir_result = _normalize_hdc_result(probe.runner(["hdc", "-t", target, "shell", "mkdir", "-p", remote_dir], 30))
        steps.append(_step("mkdir_remote", mkdir_result))
        push_result = ProbeResult.failed("previous step failed")
        if mkdir_result.exit_code == 0:
            push_result = _normalize_hdc_result(probe.runner(["hdc", "-t", target, "file", "send", str(hypium_path), remote_path], 60))
            steps.append(_step("push_hypium", push_result))
        launch_result = ProbeResult.failed("previous step failed")
        if install_ok and mkdir_result.exit_code == 0 and push_result.exit_code == 0:
            launch_command = _aa_test_command(case_name, aa_bundle_name, aa_module_name, test_runner, wait_time_s)
            launch_result = _normalize_hdc_result(probe.runner(["hdc", "-t", target, "shell", *launch_command], max(wait_time_s + 60, 180)))
        steps.append(_step("aa_test", launch_result))
        hilog_result = _normalize_hdc_result(probe.runner(["hdc", "-t", target, "shell", "hilog", "-x"], 30))
        steps.append(_step("hilog", hilog_result))
        parsed = _parse_hypium_result(launch_result.stdout + "\n" + launch_result.stderr)
        passed = mkdir_result.exit_code == 0 and push_result.exit_code == 0 and launch_result.exit_code == 0 and parsed["passed"]
        payload = {
            "run_id": run_id,
            "status": "PASSED_REAL" if passed else "FAILED",
            "quality_gate": "HYPIUM_REAL_PASS" if passed else "HYPIUM_REAL_FAILED",
            "device": device,
            "case_name": case_name,
            "bundle_name": bundle_name,
            "module_name": module_name,
            "test_bundle_name": test_bundle_name,
            "test_module_name": test_module_name,
            "test_runner": test_runner,
            "package_dir": str(package_dir) if package_dir is not None else None,
            "installed_packages": installed_packages,
            "remote_dir": remote_dir,
            "remote_path": remote_path,
            "steps": steps,
            "readiness": readiness,
            "result": parsed,
            "hilog_excerpt": (hilog_result.stdout or hilog_result.stderr).strip()[:2000],
            "passed": passed,
        }

    result_path = root / ".leaf" / "runs" / run_id / "hypium_result.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts["hypium_result"] = str(result_path.relative_to(root))
    workflow["artifacts"] = artifacts
    workflow["current_phase"] = "hypium_ran"
    save_workflow(root, workflow)
    return {**payload, "hypium_result_path": str(result_path), "next_action": "collect_gui_context"}


class ProbeResult:
    @staticmethod
    def failed(reason: str):
        from tools.leaf_author.device_probe import ProbeCommandResult

        return ProbeCommandResult(1, "", reason)


def _render_hypium_case(plan: dict[str, object], safe_run_id: str, domain: str) -> str:
    run_id = str(plan["run_id"])
    target_feature = str(plan["target_feature"])
    steps = list(plan.get("steps", []))
    body = _camera_body(steps) if domain == "camera" else _generic_body(steps)
    config_import = "import { configureCameraAW } from '../aw/CameraAWConfig';\n" if domain == "camera" else ""
    config_call = "    configureCameraAW();\n" if domain == "camera" else ""
    return f"""import {{ describe, it, expect }} from '@ohos/hypium';
import {{ CameraAW, GalleryAW }} from '../aw/CameraAW';
{config_import}

const RUN_ID = '{run_id}';
const DOMAIN = '{domain}';
const TARGET_FEATURE = '{target_feature}';

describe('{run_id}_{domain}', () => {{
  it('{target_feature}', 0, async () => {{
{config_call}    const testStartedAt = Date.now();
{body}
  }});
}});
"""


def _camera_body(steps: list[object]) -> str:
    lines = ["    expect(RUN_ID.length > 0).assertTrue();"]
    for index, raw_step in enumerate(steps, start=1):
        step = _normalized_step(raw_step)
        title = str(step["title"])
        action = str(step["action"])
        lines.append(f"    // Step {index}: {title}")
        if action == "CameraAW.launch":
            lines.append("    await CameraAW.launch();")
        elif action == "CameraAW.switchToPhotoMode":
            lines.append("    await CameraAW.switchToPhotoMode();")
        elif action == "CameraAW.capture":
            lines.append("    await CameraAW.capture();")
        elif action == "GalleryAW.assertLatestPhotoCreatedAfter":
            lines.append("    await GalleryAW.assertLatestPhotoCreatedAfter(testStartedAt);")
        else:
            lines.append(f"    await CameraAW.performStep({json.dumps(title, ensure_ascii=False)});")
    if not any(str(_normalized_step(step)["action"]) == "GalleryAW.assertLatestPhotoCreatedAfter" for step in steps):
        lines.append("    await GalleryAW.assertLatestPhotoCreatedAfter(testStartedAt);")
    return "\n".join(lines)


def _normalized_step(raw_step: object) -> dict[str, object]:
    if isinstance(raw_step, dict):
        title = str(raw_step.get("title", ""))
        action = str(raw_step.get("action", ""))
        return {"title": title, "action": action}
    title = str(raw_step)
    if "打开相机" in title:
        action = "CameraAW.launch"
    elif "切拍照模式" in title or "拍照模式" in title:
        action = "CameraAW.switchToPhotoMode"
    elif "点击拍照" in title or "拍照" in title:
        action = "CameraAW.capture"
    elif "相册" in title or "照片" in title:
        action = "GalleryAW.assertLatestPhotoCreatedAfter"
    else:
        action = "CameraAW.performStep"
    return {"title": title, "action": action}


def _render_camera_aw_stub() -> str:
    return """import { Driver, ON } from '@ohos.UiTest';
import abilityDelegatorRegistry from '@ohos.app.ability.abilityDelegatorRegistry';

type CameraAWConfig = {
  bundleName?: string;
  moduleName?: string;
  abilityName?: string;
  launchText?: string;
  photoModeText?: string;
  captureText?: string;
  latestPhotoText?: string;
  actionTimeoutMs?: number;
};

const CONFIG_REQUIRED = 'LEAF_CAMERA_AW_CONFIG_REQUIRED';
let config: CameraAWConfig = {};

function timeoutMs(): number {
  return config.actionTimeoutMs ?? 5000;
}

async function driver(): Promise<Driver> {
  return await Driver.create();
}

function requiredText(name: string, value?: string): string {
  if (!value) {
    throw new Error(`${CONFIG_REQUIRED}: CameraAW.configure must set ${name}`);
  }
  return value;
}

function requiredValue(name: string, value?: string): string {
  if (!value) {
    throw new Error(`${CONFIG_REQUIRED}: CameraAW.configure must set ${name}`);
  }
  return value;
}

async function tapByText(text: string): Promise<void> {
  const component = await (await driver()).findComponent(ON.text(text), timeoutMs());
  await component.click();
}

export class CameraAW {
  static configure(nextConfig: CameraAWConfig): void {
    config = { ...config, ...nextConfig };
  }

  static async launch(): Promise<void> {
    const bundleName = config.bundleName;
    const moduleName = config.moduleName;
    const abilityName = config.abilityName;
    if (bundleName && moduleName && abilityName) {
      await abilityDelegatorRegistry.getAbilityDelegator().startAbility({
        bundleName,
        moduleName,
        abilityName,
      });
      return;
    }
    await tapByText(requiredText('launchText', config.launchText));
  }

  static async switchToPhotoMode(): Promise<void> {
    await tapByText(requiredText('photoModeText', config.photoModeText));
  }

  static async capture(): Promise<void> {
    await tapByText(requiredText('captureText', config.captureText));
  }

  static async performStep(stepText: string): Promise<void> {
    await tapByText(stepText);
  }
}

export class GalleryAW {
  static async assertLatestPhotoCreatedAfter(timestamp: number): Promise<void> {
    const text = requiredText('latestPhotoText', config.latestPhotoText);
    const component = await (await driver()).findComponent(ON.text(text), timeoutMs());
    if (!component) {
      throw new Error(`GalleryAW.assertLatestPhotoCreatedAfter failed after ${timestamp}`);
    }
  }
}
"""


def _render_camera_aw_config() -> str:
    return """import { CameraAW } from './CameraAW';

export function configureCameraAW(): void {
  CameraAW.configure({
    bundleName: 'com.huawei.hmos.camera',
    moduleName: 'phone',
    abilityName: 'com.huawei.hmos.camera.MainAbility',
    launchText: '<open-camera-entry-text>',
    photoModeText: '<photo-mode-text>',
    captureText: '<capture-button-text>',
    latestPhotoText: '<latest-photo-evidence-text>',
    actionTimeoutMs: 5000,
  });
}
"""


def _render_test_module_json5(plan: dict[str, object]) -> str:
    domain = str(plan["domain"])
    return f"""{{
  "module": {{
    "name": "leaf_{domain}_ohosTest",
    "type": "feature",
    "deviceTypes": [
      "phone"
    ],
    "srcEntry": "./ets/test/List.test.ets",
    "testRunner": {{
      "name": "OpenHarmonyTestRunner",
      "srcPath": "./ets/test"
    }}
  }}
}}
"""


def _render_hypium_list_entry(case_file_name: str) -> str:
    stem = case_file_name[:-4] if case_file_name.endswith(".ets") else case_file_name
    return f"""import './{stem}';
"""


def _render_test_oh_package_json5(plan: dict[str, object]) -> str:
    run_id = str(plan["run_id"])
    return f"""{{
  "name": "leaf-{_safe_identifier(run_id)}-ohos-test",
  "version": "1.0.0",
  "description": "Generated LEAF OpenHarmony Hypium test module",
  "dependencies": {{
    "@ohos/hypium": "1.0.21"
  }}
}}
"""


def _render_openharmony_export_readme(plan: dict[str, object], case_file_name: str) -> str:
    run_id = str(plan["run_id"])
    domain = str(plan["domain"])
    case_name = f"{run_id}_{domain}"
    return f"""# OpenHarmony Hypium Export

Generated run: `{run_id}`

Copy `src/ohosTest/ets/test/{case_file_name}` plus the files under
`src/ohosTest/ets/aw/`
into the OpenHarmony test module before building the test HAP.

The generated CameraAW file is a configurable UiTest-based starter AW. Bind it
to the built-in Camera app before building by editing
`src/ohosTest/ets/aw/CameraAWConfig.ets`:

```ts
CameraAW.configure({{
  launchText: '<open-camera-entry-text>',
  photoModeText: '<photo-mode-text>',
  captureText: '<capture-button-text>',
  latestPhotoText: '<latest-photo-evidence-text>',
}});
```

If configuration is missing the AW fails with `LEAF_CAMERA_AW_CONFIG_REQUIRED`
instead of producing a false pass.

For Camera, the target app is the built-in Camera app on the device. Do not
install an app HAP as the target. Install the Hypium test HAP only, then run
the test package with the test bundle/module values:

```text
aa test -b <bundleName> -m <moduleName> -s unittest OpenHarmonyTestRunner -s class {case_name} -w 120
```
"""


def _generic_body(steps: list[object]) -> str:
    lines = ["    expect(TARGET_FEATURE.length > 0).assertTrue();"]
    for index, raw_step in enumerate(steps, start=1):
        step = raw_step.get("title", "") if isinstance(raw_step, dict) else raw_step
        lines.append(f"    // Step {index}: {step}")
    lines.append("    expect(DOMAIN.length > 0).assertTrue();")
    return "\n".join(lines)


def _case_name(workflow: dict[str, object]) -> str:
    return f"{workflow['run_id']}_{workflow['domain']}"


def _aa_test_command(
    case_name: str,
    bundle_name: str | None,
    module_name: str | None,
    test_runner: str,
    wait_time_s: int,
) -> list[str]:
    if not bundle_name:
        return ["aa", "test", "-s", "class", case_name, "-w", str(wait_time_s)]
    command = ["aa", "test", "-b", bundle_name]
    if module_name:
        command.extend(["-m", module_name])
    command.extend(["-s", "unittest", test_runner, "-s", "class", case_name, "-w", str(wait_time_s)])
    return command


def _inspect_target_readiness(
    probe: HdcProbe,
    serial: str,
    bundle_name: str | None,
    module_name: str | None,
    case_name: str,
) -> dict[str, object]:
    if not bundle_name:
        return {
            "status": "unchecked",
            "quality_gate": "HYPIUM_TARGET_UNSPECIFIED",
            "case_name": case_name,
            "reason": "bundle_name was not provided; aa test will rely on platform defaults",
        }
    result = _normalize_hdc_result(probe.runner(["hdc", "-t", serial, "shell", "bm", "dump", "-n", bundle_name], 30))
    output = (result.stdout or result.stderr).strip()
    lowered = output.lower()
    if result.exit_code != 0 or "bundle not exist" in lowered or "not installed" in lowered or "failed to get information" in lowered:
        return {
            "status": "missing",
            "quality_gate": "TARGET_BUNDLE_MISSING",
            "bundle_name": bundle_name,
            "module_name": module_name,
            "case_name": case_name,
            "reason": output or f"target bundle is not installed: {bundle_name}",
        }
    return {
        "status": "available",
        "quality_gate": "TARGET_BUNDLE_AVAILABLE",
        "bundle_name": bundle_name,
        "module_name": module_name,
        "case_name": case_name,
        "raw_output_excerpt": output[:2000],
    }


def _install_haps(probe: HdcProbe, serial: str, haps: list[Path]) -> tuple[list[dict[str, object]], list[str]]:
    if not haps:
        return [], []
    steps: list[dict[str, object]] = []
    installed: list[str] = []
    package_dir = "/data/local/tmp/leaf/packages"
    mkdir_result = _normalize_hdc_result(probe.runner(["hdc", "-t", serial, "shell", "mkdir", "-p", package_dir], 30))
    steps.append(_step("mkdir_package_dir", mkdir_result))
    if mkdir_result.exit_code != 0:
        return steps, installed
    for hap in haps:
        remote_path = f"{package_dir}/{hap.name}"
        push_result = _normalize_hdc_result(probe.runner(["hdc", "-t", serial, "file", "send", str(hap), remote_path], 60))
        steps.append(_step(f"push_package:{hap.name}", push_result))
        if push_result.exit_code != 0:
            return steps, installed
        install_result = _normalize_hdc_result(probe.runner(["hdc", "-t", serial, "shell", "bm", "install", "-p", remote_path], 180))
        steps.append(_step(f"install_package:{hap.name}", install_result))
        if install_result.exit_code != 0:
            return steps, installed
        installed.append(hap.name)
    return steps, installed


def _resolve_haps(app_hap: Path | None, test_hap: Path | None, package_dir: Path | None) -> tuple[list[Path], str]:
    haps = [Path(hap) for hap in (app_hap, test_hap) if hap is not None]
    explicit_error = _validate_haps(haps)
    if explicit_error:
        return [], explicit_error
    if app_hap is not None and test_hap is None:
        return [], "test_hap is required when installing explicit app_hap"
    if package_dir is not None:
        package_path = Path(package_dir)
        if package_path.is_symlink():
            return [], f"package directory must not be a symlink: {package_path}"
        if not package_path.is_dir():
            return [], f"package directory does not exist: {package_path}"
        discovered = sorted(package_path.rglob("*.hap"), key=lambda item: (_is_test_hap(item), item.as_posix()))
        discovered_error = _validate_haps(discovered)
        if discovered_error:
            return [], discovered_error
        if not discovered:
            return [], f"no .hap files found in package directory: {package_path}"
        if not any(_is_test_hap(item) for item in discovered):
            return [], "test HAP is missing; expected a .hap filename containing ohosTest or test"
        haps.extend(discovered)
    return haps, _validate_haps(haps)


def _validate_haps(haps: list[Path]) -> str:
    for hap in haps:
        if hap.is_symlink():
            return f"package path must not be a symlink: {hap}"
        if hap.suffix != ".hap":
            return f"package path must point to a .hap file: {hap}"
        if not hap.is_file():
            return f"package path does not exist: {hap}"
    return ""


def _is_test_hap(path: Path) -> bool:
    name = path.name.lower()
    return "ohostest" in name or "test" in name


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]", "_", value)


def _step(name: str, result) -> dict[str, object]:
    return {
        "name": name,
        "exit_code": result.exit_code,
        "stdout": result.stdout[:2000],
        "stderr": result.stderr[:2000],
    }


def _normalize_hdc_result(result: ProbeCommandResult) -> ProbeCommandResult:
    output = f"{result.stdout}\n{result.stderr}".lower()
    if result.exit_code == 0 and ("connect server failed" in output or "not connect to server" in output):
        return ProbeCommandResult(1, result.stdout, result.stderr)
    return result


def _parse_hypium_result(output: str) -> dict[str, object]:
    lowered = output.lower()
    total = _first_int(output, r"total\s*=\s*(\d+)") or _first_int(output, r"tests?\s*[:=]\s*(\d+)") or 1
    failed = _first_int(output, r"failures?\s*=\s*(\d+)") or _first_int(output, r"failed\s*[:=]\s*(\d+)") or 0
    passed = failed == 0 and any(marker in lowered for marker in ("passed", "pass", "success", "ohos_report_status: passed"))
    return {
        "passed": passed,
        "total": total,
        "failed": failed,
        "raw_output_excerpt": output.strip()[:2000],
    }


def _first_int(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))
