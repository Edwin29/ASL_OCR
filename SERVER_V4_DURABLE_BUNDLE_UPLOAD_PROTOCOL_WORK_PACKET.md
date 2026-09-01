# Server V4 — Durable Bundle Upload Protocol 작업 패킷

상태: **승인됨 · 구현 및 로컬 회귀 검증 완료**
작성일: 2026-08-31
구현 결과: `SERVER_V4_IMPLEMENTATION_REPORT.md`
선행 조건: Integration V0 Coordinator, Scanner V2/V3-A.5 immutable artifact, Server S0/S1,
Device Connectivity C0
후속 조건: Scanner V3-B sender + LAPTOP durable outbox, LAPTOP Device Integration E0,
Raspberry Pi Port P0

## 1. 목표와 핵심 결정

Server V4는 LAPTOP Device Runtime이 만든 Scanner V2 bundle의 실제 bytes를 제품 HTTP 경계에서
수신하고, 서버 소유 저장소에 검증·원자 승격한 뒤 Server S1의 transport-neutral 접수 경계로
전달한다.

```text
Scanner immutable bundle
  -> [후속 V3-B] LAPTOP durable outbox
  -> bounded authenticated HTTP upload
  -> server-owned same-filesystem staging
  -> manifest/file hash·size·identity 검증
  -> file flush + atomic directory promotion
  -> S1 accept_verified_spread()
  -> S1 spread/fragment DB commit
  -> durable upload receipt response
```

핵심 결정은 다음과 같다.

1. V4 ACK는 HTTP body를 읽었다는 뜻이 아니다. **서버 소유 bundle 승격과 S1 receipt DB commit이
   모두 끝난 상태**를 뜻한다.
2. V4 ACK는 OCR/점역/TTS 또는 datapack revision 완료가 아니다. parser/finalize 상태는 기존 S1
   status 계약으로 별도 추적한다.
3. upload는 Scanner bundle 하나를 한 요청으로 보내는 bounded `multipart/form-data`다. V4에서는
   resumable chunk protocol을 만들지 않으며, 연결 손실 시 같은 immutable bundle 전체를 같은
   idempotency key로 안전하게 재전송한다.
4. client path는 서버 path로 사용하지 않는다. 서버가 생성한 staging/storage key만 S1에 전달한다.
5. multipart boundary가 달라져도 같은 요청으로 판정할 수 있도록 idempotency digest는 raw HTTP
   body가 아니라 canonical logical upload에서 계산한다.
6. manifest와 모든 listed file을 검증하며, 특히 left/right UVDoc의 hash·size·decode·dimension을
   S1이 다시 검증한다. V4 검증은 S1 검증을 제거하거나 약화하지 않는다.
7. request thread에서는 OCR, Page IR, 점역, TTS를 실행하지 않는다.
8. 인증은 C0/S0와 같은 endpoint 및 `X-API-Key`에서 시작한다. device별 credential/mTLS는 후속
   security 범위다.

## 2. 현재 구현과 V4 공백

### 2.1 이미 존재하는 기반

- Scanner V2 bundle schema `2.0`과 immutable `manifest.json`
- source frame과 left/right mask/crop/UVDoc/diagnostics의 size, SHA-256, image dimension 기록
- `local_readiness.ready=true`, `requires_both_pages=true` atomic spread 계약
- Coordinator의 monotonic client sequence, delivery/flush/seal lifecycle
- C0의 configured endpoint, authenticated ONLINE gate, retryable/fatal network 분류
- S0의 persistent scan session, device ownership, seal cutoff와 HTTP error schema
- S1의 server-owned bundle validator와 `accept_verified_spread(VerifiedSpreadInput)`
- S1의 `(scan_session_id, sequence)` 및 artifact collision, durable receipt, restart-safe parser queue
- S1의 `GET /api/v1/scan-sessions/{id}/spreads` receipt/status projection

### 2.2 아직 없는 것

- Scanner artifact bytes를 받는 production HTTP endpoint
- request body를 메모리에 전부 적재하지 않는 bounded multipart writer
- upload idempotency journal과 response-loss replay
- server-owned partial staging, atomic promotion과 crash recovery
- partial/orphan staging 정리 및 receive quota
- V4 response를 `DeliveryUpdate.ACKED/REJECTED/RETRYING`으로 해석할 wire 계약
- 실제 LAPTOP outbox/sender와 Coordinator `DeliveryPort` 구현

S1의 `LocalBundleIngestHarness`는 local fixture를 복사하는 테스트 경계다. 이를 public upload API로
노출하거나 device가 보낸 filesystem path를 받는 방식으로 확장하지 않는다.

## 3. 책임 경계

### 3.1 V4가 소유

- authenticated upload HTTP endpoint와 media type/version 확인
- scan/device/sequence/artifact/request identity 검증
- bounded streaming과 multipart part/path/count/byte 제한
- exact manifest bytes와 manifest SHA-256 검증
- manifest file inventory와 multipart file inventory의 정확한 일치
- 각 file의 streamed size/SHA-256 검증
- 서버 소유 staging과 same-filesystem atomic promotion
- upload request/attempt/response의 SQLite journal
- 동일 요청 replay와 다른 payload collision
- promotion/S1 handoff 사이 crash recovery
- S1 `accept_verified_spread()` 호출과 receipt 응답
- partial/orphan staging 정리 및 quota gate
- secret/path/image content를 노출하지 않는 structured diagnostics
- protocol fixture client와 HTTP/fault/restart tests

