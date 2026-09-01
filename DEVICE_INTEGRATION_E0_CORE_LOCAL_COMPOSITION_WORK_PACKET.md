# Device Integration E0-Core — Local Composition 작업 패킷

상태: **승인됨 · 핵심 local composition 구현 및 회귀 검증 완료**
작성일: 2026-09-01
구현 결과: `DEVICE_INTEGRATION_E0_CORE_IMPLEMENTATION_REPORT.md`
실행 기준 환경: 현재 개발용 데스크톱의 로컬 Windows 환경
선행 조건: Scanner V2/V3-A.5, Integration V0 Coordinator, Server S0/S1, Device Connectivity C0,
Server V4, Scanner V3-B
후속 조건: Device Integration E0-B — Laptop Acceptance, 외부 endpoint/network, Raspberry Pi 이식

## 1. 결정과 목표

이번 패킷에서 `LAPTOP`은 특정 물리 Laptop이 아니라 Raspberry Pi를 대신해 Device application을
실행하는 **device-host 역할**을 뜻한다. E0-Core 구현과 완료 판정에는 별도 Laptop 연결, 원격 접속,
실제 STM 또는 실제 오디오 장치가 필요하지 않다.

현재 개발용 데스크톱에서 다음 제품 경계를 한 프로세스로 연결한다.

```text
local control event
  -> DeviceFlowCoordinator
  -> C0 ONLINE gate
  -> S0 catalog / scan session
  -> Book Scanner SampledFrameEngine bridge
  -> Scanner V2 immutable artifact
  -> V3-B durable outbox
  -> Server V4 / S1 durable ACK
  -> Scanner delivery confirmation
  -> flush / S0 seal / finalization
  -> reading session + semantic feedback trace
```

핵심 완료 조건은 다음과 같다.

1. 기존 Scanner, Coordinator, C0, S0, V3-B, V4/S1 계약을 우회하지 않는 실행 가능한 local
   composition이 존재한다.
2. 유효한 V4 receipt 전에는 `SPREAD_SENT`가 발생하지 않고, durable flush 전에는 seal을 요청하지
   않으며, READY 전에는 `DATAPACK_SAVED`가 발생하지 않는다.
3. 실제 HTTP/SQLite local loopback에서 한 artifact가 한 sequence로 queue·ACK·flush·seal된다.
4. 실제 Laptop과 주변 장치가 없어도 deterministic replay와 local control/feedback adapter로 위 흐름을
   재현할 수 있다.

## 2. 핵심 기능과 후속 검증 분리

### 2.1 이번 E0-Core 범위

- `SampledFrameEngine`을 `asl_device.protocols.ScannerRuntime`으로 노출하는 bridge
- Scanner event/domain type을 Device Runtime type으로 보수적으로 변환
- Scanner artifact root와 V3-B `artifact_root`의 단일 소유 경로 구성
- C0, S0 HTTP adapters, V3-B, Coordinator, Scanner bridge의 composition root
- typed application config와 시작 전 path/identity/config 일관성 검증
- poll-driven `DeviceApplication`과 명시적 start/input/poll/stop lifecycle
- 테스트 가능한 local control source와 JSON/text semantic feedback sink
- replay/image-sequence profile을 사용하는 deterministic local 실행
- 선택적인 PC camera profile 구성 경로
- 실제 local Server S0/C0/V4/S1 HTTP + SQLite E2E
- ACK, feedback, flush, seal의 핵심 순서 검증
- 대표적인 response-loss retry 한 경계와 graceful shutdown 검증
- 실행 문서와 구현 보고서

### 2.2 별도 Device Integration E0-B — Laptop Acceptance 범위

- 별도 물리 Laptop 준비와 원격 접속/배포
- 실제 USB/내장 camera의 해상도, autofocus, exposure와 장시간 capture
- 실제 STM serial protocol, 버튼 debouncing, reconnect와 port discovery
- 실제 beep speaker와 TTS/audio playback 장치
- 별도 network Laptop에서 HTTPS tunnel을 거친 desktop bench server physical smoke run
- Windows service/Task Scheduler 패키징
- 실제 UVDoc/Paddle CPU/GPU 성능, RSS, 발열과 전원 설정
- 외부 Server endpoint, TLS, DNS, VPN/tunnel

