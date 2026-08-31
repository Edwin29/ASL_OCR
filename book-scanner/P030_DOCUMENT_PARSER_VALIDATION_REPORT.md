# 수능특강 수학 I p30 추출·보정·Document Parser 동일 원문 검증 보고서

작성일: 2026-08-30
실행 상태: **`EXECUTION_COMPLETE_HUMAN_VERIFIED_GOLDEN`**
보정 판정: **`ORACLE_AND_AUTOMATIC_GEOMETRY_CANDIDATE_UVDOC_BILINEAR`**
자동 crop 판정: **`SEAM_CONSERVATIVE_NO_CLEAR_REGRESSION_P030`**
후보정 판정: **`POSTPROCESS_NOT_TRIGGERED`**

후속 아키텍처 결정(2026-08-30): **영상 Scanner 기본 경로로
`seam-conservative + UVDoc bilinear` 채택**. 실험 당시의 제한된 verdict는 그대로 보존하며,
영상 runtime 통합과 Pi 4 성능은 별도 검증 대상으로 남긴다.

## 1. 결론

새로 확보한 실제 수능특강 수학 I p30 반복 촬영 3장을 기존 GPU Document Parser의
PaddleOCR-VL → Page IR → 접근성 점역 경로로 처리했다.

- oracle crop 3장 × `none|coarse|uvdoc_bilinear`: **9/9 COMPLETE**
- seam-conservative crop 3장 × `none|coarse|uvdoc_bilinear`: **9/9 COMPLETE**
- 전체 18/18 Page IR schema-valid
- 전체 18/18 점역 오류 0
- 모델 다운로드 없음
- OCR adapter는 batch별 1개 instance를 재사용
- UVDoc은 준비 batch에서 1회 load

문제 1→4의 순서와 각 선택지 block을 모두 보존한 hard gate 결과는 다음과 같다.

| geometry | oracle | automatic | 합계 |
|---|---:|---:|---:|
| none | 2/3 | 1/3 | 3/6 |
| coarse | 1/3 | 2/3 | 3/6 |
| UVDoc bilinear | **3/3** | **3/3** | **6/6** |

따라서 이 p30 반복 촬영 세트에서는 UVDoc bilinear가 유일하게 oracle과 automatic 양쪽에서
모든 구조 gate를 통과했다. `seam-conservative + UVDoc bilinear`는 자동 crop 중 다음 단계의
선두 후보로 둘 수 있다.

이 판정은 p30의 3회 반복 촬영에만 적용된다. 다른 책, 다른 페이지, 그림·표가 많은 페이지,
그림자·부분 잘림 fallback까지 포함한 production 기본값 채택은 아니다.

## 2. 입력과 provenance

검증 입력:

- `20260830_111919`
- `20260830_112000`
- `20260830_112042`

공통 조건:

- 4000×3000 JPEG
- 왼쪽 페이지: 수능특강 수학 I p30
- 오른쪽 페이지: p309
- LabelMe `left_page`, `right_page` polygon strict validation 통과
- 자기교차 및 physical frame contact 없음
- 전체 frame 기준 좌우 label overlap 약 0.0046~0.0101%

입력 ZIP:

- 크기: 11,306,253 bytes
- SHA-256:
  `FF1DE586B2ACAE9CF7540EBFDEA9CBC868DEB85E18F189A336FF5F1F0CA9F1DF`

p030 reference:

- `document-parser/tests/fixtures/accessibility/p030.json`
- SHA-256:
  `79f2bb54ff9e793999a4ec6a7de4f177fbbff41e1eaa9ce6e04644348c23d792`
- Document Parser 개발 과정에서 사람이 직접 검증한 p30 golden
- 기존 평가: braille opportunity 31, translated 31, error 0

UVDoc checkpoint SHA-256:

`7e90861b8a516eb4bc51f84bd889cb77275743d2d1d3ca8091951ec9f2b7da23`

## 3. 입력 gate에서 발견한 사항

기존 fixed-layout fallback은 spread 양쪽이 모두 통과해야 한다. 새 세 이미지에서는 목표인
왼쪽 p30이 모두 통과했으나 오른쪽 p309의 grid luminance range가 59~72로 기존 임시 기준
35를 넘어 `UNEVEN_ILLUMINATION`이었다.

