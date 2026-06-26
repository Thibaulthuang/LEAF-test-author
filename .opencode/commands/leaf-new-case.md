# /leaf-new-case

Start a LEAF test-case authoring run.

## Usage

```text
/leaf-new-case <domain> "<teststep>"
```

Example:

```text
/leaf-new-case camera "打开相机；切拍照模式；点击拍照；检查相册出现新照片"
```

## Behavior

1. Invoke the `leaf-test-author` skill/subagent.
2. Create or request a run id.
3. Load the domain skill, such as `leaf-camera`, and convert `<teststep>` into
   a semantic `.leaf/runs/<run_id>/plan_input.json`. Do not rely on punctuation
   splitting; phrases like `打开相机拍照` must become explicit ordered domain
   operations.
4. Call deterministic tools under `tools/leaf_author/` with
   `--plan-input .leaf/runs/<run_id>/plan_input.json` to create `workflow.json`,
   `plan.json`, and an optional `device_probe.json`.
5. Present the generated plan for confirmation.
6. If the user replies `yes` in this OpenCode conversation, call `confirm-plan`
   to create `.leaf/runs/<run_id>/case.json` as the final case spec, the
   host-side pytest draft under `tests/generated/`, and local workflow
   artifacts. Generated drafts must be derived from `case.json`.
7. Immediately call `advance <run_id>` to run the safe local stages: validation,
   draft run, read-only GUI context, reviewable experience record, and team
   export manifest. Do not stop after only printing `next_action`.
8. Stop before real-device execution and ask for second confirmation. A Camera
   capture run with `--run-real --camera-capture` mutates device state by taking
   a photo and creating a media file, so it must not run from the first
   confirmation.
9. For Camera real-device execution after second confirmation, first run
   `camera-smoke-preflight <run_id> --serial <device_serial>` to verify the
   device and built-in Camera target. Camera is a system app; do not require or
   request an app package. Use
   `advance <run_id> --run-real --camera-direct --serial <device_serial> --hdc-path <hdc_path>`
   as the framework check: it validates the pytest draft, runs the draft gate,
   foregrounds Camera, verifies the real UiTest layout belongs to Camera,
   records `camera_direct_smoke.json`, writes the reviewable experience record,
   and exports the team manifest. For confirmed capture flows, run
   `advance <run_id> --run-real --camera-capture --serial <device_serial> --hdc-path <hdc_path>`;
   this additionally verifies photo mode and the shutter node, snapshots media
   files under `/storage/media/100/local/files/Photo`, taps the shutter,
   verifies a new media file appears, and records `camera_capture_e2e.json`.
   HDC operations must stay serial.

## Two-Stage Confirmation

- First confirmation: approve the plan, then run `confirm-plan` and
  `advance <run_id>` automatically for safe local artifacts and validation.
- Second confirmation: required before `--run-real --camera-capture`; tell the
  user this will take a photo and create a new media file.

The Python tool layer is not the user-facing entry point. It exists so the subagent can perform stable, testable file and device operations.