### 2.3 후속 hardening 범위

- 전체 Coordinator active scan/session의 process restart checkpoint
- queue 이전 orphan Scanner artifact 자동 adoption
- 다중 application instance lock/leader election
- generalized device disk quota, retention과 관리자 GC
- accepted M1 identity bank 영속화
- exhaustive signal/power-loss/network chaos matrix
- metrics backend, remote log shipping과 운영 dashboard

이 항목들은 E0-Core의 선행 조건으로 묶지 않는다. 데이터 손실, false ACK와 중복 server side effect를
막는 기존 불변식은 그대로 유지한다.

## 3. 현재 구현과 닫아야 할 공백

이미 존재하는 구현:

- `book-scanner`의 `SampledFrameEngine`, replay/live PC camera source, V2 artifact store
- Scanner V3-A.5의 pending identity, delivery confirmed/rejected callback과 page-change gate
- `device-runtime`의 `DeviceFlowCoordinator`와 순수 port 계약
- S0 catalog/scan/reading HTTP adapters
- C0 authenticated ONLINE supervisor
- V3-B single-sender durable outbox와 Server V4 client
- Server S0/S1/C0/V4 combined application과 SQLite persistence

현재 없는 구현:

- Book Scanner event를 `ScannerEvent`로 변환하는 실제 `ScannerRuntime` adapter
- scan session마다 Scanner engine을 안전하게 생성·종료하는 factory
- C0/S0/V3-B/Scanner/Coordinator를 함께 만드는 composition root
- Coordinator를 반복 poll하고 local input을 전달하는 application shell
- 실제/가짜 STM 대신 사용할 최소 local control boundary
- semantic feedback를 관찰할 local sink
- 한 프로세스 Device flow와 actual local server를 묶는 E0 통합 테스트

E0-Core는 Scanner 영상 알고리즘, Server schema 또는 OCR/점역/TTS 변환 책임을 다시 구현하지 않는다.

## 4. 책임과 dependency 방향

### 4.1 Book Scanner

- camera/replay frame 획득
- stable candidate, M1 identity와 page-change 판단
- seam-conservative + UVDoc artifact 생성
- immutable V2 bundle commit
- delivery 상태에 따른 pending identity accept/release

`book-scanner`는 `asl_device`를 import하지 않는다. 독립 Scanner domain을 유지한다.

### 4.2 Device Runtime outer adapter

- `SampledFrameEngine` 생성 factory 호출
- Book Scanner event/type을 Device Runtime event/type으로 변환
- Coordinator가 준 delivery update를 Scanner engine callback으로 전달
- freeze/cancel/close와 camera resource 수명주기 조정
- S0/C0/V3-B와 application composition 소유

outermost `device-runtime`만 `book_scanner` public API를 import한다. Server package를 Device application
production code에서 import하지 않는다.

### 4.3 Server

- C0 presence, S0 catalog/session/reading
- V4 durable bundle acceptance
- S1 parser/finalize/publish

E0-Core local E2E test는 Server application을 test fixture로 실행할 수 있지만 Device production
composition이 Server 내부 객체를 직접 호출하면 안 된다.

## 5. ScannerRuntime bridge 계약

권장 파일: `device-runtime/src/asl_device/adapters/book_scanner_runtime.py`

### 5.1 Engine factory

Scanner engine의 `session_id`와 `data_pack_id`는 생성 시 고정되므로 bridge는 scan session마다 새 engine을
factory로 생성한다.

```python
engine = engine_factory.create(
    session_id=scan_session.scan_session_id.value,
    datapack_id=scan_session.datapack_id.value,
)
```

- 동시에 engine 하나만 소유한다.
- `start()` 중 다른 session이 active이면 fatal error다.
- 이전 engine은 camera와 worker를 닫은 뒤에만 교체한다.
- engine construction 실패는 Device `FatalPortError` 또는 명확한 recoverable error로 변환한다.

### 5.2 Scanner event mapping

