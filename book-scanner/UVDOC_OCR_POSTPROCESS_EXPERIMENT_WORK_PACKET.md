# UVDoc 화질 보존 및 Document Parser OCR A/B 실험 — 작업 패킷

상태: **IMPLEMENTED — 실제 production 경로 검증 완료, downstream acceptance 불통과**
작성일: 2026-08-30
승인: 2026-08-30
선행 결과: `UVDOC_ORACLE_EXPERIMENT_REPORT.md` (`CONDITIONAL`)

## 1. 목적

손수 라벨링한 4개 spread의 좌우 oracle page crop을 이용해 다음 두 질문을 분리해서
검증한다.

1. UVDoc의 곡률 보정 과정에서 발생하는 선명도 저하를 interpolation 또는 보수적인
   후보정으로 줄일 수 있는가?
2. 육안상의 선명도 변화가 실제 `document-parser`의 PaddleOCR-VL → Page IR → 점역
   결과에서 동등하거나 더 나은 파이프라인 건전성을 보이는가?

Laplacian variance 같은 영상 지표를 최종 목표로 삼지 않는다. 최종 선택은 실제 OCR의
인식량, confidence, 오류 진단과 overlay 검토를 기준으로 한다. 정답 transcription이
없으므로 CER 개선이나 절대 OCR 정확도는 주장하지 않는다.

## 2. 현재 확인된 사실

### 입력

| 이미지 | 라벨 | 용도 |
|---|---|---|
| `20260826_174943.jpg` | `20260826_174943.json` | 같은 spread 반복 촬영 A |
| `20260826_174953.jpg` | `20260826_174953.json` | 같은 spread 반복 촬영 B |
| `20260826_174958.jpg` | `20260826_174958.json` | 다른 spread |
| `20260826_175109.jpg` | `20260826_175109.json` | 선행 UVDoc 실험 spread |

- 네 LabelMe 파일 모두 4000×3000 원본과 크기가 일치한다.
- `left_page`, `right_page` polygon이 모두 존재하고 자기교차가 없다.
- polygon은 물리 frame edge에 닿지 않는다.
- `174943`과 `174953`은 독립적인 책/내용 샘플이 아니라 프레임 간 재현성을 보는 paired
  sample로 취급한다.
- 전체 입력은 4장·8페이지지만 일반화 성능을 주장할 데이터 규모는 아니다.

### 선행 화질 관찰

`175109`의 `bbox_original` 대비 공식 UVDoc bilinear 출력에서 전체 이미지 Laplacian
variance가 다음과 같이 감소했다.

| Side | Crop | UVDoc bilinear |
|---|---:|---:|
| left | 183.1 | 92.1 |
| right | 408.3 | 221.1 |

이 값은 재표본화에 따른 부드러움이 실제로 있음을 시사하지만, 페이지 외곽·배경 edge의
영향을 받으므로 OCR 개선/악화를 직접 증명하지 않는다.

### Document Parser OCR 경로

- 설치 확인: `paddleocr==3.7.0`, `paddlepaddle==3.3.1`, `paddlex==3.7.2`
- 일반 OCR 기준: `PP-OCRv5_server_det` + `korean_PP-OCRv5_mobile_rec`
- 두 일반 OCR model directory는 로컬에 존재한다.
- 기본 OCR 설정은 CPU, MKLDNN off, 2 threads, `text_det_limit_side_len=1600`,
  `text_det_limit_type=max`다.
- OCR 자체의 document unwarping은 꺼져 있으므로 UVDoc과 중복 보정하지 않는다.
- 실제 datapack ingest는 PaddleOCR-VL을 사용한다. 현재 일반 OCR 실험만으로 최종
  datapack 품질까지 검증했다고 주장하지 않는다.

## 3. 승인 시 확정되는 원칙

- 기존 LabelMe polygon과 원본 이미지는 수정하지 않는다.
- 기존 session loop와 transmit client를 변경하지 않는다.
- UVDoc 공식 bilinear 결과를 항상 control로 보존한다.
- 샤프닝은 색상 halo를 줄이기 위해 luminance channel에만 적용한다.
- OCR engine 설정은 후보별로 동일하게 유지한다.
- OCR을 잘 보이게 만들기 위해 threshold를 후보별로 조정하지 않는다.
- OCR model과 UVDoc model은 batch당 한 번만 load하고 재사용한다.
- runtime 중 자동 model 다운로드를 허용하지 않는다.
- 이미지 지표가 좋아져도 OCR이 악화되면 후보를 채택하지 않는다.
- 실제 PaddleOCR-VL을 실행하지 못하면 production OCR 검증을 완료로 표시하지 않는다.

