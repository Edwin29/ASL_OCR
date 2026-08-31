# Scanner Video V3-A.2 — Lightweight Page-Number Backend & Temporal Replay 작업 패킷

상태: **승인 범위 구현·실험 완료 — corrected 후보 통과 / preview temporal 선발 보류**  
작성일: 2026-08-31  
승인·실행일: 2026-08-31  
선행 조건: V2 `seam-conservative + UVDoc bilinear`, V3-A visual identity/page-change gate,
V3-A.1 bottom ROI·`SpreadPageKey`·fusion·cache 계약  
후속 조건: Integration V0 Coordinator 기본 구성 후보 확정, 이후 V3-B durable outbox·HTTP 송신

## 1. 배경과 현재 증거

V3-A.1은 페이지 번호 인식의 계약과 engine 연결을 구현했지만 production recognizer는 선택하지
않았다.

| backend | p30 corrected 결과 | PC spread median | 현재 판정 |
|---|---:|---:|---|
| OpenCV synthetic HOG | 좌 2/3, 우 0/3 | 96.155ms | 정확도 부족 |
| Tesseract 5.5.3 CLI | 좌 2/3, 우 3/3 | 215.214ms | confidence·persistent 조건 미충족 |
| Paddle recognition-only | 좌 3/3, 우 3/3 | 159.956ms | 정확도 후보, 지연 목표 미달 |

기존 영상의 user-labeled clean anchor를 최대 1920px grayscale preview로 진단한 결과 720번은
`30/309`, 780번은 좌 `30`만 partial, 2220번은 `316/317` complete였다. 손 가림·페이지 이동
1170·1500·2400·2580은 기존 hard gate가 recognizer 호출 전에 제외했다. 다만 sparse anchor라
연속 K회 합의, false page-change 및 변경 지연은 검증되지 않았다.

본 패킷은 이 두 미해결점만 다룬다.

1. 기존 OpenCV dependency로 실행 가능한 작은 digits-only backend를 선발한다.
2. 실제 연속 프레임에서 stable-K page-change와 fallback을 검증한다.

HTTP 송신, 서버 DB, Coordinator 화면, durable outbox 또는 Document Parser OCR은 본 패킷에
포함하지 않는다.

## 2. 목표

- 1~4자리 footer 숫자에 한정된 경량 recognizer를 구현·평가
- 대량 수동 라벨링 없이 synthetic 학습 자료와 소량 real golden 검증 자료를 분리 사용
- corrected artifact와 1920px preview ROI를 동일 evaluator로 비교
- 실제 영상에서 same-page 유지, page-moving 제외, new-page 안정화의 시간 순서를 replay
- 번호 인식 실패 시 기존 visual identity fallback이 그대로 작동함을 검증
- backend·전처리·모델 asset의 버전, 해시, license와 cold/warm 비용 기록
- gate를 통과한 경우에만 명시적 composition 후보를 제공

V3-A.2 완료는 Pi 4 배포 완료, 모든 교재의 페이지 번호 지원 또는 번호-only duplicate 자동 억제
활성화를 뜻하지 않는다.

## 3. 고정 불변식

- 한 spread의 좌우는 같은 source frame lineage를 유지한다.
- 인식 입력은 좌우 페이지 하단 외곽 ROI로 제한한다. 전체 페이지 OCR로 확대하지 않는다.
- Document Parser, PaddleOCR-VL layout pipeline 또는 네트워크 OCR을 호출하지 않는다.
- `data_pack_id`가 같은 경우에만 page key를 비교한다.
- 좌우 번호의 연속성·홀짝·증가 방향을 정확성 근거로 사용하지 않는다.
- 손 가림, `PAGE_MOVING`, blur 또는 한쪽 mask 누락 표본은 temporal consensus에 포함하지 않는다.
- confidence가 없거나 calibration되지 않은 결과를 `1.0`으로 가장하지 않는다.
- recognizer 미주입·load 실패·partial/missing이면 V3-A visual fallback을 유지한다.
- `allow_number_only_duplicate=false`와 `validated=false`는 본 패킷 동안 유지한다.
- 서로 다른 페이지를 같은 key로 오인한 표본이 하나라도 있으면 자동 중복 억제를 승격하지 않는다.
- 기존 session, delivery lifecycle, immutable artifact 및 사용자 변경을 보존한다.

## 4. 자료 구성과 최소 사람 검수

### 4.1 Real golden

대량 frame-by-frame 라벨링 대신 사람이 안정 구간의 경계와 좌우 번호 한 쌍만 확인한다.

초기 최소 단위:

