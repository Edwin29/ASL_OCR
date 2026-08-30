# 고정 구도 좌우 페이지 구분·추출 실험 — 작업 패킷

상태: **구현·제한적 검증 완료 — `BOOTSTRAP_ONLY` (최종 추출기 채택 아님)**
작성일: 2026-08-30
승인일: 2026-08-30
근거 문서: `CODEX_IMPLEMENTATION_CONTEXT.md` Stage 1~4, 사용자 우선순위 변경

## 1. 목적

고정 카메라와 V자형 책받침에서 촬영한 한 장의 spread 이미지로부터 좌우 페이지를
구분하고, 각 쪽의 현재 상단 페이지 표면을 mask와 crop으로 추출하는 문제에
집중한다.

이 패킷은 다음 두 문제만 다룬다.

1. **좌우 페이지 구분**: 고정된 책등 중심과 fixed-layout ROI를 이용해 full frame을
   좌우의 독립된 페이지 처리 영역으로 나눈다.
2. **페이지 표면 추출**: 각 ROI에서 상단 페이지를 foreground mask로 검출하고,
   본문을 자르지 않는 crop을 생성한다.

UVDoc 곡률 보정은 육안상 가능성이 있다는 관찰까지만 유지한다. 실제 수능특강
수학Ⅰ p30 원본을 확보해 동일 원문 점역/OCR과 비교하기 전에는 원근·곡률 보정의
OCR 실효성을 완료 또는 채택으로 판정하지 않는다.

## 2. 현재 확인된 입력과 제약

### 촬영 조건

- 카메라, 책등 중심, V자형 책받침의 구도가 고정되어 있다.
- 항상 위에서 펼친 책의 양면을 촬영한다.
- 범용 문서 구도, 한 페이지만 보이는 구도, 휴대전화 자유 촬영은 고려하지 않는다.
- 책 크기·두께·페이지 색상·곡률·조명과 그림자는 달라질 수 있다.
- 좌우 페이지는 책등 부근에서 겹쳐 보이거나 같은 ROI 경계에 접촉할 수 있다.

### 정답 라벨

현재 LabelMe 정답 spread는 4개다.

| 이미지 | left_page 점 수 | right_page 점 수 |
|---|---:|---:|
| `20260826_174943.jpg` | 27 | 27 |
| `20260826_174953.jpg` | 18 | 26 |
| `20260826_174958.jpg` | 24 | 22 |
| `20260826_175109.jpg` | 12 | 19 |

라벨은 학습 데이터로 충분하지 않다. 이번 패킷에서는 다음 용도로만 사용한다.

- 좌우 ROI와 좌표 변환 검증
- 페이지 mask 정량 평가
- 실패 사례의 overlay 육안 검토
- 자동 라벨 초안의 수정 비용 추정

같은 네 장으로 threshold를 맞춘 뒤 같은 네 장의 점수를 일반화 성능으로 보고하지
않는다. 파라미터 비교가 필요하면 최소한 spread 단위 leave-one-out 결과와 전체
고정 파라미터 결과를 분리해 기록한다.

### 비라벨 이미지

- 책이 있는 비라벨 이미지는 자동 mask 초안 생성 및 실패 유형 관찰에만 사용한다.
- `175153`, `175200`은 육안상 빈 받침대이며 no-page 검증 대상으로 유지한다.
- 빈 받침대의 조명/반사 차이로 기존 background subtraction이 오검출된 사실이 이미
  재현되어 있다.

## 3. 승인 시 확정되는 설계 결정

- 좌우 분리는 범용 spread detector가 아니라 고정 centerline/fixed-layout polygon ROI로
  처리한다.
- 좌우 ROI는 각각 독립적인 단일 페이지 segmentation 문제로 다룬다.
- 검출 결과의 기준 표현은 네 모서리가 아니라 binary page mask다.
- `minAreaRect`와 4점 homography를 페이지 정답 또는 최종 추출기로 간주하지 않는다.
- 책등 쪽 ROI 경계 접촉은 정상일 수 있으므로 full-frame 외곽 접촉과 별도로 기록한다.
- 본문 잘림 방지가 배경 최소화와 정답 경계의 정확한 일치보다 우선한다. crop은 mask
  bbox에 검증 가능한 padding을 적용하며 원본 좌표로 round-trip할 수 있어야 한다.
