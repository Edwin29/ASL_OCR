# Server S0 — Persistent Catalog · Scan Domain · Reading Progress 작업 패킷

상태: **승인됨 · S0 구현 및 검증 완료 (S1/V4 제외)**  
작성일: 2026-08-31  
선행 조건: Integration V0 `DeviceFlowCoordinator`, Scanner V3-A.5 M1 identity/ACK lifecycle  
후속 조건: Server S1 incremental fragment·append·seal·atomic revision, Scanner V3-B + Server V4 durable outbox·HTTP spread ingest

## 1. 목표와 결정

Server S0를 제품 서버의 **영속 control plane**으로 구현한다. S0가 해결할 문제는 다음 네 가지다.

1. 서버 재시작 뒤에도 유지되는 datapack catalog와 revision 포인터
2. 신규/기존 datapack에 대한 scan session의 영속 수명주기와 seal intent
3. `device_id + datapack_id` 기준 reading cursor 복원
4. 네트워크 재시도로 create/open/navigation command가 중복 실행되지 않는 idempotency

S0는 Document Parser의 OCR·점역 알고리즘이나 Scanner의 이미지 판정을 소유하지 않는다. 기존
`DatapackSession`, `SpeechController`, `BraillePresenter`, datapack loader는 그대로 재사용하고,
그 앞뒤에 SQLite 저장소·application service·versioned HTTP/Coordinator adapter를 둔다.

개발 단계의 device client는 Raspberry Pi가 아니라 이를 대체하는 LAPTOP PC에서 실행한다. S0의
HTTP/device/idempotency 계약은 호스트 종류와 무관하며, LAPTOP 통합 후 동일 계약을 Pi로 이식한다.

이 패킷에서 scan `seal`은 cutoff를 영속 기록하고 `SEALING/FINALIZING` 상태를 반환하는 **intent**까지만
구현한다. fragment terminal 확인, 기존 revision과의 append, staging 검증, atomic current publish와
`READY` 전환은 Server S1 책임이다. 따라서 S0 단독으로 새 스캔을 READY datapack으로 완성했다고
표시하지 않는다.

## 2. 현재 구현과 공백

현재 `document-parser` 서버에는 다음 경로가 있다.

- `remote_ingest.JobRegistry`: whole-batch `/jobs`, in-memory job registry
- `combined_server`: whole-batch ingest와 reading HTTP를 한 Flask app에 조합
- `SessionStore`: loaded datapack과 active reading session을 process memory에 저장
- `http_server`: `/sessions`와 button command를 제공하지만 cursor·command receipt가 in-memory
- `/datapacks`: 디렉터리 이름만 나열하고 status/revision/title을 영속 관리하지 않음

이 상태에서는 다음이 보장되지 않는다.

- 서버 재시작 후 reading 위치 복원
- 같은 navigation command 재전송 시 한 번만 이동
- 응답을 잃은 `새 데이터팩 추가` 재시도에서 draft 한 개만 생성
- 한 datapack에 둘 이상의 active append scan 방지
- scan cutoff와 상태 조회
- 새 revision publish 뒤 `SessionStore` cache invalidation

기존 `/jobs`는 내부 whole-batch 시험 도구로 보존하되 Scanner 제품 upload API로 승격하지 않는다.

## 3. 책임 경계

### 3.1 S0가 소유

- shared datapack catalog: ID, title, status, current revision, 생성 장치, timestamp
- 기존 on-disk datapack의 revision 1 bootstrap/reconciliation
- draft 생성과 자동 기본 제목
- scan session open/recovery, base revision, one-active-scan lease
- seal cutoff intent와 같은 cutoff 재시도의 idempotency
- reading session metadata와 persistent navigation progress
- reading command의 durable receipt와 request-digest 충돌 감지
- SQLite schema migration, transaction, restart recovery
- `/api/v1` catalog/scan/reading HTTP 계약
- Integration V0 port를 구현하는 HTTP client adapter

### 3.2 S0가 소유하지 않음

- Scanner artifact upload body와 durable device outbox
- spread sequence별 artifact/fragment 저장과 parser job 실행
- PaddleOCR-VL, 수식/혼합 점역, Piper 합성 실행
- append document/audio assembly와 atomic revision publish
- parser reject/fallback 정책
- remote audio byte streaming/cache
- datapack rename/delete/admin UI
- multi-tenant authorization, TLS termination, 외부 인터넷 배포
- STM/GPIO, camera, beep/TTS renderer