| Book Scanner event | Device Scanner event | 규칙 |
|---|---|---|
| `ARTIFACT_READY` | `ARTIFACT_READY` | artifact/session/spread/frame/manifest identity 전수 변환 |
| `GUIDANCE_REQUESTED` | `GUIDANCE` | `ReadinessReason.value`를 code로 보존 |
| `SESSION_ERROR` | `FATAL` | reason 누락 없이 active flow 중단 |
| 기타 diagnostics/state event | Device event 없음 | optional local diagnostic trace만 허용 |

Artifact 변환 시 다음을 검증한다.

- event session이 active `ScanSessionRef`와 일치
- left/right가 동일 source frame과 spread에 속함
- manifest path와 SHA-256이 `SpreadArtifactRef`와 일치
- manifest가 configured artifact root 바로 아래 `{artifact_id}/manifest.json`에 위치
- identity mismatch event는 조용히 queue하지 않고 fatal로 중단

### 5.3 Delivery update mapping

| Device delivery status | Scanner engine callback |
|---|---|
| `QUEUED`, `SENDING` | `delivery_queued(artifact_id)` |
| `RETRYING` | `delivery_retrying(artifact_id)` |
| `ACKED` | `delivery_confirmed(artifact_id, receipt_id)` |
| `REJECTED` | `delivery_rejected(artifact_id, reason)` |

- ACK에 receipt가 없으면 callback하지 않고 fatal이다.
- 다른 artifact/session/sequence update는 Scanner state를 바꾸지 않는다.
- 같은 terminal update가 반복돼도 engine terminal callback side effect는 최대 한 번이다.
- V3-B가 ACK commit 뒤 artifact를 제거해도 Scanner callback은 artifact bytes를 다시 읽지 않아야 한다.

### 5.4 Freeze와 cancel

Coordinator `freeze()`의 의미는 새 artifact 생성을 중지하면서 이미 outbox가 소유한 artifact delivery는
계속 진행시키는 것이다.

- freeze 이후 engine의 새 frame processing/poll을 중지한다.
- pending artifact가 없으면 camera를 즉시 중지하고 engine을 닫는다.
- pending artifact가 있으면 terminal delivery update를 먼저 적용한 뒤 engine cancel/close로 camera를
  해제한다.
- freeze가 queued artifact나 V3-B source directory를 삭제하면 안 된다.
- `cancel()`은 Scanner 계산과 camera를 종료하지만 durable outbox row를 취소하거나 삭제하지 않는다.

필요하면 이 semantics를 bridge 내부 상태로 구현한다. `SampledFrameEngine` 자체에 범용 pause/resume 상태나
새 persistence layer를 추가하지 않는다.

## 6. Scanner local composition

권장 파일: `book-scanner/src/book_scanner/video/runtime_composition.py`

factory는 현재 public 구성 요소를 조합한다.

- `OpenCVCameraSource`, `VideoFileCameraSource` 또는 `ImageSequenceCameraSource`
- `OpenCVCandidateAnalyzer`
- `SeamUVDocSpreadPreparer`
- `FilesystemArtifactStore`
- `SampledFrameEngine`
- V3-A.5 identity/page-change components
- default M1 사용 시 explicit hash-pinned local Paddle backend

E0-Core automated acceptance profile은 deterministic replay/image sequence를 사용한다. 선택적 PC camera
profile은 구성·start/stop 경로까지 제공하되 실제 camera 성공을 자동 완료 기준으로 삼지 않는다.

구성 규칙:

- Scanner `ready_root == DeviceDeliveryConfig.artifact_root`
- staging root와 ready root는 같은 filesystem
- outbox DB는 ready root 밖
- UVDoc runtime/checkpoint와 M1 model은 explicit local path
- model 자동 다운로드와 silent fallback 금지
- M1 asset 누락 시 `LEGACY_VISUAL`로 자동 전환하지 않고 startup fail-fast
- replay input은 source hash 또는 테스트 fixture identity를 기록

## 7. Device application shell

권장 파일:

- `device-runtime/src/asl_device/application.py`
- `device-runtime/src/asl_device/app_config.py`
- `device-runtime/src/asl_device/local_composition.py`
- `device-runtime/src/asl_device/__main__.py`

