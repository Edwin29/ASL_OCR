# Scanner V3-B — Single-Sender Durable Outbox + Server V4 Client 작업 패킷

상태: **승인됨 · 핵심 기능 구현 및 로컬 회귀 검증 완료**
작성일: 2026-09-01
구현 결과: `SCANNER_V3_B_IMPLEMENTATION_REPORT.md`
선행 조건: Scanner V2 immutable two-page bundle, Scanner V3-A.5 single in-flight/ACK identity
lifecycle, Integration V0 `DeliveryPort`, Device Connectivity C0, Server V4 durable upload API
후속 조건: LAPTOP Device Integration E0, 필요성이 확인된 V3-B 운영 hardening

## 1. 목표

기존 `DeviceFlowCoordinator`의 `DeliveryPort`를 실제 LAPTOP 구현으로 연결한다.

```text
Scanner immutable artifact
  -> durable outbox enqueue
  -> single poll-driven sender
  -> Server V4 multipart upload
  -> receipt identity 검증
  -> durable ACK commit
  -> Scanner ACK callback / flush / seal 진행
```

핵심 완료 조건은 다음 두 가지다.

1. 서버가 확인하지 않은 artifact를 ACK로 처리하지 않는다.
2. timeout·response loss·process restart 재전송이 같은 sequence/artifact/idempotency key를 사용해
   Server V4/S1 fragment를 중복 생성하지 않는다.

이번 패킷은 위 흐름을 닫는 **single-process, single-sender prototype**이다. 운영 hardening을 한
패킷에 함께 일반화하지 않는다.

## 2. 핵심 기능과 hardening 분리

### 2.1 이번 패킷의 핵심 기능

- 기존 `DeliveryPort.queue/pending_status/flush_through` concrete 구현
- SQLite outbox ledger와 atomic enqueue
- Scanner V2 manifest/file inventory의 로컬 재검증
- stable sequence, artifact ID, idempotency key, upload digest 영속화
- Server V4 bounded multipart streaming client
- timeout/response loss의 same-key full retry
- 2xx response의 receipt identity 전수 대조 뒤에만 durable ACK
- deterministic server reject 보존과 `DeliveryStatus` mapping
- adapter 재생성/process restart 시 미확정 `SENDING`을 `RETRYING`으로 복구
- ACK 이후에만 source artifact cache 제거
- 실제 LAPTOP loopback V3-B → V4 → S1 round trip

### 2.2 별도 hardening 패킷으로 미루는 항목

- 다중 process/sender/writer와 lease·leader election
- global/per-device quota, disk watermark, capture freeze 정책 일반화
- artifact 복사본·content-addressed blob store·deduplication
- resumable/chunk upload
- 장기 rejected retention, quarantine, 관리자 GC
- 모든 filesystem/network crash 지점을 열거한 exhaustive matrix
- 전체 Coordinator active scan/session의 process restart 복원
- M1 accepted identity bank 영속화
- 외부 TLS endpoint, proxy, VPN, 장시간 부하와 network chaos
- Windows service, Raspberry Pi systemd와 전원 차단 검증

이 항목들은 잘못되거나 불필요하다는 뜻이 아니다. 현재 핵심 경로의 선행 조건으로 묶지 않고,
실제 E2E 관측 결과가 필요성을 보일 때 별도 승인한다.

## 3. 현재 코드와 닫아야 할 공백

이미 존재하는 계약:

- `book-scanner`: 같은 full-spread frame에서 만든 immutable V2 bundle과 `manifest.json`
- Scanner V3-A.5: 한 artifact만 pending으로 두고 ACK 전 새 artifact 생성 억제
- `device-runtime`: 순수 `DeliveryPort`와 Coordinator의 stable sequence/flush 계약
- C0: server origin, provisioned device ID, API key와 ONLINE gate
- Server V4: bounded multipart, canonical digest, idempotency journal, S1 durable receipt

