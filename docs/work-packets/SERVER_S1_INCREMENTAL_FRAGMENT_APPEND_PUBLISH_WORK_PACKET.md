# Server S1 — Incremental Fragment · Append Assembly · Atomic Revision Publish 작업 패킷

상태: **승인됨 · 구현 및 회귀 검증 완료**  
작성일: 2026-08-31  
선행 조건: Server S0 persistent control plane, Integration V0 Coordinator, Scanner V3-A.5 artifact contract  
후속 조건: LAPTOP Device Connectivity C0, Scanner V3-B + Server V4 HTTP artifact
ingest/durable outbox, LAPTOP Device Integration, Raspberry Pi Port/Target Validation

## 1. 목표와 핵심 결정

Server S1은 Scanner가 만든 spread를 Document Parser 입력으로 처리하고, 그 결과를 신규 또는 기존
datapack에 순서대로 결합한 뒤 새 immutable revision을 원자적으로 발행한다.

S1의 완료 경로는 다음과 같다.

```text
server-owned verified spread
  -> durable spread/page rows
  -> left/right parser fragments
  -> seal cutoff terminal 확인
  -> base revision + ordered new pages 조립
  -> document/audio/manifest 전체 검증
  -> immutable revision directory 승격
  -> SQLite current_revision 원자 교체
  -> scan SEALED + datapack READY
```

핵심 결정은 다음과 같다.

1. spread의 전송 순서는 `client sequence`, 한 spread 안의 순서는 `left -> right`가 권위다.
2. 페이지 번호 OCR은 정렬·중복 방지·identity의 권위로 사용하지 않는다.
3. 서버 ACK는 parser 성공이 아니라 **서버 소유 저장소와 DB에 artifact가 durable하게 접수됨**을 뜻한다.
4. parser 실패 페이지를 누락한 채 READY를 발행하지 않는다.
5. 기존 revision directory를 덮어쓰지 않고 새 immutable revision을 만든다.
6. filesystem rename 뒤 SQLite current pointer를 한 transaction에서 바꾸며, crash 중간 상태는
   publish journal로 재개한다.
7. 외부 HTTP multipart 수신·device durable outbox는 V4 책임이다. 개발 단계 outbox는 LAPTOP
   persistent storage에 두고 이후 같은 계약으로 Pi에 이식한다. S1은 서버 소유 bundle을 받는
   transport-neutral application contract를 구현한다.

## 2. 현재 구현과 S1 공백

### 2.1 Server S0에서 이미 보장되는 것

- SQLite migration, catalog, current revision pointer
- DRAFT/READY/FINALIZING/ERROR datapack 상태
- datapack별 active OPEN/SEALING scan 하나
- scan `base_revision`, `through_sequence`, seal intent
- persistent reading cursor와 command receipt
- `/api/v1` catalog/scan/reading 경로
- revision-aware datapack loader cache

S0 seal은 cutoff와 FINALIZING만 기록하며 READY revision을 만들지 않는다.

### 2.2 기존 whole-batch `/jobs`를 재사용할 수 없는 이유

기존 `remote_ingest.JobRegistry`는 내부 시험 도구다.

- job과 queue가 process memory에만 존재
- 모든 이미지를 한 번에 받아 datapack directory를 직접 작성
- scan session, sequence, side, artifact digest, receipt가 없음
- 기존 revision append와 atomic current pointer가 없음
- worker 완료 순서와 page order를 분리하지 않음

따라서 `/jobs` 구현을 S1 제품 경로로 승격하거나 그 위에 얇게 sequence만 붙이지 않는다.

### 2.3 Scanner artifact에서 이미 존재하는 정보

Scanner의 V2 bundle manifest(`schema_version: "2.0"`)에는 다음이 있다.

- `artifact_id`, `session_id`, `spread_id`, `source_frame_id`
- source frame, seam/ownership/UVDoc diagnostics
- left/right `mask`, `crop`, `uvdoc`, `diagnostics` 파일과 SHA-256
- 양쪽 페이지 local readiness와 UVDoc 결과
- bundle manifest SHA-256