### 3.2 V4가 소유하지 않음

- LAPTOP durable outbox, artifact cache, retry scheduler와 ACK 후 eviction
- Coordinator production `DeliveryPort` composition
- Scanner candidate/identity/seam/crop/UVDoc 알고리즘
- accepted M1 bank의 process restart 복원
- Document Parser OCR/Page IR/점역/TTS semantics
- parser worker, fragment assembly, finalize 또는 revision publish
- parser 실패 sequence의 재촬영 UI, partial finalize
- C0 heartbeat/presence state와 network discovery
- audio byte streaming/device cache
- 외부 DNS, tunnel/VPN, TLS certificate, reverse proxy 배포
- Windows 자동 시작, Raspberry Pi systemd/camera/GPIO/audio/resource 검증
- device별 credential, mTLS, 역할 기반 authorization

V4는 protocol/server core를 고정한다. 실제 outbox에서 이 protocol을 호출하고 Coordinator
`DeliveryPort`를 완성하는 작업은 Scanner V3-B 패킷에서 별도 승인 후 수행한다.

## 4. HTTP V1 upload 계약

제품 경로는 기존 `/api/v1` namespace에 additive하게 추가한다.

```http
POST /api/v1/scan-sessions/{scan_session_id}/spreads
Content-Type: multipart/form-data; boundary=...
Content-Length: ...
X-API-Key: ...
Idempotency-Key: ...
X-ASL-Upload-Digest: <64 lowercase hex>
```

다음 header 규칙을 고정한다.

- `X-API-Key` 필수; 기존 S0/C0 secret-safe 비교와 error body를 재사용
- `Idempotency-Key`는 1~128자의 기존 safe ASCII ID 규칙을 만족
- `X-ASL-Upload-Digest`는 아래 canonical logical upload의 lowercase SHA-256
- `Content-Length` 필수; 음수, 중복 불일치, 설정 상한 초과는 body 처리 전에 거부
- `Transfer-Encoding: chunked`는 V4에서 지원하지 않음
- `Content-Encoding` 압축은 허용하지 않음
- cross-origin redirect로 credential 또는 body를 전달하지 않음
- 성공은 `201 Created` 또는 이미 S1에 존재하는 exact logical replay의 `200 OK`
- 비동기 `202 Accepted`는 사용하지 않음. V4 ACK 의미를 약화시키기 때문이다.

### 4.1 Multipart parts

정확히 다음 part만 허용한다.

```text
metadata     1개, application/json, filename 없음
manifest     1개, application/json, filename="manifest.json"
bundle_file  manifest.files의 각 path마다 정확히 1개
```

part 순서는 `metadata` 첫 번째, `manifest` 두 번째, 이후 `bundle_file`들로 고정한다. 이는 metadata와
manifest를 작은 상한 안에서 먼저 검증하고 upload claim/quota를 확보한 뒤 large file stream을 받기
위한 wire framing 규칙이다. `bundle_file` 사이의 순서는 권위가 아니다.

`bundle_file`의 `filename`은 manifest file record의 relative POSIX path다. 예:

```text
source_frame.jpg
left/mask.png
left/crop.jpg
left/uvdoc.jpg
left/diagnostics.json
right/mask.png
right/crop.jpg
right/uvdoc.jpg
right/diagnostics.json
```

규칙:

- metadata/manifest의 선행 순서를 어기면 large body를 쓰기 전에 protocol error로 거부한다.
- bundle file 순서와 multipart boundary는 content identity가 아니다. server는 path로 inventory를
  맞춘다.
- unknown part, duplicate metadata/manifest/path, 누락/추가 file을 거부한다.
- `filename`과 part media type은 identity나 신뢰 근거가 아니다.
- backslash, absolute path, drive prefix, 빈 segment, `.`/`..`, NUL/control character를 거부한다.
- 초기 schema의 path는 ASCII `[A-Za-z0-9._/-]` 범위와 255-byte 상한을 사용한다.
- client path에서 directory를 만들기 전에 전체 path를 검증하고 server staging root confinement를
  확인한다.
- multipart filename을 OS basename helper로 조용히 변환하지 않는다. 변형은 manifest hash와
  inventory 계약을 깨뜨리므로 명시 reject한다.

### 4.2 Metadata schema v1

```json
{
  "schema_version": 1,
  "device_id": "asl-device-prototype-01",
  "sequence": 1,
  "artifact_id": "artifact-...",
  "spread_id": "spread-...",
  "source_frame_id": "frame-...",
  "manifest_sha256": "64-lowercase-hex",
  "file_count": 9,
  "total_file_bytes": 12345678
}
```

- `scan_session_id`는 URL path가 권위이며 metadata에 중복하지 않는다.
- `device_id`는 scan session owner와 정확히 같아야 한다.
- `sequence`는 양의 정수이고 S1의 logical position으로 그대로 전달한다.
- artifact/spread/source ID는 기존 safe ASCII 규칙을 만족하고 manifest와 정확히 일치해야 한다.
- `manifest_sha256`은 multipart manifest의 exact bytes SHA-256이다.
- `file_count`와 `total_file_bytes`는 manifest의 unique file records 합계와 일치해야 한다.
- unknown field는 schema 진화를 명시적으로 승인하기 전 거부한다.
- client timestamp, local path, API key, presence session 또는 arbitrary metadata를 받지 않는다.

### 4.3 Canonical upload digest

