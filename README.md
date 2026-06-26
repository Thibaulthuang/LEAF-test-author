# LEAF Test Authoring Layer

This repository contains the OpenCode-facing authoring layer for LEAF test cases.
The user-facing entrypoint is the OpenCode command, not the Python module:

```text
/leaf-new-case <domain> "<teststep>"
```

Related OpenCode workflow commands:

```text
/leaf-resume <run_id>
/leaf-batch <batch_id> [--run-id <run_id>...]
/leaf-report <run_id|batch_id>
```

Current default platform is OpenHarmony. The most complete domain is `camera`.

## Architecture

- `.opencode/commands/`: user-facing OpenCode commands.
- `.opencode/skills/`: workflow, domain, and GUI-agent skills.
- `tools/leaf_author/`: deterministic Python tool layer for files, state, draft generation, validation, and device orchestration.
- `tools/leaf_author/domain_registry.py`: domain plugin contract for target
  feature inference, semantic plan validation, and action mapping.
- `tools/leaf_author/runtime_registry.py`: runtime plugin contract for
  real-device modes, runtime artifacts, quality gates, experience confidence,
  and review notes.
- `tests/`: unit and orchestration tests.
- `docs/workflow-contract.json`: machine-readable phase, quality-gate, and resume contract.
- `leaf-workflow-architecture.html`: human-readable workflow architecture document.

## Basic Workflow

1. User runs `/leaf-new-case camera "打开相机拍照"`.
2. OpenCode loads `leaf-test-author` and the domain skill, such as `leaf-camera`.
3. OpenCode writes `.leaf/runs/<run_id>/plan_input.json`.
4. Python creates `.leaf/runs/<run_id>/workflow.json` and `plan.json`.
5. User confirms the plan.
6. Python generates `case.json` and a local pytest draft.
7. `advance <run_id>` runs safe local stages.
8. Real-device execution requires a second confirmation.

For interrupted work, users run `/leaf-resume <run_id>`. For multi-case work,
users run `/leaf-batch <batch_id> ...` to create or continue a batch and
`/leaf-report <run_id|batch_id>` to get the current operator decision summary.
These OpenCode commands delegate to the deterministic Python tools documented
below.

## Common Commands

Create a run from deterministic tools:

```bash
python3 -m tools.leaf_author new-case camera "打开相机拍照" --run-id run-demo --plan-input .leaf/runs/run-demo/plan_input.json
```

Confirm a plan:

```bash
python3 -m tools.leaf_author confirm-plan run-demo
```

Resume and automatically advance safe local stages:

```bash
python3 -m tools.leaf_author resume run-demo --auto-safe
```

List active and historical runs with lightweight summaries:

```bash
python3 -m tools.leaf_author list-runs
```

Inspect one run when OpenCode needs details:

```bash
python3 -m tools.leaf_author inspect-run run-demo
```

Create a batch for multi-case authoring:

```bash
python3 -m tools.leaf_author create-batch camera-suite --run-id run-a --run-id run-b --title "Camera suite"
```

Inspect a batch summary before focusing on a single run:

```bash
python3 -m tools.leaf_author inspect-batch camera-suite
```

Resume safe local stages across a batch:

```bash
python3 -m tools.leaf_author resume-batch camera-suite --auto-safe
```

Report one run or a batch without loading large artifacts into OpenCode context:

```bash
python3 -m tools.leaf_author report-run run-demo
python3 -m tools.leaf_author report-batch camera-suite
python3 -m tools.leaf_author workflow-diagnostics run-demo
python3 -m tools.leaf_author audit-run run-demo
python3 -m tools.leaf_author audit-batch camera-suite
```

Export the framework extension contract for a domain:

```bash
python3 -m tools.leaf_author extension-contract camera
python3 -m tools.leaf_author export-extension-contract camera --output /tmp/camera-extension.json
python3 -m tools.leaf_author validate-extension-contract camera
python3 -m tools.leaf_author validate-extension-contract camera --strict-real-device
python3 -m tools.leaf_author runtime-evidence-contract camera
```

The extension contract combines domain hooks, runtime registry status,
real-device gate status, phase guard status, and agent handoff metadata so a new
domain plugin can be reviewed before it is used for real-device execution.
`runtime-evidence-contract <domain>` prints the runtime artifact schema that a
domain plugin must satisfy for report and audit evidence checks.

Validate the phase trigger, context, agent, and user-in-loop contract:

```bash
python3 -m tools.leaf_author phase-guard
python3 -m tools.leaf_author agent-handoff-contract
python3 -m tools.leaf_author real-device-contract
python3 -m tools.leaf_author runtime-evidence-contract camera
python3 -m tools.leaf_author runtime-registry-contract
```

Run safe local stages directly:

```bash
python3 -m tools.leaf_author advance run-demo
```

Run Camera direct smoke after explicit user approval:

```bash
python3 -m tools.leaf_author advance run-demo --run-real --runtime-mode direct_smoke --serial <serial>
```

Run Camera capture E2E after explicit user approval:

```bash
python3 -m tools.leaf_author advance run-demo --run-real --runtime-mode capture_e2e --serial <serial> --approval-token approve_camera_capture_e2e
```

## Quality Gates

- `DRAFT_VALIDATED`: generated draft contains required traceability metadata.
- `DRAFT_STATIC_PASS`: host-side draft gate passed; not a real-device pass.
- `CAMERA_DIRECT_SMOKE_PASS`: built-in Camera launched and UiTest layout evidence matched Camera.
- `CAMERA_CAPTURE_E2E_PASS`: Camera shutter was clicked and a new media file was observed.

## Safety Rules

- Do not generate executable drafts before plan confirmation.
- Do not run state-changing device actions before plan confirmation.
- Camera capture creates a media file and requires a second confirmation plus
  `--approval-token approve_camera_capture_e2e`.
- GUI context collection is read-only by default.
- Experience records are reviewable draft knowledge and must not auto-modify AW code.

## Multi-Run Context Management

OpenCode should not load every `.leaf/runs/<run_id>/` artifact into one prompt.
Use `list-runs` to get lightweight summaries, then `inspect-run <run_id>` to load
one run at a time. Large artifacts such as layout dumps, device logs, and result
evidence should be opened only when the inspected run requires them.

For multi-case work, group run ids with `create-batch`. Use `list-batches` and
`inspect-batch` to decide which run needs attention next, then switch back to
`inspect-run <run_id>` for details. Batch manifests store membership and phase
counts only; they do not duplicate run artifacts.

Use `report-run` and `report-batch` when the agent needs an operator-facing
decision summary: current phase, latest quality gate, user checkpoint, next safe
command, and existing evidence paths. Use `resume-batch --auto-safe` to advance
only confirmed safe local stages across multiple runs; it still stops at plan
confirmation and real-device confirmation.

If a report returns `next_action: repair_workflow`, run
`workflow-diagnostics <run_id>` before retrying resume or audit. The diagnostics
artifact checks whether `workflow.json` exists, is non-empty, parses as JSON,
contains the expected run id, and names a current phase.

Report `next_command` is generated from the phase/runtime contracts. For Camera
real-device checkpoints it recommends the registered runtime mode, for example
`advance <run_id> --run-real --runtime-mode direct_smoke --serial <serial>`.

Phase decisions are contract-driven. `docs/workflow-contract.json` defines each
phase's `next_action`, `auto_safe` flag, `agent_owner`, `context_slice`, and
`user_loop` position. `tools.leaf_author.phase_contract` reads that contract for
`resume`, `inspect-run`, and `report-run`, so OpenCode does not need to infer the
next step from conversation history.

`phase-guard` is the machine check for that design. It fails if a phase stops
using `workflow.json` as the trigger source, omits the workflow from its context
slice, lets an auto-safe phase cross a user checkpoint, assigns `leaf-gui-agent`
without UI-tree context, or leaves a user checkpoint without required operator
input. `agent-handoff-contract` prints the stable handoff map: which phases each
agent owns, which context slice each phase may load, which phases can auto-run,
and where the user must re-enter the loop.

`real-device-contract` prints the machine-readable gate map for real-device
runtime execution. It exposes the approval, input, and preflight decision
contracts from `tools/leaf_author/real_device_contract.py`, including the
`agent_owner`, bounded `context_slice`, allowed artifacts, and `user_loop`
position that subagents should use before or during device execution.
`runtime-registry-contract` prints the registered runtime modes, default mode,
runtime artifacts, quality gates, and safety profiles that domain plugins must
keep complete before real-device execution can be considered stable.
`runtime-evidence-contract <domain>` prints the required runtime evidence fields
for each registered real-device mode, such as Camera direct smoke requiring
`layout_verified`, `bundle_verified`, and `ability_verified`.

Each `resume` refreshes `.leaf/runs/<run_id>/context_manifest.json`. This file is
the handoff boundary for multi-agent and multi-case work: it names the active
agent, the context slice to load, existing artifact paths, the user checkpoint,
and the attention boundary `one_active_run`. It also includes a `handoff`
snapshot with `from_agent`, `to_agent`, `next_action`, `allowed_artifacts`, and
the referenced artifact paths for the next owner. The embedded `user_loop`
snapshot carries `requires_user_confirmation` and `safe_to_auto_continue`, so
subagents can return control to the user instead of crossing checkpoints.
Domain and GUI agents should use this manifest plus specific evidence paths
instead of loading the full run directory.

This keeps attention scoped to the active run and makes multi-case authoring
and execution resumable without relying on conversational memory.

## Development

Run tests with the project virtual environment:

```bash
.venv/bin/python -m pytest -q
```

Generated run artifacts are ignored under `.leaf/`. Generated pytest drafts are ignored under `tests/generated/`.
