# Device Integration E0-B.3.3 — ACK Callback Diagnostic Forwarding 작업 패킷

상태: **승인됨 / 구현 및 local 전체 회귀 완료 / E0-B.4 actual evidence closure 대기**
기준일: 2026-09-02
성격: **Device ScannerRuntime callback event 전달 경계 복구**
선행 조건: E0-B.3.2 identity role/report 계약 교정, 실제 Laptop E0-B.3.2 replay 성공 로그
후속 조건: E0-B.4 actual evidence closure, physical E0-B acceptance, production OCR/TTS/braille acceptance

## 1. 우선순위

이 패킷을 E0-B.4 actual evidence closure보다 먼저 수행한다.

| 순서 | 패킷 | 이유 |
|---:|---|---|
| 1 | **E0-B.3.3 ACK callback diagnostic forwarding** | 실제 로그에서 확인된 관측 경계 유실을 저장소 내부에서 작게 수정하고 전체 회귀할 수 있음 |
| 2 | **E0-B.4 actual evidence closure** | 수정된 lifecycle 로그와 Server 2/4/0 증거를 결합해 최종 `passed` 산출물을 동결 |
| 3 | **Physical E0-B acceptance** | camera, HC-05/STM, speaker를 물리 장비에서 검증 |
| 4 | **Production content acceptance** | 실제 OCR/TTS/braille 내용 품질을 별도 authority로 평가 |

E0-B.3.3과 E0-B.4를 합치지 않는다. E0-B.3.3은 로컬 코드와 결정론적 테스트만으로 끝낼 수 있지만,
E0-B.4는 Laptop transcript, pinned source report, Desktop Server summary라는 외부 증거가 필요하다.

## 2. 실제 로그에서 확인된 결과

E0-B.3.2가 적용된 pinned `test1.mp4` replay에서 다음 핵심 결과는 성공했다.

```text
fresh datapack
  datapack-db802a4499c541ab8233f161d905e997

candidate spread 1
  video-00000092 selected
  candidate_verification 1/5 ... 5/5
  decision=different, timed_out=false
  spread_sent sequence=1

page-change monitoring
  repeated identity_role=page_change decision=same
  video-00000310 ... video-00000314
  identity_role=page_change 5/5 different

candidate spread 2
  video-00000365 selected
  candidate_verification 1/5 ... 5/5
  decision=different, timed_out=false
  spread_sent sequence=2

scan_input_exhausted queued_count=2 acked_count=2
datapack_saved revision=1
reading pages 00000001-L/R, 00000002-L/R
```

이 결과는 다음을 확인한다.

- candidate verification은 정확히 2회다.
- 두 candidate 모두 5/5 `different` 뒤 전송됐다.
- `video-00000310`~`314`는 candidate 실패가 아니라 page-change 감시다.
- 2 spreads, 4 reading page positions의 runtime 경계가 유지된다.

그러나 각 `spread_sent` 뒤 로그에는 다음 이벤트가 없다.

```json
{
  "type": "feedback",
  "code": "identity_collection_started",
  "details": {
    "identity_role": "page_change",
    "spread_id": "...",
    "query_sample_count": 5
  }
}
```

대신 첫 `page_change` progress부터 나타난다.

```json
{
  "type": "feedback",
  "code": "identity_collection_progress",
  "details": {
    "source_frame_id": "video-00000100",
    "identity_role": "page_change",
    "valid_observations": 1,
    "query_sample_count": 5
  }
}
```

따라서 role 자체는 구분되지만 page-change lifecycle의 시작 시점과 accepted spread lineage가 feedback
경계에서 유실된다.

## 3. 원인

Book Scanner 엔진의 ACK callback은 이미 올바른 이벤트를 생성한다.

```text
BookScannerEngine.delivery_confirmed(...)
  -> DELIVERY_CONFIRMED
  -> OPAQUE_IDENTITY_BANK_ACCEPTED
  -> OPAQUE_IDENTITY_COLLECTION_STARTED
       identity_role=page_change
       pending spread/source lineage
  -> WAITING_FOR_PAGE_CHANGE
```

Device adapter도 `opaque_identity_collection_started`를 bounded diagnostic으로 변환할 수 있다.

```text
opaque_identity_collection_started
  -> identity_collection_started
  -> identity_role, query_sample_count
  + event source_frame_id/spread_id
```

유실은 delivery callback 경계에서 발생한다.

```text
Coordinator._handle_delivery_update()
  -> scanner.apply_delivery_update(...)

BookScannerRuntimeAdapter.apply_delivery_update()
  -> events = engine.delivery_confirmed(...)
  -> DELIVERY_CONFIRMED 존재만 검사
  -> events를 ScannerEvent로 변환하거나 반환하지 않음

Coordinator
  -> spread_sent feedback만 방출
```

