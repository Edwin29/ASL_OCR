# Stage 0~2 세부 구현 계획과 검증 기록

이 문서는 `CODEX_IMPLEMENTATION_CONTEXT.md`의 Stage 0~2만 구현하기 위한 범위와
완료 판단을 기록한다. 기존 `session/loop.py`, `transmit/client.py`, 4점 보정 경로는
비교 기준으로 보존한다. 새 mask 경로를 기존 전송 상태 머신에 합치는 일은 Stage 6의
사용자 상호작용/재시도 정책 결정 전에는 수행하지 않는다.

## Stage 0 — 기준선 보존과 재현

계획:

1. 기존 unit test를 변경 전 실행하고 결과를 기록한다.
2. legacy background subtraction을 `PageSegmenter` 공통 경계의 adapter로 제공한다.
3. 평가 실행마다 ROI 원본, mask, overlay, crop, JSON diagnostics를 남긴다.
4. 새 경로는 opt-in 오프라인 도구로 추가하고 기존 session/transmit 기본 동작을 바꾸지 않는다.

검증 기록:

- 2026-08-29, Python 3.12 격리 런타임: 변경 전 `41 passed in 1.20s`.
- 구현 후 전체 unit test: `52 passed in 0.49s`; `compileall` 및 `git diff --check` 통과.
- `tools/evaluate_page_masks.py --segmenter legacy-background --background ...`로 동일 입력을
  brightness baseline과 같은 출력 규칙으로 비교할 수 있다.
- 저장소의 평면 PDF 렌더 PNG 1장으로 brightness CLI의 raw/ROI/mask/overlay/crop/JSON
  저장을 smoke test했다. 같은 이미지를 legacy 배경/입력으로 사용했을 때 좌우 모두
  `no_page`와 `no_plausible_page_component`가 기록되는 것도 확인했다. 이 입력은 실제
  스캐너 사진이 아니므로 검출 정확도 검증으로 간주하지 않는다.

### TESTIMAGES.zip 실사진 기준선 관찰

작업 중 사용자가 추가한 `TESTIMAGES.zip` 12장을 원본 변경 없이 임시 디렉터리에서
일괄 실행했다. 육안 확인 결과 `175153`, `175200`은 서로 조명/반사가 다른 빈 받침대다.
나머지 이미지의 정확한 정답 mask는 없으므로 page detection의 정밀도는 계산하지 않았다.

- brightness baseline: 12장 × 좌우 24개 ROI를 전부 `page`로 분류했다. 따라서 빈
  받침대 2장에서도 4/4 ROI가 false capture 후보가 되는 실패가 재현됐다.
- legacy background baseline (`175153`을 background로 등록): 등록 프레임의 좌우는
  `no_page`였지만 다른 빈 받침대 `175200`은 좌우 모두 `page`로 오검출했다. 조명과
  반사 변화에 대한 기존 경로의 실패가 재현됐다.
- legacy가 책 이미지에서 만든 20개 page 결과는 모두 물리 full-frame outer edge와
  접촉했다고 기록됐다. 현재 geometry 정책과 결합하면 `OUT_OF_FRAME` reject가 될 수
  있어, 책등/ROI/물리 외곽 경계를 분리해야 한다는 설계를 뒷받침한다.
- full-resolution 4000×3000 이미지에서 측정된 side당 처리시간은 brightness 약
  79~118 ms, legacy 약 52~61 ms였다. 개발 PC의 단발 측정이며 Raspberry Pi 성능으로
  해석하지 않는다.

overlay를 육안 확인했지만 ground-truth mask가 없으므로 IoU/Dice/boundary F1, 본문
잘림, 상단 페이지와 페이지 묶음 분리는 여전히 미검증이다.

## Stage 1 — 페이지 mask 경계

계획:

1. `PageSegmenter` protocol과 `SegmentationResult`를 모델 독립 계약으로 둔다.
2. `StaticPageSegmenter`로 ML 런타임 없이 파이프라인을 시험한다.
3. fraction centerline과 normalized calibrated polygon을 모두 지원하는 `PageROI`를 둔다.
4. largest component, morphology, bbox, area ratio, centroid, confidence, edge contact를
   `PageMask`로 측정한다.
5. 책등 접촉과 실제 full-frame 외곽 접촉을 분리하고 모든 좌표를 full frame으로 역매핑한다.
6. padding crop과 mask 바깥 중립화를 선택적으로 제공한다.
7. `session/mask_pipeline.py`에서 fake segmenter로 실제 ROI → mask → crop 준비 경계를
   실행하되, 전송/재시도 정책은 기존 상태 머신과 결합하지 않는다.

완료 판단:

- 코드/합성 unit test로 ROI-local → full-frame mapping과 mask → crop을 검증한다.
- 실제 페이지 의미 분할 정확도와 임곗값은 데이터 부재로 완료 처리하지 않는다.
- 기존 `PageGeometry`나 `minAreaRect`를 새 mask 타입으로 재사용하지 않는다.

## Stage 2 — 오프라인 segmentation 평가 도구

계획:

1. 단일 이미지 또는 디렉터리 입력을 지원한다.
2. 각 이미지의 좌/우 raw ROI, mask, overlay, crop과 전체 summary JSON을 저장한다.
3. confidence, area ratio, centroid, edge contact, 처리 시간을 기록한다.
4. `<stem>_<side>.png` 정답 mask가 있으면 IoU, Dice, tolerance boundary F1을 계산한다.
5. OpenCV brightness baseline과 legacy background adapter를 동일 실행 경계에 둔다.

완료 판단:

- 합성 입력으로 산출물, no-page, metric 계산을 unit test한다.
- 실제 예시 세트 전체 결과, 실제 실패 유형 분류, Pi 처리시간은 해당 데이터/장비가 없어
  미검증으로 남긴다.
- OpenCV baseline은 최종 모델이나 확정 threshold가 아니라 실험/라벨 초안 도구다.

## 재현 명령

```bash
python -m pytest tests/unit -q
python tools/evaluate_page_masks.py IMAGE_OR_DIR --output-dir mask_eval
python tools/evaluate_page_masks.py CAPTURE_DIR --segmenter legacy-background \
  --background EMPTY_FRAME.jpg --output-dir legacy_eval
```

정답 mask는 `--ground-truth-dir` 아래에 `<image-stem>_left.png`,
`<image-stem>_right.png`로 둔다. calibrated ROI는 JSON normalized polygon을
`--left-polygon`, `--right-polygon`에 함께 전달한다.

## Stage 2 이후 미결정 항목

- 실제 segmentation 모델/weight, confidence와 mask validity threshold
- 실제 촬영 데이터의 label 정의 검증 및 session/book 단위 split
- mask stability와 기존 session 상태 머신의 통합 정책
- 동일 spread 원본에서 좌우를 함께 처리할지 여부
- UVDoc weight 배포, 라이선스 고지, CPU/Pi 성능 및 OCR 품질 A/B