S1 parser 입력은 각 side의 `uvdoc.jpg`다. crop/source를 다시 보정하거나 UVDoc 실패를 unwarped
fallback으로 바꾸지 않는다.

## 3. 책임 경계

### 3.1 S1이 소유

- verified spread의 sequence/artifact 멱등 접수와 receipt
- spread/page fragment 상태와 persistent parser job
- 서버 재시작 후 QUEUED/PROCESSING job 복구
- injected Document Parser backend를 통한 left/right Page IR 생성
- Page IR validation, accessible page 생성과 diagnostics 보존
- seal cutoff 이하 spread의 completeness/terminal 판정
- base revision과 새 fragment의 append assembly
- 신규 page/item ID의 deterministic uniqueness
- 신규 utterance TTS와 audio index 조립
- staging datapack 전체 검증
- immutable revision directory와 publish journal
- SQLite revision/current pointer/scan/datapack 상태 원자 전환
- finalize status를 기존 `/api/v1/scan-sessions/{id}`에 투영
- publish 뒤 S0 datapack cache invalidation

### 3.2 S1이 소유하지 않음

- device-side durable upload outbox와 retry cache(LAPTOP 개발 구현, 이후 Pi 이식)
- 외부 multipart/resumable upload, chunk protocol, TLS
- client-local staging path를 서버 path로 직접 사용
- camera/frame sampling, crop, seam, UVDoc, page-change gate
- 페이지 번호를 이용한 sequence 재정렬 또는 자동 누락 보정
- parser 결과가 나쁜 페이지의 자동 생략/대체
- partial finalize 사용자 UI와 특정 sequence 재촬영 protocol
- audio byte streaming/device cache
- 모델 교체 또는 OCR·수식 점역 알고리즘 자체의 품질 개선

V4는 업로드 bytes를 server-owned immutable bundle로 만든 뒤 S1의 `accept_verified_spread()`를
호출한다. S1 테스트는 같은 경계를 통과하는 local fixture harness를 사용하되 production HTTP
upload endpoint를 만들지 않는다.

## 4. Transport-neutral spread 접수 계약

S1 application boundary는 임의 client path가 아니라 서버 저장소 key와 검증 metadata만 받는다.

```python
VerifiedSpreadInput(
    scan_session_id,
    sequence,
    artifact_id,
    spread_id,
    source_frame_id,
    bundle_storage_key,
    manifest_sha256,
)

accept_verified_spread(input) -> SpreadReceipt
```

`bundle_storage_key`는 configured receive root 아래의 server-generated relative key다. S1은 다음을
다시 검증한다.

- manifest schema `2.0`, manifest hash, artifact/session/source identity
- left/right가 모두 존재하고 같은 source frame을 공유함
- `local_readiness.ready=true`, `requires_both_pages=true`
- 모든 상대 경로의 root confinement와 중복 path 부재
- symlink/reparse traversal 부재
- manifest에 기록된 size/SHA-256과 실제 file 일치
- UVDoc image decode 성공, 기록된 width/height와 일치
- 허용된 file count/총 byte/image dimension 상한

접수 transaction 규칙:

- `(scan_session_id, sequence)`가 primary logical position
- 동일 position + 동일 artifact/manifest digest 재시도: 기존 receipt 반환, mutation 0
- 동일 position + 다른 digest: `409 SPREAD_SEQUENCE_COLLISION`
- 동일 artifact를 다른 session/sequence에 재사용: `409 ARTIFACT_ID_COLLISION`
- OPEN이면 양의 sequence를 접수
- SEALING이면 `sequence <= through_sequence`의 missing/exact retry만 허용
- `sequence > through_sequence`, SEALED/ERROR scan에는 신규 접수 거부
- receipt는 bundle durability와 DB commit 이후에만 반환

ACK는 OCR 품질 승인이 아니다. Parser terminal failure는 finalize를 차단하며 기존 revision을 보존한다.

## 5. SQLite migration v2

기존 S0 database를 additive migration으로 확장한다. 자동 삭제·재생성하지 않는다.

### 5.1 `scan_spreads`