Scanner의 정기 `poll()`에서 생긴 이벤트는 `_convert_event()`를 거쳐 전달되지만, ACK/REJECT callback에서
동기적으로 생긴 이벤트는 현재 버려진다. 이는 Scanner 판정이나 전송 실패가 아니라 Device 관측 경계의
event plumbing 결함이다.

## 4. 목표

1. delivery callback이 생성한 Scanner event를 Device Coordinator까지 명시적으로 전달한다.
2. ACK 완료 feedback 뒤 `page_change identity_collection_started`를 정확히 한 번 방출한다.
3. 시작 feedback에 `identity_role=page_change`, `spread_id`, `source_frame_id`, `query_sample_count=5`를 보존한다.
4. 반복 ACK 또는 terminal update가 동일 start feedback을 재방출하지 않도록 한다.
5. Scanner threshold, identity decision, artifact, queue, ACK, save/read 결과를 변경하지 않는다.
6. E0-B.3.2 report가 progress에서 암묵적으로 lifecycle을 복원할 필요 없이 명시적 start를 수집하게 한다.

## 5. 설계 결정

### 5.1 명시적 callback 반환 계약

`ScannerRuntime.apply_delivery_update()`의 반환 계약을 다음과 같이 변경한다.

```python
def apply_delivery_update(
    self,
    artifact_id: ArtifactId,
    update: DeliveryUpdate,
) -> tuple[ScannerEvent, ...]: ...
```

`BookScannerRuntimeAdapter`는 callback으로 받은 raw Scanner events를 기존 `_convert_event()` 경계로
변환해 반환한다.

```text
engine.delivery_confirmed(...)
  -> raw callback events
  -> 기존 bounded _convert_event()
  -> tuple[ScannerEvent, ...]
  -> Coordinator
```

별도 hidden queue는 만들지 않는다.

- ACK callback에서 생긴 사건을 다음 poll까지 지연하지 않는다.
- freeze/close 전환 때문에 queued diagnostic이 사라지는 새 경계를 만들지 않는다.
- callback의 stable event ID를 Coordinator의 기존 `_seen_scanner_events` 중복 방지에 그대로 사용한다.
- 실제 생성 원인과 feedback 방출 사이의 추적을 명시적으로 유지한다.

### 5.2 feedback 순서

ACK 처리 순서는 다음으로 고정한다.

```text
delivery ACK 확인
  -> Scanner callback 적용 및 callback events 확보
  -> spread_sent sequence=N
  -> callback diagnostic 처리
  -> identity_collection_started identity_role=page_change
  -> 다음 poll에서 page_change progress/decision
```

따라서 실제 console에서 최소 순서는 다음과 같다.

```text
identity_collection_decided role=candidate_verification decision=different 5/5
spread_sent sequence=N
identity_collection_started role=page_change spread_id=... query_sample_count=5
identity_collection_progress role=page_change ...
```

`spread_sent`는 Device/Server ACK 경계이고 page-change monitoring은 accepted spread를 기준으로 시작하므로,
위 순서가 사용자에게 가장 직접적인 의미를 제공한다.

### 5.3 callback event 처리 범위

Coordinator는 반환된 callback event를 기존 `_handle_scanner_event()`로 처리한다.

- 기존 session lineage 검사 유지
- 기존 stable event ID dedup 유지
- 기존 diagnostic code whitelist 유지
- unknown/non-public Scanner event는 기존처럼 feedback으로 노출하지 않음
- raw opaque token, image, digest, receipt ID를 diagnostic detail에 추가하지 않음

ACK callback의 `DELIVERY_CONFIRMED`, `OPAQUE_IDENTITY_BANK_ACCEPTED`, `WAITING_FOR_PAGE_CHANGE`가 현재
public ScannerEvent로 변환되지 않는 동작은 유지한다. 이번 패킷에서 새로 사용자 feedback으로 필요한 것은
bounded `OPAQUE_IDENTITY_COLLECTION_STARTED`뿐이다.

## 6. 포함 범위

### 6.1 Device Runtime port와 adapter

- `ScannerRuntime.apply_delivery_update()` 반환형을 `tuple[ScannerEvent, ...]`로 변경
- no-op/stale/mismatched/repeated update는 빈 tuple 반환
- ACK/REJECT callback raw event를 공통 변환 함수로 처리
- callback mapping 실패는 기존 `FatalPortError` 경계를 유지
- terminal artifact idempotency 유지

### 6.2 Coordinator

- callback events를 수신
- ACK이면 기존 `spread_sent`를 먼저 방출
- 이후 callback events를 `_handle_scanner_event()`로 전달
- REJECT면 기존 `parser_rejected` semantics를 유지하고 변환 가능한 callback events만 처리
- callback diagnostic이 artifact queue 수나 flow state를 바꾸지 않음을 테스트

