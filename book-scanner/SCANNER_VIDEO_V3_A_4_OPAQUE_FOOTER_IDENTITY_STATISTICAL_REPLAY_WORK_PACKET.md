# Scanner Video V3-A.4 — Opaque Footer Identity Statistical Replay 작업 패킷

상태: **승인·구현 완료 — 실험 전용 / production 중복 억제 활성화 안 함**  
작성일: 2026-08-31  
선행 조건: V3-A visual identity/page-change gate, V3-A.3 Paddle scheduler 실험,
`PAGE_NUMBER_RECOGNITION_STAGE_PAIRED_EXPERIMENT_REPORT.md`  
후속 조건: 통계적 분리력이 확인될 때만 Scanner engine integration 패킷을 별도 작성

구현·실험 결과는 `SCANNER_VIDEO_V3_A_4_IMPLEMENTATION_REPORT.md`에 기록했다. 현재 결론은
`PROVISIONAL_CANDIDATE_DATA_INSUFFICIENT`이며 production integration은 수행하지 않았다.

## 1. 결정 배경

현재 목표는 페이지 번호를 정확한 정수로 복원하는 것이 아니라 **이미 전송한 spread와 현재
후보 spread가 같은지 판정하여 중복 전송을 막는 것**이다. 이 목적에서는 `30`, `309` 같은
의미적 정답이 필수적이지 않다. 고정 구도의 책 하단 ROI에서 반복 생성되는 OCR 문자열이나
시각 특징은, 실제 번호와 달라도 재현성과 페이지 간 충돌률이 충분히 분리된다면 불투명한
identity token으로 사용할 수 있다.

직전 인식 시점 paired 실험은 다음 두 사실을 보였다.

- 1920 preview에서 누락된 p30 우측 `309`는 native ROI에서 복구됐다.
- native ROI는 p316 현재 번호 `316` 대신 페이지 더미에 노출된 이전 번호 `30`을 반복 선택해
  서로 다른 spread 간 충돌을 만들었다.

따라서 한 번의 exact OCR 결과나 의미적 페이지 번호만으로 판정하지 않는다. 동일 페이지
반복 관찰의 일치확률 `p_same`, 서로 다른 페이지 반복 관찰의 충돌확률 `p_diff`, 시행 수 `N`,
필요 일치 수 `K`를 함께 측정해야 한다.

독립 시행을 가정한 참고식은 다음과 같다.

- N회 모두 불일치: `(1 - p_same)^N`
- N회 중 한 번 이상 우연히 일치: `1 - (1 - p_diff)^N`

`p_same=0.5`, `N=10`이면 모두 불일치할 이상적 확률은 약 0.0977%이고, N=14이면 약
0.0061%다. 그러나 연속 영상 프레임은 독립 시행이 아니므로 이 식을 실측 오류율로 간주하지
않는다. 본 패킷은 시간 자기상관과 effective sample size를 별도로 기록한다.

## 2. 핵심 결정

본 패킷은 기존 의미적 `SpreadPageKey`를 바로 교체하지 않는다. production engine 밖의 frozen
replay에서 다음 질문만 답한다.

1. 정확한 숫자 정답 없이 footer 관찰을 opaque token으로 사용해 같은 페이지와 다른 페이지를
   통계적으로 분리할 수 있는가?
2. `N회 중 한 번 일치`보다 안전한 `K-of-N` 또는 3상태 판정이 존재하는가?
3. OCR token, 시각 지문, 두 방법의 혼합 중 어느 것이 가장 낮은 오중복률을 만드는가?
4. 시행 간격을 늘렸을 때 nominal N이 실제 독립 증거에 가까워지는가?
5. 기존 전체 페이지 VisualGate에 비해 footer evidence가 추가 가치를 제공하는가?

결과는 `CANDIDATE`, `REJECTED`, `PROVISIONAL_DATA_INSUFFICIENT` 중 하나로만 기록한다.
어떤 결과도 본 패킷 안에서 `validated=true` 또는 자동 중복 억제 활성화로 이어지지 않는다.

## 3. 용어와 판정 단위

### 3.1 `FooterObservation`

한 eligible full-spread frame에서 좌우 각각 다음을 저장한다.

- source video/frame/timestamp, side, ROI bbox/shape/SHA-256
- CandidateGate와 mask/seam provenance
- Paddle first-candidate의 original/CLAHE raw 문자열과 score
- 기존 provider의 selected raw token/status; 의미적 normalization은 control에만 사용
- footer ROI의 경량 visual descriptor
  - pHash 또는 dHash
  - 수평·수직 명암 projection
  - 정규화된 저해상도 patch 또는 NCC용 요약
