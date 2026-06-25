---
name: leaf-camera
description: Basic camera domain knowledge for LEAF local pytest authoring.
---

# leaf-camera

Use this skill when `/leaf-new-case` receives `domain=camera`.

## Domain Defaults

- Platform default: `openharmony`.
- Target feature for capture flows: `camera.capture`.
- Target app is the built-in device Camera app, not an external app under test.
- Common target discovery should prefer the device bundle
  `com.huawei.hmos.camera`; the module is discovered from the device, commonly
  `phone`.
- The verified Camera launch element on the current real device is ability
  `com.huawei.hmos.camera.MainAbility` in module `phone`; direct smoke should
  use `aa start -a com.huawei.hmos.camera.MainAbility -b com.huawei.hmos.camera -m phone`.
- Camera real-device execution must not require an app HAP for the target app.
  A Hypium test HAP is only the test runner carrier.
- Generated tests must stay as drafts until they are bound to real AW/fixture code.
- A local pytest draft pass is only a static draft gate. It must not be counted
  as a real-device pass.

## Common User Steps

Map common Chinese steps conservatively:

- `打开相机`: launch or navigate to the camera app/page.
- `切拍照模式`: ensure still-photo mode is selected.
- `点击拍照`: trigger capture.
- `检查相册出现新照片`: verify capture evidence through a real artifact or platform API.

## Semantic Step Expansion

When used by `/leaf-new-case`, this skill owns Camera-domain step expansion.
Do not depend on user punctuation. Natural phrases such as `打开相机拍照`,
`打开相机，并拍照`, `启动相机后拍一张照片`, and `进入相机点击快门并确认有新照片`
must be normalized into explicit Camera operations before Python writes
`plan.json`.

Use these action mappings:

- Open Camera triggers: `打开相机`, `启动相机`, `进入相机`, `打开系统相机`.
  Emit `打开系统相机`.
- Capture intent triggers: `拍照`, `拍一张照片`, `点击快门`, `按下快门`.
  Expand to:
  - `确认处于拍照模式`
  - `点击快门拍照`
- Evidence triggers: `检查相册`, `确认相册`, `新照片`, `照片出现`, `保存成功`.
  Emit `检查产生新照片`.

If the user asks to capture a photo but does not explicitly ask for evidence,
still include `检查产生新照片`; Camera capture without a persisted artifact check
is not an end-to-end case.

Example semantic input for `打开相机拍照`:

```json
{
  "target_feature": "camera.capture",
  "steps": [
    "打开系统相机",
    "确认处于拍照模式",
    "点击快门拍照",
    "检查产生新照片"
  ],
  "risk": "真实执行时会在设备中新增一张照片",
  "confirmation_required": true
}
```

## Basic AW Operation Contract

For first-stage real-device execution, generated Hypium drafts reference these
camera AW operations. The export includes a configurable UiTest-based starter
AW, but the target Harmony project must bind real selectors before the result
can be treated as a business pass:

- `CameraAW.launch()`: start or foreground the camera application/page.
- `CameraAW.switchToPhotoMode()`: make still-photo mode active.
- `CameraAW.capture()`: trigger one photo capture and wait for capture action completion.
- `GalleryAW.assertLatestPhotoCreatedAfter(timestamp)`: verify a new photo/media
  artifact exists after the test start timestamp.
- `CameraAW.performStep(stepText)`: reserved fallback for unmapped camera steps;
  using it means the draft still needs domain review.

## Current Real-Device Framework Gate

Until a built Hypium test HAP is available, the executable Camera framework gate
is `advance <run_id> --run-real --camera-direct --serial <serial> --hdc-path <hdc_path>`.
This path validates the generated pytest draft, runs the local draft gate, starts
the built-in Camera app, reads the real `uitest dumpLayout` output file, and
passes only when the layout contains:

- `bundleName`: `com.huawei.hmos.camera`
- `abilityName`: `com.huawei.hmos.camera.MainAbility`

This is the first real-device e2e framework check for Camera. It proves device
control, app launch, layout capture, evidence recording, and workflow export. It
does not yet prove capture-photo business behavior.

