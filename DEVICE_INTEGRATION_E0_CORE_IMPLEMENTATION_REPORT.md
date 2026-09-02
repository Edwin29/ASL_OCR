# Device Integration E0-Core 구현 보고서

상태: **핵심 local composition 구현 및 회귀 검증 완료**
기준일: 2026-09-01
승인 패킷: `docs/work-packets/DEVICE_INTEGRATION_E0_CORE_LOCAL_COMPOSITION_WORK_PACKET.md`

## 1. 구현 결과

현재 개발용 데스크톱에서 다음 경계를 한 Device application으로 구성했다.

- scan-session-scoped `SampledFrameEngine` factory
- Book Scanner event/artifact를 Device `ScannerRuntime`으로 변환하는 concrete bridge
- delivery queued/retrying/ACK/reject callback의 Scanner 역방향 전달
- freeze 뒤 새 capture 억제와 pending terminal update 후 camera/engine close
- C0 config를 device ID, server origin과 API key의 단일 authority로 사용하는 composition
- S0 catalog/scan/reading clients, C0 supervisor, V3-B와 Coordinator wiring
- strict TOML config, path authority와 model fail-fast
- single-threaded Coordinator application loop
- scripted/console local controls와 semantic JSON feedback
- `python -m asl_device --config ...` entrypoint
- actual local C0/S0/V4/S1 HTTP + SQLite E2E

Scanner와 V3-B 사이의 artifact ID는 한 개의 안전한 경로 요소여야 하며, manifest는 configured ready
root 바로 아래에 있어야 한다. 이 검토 과정에서 V3-B enqueue 전 symlink/path resolution 검증도
lexical root 기준으로 보강했다.

## 2. Actual local E2E 결과

E2E는 다음 경계를 실제 구현으로 사용했다.

- Werkzeug local HTTP server
- C0 health/presence와 ONLINE gate
- S0 catalog/datapack/scan/seal/reading API
- V3-B SQLite outbox와 streaming multipart client
- Server V4 upload journal과 S1 durable spread/fragment commit
- S1 fragment worker/finalization과 datapack revision publish

Scanner hardware 대신 deterministic engine이 immutable V2 bundle을 생성했다. 첫 V4 request는 server
commit과 receipt 생성 뒤 client response만 유실시켰다. retry는 같은 sequence/digest/idempotency key를
사용했고 최종 결과는 다음과 같았다.

- server spread 1개
- left/right fragment 2개
- V3-B attempt 2회
- Scanner terminal ACK callback 1회
- `SPREAD_SENT` 1회
- seal/finalization 1회
- `DATAPACK_SAVED` 1회
- reading session open
- ACK 뒤 local artifact cleanup

## 3. 주요 파일

- `device-runtime/src/asl_device/adapters/book_scanner_runtime.py`
- `device-runtime/src/asl_device/app_config.py`
- `device-runtime/src/asl_device/application.py`
- `device-runtime/src/asl_device/local_composition.py`
- `device-runtime/src/asl_device/__main__.py`
- `device-runtime/src/asl_device/adapters/local_controls.py`
- `device-runtime/src/asl_device/adapters/local_feedback.py`
- `book-scanner/src/book_scanner/video/runtime_composition.py`
- `device-runtime/tests/integration/test_e0_local_composition.py`
- `device-runtime/docs/device-integration-e0-core.md`

## 4. 검증 결과

2026-09-01 로컬 Windows 결과:

| 범위 | 결과 |
|---|---:|
| Device Runtime 전체 | 69 passed |
| Book Scanner 전체 | 288 passed |
| Document Parser 전체 | 571 passed, 4 skipped |
| E0-Core 신규 unit | 9 passed |
| E0-Core actual HTTP/SQLite E2E | 1 passed |

Document Parser 실행의 `.pytest_cache` permission warning은 test failure가 아니며 571개 test 결과에는
영향이 없었다.

## 5. 완료하지 않은 범위

- 별도 물리 Laptop 연결과 배포
- 실제 camera exposure/focus/장시간 capture
- 실제 UVDoc/Paddle asset을 사용한 E0 application smoke run
- STM serial/buttons와 debounce/reconnect
- beep/TTS/audio playback
- LAN, external TLS/DNS/VPN과 network fault validation
- Windows service/auto-start
- whole Coordinator active scan/session restart checkpoint
- queue 이전 orphan artifact adoption
- accepted M1 identity bank persistence
- generalized quota/retention/GC와 exhaustive crash matrix
- Raspberry Pi camera/GPIO/audio/systemd/resource validation

따라서 다음 hardware 단계는 **Device Integration E0-B — Laptop Acceptance**다. 실제 장치가 준비되기 전에는 외부 endpoint
또는 Pi 이식을 E0-Core 완료 조건으로 소급하지 않는다.
