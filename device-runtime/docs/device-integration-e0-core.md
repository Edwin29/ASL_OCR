# Device Integration E0-Core

E0-Core is the local development-host composition of the existing Device Coordinator, Book
Scanner, C0 presence, S0 control plane clients, V3-B outbox, and Server V4 upload client. The word
"device host" describes the role; a separate physical laptop is not required for this milestone.

## Entrypoint

Install or expose both local packages, then run the Device application with an explicit config.

```powershell
$env:PYTHONPATH='device-runtime/src;book-scanner/src'
python -m asl_device --config D:\device-config\device-app.toml
```

The Server S0/C0/V4 application runs separately. The Device production composition communicates
with it only through HTTP.

## Configuration

Start from `device-app.e0.example.toml` and `device-connectivity.e0.example.toml`. Relative paths
are resolved from the file that contains them. The API key remains in the separate file referenced
by the connectivity config.

Important startup invariants:

- Scanner `ready_root` equals the V3-B `artifact_root`;
- Scanner staging and ready roots use the same filesystem;
- the outbox database stays outside the ready artifact root;
- the server origin and device ID come only from the C0 config;
- UVDoc and M1 Paddle assets are explicit local paths;
- missing or hash-mismatched M1 assets fail startup instead of selecting another model.

The automated E0 acceptance test injects a deterministic Scanner engine, so its placeholder model
paths are not read. The normal entrypoint constructs `LocalBookScannerEngineFactory` and validates
the configured replay/camera and model assets.

## Local controls and feedback

The console control adapter accepts one command per line. Examples include `up`, `down`, `confirm`,
`confirm long`, `page_next`, and `lever activated`. It converts commands to the existing
`DeviceInputEvent` contract; it is not an STM serial protocol.

Feedback is emitted as one JSON object per line. These records contain semantic feedback codes and
small domain details, not API keys, image bytes, or manifest paths. In particular:

- `spread_sent` follows a durable, identity-matched V4 ACK;
- `finalizing` follows a successful V3-B flush and S0 seal request;
- `datapack_saved` follows the server READY result.

Physical adapters are implemented under Device Integration E0-B — Laptop Acceptance, but their
actual Laptop/camera/STM/speaker/LAN evidence remains pending. See
`device-integration-e0b-laptop.md`.

## Scanner bridge

`BookScannerRuntimeAdapter` creates one `SampledFrameEngine` per scan session. It converts only
artifact-ready, guidance, and fatal events into the Device Scanner contract. Other Scanner events
remain diagnostics.

Delivery updates are mapped back to the Scanner engine without reinterpreting ACK:

```text
queued/sending -> delivery_queued
retrying       -> delivery_retrying
acked          -> delivery_confirmed(receipt_id)
rejected       -> delivery_rejected(reason)
```

Freeze stops new Scanner polling but allows a pending artifact to receive its terminal delivery
update. The engine and camera close after that terminal update. Cancel never deletes the V3-B
outbox or its source artifact.

## Verified local scenario

The integration test uses actual local HTTP, C0, S0, V3-B multipart streaming, V4/S1 persistence,
SQLite, finalization, and reading-session APIs. It deliberately discards the first successful V4
response after the server commit. The Device retries the same sequence, digest, and idempotency key;
the server retains one spread and two page fragments. Scanner confirmation, `spread_sent`, seal,
and `datapack_saved` each occur once.

This does not validate a physical laptop, real camera exposure/focus, STM serial, audio output,
external networking, service startup, or whole-Coordinator active-session restart.