## 4. 실험 행렬

각 입력의 좌우 8페이지에 다음 8개 variant를 생성한다. 일반 OCR 결과는 보조 진단용
캐시로만 유지하며, 승인 후 요구사항 정정에 따라 64회 완료는 더 이상 최종 완료 조건이
아니다.

| ID | 입력/보정 | 목적 |
|---|---|---|
| `crop_original_control` | oracle bbox 원본 crop | UVDoc 전 OCR 대조군 |
| `legacy_homography_control` | 기존 4점 homography | 기존 보정 대조군 |
| `uvdoc_bilinear_original` | 원본 배경 crop + 공식 bilinear | 공식 UVDoc control |
| `uvdoc_bilinear_neutralized` | mask 밖 흰색 + 공식 bilinear | 입력 배경 정책 비교 |
| `uvdoc_bicubic_original` | 원본 배경 crop + bicubic sampling | interpolation 비교 |
| `uvdoc_bicubic_neutralized` | mask 밖 흰색 + bicubic sampling | interpolation/배경 조합 |
| `uvdoc_unsharp_original` | 공식 bilinear 후 약한 luminance unsharp | 후보정 비교 |
| `uvdoc_unsharp_neutralized` | neutralized + 공식 bilinear 후 unsharp | 후보정/배경 조합 |

`bicubic + unsharp` 조합은 두 효과를 구분할 수 없고 조합 수를 늘리므로 이번 범위에서
제외한다.

## 5. 고정 후보정 사양

### Bicubic sampling

- UVDoc이 예측한 sampling grid는 그대로 사용한다.
- `torch.nn.functional.grid_sample`의 sampling mode만 `bilinear`에서 `bicubic`으로
  바꾼다.
- `align_corners=True`와 나머지 공식 demo 호환 설정은 유지한다.
- adapter 기본값은 계속 `bilinear`로 두어 기존 결과를 변경하지 않는다.

### Luminance unsharp

초기 후보는 한 세트만 사용한다.

- BGR → Lab 변환 후 L channel만 처리
- Gaussian sigma: 1.0
- amount: 0.5
- 원본 L과 blur 차이가 3 intensity 미만인 영역은 증폭하지 않음
- 결과 clip 후 uint8 BGR 복원
- 입력 배열을 수정하지 않음

이는 production 기본값이 아니라 A/B 후보의 고정 조건이다. 결과를 보고 amount를 여러
개 sweep하거나 CLAHE를 추가하려면 별도 판단을 한다.

### 2026-08-30 승인 후 요구사항 정정

- 일반 PP-OCR 토큰 confidence는 선별용 보조 지표로만 사용한다.
- 최종 검증 입력은 실제 datapack ingest와 같은 `PaddleOcrVlAdapter` 및
  `build_document_ir_from_vl` 경로를 통과시킨다.
- 그 결과를 `flatten_document`, `math_focus_item_to_braille`,
  `table_cell_braille`에 넣어 점역 기회·성공·보류·오류를 기록한다.
- 저장된 `tests/fixtures/accessibility/p030.json`과 `data/debug/demo_p030/braille`은
  기존 점역 경로가 그대로 동작하는지 확인하는 회귀 기준이다.
- 새 촬영본은 p030과 원문이 다르므로 exact OCR text/cell similarity를 주장하지 않는다.
  같은 원문의 정답 점역이 발견되거나 제공된 경우에만 cell similarity를 계산한다.
- 일반 텍스트는 현재 제품 정책상 점자 출력 대상이 아니므로 빈 점자 출력을 실패로
  세지 않는다. 새 페이지에 수식과 표가 없으면 점역 품질은 `NOT_APPLICABLE`로 둔다.

## 6. 구현 작업

### WP-1. 추가 oracle 입력 batch 검증

책임:

- 4개 이미지/JSON pairing과 SHA-256 기록
- LabelMe 크기, 필수 label, 자기교차, overlap, winding, frame-edge 접촉 검증
- 각 페이지 mask/overlay/contact sheet 저장
- 같은 page ID가 variant 사이에서 안정적으로 대응하도록 naming 규칙 확정

