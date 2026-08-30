# 고정 구도 Spine Seam 검출·좌우 페이지 소유권 결정 — 작업 패킷

상태: **추가 검증 완료 — fallback 통과 입력에 한한 잠정 `SEAM_CANDIDATE`**
작성일: 2026-08-30
승인일: 2026-08-30
선행 문서:

- `CODEX_IMPLEMENTATION_CONTEXT.md`
- `PAGE_SEPARATION_EXTRACTION_WORK_PACKET.md`
- `PAGE_SEPARATION_EXTRACTION_EXPERIMENT_REPORT.md`

## 1. 목적과 우선순위

현재 fixed-layout ROI는 중심축 양쪽에 full-frame 폭의 6%씩 overlap을 둬 수동 라벨
8면의 ROI page recall을 1.0으로 보존한다. 반면 `contrast-spatial` 좌우 예측 mask는
full-frame에서 평균 약 922,211 px 겹치며, 책등 부근에 반대 페이지가 포함된다.

이번 패킷은 overlap strip 안에서 위에서 아래까지 연속된 **spine seam**을 검출하고,
이를 기준으로 각 픽셀의 좌우 페이지 소유권을 결정하는 데 집중한다. 목표는 단순히
mask overlap을 0으로 만드는 것이 아니라, 현재의 보수적인 본문 보존 특성을 유지하며
반대 페이지 유입을 줄이는 것이다.

우선순위는 다음과 같이 고정한다.

1. spine seam 검출 및 좌우 소유권 결정
2. seam이 적용된 실제 crop과 oracle crop을 이용한 warp × 후보정 paired OCR 실험

paired OCR을 먼저 수행하면 페이지 추출 오류와 보정 효과가 섞이므로 이번 패킷에서는
실행하지 않는다. 다만 다음 패킷에서 원본·warp·후보정 변형을 동일하게 입력할 수 있도록
crop provenance와 좌표 계약은 보존한다.

## 2. 선행 결과와 해석 정정

선행 실험에서 측정된 Laplacian variance ratio는 서로 다른 해상도와 기하 스케일의
영상을 비교한 비참조 보조값이다. OCR 성능이나 순수한 blur 양을 입증하지 않는다.
또한 A 방식의 `NO_PAGE_AFTER_WARP`는 warp가 원리적으로 부적합하다는 뜻이 아니라,
warp 후 검은 background ring이 사라져 현 segmenter의 전제가 깨진 결과다.

따라서 구현 착수 시 `PAGE_SEPARATION_EXTRACTION_EXPERIMENT_REPORT.md`의
“warp를 생략해야 한다”는 취지의 문구를 다음 결론으로 정정한다.

> OCR paired 검증 전에는 원본 crop, coarse warp, UVDoc 중 어느 입력도 채택하거나
> 배제하지 않는다. 원본 crop은 무손실 기준 입력으로 보존하고 모든 보정 변형은 후보로
> 유지한다.

이번 패킷은 warp, UVDoc, OCR 또는 화질 복원 알고리즘을 평가하지 않는다.

## 3. 입력과 고정 제약

### 입력

- 항상 위에서 촬영한 펼친 책의 양면
- 고정 카메라, 고정 책받침, 검은 배경
- `centerline_fraction=0.50`
- `spine_overlap_fraction=0.06`을 기본 비교 설정으로 사용
- 기존 `contrast-spatial` 좌우 raw/postprocessed mask
- 현재 LabelMe 정답 4 spread, 좌우 8면
- 빈 받침대 `20260826_175153.jpg`, `20260826_175200.jpg`

### 제약

- 마커, 실측 기준점 또는 카메라 metric calibration을 가정하지 않는다.
- 기존 LabelMe JSON과 원본 이미지를 수정하지 않는다.
- 좌우 정답 polygon의 겹침은 annotation ambiguity로 별도 기록한다.
- Canny 사용은 허용하지만 contour 크기 또는 사각형 크기만으로 seam을 결정하지 않는다.
- seam은 고정 구도용이며 자유 촬영·한 페이지만 보이는 구도는 고려하지 않는다.
- session/transmit/UVDoc/Document Parser 기본 경로를 변경하지 않는다.
- 실패를 숨기기 위한 샘플별 좌표 예외나 이미지 stem 분기를 금지한다.

## 4. 설계 계약

### 4.1 기준 표현

출력은 단일 x 좌표가 아니라 각 행에 하나의 x 좌표를 갖는 full-frame seam path다.

