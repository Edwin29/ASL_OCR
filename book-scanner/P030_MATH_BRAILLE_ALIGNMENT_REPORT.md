# p30 golden 공통 수식 셀·후보 추가 수식 셀 분리 평가 보고서

작성일: 2026-08-30  
상태: **`COMPLETE_EXISTING_PAGE_IR_REEVALUATION`**  
OCR 재실행: **없음**  
기준: 사람이 검증한 `document-parser/tests/fixtures/accessibility/p030.json`

## 1. 결론

실제 후보인 `seam-conservative + UVDoc bilinear`는 세 촬영에서 p30 golden의 공통 수식
span **93/93개**, 공통 점자 셀 **624/624개**를 정확히 보존했다.

- golden 공통 수식 누락: 0 span, 0 cell
- golden 공통 셀 유사도: 1.0000
- 후보 추가 수식: 22 span, 98 cell
- 추가 수식 중 golden 일반 텍스트에 존재하는 표현: 22/22 span, 98/98 cell
- 점역 오류: 0

따라서 기존 전체 셀열 평균 유사도 0.9298은 golden 점자 셀의 오역·누락을 의미하지 않는다.
두 촬영에서 문제 4 본문 수식이 일반 텍스트에서 수식 span으로 승격되면서 각각 49셀이
추가된 것을 전체 셀열 비교기가 차이로 계산한 결과다.

## 2. 평가 방법

각 Page IR을 기존 production 접근성 경로로 flatten한 뒤 수식 span과 점자 셀을 추출했다.

정렬 키:

- `presentation_ast`의 canonical JSON
- 페이지 읽기 순서와 span 등장 순서
- AST가 없을 때만 정규화 수식 텍스트 fallback

`2^x`와 `2^{x}`처럼 표기는 다르지만 AST가 같은 수식은 공통 span으로 정렬한다. 정렬 후
결과를 다음 세 종류로 분리했다.

1. golden과 후보에 모두 있는 공통 수식 span과 셀
2. golden에는 있으나 후보에서 누락되거나 다른 AST로 인식된 span
3. 후보에만 수식으로 존재하는 추가 span

후보 추가 span의 정규화 수식 문자열이 golden Page IR의 일반 텍스트에 존재하는지도 별도로
기록했다. 이는 원문에 없는 무작위 수식 추가와, 기존 일반 텍스트를 수식으로 승격한 경우를
구분하기 위한 진단이다.

## 3. 자동 crop + UVDoc 결과

| capture | golden 공통 span | 공통 셀 | 공통 셀 일치 | golden 누락 | 후보 추가 |
|---|---:|---:|---:|---:|---:|
| `111919` | 31/31 | 208/208 | 1.0000 | 0 span / 0 cell | 0 span / 0 cell |
| `112000` | 31/31 | 208/208 | 1.0000 | 0 span / 0 cell | 11 span / 49 cell |
| `112042` | 31/31 | 208/208 | 1.0000 | 0 span / 0 cell | 11 span / 49 cell |
| 합계 | **93/93** | **624/624** | **1.0000** | **0 / 0** | **22 / 98** |

`112000`과 `112042`의 추가 span은 서로 동일하다.

| 추가 수식 | 셀 수 |
|---|---:|
| `y=m` | 4 |
| `f(x)=2^{x-3}+2` | 18 |
| `m` | 1 |
| `k` | 1 |
| `y=f(x)` | 7 |
| `x` | 1 |
| `k` | 1 |
| `y` | 1 |
| `-2k` | 4 |
| `y=g(x)` | 7 |
| `g(k)` | 4 |
| 촬영 1장당 합계 | **49** |

이 표현들은 모두 golden의 문제 4 본문 일반 텍스트에 존재한다. golden Page IR에서는 해당
본문이 하나의 `TEXT` span으로 저장돼 점역 대상이 아니었고, 두 후보 Page IR에서는 11개
수식 AST가 `VALID`로 생성돼 점역 대상이 됐다.

이는 후보가 원문에 없는 49셀을 무작위로 삽입했다는 증거가 아니다. 저장된 golden 점자
sequence보다 수식 접근성 범위를 넓힌 결과다. 다만 추가 span은 golden의 기존 math-span
집합 밖이므로, 이 49셀을 golden 공통 셀 정확도 분모에 섞지 않고 별도 promotion으로 남긴다.

## 4. 전체 방식 비교

세 촬영을 합친 값이다. 공통 셀 유사도는 정렬된 공통 AST의 셀만 비교한다.

