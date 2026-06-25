from __future__ import annotations

import json
from pathlib import Path

from tools.leaf_author.device_probe import HdcProbe, ProbeRunner
from tools.leaf_author.workflow import load_workflow, save_workflow


def collect_gui_context(
    root: Path,
    run_id: str,
    hdc_runner: ProbeRunner | None = None,
    serial: str | None = None,
) -> dict[str, object]:
    probe = HdcProbe(runner=hdc_runner)
    device = probe.probe(serial=serial)
    serial = str(device.get("serial", ""))
    ui_tree = ""
    hilog = ""
    if device.get("status") == "connected" and serial:
        ui_tree_result = probe.runner(["hdc", "-t", serial, "shell", "uitest", "dumpLayout"], 10)
        hilog_result = probe.runner(["hdc", "-t", serial, "shell", "hilog", "-x"], 10)
        ui_tree = (ui_tree_result.stdout or ui_tree_result.stderr).strip()
        hilog = (hilog_result.stdout or hilog_result.stderr).strip()
    payload = {
        "run_id": run_id,
        "status": "collected" if device.get("status") == "connected" else "unavailable",
        "device": device,
        "serial": serial,
        "ui_tree_excerpt": ui_tree[:2000],
        "hilog_excerpt": hilog[:2000],
    }
    context_path = root / ".leaf" / "runs" / run_id / "gui_context.json"
    context_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    workflow = load_workflow(root, run_id)
    artifacts = dict(workflow.get("artifacts", {}))
    artifacts["gui_context"] = str(context_path.relative_to(root))
    workflow["artifacts"] = artifacts
    workflow["current_phase"] = "gui_context_collected"
    save_workflow(root, workflow)
    return {**payload, "gui_context_path": str(context_path), "next_action": "record_experience"}
