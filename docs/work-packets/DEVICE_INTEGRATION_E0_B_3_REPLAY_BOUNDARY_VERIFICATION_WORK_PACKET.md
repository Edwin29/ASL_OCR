# Device Integration E0-B.3 — Replay Candidate/Identity Boundary Verification 작업 패킷

상태: **완료 후 E0-B.3.2에 의해 진단 원인 가설과 report 성공 조건이 대체됨**
기준일: 2026-09-01
성격: **E0-B 실제 Laptop 환경의 replay 판정 증거 보강 및 software acceptance 종료 패킷**
선행 조건: Device Integration E0-B.2 구현과 동일 영상의 실제 Laptop remote replay/upload/reading 성공
후속 조건: E0-B remote software acceptance 종료 후 physical camera + HC-05/STM acceptance

> **2026-09-02 정정:** 실제 E0-B.3.1 이후 full Laptop log는 candidate identity와 전송 후
> page-change identity가 같은 event family를 사용한다는 사실을 확인했다. 이 패킷의 314/315 `4/5 +
> content_occluded` 및 318 `1/5 + EOF` 원인 가설은 실제 runtime 증거로 확정되지 않았으며,
> 이를 필수로 검사하는 report 계약도 잘못됐다. 역사적 승인 내용은 보존하지만 현재 authority는
> `docs/work-packets/DEVICE_INTEGRATION_E0_B_3_2_IDENTITY_ROLE_REPORT_CONTRACT_CORRECTION_WORK_PACKET.md`와 교정된
> verification report다. Scanner capture 정책과 exact-video 기대 전송 수 2는 변경하지 않는다.

## 1. 배경과 실제 관측

실제 Laptop에서 다음 prepared MP4를 E0-B replay로 실행했다.

```text
SHA-256: 16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8
resolution: 3840 x 2160
fps: 59.69965076707844
frames: 2677
duration: 44.84113333333334s
effective sampling: 100ms / frame step 6
```

실제 remote flow는 다음 경계를 통과했다.

- Desktop Tailscale Serve private HTTPS health와 API key 인증
- Laptop C0 presence, S0 catalog/datapack/scan session
- Scanner candidate/opaque identity/UVDoc artifact 생성
- V3-B durable queue와 Server V4/S1 valid ACK
- `spread_sent` sequence 1, 2
- replay EOF `scan_input_exhausted(queued_count=2, acked_count=2)`
- user confirm 뒤 flush/seal/finalize READY
- Laptop `reading_snapshot`과 navigation response
- Server spread 2개, left/right fragment 4개, duplicate 0

동일 영상을 100ms cadence로 offline candidate audit하고 실제 프레임을 대조한 결과는 다음과 같다.

| 펼침면 | candidate 관측 | 현재 계약에 따른 판정 | 실제 runtime 결과 |
|---|---|---|---|
| 30/309 | 긴 clean stable 구간 | candidate + N=5 identity 완료 가능 | sequence 1 전송 |
| 310/311 | 손 가림과 지속 `content_occluded` | candidate hard reject | 전송하지 않음 |
| 312/313 | 해당 구간 58개 중 56개 `content_occluded` | candidate hard reject | 전송하지 않음 |
| 314/315 | frame 1854~1890의 연속 clean 표본 7개 | candidate 3개 뒤 identity 4개만 가능, 이후 hard reject | 전송하지 않음 |
| 316/317 | frame 2148~2256의 연속 clean 표본 19개 | candidate + N=5 identity 완료 가능 | sequence 2 전송 |
| 318/12장 시작 | frame 2658~2676의 연속 clean 표본 4개 | candidate 3개 뒤 identity 1개만 가능, 이후 EOF | 전송하지 않음 |

offline audit의 `stable_window_count=42`는 페이지 수가 아니라 서로 겹치는 rolling stable window 수다.
고유 candidate 구간은 4개지만, candidate-valid라는 사실만으로 opaque identity까지 완료됐다고 판단할
수는 없다. audit policy도 `validated=false`이고 결과는 provisional authority다.

현재 M1 Scanner 계약은 다음 두 단계를 순차 수행한다.

```text
candidate stable: 서로 다른 eligible sample 3개
  -> 새 opaque identity collector 시작
  -> identity: 이후 valid token pair sample 5개
```