```text
scan_session_id FK
sequence
artifact_id UNIQUE
spread_id
source_frame_id
manifest_sha256
bundle_relative_path
receipt_id UNIQUE
status: RECEIVED | PROCESSING | READY | REJECTED | ERROR
received_at, updated_at
error_code NULL, error_detail NULL
PRIMARY KEY(scan_session_id, sequence)
```

### 5.2 `page_fragments`

```text
scan_session_id, sequence, side: LEFT | RIGHT
page_id UNIQUE
image_relative_path, image_sha256
status: QUEUED | PROCESSING | READY | REJECTED | ERROR
page_ir_relative_path NULL
accessible_page_relative_path NULL
parser_engine_json NULL
validation_json NULL
attempt_count, lease_owner NULL, lease_until NULL
created_at, updated_at, terminal_at NULL
error_code NULL, error_detail NULL
PRIMARY KEY(scan_session_id, sequence, side)
```

### 5.3 `finalize_runs`

```text
finalize_run_id PK
scan_session_id UNIQUE FK
datapack_id FK
base_revision NULL
target_revision NULL
through_sequence
status: WAITING | ASSEMBLING | VALIDATING | PROMOTED | PUBLISHED | ERROR
staging_relative_path NULL
final_relative_path NULL
manifest_sha256 NULL
created_at, updated_at, published_at NULL
error_code NULL, error_detail NULL
```

### 5.4 기존 테이블 보강

`scan_sessions`에 다음 additive column을 둔다.

- `published_revision NULL`
- `finalize_run_id NULL`
- `finalize_error_code/detail NULL`
- `finalize_started_at/completed_at NULL`

필요한 invariant는 DB unique/check constraint와 service transaction을 함께 사용한다. process-local
dict나 thread lock만으로 중복 receipt/revision을 막지 않는다.

## 6. Persistent parser worker

S1 worker는 DB를 queue의 권위로 사용한다.

1. `QUEUED` fragment를 transaction에서 claim하고 lease 기록
2. bundle의 해당 side UVDoc SHA를 재검증
3. injected `PageParserPort.parse(image_path, page_id)` 호출
4. Paddle adapter composition에서는 `parse_page()` 결과를 explicit page ID로
   `build_page_ir_from_vl_result()`에 전달하고, 기존 `detect_problem_units_in_document()`를 적용
5. one-page document payload를 기존 `validate_document_ir()`로 검증
6. `flatten_page()`로 accessible page 생성
7. Page IR, accessible page, parser metadata를 fragment staging에 atomic write
8. 성공 시 READY, content/validation reject는 REJECTED, retryable runtime failure는 재queue

기본 parser concurrency는 1이다. PaddleOCR-VL instance는 worker composition에서 한 번 load하여
재사용하고 매 fragment마다 모델을 다시 만들지 않는다. concurrency와 retry/backoff는 config로
분리하지만 실제 GPU 메모리·처리시간 계측 전 기본값을 늘리지 않는다.

PROCESSING lease가 만료된 fragment는 서버 재시작 시 QUEUED로 회수한다. retry 횟수를 초과한
infrastructure failure는 ERROR로 남긴다. validation/content failure를 같은 입력으로 무한 재시도하지
않는다.

## 7. Stable page identity와 순서

페이지 번호 OCR은 identity가 아니다. 신규 page ID는 scan identity, sequence, side에서 결정론적으로
만든다.

```text
pg-{sha256(scan_session_id)[0:12]}-{sequence:08d}-L
pg-{sha256(scan_session_id)[0:12]}-{sequence:08d}-R
```

Page IR builder에는 이 ID를 명시 전달하여 filename fallback `p001`에 의존하지 않는다. node/table
cell/problem ID는 page ID prefix를 사용하므로 새 fragment끼리 충돌하지 않는다.

최종 append order:

```text
base revision pages unchanged
then sequence 1 LEFT, sequence 1 RIGHT,
     sequence 2 LEFT, sequence 2 RIGHT, ... through N
```

- worker 완료 순서는 최종 page order에 영향 없음
- 기존 page/focus item ID는 byte-level 의미로 보존
- 새 revision에서 기존 reading anchor가 그대로 resolve되어야 함
- 같은 물리 페이지를 다른 scan에서 다시 보낸 문제는 Scanner M1 gate 책임이며, S1은 digest가 다른
  두 logical sequence를 임의로 동일 페이지라 추정해 제거하지 않음