`X-ASL-Upload-Digest`는 multipart raw bytes의 hash가 아니다. 다음 object를 구성한 뒤 Python/JSON
호환 canonical form으로 직렬화해 SHA-256을 계산한다.

```text
UTF-8 bytes of json.dumps(
  {
    "schema_version": 1,
    "scan_session_id": ...,
    "device_id": ...,
    "sequence": ...,
    "artifact_id": ...,
    "spread_id": ...,
    "source_frame_id": ...,
    "manifest_sha256": ...,
    "files": [
      {"path": ..., "size_bytes": ..., "sha256": ...}, ...
    ]
  },
  ensure_ascii=True,
  sort_keys=True,
  separators=(",", ":"),
)
```

`files`는 normalized relative path 오름차순으로 정렬한다. 모든 ID/path가 safe ASCII이므로 Unicode
normalization 차이를 허용하지 않는다. server는 manifest를 읽은 뒤 digest를 재계산한다.

이 digest는 다음을 보장한다.

- multipart boundary/part order가 달라도 logical replay는 같은 digest
- sequence/artifact/manifest/file inventory 중 하나라도 바뀌면 다른 digest
- 실제 file bytes는 각 record SHA-256 검증으로 digest 선언과 연결
- raw body 전체를 메모리에 올려 hash할 필요가 없음

## 5. Scanner manifest와 bundle 검증

V4 writer는 저장 전 최소 다음을 확인한다.

- manifest exact bytes가 UTF-8 JSON object이며 4 MiB 이하
- `schema_version == "2.0"`
- manifest artifact/session/spread/source identity가 URL/metadata와 일치
- `session_id == scan_session_id`
- `local_readiness.ready == true`
- `local_readiness.requires_both_pages == true`
- `pages` key가 정확히 `left`, `right`
- `files`가 non-empty list이고 path가 unique
- `file_count`, `total_file_bytes`, upload digest가 manifest와 일치
- manifest의 left/right page가 해당 side와 source frame을 보존
- left/right `files.uvdoc` record가 top-level `files` record와 hash/size/dimension 기준으로 일치
- multipart inventory가 manifest inventory와 정확히 일치
- stream 중 실제 byte count와 SHA-256이 각 record와 일치

V4는 archive를 풀지 않는다. multipart bytes에서 검증된 regular file만 새 staging directory에 직접
쓴다. 따라서 zip/tar traversal, symlink, hard-link, device file을 허용하지 않는다.

atomic promotion 뒤 S1의 기존 `ScannerBundleValidator`가 다음을 다시 검증한다.

- receive root confinement, symlink/reparse traversal 부재
- 실제 directory inventory와 manifest inventory 일치
- 모든 file size/hash 재검증
- UVDoc decode, width/height와 dimension limit
- 양면 readiness/source/identity
- S1 configured file/byte/image 상한

V4와 S1의 중복 hash 검증은 의도적 defense-in-depth다. V4가 S1 validator 내부 구현을 복사해
별도 권위로 만들기보다 공통 pure validation helper를 추출해 재사용할 수는 있지만, S1 public
accept 경계의 재검증은 유지한다.

## 6. Streaming과 resource limit

현재 S1 `S1Config`의 기본 상한을 단일 권위로 재사용한다.

```text
max_manifest_bytes:          4 MiB
max_bundle_files:            32
max_bundle_bytes:            128 MiB
max_image_dimension:         16,384
max_multipart_overhead:      1 MiB
max_request_bytes:           max_manifest + max_bundle + max_multipart_overhead
max_part_header_bytes:       8 KiB
max_relative_path_bytes:     255
```

상한은 config로 분리하되 endpoint와 S1 validator가 서로 다른 값을 조용히 사용하지 않는다.

구현 규칙:

- `request.get_data()` 또는 raw body 전체 read 금지
- Flask/Werkzeug global `MAX_CONTENT_LENGTH` 또는 동등한 WSGI pre-limit 설정
- file part는 bounded chunk로 server staging file에 직접 copy하며 incremental SHA-256 계산
- metadata와 manifest만 각자의 작은 상한 안에서 memory parse 가능
- declared size를 넘는 순간 해당 part/request를 중단
- actual request가 `Content-Length`보다 짧으면 incomplete, 길면 protocol error
- 한 upload request당 writer 하나; request 내부 file parallel write 금지
- request thread는 filesystem/hash 작업과 S1 durable accept까지만 수행
- OCR/TTS worker queue를 기다리지 않음

Werkzeug multipart parser가 file part를 제어되지 않은 임시 위치에 body 전체로 먼저 spool하거나,
application handler 이전에 설정 상한을 우회하는 구조라면 이를 그대로 사용하지 않는다. bounded
stream factory/WSGI wrapper를 구성하거나 구현을 중단하고 계약 변경 승인을 요청한다.

## 7. Idempotency와 collision 계약

idempotency scope는 `(scan_session_id, Idempotency-Key)`다.

- same key + same upload digest + terminal response: 저장된 HTTP status/body를 그대로 반환, mutation 0
- same key + different upload digest: `409 IDEMPOTENCY_KEY_REUSED`
- same key + same digest + active lease: `409 UPLOAD_IN_PROGRESS`, `retryable=true`, `Retry-After`
- same key + same digest + expired/incomplete attempt: partial staging을 정리한 뒤 같은 logical attempt를
  전체 body부터 재개