따라서 이상적인 100ms source cadence에서도 첫 clean sample부터 마지막 identity sample까지 최소 8개의
연속 eligible observation이 필요하다. 이것을 이 패킷에서는 **clean dwell requirement**라고 부른다.
이는 사용자가 벽시계로 기다린 시간을 직접 뜻하지 않는다. 손·움직임·geometry/footer missing 없이
연속으로 판정 가능한 source frame 구간을 뜻한다.

314/315에는 연속 clean 표본이 7개뿐이었다. 앞의 3개로 candidate를 확정하고 이후 4개가 identity에
들어간 다음, 다음 sample의 `content_occluded` hard reject가 진행 중 collector를 폐기한 것으로
판단된다. 318은 candidate 확정 뒤 identity sample 1개만 남은 채 source가 끝났다.

이 동작은 현재 계약의 false duplicate/false ACK 방지 보수성에 부합한다. 따라서 314/315와 318을
반드시 전송하도록 만드는 것은 버그 수정이 아니라 최소 clean dwell과 evidence acquisition 순서를
바꾸는 별도 제품·알고리즘 정책 변경이다.

## 2. 이 패킷의 판정

이번 E0-B.3은 다음을 현재 정상 동작으로 수용한다.

1. 310/311과 312/313는 손/가림으로 인한 정상 hard reject다.
2. 314/315는 stable candidate였지만 post-selection identity가 4/5에서 hard reject되어 정상적으로
   `UNKNOWN`/abort된 것으로 본다.
3. 318/12장 시작은 stable candidate였지만 post-selection identity가 1/5에서 EOF를 만나 정상적으로
   artifact 없이 종료된 것으로 본다.
4. 동일 영상에서 30/309와 316/317 두 spread만 ACK된 결과는 현재 보수 계약의 정상 기대값이다.
5. 이 평가는 E0-B remote software integration을 판정하기 위한 것이며 Scanner의 production recall이나
   모든 책/손 동작에 대한 capture quality 승인이 아니다.

동일 prepared MP4의 acceptance 기대값은 다음으로 동결한다.

```text
sequence 1: 30/309
sequence 2: 316/317

scan_input_exhausted:
  queued_count = 2
  acked_count = 2

Server:
  spread receipt = 2
  left/right fragment = 4
  duplicate spread/fragment = 0
```

## 3. 목표

이 패킷은 Scanner 판정 동작을 바꾸지 않고 다음 세 가지를 완료한다.

1. runtime log만으로 candidate 선택, identity 유효 표본 수와 terminal abort reason을 구분할 수 있게 한다.
2. 동일 prepared MP4에서 314/315의 `3 + 4 + hard reject`와 318의 `3 + 1 + EOF`를 재현 가능한
   구조화 증거로 확정한다.
3. 기존 remote 결과 `2 spreads / 4 fragments / duplicate 0 / READY / reading navigation`을 E0-B
   software acceptance 성공으로 문서화한다.

## 4. 포함 범위

### 4.1 Bounded candidate/identity diagnostics

가능하면 기존 Book Scanner semantic event를 Device Runtime feedback/report에 연결한다. 기존 event에
terminal reason 또는 valid count가 없다면 필요한 최소 필드만 추가한다.

필요한 증거:

```json
{"code":"candidate_selected","details":{"source_frame_id":"..."}}
{"code":"identity_collection_started","details":{"required":5}}
{"code":"identity_collection_progress","details":{"valid":4,"required":5}}
{"code":"identity_collection_aborted","details":{"reason":"content_occluded","valid":4,"required":5}}
{"code":"identity_collection_aborted","details":{"reason":"source_exhausted","valid":1,"required":5}}
```

규칙:

- progress는 valid count가 바뀔 때만 출력한다.
- selected/started/terminal event는 해당 attempt당 정확히 한 번 기록한다.
- candidate hard reject와 identity missing/provider error/source exhausted를 구분한다.
- raw OCR token, ROI/image bytes, API key와 absolute model path를 기록하지 않는다.
- frame ID, count, bounded reason code와 duration만 기록한다.
- diagnostic feedback은 관측자이며 candidate, identity, artifact, ACK state를 변경하지 않는다.
- feedback 출력 실패가 Scanner 또는 delivery state를 되돌리지 않는다.

