# 수능특강 수학 I p30 추출·보정·Document Parser 동일 원문 검증 — 작업 패킷

상태: **구현 및 실제 검증 완료 — p30 한정 후보 판정, 인간 golden 미검증**
작성일: 2026-08-30
승인일: 2026-08-30
완료일: 2026-08-30
선행 결과:

- `UVDOC_OCR_POSTPROCESS_EXPERIMENT_REPORT.md`
- `SPINE_SEAM_DETECTION_EXPERIMENT_REPORT.md`
- `PAIRED_OCR_INPUT_EXPERIMENT_REPORT.md`
- `PAIRED_OCR_EXECUTION_RECOVERY_REPORT.md`

## 1. 목적

이번 패킷은 새로 확보한 실제 수능특강 수학 I p30 촬영본을 이용해 다음 세 문제를
순서대로 분리 검증한다.

1. 손수 라벨링한 `left_page` 정답 crop을 기준으로 `none`, coarse perspective,
   UVDoc bilinear 중 어느 입력이 기존 Document Parser의 p30 처리 결과를 가장 잘
   재현하는가?
2. 같은 보정 조건에서 자동 `seam-conservative` crop이 oracle crop 대비 본문·수식·선택지·
   점역 결과를 보존하는가?
3. UVDoc이 실제 OCR/점역 회귀를 보일 때에만 기존 고정 bicubic 또는 luminance unsharp
   후보정이 회귀를 줄이는가?

최종 목표는 영상 선명도 수치 자체가 아니라 다음 실제 운영 경로의 결과다.

```text
p30 왼쪽 페이지 이미지
→ PaddleOCR-VL
→ Page IR
→ flatten_document
→ 수식/표 점역
→ 기존 p030 회귀 기준과 동일 원문 비교
```

페이지 검출과 보정의 영향을 섞지 않기 위해 oracle 보정 비교를 먼저 끝낸 뒤 자동 crop을
비교한다. 이번 작은 반복 촬영 세트만으로 페이지 검출 또는 보정 방식을 production 기본값으로
확정하지 않는다.

## 2. 현재 실행으로 확인된 입력 사실

Google Drive `Ocr_scan/testimages.zip`을 읽기 전용으로 내려받아 검사했다.

- ZIP 크기: 11,306,253 bytes
- ZIP SHA-256:
  `FF1DE586B2ACAE9CF7540EBFDEA9CBC868DEB85E18F189A336FF5F1F0CA9F1DF`
- 압축 내부: JPG 6개, JSON 6개
- 모든 JPG 실제 크기: 4000×3000
- 모든 JSON의 `imageWidth`, `imageHeight`, `imagePath`는 대응 JPG와 일치
- `imageData`는 포함되지 않음

### 이번 패킷의 정량 입력

| capture | left/right polygon | strict loader | 왼쪽 페이지 하단 여백 | 용도 |
|---|---|---|---:|---|
| `20260830_111919` | 14 / 19 points | PASS | 248 px | p30 반복 촬영 A |
| `20260830_112000` | 15 / 24 points | PASS | 280 px | p30 반복 촬영 B |
| `20260830_112042` | 19 / 21 points | PASS | 341 px | p30 반복 촬영 C |

세 입력 모두 다음을 만족한다.

- `left_page`, `right_page`가 하나씩 존재함
- polygon이 이미지 범위 안에 있음
- 자기교차 없음
- 물리 frame edge 비접촉
- 좌우 mask overlap은 전체 frame의 약 0.0046~0.0101%
- p30은 왼쪽 페이지이며 문제 1~4와 페이지 번호 30이 육안상 보존됨

좌우 polygon winding이 서로 반대라는 진단은 있으나 현재 mask rasterization을 막지 않으며
strict loader도 오류로 처리하지 않는다. 이번 실험은 원본 라벨을 수정하거나 winding을
자동 정규화하지 않는다.

### 정량 분모에서 제외할 입력

| capture | 제외 이유 |
|---|---|
| `20260830_104315` | `right_page` 라벨 없음 |
| `20260830_104447` | `right_page` 라벨 없음, `left_page` polygon이 frame 하단 접촉 |
| `20260830_104511` | `right_page` 좌표 하나가 `x=4000`으로 strict 범위 밖 |
| `20260830_112018` | Drive에는 JPG가 있으나 ZIP과 JSON 라벨에는 없음 |