이번 패킷은 왼쪽 페이지만 평가하므로 오프라인 runner에 `selected_sides` gate를 추가했다.

- 왼쪽 side gate: 3/3 통과
- 전체 spread gate: 0/3 통과
- production session gate: 변경하지 않음
- 오른쪽 실패 진단: manifest에 보존
- oracle crop: automatic gate와 독립적으로 보존

이는 오른쪽 실패를 성공으로 바꾼 것이 아니다. 이번 정량 OCR queue의 목표 side를 왼쪽으로
제한한 것이다. 실제 양면 production 처리에서는 오른쪽 조명 정책을 별도로 해결해야 한다.

## 4. 동일 원문 golden의 지위와 한계

이번 촬영본은 p030 fixture와 같은 인쇄 원문이므로 이전 실험에서 불가능했던 다음 비교를
수행했다.

- 전체 정규화 OCR text similarity
- 문제 1~4 structure와 순서
- choice block 수
- 실제 점역 기회/오류
- packed braille cell sequence similarity

p030 fixture는 Document Parser 개발 과정에서 사람이 직접 검증한 동일 원문 golden이다.
따라서 아래 text/cell similarity와 구조 gate는 p30 golden 대비 결과로 해석할 수 있다.

다만 이번 비교기는 정규화 SequenceMatcher 유사도와 packed cell sequence similarity를
사용했으며 CER/WER이나 별도의 cell error rate를 계산하지 않았다. 따라서 보고되지 않은
정확도 지표를 계산한 것처럼 표현하지 않으며, p30 golden의 지위를 다른 페이지나 책으로
일반화하지 않는다.

## 5. 전체 geometry 집계

oracle과 automatic을 합친 6개 결과의 평균이다.

| geometry | hard gate | 평균 reference text similarity | 평균 cell similarity | 점역 오류 |
|---|---:|---:|---:|---:|
| none | 3/6 | 0.8993 | 0.8694 | 0 |
| coarse | 3/6 | 0.9558 | 0.8851 | 0 |
| UVDoc bilinear | **6/6** | **0.9624** | **0.9083** | 0 |

coarse의 평균 text similarity는 높았지만 두 oracle과 한 automatic에서 문제 unit 하나가
구조화되지 않았다. 전체 text가 많이 남아 있어도 문제 단위 읽기 순서가 실패할 수 있으므로
문자 수 또는 전체 similarity만으로 채택하지 않았다.

## 6. Oracle 결과

| capture | geometry | hard gate | text similarity | cell similarity | 문제 순서 | 점역 오류 |
|---|---|---:|---:|---:|---|---:|
| 111919 | none | 실패 | 0.9494 | 0.8220 | 2,3,4 | 0 |
| 111919 | coarse | 통과 | 0.9659 | 0.8946 | 1,2,3,4 | 0 |
| 111919 | UVDoc | 통과 | 0.9589 | 0.8884 | 1,2,3,4 | 0 |
| 112000 | none | 통과 | 0.9576 | 0.8946 | 1,2,3,4 | 0 |
| 112000 | coarse | 실패 | 0.9572 | 0.8946 | 1,3,4 | 0 |
| 112000 | UVDoc | 통과 | 0.9680 | 0.8946 | 1,2,3,4 | 0 |
| 112042 | none | 통과 | 0.9344 | 0.8946 | 1,2,3,4 | 0 |
| 112042 | coarse | 실패 | 0.9389 | 0.8497 | 1,3,4 | 0 |
| 112042 | UVDoc | 통과 | 0.9475 | 0.8777 | 1,2,3,4 | 0 |

oracle에서 UVDoc만 세 촬영 모두 문제 구조를 보존했다. 이 단계는 페이지 검출 오류가 없는
상태이므로 p30에 대한 보정 방식의 선두 후보 근거다.

## 7. Automatic seam-conservative 결과