- 예측 mask/crop의 크기가 정답과 다르더라도 본문을 보존하고 유해한 배경 유입이 없다면
  실패로 간주하지 않는다. IoU와 bbox 차이는 진단값이지 단독 합격 기준이 아니다.
- 네 장의 수동 라벨은 원본 그대로 보존한다. 코드는 임의 erosion/dilation으로 정답을
  수정하지 않는다.
- 모델 학습, UVDoc 재평가, OCR/점역 품질 결론, session/transmit 통합은 수행하지 않는다.

## 4. 구현 범위

### WP-1. LabelMe 정답을 평가 경로에 직접 연결

기존 `annotations/labelme.py`가 생성하는 full-frame 좌우 mask를
`evaluate_page_masks.py`의 ROI-local 정답 입력으로 직접 전달할 수 있게 한다.

필수 동작:

- `--labelme-dir` 또는 동등한 명시적 입력 지원
- 이미지 stem과 JSON의 `imagePath`, 크기, 필수 label 일치 검증
- full-frame mask → ROI-local mask 변환
- label/ROI 밖 픽셀, 좌우 overlap, 책등 접촉 진단
- 기존 `<stem>_<side>.png` 정답 mask 입력과의 하위 호환 유지
- 라벨 누락/불일치 시 해당 이미지를 점수에서 제외하고 명시적 실패 reason 기록

### WP-2. 고정 구도 ROI 진단

현재 fraction centerline과 normalized polygon ROI 구현을 유지하면서, 네 라벨을
기준으로 다음을 측정한다.

- 각 page mask가 반대쪽 ROI로 잘리는 픽셀 비율
- 책등 중심선 부근의 좌우 overlap 폭과 면적
- full-frame 외곽 및 ROI의 spine/outer/top/bottom edge 접촉
- 라벨 bbox와 ROI 사이의 여유 폭
- centerline fraction 후보별 page recall

이 단계는 네 라벨에서 고정 ROI가 가능한지 판단하는 진단이다. 마커, 카메라
intrinsic/extrinsic, 실측 기준점이 없으므로 이를 기하학적 또는 계량적
`calibration`이라고 부르지 않는다. 여기서 얻는 것은 다음뿐이다.

- 고정 카메라 영상 좌표에서 관찰한 경험적 중심축 범위
- 라벨을 자르지 않는 보수적인 normalized 처리 영역
- 촬영 장치가 움직이지 않았다는 전제 아래 재사용하는 fixed-layout prior

기존 코드의 `is_calibrated` 같은 이름은 이미 만들어진 API 명칭일 뿐이며, 이번
실험 보고서에서는 `fixed_layout`과 `metric_calibration`을 구분한다. 네 라벨로 정한
ROI를 같은 네 라벨에서 평가한 값은 ROI 일반화 성능으로 주장하지 않는다.

### WP-3. 고정 구도 추출 baseline

기존 두 baseline을 같은 평가 경로에 유지한다.

1. `brightness`
2. `legacy-background`

추가로 외부 ML 의존성이 없는 `contrast-spatial` 실험 구현체를 하나 둔다.
구체 알고리즘은 구현 중 작은 단위로 비교하되 다음 경계를 지킨다.

- 입력은 한쪽 `PageROI`만 받는다.
- 고정된 공간 prior와 빈 받침대 표본의 배경 색/밝기 정보를 사용할 수 있다.
- 조명 변화에 민감한 단일 absdiff threshold만으로 판정하지 않는다.
- morphology, connected component, hole filling은 기존 mask 후처리 경계에서 수행한다.
- 출력은 `SegmentationResult(mask, confidence, diagnostics)` 계약을 따른다.
- threshold와 조합은 CLI/config로 노출하고 코드 내부의 샘플별 예외 분기를 금지한다.

후보가 네 라벨과 빈 받침대 모두에서 기존 baseline보다 개선되지 않으면 실패 결과를
그대로 기록한다. 이 패킷의 완료 조건은 특정 OpenCV 방식의 성공을 전제하지 않는다.

#### 검은 배경을 이용한 경계 검출 후보