이 입력들은 자동 수정, 좌표 clamp 또는 분모 편입하지 않는다. 필요하면 별도 라벨 수정
승인을 받은 뒤 추가 batch로 처리한다.

## 3. p030 기준의 지위와 해석 제한

`document-parser/tests/fixtures/accessibility/p030.json`은 이번 촬영본 왼쪽 페이지와 같은
인쇄 원문이다. 따라서 선행 실험과 달리 다음 동일 원문 비교가 가능하다.

- 정규화된 OCR 본문 유사도
- 문제 1~4 구조 및 읽기 순서
- 문제 코드, stem, choices 역할 보존
- 수식/선택지 점역 기회와 변환 결과
- 정규화된 점자 cell sequence 유사도

그러나 이 fixture는 사람이 전사해 만든 독립적인 golden transcription이 아니라 기존
Document Parser 파이프라인의 회귀 fixture다. 따라서 다음 주장은 금지한다.

- fixture와 일치하므로 OCR이 절대적으로 정확하다는 주장
- CER/WER을 인간 정답 대비 정확도로 표현
- 세 반복 촬영의 결과를 다른 책·페이지·조명에 일반화
- fixture 자체에 남아 있을 수 있는 OCR 오류를 정답으로 확정

fixture 비교는 **기존 테스트 당시 결과의 재현성**과 variant 간 상대 비교에 사용한다.
추가로 문제 번호 1~4, 문제 코드 4개, 각 문제의 선택지 존재, 페이지 번호 30을 최소 수동
anchor로 검사하되 전체 페이지 수작업 transcription을 이번 범위에 포함하지 않는다.

## 4. 승인 시 고정되는 원칙

- 정량 실험 입력은 strict validation을 통과한 새 촬영본 3장의 왼쪽 페이지만 사용한다.
- 원본 JPG, LabelMe JSON, p030 fixture는 수정하지 않는다.
- oracle 결과를 먼저 실행·판정하기 전 자동 crop 결과를 보정 우승 근거로 사용하지 않는다.
- Document Parser의 실제 `PaddleOcrVlAdapter`와 `build_document_ir_from_vl` 경로를 사용한다.
- 기존 `D:/venvs/gpu_ocr_test`와 로컬 model cache를 재사용하고 설치·교체·자동 다운로드하지
  않는다.
- GPU가 보이지 않으면 암묵적으로 장시간 CPU batch로 전환하지 않는다.
- OCR adapter와 UVDoc model은 batch마다 한 번만 load해 재사용한다.
- 동일 image SHA-256과 engine signature가 일치할 때만 cache를 재사용한다.
- 한 artifact 실패가 나머지 batch를 중단시키지 않되 실패 reason과 입력을 보존한다.
- 영상 지표가 좋아져도 실제 Page IR/점역이 악화되면 후보를 채택하지 않는다.
- session loop, transmit client, TTS, datapack 전송 경로는 변경하거나 실행하지 않는다.
- 실제 GPU OCR을 실행하지 못한 항목은 완료로 표시하지 않는다.

## 5. 실험 행렬과 단계별 gate

### WP-0. 입력 staging 및 provenance

책임:

- ZIP과 12개 내부 파일의 SHA-256 manifest 생성
- JSON/JPG pairing, 크기, 필수 label, 자기교차, frame contact, overlap 재검증
- 승인된 3개 capture만 정량 manifest에 등록
- 원본과 라벨을 Git 추적 대상과 분리된 입력 경로에 복사하되 원본을 덮어쓰지 않음
- 라벨 overlay와 왼쪽 페이지 contact sheet 생성

Gate:

- 세 capture가 모두 strict validation을 통과해야 WP-1로 진행한다.
- 하나라도 이전 검사와 달라졌으면 `BLOCKED_INPUT_CHANGED`로 중단한다.

### WP-1. Oracle crop × geometry

각 capture의 `left_page`에 다음 3개 variant를 생성한다.

| ID suffix | 입력 | 목적 |
|---|---|---|
| `oracle_none_none` | oracle mask bbox crop, warp 없음 | 무보정 control |
| `oracle_coarse_none` | 기존 mask 기반 coarse warp | 큰 원근 정규화 비교 |
| `oracle_uvdoc_bilinear_none` | 공식 UVDoc bilinear | 곡률·원근 보정 비교 |