## 8. Seal과 finalize readiness

S0의 `request_seal(scan_session_id, N)`가 SEALING을 기록하면 S1 finalize worker가 persistent
`finalize_run`을 생성하거나 기존 run을 재사용한다.

Finalize prerequisites:

- sequence가 정확히 `1..N`으로 contiguous
- 각 spread에 LEFT/RIGHT fragment가 정확히 하나씩 존재
- 모든 cutoff 이하 fragment가 READY
- REJECTED/ERROR fragment 0
- base revision이 scan open 시점과 동일
- `N` 이후 accepted spread 0

아직 parser가 진행 중이면 FINALIZING을 유지한다. missing row나 transient worker 상태를 READY/ERROR로
성급히 바꾸지 않는다. terminal REJECTED/ERROR가 있으면 finalize는 명시 실패한다.

### 8.1 cutoff 0 정책

- 기존 READY datapack + `N=0`: 새 revision을 만들지 않는 no-op finalize. scan을 SEALED로 바꾸고
  `published_revision=base_revision`을 반환하여 사용자가 바로 기존 reading으로 진입 가능
- 신규 DRAFT + `N=0`: `EMPTY_DRAFT_SCAN`으로 scan finalize 실패, datapack은 재촬영 가능한 DRAFT 유지

## 9. Append assembly

### 9.1 Base revision

- DRAFT: 빈 document에서 revision 1 생성
- READY append: scan의 `base_revision`이 가리키는 immutable datapack을 load
- target revision은 DRAFT면 1, append면 `base_revision + 1`
- finalize 직전 catalog current revision이 base와 다르면 `BASE_REVISION_CHANGED` 충돌
- base의 document page/item ID, audio entry, WAV는 변경하지 않음

### 9.2 New document

- document ID는 datapack ID 유지
- base accessible pages 뒤에 fragment accessible pages를 규정 순서로 append
- page ID, focus item ID, reading order uniqueness 전수 검사
- 빈 page, focus item 0개, dangling relationship, invalid math/table structure는 정책에 따라 명시 reject;
  조용히 page를 빼지 않음

### 9.3 TTS와 audio index

- 기존 audio index/WAV는 그대로 복사 또는 immutable hard-link 가능한 환경에서 검증 후 재사용
- 새 fragment의 utterance만 기존 `enumerate_utterances()` 규칙으로 열거
- key/text mismatch는 `AUDIO_KEY_COLLISION`으로 중단
- 같은 text는 loader의 기존 text lookup semantics에 따라 재사용 가능
- 새 utterance만 injected synthesizer로 생성
- `_system` boundary pool은 기존 `ensure_system_pool()`을 재사용하고 concurrent writer를 직렬화
- audio index의 모든 WAV 존재/hash/decode metadata를 publish 전 확인

S1은 OCR·TTS를 request thread에서 수행하지 않는다.

### 9.4 Manifest

새 manifest는 다음을 포함한다.

- 기존 book ID/title
- 전체 ordered page IDs
- revision/base revision/publish timestamp provenance
- incremental pipeline/parser/TTS versions
- accepted spread/fragment digest summary
- 전체 validation summary

기존 datapack loader와 navigation code가 읽을 수 있는 schema를 유지한다. 새 provenance field는
backward-compatible additive field로 둔다.

## 10. Immutable storage와 atomic publish

권장 layout:

```text
datapacks/
  _server/received/{scan_id}/{sequence}/{artifact_id}/...
  _server/fragments/{scan_id}/{sequence}/{left|right}/...
  _server/finalize/{finalize_run_id}.tmp/...
  _revisions/{storage_key}/r00000001/...
  _revisions/{storage_key}/r00000002/...
```

기존 bootstrap revision 1이 `datapacks/{book_id}`에 있더라도 이를 이동하거나 덮어쓰지 않는다.
첫 append부터 새 immutable root를 `_revisions` 아래에 만든다. product reading은 SQLite revision
pointer를 사용하는 S0 `/api/v1` 경로가 권위다. legacy `/sessions`는 기존 whole-batch 시험 경로로
보존하지만 S1 current revision 권위로 사용하지 않는다.

