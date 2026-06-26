---
name: leaf-test-author
description: Main LEAF local test-case authoring skill. Use for /leaf-new-case and /leaf-resume workflows.
---

# leaf-test-author

`leaf-test-author` is the workflow owner for local LEAF pytest authoring.

## Responsibilities

- Interpret `<domain>` and `<teststep>` from `/leaf-new-case`.
- Create and maintain `.leaf/runs/<run_id>/workflow.json`.
- Generate a semantic plan input before calling deterministic tools, then present `plan.json` for user confirmation.
- After confirmation, generate `.leaf/runs/<run_id>/case.json` as the final case spec; pytest and Hypium drafts are derived from this JSON spec.
- Call deterministic tools under `tools/leaf_author/` for file writes, pytest/Hypium draft generation, and HDC probing/execution.
- Do not generate pytest drafts until the plan is confirmed.
- Load domain-specific skills such as `leaf-camera` when domain behavior is needed.
- After confirmation, continue through pytest/Hypium generation, validation, optional real-device Hypium execution, GUI context collection, rerun, and experience updates.
- Own `/leaf-batch` and `/leaf-report` decisions by using deterministic batch
  and report tools before opening large artifacts.

## Semantic Planning Contract

For `/leaf-new-case`, do not rely on punctuation splitting to understand the
test step. The OpenCode agent owns semantic interpretation:

1. Load the domain skill, such as `leaf-camera`, before creating the plan.
2. Convert the user's natural-language `<teststep>` into a structured semantic
   plan input with explicit ordered `steps`.
3. Create `.leaf/runs/<run_id>/`, then write the semantic input under
   `.leaf/runs/<run_id>/plan_input.json`.
4. Call `python3 -m tools.leaf_author new-case <domain> "<teststep>" --run-id <run_id> --plan-input .leaf/runs/<run_id>/plan_input.json`.
5. Present the resulting `plan.json` and stop for user confirmation.

The deterministic Python layer validates and persists the semantic plan. It is
not responsible for LLM reasoning. If `--plan-input` is omitted, Python may use
its fallback splitter, but OpenCode `/leaf-new-case` should not rely on that
fallback for normal authoring.

`plan_input.json` shape:

```json
{
  "target_feature": "camera.capture",
  "steps": [
    "打开系统相机",
    "确认处于拍照模式",
    "点击快门拍照",
    "检查产生新照片"
  ],
  "risk": "真实执行时会在设备中新增一张照片",
  "confirmation_required": true
}
```

## Two-Stage Confirmation

The first user confirmation approves the plan and safe local authoring only. If
the user replies `yes` to the plan prompt in the same OpenCode conversation,
continue automatically:

1. Run `python3 -m tools.leaf_author confirm-plan <run_id>`.
2. Run `python3 -m tools.leaf_author advance <run_id>`.
3. Summarize generated artifacts, including `case.json` final case spec, and
   local validation result.
4. Stop before any real-device action and ask for second confirmation when a
   real Camera path is relevant.

The second confirmation is required before device-mutating execution. A Camera
capture command such as
`python3 -m tools.leaf_author advance <run_id> --run-real --camera-capture --serial <serial> --hdc-path <hdc_path>`
must not run from the first confirmation. State clearly that the action will
take a photo and create a new media file. Only run it after the user explicitly
confirms the real-device capture step.

## Multi-Case And Reporting Contract

Use `/leaf-batch` for multi-case coordination and `/leaf-report` for lightweight
operator status. These commands must use deterministic summaries first:

1. `python3 -m tools.leaf_author report-run <run_id>` for one run.
2. `python3 -m tools.leaf_author report-batch <batch_id>` for one batch.
3. `python3 -m tools.leaf_author resume-batch <batch_id> --auto-safe` only
   when the batch report shows safe local work.

Keep the active reasoning scope to one run at a time. Batch reports may choose
`next_run_focus`, but the agent should inspect or open artifacts only for that
focused run. Reports expose `latest_quality_gate`, `user_checkpoint`,
`next_command`, and evidence paths; they do not require loading Hypium sources,
layout dumps, build logs, or result evidence into context unless the next
decision specifically needs them.

Batch auto-resume must obey the same confirmation rules as single-run resume.
It must not confirm plans on behalf of the user and must not run real-device
actions from `--auto-safe`.

## First MVP Scope

The first implementation supports:

- Creating workflow state.
- Creating a plan.
- Resuming a run and reporting the next action.
- Generating a JSON final case spec at `.leaf/runs/<run_id>/case.json`.
- Generating a traceable pytest draft.
- Generating a traceable Hypium `.ets` draft for OpenHarmony real-device execution.
- Exporting the Hypium case plus compile-time AW stubs under
  `.leaf/runs/<run_id>/openharmony_test_project/` so they can be copied into
  the target OpenHarmony test module before building the test HAP.
- Syncing that export into a target OpenHarmony module and recording
  `openharmony_sync.json` when the user provides a module path.
- Running a provided OpenHarmony project build command, defaulting to
  `./hvigorw assembleHap` and allowing `./hvigorw assembleOhosTest` for Hypium
  test-HAP tasks, then recording `openharmony_build.json` plus package
  inventory when build outputs exist.
- Optionally probing an OpenHarmony device through read-only HDC commands.
- Validating the pytest draft.
- Running the draft as a non-real-pass quality gate.
- Inspecting HAP output directories and recording `package_inventory.json`
  before real execution.
- Inspecting combined E2E readiness and recording `e2e_readiness.json` or
  `e2e_preflight_report.json` so missing device/package/export/target
  prerequisites are visible before a run, including the next `run-e2e` command.
- Running the built-in Camera smoke path through `camera-smoke-preflight` and
  `run-camera-smoke`. Camera is the target app already present on the device;
  an app HAP is not required for the target, and the Hypium test HAP is only the
  runner package.
- Running `run-camera-direct-smoke` as a safe first real-device framework check
  when no Hypium test HAP is available yet. This only foregrounds the built-in
  Camera app and records layout/log evidence; it is not a replacement for the
  final Hypium e2e pass.
- Running `advance <run_id> --run-real --camera-direct --serial <serial>` as
  the current Camera end-to-end framework path when no test HAP is available:
  it performs draft validation, the local draft gate, Camera direct smoke,
  reviewable experience recording, and team manifest export in one resumable
  workflow. The smoke must verify the real UiTest layout contains the Camera
  bundle and ability before it can pass.
- Running `advance <run_id> --run-real --camera-capture --serial <serial>` for
  confirmed Camera capture flows. This path verifies the photo-mode and shutter
  nodes from the real Camera layout, clicks the shutter through UiTest, records
  `camera_capture_e2e.json`, then writes experience and team manifest artifacts.
  It mutates device state and must not run before plan confirmation.
- Orchestrating real-device E2E through `run-e2e`, which can discover the
  target bundle, sync the exported `src/ohosTest` files, build with a supplied
  command, install required test packages, and run Hypium through serial
  HDC/`aa test`.
- Running the installed Hypium test package on a real device when the user
  explicitly requests real execution and a serial is available. The `.ets`
  source must be built into a test HAP; pushing the source to `/data/local/tmp`
  is only an execution artifact, not dynamic source loading.
- Collecting read-only GUI context through HDC layout dump and hilog.
- Writing reviewable local experience records.
- Exporting a team knowledge manifest for review.

It does not yet perform GUI repair, AW code modification, or automatic application of experience records.

## Tool Boundary

Do not encode deterministic file formats only in prompt text. Use `tools/leaf_author/` for stable operations and verify its behavior with tests.