현재 없는 것:

- `DeliveryPort` production adapter
- device-side durable sequence/artifact/idempotency ledger
- V4 multipart client
- receipt 검증과 ACK persistence
- response-loss resend와 ACK 후 artifact cleanup

V3-B는 Scanner 영상 판단이나 Server V4 저장 정책을 다시 구현하지 않는다.

## 4. 책임 배치

### 4.1 Scanner

- 로컬 영상/identity 판단
- 좌우 atomic artifact 생성
- `ScannerArtifactReady` event 발행
- `DeliveryUpdate`를 받아 pending identity를 ACK 또는 reject 처리

### 4.2 V3-B Delivery adapter

- immutable artifact의 outbox 소유권 pin
- sequence/idempotency/digest 영속화
- bundle bytes 전송과 retry
- V4 response 검증
- durable delivery status와 receipt 보존
- ACK 뒤 artifact cache cleanup

### 4.3 Server V4/S1

- request/file hash 검증
- server-owned atomic promotion
- upload idempotency와 response replay
- S1 spread/page-fragment DB commit
- durable receipt 반환

Heartbeat success, HTTP body 송신 완료, TCP close 없음은 ACK 근거가 아니다.

## 5. 최소 상태 흐름

```text
queue()
  -> local manifest/inventory 검증
  -> SQLite QUEUED commit
  -> return DeliveryStatus.QUEUED

pending_status() 또는 flush_through()
  -> 가장 오래된 미확정 row 1개 선택
  -> SENDING commit
  -> V4 streaming upload
       ├─ timeout/connection/retryable response -> RETRYING
       ├─ deterministic content/state reject   -> REJECTED
       ├─ auth/incompatible/malformed success  -> artifact 보존 + FatalPortError
       └─ valid ACK identity match             -> ACKED commit
  -> ACK commit 뒤 source artifact cleanup 시도
```

background thread는 두지 않는다. Coordinator의 기존 poll 경계가 전송 진행을 구동하며, 한 번의
호출은 최대 한 artifact의 한 upload attempt만 수행한다.

## 6. Durable boundary와 불변식

### 6.1 Enqueue 성공의 의미

`queue()` 성공은 다음이 SQLite transaction으로 고정됐음을 뜻한다.

- scan session ID와 positive client sequence
- artifact/spread/source-frame identity
- canonical manifest path와 manifest SHA-256
- manifest file inventory snapshot
- V4 metadata, upload digest와 idempotency key
- initial `QUEUED` status

`queue()`는 네트워크 요청을 하지 않는다. DB commit 실패 시 `RecoverablePortError`를 내고
Coordinator는 같은 sequence/artifact로 `queue()`를 재시도한다.

### 6.2 ACK 불변식

다음 값이 모두 local row와 일치해야만 `ACKED`를 commit한다.

```text
status == acked
receipt_id: non-empty
scan_session_id
sequence
artifact_id
manifest_sha256
upload_digest
```

HTTP 200/201만으로 ACK하지 않는다. response JSON 손상, 필드 누락, identity mismatch는 ACK가
아니며 source artifact를 삭제하지 않는다.

### 6.3 중복 방지 불변식

- `(scan_session_id, sequence)`는 정확히 한 logical artifact만 소유한다.
- 같은 queue call은 기존 row를 반환하며 attempt나 sequence를 새로 만들지 않는다.
- 같은 위치에 다른 artifact/digest를 넣으면 conflict로 중단한다.
- retry는 저장된 key/digest/metadata/inventory를 그대로 사용한다.
- ACKED/REJECTED terminal update는 뒤늦은 retry 결과로 되돌리지 않는다.
- `flush_through(N)`은 `1..N` 모든 row가 ACKED일 때만 `FLUSHED`다.

## 7. Artifact filesystem 정책

Scanner V2 artifact는 이미 private staging에서 검증된 뒤 같은 filesystem의 final directory로
원자적으로 commit된다. V3-B 최소 구현은 이를 다시 복사하지 않는다.