Publish 순서:

1. 같은 filesystem의 finalize temp directory에 완전한 datapack 생성
2. loader/schema/audio/hash 및 append invariant 전수 검증
3. directory fsync 가능한 환경에서는 적용하고 temp를 final immutable revision path로 rename
4. SQLite `BEGIN IMMEDIATE`
5. finalize run/base/current/cutoff를 다시 확인
6. target revision READY insert, 이전 revision SUPERSEDED
7. datapack `current_revision=target`, `status=READY`
8. scan `status=SEALED`, `published_revision=target`
9. finalize run PUBLISHED 후 commit
10. S0 cache invalidate

DB commit 전에는 READY response나 저장 완료 feedback을 노출하지 않는다.

Crash recovery:

- temp만 존재: finalize run 상태/hash에 따라 같은 run 재개, 자동 READY 처리 금지
- final dir 존재 + DB 미발행: hash가 journal과 같으면 publish transaction 재개
- DB published + cache invalidate 전 crash: 새 revision key로 reload하므로 correctness 유지
- 같은 target path에 다른 hash: `REVISION_STORAGE_COLLISION`, 자동 덮어쓰기 금지
- orphan을 즉시 삭제하지 않고 diagnostics/관리 대상으로 기록

## 11. 실패 시 기존 데이터 보존

### 기존 READY datapack append 실패

- 기존 current revision과 reading 가능 상태 유지
- scan/finalize run은 ERROR
- datapack catalog status는 READY로 복원
- finalize error는 scan/finalize diagnostics에 보존
- 새 staging/fragment는 READY datapack에 섞지 않음

### 신규 DRAFT finalize 실패

- scan/finalize run은 ERROR
- recoverable parser/content 실패면 datapack은 DRAFT로 복원하여 새 scan 가능
- catalog/storage 자체가 손상된 fatal failure만 datapack ERROR
- 실패 fragment와 원본 bundle은 진단용으로 보존

partial page omission, 자동 side 교체, 이전 revision 위 덮어쓰기는 금지한다.

## 12. S1 status/API 확장

외부 artifact body endpoint는 만들지 않는다. 기존 S0 경로를 additive하게 확장한다.

```text
GET /api/v1/scan-sessions/{scan_session_id}
GET /api/v1/scan-sessions/{scan_session_id}/spreads
POST /api/v1/scan-sessions/{scan_session_id}/seal-intent   # 기존, S1 finalize enqueue 연결
```

scan status response 추가 field:

```json
{
  "status": "open|sealing|sealed|error",
  "through_sequence": 3,
  "published_revision": 2,
  "spread_counts": {"received": 3, "ready": 3, "rejected": 0, "error": 0},
  "finalization": {"status": "published", "error_code": null, "error_detail": null}
}
```

- SEALING은 Coordinator `FINALIZING`
- SEALED + `published_revision`은 Coordinator `READY`
- ERROR는 structured reason과 함께 Coordinator recoverable error
- poll 응답은 read-only이며 polling 자체가 parser/finalize mutation을 실행하지 않음

실제 upload receipt API와 `DeliveryPort` HTTP adapter는 V4에서 추가한다.

## 13. Worker와 resource 정책

- parser queue와 finalize queue는 SQLite persistent state가 권위
- 기본 parser worker 1, finalize worker 1
- PaddleOCR-VL과 TTS runtime은 process composition에서 lazy singleton 재사용
- request thread에서 GPU inference/음성 합성 금지
- worker heartbeat/lease timeout/retry limit/backoff는 config
- DB polling interval은 과도한 busy loop를 피하도록 config
- 동일 scan의 left/right 또는 여러 scan job 결과가 순서 밖으로 끝나도 assembly는 sequence로 정렬
- shutdown은 새 claim을 중단하고 현재 DB 상태를 복구 가능하게 남김

배포나 horizontal scaling은 이번 범위가 아니다. 다중 process worker claim은 SQLite transaction으로
중복 실행을 막되, 성능을 검증하지 않고 worker 수를 늘리지 않는다.