## 4. ID·상태·시간 계약

모든 ID는 opaque ASCII 문자열이며 path로 사용하지 않는다. server-generated ID는 UUID 계열을
사용하고, filesystem directory name은 별도 검증된 storage key로 매핑한다.

```text
DatapackStatus: DRAFT | FINALIZING | READY | ERROR
ScanSessionStatus: OPEN | SEALING | SEALED | ERROR
ReadingSessionStatus: OPEN | CLOSED | ERROR
RevisionStatus: STAGING | READY | SUPERSEDED | ERROR
```

- timestamp는 UTC ISO-8601 또는 UTC epoch 정수로 저장한다.
- revision은 datapack별 0부터 시작하는 단조 증가 정수다.
- 신규 DRAFT는 current revision이 없다. 기존 검증된 datapack bootstrap은 revision 1이다.
- READY datapack만 reading session을 열 수 있다.
- READY 또는 DRAFT datapack은 append scan을 열 수 있다.
- 한 datapack에는 `OPEN/SEALING` scan session을 동시에 하나만 허용한다. 다른 장치는 409이다.
- 동일 device/datapack의 재접속은 기존 active session을 반환하여 복구 가능하게 한다.
- seal cutoff는 0 이상의 `through_sequence`다. 같은 cutoff 재시도는 같은 결과, 다른 cutoff는 409다.

기본 draft 제목은 설정된 Asia/Seoul 표시 시간과 서버 순번을 사용한
`새 데이터팩 YYYY-MM-DD HH:mm #NN`으로 한다. 이 제목 형식은 사용성 기본값이며 identity가 아니다.

## 5. SQLite 스키마

기본 저장소는 Python 표준 `sqlite3`로 구현한다. 새 ORM dependency는 추가하지 않는다.

### 5.1 핵심 테이블

```text
schema_migrations
  version PK, applied_at

devices
  device_id PK, first_seen_at, last_seen_at, metadata_json

datapacks
  datapack_id PK
  storage_key UNIQUE
  title
  status
  current_revision NULL
  created_by_device_id FK
  created_at, updated_at
  error_code NULL, error_detail NULL

datapack_revisions
  datapack_id FK, revision, status
  root_relative_path
  manifest_sha256
  created_at, published_at NULL
  PRIMARY KEY(datapack_id, revision)

scan_sessions
  scan_session_id PK
  datapack_id FK, device_id FK
  base_revision NULL
  status
  through_sequence NULL
  open_operation_id
  seal_operation_id NULL
  created_at, updated_at
  error_code NULL, error_detail NULL

reading_sessions
  reading_session_id PK
  device_id FK, datapack_id FK, revision
  viewport_size
  status, created_at, last_seen_at

reading_progress
  device_id FK, datapack_id FK
  revision_seen
  cursor_json
  cursor_version
  updated_at
  PRIMARY KEY(device_id, datapack_id)

command_receipts
  scope_type, scope_id, command_id
  request_sha256
  response_json
  created_at
  PRIMARY KEY(scope_type, scope_id, command_id)
```

추가 invariant:

- partial unique index로 datapack별 active `OPEN/SEALING` scan 하나만 허용
- current revision은 동일 datapack의 READY revision만 참조
- JSON은 UTF-8 canonical serialization 후 SHA-256 계산
- `PRAGMA foreign_keys=ON`, WAL, bounded busy timeout 사용
- 모든 mutation과 command receipt 기록은 하나의 transaction에서 수행
- DB path, datapacks root, staging root는 명시 설정하며 request의 path 값을 신뢰하지 않음

### 5.2 Migration과 백업

- migration은 순방향 additive SQL 파일과 `schema_migrations`로 관리
- unknown future schema version이면 fail-fast하고 downgrade를 시도하지 않음
- startup 시 DB 파일과 root를 만들 수 있는지 사전 검사
- S0는 자동 DB 삭제·재생성을 하지 않음
- 운영 backup/restore 도구는 후속이나, 테스트는 DB 파일 복사 후 재개를 검증

