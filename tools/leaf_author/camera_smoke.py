from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.device_diagnostics import inspect_test_target
from tools.leaf_author.device_probe import ProbeRunner
from tools.leaf_author.device_probe import HdcProbe
from tools.leaf_author.e2e import run_e2e
from tools.leaf_author.e2e_report import write_e2e_preflight_report
from tools.leaf_author.runtime.actions import ActionRunner
from tools.leaf_author.runtime.device import DeviceSession, command_succeeded, command_text
from tools.leaf_author.runtime.evidence import write_ui_snapshot
from tools.leaf_author.runtime.ui_tree import build_index, diff_indexes, find_candidates, parse_layout
from tools.leaf_author.workflow import load_workflow, save_workflow


def write_camera_smoke_preflight(
    root: Path,
    run_id: str,
    serial: str,
    test_hap: Path | None = None,
    package_dir: Path | None = None,
    project_dir: Path | None = None,
    target_module_dir: Path | None = None,
    discover_root: Path | None = None,
    build_command: list[str] | None = None,
    hdc_runner: ProbeRunner | None = None,
) -> dict[str, object]:
    report = write_e2e_preflight_report(
        root,
        run_id,
        serial=serial,
        target_filter="camera",
        test_hap=test_hap,
        package_dir=package_dir,
        discover_root=discover_root,
        build_command=build_command,
        hdc_runner=hdc_runner,
        app_hap=None,
    )
    return _camera_payload(report, next_command=_camera_next_command(report, project_dir, target_module_dir))


def run_camera_smoke(
    root: Path,
    run_id: str,
    serial: str,
    test_hap: Path | None = None,
    package_dir: Path | None = None,
    project_dir: Path | None = None,
    target_module_dir: Path | None = None,
    discover_root: Path | None = None,
    build_command: list[str] | None = None,
    hdc_runner: ProbeRunner | None = None,
) -> dict[str, object]:
    result = run_e2e(
        root,
        run_id,
        serial=serial,
        bundle_name=None,
        target_filter="camera",
        target_module_dir=target_module_dir,
        project_dir=project_dir,
        package_dir=package_dir,
        app_hap=None,
        test_hap=test_hap,
        discover_root=discover_root,
        build_command=build_command,
        hdc_runner=hdc_runner,
    )
    return _camera_payload(result)


