# Android Cross-Platform Camera Options

Research snapshot: 2026-09-03

## Decision

Prefer **Android IP Camera** as the production candidate for using the same Galaxy phone camera with Windows and
Raspberry Pi/Linux. It exposes host-independent HTTPS endpoints instead of depending on Windows Connected Camera,
DirectShow, or a native Android USB-webcam mode.

- Source: <https://github.com/DigitallyRefined/android-ip-camera>
- F-Droid: <https://f-droid.org/packages/com.github.digitallyrefined.androidipcamera/>
- License: MIT
- Android requirement: Android 7 or newer
- Relevant endpoints:
  - `https://PHONE_IP:4444/video/snapshot` for a single JPEG
  - `https://PHONE_IP:4444/video/mjpeg` for an MJPEG stream
  - `https://PHONE_IP:4444/video/h264` for raw H.264
- Connection candidates: isolated Wi-Fi/hotspot for initial tests; USB tethering for a more stable host-to-phone
  network after it is verified on both Windows and Raspberry Pi.

The first ASL OCR integration should use bounded snapshot fetches because the Book Scanner samples a mostly static
page and does not require a 30 FPS virtual webcam. The adapter must have explicit authentication and TLS trust,
response-size and timeout limits, bounded reconnects, decoded-frame and resolution validation, source provenance,
and no fallback to another camera or replay input.

## Alternatives

### scrcpy

- Source: <https://github.com/Genymobile/scrcpy>
- License: Apache-2.0
- Mature, supports USB or TCP/IP and Android camera capture on Android 12 or newer.
- Windows and Linux hosts are supported, but direct virtual-webcam output uses V4L2 and is Linux-only. A common
  Windows/Linux ASL OCR path would therefore need a custom H.264 stream/decoder adapter.
- Keep as the fallback when USB/ADB transport is more important than a simple HTTP camera contract.

### Nexora

- Source: <https://github.com/akashlenvo/Nexora>
- License: MIT
- Provides Windows DirectShow and Linux V4L2 virtual cameras over USB or Wi-Fi.
- The documented Linux targets are currently x86_64. It is new and does not establish Raspberry Pi ARM64 support,
  so it is not the production choice for this project.

### Excluded as the common production basis

- Windows Connected Camera is useful for Laptop experiments but does not provide the Raspberry Pi path.
- Camo and DroidCam may be useful diagnostic fallbacks, but they are not selected as the project's end-to-end open
  source transport contract.
- A raw `pc_camera` index is insufficient for production because it may silently select the Laptop's built-in
  webcam after the phone disconnects.

## Required future work

Add a distinct `android_ip_camera` scanner profile rather than weakening the existing guarded `android_uvc` profile.
Implement and test an HTTP snapshot/MJPEG source, secrets and certificate provisioning, a live probe, Windows and
Raspberry Pi launch wrappers, disconnect/reconnect behavior, and evidence that the selected source was never replaced
by a local webcam or replay file.
