# Scanner Video V3-A.3 — Paddle Recognition-Only & VisualGate Value Evaluation 작업 패킷

상태: **승인 범위 구현·실험 완료 — Paddle 후보 유지 / 750ms VisualGate 가치 gate 실패**
작성일: 2026-08-31
승인·실행일: 2026-08-31
선행 조건: V2 `seam-conservative + UVDoc bilinear`, V3-A visual identity/page-change gate,
V3-A.1 bottom ROI·`SpreadPageKey`·fusion·cache 계약, V3-A.2 temporal replay
후속 조건: page-number verification scheduler 선발 후 Scanner V3-A 계열의 기본 composition 결정

## 1. 결정 배경

V3-A.2의 경량 ONNX 숫자 분류기는 corrected artifact에서는 후보가 되었지만 1920px preview에서
안정적인 complete key를 만들지 못했다. 반면 기존 Paddle `en_PP-OCRv5_mobile_rec` recognition-only
실험은 corrected p30 세 spread에서 좌우 3/3을 맞혔고, 영상 preview 진단에서도 frame 720의
`30/309`, frame 2220의 `316/317`을 complete로 관찰했다. PC 지연은 corrected 양쪽 spread 기준
약 159.956ms로 경량 모델보다 느리지만 현재 750ms sampling 간격에는 비교 가능한 후보다.

따라서 다음 후보는 전체 Document Parser나 PaddleOCR-VL layout pipeline이 아니라, Scanner가
잘라낸 좌우 bottom ROI에만 적용하는 **로컬 persistent Paddle recognition-only backend**로 둔다.

다만 현재 구조와 V3-A.2 replay 결과만으로는 “VisualGate가 Paddle 호출을 충분히 줄인다”고 말할
수 없다. 현재 engine은 candidate hard gate를 통과한 모든 page-change 표본에서 page-number
provider를 호출한다. visual identity 비교는 같은 poll 안에서 fusion에 사용되지만 OCR 호출을
사전에 억제하지 않는다. V3-A.2의 다음 수치도 VisualGate 절감률이 아니다.

| cadence | baseline 뒤 표본 | candidate-eligible 표본 | backend `recognizer_calls` |
|---:|---:|---:|---:|
| 500ms | 66 | 12 | 36 |
| 750ms | 44 | 10 | 28 |
| 1000ms | 33 | 5 | 16 |

`recognizer_calls`는 baseline 전·후 좌우 ROI와 accepted corrected baseline 처리가 섞인 backend 내부 카운터이므로
표본 수로 직접 나눌 수 없다. candidate-eligible 표본이 적었던 것은 기존 blur·mask·손·이동 등의
hard gate 결과이며, VisualGate 단독의 호출 억제 효과를 증명하지 않는다.

본 패킷은 Paddle 정확도 평가와 함께 이 계측 공백을 먼저 해소한다. VisualGate가 비용·지연·정확도
중 하나라도 실질적으로 개선하지 못하면 gate 기반 scheduler를 채택하지 않고, 매 eligible sample
Paddle 호출 또는 더 단순한 주기 정책을 선택한다.

## 2. 용어와 책임 분리

혼동을 막기 위해 다음 세 계층을 별도 단계와 별도 지표로 기록한다.

1. **Candidate hard gate**
   - 페이지 mask 누락, 손 가림, `PAGE_MOVING`, blur 등 OCR 입력으로 부적합한 표본을 제외한다.
   - 안전성 gate이며 VisualGate 절감률에 포함하지 않는다.
2. **VisualGate**
   - hard gate를 통과한 preview와 accepted baseline의 좌우 visual fingerprint를 비교해
     `same`, `changed`, `ambiguous` evidence를 만든다.
   - 본 패킷에서만 Paddle 호출 scheduler의 입력 후보가 된다.