- p30/309 stable 구간 1개
- p316/317로 보이는 stable 구간 1개: 사람 확인 전에는 diagnostic
- page turn 전후 stable 구간 각 1개
- 손 가림·page-moving 구간은 기존 사용자 라벨 재사용
- 보유한 corrected p30 세 artifact
- 가능하면 서로 다른 spread 3개 이상을 추가해 different-page negative 구성

각 stable 구간 내부에서 engine cadence로 추출한 프레임은 구간 label을 상속할 수 있다. 단,
경계 양쪽 safety margin과 실제 움직임 구간은 자동 상속하지 않고 `EXCLUDED_TRANSITION`으로 둔다.

### 4.2 분할 원칙

- 인접 프레임을 train과 validation에 나누지 않는다.
- 동일 촬영 burst 또는 동일 stable run은 하나의 split에만 둔다.
- corrected 세 p30 이미지는 same-page positive이며 different-page negative로 재사용하지 않는다.
- OCR 출력이나 현재 recognizer 예측을 사람 label로 승격하지 않는다.
- right `309`, `316/317`은 사용자 또는 별도 사람 검수 전 golden 정확도 분모에 넣지 않는다.

### 4.3 Synthetic 학습 자료

수동으로 학습 규모를 채우지 않는다. 0~9 glyph를 다음 조합으로 생성한다.

- 재배포 가능한 인쇄체 또는 로컬 font 이름·버전을 manifest에 기록
- 1~4자리 숫자열과 개별 glyph
- 작은 회전·원근·곡률 근사, blur, JPEG, resize, 밝기/대비, 음영, 배경색, erosion/dilation
- 실제 ROI에서 측정한 glyph 크기·간격·baseline 분포
- footer 연도·단원 텍스트와 본문 문제 번호를 hard negative로 포함

Synthetic 자료는 모델 학습·튜닝에만 사용한다. production 선발의 최종 gate는 hold-out real
golden과 temporal replay로 판단한다.

## 5. Backend 후보

### 5.1 기준선

- Paddle `en_PP-OCRv5_mobile_rec`: 정확도 기준선이며 production 의존성으로 자동 추가하지 않음
- 기존 OpenCV HOG와 Tesseract CLI: rejected control로만 유지하고 p30에 맞춰 반복 튜닝하지 않음

### 5.2 우선 후보 — OpenCV DNN digits-only classifier

현재 component locator가 1~4개 glyph sequence와 physical outer-edge 우선순위를 계산한다.
이를 유지하고 각 glyph를 작은 0~9 classifier로 판별한다.

- 모델 형식: ONNX
- runtime: 기존 `opencv-python`의 `cv2.dnn`, 신규 범용 OCR runtime 없음
- 입력: 정규화된 단일 glyph, 예: `32x48` grayscale
- 출력: 10-class logits와 calibrated probability
- sequence confidence: 개별 glyph 최소/기하평균 confidence + segmentation quality
- 좌우 page label: glyph 순서 결합, 1~4자리만 허용
- Otsu/adaptive 또는 원본/CLAHE 중 두 variant 합의 유지
- 모델은 process/session 동안 한 번 load

학습 도구는 runtime package와 분리한다. PyTorch 등을 사용하더라도 export 검증 뒤 production
dependency에 포함하지 않는다.

### 5.3 보조 후보 — 경량 sequence recognizer

glyph segmentation이 실제 hold-out에서 반복 실패할 때만 작은 CRNN/CTC ONNX를 비교한다.
vocabulary는 blank + `0`~`9`로 제한하고 detector 없이 locator가 만든 tight sequence crop만 받는다.
보조 후보 때문에 전체 text recognizer나 Document Parser를 production 경로에 넣지 않는다.

Paddle→ONNX 변환은 정확도 기준선 최적화 실험으로 허용할 수 있으나, digits-only 모델보다
dependency·모델·latency가 크면 선택하지 않는다.

## 6. Sampling 및 temporal replay

현재 기본 `sample_interval_ms=750`, page-number `stable_sample_count=3`을 기준선으로 둔다.

- 첫 eligible changed sample부터 세 번째 합의까지 관찰 간격은 약 1.5초
- 변화 직후 다음 sampling까지 포함한 worst-case release는 약 2.25초
- 페이지 이동 구간은 stable count를 reset
- same complete key는 visual change count를 reset
- partial/missing/conflict는 page-number count를 reset하고 visual gate로 fallback
- 한 표본의 `30/309 → 오인 → 30/309` spike는 release 0
- `30/309 → transition excluded → 316/317 x K`에서 release 1회
- release 뒤 corrected artifact key가 baseline과 같으면 새 전송 요청을 만들지 않음

동일 replay에 500/750/1000ms cadence를 적용해 지연과 duty cycle을 비교하되, 작은 자료에서 가장
빠른 값만 보고 기본값을 즉시 변경하지 않는다. 변경 권고에는 false release와 missed change를
함께 기록한다.