검은 배경은 통제 가능한 가장 강한 신호이므로 무시하지 않고 주 검출 후보로 사용한다.
Canny를 포함한 edge filter 자체는 금지하지 않는다. 금지하는 것은 edge 결과에서
**가장 큰 사각형 또는 가장 큰 contour라는 크기 조건만으로 페이지를 결정하는 것**이다.
페이지 내부의 글자·표·그림이 외곽보다 강한 edge를 만들 수 있고, 곡률이 있는 실제
페이지 경계는 사각형이 아닐 수 있기 때문이다.

초기 후보 순서는 다음과 같다.

1. 저해상도 Lab/HSV 영상에서 검은 배경 seed를 찾는다.
   - frame/ROI 외곽의 어두운 픽셀
   - `175153`, `175200`의 빈 받침대 표본
   - 단일 밝기값이 아니라 밝기와 색차를 함께 기록
2. 배경 seed와 명백한 페이지 내부 seed로 foreground likelihood 또는 GrabCut 초안을
   만든다.
3. fixed-layout side prior로 반대 페이지와 불가능 영역을 제거한다.
4. morphology, hole filling, connected component로 page surface 후보를 만든다.
5. Canny/Sobel edge map을 초안 contour 주변 refinement에 사용할 수 있으며, 원본
   전체 edge map도 다음 조건을 결합하는 후보 생성에 사용할 수 있다.
   - 검은 배경 영역과의 인접성
   - fixed-layout side/centerline 위치
   - 경계의 연속성과 닫힘 정도
   - 페이지 내부를 충분히 포함하는 topology
   - 반대쪽 페이지 또는 frame 외곽과의 비정상 연결 여부
   - 여러 threshold/scale에서의 경계 안정성
6. contour 후보는 면적 하나로 순위를 정하지 않고 위 신호와 foreground likelihood를
   함께 사용한다. 면적은 지나치게 작거나 전체 frame에 가까운 명백한 오검출을 거르는
   보조 조건으로만 사용한다.
7. 최종 crop 경계는 곡선을 보존하는 mask/contour로 유지한다. Hough line,
   `approxPolyDP`, 사각형 fitting은 아래 coarse perspective 실험용 anchor를 만드는
   경우에만 사용한다.

따라서 edge는 검은 배경 segmentation의 보정 신호뿐 아니라 독립적인 경계 후보
생성에도 사용할 수 있다. 다만 최종 선택은 대비·공간 prior·연속성·배경 인접성 등과
결합한다. 그림자 때문에 페이지 일부가 어두워져도 배경으로 뚫리지 않는지, 흰 페이지
묶음 옆면이 상단 페이지에 붙는지는 별도 실패 유형으로 기록한다.

### WP-4. 처리 순서 A/B/C 실험

사용자가 제안한 세 순서를 동일 입력과 동일 지표로 비교한다. 여기서 perspective
correction은 UVDoc 곡률 보정이 아니라 OpenCV homography 기반 **coarse perspective
warp 후보**를 뜻한다.

#### A. 중심축 구분 → coarse perspective → page crop

```text
full frame
→ fixed centerline으로 좌우 분리
→ 고대비 rough foreground/contour envelope
→ side별 quad surrogate와 coarse homography
→ 보정 공간에서 curved page mask refinement
→ crop
```

곡률 때문에 원본에서 휜 경계가 coarse warp 뒤에 다각형에 가까워져 후속 mask/crop이
쉬워질 수 있다는 직관을 검증한다. homography anchor는 rough foreground 외곽에서
얻으므로, 정답 polygon을 입력으로 사용하지 않는다. 안정적인 네 anchor를 만들지
못하면 임의 사각형으로 진행하지 않고 `WARP_ANCHOR_NOT_FOUND`로 기록한다.

#### B. spread coarse perspective → 중심축 구분 → page crop

```text
full frame
→ spread 전체 rough envelope로 단일 coarse homography
→ 보정 공간의 중심축으로 좌우 분리
→ side별 curved page mask
→ crop
```

