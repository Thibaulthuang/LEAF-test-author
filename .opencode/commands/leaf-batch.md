# /leaf-batch

Manage a multi-case LEAF authoring batch without loading every run into one
OpenCode context.

## Usage

```text
/leaf-batch <batch_id> [--run-id <run_id>...]
```

Examples:

```text
/leaf-batch camera-suite --run-id run-a --run-id run-b
/leaf-batch camera-suite
```

## Behavior

1. Invoke the `leaf-test-author` skill/subagent.
2. If `--run-id` values are provided, call
   `python3 -m tools.leaf_author create-batch <batch_id> --run-id <run_id>...`.
3. Call `python3 -m tools.leaf_author report-batch <batch_id>` to get the
   operator decision summary.
4. Check `batch_audit_summary.failed_checks` before any resume dispatch. If it
   is non-empty, present the failed checks and `batch_audit_summary.focus_plan`
   to the user; OpenCode must not dispatch `resume-batch` or a selected run
   until the route/audit drift is resolved.
5. If `resume-batch --auto-safe` returns `block_reason=batch_audit_failed`,
   treat `next_action=inspect_batch_audit` and `next_command` as the stable
   route. Present `operator_message`, `user_checkpoint`, `user_loop`,
   `batch_audit_summary.failed_checks`, and `next_command` to the user before
   any retry.
6. If the report shows safe local work and `batch_audit_summary.failed_checks`
   is empty, call
   `python3 -m tools.leaf_author resume-batch <batch_id> --auto-safe`.
7. It must still stop at user checkpoints, including first plan confirmation
   and real-device confirmation.
8. Keep attention scoped to one run at a time. Use the batch report to pick a
   `next_run_focus`, then use `/leaf-report <run_id>` or `inspect-run <run_id>`
   before opening run artifacts.
9. When `resume-batch` returns a `focus_plan`, read
   `focus_plan.action_route` before dispatching the selected run. The route is
   derived from that run's persisted phase, not from the batch conversation.

Batch commands are coordination commands. They do not replace domain skills,
plan confirmation, or real-device approval.

## One-Run Dispatch Contract

`focus_plan.action_route` is the batch-safe version of the single-run
`resume_summary.action_route`. It keeps multi-case authoring from collapsing
all plans, artifacts, and evidence into one OpenCode context.

- `action_route.command`: the deterministic command for the selected run, if the
  current phase can advance without more user input.
- `agent_mode`: whether the selected run should stay with `leaf-test-author` or
  be handed to a bounded specialist such as `leaf-gui-agent`.
- `handoff_required`: whether OpenCode must create an explicit handoff instead
  of continuing inline.
- `subagent_boundary`: the work boundary for the receiving agent. Do not let a
  GUI/domain handoff rewrite the whole workflow or modify unrelated runs.
- `context_slice`: the exact run-level context to load for the selected case.
  Keep the rest of the batch as lightweight summaries.
- `user_checkpoint`: the user-in-loop stop point for the selected run. If it is
  present, `resume-batch --auto-safe` must still stop before crossing it.

For multi-use-case writing and execution, batch state chooses the next run, and
the selected run's `action_route` chooses the phase action. This preserves
attention by loading one run, one phase, and one agent boundary at a time while
leaving the user as the owner of plan and real-device approval.