규모: 3 captures × 3 geometry = **9개 실제 PaddleOCR-VL 입력**.

이 단계는 페이지 검출 오차를 제거한 상태에서 보정 효과만 비교한다. 세 variant의 padding,
배경 정책, OCR 설정은 동일하게 유지한다. UVDoc 전후로 임의의 threshold, denoise, sharpen를
추가하지 않는다.

Gate:

- 9/9 artifact 생성 또는 명시적 실패 record 존재
- 실제 PaddleOCR-VL Page IR 9/9 생성 및 schema validation 기록
- 문제 1~4와 수동 anchor의 보존 여부 기록
- p030 reference 동일 원문 비교와 세 반복 촬영 안정성 비교 완료

일부 variant가 실패하면 해당 geometry를 완료 또는 우승으로 표시하지 않는다.

### WP-2. 자동 seam-conservative crop × geometry

WP-1을 완료한 뒤 동일한 세 capture 왼쪽 페이지에서 자동 `seam-conservative` crop을
생성한다.

| ID suffix | 입력 |
|---|---|
| `seam_conservative_none_none` | 자동 crop, warp 없음 |
| `seam_conservative_coarse_none` | 자동 crop + coarse warp |
| `seam_conservative_uvdoc_bilinear_none` | 자동 crop + UVDoc bilinear |

규모: 3 captures × 3 geometry = **최대 9개 추가 PaddleOCR-VL 입력**.

각 결과는 같은 capture·같은 geometry의 oracle 결과와 직접 비교한다. 이렇게 해야 자동
페이지 추출 손실과 보정 효과가 분리된다.

추가 기록:

- oracle own-page mask recall
- opposite-page inclusion
- 자동 mask/bbox와 oracle mask/bbox 차이
- 본문, 문제 번호, 선택지, footer의 잘림 여부
- seam confidence와 fallback 진단

자동 detector 또는 fallback gate가 한 capture를 reject하면 oracle 결과로 대체해 성공으로
기록하지 않는다. 해당 입력은 명시적 automatic extraction failure다.

### WP-3. 후보정 screening — 조건부

다음 중 하나가 WP-1 또는 WP-2의 UVDoc 결과에서 실제로 관찰될 때만 실행한다.

- 무보정 대비 정규화 본문 유사도 또는 점자 cell 유사도의 명확한 하락
- 문제/선택지/수식 node 누락
- node sequence의 구조적 회귀
- 육안상의 획 손상과 일치하는 OCR 회귀

고정 후보는 이미 구현된 다음 두 개뿐이다.

- UVDoc bicubic sampling
- UVDoc bilinear 후 luminance unsharp (`sigma=1.0`, `amount=0.5`, threshold=3)

parameter sweep, CLAHE, adaptive threshold, denoise, super-resolution은 수행하지 않는다.
회귀가 가장 큰 geometry/extraction 조합을 최대 3 captures에서 두 후보로 비교하므로 신규
PaddleOCR-VL 실행은 **최대 6개**다.

트리거가 없으면 `POSTPROCESS_NOT_TRIGGERED`로 기록한다. 이는 후보정이 일반적으로
불필요하다는 주장이 아니라 이번 p30 표본에서 실행 근거가 없었다는 뜻이다.

### 최대 실행량

| 단계 | 최대 신규 GPU OCR |
|---|---:|
| oracle geometry | 9 |
| seam-conservative geometry | 9 |
| 조건부 후보정 | 6 |
| 합계 | **24** |

## 6. 동일 원문 비교기

기존 비교기는 p030을 다른 원문으로 고정해 cell similarity를 비활성화한다. 이번 패킷에서
동일 원문임을 명시적으로 선택한 경우에만 다음 비교를 활성화한다.

### Page IR/본문

- schema validity와 validation summary
- page/node/focus-item 수
- node type sequence와 node type별 수
- 정규화된 전체 content text 유사도
- 비공백 문자 수와 reference 대비 증감
- parse issue code와 수
- 문제 unit 1~4의 존재와 순서
- problem code/stem/choices 역할 보존
- 문제별 정규화 text 유사도

### 점역

- braille opportunity/translated/withheld/error 수
- 전체 translation rate
- 동일 원문 전체 packed cell sequence similarity
- 가능하면 문제별 packed cell sequence similarity
- 수식 span과 선택지별 누락/오류 목록

