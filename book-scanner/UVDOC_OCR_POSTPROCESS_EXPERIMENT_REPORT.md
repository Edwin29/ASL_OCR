# UVDoc → Document Parser → 점역 실험 보고서

상태: **실제 production 경로 검증 완료 / downstream acceptance 불통과**
판정: **POSTPROCESS_NONE, 추가 데이터 없이 화질 후보정 채택 금지**
실행일: 2026-08-30

## 결론

손수 라벨링한 4개 spread의 좌우 8페이지를 공식 UVDoc bilinear로 보정한 뒤,
프로젝트의 실제 운영 경로인 PaddleOCR-VL → Page IR → `flatten_document` → 수식/표
점역에 입력했다.

- UVDoc 출력 8/8은 Page IR schema validation을 통과했다.
- 기존 p030 회귀 기준은 점역 대상 31/31 성공, 오류 0으로 재현됐다.
- 새 촬영본의 UVDoc 출력은 점역 대상 70개 중 28개 성공, 42개 오류였다.
- 원본 oracle bbox crop도 점역 대상 99개 중 39개 성공, 60개 오류였다.
- 두 입력 모두 성공률이 40% 안팎이므로 p030과 유사한 점역 품질이라고 판단할 수 없다.
- 오류의 직접 원인은 대부분 UVDoc 화질이 아니라 기존 표 셀 점역기가 혼합 문자열의
  구두점, 숫자, 라틴 문자를 지원하지 않는 점이다.
- 다만 `20260826_174958` 오른쪽의 회색 예제 영역에서는 UVDoc 보정 후 PaddleOCR-VL의
  구조·문자 인식이 원본 crop보다 실제로 악화됐다.
- bicubic과 약한 luminance unsharp는 이 회귀를 복구하지 못했다. 따라서 어느 후보정도
  production 기본값으로 채택하지 않는다.

동일 원문의 정답 점역이 없으므로 exact cell similarity나 CER은 계산하지 않았다.

## 실행 경로

실제 사용한 경로:

```text
LabelMe 좌/우 polygon
  → oracle bbox crop
  → UVDoc official checkpoint
  → PaddleOCR-VL 1.6 / PaddleOCR 3.7.0 (gpu:0)
  → build_document_ir_from_vl
  → flatten_document
  → math_focus_item_to_braille / table_cell_braille
```

TTS 합성, datapack 쓰기, session loop, transmit client는 변경하거나 실행하지 않았다.

## 모델과 실행 환경

다운로드한 모델은 Git 외부 로컬 캐시에만 저장했다.

| 모델 | 파일 크기 | SHA-256 |
|---|---:|---|
| PaddleOCR-VL-1.6 `model.safetensors` | 1,917,255,968 bytes | `85A479D506A11E724E7285D395C551BE69F41DBC16B6342D3CACFB189AED71DB` |
| PP-DocLayoutV3 `inference.pdiparams` | 130,806,572 bytes | `70BD316B0582769EC968829FD1FEB1A6A58B7C941B938327E551B6B12B45C137` |

- 캐시: `document-parser/data/debug/model_home_vl/.paddlex/official_models/`
- PaddleOCR: 3.7.0
- PaddlePaddle GPU: 3.2.1
- device: `gpu:0`
- UVDoc checkpoint: 기존 `tmp/uvdoc-runtime/model/best_model.pkl`
- UVDoc model load: batch별 1회

Paddle이 설치 cuDNN 9.9와 시스템 cuDNN 9.5 차이를 경고했지만, 16개 production OCR
호출과 후보 screening 2개 호출은 예외나 중단 없이 완료됐다. 장기 안정성까지 검증한
것은 아니다.

## p030 기준선

`document-parser/tests/fixtures/accessibility/p030.json`을 현재 코드로 다시 실행했다.

| 항목 | 결과 |
|---|---:|
| schema valid | true |
| focus items | 18 |
| 점역 기회 | 31 |
| 정상 변환 | 31 |
| 정책상 보류 | 0 |
| 미지원 표기 오류 | 0 |
| 변환률 | 100% |

p030은 새 촬영본과 원문 및 콘텐츠 유형이 다르다. 이 값은 점역 코드의 회귀 기준이지
새 촬영본의 정답 문자열이 아니다.

## 8페이지 production 결과

### 전체 집계