def run_camera_direct_smoke(
    root: Path,
    run_id: str,
    serial: str,
    bundle_name: str = "com.huawei.hmos.camera",
    module_name: str | None = None,
    ability_name: str = "com.huawei.hmos.camera.MainAbility",
    hdc_path: str = "hdc",
    hdc_runner: ProbeRunner | None = None,
) -> dict[str, object]:
    probe = HdcProbe(runner=hdc_runner, hdc_path=hdc_path)
    session = DeviceSession(root=root, run_id=run_id, serial=serial, runner=probe.runner, hdc_path=probe.hdc_path)
    actions = ActionRunner(session)
    device = probe.probe(serial=serial)
    if device.get("status") != "connected":
        return _write_direct_smoke(
            root,
            run_id,
            {
                "run_id": run_id,
                "domain": "camera",
                "status": "failed",
                "quality_gate": "CAMERA_DIRECT_SMOKE_DEVICE_UNAVAILABLE",
                "device": device,
                "target_app": _target_app(bundle_name, module_name),
                "next_action": "connect_device",
            },
        )

    target = inspect_test_target(root, run_id, serial, bundle_name, hdc_runner=probe.runner, hdc_path=probe.hdc_path)
    resolved_module = module_name or str(target.get("module_name") or "phone")
    if target.get("status") != "available":
        return _write_direct_smoke(
            root,
            run_id,
            {
                "run_id": run_id,
                "domain": "camera",
                "status": "failed",
                "quality_gate": "CAMERA_DIRECT_SMOKE_TARGET_MISSING",
                "device": device,
                "target": target,
                "target_app": _target_app(bundle_name, resolved_module),
                "next_action": "inspect_camera_target",
            },
        )

    launch_action = actions.execute(
        {
            "id": "camera_direct_launch",
            "action": "system_app.launch",
            "params": {"bundle": bundle_name, "ability": ability_name, "module": resolved_module},
        }
    )
    launch = launch_action["result"]
    layout = session.client.dump_layout()
    ui_tree = layout["dump"]
    layout_path = layout["path"]
    ui_tree_text = str(layout["raw_layout"])
    ui_snapshot = write_ui_snapshot(root, run_id, phase="after_launch", action_id="camera_direct", raw_layout=ui_tree_text)
    hilog = session.client.hilog()
    bundle_verified = bundle_name in ui_tree_text
    ability_verified = ability_name in ui_tree_text
    layout_verified = bundle_verified and ability_verified
    passed = command_succeeded(launch) and command_succeeded(ui_tree) and layout_verified
    return _write_direct_smoke(
        root,
        run_id,
        {
            "run_id": run_id,
            "domain": "camera",
            "status": "complete" if passed else "failed",
            "quality_gate": "CAMERA_DIRECT_SMOKE_PASS" if passed else "CAMERA_DIRECT_SMOKE_FAILED",
            "device": device,
            "target": target,
            "target_app": _target_app(bundle_name, resolved_module),
            "launch": launch,
            "evidence": {
                "layout_path": layout_path,
                "layout_verified": layout_verified,
                "bundle_verified": bundle_verified,
                "ability_verified": ability_verified,
                "ui_snapshots": {
                    "after_launch": ui_snapshot,
                },
                "ui_tree_excerpt": ui_tree_text[:4000],
                "hilog_excerpt": command_text(hilog)[:4000],
            },
            "commands": [
                "hdc shell bm dump -n <camera_bundle>",
                "hdc shell aa start -a <camera_ability> -b <camera_bundle> -m <camera_module>",
                "hdc shell uitest dumpLayout",
                "hdc shell hilog -x",
            ],
            "next_action": "inspect_camera_direct_smoke" if not passed else "promote_to_hypium_runner",
        },
    )