- different key + same accepted sequence/artifact/manifest: 기존 S1 row의 spread/source identity까지
  모두 대조한 뒤 기존 receipt를 반환
- same sequence + different artifact/manifest digest: `409 SPREAD_SEQUENCE_COLLISION`
- same artifact를 다른 session/sequence에 사용: `409 ARTIFACT_ID_COLLISION`
- same sequence에 V4 terminal reject만 있고 S1 accepted row가 없으면 새 idempotency key와 새 immutable
  artifact로 같은 logical sequence를 재시도할 수 있음

`Idempotency-Key`만으로 content identity를 추정하지 않는다. `artifact_id`만으로도 동일 bytes를
추정하지 않는다. canonical upload digest와 실제 file hash 검증을 함께 사용한다.

현재 S1 exact replay는 기존 `bundle_relative_path`도 비교한다. 따라서 이미 S1에 accepted된 logical
position의 exact replay를 새 storage key로 다시 `accept_verified_spread()`에 전달하지 않는다. V4가
기존 S1 row의 sequence/artifact/spread/source/manifest를 조회해 모두 같으면 기존 durable receipt를
`200 OK`로 반환하고, 하나라도 다르면 기존 S1 collision을 반환한다. 이 조정 경로는 새 received
directory나 fragment를 만들지 않는다.

동시 요청은 SQLite transaction/unique constraint와 upload lease가 직렬화한다. process-local lock만으로
same key/sequence race를 막지 않는다.

## 8. Server-owned storage와 ACK 순서

권장 layout:

```text
datapacks/
  _server/
    upload-staging/{server_upload_id}.partial/
    received/v4/{server_upload_id}/
    upload-quarantine/{server_upload_id}/
```

`server_upload_id`와 storage key는 server-generated opaque ID다. scan/artifact/device ID를 그대로
directory name으로 사용하지 않는다. staging과 received는 같은 filesystem이어야 한다.

성공 순서는 다음으로 고정한다.

1. auth, content type/length, header ID/digest 형식 preflight
2. 첫 metadata와 두 번째 manifest part를 각각 bounded parse
3. identity/inventory/limit/canonical upload digest 검증
4. SQLite에서 idempotency key와 기존 S1 logical position 조정
5. exact terminal replay면 저장 response, exact S1 replay면 기존 receipt 반환; large file write 0
6. 신규 upload이면 SQLite upload attempt claim/lease와 quota reservation
7. server-generated empty staging directory 생성
8. 각 file을 chunk 단위로 write하면서 actual size/SHA-256 검증
9. staging의 exact inventory와 manifest 재검증
10. 모든 file flush + `os.fsync`; 가능한 platform에서는 directory fsync
11. received final path가 비어 있음을 확인
12. 같은 filesystem에서 staging directory를 final received path로 atomic promotion
13. upload journal을 `promoted`와 internal storage key로 기록
14. S1 `accept_verified_spread()` 호출
15. S1이 bundle을 재검증하고 `scan_spreads/page_fragments` transaction commit
16. V4 journal에 S1 receipt와 외부 response를 commit
17. HTTP success response 반환

S1 입력:

```python
VerifiedSpreadInput(
    scan_session_id=scan_session_id,
    sequence=metadata.sequence,
    artifact_id=metadata.artifact_id,
    spread_id=metadata.spread_id,
    source_frame_id=metadata.source_frame_id,
    bundle_storage_key=server_generated_relative_key,
    manifest_sha256=metadata.manifest_sha256,
)
```

금지:

- S1 receipt commit 전 `ACKED`, 저장 완료음 또는 success body 노출
- client의 local path/staging path를 `bundle_storage_key`로 전달
- final received directory를 replay 중 덮어쓰기
- cross-filesystem copy를 atomic promotion으로 표시
- hash mismatch를 재인코딩/파일명 수정으로 보정
- UVDoc 실패를 crop/source image로 silent fallback

file fsync와 same-filesystem promotion은 process/restart durability의 필수 조건이다. directory fsync가
지원되지 않는 Windows 개발 환경에서는 그 제한을 구현 보고서에 명시하고 process crash/restart를
검증한다. 이를 갑작스러운 전원 차단 durability까지 검증한 것으로 기록하지 않는다.

## 9. ACK와 response 계약

최초 성공 예시:

```json
{
  "status": "acked",
  "receipt_id": "receipt-...",
  "scan_session_id": "scan-...",
  "sequence": 1,
  "artifact_id": "artifact-...",
  "manifest_sha256": "...",
  "upload_digest": "...",
  "spread_status": "received",
  "accepted_at": "server UTC timestamp"
}
```

- 최초 V4/S1 accept는 `201 Created`
- 다른 idempotency key로 온 exact S1 logical replay는 `200 OK`
- 같은 idempotency key replay는 저장된 status/body를 그대로 반환하고
  `Idempotency-Replayed: true` header만 추가 가능
- response에 filesystem path, storage key, API key, raw manifest 또는 image metadata 전체를 노출하지
  않음

이 응답을 받은 client만 `DeliveryStatus.ACKED`와 `receipt_id`를 Coordinator/Scanner에 전달한다.
ACK 이후 Scanner M1 pending identity bank가 accepted로 승격될 수 있다.

`spread_status="received"`는 parser 완료가 아니다. 이후 상태는 기존
`GET /api/v1/scan-sessions/{scan_session_id}/spreads`와 scan finalization API가 권위다. parser
REJECTED/ERROR는 upload ACK를 없던 것으로 만들지 않고 finalize를 차단한다.

