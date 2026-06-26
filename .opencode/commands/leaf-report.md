# /leaf-report

Report the current LEAF workflow decision state for one run or one batch.

## Usage

```text
/leaf-report <run_id|batch_id>
```

## Behavior

1. Invoke the `leaf-test-author` skill/subagent.
2. Prefer `python3 -m tools.leaf_author report-run <run_id>` when the argument
   matches a run under `.leaf/runs/`.
3. Prefer `python3 -m tools.leaf_author report-batch <batch_id>` when the
   argument matches a batch under `.leaf/batches/`.
4. Present the report fields that determine the next operator decision:
   `current_phase`, `latest_quality_gate`, `user_action_required`,
   `user_checkpoint`, `next_command`, and `evidence`.
5. Do not open large artifacts unless the user asks or the report points to a
   specific evidence file that must be inspected.
6. If `user_checkpoint` is present, stop and ask the user. If `next_command`
   is safe local work, run it only when it stays inside the workflow's
   auto-safe policy.

This command is the lightweight status surface for interrupted work, multi-case
execution, and handoff between OpenCode sessions.
