# book-scanner v2

문제집 페이지를 개조 휴대폰/PC 카메라로 스캔해 `document-parser`에 input으로 넘기는
파이프라인. **v1(단일 프레임 사전 촬영-가능 판정)은 폐기하고 처음부터 다시 설계했다** —
v1은 배경(책상/천)과 페이지가 하나의 컨투어로 뭉개지는 문제, 페이지 내부 인쇄물이
실제 페이지 경계보다 강한 엣지로 경쟁하는 문제 때문에 실사진 신뢰도가 낮았다.

## 핵심 전환: "촬영가능여부" → "전송가능여부"

v1은 촬영 *전에* "찍어도 되는가"를 저해상도 프리뷰 한 장으로 실시간 판단하려 했다.
v2는 다르다: 카메라가 고정된 환경에서 프레임을 **반복적으로 캡쳐**하고, 각 캡쳐+
후보정 결과에 대해 "**전송 가능한가**"를 사후 판단한다. 카메라 고정이라는 제약을
실제로 활용해서, 세션 시작 시 찍어둔 "책 없는 빈 프레임"과 각 캡쳐 프레임을
배경 차감(background subtraction)으로 비교한다 — 배경 텍스처가 무엇이든, 인쇄물이
페이지 위에 뭐가 있든 상관없이 "달라진 영역 = 책"으로 분리되므로 v1의 두 실패 원인이
구조적으로 사라진다.

## 전송가능여부의 세 축

1. **기하** (`judge/geometry_judge.py`) — 회전/크기/프레임경계. v1 `judge.py` 계승.
2. **안정성** (`judge/stability_judge.py`) — 최근 N프레임의 코너/면적이 일관되는지
   (책이 정지했는지). 반복 캡쳐 구조라서 처음으로 구현 가능해진 축(로드맵 Stage 4의
   원래 취지).
3. **화질** (`judge/quality_judge.py`) — document-parser 자신의
   `document_parser.preprocess.quality.ImageQualityGate`를 그대로 재실행. 새 화질
   기준을 만들지 않는다 — document-parser가 실제로 무엇을 안정적으로 받는지의
   권위있는 기준이 이미 거기 있다.

세 축 모두 실패해야 최종적으로 전송 거부(`TransmitBlockReason`), 어느 하나만
실패해도 그 프레임은 재시도 대상이 된다.

## 두 페이지 스프레드

책받침을 완만한 V자로 만들어 펼친 책을 올리는 설계를 사용자가 제안했다(곡률 완화 +
카메라를 책등 중심에 고정). 실제 예시 사진으로 확인한 것: 단순한 "사다리꼴 두 장
접붙인 리본" 모양이 아니라 책등 근처가 진짜 곡면으로 휘어 있다(로드맵이 이미 위험
요소로 짚어둔 문제). 물리적 V자 받침이 아직 없어 정확한 형상을 모델링할 수 없으므로,
**곡면을 직접 푸는 대신 중심선으로 프레임을 좌/우로 나누고 각각에 단일 페이지
파이프라인을 독립적으로 적용**한다(`detect/spread.py`). 왼쪽 페이지 전송 완료 →
오른쪽 페이지 → 둘 다 끝나면 다음 스프레드 감시로 자동 복귀.

중심선 위치는 이번 라운드에서 자동 검출하지 않고 세션 설정값(기본 50%)으로 취급한다
— 실제 받침이 없어 검증할 수 없는 상태에서 새 검출 알고리즘을 또 만들지 않기 위해서.

## 구조