def run_camera_capture_e2e(
    root: Path,
    run_id: str,
    serial: str,
    bundle_name: str = "com.huawei.hmos.camera",
    module_name: str | None = None,
    ability_name: str = "com.huawei.hmos.camera.MainAbility",
    hdc_path: str = "hdc",
    hdc_runner: ProbeRunner | None = None,
) -> dict[str, object]:
    probe = HdcProbe(runner=hdc_runner, hdc_path=hdc_path)
    session = DeviceSession(root=root, run_id=run_id, serial=serial, runner=probe.runner, hdc_path=probe.hdc_path)
    actions = ActionRunner(session)
    device = probe.probe(serial=serial)
    if device.get("status") != "connected":
        return _write_capture_e2e(
            root,
            run_id,
            {
                "run_id": run_id,
                "domain": "camera",
                "status": "failed",
                "quality_gate": "CAMERA_CAPTURE_E2E_DEVICE_UNAVAILABLE",
                "device": device,
                "target_app": _target_app(bundle_name, module_name),
                "next_action": "connect_device",
            },
        )

    target = inspect_test_target(root, run_id, serial, bundle_name, hdc_runner=probe.runner, hdc_path=probe.hdc_path)
    resolved_module = module_name or str(target.get("module_name") or "phone")
    if target.get("status") != "available":
        return _write_capture_e2e(
            root,
            run_id,
            {
                "run_id": run_id,
                "domain": "camera",
                "status": "failed",
                "quality_gate": "CAMERA_CAPTURE_E2E_TARGET_MISSING",
                "device": device,
                "target": target,
                "target_app": _target_app(bundle_name, resolved_module),
                "next_action": "inspect_camera_target",
            },
        )

    launch_action = actions.execute(
        {
            "id": "camera_capture_launch",
            "action": "system_app.launch",
            "params": {"bundle": bundle_name, "ability": ability_name, "module": resolved_module},
        }
    )
    launch = launch_action["result"]
    before = session.client.dump_layout()
    before_text = str(before["raw_layout"])
    before_snapshot = write_ui_snapshot(root, run_id, phase="before_capture", action_id="camera_capture", raw_layout=before_text)
    before_index = build_index(parse_layout(before_text))
    photo_mode_candidates = find_candidates(before_index, selectors=[{"id": "COMPONENT_ID_CONTROL_PHOTO_2"}, {"text": "拍照"}])
    shutter_candidates = find_candidates(before_index, selectors=[{"id": "COMPONENT_ID_SHUTTER_PHOTO_1"}, {"clickable": True}])
    photo_mode_node = _first_candidate(photo_mode_candidates, required_id="COMPONENT_ID_CONTROL_PHOTO_2", required_text="拍照")
    shutter_node = _first_candidate(shutter_candidates, required_id="COMPONENT_ID_SHUTTER_PHOTO_1", required_clickable=True)
    tap = _node_center(shutter_node) if shutter_node else None
    before_media = _list_camera_media(session) if tap else []
    capture_action = (
        actions.execute(
            {
                "id": "camera_capture_tap_shutter",
                "action": "ui.click",
                "params": {"x": tap["x"], "y": tap["y"]},
                "capture_ui": {"after": True},
            }
        )
        if tap
        else {"status": "failed", "result": {"args": [], "exit_code": 1, "stdout": "", "stderr": "shutter node not found"}}
    )
    capture = capture_action["result"]
    after_snapshot = capture_action.get("ui_snapshots", {}).get("after") if command_succeeded(capture) else None
    after = session.client.dump_layout() if command_succeeded(capture) and after_snapshot is None else {"path": None, "layout": {"exit_code": 0, "stdout": "", "stderr": ""}, "raw_layout": ""}
    after_media = _list_camera_media(session) if command_succeeded(capture) else []
    new_media_files = _new_media_files(before_media, after_media)
    after_text = str(after["raw_layout"])
    if after_snapshot is None:
        after_snapshot = write_ui_snapshot(root, run_id, phase="after_capture", action_id="camera_capture", raw_layout=after_text)
        after_index = build_index(parse_layout(after_text))
    else:
        after_index = build_index(parse_layout((root / str(after_snapshot["raw_path"])).read_text(encoding="utf-8")))
        after_text = (root / str(after_snapshot["raw_path"])).read_text(encoding="utf-8")
    hilog = session.client.hilog()
    before_verified = _layout_verified(before_text, bundle_name, ability_name)
    after_verified = _layout_verified(after_text, bundle_name, ability_name)
    capture_triggered = command_succeeded(capture)
    media_delta_detected = bool(new_media_files)
    passed = (
        command_succeeded(launch)
        and before_verified
        and photo_mode_node is not None
        and shutter_node is not None
        and capture_triggered
        and after_verified
        and media_delta_detected
    )
    failure_reason = _capture_failure_reason(
        launch=launch,
        before_verified=before_verified,
        photo_mode_node=photo_mode_node,
        shutter_node=shutter_node,
        capture=capture,
        after_verified=after_verified,
        new_media_files=new_media_files,
    )
    return _write_capture_e2e(
        root,
        run_id,
        {
            "run_id": run_id,
            "domain": "camera",
            "status": "complete" if passed else "failed",
            "quality_gate": "CAMERA_CAPTURE_E2E_PASS" if passed else "CAMERA_CAPTURE_E2E_FAILED",
            "device": device,
            "target": target,
            "target_app": _target_app(bundle_name, resolved_module),
            "launch": launch,
            "capture": capture,
            "failure_reason": None if passed else failure_reason,
            "evidence": {
                "before_layout_path": before["path"],
                "after_layout_path": after["path"],
                "before_layout_verified": before_verified,
                "after_layout_verified": after_verified,
                "layout_verified": before_verified and after_verified,
                "capture_triggered": capture_triggered,
                "media_delta_detected": media_delta_detected,
                "photo_mode_node": photo_mode_node,
                "shutter_node": shutter_node,
                "shutter_tap": tap,
                "media_before": before_media,
                "media_after": after_media,
                "new_media_files": new_media_files,
                "ui_snapshots": {
                    "before_capture": before_snapshot,
                    "after_capture": after_snapshot,
                },
                "ui_diff": capture_action.get("ui_diff") or diff_indexes(before_index, after_index),
                "photo_mode_candidates": photo_mode_candidates[:5],
                "shutter_candidates": shutter_candidates[:5],
                "ui_tree_excerpt": before_text[:4000],
                "after_ui_tree_excerpt": after_text[:4000],
                "hilog_excerpt": command_text(hilog)[:4000],
            },
            "commands": [
                "hdc shell bm dump -n <camera_bundle>",
                "hdc shell aa start -a <camera_ability> -b <camera_bundle> -m <camera_module>",
                "hdc shell uitest dumpLayout",
                "hdc shell uitest uiInput click <shutter_center_x> <shutter_center_y>",
                "hdc shell hilog -x",
            ],
            "next_action": "inspect_camera_capture_e2e" if not passed else "promote_to_hypium_runner",
        },
    )