### 4.2 Exact-video boundary audit

동일 SHA-256 영상에 대해 candidate audit 결과와 실제 Scanner identity lifecycle을 시간 순서로 결합한
구조화 report를 생성한다.

spread interval별 최소 출력:

- source frame/timestamp 범위
- candidate eligible/hard-rejected sample 수
- candidate selected frame ID
- identity valid/missing/hard-rejected sample 수
- terminal reason과 terminal frame ID
- artifact/sequence/ACK 발생 여부
- accepted spread는 Server receipt와 fragment count

이 audit은 기존 provider와 engine contract를 사용한다. 별도의 완화된 evaluator로 성공 수를 늘리지
않고, provisional candidate label을 production ground truth로 승격하지 않는다.

### 4.3 E0-B software acceptance closure

기존 실제 Laptop 결과와 diagnostics를 다음 경계별로 정리한다.

- network/auth/presence/catalog/session
- candidate/identity/artifact
- V3-B queue와 V4 receipt
- EOF와 user-confirmed finalize
- READY/read/navigation
- expected reject와 unexpected failure 구분

Quickstart에는 이 prepared MP4의 정상 기대값과 `stable candidate != transmitted spread`를 명시한다.

## 5. 명시적 제외 범위

이번 패킷에서는 다음을 구현하지 않는다.

- stable-window frame을 identity evidence로 재사용
- 마지막 decoded frame 반복 또는 synthetic source ID를 통한 EOF padding
- `stable_sample_count=3`, `query_sample_count=5` 변경
- `k_same=1`, `k_different=0` 변경
- candidate motion/occlusion/geometry/seam/clipping threshold 완화
- missing/provider error를 valid identity observation 또는 mismatch로 계수
- identity hard reject 시 기존 collector를 보존하거나 자동 재개
- EOF 기반 auto ACK, auto confirm, auto seal/finalize/READY
- 314/315 또는 318을 acceptance 성공 조건으로 강제
- alternate/synthetic positive video 제작 또는 repository 추가
- Server S0/S1/V4, DB schema 또는 V3-B outbox 변경
- multi-writer, quota, lease, quarantine, crash matrix 등 운영 hardening
- actual OCR/TTS 품질 또는 physical camera/HC-05/STM/speaker 완료 처리

향후 “stable candidate를 더 짧은 clean dwell로도 전송해야 한다”는 요구가 확정되면 candidate-window
evidence 재사용, identity acquisition 순서 또는 별도 capture-hold UX를 독립 패킷에서 비교한다.

## 6. 유지해야 할 불변식

```text
valid stable candidate
  -> post-selection N=5 valid opaque identity observations
  -> SAME이면 duplicate suppression
  -> DIFFERENT이면 immutable artifact
  -> V3-B durable queue
  -> V4/S1 valid receipt
  -> local ACK
  -> SPREAD_SENT
```

- candidate stable 3개와 identity N=5를 조용히 합치지 않는다.
- identity valid count가 5 미만이면 DIFFERENT 또는 artifact를 만들지 않는다.
- hard reject frame과 missing/provider error는 valid observation이 아니다.
- ACK 전에 `SPREAD_SENT`를 출력하지 않는다.
- pending identity bank는 Server ACK 뒤에만 accepted로 승격한다.
- EOF와 diagnostic event는 ACK 또는 finalize authority가 아니다.
- user `confirm`만 stop/freeze/flush/seal intent다.
- physical profile과 replay profile의 기존 Scanner 의미를 변경하지 않는다.

## 7. 구현 단계

### Phase 0 — Evidence 동결

- exact video SHA-256, 해상도, frame count와 cadence 확인
- candidate audit와 실제 Laptop JSONL 원본 보존
- 기존 Server 결과 spread 2, fragment 4, duplicate 0 확인
- V3-B/V4 public contract diff 0 확인

### Phase 1 — Observer-only diagnostics

- 기존 Scanner event가 제공하는 selected/collection/observation/decision 필드 확인
- 부족한 terminal abort reason과 valid count만 최소 추가
- Device Runtime feedback/report에 bounded mapping
- secret/raw token/image 비노출과 progress dedup
- diagnostics off/failure 시 state와 결과가 동일함을 검증

### Phase 2 — Deterministic boundary audit

