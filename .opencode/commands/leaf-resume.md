# /leaf-resume

Resume an interrupted LEAF authoring run.

## Usage

```text
/leaf-resume <run_id>
```

## Behavior

1. Invoke the `leaf-test-author` skill/subagent.
2. Load `.leaf/runs/<run_id>/workflow.json`.
3. Call the deterministic `resume` tool with `--auto-safe`.
4. If `resume_summary.safe_to_auto_continue` is true, the tool may advance safe local stages automatically.
5. It must still stop at user checkpoints, including the first plan confirmation and any real-device confirmation.
6. Do not repeat high-risk actions unless the workflow state and user approval allow them.

The expected deterministic call is:

```text
python3 -m tools.leaf_author resume <run_id> --auto-safe
```

If the result reports `auto_advanced=false`, present `resume_summary.operator_message` and the current `next_action` to the user.