## 10. SQLite migration v4

기존 S0/S1/C0 database schema v3를 additive migration으로 확장한다. DB를 삭제·재생성하지 않는다.

### 10.1 `spread_upload_attempts`

```text
upload_id PK
scan_session_id FK
device_id FK
sequence > 0
idempotency_key
request_sha256                 # canonical upload digest
artifact_id
spread_id
source_frame_id
manifest_sha256
declared_file_count
declared_total_bytes
received_file_count
received_total_bytes
status: receiving | abandoned | promoted | accepted | rejected
attempt_count
lease_owner NULL
lease_until NULL
staging_relative_path NULL
bundle_relative_path NULL
s1_receipt_id NULL
response_http_status NULL
response_json NULL
created_at, updated_at, completed_at NULL
error_code NULL, error_detail NULL
UNIQUE(scan_session_id, idempotency_key)
```

필요 index/constraint:

```text
(status, lease_until)
(scan_session_id, sequence, status)
(artifact_id, status)
partial UNIQUE(scan_session_id, sequence)
  WHERE status IN ('receiving', 'promoted')
partial UNIQUE(artifact_id)
  WHERE status IN ('receiving', 'promoted')
```

accepted logical position/artifact의 최종 권위는 기존 S1 `scan_spreads` constraints다. V4 partial unique
index는 동시에 진행되는 writer만 막는다. rejected/abandoned attempt history 때문에 새 corrected
artifact가 같은 sequence를 영구적으로 점유하지 않게 한다.

`response_json`은 bounded server-generated error/success body만 저장한다. raw request header, API key,
manifest, image bytes와 client local path를 DB에 저장하지 않는다.

### 10.2 상태 전이

```text
new -> receiving
receiving -> promoted -> accepted
receiving -> rejected
receiving -> abandoned -> receiving     # same key/digest full retry
promoted -> accepted
promoted -> rejected                    # deterministic S1 validation/state reject
```

- `accepted`와 terminal `rejected`는 같은 key/digest replay response의 권위
- `promoted`는 startup/request recovery가 S1 handoff를 재실행
- `receiving` lease expiry는 ACK가 아니며 partial directory를 정리한 뒤 full retry
- unknown state나 future schema는 fail-fast; 자동 DB rebuild 금지

## 11. 실패·retry·HTTP error 계약

기존 error body를 유지한다.

```json
{
  "code": "...",
  "message": "...",
  "retryable": true,
  "details": {}
}
```

대표 mapping:

| HTTP | code 예 | retryable | 의미 |
|---:|---|---|---|
| 400 | `UPLOAD_METADATA_INVALID`, `BUNDLE_PATH_INVALID` | false | 구조/ID/path 오류 |
| 401 | `UNAUTHORIZED` | false | API key 오류 |
| 404 | `SCAN_SESSION_NOT_FOUND` | false | unknown scan |
| 409 | `IDEMPOTENCY_KEY_REUSED` | false | same key, different digest |
| 409 | `SPREAD_SEQUENCE_COLLISION`, `ARTIFACT_ID_COLLISION` | false | logical identity 충돌 |
| 409 | `SCAN_NOT_ACCEPTING_SPREADS` | false | cutoff/state 위반 |
| 409 | `UPLOAD_IN_PROGRESS` | true | 같은 attempt의 active lease |
| 411 | `CONTENT_LENGTH_REQUIRED` | false | bounded upload 불가 |
| 413 | `UPLOAD_REQUEST_LIMIT`, `BUNDLE_BYTE_LIMIT` | false | configured per-request limit 초과 |
| 415 | `UPLOAD_MEDIA_TYPE_UNSUPPORTED` | false | multipart/version/encoding 미지원 |
| 422 | `BUNDLE_HASH_MISMATCH`, `BUNDLE_INVENTORY_MISMATCH` | false | 완전 수신됐지만 content invalid |
| 429 | `UPLOAD_CAPACITY_BUSY` | true | 동시 writer/backpressure limit |
| 503 | `UPLOAD_STORAGE_TEMPORARY`, `DATABASE_BUSY` | true | 일시 I/O/DB 장애 |
| 507 | `UPLOAD_STORAGE_QUOTA` | true | 안전한 staging/receive 공간 부족 |

세부 규칙:

- timeout, connection reset, DNS failure, response 없음: client는 ACK/REJECT로 추정하지 않고 같은
  key/digest/bundle을 RETRYING
- `retryable=true`: 같은 immutable artifact와 sequence를 유지하고 backoff 후 retry
- deterministic 4xx `retryable=false`: `DeliveryStatus.REJECTED` 후보. V3-B가 structured reason을
  보존하고 Coordinator recovery 정책에 전달
- 5xx라고 새 sequence/frame을 만들지 않음
- 응답 body를 parse할 수 없거나 receipt identity가 요청과 다르면 ACK 금지
- HTTP success라도 receipt의 scan/sequence/artifact/manifest가 local outbox와 모두 같아야 ACK
- `Retry-After`가 있으면 V3-B retry scheduler가 최소 대기값으로 사용

server가 S1 commit 뒤 response write에서 실패한 경우 client는 응답 없음으로 처리한다. 재전송 시
S1/V4 journal replay가 같은 receipt를 반환하므로 page/fragment를 중복 생성하지 않는다.

## 12. Crash recovery와 orphan cleanup