## 14. 구현 단계

### Phase 0 — 계약 고정

- S1/V4 경계와 ACK 의미 문서화
- verified bundle/input/receipt/finalize view pure types
- page ID/order/no-op cutoff 정책 고정

### Phase 1 — Migration·repository

- SQLite v2 migration
- spread/fragment/finalize repository와 constraints
- receipt collision, lease, restart recovery 테스트

### Phase 2 — Bundle validation·fragment creation

- Scanner bundle `2.0` reader/validator
- root confinement/hash/image/left-right 검증
- atomic spread/page row 생성
- local fixture ingest harness

### Phase 3 — Persistent parser worker

- injected parser port와 Paddle composition adapter
- deterministic page ID를 사용하는 per-side Page IR
- validation/flattening/fragment atomic output
- transient retry와 terminal reject 분류

### Phase 4 — Append assembler·TTS

- base loader와 ordered accessible page assembly
- existing ID/audio preservation
- new utterance synthesis와 audio index merge
- staging datapack full validation

### Phase 5 — Finalize·atomic publish

- finalize run state machine와 cutoff terminal gate
- immutable directory promotion
- DB pointer/state atomic transaction
- crash recovery와 cache invalidation
- cutoff 0 no-op

### Phase 6 — Status/API·Coordinator compatibility

- scan/spread/finalize status projection
- seal intent → persistent finalize enqueue
- existing S0 HTTP client finalization mapping 검증
- legacy endpoint 회귀

### Phase 7 — 회귀·보고

- Document Parser 전체 unit regression
- Server S0/S1 restart/fault/idempotency regression
- Device runtime Coordinator regression
- fixture end-to-end: new draft와 existing append
- GPU/model이 실제 사용 가능한 경우 실모델 smoke 결과를 별도 기록
- 구현 보고서와 미검증 항목 명시

## 15. 테스트 행렬

### 15.1 Migration·repository

- S0 v1 DB → v2 migration, 반복 no-op, future schema fail-fast
- FK/status/side/sequence/unique constraint
- same sequence/same digest receipt replay mutation 0
- same sequence/different digest, artifact reuse collision
- restart 뒤 RECEIVED/QUEUED/PROCESSING lease 회수
- SEALING cutoff 이하 retry 허용, cutoff 초과 거부

### 15.2 Bundle validation

- 실제 Scanner V2 fixture manifest acceptance
- manifest/file/image hash mismatch
- missing left/right, side/source identity mismatch
- absolute/`..`/symlink path와 duplicate path 거부
- local readiness false, UVDoc decode/dimension mismatch
- oversized file count/bytes/dimensions
- crop/source가 존재해도 parser 입력은 UVDoc only

### 15.3 Parser fragments

- worker completion order 역전에도 page order 불변
- deterministic page/node ID, 서로 다른 spread 충돌 0
- valid Page IR → accessible page READY
- schema invalid/content loss → REJECTED, silent page 없음
- retryable backend failure 후 제한 재시도
- process restart 후 job exactly one terminal result
- 한 side 실패 시 spread READY 0

### 15.4 Assembly·append

- 신규 DRAFT: N spread → 2N ordered pages, revision 1
- 기존 READY: 기존 pages byte-equivalent identity + 2N append, revision +1
- 기존 page/focus item anchor가 새 revision에서 resolve
- duplicate page/item/audio key 충돌 중단
- 기존 audio 재사용, 새 utterance만 synthesize
- document/manifest/audio page count/order 일치
- parser reject 하나라도 READY publish 0

### 15.5 Atomic publish·recovery

- base current 변경 충돌
- validation failure에서 current revision unchanged
- rename 전/후, DB commit 전/후 fault injection
- final dir same hash 재개, different hash collision
- publish retry revision 중복 0
- commit 뒤 SEALED/READY/revision/cache 일치
- 기존 append 실패 시 old READY, draft 실패 시 DRAFT 복원
- READY base cutoff 0 no-op, DRAFT cutoff 0 명시 실패

### 15.6 API·회귀