```
src/book_scanner/
  detect/
    background.py   # 배경 등록 + 차감 -> foreground mask (순수 함수)
    corners.py        # foreground mask -> PageGeometry (v1의 해상도 독립 처리 계승)
    spread.py           # 프레임을 좌/우 서브프레임으로 분할
  correct/              # v1에서 거의 그대로 복구: 원근 보정 + 해시/원자적 저장 +
                         # 메타데이터. 검출 전략이 바뀌어도 유효했음 — v1 때 실사진으로
                         # document-parser 통합까지 검증됨
  judge/
    geometry_judge.py / stability_judge.py / quality_judge.py  # 세 축
    transmit_judge.py    # 세 축 합성 (기하->안정성->화질 순, 화질만 파일 I/O 있어
                          # 앞의 두 축을 통과해야 실행)
    guidance.py            # TransmitBlockReason -> 안내 문구 (비프음/TTS 연동은 보류)
  session/
    capture_source.py  # CaptureSource 프로토콜 + 웹캠/이미지시퀀스 구현체
    loop.py               # 상태 머신 제너레이터: 배경등록 -> (좌/우 반복) 판정 ->
                           # 가이드 또는 보정+전송 -> 완료 시 자동으로 다음 스프레드 대기
  transmit/
    client.py           # document-parser의 기존 remote_ingest 업로드 API 얇은 래퍼
                         # (책임 모듈 위치는 미정 -- 양쪽 다 옮기기 쉽게 분리해 둠)
```

## 실행

```bash
pip install -e .
python -m pytest tests/unit -q
```

수동 테스트(웹캠 또는 이미지 시퀀스로 실제 루프 돌려보기):

```bash
# 이미지 시퀀스 (첫 장이 배경 프레임)
python tools/run_session_cli.py --images bg.jpg f1.jpg f2.jpg ... --out-dir session_out

# 웹캠
python tools/run_session_cli.py --webcam --out-dir session_out

# 실제 document-parser 서버로 전송하려면
python tools/run_session_cli.py --images ... --out-dir session_out \
  --server http://localhost:8420 --api-key KEY --book-id my_book
```

## Stage 0~2 mask 실험 경로

기존 세션/전송 경로는 그대로 유지하면서, 좌우 ROI → 교체 가능한 segmenter →
`PageMask` → crop을 검증하는 오프라인 경로가 추가되어 있다. OpenCV brightness
segmenter는 최종 검출기가 아니라 측정/라벨 초안 baseline이다.

```bash
python tools/evaluate_page_masks.py IMAGE_OR_DIR --output-dir mask_eval
python tools/evaluate_page_masks.py CAPTURE_DIR --segmenter legacy-background \
  --background EMPTY_FRAME.jpg --output-dir legacy_eval
python tools/evaluate_page_masks.py TESTIMAGES --segmenter contrast-spatial \
  --spine-overlap-fraction 0.06 --labelme-dir TESTIMAGES --output-dir mask_eval
python tools/evaluate_extraction_orders.py TESTIMAGES --labelme-dir TESTIMAGES \
  --output-dir extraction_orders
python tools/export_page_label_drafts.py UNLABELED_IMAGES --output-dir label_drafts
python tools/evaluate_spine_seams.py TESTIMAGES --labelme-dir TESTIMAGES \
  --include-fixed-grid --output-dir spine_seam_eval
```

각 입력에 대해 좌우 ROI, mask, overlay, crop, diagnostics JSON을 저장한다. 정답
mask가 있으면 `--ground-truth-dir`로 IoU/Dice/boundary F1을 계산할 수 있다.
상세 범위와 실제 검증/미검증 상태는 `STAGE_0_2_IMPLEMENTATION_PLAN.md`에 기록했다.
고정 구도 페이지 추출의 최신 수치와 `BOOTSTRAP_ONLY` 판정은
`PAGE_SEPARATION_EXTRACTION_EXPERIMENT_REPORT.md`에 기록했다. 자동 LabelMe 출력은
사람이 검수하기 전에는 정답으로 취급하지 않는다.
좌우 overlap의 spine seam 및 소유권 분리 실험은
`SPINE_SEAM_DETECTION_EXPERIMENT_REPORT.md`를 참고한다. 현재 luminance-valley는
작은 라벨 집합에서만 `SEAM_CANDIDATE`이며 session 기본 경로에는 통합되지 않았다.
비라벨 stress 이미지는 정상 성공 표본이 아니라 오배치·부분 이탈·그림자·빈 받침대의
offline fallback 진단에 사용하며, 진단을 통과한 입력만 후속 OCR 후보로 취급한다.

## Oracle 라벨 기반 UVDoc 검증