- 누락, conflict, 빈 문자열, 후보 수

빈 문자열, locator 실패, `NOT_OBSERVED`를 서로 같은 token으로 취급하지 않는다. 두 missing
결과가 같다는 이유로 `SAME` evidence를 만들지 않는다.

### 3.2 Reference bank와 query bank

- **Reference bank**: 전송·ACK된 spread의 안정 eligible 관찰 N개
- **Query bank**: page-turn 이후 현재 후보 spread의 안정 eligible 관찰 N개
- 같은 bank 안의 프레임은 시간 순서를 보존한다.
- reference와 query는 겹치는 frame 또는 같은 JPEG artifact를 공유하지 않는다.
- OCR 결과를 보고 bank에 포함할 frame을 선택하지 않는다.

reference bank를 먼저 고정한 뒤 각 query 관찰이 reference bank와 일치하는지를 1회의 증거로
센다. reference×query의 N² pair를 독립 시행 N²개로 계산하지 않는다.

### 3.3 3상태 판정

query 관찰 N개 중 reference bank와 match한 횟수를 `S`라고 한다.

- `SAME`: `S >= K_same`
- `DIFFERENT`: `S <= K_diff`
- `UNKNOWN`: `K_diff < S < K_same`
- 제약: `0 <= K_diff < K_same <= N`

`N회 중 한 번이라도 동일`은 `K_same=1`인 binary control로만 평가한다. production 후보는
`UNKNOWN`을 허용해 모호한 경우 더 관찰하도록 설계한다.

## 4. 비교 방법

모든 방법은 동일 frame banks와 동일 cadence를 사용한다.

### M0 — Semantic page key control

- 기존 normalized page label과 complete `SpreadPageKey`
- 현재 방식과의 비교 기준이며 opaque 접근의 목표가 아님
- partial/conflict/missing은 match evidence 0

### M1 — Selected raw OCR token

- 정확한 번호인지 보지 않고 provider가 선택한 non-empty raw 문자열의 exact equality만 사용
- 좌우 token pair가 모두 일치할 때 spread match
- confidence/semantic range는 진단값으로 남기되 token 의미는 검사하지 않음

### M2 — Variant token-set overlap

- 좌우 first candidate의 original/CLAHE non-empty 출력 집합 사용
- 각 side에서 집합 교집합이 존재하고, 양쪽 side가 모두 만족할 때 spread match
- missing-to-missing, empty-to-empty는 match 금지
- `30`처럼 여러 spread에 반복 노출되는 stale footer 충돌을 별도 집계

### M3 — Footer visual fingerprint

- OCR을 호출하지 않고 좌우 footer ROI의 경량 visual descriptor 비교
- 양쪽 side가 fixed threshold를 만족할 때 spread match
- pHash Hamming, projection MAE, NCC를 개별/결합 control로 기록
- threshold는 calibration fold에서만 선택하고 hold-out에서 재튜닝하지 않음

### M4 — Hybrid

- visual strong match 또는 `visual compatible + OCR token overlap`을 match evidence로 사용
- OCR 한 번 일치만으로 visual contradiction을 무시하지 않음
- 기존 full-page VisualGate의 `same/changed/ambiguous`도 별도 evidence로 기록
- footer 결과와 full-page VisualGate가 충돌하면 자동 `SAME/DIFFERENT`가 아니라 `UNKNOWN`

## 5. 고정 입력 자료와 정답 경계

### 5.1 현재 사용 가능한 자료