def _camera_payload(payload: dict[str, object], next_command: str | None = None) -> dict[str, object]:
    selected_target = payload.get("selected_target") or _selected_target(payload)
    missing = _camera_missing(payload.get("missing", []))
    quality_gate = _camera_quality_gate(str(payload.get("quality_gate", "")), missing)
    return {
        **payload,
        "domain": "camera",
        "target_app": {
            "kind": "builtin",
            "bundle_name": _field(selected_target, "bundle_name"),
            "module_name": _field(selected_target, "module_name"),
            "requires_app_hap": False,
        },
        "runner": {
            "kind": "python_hdc_uitest",
            "requires_test_hap": False,
            "default_command": "advance --run-real --camera-direct",
        },
        "missing": missing,
        "readiness_summary": _camera_readiness_summary(payload, selected_target, missing),
        "blocking_reason": _camera_blocking_reason(quality_gate, missing),
        "quality_gate": quality_gate,
        "quality_gate_description": _camera_quality_gate_description(quality_gate),
        "recommended_actions": _camera_recommended_actions(quality_gate),
        "next_command": next_command or str(payload.get("next_command", "")),
    }


def _selected_target(payload: dict[str, object]) -> dict[str, object]:
    target_discovery = payload.get("target_discovery", {})
    candidates = target_discovery.get("candidates", []) if isinstance(target_discovery, dict) else []
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
        return candidates[0]
    readiness = payload.get("readiness", {})
    target = readiness.get("target", {}) if isinstance(readiness, dict) else {}
    return target if isinstance(target, dict) else {}


def _field(value: object, key: str) -> str | None:
    if isinstance(value, dict) and value.get(key):
        return str(value[key])
    return None


def _camera_missing(missing: object) -> list[str]:
    values = [str(item) for item in missing] if isinstance(missing, list) else []
    ignored_for_builtin_direct = {
        "HAP_ARTIFACTS_MISSING",
        "HAP_PACKAGE_DIR_UNSPECIFIED",
        "HAP_TEST_PACKAGE_MISSING",
        "OPENHARMONY_PROJECT_MISSING",
    }
    mapped = [item for item in values if item not in ignored_for_builtin_direct]
    return list(dict.fromkeys(mapped))