예정 page ID:

```text
{capture_stem}_{left|right}_{variant}
```

### WP-2. UVDoc sampling mode 확장

예정 수정:

- `src/book_scanner/correct/uvdoc_adapter.py`
- 필요 시 `src/book_scanner/correct/unwarper.py`

책임:

- `UVDocConfig.sampling_mode`에 `bilinear`/`bicubic` 허용
- 기본값 `bilinear` 유지
- 지원하지 않는 mode는 inference 전에 명시적 `INVALID_INPUT` 반환
- 두 mode 모두 output shape/dtype/channel/finite 검증
- diagnostics에 sampling mode 기록

### WP-3. 보수적 후보정 모듈

예정 파일:

- `src/book_scanner/correct/postprocess.py`

책임:

- model과 독립적인 `ImagePostprocessor` 경계
- no-op과 luminance unsharp 구현
- 적용 parameter를 diagnostics와 artifact metadata에 기록
- 실패 시 원본 UVDoc 결과를 보존하고 명시적 reason 반환

### WP-4. OCR batch runner

예정 파일:

- `src/book_scanner/evaluation/ocr_ab_experiment.py`
- `tools/run_uvdoc_ocr_ab_experiment.py`

책임:

- 8페이지 × 8 variant 생성 및 lineage 저장
- `document-parser`의 `create_baseline_ocr_adapter` 재사용
- CPU 일반 OCR model 1회 load 및 순차 재사용
- OCR token, bbox, text, confidence, engine version, runtime 저장
- 중단 후 재실행 시 image hash + engine signature가 같은 결과 cache 재사용
- 한 variant 실패가 다른 page/variant 실행을 막지 않도록 실패 artifact 보존
- 입력, label, UVDoc checkpoint, 생성 이미지, OCR JSON의 SHA-256 연결

### WP-5. 이미지 품질 지표

각 variant에서 다음을 기록한다.

- 출력 해상도와 aspect ratio
- 전체 이미지 Laplacian variance
- 바깥쪽 5%를 제외한 내부 영역 Laplacian variance
- Tenengrad 또는 동등 gradient energy
- 1600px long-edge로 정규화한 proxy 이미지에서 같은 지표
- `document-parser` ImageQualityGate 결과

1600px proxy는 PaddleOCR 내부 preprocessing과 완전히 같다고 주장하지 않는다. 후보 간
동일 크기 비교를 위한 보조 지표로만 쓴다.

### WP-6. OCR 비교 지표

페이지/variant별:

- token 수와 비공백 문자 수
- confidence 평균, 중앙값, 최솟값, 10 percentile
- confidence 0.5 미만 token 수와 비율
- OCR issue code
- bbox 면적/분포와 비정상적으로 큰 token 수
- OCR 처리시간
- 정규화된 OCR text dump와 overlay

전체 집계:

- 공식 bilinear control 대비 variant별 delta
- 좌/우 side별 delta
- 8페이지 중 개선/동률/악화 수
- `174943`과 `174953` 동일 side 사이의 정규화 text similarity

paired-frame similarity는 재현성 지표이며, 두 결과가 동일하게 틀릴 수 있으므로 정확도
지표로 해석하지 않는다.

### WP-7. 실제 Document Parser acceptance gate

일반 OCR A/B에서 후보가 선별된 뒤 다음을 확인한다.

1. 실제 datapack ingest가 사용하는 PaddleOCR-VL runtime과 model이 로컬에 완전히
   준비되어 있는지 read-only preflight한다.
2. 준비되어 있으면 TTS/datapack 생성 없이 `PaddleOcrVlAdapter`와
   `build_document_ir_from_vl`까지만 실행한다.
3. 공식 bilinear control과 선별 후보를 8페이지에서 비교한다.
4. Page IR의 node/block 수, 누락, validation summary, parse issues를 기록한다.
5. 같은 production 접근성 경로로 수식 span과 표 셀을 점역하고, 점역 기회 수, 정상
   변환 수, 정책상 보류 수, 미지원 표기 오류 수를 기록한다.
6. p030 회귀 기준과는 schema/translation coverage만 비교한다. 원문이 다르므로 exact
   text/cell 동등성으로 오해할 수 있는 수치를 만들지 않는다.

