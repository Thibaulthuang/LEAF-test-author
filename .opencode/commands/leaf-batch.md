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
4. If the report shows safe local work, call
   `python3 -m tools.leaf_author resume-batch <batch_id> --auto-safe`.
5. It must still stop at user checkpoints, including first plan confirmation
   and real-device confirmation.
6. Keep attention scoped to one run at a time. Use the batch report to pick a
   `next_run_focus`, then use `/leaf-report <run_id>` or `inspect-run <run_id>`
   before opening run artifacts.

Batch commands are coordination commands. They do not replace domain skills,
plan confirmation, or real-device approval.