startup 및 bounded maintenance pass에서 다음을 수행한다.

### 12.1 `receiving`

- lease가 유효하면 다른 worker가 건드리지 않음
- lease 만료 + partial directory 존재: journal identity를 확인하고 partial만 삭제, `abandoned`
- lease 만료 + directory 없음: `abandoned`
- 같은 key/digest retry는 새 empty partial directory에서 전체 body 재수신
- 부분 file offset resume는 V4에서 지원하지 않음

### 12.2 `promoted`

- final directory/hash/inventory가 journal과 일치하면 S1 accept를 idempotently 재실행
- S1에 이미 receipt가 있으면 같은 receipt로 V4 `accepted` commit
- final directory가 없거나 다른 content면 `UPLOAD_PROMOTION_LOST/COLLISION`; 자동 재생성·덮어쓰기 금지
- promoted bundle은 orphan TTL로 삭제하지 않음

### 12.3 `accepted`

- S1 `scan_spreads` receipt와 identity가 일치해야 함
- accepted bundle의 lifetime/cleanup 권한은 S1 processing/finalization 정책으로 넘어감
- V4 quota 확보를 위해 미처리 accepted bundle을 임의 삭제하지 않음

### 12.4 `rejected`와 filesystem orphan

- deterministic reject response는 journal에 남겨 exact retry에 재사용
- 진단 보존이 필요한 promoted reject는 quarantine으로 이동 가능하되 response path에는 노출하지 않음
- DB row가 없는 `.partial`만 configurable TTL 이후 삭제 가능
- DB row가 없는 final received directory는 자동 삭제하지 않고 quarantine/diagnostic으로 격리
- cleanup은 root confinement와 server-generated path를 다시 확인하며 symlink/reparse point를 따라가지
  않음

## 13. Quota와 backpressure

다음 값을 config로 둔다.

```text
max_concurrent_upload_writers
max_staging_bytes
max_received_bytes
partial_orphan_ttl_seconds
rejected_quarantine_ttl_seconds
upload_lease_seconds
```

정확한 global byte 기본값은 실제 bundle 크기/scan 길이와 disk 용량을 계측해 확정한다. 구현 시
무제한을 safe default로 사용하지 않고 테스트 profile과 LAPTOP profile에 명시적 값이 있어야 한다.

quota 계산 규칙:

- 새 claim 전에 현재 staging + reserved declared bytes를 transaction에서 검사
- concurrent request가 같은 여유 공간을 중복 예약하지 못하게 함
- active/promoted/accepted unprocessed bytes를 eviction 대상으로 사용하지 않음
- 공간 부족은 partial success나 oldest accepted 삭제가 아니라 retryable `507`
- repeated quota failure가 Scanner 새 capture를 계속 허용하는 문제는 V3-B outbox capacity와
  Coordinator freeze 정책에서 함께 닫음

## 14. Security와 privacy 경계

- 기존 `X-API-Key`를 URL/query/form field에 넣지 않음
- request/response/log/DB에 API key와 authorization header를 기록하지 않음
- HTTPS hostname/certificate 검증 기본; insecure HTTP는 C0의 explicit development opt-in만 허용
- shared API key 환경에서도 metadata device ID와 scan owner 일치 확인
- presence heartbeat 성공을 upload authorization/ACK로 대신하지 않음
- multipart filename은 untrusted data이며 path validation 전 filesystem 사용 금지
- archive extraction, symlink, hard-link, reparse traversal 없음
- content type/extension만으로 image를 신뢰하지 않음; S1이 실제 UVDoc decode
- error details에 server absolute path, DB path, host/user name 또는 raw manifest를 포함하지 않음
- raw page image/diagnostics/token text를 일반 application log에 출력하지 않음
- file/digest/ID length와 multipart header/boundary 상한을 둠
- malformed multipart/parser exception을 generic 500 stack trace로 client에 반사하지 않음

이 계약은 prototype shared credential 수준이다. 외부 인터넷 production security, device별 revoke,
mTLS, rate-limit identity 강화는 별도 패킷 없이 완료로 표시하지 않는다.

## 15. Observability와 운영 진단

structured event/metric 최소 항목:

- upload ID, scan ID, sequence, artifact ID
- upload digest/manifest digest의 짧은 표시 또는 전체 safe digest
- attempt count, replay/collision/recovery 여부
- declared/received file count와 bytes
- receive/hash/fsync/promotion/S1 handoff/total duration
- current staging/received reserved bytes와 quota rejection count
- terminal HTTP status/error code/retryable
- S1 receipt ID와 spread initial status

금지 항목:

- API key/header dump
- client/server absolute path
- image bytes, OCR text, raw footer token
- full arbitrary manifest/diagnostics dump

request마다 progress log를 과도하게 남기지 않는다. large file chunk마다 log하지 않고 stage transition과
terminal result만 기록한다.

## 16. Protocol/client mapping

V4 구현에는 production durable outbox를 포함하지 않는다. 다만 wire contract를 실제로 검증하기 위한
stateless protocol fixture client 또는 test helper를 제공한다.

후속 V3-B는 다음 mapping을 사용한다.

```text
local outbox NEW/QUEUED      -> DeliveryStatus.QUEUED
HTTP body in flight          -> DeliveryStatus.SENDING
network/retryable response   -> DeliveryStatus.RETRYING
valid V4 ACK receipt         -> DeliveryStatus.ACKED
terminal structured reject   -> DeliveryStatus.REJECTED
```

