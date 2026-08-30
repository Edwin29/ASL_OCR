# Scanner Video V0 — 계약·상태·테스트 더블 작업 패킷

상태: **구현·검증 완료**
작성일: 2026-08-30
상위 설계: `SCANNER_CONTINUOUS_TRANSFER_READINESS_DESIGN.md`
후속 패킷: V1 연속 프레임 엔진, V2 seam+UVDoc artifact

## 1. 목표

연속 영상 Scanner가 구현 중에도 기존 session·전송 경로와 충돌하지 않도록 새 runtime의
계약, 상태, event, 실패 이유와 테스트 경계를 먼저 고정한다.

이 패킷은 실제 카메라나 UVDoc을 실행하는 패킷이 아니다. V1과 V2가 의존할 작은 domain
계약과 deterministic fake를 구현하는 패킷이다.

## 2. 확정 입력 결정

- 기본 처리 경로 식별자: `seam-conservative + uvdoc-bilinear`
- 버튼: `IDLE`에서 시작, active 상태에서 취소
- 좌우 페이지는 하나의 `source_frame_id`와 `spread_id`를 공유
- `전송가능여부` 단일 bool을 만들지 않음
- 완료음의 근거는 local artifact 생성이 아니라 서버의 접수 확인
- legacy `session/loop.py`와 기존 event는 삭제·의미 변경하지 않음

## 3. 구현 범위

### 3.1 Domain 타입

새 모듈에 다음 immutable 타입을 둔다.

- `VideoSessionState`
  - `IDLE`, `ARMING`, `SEARCHING`, `SETTLING`, `PROCESSING_CANDIDATE`
  - `LOCAL_RETRY`, `READY_FOR_SERVER_PREFLIGHT`, `UPLOADING`, `REMOTE_RETRY`
  - `PARSER_REJECTED`, `DELIVERY_CONFIRMED`, `WAITING_FOR_PAGE_CHANGE`
  - `CANCELLING`, `ERROR`
- `ReadinessState`
  - `RETRY_LOCAL`, `READY_FOR_PREFLIGHT`, `RETRY_REMOTE`, `ACCEPTED`, `FATAL`
- 계층화된 reason code
  - acquisition, motion, layout, illumination, quality, correction, parser, transport
- `FrameId`, `SpreadId`, `ArtifactId`
- `FrameCandidate`
- `ReadinessDecision`
- `SpreadArtifactRef`

문자열 reason을 임의로 추가하지 못하도록 enum과 serializer를 함께 둔다. 저장·전송 JSON에는
`schema_version`과 evaluator version이 반드시 포함된다.

### 3.2 Protocol

V1 이후 구현을 교체할 수 있도록 다음 protocol을 정의한다.

- `CameraSource.start/read/stop`
- `ButtonSource.events`
- `GuidanceSink.emit`
- `CandidateEvaluator.evaluate`
- `SpreadProcessor.process`
- `ArtifactStore.commit`
- `ParserClient.preflight_and_submit`
- monotonic `Clock`

protocol은 OpenCV, Picamera2, GPIO, TTS, 실제 서버 라이브러리를 import하지 않는다.

### 3.3 구성과 정책

- `ScannerPipelineConfig`
  - extraction 기본값 `seam_conservative`
  - correction 기본값 `uvdoc_bilinear`
  - silent fallback 금지
- `CandidatePolicy`
  - sample interval, stable sample count, sample window 용량, cooldown
- `GuidancePolicy`
  - 지속 frame/시간, 동일 문구 cooldown
- `DeliveryPolicy`
  - 성공 ack 수준과 retry 범주

임곗값은 V0에서 production 수치로 확정하지 않는다. 기본값은 테스트 가능한 보수적 placeholder로
표시하고 `validated=false` provenance를 가진다.

### 3.4 Event

- session started/cancelled/error
- candidate observed/selected/processed
- guidance requested
- artifact ready
- upload queued/retrying
- parser rejected
- delivery confirmed
- waiting for page change/page changed

모든 event는 `event_id`, monotonic timestamp, session ID를 가진다. frame 관련 event는
`source_frame_id`를 가진다.

### 3.5 Deterministic fake