### 7.1 Lifecycle

```text
load + validate config
  -> construct adapters
  -> coordinator.start()
  -> while running:
       drain submitted local input
       coordinator.handle_input(...)
       coordinator.poll()
       bounded poll wait
  -> coordinator.stop()
  -> scanner close / connectivity stop
```

- application loop는 하나의 thread에서 Coordinator를 호출한다.
- input producer가 있더라도 Coordinator mutation은 application loop에서만 수행한다.
- poll interval은 bounded positive config다.
- Ctrl+C/termination은 graceful `stop()`을 한 번 호출한다.
- start 도중 일부 adapter가 실패하면 이미 열린 resource를 역순으로 닫는다.
- feedback 실패는 기존 Coordinator 계약처럼 성공한 ACK/server state를 되돌리지 않는다.

### 7.2 Local control boundary

실제 STM 대신 최소 `ControlSource`/input queue를 둔다.

- 자동 E2E에서는 deterministic scripted input을 사용한다.
- local CLI는 keyboard/line command를 `DeviceInputEvent`로 변환할 수 있다.
- event ID는 process 내에서 stable unique해야 한다.
- 지원 명령은 기존 `DeviceControl`과 `InputAction`만 사용한다.
- STM frame protocol, reconnect와 debounce는 Device Integration E0-B — Laptop Acceptance에서 구현한다.

### 7.3 Local feedback boundary

E0-Core는 semantic feedback가 정확한 시점에 발생하는지를 검증한다.

- `FeedbackEvent`를 bounded JSON line 또는 in-memory trace로 기록
- API key, full manifest path, image bytes를 출력하지 않음
- `SPREAD_SENT`는 valid V4 ACK 이후만
- `DATAPACK_SAVED`는 S0/S1 READY 이후만
- physical beep pattern, TTS voice와 speaker playback은 별도 Laptop adapter 범위

## 8. E0 app config schema v1

하나의 top-level config가 기존 config를 참조하며 secret을 복제하지 않는다.

```toml
schema_version = 1
connectivity_config = "device-connectivity.toml"
viewport_size = 40
poll_interval_ms = 50

[delivery]
outbox_db_path = "state/delivery.sqlite3"
artifact_root = "state/artifacts/ready"

[scanner]
profile = "replay" # replay | image_sequence | pc_camera
staging_root = "state/artifacts/staging"
ready_root = "state/artifacts/ready"
uvdoc_runtime_path = "models/uvdoc/runtime"
uvdoc_checkpoint_path = "models/uvdoc/checkpoint.pth"
uvdoc_device = "auto"
m1_model_dir = "models/paddle/page-number"
m1_model_manifest = "models/paddle/page-number-manifest.json"

[local_io]
feedback = "jsonl"
```

정확한 필드명은 구현 중 기존 config API에 맞게 조정할 수 있지만 다음 원칙은 고정한다.

- 모든 relative path는 top-level config directory 기준
- unknown field 거부
- API key는 기존 C0 `api_key_file`만 사용
- device ID와 server origin은 C0 config가 단일 authority
- Scanner ready root와 delivery artifact root가 다르면 startup 거부
- production 의미를 가진 환경변수 override를 새로 대량 추가하지 않음
- config 또는 exception에 API key 값을 포함하지 않음

## 9. S0/C0/V3-B composition

`local_composition`은 같은 `DeviceConnectivityConfig` 인스턴스에서 다음을 만든다.

- `DeviceConnectivitySupervisor`
- API key 하나를 공유하는 `S0HttpClient`
- `S0CatalogHttpAdapter`
- `S0ScanHttpAdapter`
- `S0ReadingHttpAdapter`
- `DurableDeliveryPort`
- Book Scanner runtime bridge
- local feedback sink
- `DeviceFlowCoordinator`
- `DeviceApplication`

S0와 V4 client가 각자 URL이나 device ID를 다시 해석하지 않게 한다. production composition은 local
Server Python package를 import하지 않고 HTTP만 사용한다.

## 10. 안전성 및 순서 불변식

### 10.1 Artifact ownership