## 6. 기존 datapack bootstrap

기존 `datapacks/{book_id}`를 잃지 않기 위해 startup reconciliation을 제공한다.

1. `_system`을 제외한 디렉터리 후보를 열거
2. `manifest.json`, `document.json`, `audio_index.json`을 기존 loader/validator로 읽음
3. manifest hash와 book ID/title을 추출
4. DB에 없는 검증 성공 datapack만 revision 1, READY로 import
5. 같은 ID·같은 manifest hash는 no-op
6. 같은 ID인데 hash가 다르면 자동 덮어쓰기 없이 `CATALOG_RECONCILIATION_CONFLICT`
7. 불완전/손상 datapack은 READY로 가장하지 않고 진단만 기록

DB가 만들어진 뒤에는 filesystem 열거 결과가 catalog 진실 원천이 아니다. DB current revision과
검증된 revision root가 진실 원천이다. S1 publish만 current revision을 바꿀 수 있다.

## 7. Idempotency 계약

### 7.1 공통 규칙

모든 mutation은 client operation/command ID를 가진다.

- 동일 scope + command ID + 동일 request digest: 저장된 동일 응답 반환, domain mutation 0
- 동일 scope + command ID + 다른 digest: `409 IDEMPOTENCY_KEY_REUSED`
- receipt를 commit하기 전에 성공 응답을 외부에 노출하지 않음
- DB commit 성공 후 HTTP 응답을 잃어도 재시도 결과가 동일함
- stale reading/scan session ID는 다른 current session을 변경하지 않음

receipt의 무기한 정리 정책은 S0에서 섣불리 정하지 않는다. 소형 prototype에서는 session/datapack
수명 동안 보존하고, bounded archival은 실제 사용량 계측 뒤 후속으로 둔다.

### 7.2 Integration V0 최소 계약 보강

현재 `CatalogPort.create_datapack(device_id)`와 `ScanSessionPort.open(device_id, datapack_id)`에는
재시도용 key가 없다. S0 구현 시 다음처럼 보강한다.

```python
CatalogPort.create_datapack(device_id, operation_id)
ScanSessionPort.open(device_id, datapack_id, operation_id)
ReadingSessionPort.open(device_id, datapack_id, viewport_size, operation_id)
```

- 선택 CONFIRM의 `DeviceInputEvent.event_id`에서 create/open용 파생 operation ID를 한 번 만들고 재시도에 재사용
- seal은 `(scan_session_id, through_sequence)` 자체가 idempotency identity
- reading open은 scan ID/revision 기반 deterministic operation ID 사용
- reading command는 이미 존재하는 `command_id=input_event.event_id`를 유지
- 기존 중복 input event 차단, stale callback 차단, public Scanner event 계약은 보존

장치 재부팅으로 operation ID를 잃은 경우에도 같은 device/datapack의 active scan을 조회해 반환한다.
응답을 잃은 빈 draft는 catalog에 DRAFT로 남아 사용자가 다시 선택할 수 있으며 자동으로 두 번째
draft를 생성하지 않는다.

## 8. Catalog application service

```text
list_datapacks(device_id)
create_datapack(device_id, operation_id)
get_datapack(datapack_id)
```

- catalog는 초기 prototype에서 장치 간 shared 목록이다. device ID는 audit/progress key다.
- list 정렬은 `updated_at DESC, datapack_id ASC`로 deterministic하게 고정
- READY와 DRAFT는 Coordinator에서 selectable, FINALIZING/ERROR는 상태 조회에는 보이되 선택 목록에서 제외
- `[새 데이터팩 추가]` pseudo-item은 지금처럼 Coordinator projection이 한 번만 추가하며 server row가 아님
- create retry는 같은 CatalogEntry를 반환
- title audio가 없으면 `title_audio_ref=None`; S0에서 TTS 합성을 시작하지 않음

## 9. Scan session service

```text
open_scan(device_id, datapack_id, operation_id)
get_scan(scan_session_id)
request_seal(scan_session_id, through_sequence)
```

open:

- datapack 상태와 active lease를 transaction 안에서 검사
- READY append는 `base_revision=current_revision`, DRAFT는 `base_revision=NULL`
- 같은 device/datapack의 기존 OPEN은 복구 응답으로 반환
- 다른 device의 active scan은 409
- open 성공 뒤에만 Coordinator가 Scanner를 시작

