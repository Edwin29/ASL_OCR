# Android UVC Camera Host Runbook

## Purpose

This procedure connects an Android phone that Windows exposes as a camera device to the production Book Scanner
host. It does not use an MP4 fallback. The camera probe can run before the server, STM32, or OCR models are started.

## 1. Prepare the phone

Use a USB data cable, select the phone's native webcam/UVC mode when available, keep the phone unlocked, select the
rear camera, and close Windows applications that may already own the camera. Mount the phone in landscape above the
open book. A vendor virtual-camera application is acceptable only when it registers an ordinary Windows camera
device; its installation and network protocol are outside this procedure.

## 2. Enumerate camera identities

Run from the repository root:

```powershell
Set-Location D:\Projects\OCR
tools\windows\e0b-android-uvc-camera.bat --list --backend dshow
```

Copy the exact Android `stable_id` when possible. If reconnecting the same USB port changes its transient suffix,
use the exact unique `name`. A name shared by two devices is intentionally rejected as ambiguous.

## 3. Create the isolated configuration

Keep the live-camera configuration separate from the replay configuration:

```powershell
$preparedRoot = "D:\ASL_OCR_E0B"
Copy-Item `
  D:\Projects\OCR\device-runtime\device-app.android-uvc.example.toml `
  "$preparedRoot\device-app.android-uvc.toml"
```

Edit `device-app.android-uvc.toml`:

- replace `camera_selector` with the exact enumerated name or stable ID;
- set `camera_fallback_index` to the OpenCV camera index verified on this desktop;
- start with `camera_backend = "dshow"` and `camera_fourcc = "MJPG"`;
- set `camera_rotation` to `0`, `90`, `180`, or `270` after checking orientation;
- leave `camera_mirror = false` unless the captured frame itself, not merely the phone preview, is mirrored;
- keep `opaque_identity_max_collection_ms = 8000` for the first physical acceptance;
- keep all model, connectivity, secret, state, and artifact paths inside the prepared root.

The Windows PnP API proves that the selected phone identity is present but does not expose a reliable OpenCV index.
For that reason Windows requires the selector and an explicitly verified fallback index together. If the selected
identity is absent, the host refuses to open the index and cannot silently use the built-in webcam.

## 4. Probe mode and liveness

Move a printed marker once during the sample window so `liveness_observed` can become true:

```powershell
$preparedRoot = "D:\ASL_OCR_E0B"
$report = "$preparedRoot\reports\android-uvc-probe.json"

tools\windows\e0b-android-uvc-camera.bat `
  --config "$preparedRoot\device-app.android-uvc.toml" `
  --samples 20 `
  --interval-ms 150 `
  --report $report
```

The command must report `status=passed`, `source_profile=android_uvc`, `replay_path_used=false`, the expected
`selection_method`, and requested/effective mode agreement. `liveness_observed=false` is diagnostic rather than an
automatic failure because a correctly operating camera may observe a perfectly still page; repeat while moving a
marker before accepting the physical setup.

No preview frame is persisted by this command. If visual orientation must be reviewed, use the Windows Camera app
briefly, close it, and then rerun the probe so it releases the device.

## 5. Run the live integration

Start the configured server and tunnel exactly as for the existing E0-B environment, then run:

```powershell
Set-Location D:\Projects\OCR
tools\windows\e0b-android-uvc-run.bat D:\ASL_OCR_E0B
```

Use the console controls to enter capture mode, select New Datapack, present a spread, turn the page after the
capture-complete Piper cue, and confirm after all intended spreads have been ACKed. The app must return to the capture
mode datapack catalog after saving. Open the datapack from reading mode to verify accessible items, non-empty braille
cells, and Piper audio.

When no mode jumper/lever is available, start directly in reading mode:

```powershell
tools\windows\e0b-laptop-read.bat D:\ASL_OCR_E0B android-uvc
```

## 6. Failure checks

- Disconnect USB during a disposable scan. The host must produce a bounded camera/session error and must not switch
  to another camera.
- Reconnect the phone and start a new scan. The new scan/session and spread IDs must differ from the failed run.
- Preserve the probe report, console JSONL, boundary report, and server 2/4/0-style evidence for the run directory.

Actual OCR meaning accuracy is not an Android UVC transport acceptance criterion. Empty, corrupted, incorrectly
oriented, or mirrored input is a transport failure; imperfect recognition of a valid frame remains later OCR/camera
calibration work.