def _camera_quality_gate(quality_gate: str, missing: list[str]) -> str:
    if quality_gate in {"E2E_REAL_PASS", "HYPIUM_REAL_PASS"}:
        return quality_gate
    if any(item in missing for item in ("HDC_DEVICE_UNAVAILABLE", "DEVICE_UNAVAILABLE", "HDC_TARGET_UNAVAILABLE")):
        return "CAMERA_SMOKE_DEVICE_UNAVAILABLE"
    if "TARGET_CANDIDATES_EMPTY" in missing:
        return "CAMERA_SMOKE_TARGET_MISSING"
    if not missing and quality_gate == "E2E_PREFLIGHT_NOT_READY":
        return "CAMERA_SMOKE_READY"
    return "CAMERA_SMOKE_READY" if quality_gate == "E2E_PREFLIGHT_READY" else quality_gate


def _camera_readiness_summary(payload: dict[str, object], selected_target: object, missing: list[str]) -> dict[str, object]:
    readiness = payload.get("readiness", {})
    device = "unknown"
    if isinstance(readiness, dict):
        target = readiness.get("target", {})
        if isinstance(target, dict) and target.get("device"):
            device = "ready"
    if any(item in missing for item in ("HDC_DEVICE_UNAVAILABLE", "DEVICE_UNAVAILABLE", "HDC_TARGET_UNAVAILABLE")):
        device = "missing"
    target_app = "missing" if "TARGET_CANDIDATES_EMPTY" in missing else "ready" if isinstance(selected_target, dict) and selected_target else "unknown"
    return {
        "device": device,
        "target_app": target_app,
        "executor": "ready" if target_app == "ready" else "unknown",
        "app_hap_required": False,
        "test_hap_required": False,
    }


def _camera_blocking_reason(quality_gate: str, missing: list[str]) -> str | None:
    if quality_gate in {"CAMERA_SMOKE_READY", "E2E_REAL_PASS", "HYPIUM_REAL_PASS"}:
        return None
    preferred = [
        "HDC_DEVICE_UNAVAILABLE",
        "TARGET_CANDIDATES_EMPTY",
    ]
    for item in preferred:
        if item in missing:
            return item
    return missing[0] if missing else quality_gate


def _camera_quality_gate_description(quality_gate: str) -> str:
    descriptions = {
        "CAMERA_SMOKE_READY": "Built-in system Camera is ready for the Python/HDC/UiTest direct path.",
        "CAMERA_SMOKE_DEVICE_UNAVAILABLE": "No usable OpenHarmony device is available through HDC.",
        "CAMERA_SMOKE_TARGET_MISSING": "No Camera bundle candidate was found on the connected device.",
        "E2E_REAL_PASS": "Camera E2E passed on a real device.",
        "HYPIUM_REAL_PASS": "Real-device execution passed.",
    }
    return descriptions.get(quality_gate, "Camera smoke preflight is not ready; inspect missing prerequisites.")


def _camera_recommended_actions(quality_gate: str) -> list[str]:
    if quality_gate == "CAMERA_SMOKE_DEVICE_UNAVAILABLE":
        return [
            "Connect an OpenHarmony device, verify HDC can list the serial, then rerun camera-smoke-preflight.",
            "If multiple devices are connected, pass the intended --serial explicitly.",
        ]
    if quality_gate == "CAMERA_SMOKE_TARGET_MISSING":
        return [
            "Verify the device has the built-in Camera app and that the selected serial is correct.",
            "Run discover-targets with --bundle-filter camera to inspect available bundles.",
        ]
    if quality_gate == "CAMERA_SMOKE_READY":
        return ["Run the provided camera-direct next_command for the system Camera path."]
    return ["Inspect the preflight report and resolve listed missing prerequisites."]


def _camera_next_command(report: dict[str, object], project_dir: Path | None, target_module_dir: Path | None) -> str:
    parts = [
        ".venv/bin/python",
        "-m",
        "tools.leaf_author",
        "advance",
        str(report.get("run_id", "")),
        "--run-real",
        "--camera-direct",
        "--serial",
        str(report.get("serial", "")),
    ]
    return " ".join(parts)