```text
SpineSeam
- points_full: [(x_0, y_0), ..., (x_n, y_n)]
- confidence
- uncertainty_band_px
- method
- fallback_used
- diagnostics
```

seam 검출 결과로 좌우 mask를 소유권 분리하되 다음 불변식을 검사한다.

- 출력 left/right mask는 ambiguous band 밖에서 서로 겹치지 않는다.
- 분리된 두 mask의 union이 원래 두 예측 mask의 union에서 임의로 크게 줄지 않는다.
- mask, crop, seam은 full-frame 좌표로 round-trip할 수 있다.
- uncertainty band는 삭제 영역이 아니라 판단 보류 영역으로 diagnostics에 남는다.

### 4.2 실패 계약

검출기가 연속된 seam을 만들지 못하면 임의의 곡선을 생성하지 않는다.

- `NO_PAGE`: 양쪽 페이지 mask가 성립하지 않음
- `NO_OVERLAP_SUPPORT`: seam 후보를 계산할 공통 strip이 없음
- `SEAM_PATH_NOT_FOUND`: 유한 비용의 연속 경로가 없음
- `SEAM_OUTSIDE_ALLOWED_BAND`: path가 fixed-layout 허용 범위를 벗어남
- `LOW_CONFIDENCE_SEAM`: 최선·차선 경로 비용 차이가 불충분
- `FIXED_CENTERLINE_FALLBACK`: 명시적으로 허용한 평가 baseline에만 사용

production fallback은 이번 패킷에서 정하지 않는다. 평가 중 fixed centerline fallback을
사용한 결과는 adaptive seam 성공 결과와 분리한다.

## 5. 구현 범위

### WP-0. 선행 보고서 해석 정정

- warp 생략 권고를 채택 보류로 정정
- Laplacian ratio의 스케일 confound와 OCR 미검증 상태 명시
- 원본 crop도 OCR 적합성이 입증되지 않았음을 명시
- 기존 측정값 자체는 변경하지 않음

### WP-1. Seam 공통 인터페이스와 산출물

다음 모듈 경계를 추가한다.

- `SpineSeamDetector` 프로토콜
- `SpineSeam`, `SeamResult`, 실패 reason
- full-frame/ROI-local 좌표 변환
- seam을 이용한 left/right ownership mask 생성
- 원래 union, 분리 union, 잘린 픽셀, ambiguous band 통계

각 입력마다 다음을 저장한다.

- overlap strip 원본
- seam cost map
- seam overlay
- 분리 전/후 좌우 mask
- 분리 전/후 comparison overlay
- 좌우 crop
- diagnostics JSON
- 방법별 contact sheet

### WP-2. Fixed centerline baseline

`x = centerline_fraction × frame_width`를 행 전체에 적용한다. 이 방법은 adaptive seam의
필수 비교 기준이며 성공 후보로 미리 간주하지 않는다.

비교할 설정:

- centerline fraction 0.49, 0.50, 0.51, 0.52
- uncertainty band 0, 4, 8, 16 px

중심선 후보는 현재 네 라벨에서 평가하되, 같은 라벨로 선택한 값을 일반화 성능으로
보고하지 않는다.

### WP-3. Luminance-valley 연속 경로 baseline

overlap strip에서 검은 책등 또는 어두운 골짜기를 선호하는 행별 비용을 만들고,
dynamic programming으로 위에서 아래까지 연속 경로를 구한다.

비용 후보:

- 저해상도 grayscale/Lab luminance
- local percentile 기준의 상대적 어두움
- centerline 거리 prior
- 1차 행간 이동 penalty
- 큰 방향 변화에 대한 2차 smoothness penalty

한 행의 최저 밝기점을 독립적으로 연결하지 않는다. 검은 글자, 수식, 그림 내부로
경로가 끌려가지 않는지 실패 유형으로 기록한다.

### WP-4. Mask-aware content-preserving seam

WP-3 비용에 다음 신호를 결합한다.

- 좌우 예측 mask의 중복/경계 위치
- 검은 배경과 연결된 gutter 후보
- Canny/Sobel high-frequency content를 가로지르는 비용
- 인쇄 edge 밀도가 높은 영역 회피
- seam 좌우에서 각 page mask가 유지하는 연결성
- fixed-layout 허용 band 밖으로 나가는 hard penalty

면적은 명백히 작은 노이즈 제거에만 사용한다. 최종 경로는 최소 면적 contour나
최대 사각형으로 결정하지 않는다.

WP-3과 WP-4는 동일한 solver와 diagnostics 계약을 사용해 cost 항만 비교 가능하게 한다.