점자 cell 비교는 source id가 촬영마다 달라질 수 있으므로 단순 ID 일치만 요구하지 않는다.
문제 순서와 역할로 먼저 정렬한 뒤 비교하고, 정렬 실패 자체를 진단으로 남긴다. 오류가 난
translation을 조용히 빈 cell로 간주하지 않는다.

### 수동 anchor

- page number `30`
- problem number `1`, `2`, `3`, `4`
- problem code `26008-0042`~`26008-0045`
- 각 문제의 choices block 존재
- 문제 순서 1→2→3→4

anchor는 대규모 수동 라벨 데이터가 아니라 catastrophic omission을 탐지하는 소규모 검증
수단이다. 수식의 모든 문자를 사람이 전사했다고 주장하지 않는다.

## 7. 판정 규칙

### 보정 방식 판정

각 geometry는 다음 hard gate를 모두 만족해야 후보가 될 수 있다.

- 세 capture 모두 실제 OCR 완료 및 schema valid
- 세 capture 모두 문제 1~4 순서 보존
- 새 braille translation error가 reference 또는 무보정 control보다 증가하지 않음
- 어느 capture에서도 문제·선택지 block의 치명적 누락이 없음
- overlay에서 본문 잘림 또는 이중 획 등 명백한 손상이 없음

hard gate를 통과한 뒤 다음 순서로 상대 비교한다.

1. 문제별 reference text와 cell similarity
2. 세 반복 촬영 사이의 text/cell/구조 안정성
3. parse issue와 누락 수
4. 문자 수와 영상 품질 보조 지표

하나의 geometry가 3개 중 최소 2개 capture에서 나머지 후보보다 우세하고, 남은 capture에서
hard regression이 없을 때만 `ORACLE_GEOMETRY_CANDIDATE_{NONE|COARSE|UVDOC}`로 기록한다.
지표가 상충하거나 차이가 미미하면 `ORACLE_GEOMETRY_INCONCLUSIVE`로 둔다.

### 자동 crop 판정

같은 geometry의 oracle 대비 자동 crop이 다음을 만족하면
`SEAM_CONSERVATIVE_NO_CLEAR_REGRESSION_P030`으로 기록할 수 있다.

- 세 capture 실제 OCR 완료 및 schema valid
- 문제/선택지 hard omission 0
- own-page mask recall 99% 이상
- opposite-page inclusion 1% 이하
- reference text/cell similarity의 치명적 하락 없음
- oracle 대비 새 braille error 증가 없음

이는 p30 반복 촬영에서의 제한된 판정이며 production 기본값 채택이 아니다. 하나라도 hard
omission이 있으면 `SEAM_CONSERVATIVE_REGRESSION_P030`, 결과가 상충하면
`SEAM_CONSERVATIVE_INCONCLUSIVE_P030`로 둔다.

### 정확도 표현

결과 보고서는 다음 세 층을 분리한다.

1. 실행으로 확인한 pipeline/구조/유사도 사실
2. p030 회귀 fixture에 대한 동일 원문 재현성
3. 사람 golden 부재로 인해 확인하지 못한 절대 OCR·점역 정확도

## 8. 구현 작업

### WP-4. 입력 목록 주입과 기존 runner 호환성

현재 `paired_ocr_inputs.py`의 capture와 fallback 목록은 선행 20260826 실험에 고정돼 있다.
기본값을 유지하면서 다음을 주입 가능하게 만든다.

- labeled capture 목록
- control/fallback 목록을 비워 실행하는 옵션
- 대상 side와 extraction/geometry filter

기존 명령과 manifest ID는 그대로 유지해야 한다. p30 전용 runner가 새 옵션을 명시적으로
전달하고, 기존 20260826 manifest를 재생성했을 때 record 수와 stable ID가 바뀌지 않아야
한다.

### WP-5. p30 실험 runner

예정 파일:

- `tools/run_p030_document_parser_validation.py`

책임:

- `audit|prepare|oracle|automatic|postprocess|report` 단계 지원
- 왼쪽 페이지만 OCR queue에 넣음
- 모델/환경/입력 hash preflight
- batch당 adapter와 UVDoc model 1회 재사용
- 단계별 재개와 exact cache 검증
- 실패 격리 및 summary 생성
- 최대 실행량 gate 준수

