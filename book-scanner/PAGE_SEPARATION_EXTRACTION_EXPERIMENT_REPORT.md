# 고정 구도 좌우 페이지 구분·추출 실험 보고서

상태: **구현·제한적 검증 완료 — `BOOTSTRAP_ONLY`**
실험일: 2026-08-30
근거: `PAGE_SEPARATION_EXTRACTION_WORK_PACKET.md`

## 결론

검은 배경 대비와 `RETR_EXTERNAL` 외부 윤곽, 고정 좌우 ROI를 결합한
`contrast-spatial`은 현재 네 라벨 spread에서 기존 두 baseline보다 페이지 보존과
빈 받침대 거부가 좋았다. 그러나 페이지 묶음 옆면과 반대 페이지가 mask에 상당량
포함된다. 따라서 **사람이 고칠 LabelMe 초안과 본문을 보수적으로 보존하는 crop에는
사용 가능하지만, 안정적인 최종 좌우 페이지 추출기로 채택할 근거는 부족하다.**

coarse homography 뒤 Laplacian variance가 감소했고, A는 warp 뒤 검은 배경 ring이
사라져 현재 검출기가 자주 실패했다. 그러나 서로 다른 해상도와 기하 스케일의
Laplacian variance는 순수한 blur 또는 OCR 성능 지표가 아니며, A의 실패도 warp 자체가
아닌 검출기 전제의 실패다. B의 mask 수치는 C보다 약간 좋았다. 실제 수능특강 수학Ⅰ
p30의 동일 원문 OCR/점역 비교 전에는 원본 crop, coarse warp, UVDoc 중 어느 것도
채택하거나 배제하지 않는다.

## 구현 결과

- LabelMe `left_page`/`right_page` full-frame polygon을 ROI-local 정답으로 직접 변환한다.
- 중심축 양쪽에 6%씩 겹치는 fixed-layout ROI를 지원한다. 이는 metric calibration이
  아니라 고정 촬영 구도에 대한 경험적 영상 좌표 prior다.
- `contrast-spatial`은 밝은 foreground, 검은 외곽 ring 대비, Canny 경계 지지,
  세로 coverage와 넓은 면적 plausibility를 결합한다. 면적 하나로 contour를 선택하지
  않으며 최종 표현은 곡선 binary mask다.
- page/safe-crop/content-proxy recall, leakage, 누락/과다 픽셀, bbox edge delta,
  crop 누락 픽셀, full-frame 좌우 예측 overlap을 기록한다.
- A/B/C coarse perspective 순서를 별도로 실행하고 anchor, 행렬, 보간법, warp 횟수,
  실패 reason과 Laplacian 선명도 비율을 저장한다.
- 자동 LabelMe 초안은 사람 검수 전임을 명시하고 generator/config/source SHA-256을
  기록한다. 기존 JSON은 기본적으로 덮어쓰지 않으며 원본 mask도 함께 저장한다.
- 기존 session/transmit/UVDoc 경로는 변경하지 않았다.

## 실제 측정

### Fixed-layout ROI

겹침이 없는 단일 중심선 후보는 책등을 넘는 곡면 때문에 양쪽 정답을 모두 보존하지
못했다. 네 spread 8면에서 중심선 fraction별 최소/평균 ROI page recall은 다음과 같다.

| 중심선 fraction | 최소 recall | 평균 recall |
|---:|---:|---:|
| 0.47 | 0.8152 | 0.9347 |
| 0.49 | 0.8741 | 0.9612 |
| 0.50 | 0.9032 | 0.9742 |
| 0.51 | 0.9318 | 0.9865 |
| 0.52 | 0.9599 | 0.9905 |
| 0.53 | 0.9597 | 0.9848 |

중심선 0.50에 좌우 0.06 overlap을 주면 현재 8면의 ROI recall은 모두 1.0이었다.
이는 같은 네 라벨에서 선택하고 측정한 값이므로 일반화 성능이 아니다. overlap은
본문 손실을 막지만 좌우 예측 mask의 full-frame 중복을 평균 922,211 px
(876,142~946,009 px)까지 허용했다. 다음 단계에서 책등 소유권을 별도 결정해야 한다.

### Segmenter 비교

동일 입력, centerline 0.50, overlap 0.06, 라벨 8면과 빈 받침대 4면을 사용했다.
legacy-background는 `175200`을 등록 배경으로 사용했다.

| 방식 | 평균 IoU | 평균 page recall | 최소 page recall | 평균 leakage | 빈 받침대 false-page |
|---|---:|---:|---:|---:|---:|
| contrast-spatial | 0.7785 | 0.9983 | 0.9965 | 0.2204 | 0/4 |
| brightness | 0.7418 | 0.9534 | 0.9002 | 0.2282 | 4/4 |
| legacy-background | 0.4706 | 0.8793 | 0.8640 | 0.4967 | 2/4 |