### WP-5. 좌우 소유권 분리

각 seam 후보에 대해 세 정책을 비교한다.

1. hard ownership: seam 왼쪽/오른쪽으로 즉시 분리
2. uncertainty band 보존: band를 양쪽 crop에 보존하되 확정 mask에서는 제외
3. union-preserving assignment: band 안 픽셀을 page 연결성과 content cut 비용으로 배정

본문 보존이 최우선이므로 hard ownership의 overlap 0만으로 우수하다고 판정하지 않는다.
OCR 후속 입력 후보는 확정 mask와 보수적인 uncertainty-band crop을 모두 저장한다.

### WP-6. 정량 평가

기존 지표를 유지하고 다음을 추가한다.

- `prediction_overlap_px_before/after`
- `own_page_recall`
- `opposite_page_inclusion_px/ratio`
- `union_page_recall`
- `seam_cut_truth_px`
- `seam_cut_content_proxy_px/ratio`
- ambiguous truth overlap을 제외한 지표
- uncertainty band 안의 truth/content 픽셀 수
- seam x의 평균/최대 행간 이동량
- centerline으로부터 평균/최대 거리
- 최선·차선 경로 cost margin
- method/fallback/failure reason
- 처리시간

`content_proxy`는 OCR 정답이 아니므로 “본문 손실 0” 또는 OCR 품질로 표현하지 않는다.

### WP-7. 실제 데이터 일괄 비교 보고서

다음을 동일 실행 경로로 비교한다.

- 현재 overlapping mask
- fixed centerline baseline
- luminance-valley seam
- mask-aware content-preserving seam

보고서는 다음을 분리한다.

1. 실제 측정
2. 원본 해상도 육안 관찰
3. 네 spread에 한정된 잠정 해석
4. 실패 사례
5. 검증하지 못한 사항
6. paired OCR 패킷 진입 가능 여부

예정 보고서: `SPINE_SEAM_DETECTION_EXPERIMENT_REPORT.md`

## 6. 테스트 범위

### Unit tests

- 직선·곡선·부분 단절 synthetic gutter에서 연속 seam 검출
- 글자형 검은 edge가 gutter보다 강한 경우의 content 회피
- fixed-layout band 밖 최저 비용 경로 거부
- 급격한 지그재그 smoothness 억제
- 좌우 mask가 겹치지 않는 ownership 불변식
- 원래 union 대비 분리 union 손실 계산
- ambiguous truth 영역 제외 지표
- uncertainty band의 mask/crop 동작
- 빈 mask, 한쪽 mask만 존재, overlap 없음의 실패 reason
- full-frame/ROI-local 좌표 round-trip
- 비ASCII Windows 경로의 diagnostics/overlay 저장
- 기존 LabelMe 및 page-mask 평가 회귀 테스트

### 실제 데이터 검증

- 라벨 4장 × 좌우 8면
- 빈 받침대 2장 × 좌우 4면
- 비라벨 책 이미지의 실패 유형 관찰
- 방법별 seam/crop/contact sheet 육안 검토
- `pytest`, `compileall`, `git diff --check`

## 7. 잠정 판정 기준

작은 표본에서의 다음 값은 배포 합격 기준이 아니라 paired OCR 단계로 진입하기 위한
조건이다.

### `SEAM_CANDIDATE`

- 라벨 8면 각각의 `content_proxy_recall >= 0.995`
- ambiguous truth를 제외한 own-page recall 저하가 현재 overlapping crop 대비 면당
  0.5%p 이하
- 반대 페이지 유입이 네 spread 모두에서 현재보다 감소
- seam cut content proxy가 fixed centerline보다 일관되게 작음
- 빈 받침대에서 seam/page를 생성하지 않음
- 원본 해상도 overlay에서 명백한 본문 절단이 관찰되지 않음

### `FIXED_SEAM_ONLY`

- adaptive seam이 fixed centerline보다 일관되게 개선되지 않지만, 고정 seam이 현재
  overlap crop보다 반대 페이지 유입을 줄이고 보존 조건을 만족

### `MODEL_REQUIRED`

- 고전적 비용 조합이 글자·그림과 gutter를 구분하지 못함
- 반대 페이지 유입 감소와 본문 보존을 동시에 달성하지 못함
- 촬영별 조명 변화에 seam이 불안정함

동일 네 라벨로 파라미터를 선택하고 평가한 결과는 일반화 성능으로 주장하지 않는다.

## 8. 완료 조건

다음을 모두 충족한 항목만 구현 완료로 처리한다.