- `artifact_root/{artifact_id}/manifest.json`을 outbox source로 pin한다.
- configured `artifact_root` 밖의 path, symlink/junction, `artifact_id`와 다른 parent는 거부한다.
- queue 시 manifest와 모든 listed file의 path/size/SHA-256을 검증한다.
- upload attempt 직전에도 manifest hash와 inventory를 다시 검증한다.
- QUEUED/SENDING/RETRYING/REJECTED 동안 directory를 보존한다.
- valid ACK를 DB에 먼저 commit한 뒤에만 해당 artifact directory를 confined delete한다.
- ACK 뒤 cleanup 실패는 ACK를 취소하지 않으며 terminal row에 cleanup 오류만 남긴다.

이번 패킷의 durable 보장은 **성공한 `queue()` 이후**다. Coordinator가 `queue()`를 호출하기 전
process가 종료된 orphan artifact 자동 재할당과 전체 active scan 복원은 E0/후속 hardening 범위다.

## 8. SQLite outbox schema v1

권장 파일: `device-runtime/src/asl_device/delivery_store.py`

```text
delivery_schema_migrations
  version, applied_at

delivery_outbox
  outbox_id TEXT PRIMARY KEY
  scan_session_id TEXT NOT NULL
  sequence INTEGER NOT NULL
  device_id TEXT NOT NULL
  artifact_id TEXT NOT NULL
  spread_id TEXT NOT NULL
  source_frame_id TEXT NOT NULL
  manifest_path TEXT NOT NULL
  manifest_sha256 TEXT NOT NULL
  inventory_json TEXT NOT NULL
  file_count INTEGER NOT NULL
  total_file_bytes INTEGER NOT NULL
  upload_digest TEXT NOT NULL
  idempotency_key TEXT NOT NULL
  status TEXT NOT NULL
    CHECK(status IN ('queued','sending','retrying','acked','rejected'))
  attempt_count INTEGER NOT NULL DEFAULT 0
  receipt_id TEXT NULL
  server_accepted_at TEXT NULL
  last_http_status INTEGER NULL
  last_error_code TEXT NULL
  last_error_detail TEXT NULL
  cleanup_error TEXT NULL
  created_at TEXT NOT NULL
  updated_at TEXT NOT NULL
  terminal_at TEXT NULL

  UNIQUE(scan_session_id, sequence)
  UNIQUE(scan_session_id, idempotency_key)
  UNIQUE(artifact_id)
```

API key, raw response header, raw image bytes는 DB에 넣지 않는다. `inventory_json`은 path/size/hash만
저장한 canonical snapshot이다.

## 9. Stable idempotency와 digest

V3-B는 Server package를 import하지 않고 V4 canonical algorithm을 독립 구현한다. 고정 test
vector로 양쪽 결과가 같음을 검증한다.

```text
upload_digest = sha256(canonical JSON of
  schema version
  scan_session_id, device_id, sequence
  artifact_id, spread_id, source_frame_id
  manifest_sha256
  sorted file path/size/sha256 inventory)

idempotency_key = "v3b-" + upload_digest
```

multipart boundary와 file 전송 순서가 바뀌어도 logical digest/key는 바뀌지 않는다. sequence를
새로 부여하거나 artifact를 재촬영해서 network retry를 해결하지 않는다.

## 10. Server V4 multipart client

권장 파일: `device-runtime/src/asl_device/adapters/http_v4.py`

필수 request:

```http
POST /api/v1/scan-sessions/{scan_session_id}/spreads
Content-Type: multipart/form-data; boundary=...
Content-Length: <정확한 전체 길이>
X-API-Key: <C0와 같은 secret>
Idempotency-Key: v3b-...
X-ASL-Upload-Digest: <digest>
Accept: application/json
```

part 순서:

1. `metadata`, `application/json`
2. `manifest`, filename `manifest.json`, `application/json`
3. manifest inventory의 각 `bundle_file`

구현 규칙:

- stdlib `http.client` 또는 동등한 streaming transport 사용
- raw multipart 전체를 메모리에 만들지 않음
- header/metadata/manifest byte 길이와 file size로 `Content-Length`를 사전 계산
- file을 bounded chunk로 읽어 socket에 전송
- chunked transfer와 compression 사용 금지
- HTTPS는 기본 certificate/hostname 검증 유지
- C0의 explicit local HTTP opt-in을 재사용
- response body는 작은 configured 상한까지만 읽음
- API key나 full local path를 exception/log/body에 노출하지 않음

## 11. HTTP 결과 mapping

| 결과 | durable row | public 결과 |
|---|---|---|
| valid 200/201 ACK identity match | `acked` | `DeliveryStatus.ACKED` |
| timeout, reset, DNS/connection | `retrying` | `DeliveryStatus.RETRYING` |
| body `retryable=true`, 408/429/5xx | `retrying` | `DeliveryStatus.RETRYING` |
| deterministic non-retryable V4 4xx | `rejected` | `DeliveryStatus.REJECTED` |
| 401/403 | artifact 보존, 오류 기록 | `FatalPortError` |
| non-JSON/oversized response | artifact 보존, 오류 기록 | `FatalPortError` |
| 2xx receipt identity mismatch | artifact 보존, 오류 기록 | `FatalPortError` |

`Retry-After`가 있으면 다음 poll 시도 하한으로 사용한다. 추가 retry는 단순 bounded
initial/max backoff만 사용하며 jitter·adaptive policy는 hardening으로 미룬다. process restart 뒤
미확정 row는 즉시 한 번 재시도 가능하다.

## 12. `DeliveryPort` method 계약

### 12.1 `queue(scan_session_id, sequence, artifact)`

- identity/manifest/path/inventory 검증
- stable digest/key 계산
- exact existing row면 현재 `DeliveryUpdate` 반환
- collision이면 `FatalPortError`
- 새 row를 `QUEUED`로 commit하고 반환
- network call 0

### 12.2 `pending_status(scan_session_id)`

- 현재 scan의 oldest nonterminal row 최대 1개를 advance
- retry due 전이면 network call 0
- 모든 row를 sequence 순 `DeliveryUpdate`로 반환
- terminal ACK/REJECT도 Coordinator가 재구성할 수 있도록 반환

### 12.3 `flush_through(scan_session_id, N)`

- `pending_status`와 같은 single-attempt advance를 수행 가능
- `1..N` 모두 ACKED: `FLUSHED`
- 하나라도 REJECTED: `BLOCKED`
- missing/queued/sending/retrying: `PENDING`
- Server seal API는 호출하지 않음; 기존 Coordinator가 flush 후 S0 seal을 소유

## 13. Process restart의 최소 복구

adapter/store 초기화 시:

```text
SENDING -> RETRYING
QUEUED/RETRYING -> 그대로 유지
ACKED/REJECTED -> terminal 유지
```

그 뒤 동일 SQLite와 artifact root로 `pending_status/flush_through`를 호출하면 같은 key/digest로
재전송한다.

대표적으로 검증할 restart 경계는 세 개만 둔다.

1. queue DB commit 뒤 첫 network call 전 restart
2. server가 commit했지만 client가 response를 잃은 뒤 restart
3. client가 2xx를 받았지만 local ACK DB commit 전 restart

세 경우 모두 final ACK receipt는 동일하고 Server S1 spread/page-fragment 중복은 0이어야 한다.
그 밖의 exhaustive power-loss/filesystem matrix는 이번 완료 조건이 아니다.

## 14. Config와 composition

C0의 `DeviceConnectivityConfig`가 가진 다음 값을 재사용한다.