def _target_app(bundle_name: str, module_name: str | None) -> dict[str, object]:
    return {
        "kind": "builtin",
        "bundle_name": bundle_name,
        "module_name": module_name,
        "requires_app_hap": False,
    }


def _layout_verified(text: str, bundle_name: str, ability_name: str) -> bool:
    return bundle_name in text and ability_name in text


def _find_layout_node(text: str, node_id: str, text_value: str | None = None, clickable: bool | None = None) -> dict[str, object] | None:
    try:
        root = json.loads(text)
    except json.JSONDecodeError:
        return None
    for attributes in _iter_layout_attributes(root):
        if attributes.get("id") != node_id and attributes.get("key") != node_id:
            continue
        if text_value is not None and attributes.get("text") != text_value and attributes.get("originalText") != text_value:
            continue
        if clickable is not None and (attributes.get("clickable") == "true") != clickable:
            continue
        return {
            "id": str(attributes.get("id") or attributes.get("key") or ""),
            "type": str(attributes.get("type") or ""),
            "text": str(attributes.get("text") or ""),
            "bounds": str(attributes.get("bounds") or ""),
            "clickable": attributes.get("clickable") == "true",
        }
    return None


def _first_candidate(
    candidates: list[dict[str, object]],
    required_id: str | None = None,
    required_text: str | None = None,
    required_clickable: bool | None = None,
) -> dict[str, object] | None:
    for candidate in candidates:
        if required_id is not None and candidate.get("id") != required_id:
            continue
        if required_text is not None and candidate.get("text") != required_text:
            continue
        if required_clickable is not None and bool(candidate.get("clickable")) is not required_clickable:
            continue
        return candidate
    return None


def _iter_layout_attributes(node: object):
    if not isinstance(node, dict):
        return
    attributes = node.get("attributes", {})
    if isinstance(attributes, dict):
        yield attributes
    children = node.get("children", [])
    if isinstance(children, list):
        for child in children:
            yield from _iter_layout_attributes(child)


def _node_center(node: dict[str, object] | None) -> dict[str, int] | None:
    if not node:
        return None
    center = node.get("center")
    if isinstance(center, dict) and isinstance(center.get("x"), int) and isinstance(center.get("y"), int):
        return {"x": int(center["x"]), "y": int(center["y"])}
    if isinstance(node.get("bounds"), list):
        bounds_values = node["bounds"]
        if len(bounds_values) == 4 and all(isinstance(value, int) for value in bounds_values):
            x1, y1, x2, y2 = bounds_values
            return {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2}
    bounds = str(node.get("bounds") or "")
    parts = [int(value) for value in bounds.replace("[", ",").replace("]", ",").split(",") if value.strip().isdigit()]
    if len(parts) != 4:
        return None
    x1, y1, x2, y2 = parts
    return {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2}


def _list_camera_media(session: DeviceSession) -> list[str]:
    return session.client.list_files("/storage/media/100/local/files/Photo", maxdepth=3)


def _new_media_files(before: list[str], after: list[str]) -> list[str]:
    before_set = set(before)
    return [path for path in after if path not in before_set]


def _write_direct_smoke(root: Path, run_id: str, payload: dict[str, object]) -> dict[str, object]:
    path = root / ".leaf" / "runs" / run_id / "camera_direct_smoke.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    if workflow_path.exists():
        workflow = load_workflow(root, run_id)
        artifacts = dict(workflow.get("artifacts", {}))
        artifacts["camera_direct_smoke"] = str(path.relative_to(root))
        workflow["artifacts"] = artifacts
        workflow["current_phase"] = "camera_direct_smoke_complete" if payload.get("status") == "complete" else "camera_direct_smoke_failed"
        save_workflow(root, workflow)
    return {**payload, "camera_direct_smoke_path": str(path)}