- candidate와 identity lifecycle을 동일 source timeline으로 결합
- 314/315 `candidate 3 + identity 4 + hard reject` 확인
- 318 `candidate 3 + identity 1 + source exhausted` 확인
- 310/311, 312/313가 candidate hard reject임을 확인
- 30/309, 316/317의 N=5 decision과 artifact/ACK lineage 확인

### Phase 3 — Actual Laptop confirmation

- 필요 시 fresh datapack으로 동일 영상을 한 번 재실행
- EOF `queued=2`, `acked=2` 확인
- user confirm 뒤 READY와 reading navigation 확인
- Server receipt 2, fragment 4, duplicate 0 확인
- exact diagnostic report 보존

### Phase 4 — 문서와 handoff

- E0-B.3 verification report 작성
- E0-B Quickstart에 expected result와 dwell 설명 추가
- E0-B.1/E0-B.2 보고서와 PROJECT_HANDOFF의 실제 상태 정합화
- physical acceptance의 remaining scope를 분리 기록

## 8. 테스트 행렬

### 8.1 Existing conservative behavior freeze

- 3 candidate + 4 valid identity + hard reject -> artifact 0
- 3 candidate + 1 valid identity + EOF -> artifact 0
- 3 candidate + 5 valid all-mismatch identity -> DIFFERENT/artifact 1
- accepted reference와 첫 exact match -> SAME 조기 결정/artifact 0
- identity missing/provider error -> valid count 증가 0
- hard reject 뒤 stale collector observation/decision 0
- stable-window frame의 identity 자동 재사용 0
- EOF synthetic/repeated observation 0

### 8.2 Diagnostic observer contract

- candidate selected/identity started attempt당 정확히 1
- valid count가 바뀔 때만 progress 출력
- hard reject reason과 source exhaustion reason 구분
- terminal event attempt당 정확히 1
- raw token/image/API key/model path 노출 0
- diagnostic sink 실패 시 artifact/queue/ACK 결과 변화 0

### 8.3 Exact prepared MP4

- 30/309 sequence 1
- 316/317 sequence 2
- 310/311, 312/313 artifact 0: candidate hard reject
- 314/315 artifact 0: identity 4/5 뒤 hard reject
- 318/12장 시작 artifact 0: identity 1/5 뒤 EOF
- queued 2, acked 2
- V4 receipt 2
- Server left/right fragment 4
- duplicate receipt/spread/fragment 0
- EOF feedback 1
- user confirm 뒤 READY와 reading snapshot/navigation

### 8.4 회귀 기준

구현 전 최신 기준선:

| 프로젝트 | 기준 |
|---|---:|
| Book Scanner | 296 passed |
| Device Runtime | 96 passed |
| Document Parser core | 573 passed, 4 skipped |
| Document Parser hardware bridge | 29 passed |
| Document Parser 합계 | 602 passed, 4 skipped |

추가 테스트로 총수는 증가할 수 있다. 기존 테스트 감소, 새 error 또는 설명되지 않은 skip이 있으면
완료 처리하지 않는다.

## 9. 완료 기준

다음을 모두 만족해야 E0-B.3을 완료로 표시한다.

1. Scanner candidate/identity decision semantics와 threshold가 변경되지 않는다.
2. 동일 영상에서 30/309와 316/317 두 spread만 전송되는 결과를 재현한다.
3. 314/315가 identity 4/5 뒤 hard reject됐음을 구조화 증거로 확인한다.
4. 318이 identity 1/5 뒤 source exhausted됐음을 구조화 증거로 확인한다.
5. 310/311과 312/313는 candidate hard reject로 구분된다.
6. EOF에서 `queued_count=2`, `acked_count=2`가 관측된다.
7. Server receipt 2개, left/right fragment 4개와 duplicate 0을 확인한다.
8. ACK 전 `spread_sent`가 없고 pending bank 승격 순서가 유지된다.
9. EOF가 자동 finalize를 만들지 않고 user confirm 뒤에만 READY가 된다.
10. Laptop이 READY revision의 reading snapshot과 navigation response를 받는다.
11. bounded log/report만으로 각 candidate의 identity terminal reason을 판정할 수 있다.
12. 세 프로젝트 회귀가 최신 기준 이상으로 통과한다.
13. 이 결과를 production capture recall, OCR/TTS 품질 또는 physical hardware 승인으로 확대하지 않는다.