- GET status가 worker mutation을 유발하지 않음
- SEALED response에 published revision 필수
- S0 device HTTP adapter가 FINALIZING/READY/ERROR를 올바르게 매핑
- legacy `/jobs`, `/sessions`, `/datapacks` 기존 테스트 유지
- Document Parser 전체 unit regression
- Device runtime 전체 regression
- production artifact upload HTTP 호출 0(S1 범위 확인)

## 16. 완료 기준

- 서버 재시작 후 accepted spread/parser/finalize 상태가 소실되지 않음
- 동일 sequence 재전송이 fragment/revision/page를 중복 생성하지 않음
- seal cutoff `1..N`의 모든 left/right가 READY일 때만 publish 가능
- parser/validation/TTS 실패를 페이지 누락 READY로 처리하지 않음
- 신규 draft와 기존 datapack append 모두 immutable revision을 생성
- 기존 revision과 reading anchor를 보존
- filesystem/DB fault injection에서 old current 또는 완전한 new current 중 하나만 노출
- DB commit 뒤에만 SEALED/READY 및 완료 feedback 근거가 생김
- S0/legacy/Document Parser/Coordinator 회귀 통과
- V4·실장치·실네트워크 미구현 사항을 완료로 표시하지 않음

실제 PaddleOCR-VL/TTS smoke를 환경 문제로 실행하지 못했다면 pure/fake pipeline 완료와 분리해
보고한다. 실행하지 않은 실모델 품질·성능은 S1 완료 근거로 주장하지 않는다.

## 17. 명시적 후속 범위

- Device Connectivity C0: LAPTOP 고정 endpoint·boot-equivalent handshake·presence/heartbeat·재연결
- V4 HTTP multipart/chunk ingest, server-owned upload writer, DeliveryPort HTTP adapter
- LAPTOP durable outbox, retry/backoff/storage quota/eviction과 이후 Pi storage 이식
- targeted sequence 재촬영/교체와 partial finalize 사용자 선택
- audio download endpoint, ETag/range/device cache
- LAPTOP STM/camera/feedback 실제 E2E
- Raspberry Pi systemd·camera/GPIO/audio·자원·전원 차단 target 검증
- PostgreSQL/object storage/horizontal worker scaling
- production deployment/systemd/TLS/monitoring
- datapack rename/delete/admin UI와 garbage collection
- OCR/수식 점역 모델 품질 개선
- commit/push/PR/release

## 18. 승인 시 변경 범위

승인 시 다음을 구현한다.

- `document-parser.server` S1 domain/repository/migration/services/workers/status API
- Scanner bundle `2.0` server-side validator와 local fixture harness
- incremental fragment parser adapter와 append/TTS assembler
- immutable revision publisher와 recovery journal
- S0 scan/finalize response의 additive 확장
- S0/S1/legacy/Document Parser/device-runtime 회귀 테스트
- Server S1 API/schema 문서와 구현 보고서

다음은 승인 범위에 포함하지 않는다.

- production artifact upload endpoint와 device outbox(LAPTOP 개발, Pi 이식)
- Scanner/UVDoc/OCR 알고리즘 수정
- partial finalize/targeted replacement UI
- 실제 배포, commit/push

## 19. 중단 조건

다음이 확인되면 silent workaround 없이 구현을 중단하고 보고한다.

- 기존 AccessibleDocument page/item ID를 보존한 append가 불가능함
- S1 publish에 기존 current revision directory 덮어쓰기가 필수임
- filesystem 승격과 DB pointer 사이 crash를 recovery journal로 구분할 수 없음
- parser 실패 page를 누락해야만 READY datapack을 만들 수 있음
- ACK 전에 parser/TTS 완료까지 기다리지 않으면 현재 Coordinator가 동작할 수 없음
- V4 upload transport를 동시에 구현하지 않으면 S1 core를 검증할 수 없음
- current revision을 바꾸기 전에 READY/완료 feedback을 보내야만 흐름이 진행됨
- legacy 시험 endpoint 보존을 위해 S1 product revision을 filesystem listing에 종속시켜야 함

중단 시 repository/fragment/parser/assembler/publisher 중 실제 검증된 단계까지만 완료로 표시하고,
나머지를 같은 성공 상태로 묶지 않는다.