def _write_capture_e2e(root: Path, run_id: str, payload: dict[str, object]) -> dict[str, object]:
    payload = _enrich_capture_payload(payload)
    path = root / ".leaf" / "runs" / run_id / "camera_capture_e2e.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    workflow_path = root / ".leaf" / "runs" / run_id / "workflow.json"
    if workflow_path.exists():
        workflow = load_workflow(root, run_id)
        artifacts = dict(workflow.get("artifacts", {}))
        artifacts["camera_capture_e2e"] = str(path.relative_to(root))
        workflow["artifacts"] = artifacts
        workflow["current_phase"] = "camera_capture_e2e_complete" if payload.get("status") == "complete" else "camera_capture_e2e_failed"
        save_workflow(root, workflow)
    return {**payload, "camera_capture_e2e_path": str(path)}


def _enrich_capture_payload(payload: dict[str, object]) -> dict[str, object]:
    quality_gate = str(payload.get("quality_gate", ""))
    enriched = {
        **payload,
        "evidence_schema_version": "1.0",
        "quality_gate_description": _capture_quality_gate_description(quality_gate),
    }
    evidence = payload.get("evidence", {})
    if isinstance(evidence, dict):
        enriched["evidence_summary"] = _capture_evidence_summary(evidence, failure_reason=payload.get("failure_reason"))
    return enriched


def _capture_quality_gate_description(quality_gate: str) -> str:
    if quality_gate == "CAMERA_CAPTURE_E2E_PASS":
        return "Camera capture passed with real UiTest shutter control and new media-file evidence."
    if quality_gate == "CAMERA_CAPTURE_E2E_DEVICE_UNAVAILABLE":
        return "Camera capture could not run because the OpenHarmony device is unavailable."
    if quality_gate == "CAMERA_CAPTURE_E2E_TARGET_MISSING":
        return "Camera capture could not run because the built-in Camera target was not found."
    return "Camera capture failed; inspect layout, shutter, click, and media evidence."


def _capture_evidence_summary(evidence: dict[str, object], failure_reason: object = None) -> dict[str, object]:
    before_media = evidence.get("media_before", [])
    after_media = evidence.get("media_after", [])
    new_media = evidence.get("new_media_files", [])
    return {
        "failure_reason": failure_reason,
        "before_layout": {
            "path": evidence.get("before_layout_path"),
            "verified": bool(evidence.get("before_layout_verified")),
        },
        "after_layout": {
            "path": evidence.get("after_layout_path"),
            "verified": bool(evidence.get("after_layout_verified")),
        },
        "controls": {
            "photo_mode_found": evidence.get("photo_mode_node") is not None,
            "shutter_found": evidence.get("shutter_node") is not None,
            "shutter_tap": evidence.get("shutter_tap"),
        },
        "media": {
            "before_count": len(before_media) if isinstance(before_media, list) else 0,
            "after_count": len(after_media) if isinstance(after_media, list) else 0,
            "new_count": len(new_media) if isinstance(new_media, list) else 0,
            "new_files": new_media if isinstance(new_media, list) else [],
        },
    }


def _capture_failure_reason(
    *,
    launch: dict[str, object],
    before_verified: bool,
    photo_mode_node: dict[str, object] | None,
    shutter_node: dict[str, object] | None,
    capture: dict[str, object],
    after_verified: bool,
    new_media_files: list[str],
) -> str:
    if not command_succeeded(launch):
        return "CAMERA_LAUNCH_FAILED"
    if not before_verified:
        return "BEFORE_LAYOUT_NOT_CAMERA"
    if photo_mode_node is None:
        return "PHOTO_MODE_NODE_MISSING"
    if shutter_node is None:
        return "SHUTTER_NODE_MISSING"
    if not command_succeeded(capture):
        return "SHUTTER_CLICK_FAILED"
    if not after_verified:
        return "AFTER_LAYOUT_NOT_CAMERA"
    if not new_media_files:
        return "NEW_MEDIA_FILE_MISSING"
    return "UNKNOWN"