3. **Paddle verification 및 temporal consensus**
   - 호출된 좌우 bottom ROI에서 complete/partial/conflict/missing `SpreadPageKey`를 생성한다.
   - 서로 다른 complete key의 연속 K회 합의와 visual evidence를 함께 사용해 page change를 확정한다.

VisualGate의 출력은 페이지 번호 정답이 아니며, Paddle 결과도 단독 1회만으로 release 근거가 되지
않는다.

## 3. 목표

- 동일 원본 영상과 동일 sampling frame에서 Paddle recognition-only의 preview page-key 품질 측정
- hard gate, VisualGate, Paddle scheduler 각각의 호출 억제량을 독립 계측
- 매 eligible sample 호출을 기준선으로 두고 VisualGate scheduler가 실제 호출·CPU duty를 줄이는지 검증
- 호출 절감 때문에 page change를 놓치거나 늦추는 비용을 함께 측정
- same-page, 손·이동, single OCR spike, 실제 page turn에서 false/missed/duplicate release 검증
- CPU와 사용 가능한 GPU에서 persistent load·latency·RSS·호출 수 기록
- 결과에 따라 `EVERY_ELIGIBLE`, `VISUAL_TRIGGERED`, `HYBRID_AUDITED` 중 하나를 근거 있게 선발
- 선발 실패 시 현재 `validated=false`, visual fallback 및 explicit provider opt-in 유지

## 4. 비목표

- Document Parser/PaddleOCR-VL 전체 pipeline 호출
- 전체 페이지 text detection 또는 OCR
- seam, page mask, crop, UVDoc threshold 재튜닝
- HTTP 송신, retry/outbox, 서버 idempotency 또는 Coordinator 변경
- page-number-only duplicate suppression 활성화
- Pi 4 성능을 PC 측정으로 추정하거나 완료 처리
- paid cloud OCR 도입
- p30 영상에 맞춘 Paddle model fine-tuning

## 5. 입력 자료와 정답 경계

### 5.1 고정 자료

