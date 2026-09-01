# book-scanner

문제집 페이지를 개조 휴대폰/PC 카메라로 스캔해 `document-parser`에 input으로 넘기는
파이프라인. 단일 프레임을 촬영 전에 판정하는 초기 설계는 폐기했다. 현재 저장소에는
배경 차감 기반 legacy session loop와, 오프라인에서 검증한 `seam-conservative + UVDoc`
구현이 함께 있다. 연속 영상 runtime은 V0 계약, V1/V1.1/V1.2 PC 표본 frame engine,
V2 `seam-conservative + UVDoc bilinear` atomic artifact, V3-A/V3-A.5의 identity·ACK 이후
page-change까지 구현됐다. 인접 `device-runtime`에는 V3-B single-sender durable outbox와 Server
V4 HTTP client, Device Integration E0-Core local composition이 구현됐다. 실제 Laptop camera/STM/audio
검증은 Device Integration E0-B — Laptop Acceptance로 분리했다.

## 핵심 전환: "촬영가능여부" → "전송가능여부"

v1은 촬영 *전에* "찍어도 되는가"를 저해상도 프리뷰 한 장으로 실시간 판단하려 했다.
새 runtime의 기준은 카메라 프레임을 **반복적으로 획득**하고, 이미 획득해 실제 crop과
후보정까지 만든 artifact가 전송 계약을 만족하는지 사후 판단하는 것이다. 기존 loop의
빈 프레임 기반 배경 차감은 비교 가능한 legacy 경로로 보존하지만, 그림자·책 이동·빈
배경 갱신에 민감하므로 새 기본 검출 근거로 채택하지 않는다.

## 전송 준비도의 세 계층

1. **후보 준비도** — 매 camera frame이 아니라 설정 주기로 최신 frame을 표본화하고,
   motion·잘림·blur·노출·최근 안정성을 저비용으로 평가해 비싼 처리를 시도할 frame을
   고른다. 최종 전송 판정은 아니다.
2. **artifact 준비도** — 같은 full-spread frame에서 좌우 seam crop과 UVDoc 결과를
   만들고 영상·기하·lineage를 검증한다.
3. **parser 인수 및 전달 확인** — 서버가 실제 Document Parser 입력 계약을 검사하고
   artifact를 내구성 있게 접수한 뒤 job ID를 반환한다.

단일 bool이나 포괄적인 `LOW_QUALITY`로 합치지 않는다. 로컬 재촬영 사유, 네트워크 재시도,
parser 거부를 분리해야 사용자에게 잘못된 물리 조정 안내를 하지 않는다.

## 두 페이지 스프레드

책받침을 완만한 V자로 만들어 펼친 책을 올리는 설계를 사용자가 제안했다(곡률 완화 +
카메라를 책등 중심에 고정). 실제 예시 사진으로 확인한 것: 단순한 "사다리꼴 두 장
접붙인 리본" 모양이 아니라 책등 근처가 진짜 곡면으로 휘어 있다(로드맵이 이미 위험
요소로 짚어둔 문제). 물리적 V자 받침이 아직 없어 정확한 형상을 모델링할 수 없으므로,
곡면 자체를 사각형으로 가정하지 않고 luminance-valley 기반 spine seam과 보수적 소유권
분리를 적용한 뒤 각 페이지를 UVDoc으로 보정한다. 좌우는 반드시 **같은 full-spread
frame**에서 만들고 한 `SpreadArtifact`로 묶는다. 현재 `session/loop.py`의 왼쪽 완료 후
오른쪽을 별도 frame에서 처리하는 방식은 legacy이며 새 runtime에서 교체할 대상이다.

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
  video/
    sources.py          # PC camera, MP4, image sequence의 표본 frame source
    candidate.py        # bounded 안정 window와 hard gate/best-frame 선택
    engine.py           # start/cancel/retry/ready 비동기 sampled-frame 상태 엔진
    types.py            # 같은 full-spread frame lineage와 readiness 계약
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
`SPINE_SEAM_DETECTION_EXPERIMENT_REPORT.md`를 참고한다. 2026-08-30 결정으로
`seam-conservative + UVDoc bilinear`를 영상 Scanner의 기본 처리 경로로 채택했다. 현재
offline 구현과 p30 검증은 완료됐지만 session 영상 runtime 통합은 아직 진행 전이다.
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