`flush_through(N)`은 local outbox에서 `1..N` 모두 valid V4 ACK receipt를 가질 때만 `FLUSHED`다.
presence ONLINE, HTTP socket write 완료, V4 staging 완료, S1 parser READY 중 어느 것도 이 조건을
대체하지 않는다.

기존 spread 조회 API는 reconciliation에 사용할 수 있다.

```http
GET /api/v1/scan-sessions/{scan_session_id}/spreads
```

client는 sequence뿐 아니라 artifact ID, manifest SHA와 receipt ID를 모두 대조해야 한다. 조회 결과가
없으면 ACK로 추정하지 않고 같은 upload를 재시도한다.

## 17. 구현 단계

### Phase 0 — 계약 고정

- metadata schema, canonical upload digest와 multipart inventory 고정
- ACK/error/retry/idempotency 의미 문서화
- S1 boundary와 V3-B boundary 명시

### Phase 1 — Migration·pure domain

- SQLite migration v4와 upload attempt repository
- ID/digest/status/lease/response value type
- idempotency replay, active sequence/artifact collision tests

### Phase 2 — Bounded multipart writer

- request preflight와 bounded stream factory
- metadata/manifest parser와 path/inventory validation
- chunk file writer, size/hash 검증과 resource limits
- test fixture bundle upload client

### Phase 3 — Storage promotion·recovery

- same-filesystem staging/received configuration validation
- flush/fsync/atomic directory promotion
- promotion collision과 crash journal
- receiving/promoted startup recovery

### Phase 4 — S1 handoff·HTTP response

- 기존 S1 logical position의 identity/receipt 조정 조회
- promoted bundle에서 `VerifiedSpreadInput` 생성
- S1 exact receipt/collision/error mapping
- V4 response journal commit 뒤 success 반환
- existing `/api/v1` app/combined server wiring

### Phase 5 — Cleanup·quota·fault tests

- partial lease expiry와 orphan cleanup
- staging/reserved byte quota와 concurrent writer backpressure
- response-loss, process restart와 promotion/S1 boundary fault injection

### Phase 6 — 회귀·문서·보고

- S0/S1/C0/legacy HTTP/Document Parser 전체 회귀
- Device Runtime Coordinator와 Book Scanner 전체 회귀
- V4 API/schema 문서와 구현 보고서
- LAPTOP loopback actual HTTP upload/replay test
- 실행하지 않은 외부 network/Pi/outbox 항목 명시

## 18. 테스트 행렬

### 18.1 Metadata·multipart

- valid real Scanner V2 schema `2.0` bundle acceptance
- bundle file order/multipart boundary가 달라도 같은 canonical digest
- metadata/manifest 선행 순서 위반 거부
- missing/duplicate/unknown metadata, manifest, file part
- invalid JSON/schema/unknown field/ID/SHA/sequence
- absolute, drive, backslash, `.`/`..`, control, overlong path
- duplicate normalized path와 manifest/multipart inventory mismatch
- manifest exact bytes hash mismatch
- left/right/source/session/artifact identity mismatch
- local readiness false 또는 requires-both false

### 18.2 Streaming·limit

- `request.get_data()` 없이 file chunk write
- absent/invalid/oversized Content-Length
- chunked/content-encoding/unsupported media type 거부
- manifest 4 MiB, file count, total bytes, per-part declared/actual mismatch
- lying Content-Length의 short body/overflow
- bounded memory behavior와 controlled staging 위치
- client disconnect mid-file에서 receipt/ACK 0
- request thread OCR/TTS/parser worker wait 0

### 18.3 Idempotency·concurrency

- same key/same digest terminal response exact replay, mutation 0
- same key/different digest 409
- different key/same accepted logical upload는 새 storage/fragment 없이 same S1 receipt
- same sequence/different digest, artifact reuse collision
- simultaneous same key와 same sequence writer 1
- active lease retryable response, expired lease full retry
- terminal rejected attempt 뒤 new key/new artifact same sequence 가능

### 18.4 Storage·S1 handoff

- staging/final same filesystem startup validation
- file hash/size/inventory 검증 뒤에만 promotion
- final destination existing same/different journal behavior
- S1에 client path 전달 0, server key만 전달
- S1 validator가 promoted bundle 전체 재검증
- S1 receipt commit 전 HTTP success 0
- ACK 뒤 fragment rows 정확히 left/right 1개씩
- parser completion을 기다리지 않고 `spread_status=received`

### 18.5 Crash/fault recovery

- metadata 전, mid-file, file flush 전 crash
- file fsync 후 promotion 전 crash
- promotion 후 journal 전/후 crash
- promotion 후 S1 call 전 crash
- S1 commit 후 V4 response journal 전 crash
- response journal commit 후 socket response loss
- 모든 replay에서 S1 spread/page row 중복 0, receipt 동일
- promoted bundle missing/different hash는 overwrite 없이 명시 오류

### 18.6 Cleanup·quota

- expired partial만 confined delete
- valid lease, promoted, accepted bundle 자동 삭제 0
- DB 없는 partial TTL cleanup
- DB 없는 final received quarantine, silent delete 0
- reserved byte race에서 quota 초과 writer 0
- quota/worker capacity retryable error와 `Retry-After`
- cleanup path traversal/symlink follow 0

### 18.7 HTTP·integration·regression