For confirmed capture workflows, `advance <run_id> --run-real --camera-capture
--serial <serial> --hdc-path <hdc_path>` is the stronger direct e2e path. It
starts the built-in Camera app, verifies photo mode through
`COMPONENT_ID_CONTROL_PHOTO_2` / text `拍照`, verifies the shutter node
`COMPONENT_ID_SHUTTER_PHOTO_1`, taps the shutter center with UiTest, and verifies
the app remains on the Camera layout after the action. It also compares media
files under `/storage/media/100/local/files/Photo` before and after the shutter
tap, and passes only when a new photo file appears. This path mutates device
state by taking a photo and must only run after plan confirmation.

## Basic Operation Levels

- `打开相机`: implemented in the direct smoke path through `aa start -a com.huawei.hmos.camera.MainAbility -b com.huawei.hmos.camera -m phone`.
- `切拍照模式`: direct capture e2e verifies the current photo-mode node
  `COMPONENT_ID_CONTROL_PHOTO_2`; Hypium/AW keeps the operation as
  `CameraAW.switchToPhotoMode()` for selector-bound projects.
- `点击拍照`: direct capture e2e clicks `COMPONENT_ID_SHUTTER_PHOTO_1` center;
  Hypium/AW keeps the operation as `CameraAW.capture()`.
- `检查相册出现新照片`: direct capture e2e proves a new file appears under
  `/storage/media/100/local/files/Photo`; Hypium/AW keeps the richer UI/API
  operation as `GalleryAW.assertLatestPhotoCreatedAfter(timestamp)`.

## Starter AW Binding

The export includes `CameraAW.ets` and `CameraAWConfig.ets`. The Hypium case
loads `configureCameraAW()` automatically. The domain skill owns how the built-in
Camera app is opened. Bind the target test project by editing
`CameraAWConfig.ets` before building the test HAP:

- `bundleName`, `moduleName`, `abilityName`: preferred launch binding for the
  built-in Camera app. Defaults should be `com.huawei.hmos.camera`, `phone`,
  and `com.huawei.hmos.camera.MainAbility`.
- `launchText`: optional UI text fallback only when ability launch is not
  available.
- `photoModeText`: UI text that selects still-photo mode.
- `captureText`: UI text for the capture control.
- `latestPhotoText`: UI evidence used by gallery verification.

Missing configuration must fail fast with `LEAF_CAMERA_AW_CONFIG_REQUIRED`; it
must not produce a false pass.

## Required Safety

- Do not click, install, clear app data, or mutate device state before the user confirms the plan.
- Read-only device context may include HDC target metadata, `uitest dumpLayout`, and `hilog -x`.
- Any AW method change or device command expansion must become a review proposal first.
- For the first Camera smoke path, use `camera-smoke-preflight` to verify the
  device, built-in Camera target, export, and test-runner HAP/project inputs.
- Use `run-camera-smoke` for confirmed real execution. It must pass no app HAP;
  the only installable package is the Hypium test HAP when needed.
- When no Hypium test HAP is available yet, `run-camera-direct-smoke` may be
  used after plan confirmation as the first safe real-device framework check.
  It starts the built-in Camera app and records UiTest layout plus hilog
  evidence. It does not install packages, capture photos, clear data, or count
  as a full Hypium business pass.

## First Draft Shape

The pytest draft should include:

- `RUN_ID`
- `DOMAIN = "camera"`
- `TARGET_FEATURE = "camera.capture"`
- Ordered step comments copied from the confirmed plan
- Metadata assertions that make the draft executable without implying a
  real-device pass

The Hypium draft should include:

- `import { describe, it, expect } from '@ohos/hypium';`
- `RUN_ID`, `DOMAIN`, and `TARGET_FEATURE`
- Ordered step comments copied from the confirmed plan
- Calls to the basic camera AW operations above for mapped steps
- A real terminal assertion such as `GalleryAW.assertLatestPhotoCreatedAfter(...)`
  instead of `expect(true).assertTrue()`
- A matching OpenHarmony export tree with the test case under
  `src/ohosTest/ets/test/` and a review-required configurable `CameraAW.ets`
  starter AW plus `CameraAWConfig.ets` under `src/ohosTest/ets/aw/`