- 원본 MP4: 3840×2160, 2,677 frames, 59.699650767fps
- SHA-256: `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
- accepted corrected baseline: frame 780 계열 artifact, complete `30/309`
- 사용자 확인 clean anchor: frame 720, 780, 2220
- 사용자 확인 `HAND_CONTENT_OCCLUSION`: 900, 1170, 1380, 1920, 1980, 2400, 2580
- 사용자 확인 `PAGE_MOVING`: 1500, 2040
- p30 corrected 세 촬영본과 golden left `30`

### 5.2 추가 사람 확인

다음은 provisional replay에는 사용할 수 있지만 production gate 통과에는 사람 확인이 필요하다.

- frame 2220 spread의 좌 `316`, 우 `317`
- p30/309 안정 구간의 종료 경계
- p316/317 안정 구간의 시작 경계
- 경계 safety margin 밖의 stable-run 범위

확인 전에는 모델 예측이나 visual 비교 결과를 정답으로 승격하지 않는다. stable-run label이 부족하면
정확도와 release delay는 `PROVISIONAL_DATA_INSUFFICIENT`로 남긴다.

## 6. 비교할 호출 정책

모든 정책은 같은 cadence frame, 같은 hard-gate 판정, 같은 bottom ROI, 같은 Paddle output을 사용한다.
모델 추론의 비결정성이나 warm-up 차이가 scheduler 비교를 왜곡하지 않도록 1차 pass에서 frame별
Paddle 결과와 지연을 기록하고, scheduler replay는 이 frozen observation을 재사용한다. 별도 live
pass로 실제 wall time을 확인한다.

### P0 — `EVERY_ELIGIBLE` 기준선

- candidate hard gate를 통과한 모든 sampling 표본에서 좌우 Paddle 호출
- VisualGate는 최종 fusion 진단에는 사용하되 호출을 억제하지 않음
- 현재 engine의 provider 호출 위치와 가장 가까운 control
- 정확도·최소 검출 지연의 기준이며, 나머지 정책의 절감률 분모

### P1 — `VISUAL_TRIGGERED`

- baseline 대비 확실한 visual same이면 Paddle 호출 0
- visual changed 또는 양면 변화 조건을 만족하는 changed-compatible ambiguous이면 verification burst 진입
- burst 동안 eligible sampling 표본마다 Paddle을 호출해 K개의 동일한 different complete key를 요구
- single changed spike, 한쪽만 변한 ambiguous, 움직임/가림 표본은 burst를 시작하거나 유지하지 않음
- burst timeout 또는 partial/conflict 연속 시 release하지 않고 visual fallback 또는 재관찰

### P2 — `HYBRID_AUDITED`

- P1과 동일하되 visual same 구간에서도 N번째 eligible sample마다 audit Paddle 호출
- audit 목적은 VisualGate가 실제 새 페이지를 same으로 오판하는 false skip 검출
- 초기 비교 후보: N=4. 750ms에서 hard-gate eligible 상태가 계속된다는 가정하에 약 3초 간격이지만,
  실제 wall time은 eligible 간격을 따로 기록한다.
- visual changed 시에는 audit 주기를 기다리지 않고 즉시 verification burst

### P3 — 단순 저주기 control

- VisualGate 없이 Paddle만 1500ms마다 호출하는 control을 선택적으로 포함
- VisualGate의 복잡성 없이 비슷한 호출 절감과 허용 가능한 지연을 얻는지 확인
- P1/P2가 P3보다 명확히 낫지 않으면 VisualGate scheduler를 우선 채택하지 않음

정책의 이름과 조건은 config에 명시하며 숨은 default나 backend별 분기를 만들지 않는다.

## 7. VisualGate 효과 지표

각 cadence와 정책마다 다음 count를 반드시 별도로 저장한다.

- `sampled_spreads`: baseline 이후 sampling한 spread 수
- `hard_gate_rejected_spreads`: candidate hard gate에서 제외된 수
- `eligible_spreads`: `sampled - hard_gate_rejected`
- `visual_same`, `visual_changed`, `visual_ambiguous`, `visual_error`
- `paddle_requested_spreads`: scheduler가 Paddle verification을 요청한 spread 수
- `paddle_completed_spreads`: 좌우 결과가 반환된 spread 수
- `paddle_roi_calls`: 실제 좌/우 recognizer call 수
- `paddle_cache_hits`: 실제 backend call을 대체한 exact ROI cache hit 수
- `verification_bursts`, burst별 길이·성공·timeout·reset 원인
- `audit_calls`와 audit이 발견한 visual false skip 수

핵심 비율은 서로 다른 분모로 기록한다.

- hard-gate rejection = `hard_gate_rejected / sampled`
- VisualGate incremental suppression =
  `1 - paddle_requested_spreads / eligible_spreads`
- total Paddle suppression =
  `1 - paddle_requested_spreads / sampled_spreads`
- P0 대비 runtime call reduction =
  `1 - candidate_policy_roi_calls / P0_roi_calls`
- useful trigger precision = 실제 changed stable-run에서 시작된 burst / 전체 burst
- changed-run trigger recall = 사람 확인 page turn 중 timeout 전에 burst가 시작된 비율
- false-skip rate = 실제 changed stable 표본을 visual same으로 분류해 Paddle을 건너뛴 비율

`recognizer.calls` 하나만으로 절감률을 보고하지 않는다. spread request와 좌우 ROI 실행을 구분하며,
accepted baseline 인식·warm-up·cache hit는 별도 bucket으로 둔다.

## 8. 성공 기준과 채택 규칙

### 8.1 안전성·정확도 gate

- p30/309 stable run false `PAGE_CHANGED`: 0
- 사용자 확인 손·이동 anchor에서 Paddle consensus 증가: 0
- single wrong/changed spike release: 0
- 사람 확인 p30/309 → p316/317 turn에서 release: 정확히 1
- confirmed different page를 same complete key로 오인: 0
- visual same + different number, visual new + same number 충돌은 자동 release/suppression하지 않음
- partial/missing/conflict 한 번 또는 반복만으로 release: 0

### 8.2 VisualGate 가치 gate

P1/P2는 P0와 동일한 안전성·page-turn recall을 만족한 뒤에만 비용을 비교한다. 다음을 모두 충족해야
VisualGate scheduler를 기본 후보로 기록한다.

1. P0 대비 `paddle_requested_spreads` **30% 이상 감소**
2. 사람 확인 page turn의 missed release 증가 0
3. P0 대비 release delay 증가의 observed p95가 **750ms 이하**
4. visual false skip 때문에 K consensus가 불가능해진 page turn 0
5. verification burst의 대부분이 same-page 노이즈가 아님; useful trigger precision **50% 이상**

30%와 750ms는 provisional engineering threshold이며 실험 결과에 맞춰 조용히 변경하지 않는다.
자료가 적어 p95를 의미 있게 계산할 수 없으면 개별 delay와 maximum을 기록하고
`PROVISIONAL_DATA_INSUFFICIENT`로 판정한다.

### 8.3 정책 선택

- P1이 가치 gate 통과: `VISUAL_TRIGGERED` 후보
- P1이 false skip을 만들고 P2 audit이 이를 복구하며 가치 gate 통과: `HYBRID_AUDITED` 후보
- P1/P2 절감 <30% 또는 지연/누락 악화: VisualGate scheduler 기각
- P3가 P1/P2와 동등한 안전성·호출 수·지연: 복잡성이 낮은 P3 우선
- 모든 절감 정책 실패, P0가 성능 budget 충족: `EVERY_ELIGIBLE` 후보
- P0도 latency/RSS/정확도 gate 실패: Paddle production 선발 보류

즉 VisualGate는 유지해야 할 전제가 아니라 비교 대상이다.

## 9. Sampling 및 temporal 설정

- 기준: 750ms, number K=3, visual K=3
- 비교: 500/750/1000ms
- P3 control: 1500ms
- visual changed trigger가 발생하면 base cadence와 별개의 빠른 thread를 만들지 않고 다음 eligible poll에서
  verification을 이어간다. 초기 구현에서 동시 추론이나 frame queue를 추가하지 않는다.
- transition/motion/obstruction은 visual·number stable count와 active burst를 reset한다.
- burst 최대 길이 후보: eligible 5 samples. 초과 시 자동 release가 아니라 timeout/fallback 이벤트
- session/datapack/cancel/ACK 전환 시 scheduler, audit counter, burst, page-key consensus를 reset

500/750/1000ms 중 가장 좋아 보이는 단일 결과만으로 기본 cadence를 바꾸지 않는다. 최종 권고에는
false release, missed release, delay, call duty를 같이 제시한다.

## 10. Paddle runtime 경계

- backend: 로컬 `en_PP-OCRv5_mobile_rec`, recognition-only
- 입력: 기존 locator가 만든 좌우 bottom ROI; detector 및 full-page OCR 금지
- 명시적 model directory와 asset manifest/SHA-256 사용
- runtime 자동 model download와 network access 0
- process/session 중 model load count 1
- 기존 `PaddleRoiDigitRecognizer`를 재사용하되 model asset 완전성·hash 검사를 보강
- CPU와 사용 가능한 GPU를 분리 측정; 장치 fallback을 조용히 성공으로 처리하지 않음
- CPU/GPU 결과 차이와 confidence를 기록
- Pi 4는 실제 측정 전 `NOT_MEASURED`

PC prototype 성능 budget 후보:

- P0/P1/P2별 warm spread latency median, observed p95, max 기록
- 750ms cadence에서 end-to-end page-change loop duty cycle observed p95 ≤40%
- cold load ≤5초
- process RSS 증분 ≤1.5GiB
- frame backlog 0, 동시에 진행되는 Paddle inference 1개 이하

Paddle가 경량 모델보다 큰 것은 허용하되, Scanner가 사용하는 단일 recognition model과 실제 비용만
측정한다. Document Parser의 PaddleOCR-VL model/RSS를 합산하거나 Scanner 비용으로 숨기지 않는다.

## 11. 구현 단계

### Phase 0 — 계측 계약 수정

- 기존 V3-A.2 replay에서 count 단위가 섞인 문제를 재현·기록
- spread request, side ROI call, baseline, warm-up, cache hit counter 분리
- CandidateGate와 VisualGate 결과를 매 sampled frame에 기록
- frozen Paddle observation schema와 provenance 작성

### Phase 1 — Paddle offline composition

- 기존 persistent `PaddleRoiDigitRecognizer` asset/hash/load failure 경계 보강
- corrected artifact와 preview anchor 재평가
- 모델 자동 다운로드가 발생하지 않는 offline preflight
- CPU와 사용 가능한 GPU result/latency parity 기록

### Phase 2 — Scheduler를 engine 의미와 분리 구현

- `EVERY_ELIGIBLE`, `VISUAL_TRIGGERED`, `HYBRID_AUDITED`, 단순 저주기 control 구현
- VisualGate는 backend를 직접 소유하지 않고 `request/skip/audit/burst/reset` 결정만 반환
- page-number provider 및 cache 계약은 유지
- 정책별 skip 이유와 burst 상태를 구조화 event/diagnostics에 추가

### Phase 3 — 동일 영상 paired replay

- 한 번 만든 frozen Paddle observation으로 모든 정책·cadence replay
- same frame set을 보장하고 정책별 release lineage 비교
- 별도 live replay로 wall time, RSS, model load, 실제 호출 수 확인
- hard gate, visual incremental, total suppression을 각각 산출

### Phase 4 — 선발·회귀·보고

- 가치 gate에 따라 정책 채택/기각/보류
- selected composition은 여전히 explicit opt-in 및 `validated=false`
- 전체 Book Scanner 회귀, no Document Parser call, delivery lifecycle 불변식 검증
- 구현 보고서에 미검증 label, Pi, server 항목을 남김

## 12. 테스트 행렬

### 12.1 Scheduler 단위 테스트

- hard-gate rejected: VisualGate 및 Paddle request 0
- visual same: P1 Paddle request 0
- visual changed: 즉시 burst 진입 및 Paddle request 1
- changed-compatible ambiguous: 정책에 따라 burst; 한쪽만 changed ambiguous는 request 또는 release 금지
- P2 visual same N-1회 skip, N회 audit
- motion/obstruction: burst·K·audit 연속성 reset
- missing/partial/conflict: K 증가 0
- different complete key K-1회: release 0, K회: release 1
- single wrong complete spike: release 0
- burst timeout: release 0, 구조화 fallback
- session/datapack/cancel reset 후 이전 key/counter 재사용 0

### 12.2 계측 테스트

- `eligible = sampled - hard_rejected` 보존
- spread request와 ROI call count 혼합 금지
- baseline/warm-up/cache hit 별도 집계
- P0의 eligible spread는 모두 Paddle requested
- P1 skip 합과 request 합이 eligible count와 일치
- frozen replay에서 정책 간 Paddle output 동일

### 12.3 Engine·delivery 회귀

- accepted same-page는 새 artifact/transfer request 0
- 새 page release 뒤 search/capture는 1회만 재개
- pending/upload/retry 중 새 후보 준비 0
- stale/repeated ACK, reject, cancel ownership 변화 0
- `allow_number_only_duplicate=false` 유지
- provider load/error 시 crash가 아니라 명시적 visual fallback
- Document Parser import/call 0, HTTP/server call 0

## 13. 예상 파일 경계

```text
src/book_scanner/video/
  page_number_recognizer.py       # persistent Paddle offline/hash 경계
  page_number_scheduler.py        # 호출 정책과 burst/audit 상태
  config.py                       # explicit scheduler policy, provisional thresholds
  engine.py                       # scheduler decision에 따른 provider 호출
  events.py                       # request/skip/audit/burst diagnostics

