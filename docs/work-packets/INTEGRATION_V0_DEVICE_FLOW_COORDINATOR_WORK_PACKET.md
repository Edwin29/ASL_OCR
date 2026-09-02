# Integration V0 — DeviceFlowCoordinator 계약·상태기계 작업 패킷

상태: **구현 및 단위 회귀 검증 완료**
작성일: 2026-08-30
근거 문서: `INTEGRATION_ARCHITECTURE_REASSESSMENT_20260830.md`
참고 commit: `b6244884b86913b41159e6cdd97ab493dc37862f`
후속 패킷: Scanner V3-A, Server S0/S1, LAPTOP Device Connectivity C0,
Scanner V3-B + Server V4, LAPTOP Device Integration, Raspberry Pi Port/Target Validation

## 1. 목표

Book Scanner, Document Parser server, STM 입력과 feedback 출력을 조율하는 상위 장치
애플리케이션의 순수 domain 계약과 결정론적 상태기계를 구현한다.

Integration V0가 답해야 하는 질문은 다음과 같다.

- 현재 버튼 입력을 selection/scanning/reading 중 어디로 전달하는가
- 기존 데이터팩과 `[새 데이터팩 추가]`를 어떻게 구분하는가
- Scanner가 만든 artifact를 언제 전송 대상으로 소유하는가
- 스캔 중 CONFIRM을 받으면 어느 sequence까지 flush하고 seal하는가
- server ACK/finalize 결과를 어떤 상태 전이와 feedback으로 바꾸는가
- 장치 재접속 시 server의 reading progress를 어떻게 사용하도록 요청하는가

이 패킷은 실제 HTTP, SQLite, 카메라, UVDoc, OCR, TTS 또는 serial 통신을 구현하지 않는다.

개발 환경에서는 후속 adapter와 이 Coordinator를 LAPTOP PC에서 실행한다. LAPTOP은 최종
Raspberry Pi의 애플리케이션 호스트 대체물이며, 별도의 domain flow를 사용하지 않는다. 실제 Pi의
systemd·camera/GPIO·자원·전원 차단 검증은 LAPTOP 통합 완료와 분리한다.

## 2. 패키지와 책임 위치

상위 flow는 `book-scanner`나 `document-parser` 내부 domain에 넣지 않는다. 기본 제안은 새
top-level package다.

```text
device-runtime/
  pyproject.toml
  src/asl_device/
    types.py
    protocols.py
    coordinator.py
    catalog.py
    events.py
  tests/unit/
    fakes.py
    test_coordinator.py
    test_catalog.py
    test_types.py
```

이름은 구현 시 저장소 관례에 맞춰 조정할 수 있으나, 다음 의존 방향은 바꾸지 않는다.

```text
STM/HTTP/TTS/Scanner adapters
             ↓
      DeviceFlowCoordinator
             ↓
  pure types + narrow protocols
```

Coordinator core는 OpenCV, Flask, requests/urllib, serial, GPIO, Piper를 import하지 않는다.
b624488 계열의 `device_flow.py`는 behavior reference와 후속 adapter 재사용 대상으로 삼되,
그 I/O 호출을 coordinator core에 복사하지 않는다.

## 3. 확정 상태기계

최소 상태:

- `BOOTING`
- `CONNECTING`
- `SELECTING_DATAPACK`
- `OPENING_SCAN_SESSION`
- `SCANNING`
- `FLUSHING_UPLOADS`
- `FINALIZING_DATAPACK`
- `OPENING_READING_SESSION`
- `READING`
- `RECOVERABLE_ERROR`
- `CANCELLING`
- `STOPPED`

주 경로:

```text
BOOTING
  -> CONNECTING
  -> SELECTING_DATAPACK
  -> OPENING_SCAN_SESSION
  -> SCANNING
  -> FLUSHING_UPLOADS
  -> FINALIZING_DATAPACK
  -> OPENING_READING_SESSION
  -> READING
  -> SELECTING_DATAPACK
```

### 3.1 선택 상태

- catalog를 server source of truth에서 읽음
- ready 기존 데이터팩과 복구 가능한 draft 상태를 구조화해 받음
- UI list 마지막에 `NEW_DATAPACK` pseudo-item을 정확히 한 번 추가
- 데이터팩이 0개여도 `NEW_DATAPACK` 선택 가능
- UP/DOWN은 clamped 이동, LONG은 provisional burst 이동
- highlight 변경 시 title feedback event 생성
- CONFIRM SHORT:
  - 기존 데이터팩: target datapack에 append scan session 요청
  - 새 항목: draft 생성 후 해당 datapack에 scan session 요청