- `device_id`
- `server_base_url`
- `api_key_file`
- `allow_insecure_http`
- connection/request timeout의 기존 보안 의미

V3-B local config는 필요한 값만 추가한다.

```text
outbox_db_path
artifact_root
upload_timeout_seconds
retry_initial_seconds
retry_max_seconds
response_limit_bytes
file_chunk_bytes
```

`outbox_db_path`와 `artifact_root`는 explicit absolute/resolved path로 구성한다. production
dependency 추가 없이 Python stdlib로 구현한다.

권장 composition:

```python
delivery = build_laptop_delivery(
    connectivity_config=connectivity_config,
    delivery_config=delivery_config,
    clock=clock,
)
coordinator = DeviceFlowCoordinator(..., delivery=delivery)
```

실제 camera/ScannerRuntime/STM/audio 전체 composition은 E0에서 연결한다.

## 15. 구현 단계

### Phase 0 — 계약 fixture와 문서

- Server V4 metadata/digest/receipt test vector 동결
- V3-B core와 hardening 비범위 명시
- 기존 `DeliveryPort` public signature 유지

### Phase 1 — Manifest/inventory domain

- Scanner V2 manifest reader와 path confinement
- identity/readiness/file inventory 검증
- metadata와 canonical upload digest/key 생성
- server package import 없는 고정 vector test

### Phase 2 — SQLite outbox

- schema v1 migration/reopen
- idempotent queue와 collision
- status/receipt/error commit
- startup `SENDING -> RETRYING`
- `pending_status/flush_through` pure evaluation

### Phase 3 — V4 streaming transport

- exact `Content-Length` multipart encoder
- bounded file streaming
- error/`Retry-After` classification
- strict success receipt validation

### Phase 4 — Concrete DeliveryPort와 cleanup

- poll-driven oldest-one advance
- retry scheduling
- ACK DB commit 뒤 confined artifact deletion
- Scanner/Coordinator `DeliveryUpdate` mapping

### Phase 5 — Loopback integration과 보고

- actual Scanner V2 bundle fixture
- actual Server V4 + SQLite/S1 loopback
- response-loss/restart exact retry
- 세 프로젝트 회귀
- 구현 보고서와 미검증 hardening 목록

## 16. 테스트 행렬

### 16.1 Manifest/digest

- valid V2 bundle metadata/inventory 생성
- manifest hash, identity, local readiness 불일치 거부
- missing/extra/duplicate/path escape file 거부
- file size/hash mutation 거부
- file order가 달라도 digest 동일
- server canonical fixture와 digest 일치

### 16.2 Outbox

- migration과 reopen idempotency
- exact queue replay row 1개
- same sequence/different artifact conflict
- same artifact/different sequence conflict
- DB commit 실패 시 queue 성공 반환 0
- status와 stable key/digest restart 보존
- startup SENDING→RETRYING
- terminal status 역전 0

### 16.3 DeliveryPort

- queue network call 0
- pending_status 한 호출당 upload 최대 1
- timeout/retryable response에서 artifact 보존
- deterministic reject에서 reason 보존
- invalid 2xx receipt에서 ACK 0, deletion 0
- valid ACK DB commit 뒤 delivery ACK와 cleanup
- ACK cleanup 실패가 false REJECT/ACK rollback을 만들지 않음
- flush는 모든 1..N ACK 전 `PENDING`
- reject 포함 flush는 `BLOCKED`

### 16.4 Actual loopback

- V3-B multipart → Server V4 → S1 receipt
- left/right page fragment 각 1개
- response loss 뒤 same-key resend와 receipt 동일
- adapter restart 뒤 retry와 fragment 중복 0
- ACK 뒤 Coordinator/Scanner callback 1회
- ACK 전 `SPREAD_SENT` feedback 0
- flush 뒤에만 seal intent 진행

### 16.5 Regression