- 원본: `20260830_133526.mp4`
- SHA-256: `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
- 3840×2160, 2,677 frames, 59.699650767fps
- 사용자 확인 clean anchor: 720, 780, 2220
- 사용자 확인 손 가림: 900, 1170, 1380, 1920, 1980, 2400, 2580
- 사용자 확인 page moving: 1500, 2040
- 진단 stable window
  - p30: 690~810
  - p316: 2190~2250
- p30 왼쪽 `30`: 사용자 golden
- p30 오른쪽 `309`, p316 `316/317`, stable-window 경계: diagnostic label

현재 자료에서 p30↔p316은 different-spread negative로 쓸 수 있지만, 두 spread만으로 일반적인
오중복률을 검증했다고 선언하지 않는다. 숫자 정답이 diagnostic이어도 서로 다른 촬영 구간이라는
사실은 identity 실험에 사용할 수 있으며, 구간 경계의 불확실성은 그대로 기록한다.

### 5.2 분할과 누수 방지

- 한 stable run을 앞/뒤의 시간적으로 분리된 contiguous block으로 나눈다.
- 같은 frame과 인접 duplicate frame을 reference/query 양쪽에 넣지 않는다.
- calibration fold에서 descriptor threshold와 K를 선택하고 hold-out fold에는 고정 적용한다.
- fold를 바꾼 역방향 replay도 수행하되 각 결과를 독립 표본 수로 부풀리지 않는다.
- overlapping rolling window 결과는 민감도 분석으로만 표시한다.
- 사람이 확인한 occlusion/moving frame은 same/different bank에서 제외하고 negative safety로 사용한다.

## 6. N·K·sampling 실험 행렬

### 6.1 Sampling 간격

- 100ms, 250ms, 500ms, 750ms, 1000ms
- 각 간격에서 CandidateGate eligible frame만 bank에 포함
- 실제 timestamp 간격, 탈락 수, bank 구축 시간을 기록
- stable window 길이 때문에 필요한 N을 만들 수 없는 조합은 보간하거나 중복하지 않고
  `NOT_MEASURED_INSUFFICIENT_WINDOW`로 남김

### 6.2 시행 수 N

- N = 3, 5, 8, 10, 14, 20
- reference/query bank는 같은 nominal N을 사용
- 순차 판정에서는 최대 N까지 수집하되 더 이른 판정 가능 시 first-decision sample 수를 기록

### 6.3 Threshold grid

- 모든 `0 <= K_diff < K_same <= N` 조합 replay
- `K_same=1` any-match control을 반드시 포함
- 가장 좋아 보이는 한 조합만 보고하지 않고 Pareto frontier를 저장
  - false duplicate
  - false different
  - UNKNOWN
  - first-decision N
  - latency/call cost

## 7. 통계 계획

### 7.1 핵심 확률

- `p_same`: 같은 spread의 disjoint reference/query에서 query 관찰이 match할 확률
- `p_diff`: 서로 다른 spread에서 query 관찰이 reference와 충돌할 확률
- `false_duplicate`: 실제 DIFFERENT를 SAME으로 판정
- `false_different`: 실제 SAME을 DIFFERENT로 판정
- `abstention`: UNKNOWN 비율

오중복은 새 페이지를 전송하지 못하게 할 수 있으므로 오변경보다 우선순위가 높다.

### 7.2 독립성 처리

- token-match indicator와 visual distance의 lag autocorrelation 기록
- contiguous frame을 단위로 한 block bootstrap confidence interval 사용
- nominal N과 estimated effective N을 함께 보고
- theoretical binomial 결과는 `independence_reference_only`로 분리
- N² cross-pair 수를 sample size로 보고하지 않음

### 7.3 희소 자료 해석

- 현재 두 spread에서 error 0이어도 일반 오류율 0으로 쓰지 않음
- zero-error upper confidence bound와 실제 독립 block 수를 함께 표시
- p30 또는 p316 한쪽에만 맞춘 threshold는 후보 탈락
- confidence interval이 넓거나 `p_same`/`p_diff` 분리가 불명확하면
  `PROVISIONAL_DATA_INSUFFICIENT`

## 8. 실험 성공 기준

본 패킷의 성공은 production 활성화가 아니라 **재현 가능한 통계 결과와 후보 선발 또는 보류**다.

### 8.1 실행 완전성 gate

- 원본 video/model hash 검증
- frame bank와 split provenance 완비
- frozen observation을 모든 N/K 방법이 공통 사용
- runtime model download/network access 0
- 동일 seed/replay에서 결과 JSON 동일
- infeasible N/cadence를 명시적으로 NOT_MEASURED 처리

### 8.2 Diagnostic candidate gate

다음 조건을 모두 만족하는 방법만 후속 integration 후보로 기록한다.

1. disjoint hold-out의 p30↔p316 양방향에서 `false_duplicate` 0
2. same-spread hold-out에서 자동 `DIFFERENT` 0
3. `p_same` point estimate가 `p_diff`보다 모든 fold에서 큼
4. `N <= 14` 중 UNKNOWN을 포함한 안전한 operating point 존재
5. any-match control보다 false-duplicate/UNKNOWN trade-off가 악화되지 않음
6. 페이지 더미의 이전 `30` 충돌이 단독 SAME을 만들지 않음
7. M3/M4의 PC descriptor 처리 median ≤10ms/side

표본 부족으로 confidence interval 분리를 입증하지 못하면 gate 1~7을 관찰상 만족해도
`PROVISIONAL_CANDIDATE_DATA_INSUFFICIENT`로만 기록한다.

### 8.3 Production activation에 부족한 것

후속 활성화에는 최소한 다음 자료가 추가로 필요하며 본 패킷 완료 조건이 아니다.

- 여러 서로 다른 spread의 held-out negative
- 다른 조명·그림자·부분 잘림·비정렬 stable sample
- 실제 page-turn 뒤 새로운 spread를 SAME으로 억제하지 않는 반복 검증
- 선택한 cadence에서 충분한 독립 block 수
- Pi 4 실측 또는 명시적인 PC-only prototype 결정

## 9. 실행 단계

### Phase 0 — Pre-registration 및 manifest 고정

- source/model hash, stable/negative 구간, split 규칙 고정
- 방법 M0~M4, cadence/N/K grid, exclusion reason을 JSON manifest로 작성
- 실험 결과를 보기 전에 candidate gate와 status vocabulary 고정

### Phase 1 — Frozen observation capture

- 원본 영상을 한 번 forward decode
- 기존 CandidateGate·mask·seam으로 eligible frame 결정
- 1920 footer ROI를 기본 입력으로 저장
- native ROI는 직전 실험의 stale-page 충돌 control로만 함께 저장
- Paddle persistent load 1회로 raw selected/variant token 수집
- 같은 ROI에서 visual descriptor 생성
- ROI, candidate overlay, descriptor/token provenance와 latency 저장
- UVDoc와 Document Parser는 호출하지 않음

### Phase 2 — Bank builder와 match matrix

- disjoint contiguous blocks로 reference/query bank 생성
- same p30, same p316, p30→p316, p316→p30 행렬 작성
- M0~M4의 frame-level match matrix 고정
- empty/missing/stage-error와 stale footer collision을 별도 counter로 기록

### Phase 3 — Statistical replay

- cadence/N/K 전 조합 replay
- binary any-match와 SAME/DIFFERENT/UNKNOWN 비교
- block bootstrap, autocorrelation, nominal/effective N 산출
- sequential first-decision N과 예상 wall delay 계산
- false duplicate, false different, abstention Pareto frontier 저장

### Phase 4 — Stress·ablation

- p316 ROI에 함께 보이는 이전 `30` 제거 전/후 비교
- OCR selected token 대 variant-set의 충돌률 비교
- 1920/native 전면/native missing-side-only 비교
- visual descriptor 구성요소별 ablation
- full-page VisualGate 단독 대비 footer evidence 추가 이득 비교

### Phase 5 — 회귀·보고

- pure evaluation 코드 단위 테스트
- Book Scanner 전체 회귀
- engine/session/delivery/outbox 변경이 없음을 diff로 확인
- `SCANNER_VIDEO_V3_A_4_IMPLEMENTATION_REPORT.md` 작성
- 후보/기각/자료부족 중 하나와 다음 데이터 요구량 보고

## 10. 구현 경계와 예상 파일

production `video/engine.py`, session, delivery, HTTP 계약은 수정하지 않는다. 우선 evaluation와
offline tool에만 구현한다.

```text
src/book_scanner/evaluation/
  footer_identity.py             # observation, match, K-of-N, 3상태 pure logic
  footer_identity_statistics.py  # autocorrelation, block bootstrap, CI

