# Server V4 구현 보고서

상태: **구현 및 로컬 회귀 검증 완료**
기준일: 2026-08-31
승인 패킷: `docs/work-packets/SERVER_V4_DURABLE_BUNDLE_UPLOAD_PROTOCOL_WORK_PACKET.md`

## 1. 구현 결과

Scanner V2 immutable bundle의 실제 bytes를 받는 Server V4 제품 HTTP 경계를 구현했다.

- `POST /api/v1/scan-sessions/{scan_session_id}/spreads`
- metadata → manifest → bundle files 순서의 bounded multipart decoder
- raw body 전체 적재 없이 controlled spooled stream과 server-owned staging write
- canonical logical upload digest와 `Idempotency-Key`
- manifest/identity/readiness/path/inventory/file size·SHA-256 검증
- file fsync와 same-filesystem atomic directory promotion
- SQLite schema v4 `spread_upload_attempts` journal
- receiving/promoted/accepted/rejected/abandoned lifecycle와 upload lease
- response-loss exact replay, sequence/artifact/key collision
- promotion 전후와 S1 commit 경계의 restart recovery
- S1 `accept_verified_spread()` 재검증과 receipt commit 뒤 ACK
- staging/received quota와 concurrent writer backpressure
- partial orphan cleanup, DB 없는 final quarantine와 accepted/promoted bundle 보호
- combined server V4 wiring과 upload capacity CLI config
- multipart parsing 전 HTTP request admission으로 writer/temporary staging budget 선점

V4 success ACK는 서버 소유 bundle promotion과 S1 spread/page-fragment DB commit이 완료됐음을
뜻한다. OCR, 점역, TTS, fragment READY 또는 datapack revision publish 완료를 뜻하지 않는다.

## 2. Wire와 idempotency 계약

필수 header:

```text
Content-Type: multipart/form-data
Content-Length
X-API-Key
Idempotency-Key
X-ASL-Upload-Digest
```

upload digest는 raw multipart body가 아니라 scan/device/sequence/artifact/spread/source identity,
manifest SHA-256과 path/size/SHA file inventory의 canonical JSON SHA-256이다. 따라서 multipart
boundary와 bundle file 순서가 달라도 동일 logical upload를 판별할 수 있다.

- same key/same digest: 저장된 status/body exact replay
- same key/different digest: `IDEMPOTENCY_KEY_REUSED`
- different key/existing exact S1 spread: 새 storage 없이 기존 receipt 반환
- same sequence/different content: `SPREAD_SEQUENCE_COLLISION`
- artifact reused at another position: `ARTIFACT_ID_COLLISION`
- active writer/temporary storage/quota: retryable structured error
- deterministic bundle invalid: terminal structured reject

현재 S1 exact replay가 `bundle_relative_path`까지 비교하므로, different-key exact logical replay는
새 bundle path로 S1을 다시 호출하지 않고 기존 S1 row identity를 전수 대조해 receipt를 반환한다.

## 3. Crash와 storage recovery

정상 순서:

```text
bounded receive
  -> private staging file fsync
  -> received/v4/{server_upload_id} atomic promotion
  -> journal promoted
  -> S1 accept/DB commit
  -> journal accepted/response commit
  -> HTTP ACK
```

확인한 recovery:

- mid-upload/temporary failure: partial staging 제거, same key full retry
- promotion 뒤 S1 temporary failure: promoted row에서 S1 handoff 재실행
- directory promotion 뒤 journal update 전 crash: server-generated final key를 인식해 promoted 복구
- S1 commit 뒤 response loss: 같은 receipt 반환, spread/fragment 중복 0
- expired/private orphan staging만 TTL cleanup
- promoted/accepted bundle은 quota/cleanup을 위해 자동 삭제하지 않음

Windows에서는 file fsync와 process restart recovery를 검증했다. directory fsync는 지원되는 경우
시도하지만, 실제 갑작스러운 전원 차단 durability를 검증한 것으로 처리하지 않는다.

## 4. 주요 파일

- `document-parser/src/document_parser/server/v4_domain.py`
- `document-parser/src/document_parser/server/v4_multipart.py`
- `document-parser/src/document_parser/server/v4_upload.py`
- `document-parser/src/document_parser/server/s0_migrations.py`
- `document-parser/src/document_parser/server/s0_http.py`
- `document-parser/src/document_parser/server/combined_server.py`
- `document-parser/tests/unit/test_server_v4_upload.py`
- `document-parser/docs/server-v4.md`

## 5. 검증 결과

2026-08-31 로컬 Windows 환경에서 다음을 확인했다.

| 범위 | 결과 |
|---|---:|
| Server V4 집중 | 19 passed |
| S0/S1/C0/V4/combined 집중 | 51 passed |
| Document Parser 전체 | 571 passed, 4 skipped |
| Device Runtime 전체 | 47 passed |
| Book Scanner 전체 | 288 passed |

V4 집중 테스트는 다음을 포함한다.

- v3 → v4 migration과 restart no-op
- 실제 Scanner V2 fixture bundle HTTP acceptance
- server-owned promotion과 S1 left/right fragment receipt
- same-key exact response replay와 different-key S1 reconciliation
- key/sequence/artifact collision
- file hash reject journal과 terminal replay
- staging quota pre-reject
- staging allocation 실패 시 claim 즉시 abandon과 재시도 가능 상태 복원
- valid lease 보존과 expired same-key claim의 즉시 full retry
- S1 temporary failure 뒤 promoted recovery
- directory promotion 뒤 journal update 전 crash recovery
- seal cutoff gate
- partial orphan cleanup
- DB 없는 server-generated final directory의 non-destructive quarantine
- retryable HTTP capacity 오류의 `Retry-After`
- raw multipart part-order 검증
- 실제 `127.0.0.1` HTTP server/stdlib client upload round trip

Book Scanner는 한글 Windows 사용자 temp 경로 문제를 피하기 위해 저장소 내부 ASCII basetemp에서
재실행했고 288개가 통과했다. 첫 `D:/Projects/OCR/tmp` basetemp 실행의 permission error는 제품
assertion 실패가 아니며, 저장소 내부 `book-scanner/pytest_tmp_v4_run2`에서 정상 검증했다.

## 6. 완료로 처리하지 않은 사항

- Scanner V3-B production sender와 LAPTOP durable outbox
- process/OS restart 뒤 device-side sequence/idempotency/artifact 복원
- ACK 후 Scanner cache eviction과 outbox quota/freeze
- 실제 4K Scanner bundle의 장시간/대용량 upload 처리량·disk 사용량
- 외부 LAN/인터넷, fixed DNS, TLS certificate, VPN/tunnel fault test
- reverse proxy의 body/timeout limit 정합화
- 실제 PaddleOCR-VL/Piper까지 이어지는 V4 full-model E2E
- actual sudden power-loss filesystem durability
- Windows 자동 시작과 Raspberry Pi systemd/storage/camera/GPIO/audio/resource 검증
- resumable chunk upload
- device별 credential/mTLS/rate-limit hardening
- accepted/rejected bundle 장기 retention과 관리자 garbage collection
- 배포, commit, push, PR

따라서 다음 우선순위는 Server V4 확장이 아니라 **Scanner V3-B sender + LAPTOP durable outbox 작업
패킷 작성 및 승인**이다. V3-B는 V4 wire 계약을 사용해 `DeliveryPort.queue/pending_status/
flush_through`를 실제 persistence와 retry/ACK lifecycle로 구현해야 한다.