## 10. 예상 변경 파일

주 대상:

- `book-scanner/src/book_scanner/video/engine.py` — terminal diagnostics가 기존 event에 없을 때만 최소 변경
- `book-scanner/src/book_scanner/video/events.py` — 기존 event로 표현할 수 없을 때만 최소 변경
- `book-scanner/tools/` 아래 candidate/identity boundary audit 도구
- `book-scanner/tests/unit/video/test_engine_v3a5.py`
- `device-runtime/src/asl_device/adapters/book_scanner_runtime.py`
- `device-runtime/src/asl_device/events.py`
- `device-runtime/tests/unit/test_book_scanner_runtime.py`
- `device-runtime/tests/unit/test_application.py`
- `tools/windows/e0b-replay-run.bat`
- `LAPTOP_E0B_QUICKSTART.md`
- `device-runtime/docs/device-integration-e0b-laptop.md`
- `DEVICE_INTEGRATION_E0_B_3_VERIFICATION_REPORT.md`
- `PROJECT_HANDOFF_20260831.md`

기본 범위가 아닌 파일:

- `book-scanner/src/book_scanner/video/config.py`
- replay camera/source adapter
- `device-runtime/src/asl_device/app_config.py`
- `tools/windows/e0b-laptop-setup.ps1`
- `document-parser/src/document_parser/server/v4_*`
- Server DB migration/schema
- V3-B delivery/outbox schema
- STM serial adapter와 firmware
- Tailscale Serve 설정

## 11. 승인 경계

승인 시 수행:

- observer-only candidate/identity terminal diagnostics
- exact-video candidate/identity boundary audit와 report
- 관련 unit/integration regression
- Quickstart, E0-B 문서와 handoff의 acceptance 결과 갱신
- 필요할 경우 동일 영상 Laptop confirmation 절차 지원

별도 승인 없이는 수행하지 않음:

- stable-window evidence 재사용 또는 identity acquisition 순서 변경
- replay EOF padding/hold/synthetic observation
- candidate/identity/clipping threshold 변경
- Server/V4/V3-B protocol 또는 schema 변경
- alternate video fixture 생성·배포
- physical camera/STM/speaker acceptance 완료 처리
- 운영 hardening, background service 또는 network 정책 변경
- commit/push/PR

## 12. 중단 조건

다음이면 범위를 조용히 넓히지 않고 보고한다.

- 기존 event와 최소 observer event만으로 identity valid count/terminal reason을 증명할 수 없음
- diagnostics 추가가 Scanner state transition 또는 timing에 영향을 줌
- 314/315가 identity 4/5가 아니라 provider missing 등 다른 이유로 종료됨
- 318이 identity 1/5가 아니라 candidate 미선택 등 다른 이유로 종료됨
- 30/309 또는 316/317 전송이 동일 authority에서 재현되지 않음
- 310/311 또는 312/313가 새로 artifact로 accepted됨
- V4 receipt/fragment count가 expected 2/4와 불일치하거나 duplicate가 발생함
- API key, raw OCR token 또는 image bytes를 기록해야만 진단 가능함

원인 가설이 틀리면 report에 실제 원인을 기록하고 수정 정책을 자동 선택하지 않는다. 다음 항목은
필요성이 확인될 때 각각 별도 승인 패킷으로 분리한다.

```text
short-dwell capture policy
EOF final-candidate policy
candidate/occlusion/clipping calibration
M1 held-out identity validation
physical Laptop acceptance
operations/network hardening
```

## 13. 후속 순서

```text
E0-B.3 replay candidate/identity boundary verification
  -> E0-B remote software acceptance 종료
  -> E0-B physical acceptance(camera + HC-05/STM + speaker)
  -> 필요 시 short-dwell capture policy 별도 패킷
  -> 필요 시 Scanner calibration/held-out validation
  -> Raspberry Pi 및 network operations hardening
```

E0-B.3은 더 많은 페이지를 전송하도록 Scanner를 완화하는 패킷이 아니다. 이미 성공한 remote
transport/lifecycle과 보수적으로 거부된 candidate를 구분할 수 있는 증거를 남기고, 현재 prepared MP4의
정상 기대값을 명확히 하여 software acceptance를 종료하는 패킷이다.