## 7. Cache와 리소스 경계

- 기존 exact ROI SHA-256 bounded LRU capacity 32 유지
- perceptual-near cache는 자동 인식 결과로 사용하지 않음
- cache에 full frame, mask, ROI pixel array 또는 model tensor를 저장하지 않음
- same source/side/source kind exact hit에서 recognizer 호출 0
- session/datapack 전환 시 temporal consensus는 reset
- 모델 파일 권고 목표: 2MiB 이하, 초과 시 실제 이득과 함께 기록
- 신규 runtime dependency 권고 목표: 기존 OpenCV/NumPy 외 추가 없음
- PC warm 양쪽 preview recognition 목표: median ≤50ms, observed p95 ≤100ms
- PC cold load 권고 목표: ≤1000ms
- process RSS 증분 권고 목표: ≤75MiB
- 750ms cadence에서 recognizer p95 duty cycle 목표: ≤13.4%

이 값은 PC prototype 선발 budget이다. Raspberry Pi 4 실측 전 Pi 성능으로 보고하지 않는다.
현재 배포 일정이 없으므로 Pi 측정은 완료 필수 조건이 아니지만, OpenCV DNN 호환성과 모델 크기는
향후 Pi 이식을 막지 않는 선택 근거로 남긴다.

## 8. 구현 단계

### Phase 0 — 자료 복구·golden manifest

- 이전 MP4 또는 동일 원본 영상 경로 확인
- stable run, transition, occlusion 구간 manifest 생성
- 사용자 확정 label과 diagnostic inference를 명시적으로 분리
- corrected/preview ROI와 candidate overlay 저장

### Phase 1 — Synthetic generator 및 lightweight model

- deterministic seed의 digit/glyph sequence generator
- font/license/augmentation manifest
- train/validation split과 leakage check
- small digit classifier 학습, ONNX export, OpenCV DNN parity test
- 필요할 때만 small CTC sequence 후보 추가

### Phase 2 — 동일 backend runner

- OpenCV DNN, Paddle baseline, rejected controls를 같은 ROI·label manifest에서 평가
- corrected/preview 정확도, abstention, wrong-complete, cold/warm latency, model size, RSS 기록
- brightness/JPEG/translation variants와 footer hard negative 검증
- threshold는 training/validation으로 정하고 final hold-out에서 재튜닝하지 않음

### Phase 3 — Temporal replay

- engine과 동일한 hard gate, 1920px input, sampling cadence, stable-K 적용
- same-page, transition, new-page, hand/page-moving, OCR spike 시나리오 replay
- event sequence와 release count, fallback count, delay 측정
- source frame → preview observation → page key → `PAGE_CHANGED` lineage 검증

### Phase 4 — 명시적 composition 및 회귀

- gate 통과 backend만 명시적 factory/config 후보로 연결
- runtime model 자동 다운로드 차단 및 asset hash 검증
- load 실패 시 session crash가 아니라 provider-disabled visual fallback 확인
- Book Scanner 전체 회귀와 Document Parser import/call 0 확인
- 구현 보고서와 threshold/provenance 갱신

## 9. 검증 행렬

### 9.1 Recognizer

- 모든 human-confirmed corrected label exact match
- stable preview에서 wrong complete key 0
- no-number/footer hard negative에서 high-confidence complete key 0
- partial crop은 추측 대신 partial/missing
- left/right swap은 다른 key
- variant disagreement는 conflict
- model load count 1
- ONNX export와 OpenCV DNN output parity
- runtime network/model download 0

### 9.2 Temporal

- same-page stable run에서 `PAGE_CHANGED` 0
- moving/hand/blur 구간에서 stable count 증가 0
- different complete key K회 전에는 `PAGE_CHANGED` 0
- K회 뒤 정확히 1회 release
- 단일 OCR spike release 0
- partial 한쪽 번호만으로 release 0
- missing 구간에서 기존 visual fallback 유지
- page change 뒤 baseline key와 같은 corrected artifact는 새 transfer request 0

### 9.3 Identity 및 delivery 회귀

- 같은 key + visual new는 conflict
- 다른 key + visual duplicate는 conflict
- number-only ambiguous는 자동 suppression 0
- stale/repeated ACK와 reject 불변식 유지
- single in-flight artifact 유지
- session cancel 시 pending key/consensus 정리
- 기존 Integration V0 delivery event 의미 변화 0

### 9.4 성능

- corrected와 preview를 분리해 median/max 및 가능한 표본 수에서 observed p95 기록
- cache hit latency와 recognizer calls 0 검증
- model bytes, runtime dependency bytes, Python-tracked peak와 process RSS를 구분
- 숫자를 충족하지 못한 표본을 latency 집계에서 제외하지 않음
- Pi 4 미측정은 명시적 `NOT_MEASURED`