| capture | geometry | hard gate | text similarity | cell similarity | 문제 순서 | 점역 오류 |
|---|---|---:|---:|---:|---|---:|
| 111919 | none | 통과 | 0.6972 | 0.8326 | 1,2,3,4 | 0 |
| 111919 | coarse | 통과 | 0.9651 | 0.8946 | 1,2,3,4 | 0 |
| 111919 | UVDoc | 통과 | **0.9837** | **1.0000** | 1,2,3,4 | 0 |
| 112000 | none | 실패 | 0.9446 | 0.8946 | 1,2,4 | 0 |
| 112000 | coarse | 실패 | 0.9544 | 0.8946 | 1,2,4 | 0 |
| 112000 | UVDoc | 통과 | 0.9624 | 0.8946 | 1,2,3,4 | 0 |
| 112042 | none | 실패 | 0.9127 | 0.8783 | 미상,2,3,4 | 0 |
| 112042 | coarse | 통과 | 0.9531 | 0.8826 | 1,2,3,4 | 0 |
| 112042 | UVDoc | 통과 | 0.9540 | 0.8946 | 1,2,3,4 | 0 |

자동 crop의 label 지표:

- own-page recall: 세 장 모두 1.0
- opposite-page inclusion: 세 장 모두 0.0
- 페이지 1~4와 footer의 육안상 잘림: 없음

자동 bbox는 oracle보다 바깥 여백을 조금 더 포함했다. 예를 들어 `111919`는 oracle
1778×2741, automatic 1869×2751이었다. 이 차이는 무보정 OCR에서 크게 나타났지만 UVDoc
뒤에는 문제 구조가 세 장 모두 복구됐다.

따라서 `seam-conservative` 단독을 안정적이라고 판정하지 않는다. 이번 positive 판정은
**`seam-conservative + UVDoc bilinear` 조합**에 한정한다.

## 8. Automatic과 oracle의 직접 비교

UVDoc 동일 geometry에서 automatic 대 oracle은 다음과 같다.

| capture | OCR text similarity | cell similarity | reference text delta | reference cell delta |
|---|---:|---:|---:|---:|
| 111919 | 0.9735 | 0.8884 | +0.0248 | +0.1116 |
| 112000 | 0.9918 | 1.0000 | -0.0056 | 0.0000 |
| 112042 | 0.9828 | 0.9862 | +0.0065 | +0.0169 |

`111919`은 automatic UVDoc이 reference cell sequence와 1.0000으로 일치했지만, oracle과
automatic 사이의 opportunity 수가 42 대 31로 달라 두 결과의 직접 cell similarity는
0.8884였다. cell similarity 하나만 보지 않고 문제 구조, 기회 수, 오류 수를 함께 봐야 한다.

### 8.1 Golden 공통 수식 셀과 후보 추가 셀 분리 평가

후속 AST 정렬 평가에서 `seam-conservative + UVDoc` 세 결과는 golden 공통 수식 span
93/93개와 공통 점자 셀 624/624개를 정확히 보존했다. golden-only 누락은 0 span/0 cell이다.

`112000`과 `112042`에는 각각 문제 4의 수식 11개가 추가 점역되어 49셀이 늘었다. 추가된
22개 span/98셀은 모두 golden 문제 4의 일반 텍스트에 실제 표현이 존재한다. 즉 기존 전체
셀 유사도 0.8946은 golden 셀 오역이 아니라 source-backed 수식 promotion을 차이로 계산한
값이다.

상세 근거는 `P030_MATH_BRAILLE_ALIGNMENT_REPORT.md`와
`math_braille_alignment_summary.json`에 분리해 기록했다.

## 9. 선명도와 후보정 판단

1600px long-edge proxy 영상 지표 평균:

| geometry | Laplacian variance | Tenengrad mean |
|---|---:|---:|
| none | 421.3 | 5513.4 |
| coarse | 299.1 | 4925.0 |
| UVDoc bilinear | 297.5 | 4852.3 |

UVDoc 결과가 무보정보다 부드럽다는 관찰은 재현됐다. contact sheet에서도 가는 획의 대비가
약간 낮아진다. 그러나 이번 p30에서 그 부드러움은 실제 OCR 구조 또는 점역 회귀로 이어지지
않았다.

- UVDoc hard gate: 6/6
- UVDoc 평균 text/cell similarity: 세 geometry 중 최고
- 신규 점역 오류: 0
- 본문, 선택지, footer의 육안상 잘림: 없음
- 이중 edge 또는 심한 sharpening halo: 관찰되지 않음