### 6.3 Replay report

- schema version과 최종 성공 조건은 유지
- explicit page-change start가 있으면 해당 `spread_id`와 시작 frame을 `page_change_checks[]`에 보존
- progress-only legacy/E0-B.3.2 로그의 보수적 복원 호환은 유지
- 새 E0-B.3.3 fixture에서는 start event 누락을 허용하지 않는 별도 check 또는 fixture assertion 추가

최종 report가 과거 로그를 읽지 못하도록 만들지 않는다. 다만 E0-B.3.3 이후 새 증거의 lifecycle 완전성은
테스트와 문서에서 더 강하게 요구한다.

### 6.4 문서

- Laptop Quickstart에 ACK 뒤 기대 feedback 순서 추가
- E0-B 검증 보고서에 실제 E0-B.3.2 로그의 성공과 start 유실을 구분해 기록
- 프로젝트 handoff에 E0-B.3.3 상태와 E0-B.4 선행 관계 반영
- 구현 완료 시 별도 E0-B.3.3 구현 보고서 작성

## 7. 명시적 제외 범위

이번 패킷에서 변경하지 않는다.

- Scanner candidate selection과 stable window
- `sample_interval_ms=100`
- `stable_sample_count=3`, `sample_window_size=5`
- opaque identity `query_sample_count=5`
- identity SAME/DIFFERENT threshold와 evidence collector
- obstruction/page movement 판단
- artifact 생성과 L/R fragment 수
- durable outbox, Server API/DB/schema
- datapack save/finalize/reading navigation
- replay source와 pinned video
- production OCR/TTS/braille content
- physical camera, STM, HC-05, speaker
- 로그 소음 throttle 또는 UI/음성 guidance 변경

`page_change identity_collection_started`가 없다는 이유로 더 많은 페이지를 후보로 승인하거나 318을
강제로 수용하지 않는다. 이번 문제는 observer event 전달 문제다.

## 8. 유지해야 할 불변식

1. pinned replay 결과는 `spread_sent [1,2]`다.
2. EOF 결과는 `queued_count=2`, `acked_count=2`다.
3. candidate verification은 정확히 두 번이며 각각 5/5 `different`, timeout false다.
4. `video-00000310`~`314`의 5/5 `different`는 계속 `identity_role=page_change`다.
5. page-change start diagnostic은 artifact나 sequence를 새로 만들지 않는다.
6. 동일 ACK 재적용은 feedback을 중복 방출하지 않는다.
7. callback diagnostic의 session/event lineage 검사를 우회하지 않는다.
8. raw opaque token, footer image, digest, credential은 public feedback/report에 포함하지 않는다.
9. 최종 reading의 고유 page positions는 두 spread의 L/R 네 개다.
10. Server receipt/fragment/duplicate truth는 E0-B.4의 Server authority에서 판정한다.

## 9. 테스트 행렬

### 9.1 Adapter unit

- ACK callback에서 반환된 `OPAQUE_IDENTITY_COLLECTION_STARTED`가 `ScannerEventType.DIAGNOSTIC`으로 변환됨
- details:
  - `identity_role=page_change`
  - `query_sample_count=5`
  - bounded `source_frame_id`
  - bounded `spread_id`
- `DELIVERY_CONFIRMED` 등 비공개 이벤트는 반환 결과에서 제외됨
- stale session/update, unknown artifact, terminal artifact 반복은 `()` 반환
- raw token/digest/receipt secret이 diagnostic에 없음
- REJECT callback의 기존 terminal 동작 유지

### 9.2 Coordinator unit

- ACK 처리 feedback 순서:

```text
spread_sent
identity_collection_started(role=page_change)
```

- callback event가 기존 `_seen_scanner_events` dedup을 통과함
- 동일 event ID/반복 ACK에서 start feedback이 한 번만 출력됨
- returned diagnostic이 sequence, queue count, state를 변경하지 않음
- unknown diagnostic code는 기존처럼 무시됨

### 9.3 Report unit

- page-change start의 spread lineage가 `page_change_checks[]`에 보존됨
- start 뒤 progress/decision이 동일 check에 집계됨
- 두 번째 start가 이전 열린 check를 안전하게 종료하고 새 check를 시작함
- progress-only E0-B.3.2 legacy fixture는 계속 읽을 수 있음
- E0-B.3.3 exact fixture는 두 accepted spread 각각의 명시적 page-change start를 포함함
- Server summary 없음: `provisional`
- 정확한 Server 2/4/0: `passed`

### 9.4 전체 회귀

- Device Runtime 전체 suite
- Book Scanner 전체 suite
- 필요 시 actual E0-Core integration suite
- `python -m py_compile` 또는 동등한 syntax 검증
- `git diff --check`