- 선행 보고서의 warp 과잉 결론이 정정됨
- 공통 seam 인터페이스와 명시적 실패 reason이 구현됨
- fixed, luminance-valley, mask-aware 세 후보가 동일 경로에서 실행됨
- ownership 분리 전후 union 손실과 opposite-page inclusion이 기록됨
- 라벨 8면과 빈 받침대 4면의 결과가 side별로 기록됨
- uncertainty band 포함/제외 crop이 모두 생성됨
- seam/cost/mask/crop/contact sheet 산출물이 생성됨
- 실제 측정과 육안 관찰, 미검증 사항이 분리된 보고서가 작성됨
- 기존 session/transmit/UVDoc/Document Parser 경로가 변경되지 않음
- 전체 단위 테스트와 정적 검증이 통과함

특정 seam 후보의 성공은 패킷 완료의 전제가 아니다. 실패를 재현하고
`MODEL_REQUIRED`로 판정하는 것도 유효한 완료 결과다.

## 9. 명시적 비범위

- coarse warp, UVDoc 재실행 또는 선택
- CLAHE, sharpening, deblur, super-resolution 비교
- Document Parser 실행
- OCR/점역 정확도 결론
- 수능특강 수학Ⅰ p30 비교
- segmentation neural network 학습
- 공개 데이터셋 수집·정제·증강
- session loop, quality/stability judge, transmit client 통합
- 카메라 또는 렌즈 calibration
- 사용자 LabelMe JSON 수정

## 10. 후속 Paired OCR 패킷에 넘길 계약

이번 패킷은 각 side에 대해 다음을 보존해야 한다.

- 원본 full-frame SHA-256
- segmenter와 seam config
- seam path와 uncertainty band
- 확정 mask와 보수적 crop bbox
- 원본 좌표 round-trip 정보
- resize/warp가 아직 적용되지 않은 원본 해상도 crop
- oracle/automatic 입력을 구분하는 provenance

후속 paired OCR은 이 무손실 기준 crop과 같은 source에서 생성한 coarse warp, UVDoc,
각 후보정 변형을 비교한다. seam 결과가 `MODEL_REQUIRED`여도 oracle crop을 이용한
보정 자체 실험은 별도 승인 후 진행할 수 있다.

## 11. 예상 변경 파일

신규 후보:

- `src/book_scanner/detect/spine_seam.py`
- `src/book_scanner/evaluation/seam_metrics.py`
- `src/book_scanner/evaluation/seam_experiment.py`
- `tools/evaluate_spine_seams.py`
- `tests/unit/test_spine_seam.py`
- `tests/unit/test_seam_metrics.py`
- `SPINE_SEAM_DETECTION_EXPERIMENT_REPORT.md`

최소 수정 후보:

- `PAGE_SEPARATION_EXTRACTION_EXPERIMENT_REPORT.md`
- `README.md`
- `.gitignore`의 대형 평가 출력 제외 규칙

수정 금지:

- 기존 원본 이미지와 LabelMe JSON
- `src/book_scanner/session/loop.py`
- `src/book_scanner/transmit/client.py`
- `src/book_scanner/correct/uvdoc_adapter.py`
- `src/book_scanner/correct/postprocess.py`
- Document Parser의 OCR/점역 파이프라인

## 12. 중단 및 재승인 조건

다음 상황에서는 범위를 넓히지 않고 결과를 보고한다.

- seam 검출에 ML weight 또는 새 framework가 필요함
- 공개 데이터셋 또는 외부 pseudo-labeling이 필요함
- 기존 LabelMe 경계를 수정해야 평가가 가능함
- 카메라/책받침의 새 실측 calibration이 필요함
- session/transmit 경로를 바꿔야 검증 가능함
- paired OCR, UVDoc 또는 화질 복원 실험을 이번 패킷에 포함해야 함

## 13. 승인 요청

이 패킷 승인 시 다음을 허용하는 것으로 해석한다.

1. 위 범위의 seam 검출·ownership·평가 코드와 테스트를 추가한다.
2. 현재 LabelMe 4개를 읽기 전용 정답으로 사용한다.
3. 빈 받침대 2개와 비라벨 이미지를 실패 유형 검증에 사용한다.
4. Git 제외 임시 폴더에 seam/cost/mask/crop/contact sheet를 생성한다.
5. 선행 보고서의 warp 과잉 결론을 측정 결과는 보존한 채 정정한다.
6. 실제 결과가 나오기 전에는 seam 방식이나 warp 정책을 채택 완료로 처리하지 않는다.