이 방식도 실험하되, 한 개의 homography가 90°를 이루는 양쪽 V면을 동시에 평면화할
수 없다는 한계를 전제로 한다. 즉 성공을 가정한 설계가 아니라, 전체 spread의 큰
카메라 원근만 줄여도 중심축과 crop이 안정되는지를 확인하는 반증 가능한 baseline이다.
spread 전체에서 안정적인 reference envelope를 찾지 못하면 `NOT_RUN_NO_REFERENCE`로
남긴다. 내부적으로 좌우 두 homography를 쓰면 이미 중심축을 사용한 것이므로 B 결과로
분류하지 않는다.

#### C. 중심축 구분 → page crop → coarse perspective

```text
full frame
→ fixed centerline으로 좌우 분리
→ 검은 배경 기반 curved page mask
→ padding crop
→ 필요 시 crop envelope의 coarse homography
```

정석적인 순서이며 A/B의 비교 기준이다. 원본 곡선 mask와 warp 후 결과를 모두 저장해
homography가 페이지를 잘라내거나 반복 보간으로 선명도를 낮추는지 확인한다.

#### 공통 제한

- marker나 실측 기준점이 없으므로 warp를 metric calibration으로 부르지 않는다.
- 페이지를 사각형이라고 가정하지 않는다. quad는 coarse warp anchor일 뿐이며 최종
  정답과 crop은 mask 기반이다.
- 정답 LabelMe polygon으로 homography를 만든 결과는 oracle 진단으로만 분리하며
  검출 성능에 포함하지 않는다.
- A/B/C마다 warp 횟수, interpolation, 출력 크기, source/destination anchor와 matrix를
  diagnostics에 기록한다.
- warp를 적용하지 못한 경우도 실패 산출물과 rough mask를 보존한다.

### WP-5. 추출 품질 지표 확장

기존 IoU, Dice, tolerance boundary F1은 경계 비교용 보조 진단으로 유지하고 다음
본문·페이지 보존 중심 진단을 추가한다.

- `page_recall`: 정답 page pixel 중 예측 mask에 포함된 비율
- `background_leakage`: 예측 mask 중 정답 page 밖 픽셀 비율
- `missed_page_px`와 `extra_background_px`
- 예측/정답 bbox의 각 방향 편차
- crop이 정답 mask를 포함하지 못한 픽셀 수
- `safe_crop_page_recall`: padding을 포함한 최종 crop에 들어간 정답 page 비율
- `content_proxy_recall`: 정답 page 내부의 dark/high-frequency 인쇄 후보 픽셀 중
  최종 crop에 보존된 비율. 이는 본문 정답 라벨이나 OCR 정확도를 대신하지 않는다.
- 좌우 예측 mask의 full-frame overlap
- 이미지별/side별 처리시간
- 빈 받침대의 false-page 여부
- A/B/C 처리 순서와 warp 성공/실패 reason
- warp 전후의 gradient sharpness 또는 동등한 비참조 선명도 보조값

`page_recall`, `safe_crop_page_recall`, `content_proxy_recall`은 본문 잘림 위험의
proxy일 뿐이다. 본문 영역 라벨이 없으므로 “본문 잘림 0”을 정량 입증했다고 표현하지
않고 원본 해상도 overlay/crop 육안 검토와 구분한다. 반대로 예측 mask가 정답 경계보다
크거나 crop padding으로 크기가 달라도 본문 보존에 문제가 없으면 그 차이만으로
실패시키지 않는다.

### WP-6. 일괄 평가와 비교 보고서

라벨 4장, 책이 있는 비라벨 이미지, 빈 받침대 2장을 한 명령으로 평가하고 다음을
저장한다.

- full-frame 원본과 좌우 ROI
- raw mask, postprocessed mask
- 정답/prediction 중첩 overlay
- false-negative/false-positive 색상 overlay
- padding crop
- 이미지·side별 diagnostics JSON
- segmenter·처리 순서별 summary JSON/CSV
- 동일 샘플을 나란히 보는 contact sheet

보고서에는 다음을 분리한다.

1. 실제 측정 결과
2. 육안 관찰
3. 작은 데이터에 근거한 잠정 해석
4. 검증하지 못한 사항

예정 보고서: `PAGE_SEPARATION_EXTRACTION_EXPERIMENT_REPORT.md`

### WP-7. 라벨 확장용 초안 생성

비라벨 책 이미지에 선택된 baseline의 mask를 LabelMe에서 수정 가능한 polygon 초안으로
내보내는 opt-in 도구를 추가한다.