```text
Scanner private staging
  -> Scanner atomic ready commit
  -> Coordinator assigns one sequence
  -> V3-B queue commit owns delivery retry
  -> valid server ACK commit
  -> V3-B confined source cleanup
```

- queue 실패 시 같은 Scanner artifact와 sequence를 재사용한다.
- application shell이 artifact를 직접 복사·삭제하지 않는다.
- Scanner cancel/close가 durable outbox source를 삭제하지 않는다.
- 같은 Scanner event가 재관찰돼도 Coordinator event ID dedup과 outbox unique identity를 우회하지 않는다.

### 10.2 Feedback ordering

```text
artifact ready != queued != sent != datapack saved
```

- `SPREAD_QUEUED`: local outbox queue 성공
- `SPREAD_SENT`: valid server receipt가 local ACK로 확정
- `SCAN_STOPPING`: 사용자 stop intent
- `FINALIZING`: 모든 cutoff sequence ACK 후 seal 요청
- `DATAPACK_SAVED`: server finalization READY

HTTP request completion, C0 ONLINE, Scanner processing 완료를 ACK나 saved feedback로 사용하지 않는다.

### 10.3 Failure boundary

- C0 offline 전에 catalog/scan 호출 0
- recoverable C0/S0/V4 오류는 기존 Coordinator recovery 의미 유지
- Scanner fatal은 active flow를 중단하고 camera resource를 닫음
- feedback sink 실패는 best-effort diagnostic이며 domain state를 변경하지 않음
- malformed cross-package identity는 recoverable retry로 숨기지 않고 fatal
- E0-Core는 whole-process restart 뒤 active Coordinator flow가 자동 복원된다고 주장하지 않음

## 11. Local E2E acceptance scenario

실제 Laptop 없이 현재 개발용 데스크톱에서 다음을 자동 검증한다.

```text
actual local HTTP server + temporary SQLite
  -> DeviceApplication start
  -> C0 authenticated ONLINE
  -> scripted catalog selection/new scan
  -> deterministic Scanner engine/replay artifact event
  -> V3-B SQLite queue
  -> actual V4 multipart upload
  -> S1 durable receipt
  -> Scanner delivery_confirmed exactly once
  -> SPREAD_SENT exactly once
  -> scripted scan stop
  -> V3-B flush through cutoff
  -> S0 seal intent
  -> deterministic test parser/finalizer READY
  -> DATAPACK_SAVED + reading session open
  -> graceful application stop and camera release
```

Server parser/finalizer는 deterministic test implementation을 주입할 수 있다. 실제 PaddleOCR-VL, Piper,
STM, speaker는 이 transport/orchestration 완료 판정에 필요하지 않다.

대표 uncertainty scenario 하나를 추가한다.

- Server V4가 commit한 뒤 첫 response를 client가 잃음
- 같은 sequence/key/digest로 retry
- S1 spread 1개, left/right fragment 2개
- Scanner `delivery_confirmed`, `SPREAD_SENT`, seal intent 각각 1회

## 12. 구현 단계

### Phase 0 — Config와 contract fixture

- E0-Core와 Device Integration E0-B — Laptop Acceptance 범위 동결
- app config schema와 path authority 고정
- Scanner/Device type conversion fixture 작성
- 기존 public protocol signature 변화 없음 확인

### Phase 1 — Scanner engine factory와 bridge

- scan-session-scoped engine factory
- event/artifact type mapping
- delivery update mapping과 terminal dedup
- freeze/cancel/close resource lifecycle
- replay/live camera profile construction

### Phase 2 — Application shell과 local I/O

- single-threaded coordinator drive loop
- submitted/scripted local input
- semantic feedback trace
- graceful startup rollback과 shutdown

### Phase 3 — Full local composition

- C0 config 단일 authority
- S0 clients, V3-B, Scanner bridge, Coordinator wiring
- config/path/model fail-fast
- `python -m asl_device --config ...` 형태의 실행 진입점

### Phase 4 — Actual local E2E

- actual S0/C0/V4/S1 HTTP/SQLite fixture
- deterministic Scanner flow
- ACK/feedback/flush/seal/finalization 순서
- response-loss same-key retry와 중복 0
- resource cleanup