초기 정책에서는 기존 데이터팩을 선택해도 append scan을 거친 뒤 reading으로 이동한다.

### 3.2 Scanning 상태

- Coordinator가 Scanner runtime을 시작
- Scanner semantic guidance를 FeedbackSink로 전달
- artifact-ready event를 DeliveryPort에 전달
- accepted/pending artifact의 lifecycle 결과를 올바른 Scanner operation에 전달
- 같은 scan session의 client sequence는 단조 증가
- delivery 결과가 없는데 새 spread가 성공으로 처리되지 않음

CONFIRM SHORT:

1. 새 Scanner capture/selection을 freeze
2. 현재까지 발급한 마지막 sequence `N`을 cutoff로 고정
3. 같은 CONFIRM 반복 입력은 동일 cutoff를 반환하며 새 finalize를 만들지 않음
4. `FLUSHING_UPLOADS`로 전환

### 3.3 Flush와 finalize

- DeliveryPort에 `flush_through(N)` 요청
- `N` 이하가 durable ACK되기 전 seal 호출 금지
- retryable remote failure는 같은 artifact retry를 기다림
- terminal reject가 있으면 자동 seal/reading 진입 금지
- flush 성공 후 `seal(scan_session_id, through_sequence=N)` 정확히 한 번 요청
- server가 READY를 반환할 때까지 `FINALIZING_DATAPACK`
- FINALIZING 중 새 Scanner capture 없음
- 완성된 datapack revision/ID를 받은 뒤에만 reading session 생성

### 3.4 Reading 상태

- `device_id`, `datapack_id`, viewport 정보로 server reading session 생성
- server가 반환한 persistent cursor를 그대로 authoritative current state로 사용
- Coordinator가 별도의 local cursor를 진실 원천으로 유지하지 않음
- CONFIRM SHORT는 current-item replay command로 reading port에 전달
- CONFIRM LONG은 reading session을 종료/분리하고 catalog를 새로 읽어 선택 상태로 복귀
- UP/DOWN/LEFT/RIGHT/PAGE commands는 reading port에만 전달
- command에는 caller-generated event/command identity를 전달할 수 있는 계약 포함

## 4. Domain 타입

최소 immutable 타입:

- `DeviceFlowState`
- `DeviceId`
- `DatapackId`, `DatapackRevision`
- `DatapackStatus`: `DRAFT`, `FINALIZING`, `READY`, `ERROR`
- `CatalogEntry`
- `CatalogChoice`: existing 또는 `NEW_DATAPACK`
- `ScanSessionId`, `ScanSessionStatus`
- `ClientSpreadSequence`
- `ScannerArtifactReady`
- `DeliveryReceipt`, `DeliveryStatus`
- `FlushResult`
- `FinalizeResult`
- `ReadingSessionId`
- `DeviceInputEvent`
- `CoordinatorEvent`
- `FeedbackCode`

wire JSON이 아니라 domain 타입이다. HTTP serializer는 후속 adapter가 책임진다.

`DeviceInputEvent`는 최소 다음을 보존한다.

- unique event ID
- button/lever 종류
- SHORT/LONG action
- monotonic timestamp
- optional hardware sequence

중복 event ID를 같은 상태에서 두 번 적용하지 않는 정책을 테스트한다.

## 5. Protocol

### 5.1 외부 입력·출력

```text
HardwareInput.events()
FeedbackSink.emit(feedback_event)
Clock.monotonic()
```

### 5.2 Server-facing ports

```text
CatalogPort.list_datapacks(device_id)
CatalogPort.create_datapack(device_id)
ScanSessionPort.open(device_id, datapack_id)
ScanSessionPort.seal(scan_session_id, through_sequence)
ScanSessionPort.get_status(scan_session_id)
ReadingSessionPort.open(device_id, datapack_id, viewport_size)
ReadingSessionPort.get_current(reading_session_id)
ReadingSessionPort.send_command(reading_session_id, command_id, button, action)
```

### 5.3 Scanner와 delivery ports