Book Scanner 제품 로직을 바꾸지 않더라도 Scanner/Device callback event 계약을 함께 고정하기 위해 두
프로젝트 전체 회귀를 모두 수행한다.

## 10. 완료 기준

다음을 모두 충족해야 E0-B.3.3을 완료로 판정한다.

- [ ] `ScannerRuntime.apply_delivery_update()`가 callback Scanner events를 명시적으로 반환한다.
- [ ] real adapter가 ACK callback diagnostic을 기존 bounded mapping으로 변환한다.
- [ ] Coordinator가 `spread_sent` 뒤 callback diagnostic을 처리한다.
- [ ] page-change start feedback에 role, spread, source, required count가 있다.
- [ ] 동일 ACK에서 start feedback은 정확히 한 번이다.
- [ ] candidate/page-change 판정 수와 결과가 바뀌지 않는다.
- [ ] report가 새 explicit start lineage를 보존한다.
- [ ] progress-only 기존 로그 호환성이 유지된다.
- [ ] targeted unit tests가 통과한다.
- [ ] Book Scanner와 Device Runtime 전체 suite가 통과한다.
- [ ] Quickstart, 검증 보고서, handoff, 구현 보고서가 실제 계약과 일치한다.
- [ ] raw secret/token/image가 새 public diagnostic에 포함되지 않는다.

실제 Laptop 재실행과 Server final evidence는 이 완료 기준에 포함하지 않는다. 그것은 E0-B.4다.

## 11. 예상 변경 파일

주요 후보:

```text
device-runtime/src/asl_device/protocols.py
device-runtime/src/asl_device/adapters/book_scanner_runtime.py
device-runtime/src/asl_device/coordinator.py
device-runtime/src/asl_device/replay_boundary_report.py
device-runtime/tests/unit/fakes.py
device-runtime/tests/unit/test_book_scanner_runtime.py
device-runtime/tests/unit/test_coordinator.py
device-runtime/tests/unit/test_replay_boundary_report.py
LAPTOP_E0B_QUICKSTART.md
device-runtime/docs/device-integration-e0b-laptop.md
DEVICE_INTEGRATION_E0_B_3_VERIFICATION_REPORT.md
PROJECT_HANDOFF_20260831.md
DEVICE_INTEGRATION_E0_B_3_3_IMPLEMENTATION_REPORT.md
```

Book Scanner source 변경은 원칙적으로 필요하지 않다. 엔진이 이미 올바른 start event와 role을 생성하기
때문이다. 테스트가 엔진 계약의 추가 고정을 요구할 때만 기존 Book Scanner test assertion을 보강한다.

## 12. 승인 경계

승인 시 수행:

- Device ScannerRuntime callback 반환 계약 수정
- Book Scanner adapter callback event 변환
- Coordinator ACK feedback 순서와 forwarding 구현
- report/test fixture의 explicit page-change start lineage 보강
- 관련 문서 정정
- targeted 및 전체 local 회귀
- E0-B.3.3 구현 보고서 작성

별도 승인 없이는 수행하지 않음:

- Laptop/Desktop에서 replay 재실행
- Server summary 또는 DB evidence 수집
- Scanner threshold/identity policy 변경
- 318 또는 다른 페이지의 수용 정책 변경
- physical camera/STM/audio 작업
- production OCR/TTS/braille 품질 작업
- commit, push 또는 PR

## 13. 중단 조건

다음이면 범위를 조용히 넓히지 않고 보고한다.

- callback event 반환을 위해 Server/outbox protocol 또는 persisted schema 변경이 필요함
- diagnostic forwarding이 ACK idempotency나 sequence ordering을 변경함
- `spread_sent`와 callback diagnostic 순서를 결정론적으로 보장할 수 없음
- callback event가 stable event/session lineage를 제공하지 않음
- public feedback에 raw opaque token/image/digest가 필요함
- progress-only 기존 로그 호환성을 유지할 수 없음
- targeted 또는 전체 회귀에서 artifact/queue/save/read 결과가 달라짐

중단 시 실제 확인 범위만 보고하고 Scanner 수용 정책, Server schema 또는 외부 재실행으로 범위를 자동 확장하지
않는다.

## 14. 후속 순서

```text
E0-B.3.3 ACK callback diagnostic forwarding
  -> E0-B.4 role-complete Laptop transcript + source report + Server 2/4/0 evidence closure
  -> physical E0-B camera + HC-05/STM + speaker acceptance
  -> production OCR/TTS/braille content acceptance
```

이 패킷의 목적은 spread 수를 늘리는 것이 아니다. 이미 성공한 ACK 뒤 Scanner가 실제로 시작한
page-change monitoring lifecycle을 Device feedback 경계에서 누락 없이 보존하여, 최종 acceptance
증거가 엔진 상태와 동일한 사건 순서를 표현하도록 만드는 것이다.