### Phase 5 — Regression과 handoff

- 세 프로젝트 전체 회귀
- local runbook와 sample config
- 구현 보고서
- handoff의 다음 우선순위를 Device Integration E0-B — Laptop Acceptance로 갱신

## 13. 테스트 행렬

### 13.1 Scanner bridge

- active scan session으로 engine 1개 생성
- 다른 session 중복 start 거부
- ARTIFACT_READY identity/type 정확한 변환
- mismatched session/artifact/manifest fatal
- guidance와 fatal mapping
- diagnostics event가 artifact event로 오인되지 않음
- QUEUED/RETRYING/ACKED/REJECTED callback mapping
- receipt 없는 ACK 거부
- terminal callback 반복 side effect 0
- freeze 뒤 새 artifact 0, pending terminal update 허용
- cancel/close 뒤 camera resource release
- cancel이 outbox-owned artifact를 삭제하지 않음

### 13.2 Config/composition

- relative path config-root 기준 resolve
- unknown field와 invalid profile 거부
- C0 device ID/origin/API key 단일 authority
- Scanner ready root와 V3-B artifact root 불일치 거부
- staging/ready filesystem 불일치 거부
- M1/UVDoc asset 누락 fail-fast, silent fallback 0
- API key가 repr/error/feedback에 노출되지 않음

### 13.3 Application

- ONLINE 전 catalog 요청 0
- input event dedup 유지
- start/input/poll/stop ordering
- poll 한 cycle이 unbounded work를 수행하지 않음
- partial construction/start failure resource rollback
- Ctrl+C-equivalent stop idempotency
- feedback sink failure가 Coordinator/server state를 되돌리지 않음

### 13.4 Local E2E

- C0 ONLINE → catalog → scan session → Scanner start
- artifact 1개 → outbox row 1개 → V4/S1 receipt
- ACK 전 `SPREAD_SENT` 0
- valid ACK 뒤 Scanner confirmation과 `SPREAD_SENT` 각각 1
- stop cutoff 전 새 Scanner artifact 0
- 모든 sequence ACK 전 seal 0
- flush 뒤 seal intent 1
- READY 전 `DATAPACK_SAVED` 0, READY 뒤 1
- reading session open
- response loss retry 뒤 S1 spread/fragment 중복 0
- stop 뒤 camera/connectivity resource release

### 13.5 Regression

- Book Scanner 현재 기준 `288 passed`
- Device Runtime 구현 후 기준 `69 passed`
- Document Parser 현재 기준 `571 passed, 4 skipped`
- C0, S0/S1, V4와 V3-B 집중 회귀
- Scanner V3-A.5 single pending/ACK identity 의미 변화 0

## 14. 완료 기준

- `python -m asl_device --config <path>` 또는 동등한 단일 entrypoint가 current desktop에서 구성된다.
- 별도 Laptop 없이 deterministic replay profile로 전체 Device application 흐름을 실행할 수 있다.
- Scanner engine과 Coordinator 사이에 fake가 아닌 concrete bridge가 있다.
- C0 ONLINE gate 뒤에만 S0 flow가 시작된다.
- Scanner V2 artifact가 V3-B queue와 actual V4/S1를 거쳐 valid ACK된다.
- ACK 전 false `SPREAD_SENT`, flush 전 seal, READY 전 `DATAPACK_SAVED`가 각각 0이다.
- response loss retry가 새 capture/sequence와 server fragment 중복을 만들지 않는다.
- freeze/stop 뒤 새 capture가 없고 camera/worker/connectivity resource가 정리된다.
- 세 프로젝트 회귀와 actual local E2E가 통과한다.
- 실제 Laptop, STM, audio, external network와 whole-process active-session recovery를 완료로 주장하지 않는다.

## 15. 예상 변경 파일

주 대상:

- `device-runtime/src/asl_device/app_config.py`
- `device-runtime/src/asl_device/application.py`
- `device-runtime/src/asl_device/local_composition.py`
- `device-runtime/src/asl_device/__main__.py`
- `device-runtime/src/asl_device/adapters/book_scanner_runtime.py`
- `device-runtime/src/asl_device/adapters/local_controls.py`
- `device-runtime/src/asl_device/adapters/local_feedback.py`
- `book-scanner/src/book_scanner/video/runtime_composition.py`
- `device-runtime/tests/unit/test_app_config.py`
- `device-runtime/tests/unit/test_application.py`
- `device-runtime/tests/unit/test_book_scanner_runtime.py`
- `device-runtime/tests/integration/test_e0_local_composition.py`
- `device-runtime/docs/device-integration-e0-core.md`
- `DEVICE_INTEGRATION_E0_CORE_IMPLEMENTATION_REPORT.md`

필요할 때만 최소 변경:

- `device-runtime/pyproject.toml`
- `device-runtime/src/asl_device/protocols.py`
- `device-runtime/src/asl_device/coordinator.py`
- `device-runtime/src/asl_device/__init__.py`
- `book-scanner/src/book_scanner/video/engine.py`
- `book-scanner/src/book_scanner/video/__init__.py`
- local Server test composition fixture
- `PROJECT_HANDOFF_20260831.md`
- 각 프로젝트 README

Server S0/S1/C0/V4 production 계약과 schema 변경은 기본 범위가 아니다.

## 16. 승인 경계

승인 시 수행:

- Scanner engine factory와 concrete `ScannerRuntime` bridge 구현
- typed E0 app config와 fail-fast validation
- local controls/feedback와 poll-driven application shell
- C0/S0/V3-B/Scanner/Coordinator composition
- deterministic replay 기반 actual local HTTP/SQLite E2E
- representative response-loss test
- 세 프로젝트 회귀, 문서·보고서·handoff 갱신

별도 승인 없이는 수행하지 않음:

- 실제 Laptop 연결, 원격 실행 또는 파일 배포
- 실제 STM serial/GPIO protocol 구현
- 실제 beep/TTS/audio playback 구현
- 외부 endpoint/TLS/VPN/LAN validation
- Windows service 또는 Raspberry Pi systemd
- 전체 active scan process restart persistence
- V3-B/C0/V4 운영 hardening 확장
- Scanner threshold/model 교체 또는 자동 다운로드
- Server production schema/API 확장
- 새 대형 dependency 설치
- commit/push/PR

## 17. 중단 조건

다음 상황에서는 범위를 조용히 넓히지 않고 보고한다.

- concrete bridge가 Scanner artifact identity를 손실 없이 변환할 수 없음
- freeze/cancel 과정에서 outbox-owned artifact를 삭제해야만 현재 engine이 종료됨
- Scanner ready root와 V3-B artifact root를 동일 authority로 만들 수 없음
- actual local flow가 기존 S0/V4 API 변경 없이는 진행 불가
- valid ACK 전에 Coordinator가 sent feedback를 내야만 flow가 진행됨
- flush 전에 seal해야만 finalization이 가능함
- deterministic local E2E가 실제 camera/STM/audio 없이는 구성 불가
- whole Coordinator restart persistence가 없으면 정상 단일-process E0도 동작 불가
- 새 production dependency 또는 Server schema 변경이 필수
- 기존 Scanner/Coordinator/S0/S1/C0/V4/V3-B 회귀 발생

중단 시 핵심 composition blocker, 실제 Laptop acceptance 항목, 운영 hardening 후보를 분리해 보고한다.

## 18. 후속 패킷

E0-Core 완료 뒤 다음 승인 단위는 **Device Integration E0-B — Laptop Acceptance**다.

```text
E0-Core Local Composition on development desktop
  -> Device Integration E0-B — Laptop Acceptance: real camera + STM + beep/TTS + remote HTTPS desktop Server
  -> production tunnel policy/service와 exhaustive network fault validation
  -> Raspberry Pi camera/GPIO/audio/systemd/resource validation
```

Device Integration E0-B — Laptop Acceptance는 E0-Core 코드를 다른 환경에서 검증하고 필요한 hardware adapter만 추가한다.
E0-Core를 다시 설계하거나 운영 hardening을 한꺼번에 끌어들이는 패킷으로 만들지 않는다.