실제 수능특강 수학 I p30 촬영본을 기존 p030 회귀 fixture와 동일 원문으로 비교하는 staged
실험은 다음 runner를 사용한다. `prepare`는 UVDoc이 있는 CPU 환경에서, OCR 단계는 기존
GPU PaddleOCR-VL 환경에서 실행한다. 모델은 자동 다운로드하지 않는다.

```bash
python tools/run_p030_document_parser_validation.py prepare --image-dir <labelme-input-dir>
python tools/run_p030_document_parser_validation.py oracle --device gpu:0
python tools/run_p030_document_parser_validation.py automatic --device gpu:0
python tools/run_p030_document_parser_validation.py postprocess-prepare
python tools/run_p030_document_parser_validation.py report
```

`postprocess-prepare`가 `POSTPROCESS_NOT_TRIGGERED`를 반환하면 bicubic/unsharp OCR은 실행하지
않는다. p030 fixture는 Document Parser 개발 과정에서 사람이 직접 검증한 p30 golden이다.
p30 밖의 다른 페이지에 그 지위를 자동으로 일반화하지 않는다.

연속 영상, 버튼 start/cancel, 같은 full-spread frame의 좌우 처리, 전송 준비도 계층,
guidance, durable outbox와 PC→Pi 4 확장 설계는
`SCANNER_CONTINUOUS_TRANSFER_READINESS_DESIGN.md`를 기준으로 한다.
승인된 첫 구현 범위는 `SCANNER_VIDEO_V0_CONTRACT_WORK_PACKET.md`,
`SCANNER_VIDEO_V1_FRAME_ENGINE_WORK_PACKET.md`,
`SCANNER_VIDEO_V1_1_RUNTIME_HARDENING_WORK_PACKET.md`,
`SCANNER_VIDEO_V2_SEAM_UVDOC_ARTIFACT_WORK_PACKET.md`,
`SCANNER_VIDEO_V3_A_PAGE_IDENTITY_CHANGE_GATE_WORK_PACKET.md`,
`SCANNER_VIDEO_V3_A_1_BOTTOM_ROI_PAGE_NUMBER_IDENTITY_WORK_PACKET.md`로 분리했다.
V0~V2의 PC sampled-frame 및 `seam-conservative + UVDoc bilinear` atomic artifact 경로와,
V3-A의 동일 실행 중 page identity·single in-flight·ACK 이후 page-change gate를 구현했다.
V3-A의 실제 p30 identity 결과와 검증 한계는 `SCANNER_VIDEO_V3_A_IMPLEMENTATION_REPORT.md`를
참조한다. V3-A.1의 bottom ROI page-number 계약·fusion은 구현됐으나 production recognizer는
아직 선발되지 않았다. V3-A.2에서 71KiB OpenCV-DNN 숫자 모델을 구현했고 corrected p30 왼쪽
golden과 PC resource budget은 통과했지만, 1920px preview의 붙은 숫자 분할로 temporal consensus
release가 0건이었다. 따라서 provider는 여전히 opt-in이며 visual fallback을 유지한다. backend별
p30 정확도·PC 지연은 `SCANNER_VIDEO_V3_A_1_IMPLEMENTATION_REPORT.md`, V3-A.2 모델·500/750/1000ms
replay와 선발 보류 근거는 `SCANNER_VIDEO_V3_A_2_IMPLEMENTATION_REPORT.md`를 참조한다.
V3-A.3에서는 로컬 Paddle recognition-only와 명시적 호출 scheduler를 구현해 CandidateGate와
VisualGate의 절감률을 분리했다. 기본 750ms에서 VisualGate의 추가 Paddle 요청 억제는 22.2%로
사전 30% 가치 gate를 통과하지 못했고 page-key K=3 release도 0건이었다. 500ms에서는 37.5% 절감과
진단 release 1건이 있었지만 `316/317` 및 안정 구간이 사람 golden이 아니므로 default를 바꾸지
않았다. 상세 결과는 `SCANNER_VIDEO_V3_A_3_IMPLEMENTATION_REPORT.md`를 참조한다.

현재 작은 라벨 집합의 영상 지표, 실제 실행된 OCR 범위, device 차단 및 아직 검증하지
못한 결론은 `PAIRED_OCR_INPUT_EXPERIMENT_REPORT.md`에 분리해 기록했다.

