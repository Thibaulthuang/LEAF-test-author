# LEAF Test Author Instructions

This repository is the OpenCode-facing authoring layer for LEAF test cases.

## Entry Point

Users should start new work with:

```text
/leaf-new-case <domain> "<teststep>"
```

The command must delegate workflow decisions to the `leaf-test-author` skill/subagent. Deterministic Python code under `tools/leaf_author/` is a tool layer, not the user-facing product entry point.

## Workflow Rules

- Create one run directory per request under `.leaf/runs/<run_id>/`.
- Store resumable state in `.leaf/runs/<run_id>/workflow.json`.
- Store the generated plan in `.leaf/runs/<run_id>/plan.json`.
- Generate pytest drafts under `tests/generated/` only after the plan is confirmed.
- Default platform is `openharmony`.
- Keep the first user-in-loop checkpoint at plan confirmation. Before confirmation, tools may create workflow, plan, and read-only probe artifacts only.
- Do not run high-risk real-device actions before the plan is confirmed.
- HDC probing in the first MVP is read-only: list targets and read model/API version.
- GUI context collection is read-only in the local MVP: dump layout and hilog only.
- Experience records may be written under `.leaf/knowledge/`, but they are reviewable draft knowledge and must not auto-modify AW code.

## Boundaries

- `leaf-test-author` owns reasoning, plan presentation, and flow decisions.
- `tools/leaf_author/` owns deterministic file writes, pytest draft generation, and HDC probe parsing.
- `tools/leaf_author/` may also validate drafts, run draft checks, collect read-only GUI context, write reviewable experience records, and export team manifests.
- Domain skills such as `leaf-camera` own domain conventions and AW usage rules.
- Generated pytest files are drafts until they pass project-specific validation and real execution.