PaddleOCR-VL weight가 없거나 현재 device에서 실행할 수 없으면 자동 다운로드나 새 GPU
환경 설치를 하지 않는다. 보고서에 `PADDLEOCR_VL_NOT_VERIFIED`로 남기고 사용자 승인을
다시 요청한다.

### WP-8. 결과 보고

예정 파일:

- `UVDOC_OCR_POSTPROCESS_EXPERIMENT_REPORT.md`

보고서는 다음을 분리한다.

- 실행으로 확인한 사실
- OCR metric 기반 해석
- 사람이 overlay에서 확인한 획/halo/본문 잘림
- 일반 OCR proxy 결과와 실제 PaddleOCR-VL 결과
- 미검증 항목
- 권장 default 또는 `NONE`/`INCONCLUSIVE` 판정

## 7. 후보 선별 규칙

아래는 작은 평가 세트에서 다음 단계로 보낼 후보를 고르는 screening rule이며 production
품질 보장이 아니다.

공식 bilinear의 동일 배경 정책과 비교해 후보는 모두 만족해야 한다.

- 8/8 페이지에서 처리 성공
- 전체 비공백 인식 문자 수가 control의 95% 이상
- low-confidence token 비율이 control보다 1 percentage point 넘게 악화되지 않음
- 평균 confidence가 0.01 이상 개선되거나 low-confidence 비율이 2 percentage point
  이상 개선됨
- 어느 한 페이지에서도 인식 문자 수가 control보다 20% 넘게 감소하지 않음
- overlay에서 글자 획 파손, 이중 edge, halo, 표 선 단절이 관찰되지 않음
- paired frame text similarity가 control보다 악화되지 않음

두 후보 모두 이 기준을 통과하지 못하면 `POSTPROCESS_NONE`으로 판정한다. 서로 다른
지표가 상충하거나 변화가 미미하면 `INCONCLUSIVE`로 두고 default를 바꾸지 않는다.

`bbox_original`과 `bbox_neutralized` 입력 정책은 8페이지 중 최소 5페이지에서 같은
방향의 OCR 이득을 보이고 치명적 본문 누락이 없을 때만 우선 후보를 정한다. 아니면
입력 정책을 미정으로 유지한다.

## 8. 테스트 범위

예정 추가/수정 테스트:

- `tests/unit/test_uvdoc_adapter.py`
- `tests/unit/test_image_postprocess.py`
- `tests/unit/test_ocr_ab_experiment.py`

검증 항목:

- UVDoc adapter 기본 sampling mode가 기존 bilinear임
- bilinear/bicubic이 같은 output shape와 uint8 BGR 계약을 지킴
- invalid sampling mode reason 매핑
- unsharp가 입력을 수정하지 않고 dtype/channel/size를 보존함
- 상수 이미지와 threshold 미만 차이를 불필요하게 증폭하지 않음
- artifact ID와 SHA lineage 재현성
- OCR metric 집계와 confidence percentile
- cache signature가 image/engine/config 변경을 구분함
- OCR 한 건 실패 시 나머지 결과와 raw/UVDoc artifact 보존
- fake OCR adapter로 전체 matrix 및 model reuse 검증
- 기존 `book-scanner` unit test 전체 통과

통합 검증:

- 실제 UVDoc checkpoint CPU 추론 8페이지
- 실제 PP-OCRv5 일반 OCR 64회 또는 cache 포함 동등 matrix 완료
- 결과 JSON, overlay, contact sheet 존재 및 해시 확인
- PaddleOCR-VL은 offline runtime이 준비된 경우에만 실행
- `compileall`, `git diff --check`

## 9. 완료 조건

다음을 모두 만족해야 패킷 구현을 완료로 처리한다.

- 네 LabelMe 입력으로 좌우 8페이지가 재현 가능하게 생성됨
- 8개 variant의 이미지 또는 명시적 실패 reason이 모두 존재함
- 실제 PaddleOCR-VL로 선별된 production 검증 이미지의 Page IR이 생성됨
- UVDoc과 OCR model이 매 페이지마다 다시 load되지 않음
- 이미지/OCR metric과 overlay/contact sheet가 생성됨
- bilinear, bicubic, unsharp 결과를 동일 OCR 설정으로 비교함
- 후보 선별 규칙에 따라 `BICUBIC`, `UNSHARP`, `POSTPROCESS_NONE`,
  `INCONCLUSIVE` 중 하나로 판정함
- 기존 테스트와 신규 테스트가 통과함
- 확인한 사실과 CER/일반화/Pi 성능 등 미검증 항목이 분리됨