- 원본 이미지를 복사하거나 수정하지 않는다.
- 기존 JSON이 있으면 기본적으로 덮어쓰지 않는다.
- 자동 생성 label에는 생성기, config, source hash를 metadata로 기록한다.
- 사람이 수정하지 않은 초안은 ground truth나 완료된 라벨로 취급하지 않는다.
- 지나치게 많은 contour point는 시각 형상을 보존하는 범위에서 단순화하며 원본 mask도
  함께 저장한다.

이번 패킷에서는 최대 약 10개 수동 라벨을 학습 데이터로 간주하지 않는다. 데이터
증강은 도구/테스트의 안정성 확인용으로만 사용할 수 있으며 독립 검증 샘플 수를 늘린
것처럼 보고하지 않는다.

## 5. 테스트 범위

### Unit tests

- LabelMe full-frame mask → ROI-local truth 좌표 변환
- centerline과 polygon ROI의 page recall 계산
- spine edge 접촉과 physical outer edge 접촉 구분
- page recall/safe crop recall/content proxy recall/background leakage/bbox 지표
- 크기가 다르지만 본문을 모두 포함하는 crop이 IoU만으로 실패하지 않는 회귀 테스트
- 빈 mask, 완전 일치, 부분 누락, 과다 mask의 정확한 지표
- contrast-spatial fake/synthetic 입력의 deterministic 결과
- A/B/C 순서가 실제로 다른 단계 순서를 실행하는지 확인하는 fake warp/segmenter 테스트
- warp anchor 부재, degenerate quad, 단일 spread warp 실패 reason
- mask/anchor의 warp 전후 좌표 round-trip
- segmenter 실패 시 다른 side와 raw 산출물 보존
- LabelMe 초안 생성, metadata, no-overwrite 정책
- 비ASCII Windows 경로

### 실제 데이터 검증

- 라벨 4장 × 좌우 8개 mask를 모두 평가
- 빈 받침대 2장 × 좌우 4개 ROI에서 false-page 기록
- 비라벨 책 이미지 전체의 overlay/crop 생성
- 기존 brightness/legacy 결과와 contrast-spatial 결과 비교
- 동일 segmenter를 사용한 A/B/C 처리 순서 비교
- contact sheet 육안 검토
- `pytest`, `compileall`, `git diff --check`

## 6. 완료 조건

다음을 모두 충족한 항목만 이 패킷의 구현 완료로 처리한다.

- LabelMe 4개가 수동 PNG 변환 없이 평가 CLI에 연결된다.
- 좌우 ROI가 정답 page를 얼마나 자르는지 수치와 overlay로 확인된다.
- 세 baseline이 동일 입력·동일 지표·동일 산출물 규칙으로 비교된다.
- A/B/C 세 처리 순서가 실행되거나, 실행 불가능한 경우 명시적 reason으로 기록된다.
- 라벨 8개 mask의 IoU/Dice/boundary F1과 page/safe-crop/content-proxy recall,
  background leakage가 기록된다.
- 빈 받침대 false-page 결과가 side별로 기록된다.
- crop의 정답 page 누락 픽셀이 계산되고 육안 검토 자료가 생성된다.
- 자동 라벨 초안이 기존 라벨을 덮어쓰지 않고 생성된다.
- 기존 session/transmit/UVDoc 기본 경로가 변경되지 않는다.
- 신규·기존 테스트가 통과하고 재현 명령과 결과 보고서가 남는다.

아래는 완료 조건이 아니라 **후속 경로 선택을 위한 잠정 판정 기준**이다.

- `CLASSICAL_CANDIDATE`: 네 라벨에서 본문·페이지 보존 proxy와 원본 해상도 육안 검토가
  양호하고, 기존 baseline보다 유해한 leakage와 빈 받침대 오검출이 일관되게 감소
- `BOOTSTRAP_ONLY`: 자동 초안으로는 쓸 수 있으나 안정적인 추출기로는 부족
- `MODEL_REQUIRED`: 고정 구도 prior를 사용해도 페이지/옆면/받침대 분리가 불안정

표본이 네 spread뿐이므로 어느 판정도 일반화 성능이나 배포 준비 완료를 의미하지
않는다.

