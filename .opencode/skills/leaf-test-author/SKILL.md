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
- After confirmation, generate `.leaf/runs/<run_id>/case.json` as the final case spec; local drafts are derived from this JSON spec.
- Call deterministic tools under `tools/leaf_author/` for file writes, draft generation, and HDC probing/execution.
- Do not generate pytest drafts until the plan is confirmed.
- Load domain-specific skills such as `leaf-camera` when domain behavior is needed.
- After confirmation, continue through local draft generation, validation, optional real-device system-app execution, GUI context collection, rerun, and experience updates.
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
`python3 -m tools.leaf_author advance <run_id> --run-real --camera-capture --serial <serial> --approval-token approve_camera_capture_e2e --hdc-path <hdc_path>`
must not run from the first confirmation. State clearly that the action will
take a photo and create a new media file. Only run it after the user explicitly
confirms the real-device capture step. The approval token is the deterministic
runtime gate; without it, `advance` must block before invoking the capture
runtime.

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
`next_command`, and evidence paths; they do not require loading layout dumps,
device logs, or result evidence into context unless the next decision
specifically needs them.

Batch auto-resume must obey the same confirmation rules as single-run resume.
It must not confirm plans on behalf of the user and must not run real-device
actions from `--auto-safe`.

## Stable Phase Triggers

`workflow.json is authoritative`; conversation memory is not. Before choosing a
next action, load `workflow.json` through `resume`, `report-run`, or
`report-batch`, then dispatch from `current_phase`, `confirmed_plan`,
`next_action`, and `resume_summary`.

The stable trigger table lives in `docs/workflow-contract.json` and is consumed
by `tools.leaf_author.phase_contract`. Treat `resume_summary.trigger_source`,
`resume_summary.agent_owner`, `resume_summary.context_slice`, and
`resume_summary.user_loop` as the runtime decision contract. Do not duplicate a
separate phase table in prompt text.

Use `python3 -m tools.leaf_author phase-guard` after changing phase definitions,
resume behavior, user checkpoints, or agent ownership. It verifies that every
phase still uses `workflow.json` as the trigger source, exposes a bounded
context slice, respects auto-safe checkpoint rules, and gives GUI phases UI-tree
context. Use `python3 -m tools.leaf_author agent-handoff-contract` when a
domain, GUI, or execution subagent needs the current machine-readable handoff
map. Use `python3 -m tools.leaf_author real-device-contract` when a subagent
needs the stable approval/input/preflight gates for real-device runtime
execution. Use `python3 -m tools.leaf_author runtime-registry-contract` when a
domain plugin or execution subagent needs the registered runtime modes,
quality gates, runtime artifacts, and safety profiles.

- `plan` with `confirmed_plan=false`: present `plan.json` and must stop for
  `first_plan_confirmation`.
- `hypium_draft` or `pytest_draft` with `confirmed_plan=true`: safe local
  validation may run through `resume --auto-safe`.
- `validated`, `pytest_ran`, `gui_context_collected`, and `experience_recorded`:
  safe local stages may continue automatically.
- `e2e_ready` or any real-device action: must stop for
  `real_device_confirmation` unless the user has explicitly approved that exact
  action in the current run.
- `complete`: report evidence and do not rerun actions unless the user asks for
  a new run or explicit rerun.

## Context Control

For multi-case work, load one run at a time. Start with `list-runs` or
`report-batch`, inspect only `next_run_focus`, and open large evidence only when
the focused run's report points to it. Do not load all layout dumps, device
logs, generated drafts, or evidence files into one prompt. UI tree raw files are
evidence; prefer their generated index files and summaries unless raw inspection
is needed for a diagnosis.

Each `resume`, `inspect-run`, or `report-run` refreshes
`.leaf/runs/<run_id>/context_manifest.json`. Use that manifest as the handoff
packet for subagents: it contains the active `agent_owner`, `context_slice`,
`referenced_artifacts`, `user_checkpoint`, and `attention_boundary`. If the
manifest says `leaf-gui-agent`, pass the UI snapshot index path and the specific
question; do not pass the full run directory unless diagnosis requires it.
For real-device execution gates, use `real-device-contract` plus
`real_device_approval.json`, `real_device_input.json`, or
`real_device_preflight.json` instead of reconstructing gate logic in prompt
text.

## Subagent Boundaries

- `leaf-test-author`: owns workflow state, phase decisions, user checkpoints,
  report presentation, and when to call deterministic tools.
- Domain skills such as `leaf-camera`: own semantic step expansion, action
  mappings, selector hints, domain quality gates, and domain failure meanings.
- `leaf-gui-agent`: owns UI tree inspection, candidate analysis, layout diff
  interpretation, and GUI evidence recommendations. It does not mutate device
  state without an explicit workflow action and user approval.
- Deterministic Python tools under `tools/leaf_author/`: own file writes,
  runtime execution, evidence persistence, and stable JSON outputs.

Use a subagent when a task needs focused domain or GUI reasoning that would
otherwise load too much context into `leaf-test-author`. Keep the handoff
artifact-based: pass run id, report summary, UI snapshot index path, and the
specific question.

## User-In-Loop

The user sits at explicit workflow checkpoints, not every internal step.

- `first_plan_confirmation`: user approves the plan and safe local authoring
  only. After this, local validation and evidence collection may continue.
- `real_device_confirmation`: user approves a named device action such as
  Camera direct smoke or Camera capture. Camera capture must say that it takes a
  photo and creates a media file.
- Repair/rerun decisions: when a quality gate fails, present the failure reason,
  evidence paths, and proposed next command before mutating device state again.

If a checkpoint is present, the agent must stop and ask the user. It must not
infer consent from previous runs, batch membership, or successful preflight.

## First MVP Scope

The first implementation supports:

- Creating workflow state.
- Creating a plan.
- Resuming a run and reporting the next action.
- Generating a JSON final case spec at `.leaf/runs/<run_id>/case.json`.
- Generating a traceable pytest draft.
- Optionally probing an OpenHarmony device through read-only HDC commands.
- Validating the pytest draft.
- Running the draft as a non-real-pass quality gate.
- Inspecting Camera system-app readiness through `camera-smoke-preflight`.
- Running `run-camera-direct-smoke` as a safe first real-device framework check.
  This foregrounds the built-in Camera app and records layout/log evidence.
- Running `advance <run_id> --run-real --camera-direct --serial <serial>` as
  the current Camera framework path:
  it performs draft validation, the local draft gate, Camera direct smoke,
  reviewable experience recording, and team manifest export in one resumable
  workflow. The smoke must verify the real UiTest layout contains the Camera
  bundle and ability before it can pass.
- Running `advance <run_id> --run-real --camera-capture --serial <serial> --approval-token approve_camera_capture_e2e` for
  confirmed Camera capture flows. This path verifies the photo-mode and shutter
  nodes from the real Camera layout, clicks the shutter through UiTest, records
  `camera_capture_e2e.json`, then writes experience and team manifest artifacts.
  It mutates device state and must not run before plan confirmation.
- Collecting read-only GUI context through HDC layout dump and hilog.
- Writing reviewable local experience records.
- Exporting a team knowledge manifest for review.

It does not yet perform GUI repair, AW code modification, or automatic application of experience records.

## Tool Boundary

Do not encode deterministic file formats only in prompt text. Use `tools/leaf_author/` for stable operations and verify its behavior with tests.