seal intent:

- OPEN → SEALING 및 cutoff 원자 기록
- 반복 같은 cutoff는 기존 FINALIZING 응답
- 다른 cutoff, ERROR/SEALED session, 음수 cutoff는 거부
- S0 단독 status는 FINALIZING이며 READY revision을 만들지 않음
- S1이 fragment와 parser terminal 상태를 확인해 SEALED/ERROR 및 datapack revision을 갱신할 예정

S0에는 artifact sequence row가 없으므로 “cutoff 이하가 전부 durable ACK됨”을 자체 입증하지 않는다.
Coordinator/DeliveryPort의 flush 결과를 신뢰해 intent를 받되, 최종 publish 시 S1이 서버 저장 상태로
다시 검증한다.

## 10. Persistent reading service

### 10.1 Cursor shape

단순 index만 저장하지 않고 현재 `NavigationState`와 stable anchor를 함께 저장한다.

```json
{
  "document_id": "...",
  "page_id": "...",
  "focus_item_id": "...",
  "page_index": 0,
  "node_index": 0,
  "mode": "DOCUMENT",
  "table_row": null,
  "table_column": null,
  "braille_offset": 0,
  "math_span_index": 0,
  "generation": 0
}
```

- 같은 revision은 index와 anchor가 모두 일치해야 함
- append revision에서는 S1이 보존한 `page_id/focus_item_id`로 index를 다시 resolve
- initial progress가 없을 때만 page 0/node 0에서 시작
- 저장된 anchor가 사라졌거나 범위를 벗어나면 조용히 page 0으로 덮어쓰지 않고
  `READING_CURSOR_INVALID` recoverable error 반환
- cursor JSON의 schema/version을 명시하고 unknown version은 fail-fast

### 10.2 Command transaction

navigation command 한 건은 다음 순서로 처리한다.

1. `BEGIN IMMEDIATE`
2. command receipt 조회; 동일 retry이면 저장 응답 반환
3. DB의 최신 durable cursor로 `DatapackSession` 복원
4. 기존 `command_from_wire`/`handle_button`으로 정확히 한 번 적용
5. 새 cursor, braille frame, audio metadata 검증
6. reading progress와 response receipt를 같은 transaction에 저장
7. commit 뒤에만 response/cache 공개

DB commit이 실패하면 이동된 in-memory 객체를 폐기하고 durable cursor에서 다시 만든다. 이로써
“상태는 두 번 이동했지만 receipt는 없는” split-brain을 방지한다.

### 10.3 Cache와 revision

- loaded datapack cache key는 `(datapack_id, revision, manifest_sha256)`
- reading session cache는 authoritative progress가 아니라 재구성 가능한 최적화
- current revision 변경 시 이전 cache를 명시적으로 invalidate
- open/get_current/command는 DB revision과 cache revision 불일치 시 reload
- server restart 뒤 session ID로 get_current와 command가 복구 가능
- full document/audio 객체는 SQLite blob으로 복제하지 않음

## 11. HTTP V1 계약

기존 시험용 `/jobs`, legacy `/sessions`, `/datapacks`를 바로 깨지 않고 제품 경로는
`/api/v1` namespace로 추가한다.

```text
GET  /api/v1/devices/{device_id}/datapacks
POST /api/v1/devices/{device_id}/datapacks

POST /api/v1/datapacks/{datapack_id}/scan-sessions
GET  /api/v1/scan-sessions/{scan_session_id}
POST /api/v1/scan-sessions/{scan_session_id}/seal-intent

POST /api/v1/reading-sessions
GET  /api/v1/reading-sessions/{reading_session_id}
POST /api/v1/reading-sessions/{reading_session_id}/commands
```

규칙:

- 기존 `X-API-Key` 인증 유지
- mutation은 `Idempotency-Key` 또는 payload `command_id` 필수
- JSON content type, body size, ID 길이/문자 집합 제한
- error body는 `{code, message, retryable, details}` 구조
- DB busy/temporary I/O는 503 retryable, validation 400, unknown 404, state/idempotency conflict 409
- absolute filesystem path를 catalog/reading response에 새로 노출하지 않음
- audio metadata의 remote byte 전달은 S0 완료 기준이 아니며 opaque `audio_ref`로 유지
- health는 process 생존뿐 아니라 DB migration/version과 read/write probe 상태를 구분

