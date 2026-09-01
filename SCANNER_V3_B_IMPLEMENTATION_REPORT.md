# Scanner V3-B 구현 보고서

상태: **핵심 기능 구현 및 로컬 회귀 검증 완료**
기준일: 2026-09-01
승인 패킷: `SCANNER_V3_B_DURABLE_OUTBOX_SENDER_WORK_PACKET.md`

## 1. 구현 결과

기존 `DeviceFlowCoordinator`의 `DeliveryPort`를 실제 single-sender durable adapter로 구현했다.

- Scanner V2 manifest/identity/readiness/path/inventory/size/SHA-256 검증
- SQLite schema v1 outbox와 exact queue replay/collision
- stable scan sequence, artifact, digest와 `v3b-{upload_digest}` idempotency key
- raw multipart 전체를 만들지 않는 stdlib `http.client` file streaming
- Server V4 metadata/manifest/bundle-file wire 계약과 정확한 `Content-Length`
- network uncertainty와 retryable HTTP response의 same-key retry
- 2xx receipt identity 전수 대조 뒤에만 durable ACK
- deterministic reject reason과 artifact 보존
- startup `sending -> retrying` 복구
- ACK DB commit 이후에만 confined artifact cache cleanup
- `pending_status()`/`flush_through()`의 durable row 권위
- C0 identity/origin/API key를 재사용하는 LAPTOP composition

## 2. 대표 restart 검증

이번 핵심 패킷에서는 다음 경계만 선택했다.

1. queue commit 뒤 network call 전 adapter restart
2. Server V4/S1 commit 뒤 client response loss와 adapter restart
3. 2xx 수신 뒤 local ACK commit 직전 process 종료

모든 retry는 같은 key/digest/sequence를 사용한다. 실제 loopback response-loss 테스트에서 최종
receipt는 하나였고 Server `scan_spreads` 1개와 left/right fragment 2개만 생성됐다.

## 3. 주요 파일

- `device-runtime/src/asl_device/delivery_config.py`
- `device-runtime/src/asl_device/delivery_domain.py`
- `device-runtime/src/asl_device/delivery_store.py`
- `device-runtime/src/asl_device/delivery.py`
- `device-runtime/src/asl_device/adapters/http_v4.py`
- `device-runtime/src/asl_device/delivery_composition.py`
- `device-runtime/tests/unit/test_delivery_v3b.py`
- `device-runtime/tests/unit/test_http_v4.py`
- `device-runtime/tests/integration/test_v3b_v4_local_http.py`
- `device-runtime/docs/device-delivery-v3b.md`

## 4. 검증 결과

2026-09-01 로컬 Windows 환경 결과:

| 범위 | 결과 |
|---|---:|
| Device Runtime 전체 | 59 passed |
| Document Parser 전체 | 571 passed, 4 skipped |
| Book Scanner 전체 | 288 passed |
| V3-B unit 집중 | 11 passed |
| V3-B → V4 actual loopback | 1 passed |

집중 검증은 queue network call 0, stable digest/key, exact replay/collision, timeout/backoff,
strict receipt validation, deterministic reject, restart normalization, ACK-before-cleanup ordering,
post-queue file mutation, multipart content length와 response-loss server replay를 포함한다.

## 5. 의도적으로 완료하지 않은 hardening

- 다중 process/sender/writer, lease와 leader election
- global quota/disk watermark/capture freeze 일반화
- 별도 artifact copy/blob store/deduplication
- 장기 rejected retention, quarantine와 관리자 GC
- exhaustive crash/power-loss/network chaos matrix
- 전체 Coordinator active scan/session process restart 복원
- queue commit 전 orphan artifact 자동 adoption
- accepted M1 identity bank 영속화
- 외부 TLS/proxy/VPN, Windows service와 Raspberry Pi systemd

따라서 다음 단계는 V3-B hardening이 아니라 **LAPTOP Device Integration E0 패킷**이다. E0에서
실제 ScannerRuntime/camera, Coordinator, C0, V3-B, Server V4, STM/beep/TTS 경계를 한 프로세스의
제품 흐름으로 연결해야 한다.