- frame sequence를 내는 fake camera
- start/cancel 입력을 예약하는 fake button
- event를 수집하는 fake guidance
- 성공·retry·reject 결과를 예약하는 fake parser client
- 입력 frame ID를 그대로 기록하는 fake spread processor
- 테스트용 수동 clock

fake는 test package에 두고 production에서 선택되는 runtime backend로 노출하지 않는다.

## 4. 예상 파일 경계

구현 시 저장소 구조를 확인해 이름은 조정할 수 있지만 책임은 다음처럼 분리한다.

```text
src/book_scanner/video/
  types.py
  protocols.py
  config.py
  events.py
tests/unit/video/
  fakes.py
  test_types.py
  test_config.py
  test_events.py
```

기존 `session/`, `judge/`, `transmit/` public API는 V0에서 변경하지 않는다.

## 5. 검증

필수 단위 검증:

- state/reason JSON round-trip
- 알 수 없는 schema version 또는 reason code의 명시적 실패
- 좌우가 서로 다른 `source_frame_id`인 `SpreadArtifactRef` 생성 거부
- artifact hash나 한쪽 페이지가 없는 ready 결과 생성 거부
- transport reason이 physical guidance reason으로 분류되지 않음
- fake camera가 stop 이후 frame을 내지 않음
- fake parser가 같은 idempotency key의 결과를 재현
- 기존 전체 unit test 회귀 없음

## 6. 완료 기준

- 새 계약과 fake가 구현되고 테스트 통과
- 기본 pipeline config가 `seam_conservative/uvdoc_bilinear`
- legacy session 동작과 테스트가 그대로 통과
- 실제 카메라·UVDoc·네트워크를 사용하지 않고 V1 상태 전이를 시험할 수 있음
- 문서와 코드의 state/reason 이름이 일치

## 7. 비범위

- frame producer/consumer loop
- OpenCV webcam과 MP4 replay
- seam 검출과 실제 UVDoc
- 사용자 음향 출력
- page-change 판정
- durable outbox와 실제 서버 API
- Raspberry Pi/Picamera2/GPIO

비범위 항목은 완료로 기록하지 않는다.

## 8. 중단 조건

- 기존 public API를 깨야만 계약을 추가할 수 있음
- Document Parser의 실제 서버 계약을 V0에서 임의로 확정해야 함
- 좌우를 서로 다른 frame에서 허용해야만 테스트가 통과함

위 조건이 생기면 구현을 확대하지 않고 설계 충돌을 보고한다.

## 9. 구현 결과

구현일: 2026-08-30

추가된 production 계약:

- `src/book_scanner/video/types.py`
  - immutable ID, session/readiness state, 계층화 reason
  - frame candidate, 좌우 page/spread artifact, readiness decision
  - schema version과 strict JSON serializer
  - 동일 source frame 좌우 불변식과 hash/receipt 검증
- `src/book_scanner/video/protocols.py`
  - camera, button, guidance, evaluator, processor, store, parser, clock protocol
  - OpenCV/Picamera2/GPIO/HTTP import 없음
- `src/book_scanner/video/config.py`
  - 기본 `seam_conservative/uvdoc_bilinear`, silent fallback 금지
  - 500 ms 표본, 3개 안정 표본 등 `validated=false` provisional policy
- `src/book_scanner/video/events.py`
  - event envelope와 guidance request

test-only 구현:

- sequence camera, scheduled button, collecting guidance
- recording spread processor
- idempotent fake parser
- manual monotonic clock

검증 결과:

- V0 신규 테스트: **24 passed**
- 전체 `book-scanner/tests/unit`: **145 passed**
- `compileall`: 통과
- legacy `session/`, `judge/`, `transmit/` 코드 변경 없음

환경 메모:

- 기본 Python editable install이 과거 worktree를 가리켜 첫 수집은 새 package를 찾지 못했다.
- 현재 checkout의 `src`를 `PYTHONPATH` 선두에 지정해 검증했다.
- Windows 공용 pytest temp 경로의 권한 문제는 workspace 내부의 명시적 `--basetemp`로
  우회했다. 이는 제품 코드 실패가 아니다.

V1 frame engine, 실제 카메라, seam/UVDoc 실행, 서버 전송은 이 완료 판정에 포함하지 않는다.