## 7. 명시적 비범위

- UVDoc 재실행, 후처리 또는 보정 방식 선택
- 수능특강 수학Ⅰ p30의 OCR/점역 비교
- OCR CER, 토큰 수, confidence를 페이지 추출 완료 지표로 사용
- segmentation neural network 학습/fine-tuning
- 외부 공개 데이터셋 다운로드·정제·학습
- SAM/SAM 2 또는 외부 API를 이용한 대량 pseudo-labeling
- session loop, stability judge, quality judge, transmit client 통합
- 좌우 동시 촬영/전송 상태 머신 변경
- Raspberry Pi 성능 및 메모리 최적화
- 카메라 lens calibration 또는 ArUco pose estimation
- marker/실측 기준점 없는 warp를 metric calibration으로 확정
- 사용자가 만든 4개 LabelMe JSON 수정

## 8. 예상 변경 파일

신규 후보:

- `src/book_scanner/detect/contrast_spatial.py`
- `src/book_scanner/evaluation/extraction_orders.py`
- `src/book_scanner/correct/coarse_perspective.py`
- `src/book_scanner/evaluation/labelme_truth.py`
- `tools/export_page_label_drafts.py`
- `tests/unit/test_contrast_spatial.py`
- `tests/unit/test_labelme_truth_evaluation.py`
- `tests/unit/test_page_label_drafts.py`
- `PAGE_SEPARATION_EXTRACTION_EXPERIMENT_REPORT.md`

최소 수정 후보:

- `src/book_scanner/evaluation/page_masks.py`
- `tools/evaluate_page_masks.py`
- `tests/unit/test_page_mask_evaluation.py`
- `README.md`의 오프라인 평가 명령/보고서 링크
- `.gitignore`의 대형 평가 출력 제외 규칙

수정 금지:

- `src/book_scanner/session/loop.py`
- `src/book_scanner/transmit/client.py`
- `src/book_scanner/correct/uvdoc_adapter.py`
- `src/book_scanner/correct/postprocess.py`
- 기존 LabelMe JSON과 원본 이미지
- 기존 4점 perspective correction의 동작 계약

## 9. 의존성과 저장 정책

- 기본 구현은 현재 NumPy/OpenCV/Pillow 범위에서 수행한다.
- 새 ML framework, weight 또는 외부 서비스는 추가하지 않는다.
- 평가 출력, 자동 생성 mask/overlay/crop/contact sheet는 Git에 추가하지 않는다.
- 코드, 작은 config, 테스트 fixture, 요약 보고서만 검토 대상으로 둔다.
- 모든 실제 결과에는 입력 이미지/라벨/config의 hash 또는 재현 가능한 경로를 기록한다.

## 10. 중단 및 재승인 조건

다음 상황에서는 임의로 범위를 넓히지 않고 결과를 보고한 뒤 재승인을 요청한다.

- 기존 4개 라벨의 정의 또는 경계를 수정해야 함
- contrast-spatial이 실패해 ML 모델/weight를 도입해야 함
- A/B/C의 coarse warp에 사용할 안정적인 image-derived anchor가 없어 실측 또는 별도
  calibration이 필요함
- 공개 데이터셋 또는 외부 pseudo-labeling 서비스를 사용해야 함
- 카메라/책받침 calibration 데이터가 새로 필요함
- session loop나 전송 정책을 변경해야 실제 검증이 가능함
- 수능특강 수학Ⅰ p30이 확보되어 OCR/점역 비교를 재개할 수 있음

## 11. 승인 요청

이 패킷 승인 시 다음을 허용하는 것으로 해석한다.

1. 위 범위의 평가·검출·라벨 초안 코드와 테스트를 추가한다.
2. 현재 네 LabelMe 파일을 읽기 전용 정답으로 사용한다.
3. `175153`, `175200`을 빈 받침대 검증 입력으로 사용한다.
4. 비라벨 책 이미지에 Git 제외 평가 산출물과 LabelMe 초안을 생성한다.
5. 기존 사용자 변경을 보존한 채 현재 `book-scanner` 실험 경계 안에서 구현한다.
6. 실제 측정 보고서가 나오기 전에는 특정 추출기를 채택 완료로 처리하지 않는다.