- auth와 secret/log/path non-disclosure
- 200/201 ACK 및 4xx/5xx error schema
- actual loopback response-loss 재전송
- OPEN 및 SEALING cutoff 이하 missing/exact replay 허용
- cutoff 초과/SEALED/ERROR 신규 upload 거부
- existing spread listing reconciliation
- S0 catalog/scan/reading, S1 parser/finalize, C0 presence 회귀
- legacy `/jobs`, `/sessions`, `/datapacks` 회귀
- Device Runtime/Book Scanner 전체 회귀
- V4 테스트에서 production durable outbox/Scanner algorithm mutation 0

## 19. 완료 기준

- 실제 Scanner V2 bundle bytes를 bounded HTTP로 서버에 전송 가능
- server가 client path를 사용하지 않고 same-filesystem staging에 직접 저장
- manifest/inventory/all-file size·SHA와 left/right UVDoc 계약 검증
- exact replay는 같은 receipt, 다른 digest/key/sequence 충돌은 명시적
- mid-upload/response-loss/process restart에서 false ACK와 duplicate fragment 0
- atomic promotion과 S1 DB receipt commit 뒤에만 success response
- ACK가 parser/finalize 완료와 명확히 분리
- partial/orphan cleanup이 promoted/accepted bundle을 삭제하지 않음
- quota/backpressure가 silent eviction이나 partial success를 만들지 않음
- 기존 S0/S1/C0/Coordinator/Scanner/legacy 회귀 통과
- API/schema와 구현 보고서에 실제 검증/미검증 범위 기록
- V3-B outbox, 외부 network/TLS deployment, Pi target을 V4 완료로 표시하지 않음

Windows에서 directory fsync/power-loss semantics를 완전히 검증하지 못했다면 process restart durability와
전원 차단 durability를 분리해 보고한다.

## 20. 명시적 후속 범위

### Scanner V3-B

- LAPTOP filesystem/SQLite durable outbox
- artifact/sequence/idempotency key의 process restart 보존
- V4 multipart sender, backoff/jitter와 receipt reconciliation
- ACK 후 cache eviction, rejected artifact 보존과 quota/freeze
- accepted M1 identity metadata persistence 범위 결정

### LAPTOP Device Integration E0

- C0 + Coordinator + Scanner + V3-B/V4 실제 composition
- camera/STM serial/feedback renderer와 저장/오류 음 구분
- server/process/OS restart, network disconnect full E2E
- Windows 자동 시작과 local persistent directory 운영

### Raspberry Pi Port P0

- 동일 outbox/V4 protocol 이식
- systemd/network-online과 Linux storage fsync/power-loss
- camera/GPIO/serial/audio 및 CPU/RSS/thermal/latency 검증

### 별도 server/security 운영

- resumable chunk/range upload가 실제 필요하다는 계측 후 protocol 확장
- external TLS endpoint, VPN/tunnel, reverse proxy limit 정합화
- device별 credential/mTLS/rate limit
- accepted/rejected bundle 장기 retention과 관리자 garbage collection

## 21. 승인 시 변경 범위

승인 시 다음을 구현한다.

- `document-parser.server` V4 upload domain/repository/migration/service/storage writer
- `/api/v1/scan-sessions/{id}/spreads` POST upload route의 additive 추가
- shared bundle validation helper가 필요한 경우 S1 validator의 behavior-preserving refactor
- combined server V4 configuration/wiring
- bounded multipart protocol fixture client/test helper
- migration/idempotency/stream/limit/hash/promotion/recovery/quota HTTP tests
- S0/S1/C0/legacy/Document Parser/device-runtime/book-scanner 회귀
- V4 API 문서와 구현 보고서

다음은 별도 승인 없이 구현하지 않는다.

- production Scanner V3-B durable outbox/DeliveryPort sender
- Scanner candidate/identity/crop/UVDoc 또는 Document Parser content algorithm 변경
- partial finalize/targeted replacement UI
- resumable chunk upload
- 실제 external endpoint/TLS/VPN 배포
- Windows 자동 시작 또는 Raspberry Pi systemd/hardware 이식
- dependency/model 자동 download
- commit, push, PR, release

## 22. 중단 조건

다음이 확인되면 silent workaround 없이 구현을 중단하고 보고한다.

- success response를 S1 receipt DB commit 전에 보내야만 기존 Coordinator가 동작함
- S1이 server-owned storage key 대신 client filesystem path를 요구함
- current Scanner manifest를 수정/재직렬화해야만 upload 가능해 exact hash를 보존할 수 없음
- multipart parser가 상한 적용 전 body 전체를 memory/제어되지 않은 temp에 적재하며 bounded stream
  경계로 교체할 수 없음
- staging과 received가 다른 filesystem이라 atomic promotion이 불가능함
- same idempotency key로 다른 payload를 허용해야만 retry가 동작함
- response-loss replay에서 S1 spread/fragment 중복 생성을 막을 수 없음
- quota 확보를 위해 promoted/accepted bundle을 receipt/finalize 전에 삭제해야 함
- V4 endpoint에서 OCR/TTS 완료를 기다려야만 ACK를 만들 수 있음
- V4를 구현하려면 Scanner/Document Parser 의미론 또는 S0/S1 current revision 계약을 변경해야 함
- 기존 legacy/S0/S1/C0 회귀를 보존할 수 없음

중단 시 bounded receive, promotion, S1 handoff, replay/recovery 중 실제 검증된 단계까지만 완료로
기록하고 나머지를 같은 성공 상태로 묶지 않는다.