페이지 검출 모델을 만들기 전에 LabelMe의 `left_page`/`right_page` 정답 polygon으로
페이지 crop을 생성하고, 외부 UVDoc checkout과 checkpoint를 주입해 보정만 독립적으로
시험할 수 있다. UVDoc과 PyTorch는 기본 패키지 의존성에 포함되지 않는다.

```bash
python tools/run_oracle_uvdoc_experiment.py \
  --image TESTIMAGES/20260826_175109.jpg \
  --label TESTIMAGES/20260826_175109.json \
  --uvdoc-runtime PATH_TO_UVDOC \
  --checkpoint PATH_TO_UVDOC/model/best_model.pkl \
  --device cpu \
  --output-dir experiment_outputs/uvdoc_oracle_20260826_175109
```

좌우 각각 `bbox_original`, `bbox_neutralized`, UVDoc 결과, 기존 homography 참고 결과,
해시와 diagnostics, contact sheet를 저장한다. 실제 한 장의 CPU 실험 결과와 아직
검증하지 않은 항목은 `UVDOC_ORACLE_EXPERIMENT_REPORT.md`를 참고한다.

실제 Document Parser의 PaddleOCR-VL → Page IR → 점역 경로로 oracle/UVDoc 결과를
검증할 때는 다음 도구를 사용한다. 모델 다운로드는 기본적으로 차단되며 명시적인 승인
후에만 `--allow-model-download`를 지정한다.

```bash
python tools/run_uvdoc_document_parser_evaluation.py \
  --experiment-dir experiment_outputs/uvdoc_ocr_ab_20260826 \
  --variant uvdoc_bilinear_original \
  --output-dir experiment_outputs/uvdoc_document_parser_20260826 \
  --model-home ../document-parser/data/debug/model_home_vl \
  --device gpu:0
```

이 평가는 일반 텍스트를 점역 실패로 세지 않는다. 현재 접근성 경로에서 점자 출력 대상은
수식 span과 표 셀이며, 서로 다른 원문끼리는 exact cell similarity를 계산하지 않는다.

## Paired OCR 입력 실험

같은 페이지에서 추출 방식과 보정 방식만 한 축씩 바꾸는 staged 실험은 다음 도구로
실행한다. `extraction`은 oracle/overlap/seam 4종, `geometry`는 oracle 및 보수 seam
crop의 none/coarse/UVDoc 3종을 준비한다. fallback stress와 빈 받침대는 OCR 전에
명시적으로 제외된다. 모델 cache와 device가 준비되지 않으면 다운로드나 암묵적 device
전환 없이 차단 상태를 기록한다.

```bash
python tools/run_paired_ocr_input_experiment.py --phase extraction --prepare-only
python tools/run_paired_ocr_input_experiment.py --phase extraction --device gpu:0
python tools/run_paired_ocr_input_experiment.py --phase geometry --prepare-only
python tools/run_paired_ocr_input_experiment.py --phase geometry --device gpu:0
python tools/run_paired_ocr_input_experiment.py --phase postprocess --device gpu:0
```

현재 작은 라벨 집합의 영상 지표, 실제 실행된 OCR 범위, device 차단 및 아직 검증하지
못한 결론은 `PAIRED_OCR_INPUT_EXPERIMENT_REPORT.md`에 분리해 기록했다.

## 이번에 하지 않은 것

실제 Pi 카메라 제어, 실제 버튼 GPIO 입력, 실제 비프음 회로/TTS 오디오 출력(문구
매핑까지만), document-parser 전달 책임 모듈의 최종 위치 확정, 동일 페이지 중복 스캔
방지(로드맵 Stage 7), 중심선(책등) 자동 검출(설정값으로만 처리), 책등 곡면의 실제
복원/평탄화(원근 보정은 여전히 평면 가정 — 좌/우 분할이 곡률 문제 자체를 없애주지는
않고, 물리적 완화에 기댄다).

물리적 V자 받침이 만들어지면: 실제 스프레드 사진으로 중심선 설정값이 맞는지, 좌/우
분할 후 각 파이프라인이 신뢰할 만하게 동작하는지, 안정성/화질 임곗값이 실측과 맞는지
재검증이 필요하다 — 지금은 전부 하드웨어 부재로 미검증 상태다.
