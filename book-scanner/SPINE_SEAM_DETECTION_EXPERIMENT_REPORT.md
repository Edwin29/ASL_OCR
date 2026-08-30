# 고정 구도 Spine Seam 검출·좌우 소유권 실험 보고서

상태: **추가 검증 완료 — fallback 통과 입력에 한한 잠정 `SEAM_CANDIDATE`**
실험일: 2026-08-30
근거: `SPINE_SEAM_DETECTION_WORK_PACKET.md`

## 결론

현재 네 라벨 spread에서는 **luminance-valley 연속 seam + union-preserving ownership**이
fixed seam과 mask-aware seam보다 좋았다. 기존 overlapping mask의 반대 페이지 유입
비율을 평균 11.38%에서 0.16%로 낮추면서, page union을 추가로 잃지 않았고, seam 적용
후 own-page recall은 평균 99.64%였다.

사전 진입 조건도 현재 네 라벨에서는 충족했다.

- 8면 content-proxy recall 최소 99.84%
- 기존 overlap 대비 own-page recall 최대 저하 0.469%p
- 네 spread 모두 반대 페이지 유입 감소
- 빈 받침대 4면 모두 `NO_PAGE`
- 원본 해상도 overlay에서 명백한 인쇄 본문 절단은 관찰되지 않음

따라서 후속 paired OCR 실험에 넘길 잠정 후보는 **fallback 진단을 통과한 입력의**
luminance-valley seam이다. 그러나
라벨이 네 spread뿐이고 같은 책·구도에서 파라미터를 선택하고 평가했으므로, 이는
일반화 성능이나 production 채택을 뜻하지 않는다. seam confidence도 0.046~0.103으로
낮고 아직 calibration되지 않았다.

## 구현 결과

- full-frame 각 행에 한 점을 갖는 `SpineSeam` 인터페이스
- fixed centerline, luminance-valley, mask-aware content-preserving 검출기
- 허용 band, 행간 이동 penalty, 경로 smoothing과 명시적 실패 reason
- hard, union-preserving, uncertainty-band ownership 정책
- full-frame/ROI-local seam 좌표 변환
- ambiguity-aware own/opposite page, union, content-cut 지표
- seam/cost map/분리 mask/ambiguous band/conservative crop/contact sheet 산출물
- 라벨 누락·불일치 제외 reason과 비ASCII 경로 대응
- session/transmit/UVDoc/Document Parser 기본 경로 비변경

## 지표 정의 보정

초기 계산에서는 Canny로 검출한 페이지 외곽선까지 인쇄 content proxy로 포함했다.
페이지 경계를 seam이 나누는 것을 본문 손실로 잘못 세지 않도록, 최종 지표는 LabelMe
정답 mask를 7 px 안쪽으로 erosion한 영역의 Canny edge만 인쇄 후보로 사용한다.
이 proxy는 실제 OCR 문자 정답이 아니며 OCR 정확도를 대신하지 않는다.

## 실제 측정

### 라벨 4장, 좌우 8면

모든 값은 `contrast-spatial`, centerline 0.50, ROI overlap 0.06을 공통 입력으로
사용했다. `opposite inclusion`은 출력 side mask 중 자기 정답에 속하지 않고 반대쪽
정답에만 속하는 픽셀의 비율이다.

| 방식 | own recall 평균 | own recall 최소 | content proxy 평균 | content proxy 최소 | opposite inclusion 평균 | union 추가 손실 |
|---|---:|---:|---:|---:|---:|---:|
| 기존 overlap | 0.99831 | 0.99651 | 0.99996 | 0.99967 | 0.11383 | 0 px |
| fixed 0.50 | 0.97307 | 0.90311 | 0.98639 | 0.93562 | 0.01961 | 0 px |
| fixed 0.52, grid 최선 | 0.98876 | 0.95968 | 0.99902 | 0.99330 | 0.00804 | 0 px |
| luminance-valley | **0.99645** | **0.99372** | **0.99952** | **0.99839** | **0.00159** | 0 px |
| mask-aware | 0.97365 | 0.90207 | 0.98773 | 0.93622 | 0.01914 | 0 px |