tools/
  run_scanner_video_v3a3_paddle_capture.py
  run_scanner_video_v3a3_scheduler_replay.py
  summarize_scanner_video_v3a3_value.py

experiment_inputs/
  scanner_video_v3a3_temporal_labels.json
  scanner_video_v3a3_paddle_model_manifest.json

experiment_outputs/scanner_video_v3a3_<date>/
  frozen_paddle_observations.json
  scheduler_replay.json
  live_performance.json
  summary.json
```

기존 파일명은 구현 시 실제 구조에 맞게 최소 조정할 수 있으나, scheduler와 recognizer 책임은
분리한다.

## 14. 완료 기준

- VisualGate가 현재 OCR 호출을 억제하지 않는다는 baseline을 test/report로 고정
- mixed-unit `recognizer_calls`를 spread/ROI/baseline/cache 단위로 분리
- Paddle recognition-only offline persistent backend 및 asset provenance 검증
- 500/750/1000ms P0/P1/P2 paired replay와 선택적 P3 control 완료
- CandidateGate와 VisualGate의 독립 절감률 보고
- false skip, useful trigger precision, page-turn delay, false/missed release 보고
- CPU 및 사용 가능한 GPU latency/RSS/load/call 수 보고
- 정책 하나를 선발하거나 gate에 근거해 명시적으로 보류
- Book Scanner 전체 회귀 통과
- 실제 확인하지 않은 p316/317, stable boundaries, Pi 4, server 사항은 완료 처리하지 않음
- `SCANNER_VIDEO_V3_A_3_IMPLEMENTATION_REPORT.md` 작성

## 15. 중단·보류 조건

다음 조건에서는 범위를 확대하거나 threshold를 p30에 재튜닝하지 않고 결과를 보고한다.

- Paddle model이 runtime network download를 요구하거나 asset/license provenance를 고정할 수 없음
- corrected golden 또는 preview에서 wrong complete가 발생해 temporal safety가 확보되지 않음
- 사람이 확인한 different-page/stable-run label이 없어 false skip·release recall을 판정할 수 없음
- VisualGate가 실제 changed stable frame을 same으로 지속 오판
- P1/P2가 P0 대비 30% 호출 절감을 만들지 못함
- 호출 절감이 page-turn 누락 또는 허용 범위 초과 지연과 교환됨
- P0조차 750ms loop budget, RSS 또는 single-inference 조건을 만족하지 못함
- scheduler 도입이 session/delivery/lineage 불변식을 깨야만 동작함

이 경우 우선순위는 다음과 같다.

1. P0가 안전·성능 gate를 통과하면 단순 `EVERY_ELIGIBLE`을 provisional 후보로 유지
2. 단순 1500ms control이 충분하면 VisualGate scheduler 대신 이를 검토
3. Paddle 자체가 부적합하면 page-number production 선발을 보류하고 V3-A visual fallback 유지

## 16. 승인 경계

승인 시 Phase 0~4의 구현·실험·보고를 수행한다. 다음은 별도 승인 없이는 수행하지 않는다.

- `validated=true` 또는 `allow_number_only_duplicate=true` 전환
- default cadence/scheduler의 production 승격
- 신규 paid OCR 또는 cloud API 도입
- Document Parser, server, Coordinator, HTTP/outbox 변경
- Raspberry Pi 배포·카메라/GPIO/TTS 통합
- 외부 모델 자동 다운로드 또는 출처 불명 asset 배포
- 원격 branch push, PR 생성 또는 기존 사용자 변경 정리