### WP-6. 동일 원문 p030 비교기

예정 파일:

- `src/book_scanner/evaluation/p030_reference.py`
- 필요 시 `src/book_scanner/evaluation/document_parser_braille.py`의 명시적 same-content API 확장

책임:

- same-content는 호출자가 명시한 경우에만 활성화
- p030 문제 unit/role/순서 정렬
- 전체 및 문제별 text/cell 비교
- 수동 anchor 진단
- fixture SHA-256과 비교기 version 기록
- 다른 원문에 same-content 옵션을 잘못 적용하지 않도록 source assertion 기록

기존 다른-content 비교 동작은 기본값으로 보존한다.

### WP-7. 결과 검토 산출물

생성 항목:

- 원본+oracle+automatic mask overlay
- geometry별 왼쪽 p30 contact sheet
- 문제별 crop 또는 bbox overlay
- OCR text/structure diff
- 점자 opportunity/error/cell diff
- capture×extraction×geometry 요약 JSON/CSV
- 최종 실험 보고서

예정 보고서:

- `P030_DOCUMENT_PARSER_VALIDATION_REPORT.md`

## 9. 테스트 범위

예정 추가/수정 테스트:

- `tests/unit/test_paired_ocr_inputs.py`
- `tests/unit/test_paired_page_ir.py`
- `tests/unit/test_document_parser_braille_evaluation.py`
- `tests/unit/test_p030_reference.py`

필수 검증:

- 기존 default capture/fallback 목록과 artifact ID 불변
- p30 capture 3개와 left-only queue 선택
- strict-invalid 입력 자동 제외가 아니라 명시적 validation failure 처리
- 같은 source assertion 없이는 cell similarity 비활성
- 동일 원문에서는 전체/문제별 text와 cell 비교
- 문제 순서 또는 role alignment 실패 진단
- anchor 누락 검출
- OCR cache의 image hash/engine signature invalidation
- adapter/UVDoc model 1회 재사용
- 한 artifact 실패 시 나머지 record 보존
- 후보정 trigger와 최대 6개 queue 제한
- fake adapter로 전체 staged 흐름 검증
- 전체 기존 `book-scanner` unit test 통과
- `compileall`, `git diff --check`

실제 통합 검증:

- 3개 원본/JSON strict loader 통과
- oracle 9개 artifact 및 실제 GPU Page IR
- automatic 최대 9개 artifact 및 실제 GPU Page IR
- 조건 충족 시 후보정 최대 6개 실제 GPU Page IR
- 모든 Page IR schema validation 및 접근성 평가 실행
- fixture/모델/checkpoint/입출력 hash lineage 확인

## 10. 완료 조건

다음을 모두 만족해야 전체 패킷을 완료로 표시한다.

- 입력 3개가 변경되지 않았고 strict validation을 통과함
- oracle geometry 9건이 실제 PaddleOCR-VL로 실행됨
- geometry별 p030 동일 원문 text/structure/braille 비교가 생성됨
- automatic extraction 결과가 oracle과 같은 geometry에서 paired 비교됨
- 자동 detector reject와 OCR failure가 성공으로 대체되지 않음
- 조건부 후보정의 실행 또는 `POSTPROCESS_NOT_TRIGGERED` 근거가 기록됨
- 모델/adapter 재사용과 자동 다운로드 없음이 기록됨
- 수동 anchor와 review sheet가 검토됨
- 신규/기존 테스트와 정적 검증 통과
- 결과 보고서가 사실, 해석, 미검증 항목을 분리함
- session/transmit/Document Parser production source가 변경되지 않음

GPU 환경, local model assets 또는 UVDoc checkpoint가 실제로 사용 불가능하면 입력 준비와
코드 테스트는 완료할 수 있지만 전체 패킷은 `BLOCKED_RUNTIME`으로 남긴다. CPU 미완료
시도나 proxy OCR을 실제 production 검증으로 대신하지 않는다.

사람이 만든 전체 transcription이 없으므로 실행이 끝나도 절대 정확도 판정은
`NOT_VERIFIED_NO_HUMAN_GOLDEN`으로 남긴다. 이는 패킷 실행 완료와 별개의 제한이다.

## 11. 비범위