사전 trigger가 없으므로 bicubic/unsharp GPU OCR은 실행하지 않았다. 판정은
`POSTPROCESS_NOT_TRIGGERED`이며, 후보정이 일반적으로 불필요하다는 뜻은 아니다. 향후 다른
페이지에서 UVDoc OCR 회귀가 실제로 나타날 때 같은 고정 후보를 다시 screening한다.

## 10. 육안 검토

`none`:

- 원본 원근과 책등 곡률이 남음
- 검은 배경과 spine 쪽 여백이 남지만 p30 본문은 보존
- 촬영/crop 차이에 따라 구조 검출이 흔들림

`coarse`:

- 페이지 외형이 직사각형에 가까워짐
- 재표본화로 부드러워짐
- 본문은 육안상 남지만 문제 단위 검출이 3/6에서 누락됨

`UVDoc bilinear`:

- 페이지가 가장 평평하고 읽기 방향이 일관됨
- 가는 획이 원본보다 부드러움
- 6/6에서 문제 1~4와 선택지를 구조화
- oracle/automatic 모두 page number 30과 footer 보존

검토 sheet:

- `review/none_oracle_vs_seam_conservative.jpg`
- `review/coarse_oracle_vs_seam_conservative.jpg`
- `review/uvdoc_bilinear_oracle_vs_seam_conservative.jpg`

## 11. 구현 변경

추가:

- `src/book_scanner/evaluation/p030_reference.py`
- `tools/run_p030_document_parser_validation.py`
- `tests/unit/test_p030_reference.py`
- p30 work packet/report

확장:

- paired extraction manifest에 capture/side/extraction/control/fallback 주입
- oracle과 automatic gate 분리
- selected-side 오프라인 gate
- geometry manifest side/extraction filter
- 명시적 p030 same-source text/cell comparator
- 사전 UVDoc 후보정 trigger
- oracle/automatic 직접 paired summary와 review sheet

보존:

- 기존 20260826 default capture와 fallback 목록
- 기존 artifact ID 규칙
- session loop
- transmit client
- Document Parser production source
- 기존 UVDoc bilinear 기본 동작

## 12. 검증

- 선택 단위 테스트: 21 passed
- 전체 `book-scanner/tests`: 119 passed
- 실제 GPU OCR: 18/18 complete
- schema-valid: 18/18
- 점역 오류: 0/18
- `compileall`: 통과
- model download: 없음

cuDNN 9.9 빌드와 시스템 9.5 차이 경고는 이전 GPU 실험과 동일하게 발생했다. 이번 18건은
실제 완료됐지만 환경 호환 경고 자체가 해결됐다고 주장하지 않는다.

## 13. 남은 한계와 다음 판단

확인한 것:

- p30 반복 촬영 3장에서 oracle/automatic UVDoc이 실제 Document Parser 구조를 보존함
- 자동 crop이 oracle label mask 본문을 보존하고 반대 페이지를 포함하지 않음
- 영상 부드러움이 이번 OCR 결과의 실패를 의미하지 않음
- 사람이 검증한 p30 golden 대비 UVDoc이 세 geometry 중 가장 높은 평균 text/cell similarity를 보임

확인하지 못한 것:

- 별도 CER/WER 및 cell error rate 계산
- 다른 페이지와 다른 책으로의 일반화
- 오른쪽 p309의 uneven illumination fallback 처리
- 그림자·frame 잘림·빈 배경에서의 자동 복구
- Raspberry Pi 성능

다음 우선순위는 `seam-conservative + UVDoc`을 production에 즉시 넣는 것이 아니라, 서로
다른 내용의 라벨 페이지로 같은 6/6 구조 보존 경향이 반복되는지 검증하는 것이다. 동시에
양면 전체 처리를 위해 오른쪽 illumination gate가 실제 본문 품질 실패인지, 단순한 과민
reject인지 별도 패킷에서 조사해야 한다.

## 14. 산출물

`experiment_outputs/p030_document_parser_20260830/`

- `input_manifest.json`
- `extraction_manifest.json`
- `geometry_manifest.json`
- `oracle_ocr_summary.json`
- `automatic_ocr_summary.json`
- `postprocess_screening.json`
- `final_summary.json`
- `images/`, `masks/`, `ocr/`, `review/`

상세 결과의 절대 경로는 실행 환경 정보이며, 재현 판단에는 image/reference/model hash와
artifact ID를 사용한다.