```text
ScannerRuntime.start(scan_session_context)
ScannerRuntime.poll()
ScannerRuntime.freeze()
ScannerRuntime.cancel()
ScannerRuntime.apply_delivery_update(artifact_id, delivery_update)

DeliveryPort.queue(scan_session_id, sequence, spread_artifact)
DeliveryPort.flush_through(scan_session_id, sequence)
DeliveryPort.pending_status(scan_session_id)
```

V0 fake는 위 port를 동기 또는 수동 완료 방식으로 제어할 수 있다. 실제 background worker,
HTTP timeout, SQLite outbox 구현은 후속이다.

## 6. Event와 feedback

최소 Coordinator event:

- `CATALOG_LOADED`
- `CATALOG_HIGHLIGHT_CHANGED`
- `DATAPACK_CREATED`
- `SCAN_SESSION_OPENED`
- `SCANNER_STARTED`
- `SPREAD_QUEUED`
- `SPREAD_DELIVERY_CONFIRMED`
- `SCAN_STOP_REQUESTED`
- `UPLOAD_FLUSH_COMPLETED`
- `DATAPACK_FINALIZING`
- `DATAPACK_READY`
- `READING_SESSION_OPENED`
- `READING_RESUMED`
- `RETURNED_TO_SELECTION`
- `RECOVERABLE_ERROR`
- `FATAL_ERROR`

Feedback는 임의 문장보다 semantic code와 parameter를 사용한다.

- `SPEAK_CATALOG_TITLE`
- `CONFIRM_SELECTION`
- `SCAN_STARTED`
- Scanner physical guidance passthrough
- `SPREAD_SENT`
- `SCAN_STOPPING`
- `FINALIZING`
- `DATAPACK_SAVED`
- `SERVER_RETRYING`
- `PARSER_REJECTED`
- `READING_RESUMED`

실제 한국어 문구, beep 파일, Piper/remote audio 선택은 adapter 책임이다. 같은 상태 전이에 feedback
event가 중복 발생하지 않아야 한다.

## 7. 실패·재시도 계약

### 7.1 Selection/open 실패

- server unavailable은 `RECOVERABLE_ERROR`
- 재시도 시 catalog를 새로 읽음
- 이전 highlight가 같은 datapack ID로 존재하면 복원 가능, index만 저장하지 않음
- unknown/deleted datapack은 선택 화면으로 돌아감

### 7.2 Scanning 실패

- Scanner local retry는 high-level state를 종료하지 않음
- delivery remote retry는 새 capture 완료로 바꾸지 않음
- outbox capacity/remote unavailable로 새 artifact를 안전하게 소유할 수 없으면 Scanner를 pause/freeze
- parser terminal reject는 해당 artifact를 accepted로 표시하지 않음

### 7.3 Flush/finalize 실패

- rejected sequence가 있으면 seal 성공으로 가장하지 않음
- finalize timeout은 상태 조회를 재시도하며 새 seal 요청을 중복 생성하지 않음
- server ERROR이면 reading으로 진입하지 않음
- 기존 ready revision이 있더라도 이번 append 실패를 성공으로 보고하지 않음

### 7.4 Stale callback

모든 async 결과는 operation/session identity를 가진다. 이전 selection, scan session, artifact 또는
reading session의 늦은 결과가 현재 상태를 변경하지 못해야 한다.

## 8. 테스트 행렬

### 8.1 Catalog와 선택

- catalog 0개에서도 `NEW_DATAPACK` 한 항목 존재
- catalog N개이면 기존 N개 + new 한 개
- UP/DOWN clamp와 LONG burst
- highlight 변경 때만 title feedback
- 기존 선택은 create 없이 append scan open
- new 선택은 create 1회 후 scan open 1회
- 반복 CONFIRM이 scan session을 두 개 만들지 않음

### 8.2 Scan 시작·artifact routing

- scan session open 성공 뒤에만 Scanner start
- artifact sequence 단조 증가
- artifact ready가 정확히 한 번 delivery queue로 전달
- stale artifact event 무시
- delivery ACK가 대응 artifact에만 적용
- local guidance가 server command로 잘못 전달되지 않음

### 8.3 Confirm/flush/seal

- SCANNING 중 CONFIRM에서 Scanner freeze가 먼저 호출됨
- cutoff `N` 고정 뒤 새 sequence 발급 0
- pending이 있으면 seal 0
- `N` 이하 ACK 후 seal 1회
- CONFIRM 반복/flush callback 반복에도 seal 1회
- terminal reject가 있으면 finalize/reading 0
- finalize READY 뒤 reading open 1회