- 페이지 segmentation 모델 학습 또는 fine-tuning
- 데이터 증강·오픈데이터셋 수집
- invalid LabelMe JSON 자동 수정 또는 좌표 clamp
- `112018` 자동 라벨 생성
- 오른쪽 p309 페이지의 OCR 정확도 평가
- OCR/VL model fine-tuning
- Document Parser production parsing/점역 규칙 수정
- 전체 p30 인간 transcription 제작
- 후보정 parameter sweep, CLAHE, denoise, SR
- session loop, transmit, TTS, datapack 생성
- production default 변경
- Raspberry Pi 속도·메모리 판정

## 12. 산출물 및 Git 정책

예정 출력:

```text
book-scanner/experiment_outputs/p030_document_parser_20260830/
  input_manifest.json
  oracle_manifest.json
  automatic_manifest.json
  postprocess_screening.json
  comparisons/
  images/
  masks/
  overlays/
  ocr/
  review/
```

기존 사용자 요청에 따라 최종 보고서와 재현에 필요한 manifest, summary, Page IR record,
review sheet, 실험 입력 variant는 검증 후 branch에 포함한다. PNG/JPG는 기존 Git LFS 규칙을
사용한다. 다음은 포함하지 않는다.

- PaddleOCR-VL/UVDoc model weight와 cache
- Python virtual environment
- 중복된 원본 ZIP/JPG 사본
- 실패 중 생성된 임시 runtime 파일
- 사용자 계정명이나 호스트 종속 절대 경로

원본 Drive 파일은 hash provenance로만 연결한다.

## 13. 중단 및 재승인 조건

다음 경우 범위를 임의로 넓히지 않고 중단한다.

- 세 승인 입력 중 하나라도 strict validation 실패 또는 hash 변경
- 기존 p030 fixture가 실제 촬영 원문과 다르다는 증거 발견
- GPU 환경/package/model cache의 설치·교체·다운로드 필요
- UVDoc checkpoint 다운로드 또는 새 runtime 구축 필요
- Document Parser production source 수정 필요
- 라벨 좌표 수정이나 추가 수동 라벨링이 필수
- 24개 GPU OCR 상한을 넘는 추가 실험 필요
- 후보정 parameter sweep 또는 새 restoration model 필요
- 비교 지표가 상충하여 사전 판정 규칙 변경 필요
- 외부 전송, TTS 또는 datapack 생성이 필요

## 14. 예상 변경 파일

신규:

- `P030_DOCUMENT_PARSER_VALIDATION_WORK_PACKET.md`
- `src/book_scanner/evaluation/p030_reference.py`
- `tools/run_p030_document_parser_validation.py`
- `tests/unit/test_p030_reference.py`
- 실제 실행 후 `P030_DOCUMENT_PARSER_VALIDATION_REPORT.md`

수정 가능:

- `src/book_scanner/evaluation/paired_ocr_inputs.py`
- `src/book_scanner/evaluation/paired_page_ir.py`
- `src/book_scanner/evaluation/document_parser_braille.py`
- 관련 unit test
- 필요 시 `README.md`

수정 금지:

- `src/book_scanner/session/loop.py`
- `src/book_scanner/transmit/client.py`
- `document-parser` production source
- 원본 JPG/JSON과 p030 fixture
- 기존 UVDoc bilinear 기본 동작
- 기존 20260826 실험 산출물

## 15. 승인 요청

이 패킷 승인 시 다음을 허용하는 것으로 해석한다.

1. 기존 paired runner를 기본 동작 불변 조건으로 입력 주입 가능하게 확장한다.
2. p030 동일 원문 비교기, 전용 runner와 unit test를 구현한다.
3. strict-valid 새 촬영본 3장의 왼쪽 페이지에 oracle 9건과 automatic 최대 9건의 실제
   GPU PaddleOCR-VL을 실행한다.
4. 사전 회귀 trigger가 있을 때만 고정 후보정 최대 6건을 추가 실행한다.
5. 기존 local GPU environment, PaddleOCR-VL cache, UVDoc runtime/checkpoint만 재사용한다.
6. 결과 보고서와 재현 산출물을 기존 branch에 추가하되 model/cache와 중복 원본은 제외한다.

승인은 session/transmit/Document Parser production source 변경, 모델 다운로드·설치,
라벨 자동 수정, production 기본값 채택을 허용하지 않는다.