| extraction | geometry | 공통 span / golden | 공통 셀 | 공통 셀 유사도 | golden 누락 span/cell | 후보 추가 span/cell |
|---|---|---:|---:|---:|---:|---:|
| oracle | none | 88/93 | 614 | 1.0000 | 5 / 10 | 33 / 147 |
| oracle | coarse | 91/93 | 618 | 1.0000 | 2 / 6 | 33 / 147 |
| oracle | UVDoc | 89/93 | 595 | 1.0000 | 4 / 29 | 34 / 170 |
| seam-conservative | none | 83/93 | 552 | 1.0000 | 10 / 72 | 35 / 191 |
| seam-conservative | coarse | 92/93 | 619 | 1.0000 | 1 / 5 | 33 / 147 |
| seam-conservative | UVDoc | **93/93** | **624** | **1.0000** | **0 / 0** | **22 / 98** |

공통으로 정렬된 AST는 같은 production translator를 통과하므로 모든 방식에서 셀 자체는
일치했다. 방식 간 차이는 주로 수식 AST를 누락하거나 추가·변형했는지에서 나타났다.

`seam-conservative + UVDoc`은 유일하게 golden 수식 span을 하나도 잃지 않았다. 또한 추가
22개 span 전부가 golden 일반 텍스트에 존재하는 문제 4 수식 승격이었다.

## 5. Oracle UVDoc의 차이

Oracle UVDoc은 세 촬영 합계 공통 span 89/93, golden 누락 4 span/29 cell이었다.

- `111919`: 문제 2 수식의 지수를 `x` 대신 `2`로 인식
  - golden `f(x)=(-a^2+6a-4)^x` 22셀 누락 취급
  - 후보 `f(x)=(-a^{2}+6a-4)^{2}` 23셀 추가 취급
- `112042`: 선택지 값 `1`, `6`, `36` 세 span, 합계 7셀 누락
- 문제 4의 일반 텍스트 수식 승격: 세 촬영 모두 11 span/49 cell

따라서 정답 polygon crop이라는 사실이 곧 OCR에 가장 좋은 crop이라는 뜻은 아니다. 이번
p30에서는 자동 conservative crop + UVDoc이 Oracle UVDoc보다 수식 구조 보존이 안정적이었다.

## 6. 기존 전체 셀 유사도와의 관계

기존 비교기는 번역된 모든 셀을 한 배열로 이어 `SequenceMatcher`를 적용했다.

- `111919`: 208 대 208셀, 전체 유사도 1.0000
- `112000`: 208 대 257셀, 전체 유사도 0.8946
- `112042`: 208 대 257셀, 전체 유사도 0.8946
- 평균: 0.9298

새 분리 평가에서는 세 촬영 모두 golden 공통 208셀을 정확히 보존했다. 두 촬영의 0.8946은
49개 추가 셀을 벌점으로 계산한 값이며 golden 공통 셀 오류율이 아니다.

향후 보고에서는 다음을 함께 제시한다.

- golden 공통 span coverage
- golden 공통 셀 similarity
- golden-only 누락 span/cell
- candidate-added span/cell
- candidate-added span의 golden 일반 텍스트 존재 여부

## 7. 검증 범위와 제한

확인한 것:

- 저장된 18개 Page IR 전체를 같은 정렬 규칙으로 재평가함
- 자동 UVDoc의 golden 공통 수식 셀 624/624 정확 일치
- 자동 UVDoc의 golden 수식 누락 0
- 추가 98셀의 원문 표현이 golden 일반 텍스트에 존재함
- OCR 재실행이나 model 변경 없음

제한:

- p30에만 적용되는 평가다.
- 일반 텍스트 자체의 점역은 현재 production 접근성 경로의 대상이 아니다.
- 후보 추가 span은 source-backed promotion으로 분류했지만 기존 golden math-span 집합에는 없다.
- TTS, 점자 하드웨어 전송과 실제 사용자 읽기 평가는 수행하지 않았다.
- 다른 페이지의 수식 generalization은 검증하지 않았다.

## 8. 산출물

- `experiment_outputs/p030_document_parser_20260830/math_braille_alignment_summary.json`
- 각 `ocr/oracle/*.json`, `ocr/automatic/*.json`의
  `p030_reference_comparison.math_braille_alignment`
- `oracle_ocr_summary.json`, `automatic_ocr_summary.json`
- `final_summary.json`의 `math_braille_alignment_summary`