S0 HTTP client adapter는 Integration V0의 Catalog/Scan/Reading port만 구현한다. Scanner artifact
upload/DeliveryPort는 V3-B/V4 전까지 fake 또는 기존 test adapter로 남긴다.

## 12. 동시성·장애 복구

- Flask threaded 요청은 connection-per-operation을 사용하고 connection 객체를 공유하지 않음
- SQLite transaction과 unique constraint가 process-local lock보다 최종 권위
- 같은 reading session command는 `BEGIN IMMEDIATE`와 receipt PK로 직렬화
- 동일 datapack scan open race는 한 요청만 성공하고 나머지는 기존 same-device session 또는 409
- process kill 뒤 OPEN/SEALING/reading progress가 그대로 조회됨
- SEALING은 startup 때 READY로 자동 승격하지 않음
- 손상 DB, unknown migration, catalog hash conflict는 자동 초기화하지 않고 startup 차단 또는 명시 ERROR
- datapack directory와 DB row의 일방적 삭제를 자동 복구로 가장하지 않음

## 13. 구현 단계

### Phase 0 — 계약 정합화

- Integration V0 operation ID 보강
- S0/S1/V4 책임과 status mapping 고정
- legacy endpoint 보존 정책과 `/api/v1` error schema 기록

### Phase 1 — Pure domain·SQLite migration

- server ID/value/status/error type
- migration runner와 v1 schema
- repository transaction·constraint·restart 테스트
- 기존 datapack bootstrap/reconciliation

### Phase 2 — Catalog·scan service

- list/create idempotency
- shared catalog ordering/status mapping
- open/recovery/one-active lease
- seal intent/cutoff idempotency와 status 조회

### Phase 3 — Persistent reading

- NavigationState ↔ durable cursor/anchor codec
- revision-aware restore와 invalid cursor rejection
- transactional command receipt/progress
- restart/cache invalidation/concurrent retry

### Phase 4 — HTTP와 Coordinator adapters

- `/api/v1` Flask routes와 typed error mapping
- Catalog/Scan/Reading HTTP clients
- API key/idempotency header/timeout handling
- legacy `/jobs`·`/sessions` 회귀 보존

### Phase 5 — 회귀·보고

- Document Parser 전체 단위 회귀
- Integration V0 Coordinator 전체 회귀
- restart/fault/concurrency/HTTP contract 테스트
- schema/API 문서와 S0 구현 보고서
- 미구현 S1/V4 항목 명시

## 14. 테스트 행렬

### 14.1 Schema·repository

- empty DB migration, repeated migration no-op
- future migration version fail-fast
- foreign key/status/check/unique constraint
- restart 뒤 catalog/scan/progress/receipt 동일
- DB busy → retryable, corrupt DB → 명시 실패
- parameterized SQL과 path traversal 입력 거부

### 14.2 Catalog

- 기존 valid datapack revision 1 bootstrap
- 같은 hash repeated bootstrap no-op
- same ID/different hash conflict
- invalid/incomplete directory는 READY 0
- create retry same operation → row 1/동일 response
- same key/different payload → 409
- DRAFT/READY selectable, FINALIZING/ERROR nonselectable
- deterministic ordering과 pseudo-item server 저장 0

### 14.3 Scan session

- 신규 DRAFT와 기존 READY append open
- base revision 고정
- same device reconnect returns same OPEN session
- two-device race에서 active session 1
- seal same cutoff repeated mutation 0
- seal different cutoff conflict
- restart 뒤 OPEN/SEALING 복구
- S0 seal 후 READY revision 생성 0

### 14.4 Reading progress·command

- 최초 open만 page 0/node 0
- command 후 restart/open이 같은 stable anchor·offset에서 시작
- same command ID/digest 반복 이동 0, 동일 response
- same command ID/different button/action conflict
- DB commit fault 뒤 in-memory advance 유출 0
- 두 동시 command deterministic serialization
- append revision에서 preserved anchor 복원
- missing anchor를 page 0 success로 가장하지 않음
- viewport 변경과 progress cursor 책임 분리
- datapack revision 변경 시 stale cache 사용 0