tools/
  run_scanner_video_v3a4_footer_capture.py
  run_scanner_video_v3a4_footer_replay.py
  summarize_scanner_video_v3a4_footer_identity.py

experiment_inputs/
  scanner_video_v3a4_footer_identity_manifest.json

experiment_outputs/scanner_video_v3a4_<date>/
  frozen_footer_observations.json
  match_matrices.json
  replay_grid.json
  summary.json

tests/unit/evaluation/
  test_footer_identity.py
  test_footer_identity_statistics.py
```

실제 파일명은 기존 구조에 맞춰 최소 조정할 수 있지만 production engine 밖이라는 경계는 유지한다.

## 11. 테스트 행렬

### 11.1 Identity pure logic

- reference/query frame 중복 차단
- empty/missing-to-empty/missing match 0
- 좌우 중 한쪽만 일치할 때 spread match 0
- bank 순서 변화에 match count 불변
- reference bank 고정 뒤 query 한 개가 증거 1개만 생성
- N² pair를 N² 시행으로 세지 않음
- `SAME/DIFFERENT/UNKNOWN` 경계값과 validation
- N/K 불가능 조합 명시적 오류

### 11.2 Statistics

- 이상적 독립식의 N=10, p=0.5 결과 약 0.0009765625
- N=14 결과 약 0.0000610352
- block bootstrap deterministic seed
- 완전 상관 sequence의 effective N이 nominal N으로 보고되지 않음
- zero-error가 확률 0으로 출력되지 않음
- infeasible cadence/window `NOT_MEASURED`

### 11.3 Replay safety

- same p30/p316에서 DIFFERENT 오판 count
- p30↔p316에서 SAME 오판 count
- p316 stale `30` single collision이 SAME을 만들지 않음
- hand/page-moving frame이 bank/score에 포함되지 않음
- full-page visual conflict에서 final UNKNOWN
- frozen replay에서 Paddle 재호출 0
- runtime network/model download 0

### 11.4 기존 구조 회귀

- `allow_number_only_duplicate=false` 유지
- page-number provider explicit opt-in 유지
- single in-flight, ACK/reject/cancel 의미 변화 0
- artifact/session/data-pack lineage 변화 0
- Document Parser/server/Coordinator import 및 호출 0

## 12. 성능·캐시 계획

- capture pass에서 OCR과 descriptor 시간을 분리 계측
- replay grid는 frozen JSON만 사용하고 Paddle 호출 0
- reference bank는 최대 20개 descriptor/token만 유지하는 bounded 구조로 모사
- production 후보 설계에서는 full ROI pixel을 장기 cache하지 않음
- visual-only M3는 PC median ≤10ms/side를 provisional budget으로 둠
- OCR M1/M2/M4는 기존 Paddle 비용을 그대로 보고하며 visual-only 비용에 숨기지 않음
- sequential 방식은 평균/median/max first-decision N과 wall delay를 함께 보고
- Pi 4는 실제 실행 전 `NOT_MEASURED`

## 13. 완료 기준

- 사전 고정 manifest와 source/model provenance 작성
- 동일 영상의 frozen footer observation 및 visual descriptor 생성
- M0~M4 same/different 양방향 match matrix 생성
- 5 cadence × 가능한 N × 모든 K threshold replay
- any-match와 3상태 K-of-N 비교
- autocorrelation, block-bootstrap CI, effective N 기록
- stale `30` 충돌과 missing collision의 원인별 집계
- false duplicate/false different/UNKNOWN/decision delay/cost 보고
- 후보 하나를 선발하거나 근거 있게 기각·보류
- Book Scanner 전체 회귀 통과
- 실제 검증하지 않은 different-page 일반화, Pi 4, production 중복 억제를 완료 처리하지 않음

## 14. 중단·보류 조건

다음 조건에서는 threshold를 p30/p316에 반복 맞추거나 범위를 확대하지 않고 결과를 보고한다.

- disjoint reference/query bank를 만들 만큼 eligible stable frame이 부족함
- 모든 방법에서 `p_same`과 `p_diff`가 분리되지 않음
- any-match 또는 K-of-N이 stale footer `30` 때문에 false duplicate를 만듦
- cadence를 줄여 명목 N만 늘려야 결과가 좋아지고 effective N은 증가하지 않음
- visual threshold가 fold마다 크게 달라 고정할 수 없음
- OCR token 방식이 M3 visual-only보다 안전성 이득 없이 비용만 증가시킴
- 기존 hard gate 또는 stable-window 경계를 재튜닝해야만 gate를 통과함
- 사람 확인 different-page 자료가 없어 production 의미의 false-duplicate를 평가할 수 없음

중단 시 기존 V3-A visual fallback과 V3-A.3 explicit opt-in 상태를 유지한다.

## 15. 비범위

- 의미적 페이지 번호 OCR 정확도 개선 또는 모델 fine-tuning
- UVDoc, seam, crop, CandidateGate threshold 재튜닝
- production `video/engine.py` 통합과 자동 중복 억제 활성화
- HTTP 송신, retry/outbox, 서버 idempotency, Coordinator 변경
- Document Parser 또는 PaddleOCR-VL 호출
- 신규 외부 모델·데이터셋 다운로드
- Raspberry Pi camera/GPIO/TTS 배포
- 전체 페이지 OCR이나 클라우드 OCR 도입

## 16. 승인 경계

승인 시 Phase 0~5의 offline 구현·실험·회귀·보고를 수행한다. 다음은 별도 승인 없이는 수행하지
않는다.

- `validated=true` 또는 `allow_number_only_duplicate=true` 전환
- Scanner production composition이나 기본 cadence 변경
- engine/session/delivery/server/Coordinator/API 변경
- 신규 production dependency 추가
- 외부 데이터·모델 자동 다운로드 또는 네트워크 OCR 사용
- Raspberry Pi 배포·성능 완료 처리
- 원격 branch push, PR 생성 또는 기존 사용자 변경 정리
