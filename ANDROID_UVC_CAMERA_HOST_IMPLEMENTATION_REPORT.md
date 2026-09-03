# Android UVC Camera Host Implementation Report

## Result

The software host boundary is implemented. Device Runtime can select an `android_uvc` Scanner profile, require an
OS-enumerated Android camera identity before opening a capture index, negotiate and report the effective camera
mode, normalize orientation, perform bounded warm-up/reopen, and feed the unchanged `SampledFrameEngine` pipeline.

Actual Android-phone capture evidence remains pending because the development desktop currently enumerates only a
Logitech C270 camera. This report does not claim desktop or Raspberry Pi physical acceptance.

## Delivered contract

- Added the explicit `android_uvc` profile and typed selector, backend, fallback index, FOURCC, rotation, mirror,
  warm-up, and bounded reopen settings.
- Windows enumerates Camera/Image PnP identities and requires an exact unique selector match. Because Windows PnP
  does not provide a reliable OpenCV index mapping, an explicitly configured index is opened only while that
  identity is present; there is no silent built-in-camera fallback.
- Linux prefers stable `/dev/v4l/by-id` paths and falls back to enumerated `/dev/video*` paths only when no stable
  alias exists.
- OpenCV capture now supports explicit backend and FOURCC, requested/effective mode verification, orientation,
  bounded warm-up/reopen, monotonically increasing frame IDs, and idempotent release.
- Android source discovery/open failures use the existing `CameraUnavailableError` and Scanner session-error path.
- Added a secret-safe probe report that records a digest rather than the raw selected hardware identity.
- Added separate Windows list/probe and live-run entry points. Neither enables MP4 fallback.
- Added an isolated example config and physical runbook.

## Automated evidence

- Android UVC/source/config/probe focused tests: 43 passed.
- Book Scanner full suite: 309 passed.
- Device Runtime full suite: 195 passed.
- Document Parser full suite: 623 passed, 4 skipped, 15 subtests passed.
- Python compileall: passed.
- `git diff --check`: passed; only repository line-ending notices were emitted.

The four Document Parser skips are the existing optional real-Piper narrow tests and are unrelated to the camera
host boundary.

## Host enumeration evidence

The Windows list entry point executed successfully on 2026-09-03 with DirectShow and returned one device:

- device count: 1
- camera name: `Logi C270 HD WebCam`
- stable identity present: yes
- Android camera present: no

This confirms the enumeration path works and also confirms why Android physical acceptance cannot yet be claimed.

## Operator entry points

```powershell
# List exact Windows identities.
tools\windows\e0b-android-uvc-camera.bat --list --backend dshow

# Probe a prepared android_uvc config.
tools\windows\e0b-android-uvc-camera.bat `
  --config D:\ASL_OCR_E0B\device-app.android-uvc.toml `
  --samples 20 --interval-ms 150 `
  --report D:\ASL_OCR_E0B\reports\android-uvc-probe.json

# Run the existing production Scanner/Coordinator pipeline with live Android frames.
tools\windows\e0b-android-uvc-run.bat D:\ASL_OCR_E0B
```

The complete preparation, liveness, unplug/reconnect, capture, server evidence, and reading verification procedure is
in `docs/ANDROID_UVC_CAMERA_HOST_RUNBOOK.md`.

## Remaining physical evidence

1. Connect a phone that exposes native USB webcam/UVC mode or an approved OS virtual-camera device.
2. Copy the example config into the prepared root and set the exact selector plus the manually verified OpenCV index.
3. Obtain a passing probe with requested/effective mode agreement and user-observed liveness/orientation.
4. Capture at least one live spread through Scanner → V4 → S1 → S0 without replay fallback or duplicate receipt.
5. Verify capture-complete Piper guidance, return to the capture datapack catalog, reading-mode braille/audio, and
   bounded USB unplug/reconnect behavior.
6. Repeat the same selector/capture contract on Raspberry Pi V4L2 when physical hardware is available.