### 8.4 Reading

- server returned cursor에서 시작
- Coordinator local default page 0으로 덮어쓰지 않음
- CONFIRM SHORT가 reading replay command로 전달
- CONFIRM LONG이 server navigation으로 전달되지 않고 selection 복귀
- navigation command ID 반복 응답에서도 state transition 중복 없음
- 다른 datapack 선택 시 새 reading session 사용

### 8.5 Cancel과 race

- 각 active 상태에서 shutdown/cancel terminal behavior
- freeze와 artifact-ready race에서 cutoff owner 하나
- finalize READY와 user return/cancel race에서 stale callback 차단
- 이전 scan session callback이 새 scan session을 완료시키지 않음
- feedback exception이 domain state를 성공으로 바꾸지 않음

## 9. 완료 기준

- 별도 coordinator package와 immutable domain 타입 구현
- core에서 HTTP/serial/OpenCV/GPU/TTS import 0
- selection → append/new scan → flush → finalize → restored reading 결정론적 test 통과
- 상태별 CONFIRM SHORT/LONG routing test 통과
- Scanner와 server를 fake로 교체 가능
- pending spread가 있는데 seal 또는 reading 진입 0
- server READY 전 `DATAPACK_SAVED`/reading 진입 0
- reading 시작 시 server cursor 사용
- stale callback과 반복 command의 중복 state mutation 0
- 현재 `book-scanner` 및 `document-parser` 기존 unit test 회귀 없음
- 실제 I/O를 실행하지 않았음을 구현 보고서에 명시

## 10. 비범위

- b624488 branch와 Book Scanner branch의 실제 merge/rebase
- 실제 STM serial/Bluetooth/GPIO
- 실제 camera와 Book Scanner V3-A 구현
- 실제 HTTP client/server endpoint
- SQLite schema와 migration
- durable outbox와 idempotent upload
- Document Parser OCR·점역·TTS 실행
- incremental datapack page fragment와 atomic revision
- remote audio download/stream
- 실제 beep/TTS 문구 및 음향 장치
- LAPTOP 기반 실제 adapter/E2E 통합
- Raspberry Pi 자원·systemd·재부팅 검증

비범위 항목은 V0 완료로 기록하지 않는다.

## 11. 중단 조건

- Coordinator 구현을 위해 OpenCV/OCR/Flask/serial을 core에 직접 import해야 함
- server DB 상태를 Coordinator local memory가 authoritative하게 복제해야 함
- Book Scanner가 datapack 또는 reading session을 직접 소유해야 함
- ACK되지 않은 artifact를 완료로 간주해야만 상태기계가 진행됨
- repeated CONFIRM이 복수 scan session/seal을 생성함
- stale callback을 operation identity 없이 현재 작업에 적용해야 함
- b624488 code를 현재 branch 위에 통째로 덮어써야만 진행 가능함
- 실제 server contract를 V0 fake 테스트 편의를 위해 확정한 것처럼 주장해야 함

위 조건이 생기면 구현 범위를 확대하지 않고 계약 충돌과 필요한 후속 결정을 보고한다.

## 12. 구현 결과 (2026-08-30)

- 새 top-level `device-runtime` package와 `asl_device` namespace를 추가했다.
- immutable domain value, port protocol, catalog projection, coordinator event와
  poll-driven `DeviceFlowCoordinator`를 구현했다.
- 기존/신규 datapack 선택, append scan open, artifact sequence 부여, delivery ACK/reject,
  freeze → flush → seal → READY → reading cursor 복구 흐름을 구현했다.
- 동일 input/scanner event, stale delivery/finalize callback을 무시한다.
- delivery queue 일시 장애 시 이미 선별된 artifact와 logical sequence를 보존하고 같은
  payload를 재시도한다. 재촬영으로 page hole이나 duplicate를 만들지 않는다.
- core에는 HTTP, serial, OpenCV, OCR, GPU, TTS 구현 의존성이 없다.
- 실제 HTTP/SQLite/camera/UVDoc/OCR/TTS/STM adapter는 구현하거나 실행하지 않았다.

검증 결과와 미검증 사항은 `INTEGRATION_V0_IMPLEMENTATION_REPORT.md`에 기록한다.