| 입력 | schema valid | 보존 문자 수 | 점역 기회 | 정상 변환 | 오류 | 점역 대상 없는 페이지 |
|---|---:|---:|---:|---:|---:|---:|
| 원본 oracle bbox crop | 8/8 | 6,355 | 99 | 39 | 60 | 4 |
| UVDoc bilinear original | 8/8 | 6,461 | 70 | 28 | 42 | 4 |

일반 텍스트는 현재 제품 정책상 점자판을 비우므로, 수식 span이나 표 셀이 없는 4페이지는
실패가 아니라 `NOT_APPLICABLE_NO_BRAILLE_CONTENT`로 기록했다.

### 페이지별 비교

| 페이지 | 원본 node / 문자 / 점역(오류) | UVDoc node / 문자 / 점역(오류) | 정규화 text similarity |
|---|---|---|---:|
| 174943 left | TABLE 2, TEXT 4 / 1,044 / 15(10) | TABLE 2, TEXT 4 / 1,039 / 16(11) | 0.9832 |
| 174943 right | TEXT 40 / 573 / 0(0) | TEXT 41 / 570 / 0(0) | 0.9274 |
| 174953 left | TABLE 2, TEXT 4 / 1,039 / 15(10) | TABLE 2, TEXT 4 / 1,039 / 16(11) | 0.9779 |
| 174953 right | TEXT 31 / 496 / 0(0) | TEXT 31 / 587 / 0(0) | 0.8975 |
| 174958 left | TABLE 2, TEXT 6 / 789 / 22(12) | TABLE 2, TEXT 6 / 789 / 22(12) | 0.9861 |
| 174958 right | TABLE 4, TEXT 8 / 624 / 47(28) | TABLE 1, TEXT 15 / 626 / 16(8) | **0.5904** |
| 175109 left | TEXT 13 / 428 / 0(0) | TEXT 12 / 431 / 0(0) | 0.9406 |
| 175109 right | TEXT 8 / 1,362 / 0(0) | TEXT 9 / 1,380 / 0(0) | 0.8724 |

문자 수가 비슷하다고 내용이 정확하다는 뜻은 아니다. 특히 174958 right는 거의 같은
문자 수를 내면서 구조와 핵심 문자를 다르게 인식했다.

## 반복 촬영 안정성

174943과 174953은 같은 spread의 반복 촬영이다.

| side | 원본 crop similarity | UVDoc bilinear similarity |
|---|---:|---:|
| left | 0.9909 | 0.9962 |
| right | 0.9149 | 0.9559 |

UVDoc은 반복 촬영 결과의 안정성을 높였다. 그러나 두 결과가 동일하게 틀릴 수 있으므로
정확도 개선으로 해석하지 않는다.

## 점역 오류의 직접 원인

점역 오류는 모두 표 셀에서 발생했다. 기존 `table_cell_braille`은 한글-only 문자열이나
숫자-only 값은 처리하지만, 다음과 같은 혼합 문자열에서 의도적으로
`NotImplementedError`를 발생시킨다.

- `민원처리, 각종 행정통계 ...`의 쉼표
- `• 경영정보 시스템(MIS: Management Information System) ...`의 bullet, 괄호,
  라틴 문자, 콜론
- `[1단계] 정보의 기획`의 대괄호와 숫자
- `5W 2H`, `e-mail`, `/` 같은 혼합 표기

같은 오류가 원본 crop과 UVDoc 양쪽에서 반복되므로 후보정으로 해결할 문제가 아니다.
현재 p030의 100% 변환률은 수학 예제 fixture에 대한 결과이며, 일반 한국어 prose table의
점역 coverage를 대표하지 않는다.

## 174958 right 회귀 사례

육안상 UVDoc은 페이지 기울기와 원근을 크게 개선하고 반대편 페이지 유입을 제거했다.
하지만 회색 문제 박스의 OCR은 원본 crop보다 악화됐다.

원본 crop은 다음 구조를 6×3 table로 보존했다.

- `ㄱ. 내가 가진 소장품도 ...`
- `ㄴ. 인터넷 쇼핑, 홈뱅킹 ...`
- `ㄷ. 공공기관이나 정부는 ...`
- `ㄹ. 팩스나 전자우편 ...`
- `① ㄱ, ㄴ`, `② ㄱ, ㄷ`, `③ ㄴ, ㄷ`, `④ ㄴ, ㄹ`
- `정답 ①`, `해설 ...`

UVDoc bilinear에서는 이 영역이 TEXT로 바뀌고 다음 오인식이 발생했다.

- ㄱ/ㄴ/ㄷ/ㄹ → `7/L/C/2`
- 선택지 → `① 7, ② 7, ③ 7, ④ 7, ⑤ 7`

