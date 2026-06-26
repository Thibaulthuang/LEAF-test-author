# LEAF Test Authoring Layer

This repository contains the OpenCode-facing authoring layer for LEAF test cases.
The user-facing entrypoint is the OpenCode command, not the Python module:

```text
/leaf-new-case <domain> "<teststep>"
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
6. Python generates `case.json`, pytest draft, Hypium draft, and OpenHarmony export.
7. `advance <run_id>` runs safe local stages.
8. Real-device execution requires a second confirmation.

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
- `HYPIUM_REAL_PASS`: installed Hypium test package passed on a real device.

## Safety Rules

- Do not generate pytest/Hypium drafts before plan confirmation.
- Do not run state-changing device actions before plan confirmation.
- Camera capture creates a media file and requires a second confirmation.
- GUI context collection is read-only by default.
- Experience records are reviewable draft knowledge and must not auto-modify AW code.

## Multi-Run Context Management

OpenCode should not load every `.leaf/runs/<run_id>/` artifact into one prompt.
Use `list-runs` to get lightweight summaries, then `inspect-run <run_id>` to load
one run at a time. Large artifacts such as Hypium sources, layout dumps, build
logs, and result evidence should be opened only when the inspected run requires
them.

For multi-case work, group run ids with `create-batch`. Use `list-batches` and
`inspect-batch` to decide which run needs attention next, then switch back to
`inspect-run <run_id>` for details. Batch manifests store membership and phase
counts only; they do not duplicate run artifacts.

This keeps attention scoped to the active run and makes multi-case authoring
and execution resumable without relying on conversational memory.

## Development

Run tests with the project virtual environment:

```bash
.venv/bin/python -m pytest -q
```

Generated run artifacts are ignored under `.leaf/`. Generated pytest drafts are ignored under `tests/generated/`.
