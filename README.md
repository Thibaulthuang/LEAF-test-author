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
```

Run safe local stages directly:

```bash
python3 -m tools.leaf_author advance run-demo
```

Run Camera direct smoke after explicit user approval:

```bash
python3 -m tools.leaf_author advance run-demo --run-real --camera-direct --serial <serial>
```

Run Camera capture E2E after explicit user approval:

```bash
python3 -m tools.leaf_author advance run-demo --run-real --camera-capture --serial <serial>
```

## Quality Gates

- `DRAFT_VALIDATED`: generated draft contains required traceability metadata.
- `DRAFT_STATIC_PASS`: host-side draft gate passed; not a real-device pass.
- `CAMERA_DIRECT_SMOKE_PASS`: built-in Camera launched and UiTest layout evidence matched Camera.
- `CAMERA_CAPTURE_E2E_PASS`: Camera shutter was clicked and a new media file was observed.

## Safety Rules

- Do not generate executable drafts before plan confirmation.
- Do not run state-changing device actions before plan confirmation.
- Camera capture creates a media file and requires a second confirmation.
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

Phase decisions are contract-driven. `docs/workflow-contract.json` defines each
phase's `next_action`, `auto_safe` flag, `agent_owner`, `context_slice`, and
`user_loop` position. `tools.leaf_author.phase_contract` reads that contract for
`resume`, `inspect-run`, and `report-run`, so OpenCode does not need to infer the
next step from conversation history.

Each `resume` refreshes `.leaf/runs/<run_id>/context_manifest.json`. This file is
the handoff boundary for multi-agent and multi-case work: it names the active
agent, the context slice to load, existing artifact paths, the user checkpoint,
and the attention boundary `one_active_run`. Domain and GUI agents should use
this manifest plus specific evidence paths instead of loading the full run
directory.

This keeps attention scoped to the active run and makes multi-case authoring
and execution resumable without relying on conversational memory.

## Development

Run tests with the project virtual environment:

```bash
.venv/bin/python -m pytest -q
```

Generated run artifacts are ignored under `.leaf/`. Generated pytest drafts are ignored under `tests/generated/`.