원본 crop에도 `Electronic Commerce`를 `Electronic Commerz Store`로 읽는 오류 등이
있어 정답이라고 볼 수는 없다. 다만 이 특정 핵심 구조는 원본 쪽이 명백히 더 가깝다.

## Bicubic / unsharp screening

174958 right 한 페이지에서 공식 bilinear와 두 후보를 같은 PaddleOCR-VL 설정으로
비교했다.

| 후보 | node | 문자 | 점역 기회(오류) | bilinear text similarity | 관찰 |
|---|---|---:|---:|---:|---|
| bilinear | TABLE 1, TEXT 15 | 626 | 16(8) | 1.0000 | ㄱ/ㄴ/ㄷ/ㄹ과 선택지 오인식 |
| bicubic | TABLE 1, TEXT 15 | 628 | 16(8) | 0.9841 | 선택지 배치는 일부 회복, `해설→혈설` 및 문자 오인식 지속 |
| unsharp | TABLE 1, TEXT 15 | 626 | 16(8) | 0.9968 | 구조 개선 없음, `해설→혈설` |

어느 후보도 원본 crop의 문제 구조를 회복하지 못했다. 작은 한 페이지 screening에서
명백한 이득이 없으므로 전체 8페이지 PaddleOCR-VL 확대 실행은 하지 않았다.

## 판정

### UVDoc

`CONDITIONAL`을 유지한다.

- 기울기·원근·반대편 페이지 유입 및 반복 촬영 안정성은 개선된다.
- 일부 회색 박스/작은 문자에서 구조·문자 OCR 회귀가 있다.
- 따라서 UVDoc 결과만 고정적으로 사용하는 production 정책은 아직 승인할 수 없다.

### 후보정

`POSTPROCESS_NONE`.

- bicubic: 채택 근거 부족
- luminance unsharp: 채택 근거 없음
- bilinear 기본값은 호환성을 위해 유지하되 production acceptance를 의미하지 않음

### 최종 점역

`DOWNSTREAM_NOT_ACCEPTED`.

- 실행 자체와 schema 유효성은 검증됐다.
- p030과 유사한 점역 성공률은 재현되지 않았다.
- 주 차단점은 prose table의 혼합 문자 점역 coverage다.
- 같은 원문 정답이 없어 OCR 정확도/CER는 미검증이다.

## 다음 작업 권고

1. 이미지 후보정보다 먼저 표 셀 혼합 문자열 점역 coverage를 별도 작업 패킷으로 다룬다.
   쉼표, 마침표, 괄호, 대괄호, bullet, 숫자, 라틴 문자, 콜론, slash를 2024 규정 근거와
   함께 추가해야 한다.
2. 전체 페이지 전사 대신 8~10개 핵심 영역만 검증용으로 수작업 전사한다. 특히
   `174958 right`의 표와 회색 문제 박스는 UVDoc 회귀 검출용 golden ROI로 적합하다.
3. 페이지별로 원본 crop과 UVDoc을 모두 PaddleOCR-VL에 넣고 구조·누락 진단으로 선택하는
   fallback을 검토한다. 단, production latency가 약 2배가 되므로 별도 패킷에서 판단한다.
4. 좌우 페이지 검출과 페이지 보정 문제는 계속 분리한다. 본 결과는 oracle polygon을
   사용했으므로 자동 검출 품질을 증명하지 않는다.

## 생성물과 검증

- production 결과:
  `experiment_outputs/uvdoc_document_parser_20260826/`
- 후보 screening:
  `experiment_outputs/uvdoc_document_parser_screen_174958_right/`
- p030 평가:
  `experiment_outputs/uvdoc_document_parser_20260826/reference_p030_braille_evaluation.json`
- 모델 캐시:
  `document-parser/data/debug/model_home_vl/`

자동 테스트:

- book-scanner unit: 75 passed
- document-parser Page IR/braille regression: 92 passed
- `compileall`: passed
- `git diff --check`: passed (기존 LF→CRLF 안내만 존재)

## 미검증 사항

- 동일 원문 점역 정답과 exact cell accuracy
- 전체 페이지 OCR transcription과 CER/WER
- 8페이지 밖 일반화 성능
- 자동 좌우 페이지 검출 이후의 end-to-end 품질
- TTS, datapack 쓰기, 실제 점자 하드웨어 전송
- Raspberry Pi latency/memory
- bicubic/unsharp의 전체 8페이지 production OCR 결과