기존 좌우 예측 overlap은 라벨 spread 평균 922,211 px였다. union-preserving 정책은
공유 픽셀만 seam 좌우로 배정하므로 overlap을 0으로 만들면서 원래 mask union을 정확히
보존했다. luminance-valley의 own-page recall은 기존 overlap 대비 면별 평균 0.186%p,
최대 0.469%p 감소했다.

fixed grid는 centerline fraction 0.49/0.50/0.51/0.52와 uncertainty band
0/4/8/16 px, 세 ownership 정책을 비교했다. 가장 나은 fixed 0.52도 최소 own recall
95.97%로 adaptive luminance seam의 99.37%보다 낮았다. 같은 라벨로 fixed 값을 고른
결과이므로 별도 검증 성능으로 취급하지 않는다.

### Uncertainty band

8 px uncertainty-band의 확정 mask는 luminance-valley에서 spread당 평균 28,611 px의
원래 union을 판단 보류 영역으로 제외했다. 이 값은 삭제가 아니라 별도 ambiguous mask로
저장되며, conservative crop에는 양쪽 모두 포함된다. 후속 OCR에서는 확정 mask만으로
crop하지 않고 conservative crop과 비교해야 한다.

### 경로와 처리시간

- luminance-valley confidence: 0.0456~0.1029
- 중심선으로부터 평균 거리: spread 평균 52.2 px
- 중심선으로부터 최대 거리: 최대 171 px
- full-resolution 행간 최대 이동: 최대 3 px
- seam+ownership+metric 평균 처리시간:
  - fixed 0.50: 313.6 ms
  - luminance-valley: 341.9 ms
  - mask-aware: 382.9 ms

confidence는 최선 경로와 인접 endpoint 비용 차이에 기반한 실험값이며 확률이나
calibrated confidence가 아니다. 현재 값이 낮으므로 이후 더 다양한 책/조명에서
실패 임계값을 정해야 한다.

### 빈 받침대와 의도된 fallback 이미지

`175153`, `175200`의 좌우 4면에서 `contrast-spatial`이 모두 no-page였고, 세 seam
후보도 모두 `NO_PAGE`를 기록했다. 임의 seam이나 fixed fallback은 생성하지 않았다.

사용자 확인에 따라 비라벨 이미지 일부는 정상 seam 성공 사례가 아니라 그림자,
오배치, 부분 이탈 등의 fallback 처리를 검증하기 위한 표본으로 재분류했다. 기존
보고서에서 이들을 “비라벨 책 이미지에서 seam이 대체로 gutter를 따랐다”고 기술한
것은 불충분했다. seam이 계산 가능하다는 사실은 촬영 허용을 뜻하지 않는다.

오프라인 fixed-layout fallback 진단을 추가해 page 면적, bbox 폭·높이, 물리적 외곽
접촉과 3×3 내부 luminance 불균일을 기록했다. 결과는 다음과 같다.

| 이미지 | fallback 판정 | 주요 reason |
|---|---|---|
| `175110` | 통과한 비라벨 control | 없음 |
| `175116` | 거부 | right `OUT_OF_FRAME`, `PAGE_AREA_OUTLIER` |
| `175119` | 거부 | left narrow/area, right out-of-frame/area/uneven illumination |
| `175120` | 거부 | 양쪽 `OUT_OF_FRAME`, `PARTIAL_VERTICAL_EXTENT` |
| `175126` | 거부 | 양쪽 `OUT_OF_FRAME`, `PAGE_AREA_OUTLIER` |
| `175130` | 거부 | left `OUT_OF_FRAME`, right `PARTIAL_VERTICAL_EXTENT` |
| `175153`, `175200` | 거부 | 양쪽 `PAGE_NOT_FOUND` |

라벨 정상 4장은 모두 fallback 진단을 통과했다. 이 결과는 제공된 stress 표본을
구별한다는 제한적 근거다. 어떤 비라벨 이미지가 어떤 실패를 의도했는지에 대한 별도
정답 manifest가 없으므로 reason 단위 정확도나 일반화 성능으로 보고하지 않는다.
threshold는 fixed-layout의 잠정 영상 좌표 prior이며 metric calibration이 아니다.
session judge와 production fallback 정책은 변경하지 않았다.