- Device Runtime 전체 구현 후 기준 `59 passed`
- Book Scanner 전체 현재 기준 `288 passed`
- Document Parser 전체 현재 기준 `571 passed, 4 skipped`
- C0 health/presence와 S0/S1/V4 기존 회귀
- Scanner V2/V3-A.5 single in-flight·ACK identity 의미 변화 0

## 17. 완료 기준

- production-shaped `DeliveryPort`가 SQLite outbox와 V4 HTTP client를 사용한다.
- queue 성공 뒤 sequence/artifact/key/digest가 process restart를 넘어 유지된다.
- network uncertainty가 새 sequence나 새 capture를 만들지 않는다.
- valid receipt identity match 전 ACK와 artifact deletion이 각각 0이다.
- response loss/restart resend가 동일 receipt를 얻고 S1 fragment 중복이 0이다.
- `pending_status`와 `flush_through`가 durable row를 권위로 사용한다.
- deterministic reject는 reason과 artifact를 보존한다.
- ACK 뒤 cache cleanup이 수행된다.
- actual loopback과 세 프로젝트 회귀가 통과한다.
- hardening 비범위를 구현 완료로 주장하지 않는다.

## 18. 예상 변경 파일

주 대상:

- `device-runtime/src/asl_device/delivery_config.py`
- `device-runtime/src/asl_device/delivery_domain.py`
- `device-runtime/src/asl_device/delivery_store.py`
- `device-runtime/src/asl_device/delivery.py`
- `device-runtime/src/asl_device/adapters/http_v4.py`
- `device-runtime/src/asl_device/delivery_composition.py`
- `device-runtime/tests/unit/test_delivery_*.py`
- `device-runtime/tests/integration/test_v3b_v4_local_http.py`
- `device-runtime/docs/device-delivery-v3b.md`

필요할 때만 최소 변경:

- `device-runtime/src/asl_device/types.py`
- `device-runtime/src/asl_device/protocols.py`
- `device-runtime/src/asl_device/coordinator.py`
- `device-runtime/src/asl_device/__init__.py`
- `book-scanner`의 test fixture/문서
- `PROJECT_HANDOFF_20260831.md`

Server V4 source 변경은 기본 범위가 아니다. 실제 contract mismatch가 확인되면 자동 확장하지 않고
중단 조건으로 보고한다.

## 19. 승인 경계

승인 시 수행:

- V3-B domain/store/config/streaming client/concrete DeliveryPort 구현
- 기존 Coordinator contract의 필요한 최소 연결
- unit + actual local loopback integration test
- ACK 후 confined artifact cleanup
- 관련 문서, 구현 보고서와 handoff 갱신

별도 승인 없이는 수행하지 않음:

- 다중 writer/lease/quarantine/장기 GC
- Scanner 영상/identity threshold 또는 Paddle 모델 변경
- Server V4/S1 기능 확장
- 전체 Device app/E0 camera·STM·audio composition
- 외부 배포/TLS/Pi systemd
- 새 production dependency 설치
- commit/push/PR

## 20. 중단 조건

다음 상황에서는 범위를 조용히 넓히지 않고 보고한다.

- 실제 Scanner V2 manifest가 Server V4 wire 계약과 호환되지 않음
- 기존 immutable artifact를 pin하는 것으로 queue 이후 durability를 보장할 수 없음
- single poll-driven sender로 Coordinator의 flush 진행이 불가능함
- valid ACK 전에 Scanner가 artifact를 삭제해야만 현재 lifecycle이 동작함
- response loss retry에서 같은 key/digest/sequence를 보존할 수 없음
- whole Coordinator active-session persistence가 없으면 V3-B adapter 자체 restart도 검증할 수 없음
- Server V4 변경 또는 새로운 외부 dependency가 필수가 됨
- 기존 Scanner/Coordinator/S0/S1/C0/V4 회귀가 발생함

중단 시 핵심 기능 blocker와 후속 hardening 후보를 분리해 보고하며, hardening 구현으로 우회하지
않는다.
