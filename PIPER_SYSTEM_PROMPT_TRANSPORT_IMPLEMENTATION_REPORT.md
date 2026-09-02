# Piper System Prompt Transport Implementation Report

## Result

Production system guidance no longer depends on Windows SAPI when Piper transport playback is enabled. Server S0 synthesizes and serves system prompts and catalog titles from the shared Piper `_system` pool. Device Runtime routes those resources and reading-session audio through one bounded-RAM playback arbiter.

## Contract delivered

- Fixed cue names map to Korean UI text only on the server.
- The production combined server uses its configured Piper voice for fixed cues and dynamic datapack titles.
- `_system/audio_index.json` merges navigation, UI, and title resources without dropping earlier entries and reuses them after restart.
- Catalog title references use `s0-system-audio:<opaque-id>` and are bound to the requesting device.
- Fixed cues and opaque title resources are available only through authenticated S0 endpoints.
- The Device HTTP adapter applies the existing WAV content type, size, digest, PCM format, and duration checks.
- One controller and one `AudioPlaybackPort` serialize system and document WAVs.
- Screen speech precedes initial catalog title speech; rapid title movement replaces stale speech; a new reading generation interrupts prior playback; capture-complete/save/error cues have higher priority than ordinary guidance.
- The device cache remains RAM-only and bounded by entry and byte limits.
- `windows_audio` is an explicit legacy SAPI diagnostic backend and cannot be enabled together with Piper transport playback.

## Automated evidence

Production Full-Model Desktop E2E (`--no-playback`) passed on 2026-09-02:

- Evidence: `tmp/e0b-production-runs/e0b-production-full-model-20260902T144027Z-0760dc80/evidence`
- Scan session: `scan-4b1dcb7f9bc5412f84fda287ecc5ee66`
- Datapack: `datapack-09f3bd289c514604bc6550cca68313c4`
- Spread receipts/fragments/duplicates: `2 / 4 / 0`
- Pages with accessible items/non-empty braille: `4 / 4`
- OCR/TTS engines: `paddleocr-vl / piper`
- Verified audio resources: `151`
- System audio fetches: `2`
- System endpoint unauthenticated request rejected: `true`
- Cross-device title reference rejected: `true`
- Playback failures: `0`
- Client WAV persistence: `false`

The no-playback run validates synthesis, transport, authorization, queueing, cache, and PCM handoff with the automated player. It does not replace the already separate human listening check or Raspberry Pi ALSA/PipeWire evidence.

## Regression evidence

- Device Runtime: 188 passed.
- Book Scanner: 301 passed.
- Document Parser: 594 passed, 4 real-Piper unit tests skipped unless their standalone model environment variables are set.
- Real production E2E independently loaded real PaddleOCR-VL and Piper and passed, so the skipped narrow unit tests do not represent an untested production model path.

## Remaining hardware evidence

- Android phone exposed as UVC/virtual webcam through the live camera adapter.
- STM32 button and braille display on the final pin/serial wiring.
- Raspberry Pi ALSA/PipeWire playback adapter and physical speaker listening evidence.
