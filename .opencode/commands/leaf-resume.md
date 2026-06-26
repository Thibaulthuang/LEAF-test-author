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
7. Read `resume_summary.action_route` before deciding the next dispatch. The route is derived from the persisted `workflow.json` phase and the shared handoff contract; do not dispatch from memory or from the chat transcript alone.

The expected deterministic call is:

```text
python3 -m tools.leaf_author resume <run_id> --auto-safe
```

If the result reports `auto_advanced=false`, present `resume_summary.operator_message`,
the current `next_action`, and `resume_summary.action_route` to the user.

## Stable Dispatch Contract

`resume_summary.action_route` is the stable bridge from deterministic state to
OpenCode/subagent behavior. Treat these fields as authoritative:

- `action_route.command`: the operator command to run next, if a deterministic
  command is allowed for the current phase.
- `agent_mode`: whether the next step should stay in the main
  `leaf-test-author` flow or use a bounded subagent handoff.
- `handoff_required`: whether OpenCode should explicitly hand the next step to
  the listed agent instead of continuing in the current reasoning context.
- `subagent_boundary`: the responsibility boundary for that agent. Keep the
  handoff inside that boundary.
- `context_slice`: the minimal context to load. Do not open all run artifacts
  unless the route asks for them.
- `user_checkpoint`: the user-in-loop stop point. If this value is present,
  `--auto-safe` must still stop and ask the user for the specific confirmation.

The user sits at the checkpoint boundary, not inside the tool loop. OpenCode can
prepare plan, draft, validation, report, GUI-tree, and evidence summaries, but
it must pause when `requires_user_confirmation` or `user_checkpoint` is present.