### 14.5 HTTP·Coordinator

- auth, malformed JSON, body/ID limit, status code/error schema
- lost-response retry로 draft/session/command 중복 0
- Coordinator create/open operation ID가 retry 동안 동일
- existing/new selection, scan open, reading resume port mapping
- stale session response가 current Coordinator 상태 변경 0
- legacy `/jobs`, `/sessions`, combined server 테스트 회귀
- artifact upload/DeliveryPort HTTP 호출 0

## 15. 완료 기준

- SQLite catalog가 filesystem listing을 대신하는 authoritative control plane
- 기존 valid datapack을 파괴 없이 revision 1로 bootstrap
- draft create와 scan open이 retry/restart에 idempotent
- datapack당 active scan 하나와 same-device recovery 보장
- seal cutoff intent가 durable하되 S1 없이 READY로 가장하지 않음
- `device_id + datapack_id` reading cursor가 server restart 뒤 복원
- navigation command가 receipt/progress와 atomic하며 retry 시 이동 0
- stable page/item anchor를 저장하고 invalid cursor를 명시 실패
- Coordinator operation ID 계약과 HTTP adapters 정합화
- 기존 Scanner session/delivery 계약과 Document Parser navigation 동작 보존
- 전체 Document Parser·device-runtime 회귀 통과
- 미검증 LAPTOP 실제 network 통합 및 Pi/S1/V4 항목을 완료 처리하지 않음

## 16. 비범위

- spread multipart upload와 artifact content validation
- server-side delivery ACK/reject, parser job queue
- incremental fragment schema와 OCR/점역 실행
- datapack append assembly, seal 완료, atomic revision publish
- LAPTOP durable outbox와 upload resume; 이후 동일 저장 계약의 Pi 이식
- audio HTTP stream/cache, LAPTOP STM/camera/audio E2E
- Raspberry Pi systemd·camera/GPIO·자원·전원 차단 검증
- catalog rename/delete/search/pagination/admin UI
- partial finalize 또는 parser 실패 페이지 생략
- PostgreSQL/Redis, horizontal scaling, multi-process writer benchmark
- 실제 배포·systemd·TLS·internet security hardening
- commit/push/PR/release

## 17. 승인 시 변경 범위

승인 시 다음을 구현한다.

- `document-parser/src/document_parser/server/`의 S0 domain/repository/service/migration/API
- 기존 `SessionStore`와 `DatapackSession`을 재사용하는 persistent reading adapter
- `device-runtime` operation ID 보강과 Catalog/Scan/Reading HTTP adapter
- Document Parser 및 Integration V0 단위·restart·HTTP 회귀 테스트
- server schema/API 문서와 S0 구현 보고서

다음은 별도 승인/후속 패킷 없이 구현하지 않는다.

- Server S1 fragment/parser/append/publish
- Scanner V3-B/Server V4 artifact upload·durable outbox
- Document Parser OCR·점역 알고리즘 수정
- LAPTOP STM/camera/audio integration과 Raspberry Pi target 이식
- production dependency 자동 설치나 외부 model download
- commit/push

## 18. 중단 조건

다음이 발생하면 임시 in-memory 성공이나 silent fallback으로 우회하지 않고 보고한다.

- reading command와 progress/receipt를 한 transaction으로 만들려면 navigation semantics를 바꿔야 함
- 기존 datapack ID/page/item ID를 안정 anchor로 사용할 수 없음
- SQLite constraint 없이 process-local lock만으로 중복 scan을 막아야 함
- create/open idempotency를 위해 Scanner나 Coordinator가 datapack DB를 직접 소유해야 함
- S0 seal intent를 구현하려면 fragment/atomic publish를 함께 구현해야만 함
- 기존 `/jobs` 또는 reading session 회귀를 보존할 수 없음
- DB commit 전에 성공 응답/완료 feedback을 보내야만 흐름이 동작함
- S1 없이 새 scan을 READY로 표시해야 Coordinator 테스트가 통과함

중단 시 S0 전체를 완료로 표시하지 않고, 완료된 persistent control-plane 부분과 S1/V4 blocker를
분리해 기록한다.