추가 완료 조건:

- 실제 PaddleOCR-VL → Page IR → 접근성 점역 결과가 생성되어야 최종 downstream 검증을
  완료로 표시한다.
- PaddleOCR-VL weight가 없어 실행하지 못한 경우 전체 패킷은 완료가 아니라
  `BLOCKED_MODEL_ASSETS`로 남긴다.

실제 PaddleOCR-VL runtime/weight가 없으면 `Document Parser production OCR 및 점역
검증`을 완료로 표시하지 않는다. 일반 OCR 보조 배치의 완료 여부와 별개로 전체 패킷은
`BLOCKED_MODEL_ASSETS`로 남긴다.

## 10. 비범위

- 페이지 segmentation 모델 학습/선택
- 추가 자동/수동 라벨 생성
- 기존 polygon 자동 수정 또는 erosion
- session loop 또는 transmit 통합
- OCR model fine-tuning
- CLAHE, adaptive threshold, denoise parameter sweep
- 초해상도/SR 모델
- UVDoc fine-tuning
- CER용 전체 페이지 수작업 transcription
- PaddleOCR 내부 전처리 변경
- TTS와 최종 datapack 생성
- Raspberry Pi 성능/메모리 판정

## 11. 의존성 및 저장 정책

- UVDoc 공식 checkout/checkpoint는 기존 Git 외부 runtime을 재사용한다.
- 일반 OCR은 현재 설치된 `document-parser` 환경과 로컬 model을 재사용한다.
- 새 ML model을 저장소에 추가하지 않는다.
- 대형 이미지/OCR cache는 `experiment_outputs/uvdoc_ocr_ab_20260826/` 아래에 두고 Git에
  추가하지 않는다.
- 보고서, 설정, 재현 명령, 작은 JSON summary만 Git 대상이다.
- 외부 소스/weight의 commit 또는 SHA-256을 기록한다.

## 12. 중단 및 재승인 조건

다음 경우 범위를 임의로 넓히지 않고 중단한다.

- 추가 LabelMe polygon 수정이 필요함
- 공식 UVDoc bilinear 결과가 선행 실험과 재현되지 않음
- PP-OCRv5 model load 또는 offline 실행 실패
- PaddleOCR-VL weight 다운로드나 새 GPU environment가 필요함
- `document-parser` production code 변경이 필요함
- unsharp parameter sweep, CLAHE, SR 또는 다른 dewarper가 필요함
- 후보별 OCR 결과가 크게 상충해 선별 규칙 변경이 필요함
- OCR 결과 비교에 transcription이 필수라고 판단됨

## 13. 예상 변경 파일

신규:

- `src/book_scanner/correct/postprocess.py`
- `src/book_scanner/evaluation/ocr_ab_experiment.py`
- `tools/run_uvdoc_ocr_ab_experiment.py`
- `tests/unit/test_image_postprocess.py`
- `tests/unit/test_ocr_ab_experiment.py`
- 실제 실행 후 `UVDOC_OCR_POSTPROCESS_EXPERIMENT_REPORT.md`

수정:

- `src/book_scanner/correct/uvdoc_adapter.py`
- `tests/unit/test_uvdoc_adapter.py`
- 필요 시 `README.md`

수정 금지:

- `src/book_scanner/session/loop.py`
- `src/book_scanner/transmit/client.py`
- `document-parser` production source
- 기존 원본 이미지와 LabelMe JSON
- 기존 UVDoc bilinear 기본 동작

## 14. 승인 요청

이 패킷 승인 시 다음을 허용하는 것으로 해석한다.

1. 위 adapter 확장, 후보정 모듈, OCR 평가 도구와 테스트를 구현한다.
2. 기존 공식 UVDoc checkpoint로 추가 3장을 포함한 좌우 8페이지를 처리한다.
3. 로컬 PP-OCRv5 model로 최대 64개 variant OCR을 실행하고 결과를 Git 제외 경로에
   저장한다.
4. PaddleOCR-VL은 완전한 offline runtime이 이미 준비된 경우에만 control/선별 후보를
   실행한다.
5. 실제 결과를 검토한 뒤에만 후보정 채택 여부를 판정한다.

승인 전에는 이 문서 외 구현, 추가 UVDoc batch 실행, OCR 실행 또는 model 다운로드를
하지 않는다.