contrast-spatial의 라벨 8면 safe-crop page recall과 content-proxy recall은 모두
1.0이고 crop 누락 정답 픽셀은 모두 0이었다. 이는 본문 영역 정답이나 OCR 정확도가
아닌 proxy다. 원본 해상도 overlay 육안 확인에서는 본문은 보존됐지만 바깥쪽 페이지
묶음과 책등 부근의 반대 페이지가 파란 extra-background로 남았다. leakage 범위는
15.96~28.68%였다.

### 처리 순서 A/B/C

정답 mask에도 검출 결과와 동일한 homography를 적용해 라벨 8면을 비교했다.

| 순서 | 성공/8면 | 평균 IoU | 평균 page recall | 평균 leakage | 평균 선명도 비율(after/before) |
|---|---:|---:|---:|---:|---:|
| A: split → warp → crop | 3/8 | 0.7130 | 0.9992 | 0.2866 | 0.7526 |
| B: spread warp → split → crop | 8/8 | 0.7913 | 0.9984 | 0.2077 | 0.8463 |
| C: split → crop → warp | 8/8 | 0.7785 | 0.9983 | 0.2204 | 0.5795 |

A의 실패 5면은 `NO_PAGE_AFTER_WARP`였다. rough mask의 quad로 warp하면 페이지가 출력
대부분을 채워, 검출기가 요구하는 외곽 검은 배경 대비가 사라지는 구조적 실패다.
B는 모두 실행됐지만 하나의 spread homography가 V자의 두 평면을 동시에 보정한 것은
아니다. 육안상 원래의 곡률과 반대 페이지 유입이 남았으며 선명도도 평균 약 15% 감소했다.
C는 추출 경계는 가장 단순하고 안정적으로 실행됐지만 두 번째 보간으로 선명도 감소가
가장 컸다. 이 결과는 coarse warp를 채택하거나 생략할 근거가 아니다. **원본 crop은
무손실 기준 입력으로 보존하고, coarse warp와 UVDoc 및 후보정 결과는 paired OCR
검증 전까지 병렬 후보로 유지한다.** 원본 crop 역시 곡률·원근·배경 유입이 남아 있어
OCR에 적합하다고 입증되지 않았다.

전체 12장 24면에서는 A 5면 성공, B 17면 성공, C 20면 성공했다. 빈 받침대/책을
치우는 중간 장면도 포함되므로 이 성공 수를 정확도로 해석하지 않는다.

## 재현 명령

```powershell
$env:PYTHONPATH='src'
python tools/evaluate_page_masks.py TESTIMAGES `
  --output-dir D:\Projects\OCR\tmp\page-extraction-contrast-v3 `
  --segmenter contrast-spatial --centerline-fraction 0.5 `
  --spine-overlap-fraction 0.06 --labelme-dir TESTIMAGES

python tools/evaluate_extraction_orders.py TESTIMAGES `
  --labelme-dir TESTIMAGES `
  --output-dir D:\Projects\OCR\tmp\page-extraction-orders-v3

python tools/export_page_label_drafts.py TESTIMAGES `
  --output-dir D:\Projects\OCR\tmp\page-label-drafts-v1
```

평가 폴더에는 원본, 좌우 ROI, mask, overlay, truth comparison, crop, contact sheet와
JSON diagnostics가 있다. 이 대형 산출물은 Git에 넣지 않는다.

## 검증하지 못한 사항

- 네 spread와 같은 책/촬영 조건 밖의 일반화
- 인쇄 본문 영역 정답에 대한 실제 본문 보존율
- 페이지 묶음 옆면과 현재 상단 페이지의 안정적 분리
- overlap 영역에서 좌우 어느 페이지가 픽셀을 소유하는지 결정하는 spine seam 모델
- 실제 수능특강 수학Ⅰ p30 동일 원문의 OCR/점역 품질
- UVDoc 또는 coarse warp가 OCR에 주는 이득
- Raspberry Pi 처리시간과 메모리

## 다음 권고 작업

다음 패킷은 6장가량을 추가 라벨링해 총 약 10 spread의 검증 세트를 만든 뒤,
`contrast-spatial` 초안을 사람이 수정하는 비용과 책등/페이지 옆면 실패를 분류하는
것이 우선이다. 동시에 overlap strip 안에서 좌우 mask의 소유권을 centerline 하나가
아닌 밝기 ridge·곡률 방향·상하 연속성으로 결정하는 seam 후보를 비교해야 한다.
이 단계가 실패하면 classical 최종 추출을 더 미세 조정하기보다 공개 문서/책 데이터와
합성 검은 배경 augmentation을 이용한 소형 segmentation 모델 학습 패킷으로 전환한다.