V3-A.2의 offline 재현 도구는 다음과 같다. 학습용 PyTorch/ONNX는 production dependency가 아니며,
runtime은 hash-pinned ONNX를 기존 OpenCV DNN으로만 읽는다.

```bash
python tools/generate_page_number_synthetic_dataset.py --help
python tools/train_page_number_digit_model.py --help
python tools/run_scanner_video_v3a2_backend_evaluation.py --help
python tools/run_scanner_video_v3a2_temporal_replay.py --help
python tools/run_scanner_video_v3a3_paddle_capture.py --help
python tools/run_scanner_video_v3a3_scheduler_replay.py --help
python tools/summarize_scanner_video_v3a3_value.py --help
python tools/run_scanner_video_v3a4_footer_capture.py --help
python tools/run_scanner_video_v3a4_footer_replay.py --help
python tools/summarize_scanner_video_v3a4_footer_identity.py --help
python tools/run_page_number_stage_paired_experiment.py --help
```

V3-A.4에서는 정확한 번호 대신 좌우 bottom ROI의 raw OCR pair를 opaque identity로 반복 비교했다.
현재 두 spread의 disjoint 100ms/N=5 진단에서 native raw pair는 `p_same=0.90`, 관찰
`p_diff=0.00`이었고 기존 full-page VisualGate의 `p_same=0.70`보다 높았다. 다만 different identity가
두 개뿐이므로 `PROVISIONAL_CANDIDATE_DATA_INSUFFICIENT`이며 일반화 검증은 완료되지 않았다.
V3-A.5에서는 표본 확보가 통합 개발을 막지 않도록 이 M1을 `validated=false` 기본 runtime 전략으로
연결했다. 안정 후보 뒤 native bottom ROI를 100ms 간격, N=5, `K_same=1/K_diff=0`으로 확인하고,
SAME이면 V2 전에 억제하며 서버 ACK만 pending bank를 accepted bank로 승격한다. 명시적
`LEGACY_VISUAL` rollback과 hash-pinned local Paddle fail-fast composition도 유지한다. 상세 수치와
N=10 미측정 사유는 `SCANNER_VIDEO_V3_A_4_IMPLEMENTATION_REPORT.md`, 구현 결과는
`SCANNER_VIDEO_V3_A_5_IMPLEMENTATION_REPORT.md`를 참조한다.

번호 인식 시점을 1920 preview/native preview/seam crop/UVDoc 후로 고정 비교한 결과와,
missing-side만 native로 재시도하는 보수적 후보의 근거는
`PAGE_NUMBER_RECOGNITION_STAGE_PAIRED_EXPERIMENT_REPORT.md`에 기록했다. UVDoc 뒤 인식이나
native 전면 전환은 이 표본에서 개선으로 입증되지 않았다.

## 아직 완료하지 않은 것

실제 Laptop camera/UVDoc/Paddle smoke, 비프음/TTS, STM, Pi 카메라·GPIO, Pi 4에서의 UVDoc 위치와
성능은 아직 구현·검증하지 않았다. E0-Core deterministic local composition과 V3-B/V4 loopback은
완료됐지만 전체 Coordinator active scan restart와 외부 network 동작은 검증하지 않았다. V3-A identity와
page-change 임곗값도 충분한 held-out spread 및 MP4 page-change timeline으로 calibration하지
않았다. M1은 기본 구성이나 `validated=false`이며, semantic page-number 정확도나 일반적인
false-duplicate율을 입증한 것으로 보지 않는다. Paddle 모델 경로·manifest가 없는 M1 구성은
시각 방식으로 자동 fallback하지 않고 실패한다. seam과 UVDoc의 p30 채택 근거를 다른 책·조명·그림자·
부분 잘림에 자동 일반화하지 않는다.

V3-A.5 이후 Server S0/S1/C0/V4, Scanner V3-B와 Device Integration E0-Core까지 본래 통합 흐름을
진행했다. 다음 우선순위는 실제 Laptop camera/STM/audio와 internet HTTPS tunnel을 통한 desktop Server의
Device Integration E0-B — Laptop Acceptance이며, 이후 production network hardening과 Pi 4 이식으로
진행한다. 추가 M1 표본 검증과 V3-B 운영 hardening은 선행 blocker가 아니다.

세부 상태, 책임 경계, 실패 이유, 구현 단계와 검증 기준은
`SCANNER_CONTINUOUS_TRANSFER_READINESS_DESIGN.md`를 따른다.