## 10. 선발 gate

다음을 모두 만족할 때만 lightweight backend를 `production candidate`로 기록한다.

1. human-confirmed corrected label exact 100%
2. real stable preview wrong-complete 0
3. confirmed different-page를 same key로 오인 0
4. moving/occlusion 구간 false release 0
5. confirmed page turn마다 release 정확히 1회
6. model/runtime provenance 및 SHA-256 완비
7. session당 load 1, runtime download 0
8. 전체 Book Scanner 회귀 통과

성능 목표 미달 시 정확도 gate와 별개로 `ACCURACY_PASS_PERFORMANCE_FAIL`로 기록한다. 정확도 자료가
너무 적으면 `PROVISIONAL_DATA_INSUFFICIENT`이며 `validated=true`로 바꾸지 않는다.

본 패킷에서 gate를 통과해도 `allow_number_only_duplicate` 활성화는 자동 수행하지 않는다.
활성화 여부는 different-page false duplicate 결과와 함께 별도 승인받는다.

## 11. 예상 파일 경계

```text
src/book_scanner/video/
  page_number_recognizer.py       # OpenCV DNN adapter
  page_number_training.py         # runtime import 금지 또는 별도 tools로 이동
  page_number_provider.py         # 기존 명시 주입 유지
  config.py                       # model path/hash 및 provisional thresholds
  engine.py                       # 기존 fusion 의미 유지, composition만 추가

tools/
  generate_page_number_synthetic_dataset.py
  train_page_number_digit_model.py
  run_scanner_video_v3a2_backend_evaluation.py
  run_scanner_video_v3a2_temporal_replay.py

experiment_inputs/
  scanner_video_v3a2_temporal_labels.json
  scanner_video_v3a2_model_manifest.json
```

학습 코드와 dependency는 production runtime import graph에서 분리한다.

## 12. 완료 기준

- 최소 사람 검수 manifest와 stable/transition 구간 provenance 작성
- synthetic generator와 dataset manifest 작성
- digits-only ONNX 모델 및 OpenCV DNN adapter 구현
- Paddle 기준선과 동일 runner 비교
- corrected/preview/hard-negative 평가 결과 저장
- 500/750/1000ms temporal replay 및 event lineage 저장
- backend 선발 또는 근거 있는 보류 결정
- explicit injection·load failure visual fallback test
- 전체 Book Scanner 회귀 통과
- 모델/threshold/data/Pi 미검증 사항을 완료로 표시하지 않음
- `SCANNER_VIDEO_V3_A_2_IMPLEMENTATION_REPORT.md` 작성

## 13. 비범위

- HTTP endpoint, retry/backoff, durable outbox, 서버 idempotency
- Coordinator dataset selection UI와 STM 버튼 통신
- Document Parser ingest 또는 점역 품질 재평가
- seam/crop/UVDoc threshold 재튜닝
- Roman numeral, 한글·영문 page label, 표지·목차 번호
- 전체 페이지 text detection/OCR
- Raspberry Pi camera/GPIO/TTS 배포
- page-number key의 durable DB 저장
- 번호-only duplicate suppression 자동 활성화

## 14. 중단 조건

다음 조건에서는 범위를 조용히 확대하지 않고 결과와 필요한 선택을 보고한다.

- 원본 연속 영상 또는 안정 구간을 복구할 수 없어 temporal replay가 불가능함
- 사람 확인 different-page negative가 없어 false duplicate를 평가할 수 없음
- 실제 ROI에서 component segmentation 자체가 반복 실패해 classifier 교체로 해결되지 않음
- synthetic 성능은 높지만 real hold-out wrong-complete가 발생함
- backend가 runtime 자동 다운로드, 출처 불명 asset 또는 전체 OCR을 요구함
- lightweight 후보가 Paddle보다 느리거나 기존 OpenCV dependency로 실행되지 않음
- threshold를 p30 hold-out에 반복 맞춰야만 gate를 통과함
- session/delivery/lineage 불변식을 깨야 성능 목표를 만족함

중단 시 현재 V3-A visual fallback을 production 경로로 유지하고, page-number provider는 opt-in 상태로
남긴다.

## 15. 승인 경계

승인 시 Phase 0~4를 수행하되 다음 동작은 별도 승인 없이는 하지 않는다.

- 번호-only duplicate suppression 활성화
- 신규 production dependency 추가
- 외부 모델·데이터셋 license가 불명확한 상태에서 다운로드 또는 배포
- 서버/Coordinator/API 변경
- 원격 branch push 또는 PR 생성