## 방법별 관찰

### Fixed seam

구현이 단순하고 경로가 안정적이지만 곡률에 따라 책등 위치가 행별로 바뀌는 것을
반영하지 못했다. 0.50에서는 한 면의 own recall이 약 90.31%까지 낮아졌다. 0.52로
옮겨도 최소 95.97%에 머물렀다.

### Luminance-valley

검은 배경과 책등의 어두운 골짜기를 따라가는 현재 고정 구도에서 가장 효과적이었다.
본문 검은 글자에 끌리는 짧은 굴곡이 일부 있었지만 이동 penalty와 smoothing으로
연속 경로를 유지했다. 네 라벨에서는 판정 기준을 충족했다.

### Mask-aware

현재 cost 조합의 overlap hard penalty와 edge penalty가 page-mask 경계와 제목 박스에
지나치게 영향을 받아, 실제 결과가 fixed seam에 가까워졌다. luminance-valley보다
보존과 반대 페이지 제거가 모두 나았다는 근거가 없어 채택 후보에서 제외한다. 이는
mask-aware 접근 일반의 실패가 아니라 현재 비용 조합의 실패다.

## 재현 명령

```powershell
$env:PYTHONPATH='src'

python tools/evaluate_spine_seams.py TESTIMAGES `
  --labelme-dir TESTIMAGES `
  --stems 20260826_174943 20260826_174953 20260826_174958 20260826_175109 `
  --include-fixed-grid `
  --output-dir D:\Projects\OCR\tmp\spine-seam-labeled-grid-v2

python tools/evaluate_spine_seams.py TESTIMAGES `
  --labelme-dir TESTIMAGES `
  --output-dir D:\Projects\OCR\tmp\spine-seam-all-v2
```

최종 processing-time 포함 필수 6장 결과는
`D:\Projects\OCR\tmp\spine-seam-required-v4`에 저장했다. 대형 평가 산출물은 Git에
추가하지 않는다.

fallback 해석을 반영해 12장 전체를 다시 실행한 최종 진단은
`D:\Projects\OCR\tmp\spine-seam-fallback-v5`에 저장했다.

## 판정

현재 판정은 **fallback 통과 입력에 한한 잠정 `SEAM_CANDIDATE`**다.

- paired OCR 입력 후보: luminance-valley + union-preserving mask
- 본문 보존 우선 OCR 후보: luminance-valley + 8 px conservative crop
- 비교 기준: 원래 overlapping crop과 oracle LabelMe crop
- 제외 후보: 현 mask-aware cost 조합
- 촬영 거부 후보: offline fallback assessment가 reason을 반환한 입력

production 적용, session 통합 또는 자동 재촬영 안내 정책은 승인하거나 구현하지 않았다.

## 검증하지 못한 사항

- 다른 책, 종이색, 책 두께, 조명 및 카메라 미세 이동에서의 일반화
- 수식·표·작은 글자에 대한 실제 OCR 보존
- seam confidence threshold와 false-accept/false-reject 특성
- fallback reason별 정답 manifest와 다른 책/조명의 false accept/reject
- uncertainty band가 OCR에 주는 효과
- Raspberry Pi 처리시간과 메모리
- warp, UVDoc 또는 후보정과 결합했을 때의 OCR 효과

## 다음 작업

다음 패킷은 **fallback 진단을 통과한 같은 source에서만** 다음 입력을 생성해 기존
Document Parser에 넣는 paired OCR 실험이다.

1. oracle 원본 crop
2. overlap 원본 crop
3. luminance seam 확정 crop
4. luminance seam conservative crop
5. 각 crop의 coarse warp/UVDoc 변형
6. 각 보정 결과의 무처리/보수적 후보정 변형

이 실험 전에는 원본 crop, warp, UVDoc 또는 화질 복원 방식을 채택·배제하지 않는다.
