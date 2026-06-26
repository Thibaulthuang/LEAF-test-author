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
4. If the report is complete, run `python3 -m tools.leaf_author audit-run <run_id>`
   or `python3 -m tools.leaf_author audit-batch <batch_id>` before summarizing
   completion. Present audit `status`, failed checks, and the latest quality
   gate.
5. Present the report fields that determine the next operator decision:
   `current_phase`, `latest_quality_gate`, `user_action_required`,
   `user_checkpoint`, `user_loop`, `decision_contract`, `next_command`, and
   `evidence`.
6. If `next_action` is `repair_workflow`, run
   `python3 -m tools.leaf_author workflow-diagnostics <run_id>` and present the
   diagnostics path, failed checks, and parse error before any resume/audit
   retry.
7. Do not open large artifacts unless the user asks or the report points to a
   specific evidence file that must be inspected.
8. If `runtime_evidence_summary.ui_snapshots` is present and the user asks a UI
   positioning or selector question, prefer
   `python3 -m tools.leaf_author inspect-ui-tree <run_id>` with `--phase`,
   `--action-id`, `--id`, `--text`, `--type`, or `--clickable` before opening
   raw layout files.
9. If `user_checkpoint` is present, stop and ask the user. If `next_command`
   is safe local work, run it only when it stays inside the workflow's
   auto-safe policy.
10. Use `decision_contract.agent_owner` and `decision_contract.context_slice` to
   decide whether the main author agent should continue or hand off to a domain
   or GUI subagent. Use `.leaf/runs/<run_id>/context_manifest.json` as the
   artifact handoff packet.
11. Treat `next_command` as contract output. For real-device checkpoints it must
   come from the runtime registry and should use `--runtime-mode <mode>` when
   the domain has a registered runtime mode.

This command is the lightweight status surface for interrupted work, multi-case
execution, and handoff between OpenCode sessions.
