# /leaf-resume

Resume an interrupted LEAF authoring run.

## Usage

```text
/leaf-resume <run_id>
```

## Behavior

1. Invoke the `leaf-test-author` skill/subagent.
2. Load `.leaf/runs/<run_id>/workflow.json`.
3. Call the deterministic `resume` tool to identify the next action.
4. Continue from `current_phase`.
5. Do not repeat high-risk actions unless the workflow state and user approval allow them.
