# 페이지 추출 × 보정 × 후보정 Paired OCR 실험 — 작업 패킷

상태: **승인됨 — 구현 완료, 실제 paired OCR은 device 제약으로 차단**
작성일: 2026-08-30
선행 문서:

- `CODEX_IMPLEMENTATION_CONTEXT.md`
- `PAGE_SEPARATION_EXTRACTION_EXPERIMENT_REPORT.md`
- `SPINE_SEAM_DETECTION_EXPERIMENT_REPORT.md`
- `UVDOC_ORACLE_EXPERIMENT_REPORT.md`
- `UVDOC_OCR_POSTPROCESS_EXPERIMENT_REPORT.md`

## 1. 목적

같은 원본 페이지에서 추출 방식, 기하 보정, 화질 후보정을 하나씩 바꿔 실제
Document Parser의 PaddleOCR-VL → Page IR 결과가 어떻게 달라지는지 paired 방식으로
비교한다.

검증할 질문은 세 가지다.

1. 현재 `luminance-valley` spine seam crop이 기존 overlapping crop보다 OCR 입력으로
   유리하거나 최소한 치명적 회귀가 없는가?
2. 원본 crop, coarse perspective warp, UVDoc 중 어느 입력이 OCR 구조·문자 보존에
   상대적으로 유리한가?
3. warp 뒤의 고정된 보수적 후보정이 실제 OCR 회귀를 줄이는가?

Laplacian variance나 육안 선명도만으로 입력을 선택하지 않는다. 반대로 원본 crop도
곡률·원근·배경 유입이 남아 있으므로 자동으로 우수하다고 간주하지 않는다.

## 2. 우선순위와 인과 분리

실험 순서는 다음과 같이 고정한다.

```text
fallback 판정
→ 추출 방식 paired 비교
→ 기하 보정 paired 비교
→ 회귀가 관찰된 후보에 한해 후보정 screening
→ 실제 PaddleOCR-VL / Page IR / 접근성 경로 비교
```

추출 오류와 warp 효과를 한 번에 바꾸면 원인을 구분할 수 없다. 따라서 먼저 보정 없는
crop끼리 비교하고, 그 다음 선택된 동일 crop에서 기하 보정만 바꾼다. 후보정은 기하
보정 비교가 끝난 뒤에만 적용한다.

## 3. 입력 표본과 역할

### 정량 paired 표본

현재 LabelMe 정답이 있는 4 spread, 좌우 8면만 주 정량 비교에 사용한다.

| capture | 역할 |
|---|---|
| `20260826_174943` | 반복 촬영 A |
| `20260826_174953` | 같은 spread 반복 촬영 B |
| `20260826_174958` | 표·회색 문제 영역 및 선행 UVDoc OCR 회귀 사례 |
| `20260826_175109` | 다른 spread, seam/UVDoc 육안 비교 |

`174943`과 `174953`은 콘텐츠 독립 표본 두 개로 세지 않고 반복 촬영 안정성 pair로
다룬다.

### 비라벨·fallback 표본

- `175110`: offline fallback 진단을 통과한 비라벨 control. oracle 비교에는 사용하지
  않고 자동 crop 실행 건전성만 확인한다.
- `175116`, `175119`, `175120`, `175126`, `175130`: 오배치·부분 이탈·그림자 등
  fallback stress 표본. OCR을 실행하지 않고 명시적 skip reason을 확인한다.
- `175153`, `175200`: 빈 받침대. `PAGE_NOT_FOUND`로 OCR 대상에서 제외한다.

fallback 진단을 통과하지 못한 이미지를 OCR 성공률 분모에 넣거나 정상 실패로 세지
않는다. OCR runner가 이를 조용히 처리하면 안 되며 `SKIPPED_FALLBACK_<reason>`을
기록해야 한다.

## 4. 알려진 한계와 판정 원칙

### OCR 정답 부재

현재 촬영 페이지 전체의 검증된 transcription이나 동일 원문의 정답 점역은 없다.
따라서 다음을 주장하지 않는다.

- CER/WER 개선
- 점자 cell accuracy
- 원본/warp/UVDoc 중 절대 OCR 정확도 우승
- p030과 동일한 원문 품질

oracle crop OCR도 정답이 아니라 **같은 source에 대한 추출 영향 비교 anchor**다.
oracle과 높은 text similarity는 자동 crop이 유사한 OCR 결과를 냈다는 뜻이지 둘 다
정확하다는 뜻이 아니다.

### 혼합 점역 coverage

선행 실험의 다수 점역 오류는 쉼표, 괄호, 숫자, 라틴 문자 등을 포함한 표 셀의 혼합
점역 미지원에서 발생했다. 이는 영상 후보의 주 선별 지표로 사용하지 않는다.

- Page IR schema와 OCR 구조·텍스트 비교: 주 지표
- braille opportunity/error: downstream 진단
- 혼합 점역 `NotImplementedError`: 영상 회귀와 별도 집계

혼합 점역 기능을 이번 패킷에서 구현하거나 수정하지 않는다.

## 5. 실험 축과 단계별 행렬

조합 폭증과 GPU 낭비를 막기 위해 모든 축의 완전요인 192회 실행은 금지한다. 단계별로
후보를 좁힌다.

### Phase A. 추출 방식 비교 — 기하 보정 없음

라벨 8면에 다음 네 입력을 생성한다.

| ID | 추출 방식 | 설명 |
|---|---|---|
| `oracle_original` | LabelMe polygon bbox | 추출 영향 비교 anchor |
| `overlap_original` | 기존 6% overlapping mask crop | 본문 보존 우선 baseline |
| `seam_confirmed_original` | luminance seam union-preserving mask | 확정 좌우 ownership |
| `seam_conservative_original` | seam uncertainty band를 양쪽 crop에 보존 | 본문 보존 후보 |

공통 조건:

- 원본 해상도와 원본 색상을 유지한다.
- mask 밖 neutralization은 적용하지 않는다.
- 동일 padding fraction을 사용한다.
- resize, warp, sharpening을 적용하지 않는다.
- fallback assessment와 source/mask/crop SHA-256을 기록한다.

최대 신규 PaddleOCR-VL 실행은 8면 × 4종 = 32건이다. 기존 hash와 engine signature가
일치하는 oracle cache는 재사용한다.

### Phase B. 기하 보정 비교

Phase A 결과와 무관하게 원인 분리를 위해 다음 두 extraction anchor를 유지한다.

1. `oracle`
2. `seam_conservative`

각 anchor에서 다음 세 geometry variant를 비교한다.

| ID suffix | 처리 | 목적 |
|---|---|---|
| `none` | 원본 crop | 무보정 control |
| `coarse` | image-derived coarse page homography | 단순 원근 보정 후보 |
| `uvdoc_bilinear` | 공식 UVDoc bilinear | 곡률 보정 후보 |

제약:

- LabelMe mask로 만든 coarse anchor는 `oracle_coarse`로 명시하고 자동 결과로 세지 않는다.
- seam crop의 coarse anchor는 seam/segmenter mask에서 생성한다.
- B 방식의 spread 전체 homography는 V자 양면을 한 평면으로 가정하므로 이번 주 비교에서
  제외하고, 선행 결과만 참고한다.
- warp 횟수, 보간법, source/destination quad, matrix, 출력 크기를 기록한다.
- 한 variant 안에서 resize/warp를 중복 수행하지 않는다.
- 기존 UVDoc runtime과 checkpoint를 재사용하고 새 weight를 받지 않는다.

원본 control은 Phase A cache와 중복 실행하지 않는다. 최대 신규 실행은 coarse/UVDoc
2종 × 2 anchor × 8면 = 32건이다.

### Phase C. 후보정 screening

후보정은 Phase B에서 원본 대비 명백한 OCR 구조·문자 회귀가 나온 geometry variant에
한해서만 실행한다.

초기 screening 페이지:

- `174958 right`: 선행 UVDoc 회귀가 확인된 표·회색 문제 영역
- `175109 left` 또는 Phase B에서 가장 큰 paired 차이를 보인 일반 텍스트 페이지 1면

고정 후보:

| ID suffix | 후보정 |
|---|---|
| `none` | 무처리 control |
| `luminance_unsharp_fixed` | 기존 고정 Lab L-channel unsharp |
| `uvdoc_bicubic` | UVDoc에 한해 같은 grid의 bicubic sampling |

CLAHE, adaptive threshold, denoise, deblur, super-resolution, parameter sweep은 이번
패킷에서 제외한다. screening에서 고정 후보가 명시적 진입 기준을 통과한 경우에만
라벨 8면 전체 실행을 허용한다.

## 6. 입력 생성과 provenance

모든 artifact ID는 다음 형식을 사용한다.

```text
{capture}_{side}_{extraction}_{geometry}_{postprocess}
```

각 artifact에 다음을 연결한다.

- 원본 이미지 경로와 SHA-256
- LabelMe JSON SHA-256 또는 `automatic_seam` provenance
- fallback assessment와 통과 여부
- segmenter/seam/uncertainty/padding config
- crop bbox와 full-frame 좌표 round-trip
- mask SHA-256
- UVDoc checkpoint SHA-256
- coarse matrix 또는 UVDoc config
- 후보정 config
- 최종 OCR 입력 이미지 SHA-256
- OCR engine signature와 cache hit 여부

같은 이미지 hash와 engine signature가 아니면 이전 OCR cache를 재사용하지 않는다.

## 7. 실제 실행 경로

최종 비교는 프로젝트 루트의 기존 production 접근성 경로를 사용한다.

```text
paired image artifact
→ PaddleOcrVlAdapter
→ build_document_ir_from_vl
→ Page IR schema validation
→ flatten_document
→ math_focus_item_to_braille / table_cell_braille
```

다음은 실행하지 않는다.

- TTS 합성
- datapack 쓰기
- session loop
- transmit client
- 실제 외부 전송

PaddleOCR-VL model은 batch당 한 번만 load해 재사용한다. 기존 local cache가 불완전하면
자동 다운로드하지 않고 `BLOCKED_MODEL_ASSETS`로 중단한다.

## 8. 비교 지표

### 8.1 추출·영상 지표

- fallback pass/reason
- page/content-proxy recall과 opposite-page inclusion
- crop bbox, 해상도, aspect ratio
- crop 안 mask coverage와 배경 비율
- warp 횟수와 interpolation
- normalized Laplacian/Tenengrad 보조값

영상 지표는 OCR 결과를 대신하지 않는다. 서로 다른 출력 스케일의 raw Laplacian
variance를 직접 우열 지표로 사용하지 않는다.

### 8.2 Page IR/OCR 지표

- schema validation
- node type별 수와 순서
- TABLE/TEXT/FORMULA block 수
- 정규화 text와 비공백 문자 수
- 같은 source variant 사이 normalized text similarity
- oracle anchor 대비 block 추가/누락/타입 변경
- parse issue와 빈 페이지 여부
- 처리시간과 cache hit

### 8.3 반복 촬영 지표

`174943`과 `174953`에서 extraction/geometry가 같은 variant끼리 비교한다.

- 정규화 text similarity
- node type sequence similarity
- 표/수식 block 수 차이
- 한 pair가 동일하게 틀릴 가능성을 명시

반복 안정성 개선을 정확도 개선으로 표현하지 않는다.

### 8.4 제한된 수동 golden 진단

전체 페이지 전사 대신 `174958 right`의 선행 회귀 영역을 golden diagnostic ROI로
사용한다.

- ㄱ/ㄴ/ㄷ/ㄹ 항목 보존
- 선택지 번호와 조합 보존
- TABLE ↔ TEXT 구조 변화
- `정답`, `해설` 등 핵심 표기

기존 보고서의 육안 관찰을 자동 정답으로 복사하지 않는다. 정확도 판정을 하려면 해당
ROI의 사람이 확인한 transcription manifest가 필요하다. manifest가 없으면 결과는
`MANUAL_GOLDEN_NOT_VERIFIED`로 남기고 구조 회귀 관찰만 기록한다.

### 8.5 점역 지표

- braille opportunity 수
- 정상 변환·정책상 보류·미지원 표기 오류 수
- 수식/표 node가 사라져 opportunity가 감소했는지

혼합 문자열 오류가 많다는 이유만으로 영상 후보를 탈락시키지 않는다. 영상 후보 사이
동일한 Page IR node가 사라지거나 변형된 경우만 OCR 회귀 근거로 사용한다.

## 9. 단계별 판정 규칙

### Phase A — 추출 방식

seam 후보는 다음을 모두 만족해야 `SEAM_OCR_CANDIDATE`다.

- fallback 통과 라벨 8면에서 Page IR schema 8/8 유효
- `EMPTY_PAGE` 또는 치명적 parse failure 없음
- oracle anchor 대비 페이지별 비공백 문자 수가 20% 넘게 감소하지 않음
- 기존 overlap보다 반대 페이지 유입 감소
- 반복 촬영 text/node 안정성이 overlap보다 명백히 악화되지 않음
- golden ROI에서 명백한 항목·표 구조 추가 누락이 관찰되지 않음

정답 transcription이 없으므로 oracle보다 높은 similarity만으로 seam을 “더 정확함”으로
판정하지 않는다. 기준이 상충하면 `EXTRACTION_INCONCLUSIVE`, 명백한 누락이 있으면
`OVERLAP_FALLBACK`으로 둔다.

### Phase B — 기하 보정

geometry 후보의 가능한 판정:

- `NO_CLEAR_REGRESSION`: paired 결과에서 치명적 회귀가 없음
- `OCR_REGRESSION`: 핵심 구조/문자 누락이 반복적으로 증가
- `INCONCLUSIVE_NO_GROUND_TRUTH`: 지표가 상충하거나 정확도 판정 불가

검증 transcription 없이 `OCR_IMPROVED` 판정을 금지한다. 원본, coarse, UVDoc 중
production default를 이번 작은 표본만으로 변경하지 않는다.

### Phase C — 후보정

후보정은 같은 geometry의 `none` control과 비교해 다음을 모두 만족해야 전체 8면으로
확대한다.

- screening 2면 모두 schema valid
- 회귀 golden ROI의 명백한 구조·핵심 문자 중 하나 이상 복구
- 다른 면에서 새로운 block 누락이나 20% 초과 문자 감소 없음
- halo, 이중 획, 표 선 단절이 원본 해상도에서 관찰되지 않음

통과하지 못하면 `POSTPROCESS_NONE`이 아니라 **`NO_POSTPROCESS_EVIDENCE`**로 기록한다.
이는 후보정 일반을 배제한다는 뜻이 아니다.

## 10. 구현 범위

### WP-1. Paired artifact manifest

- fallback gate를 입력 생성 앞에 적용
- four extraction variant 생성
- stable artifact ID와 lineage JSON
- 기존 oracle/UVDoc artifact hash가 같으면 재사용
- 실패·skip도 artifact manifest에 포함

### WP-2. Paired image generator

- overlap/seam confirmed/seam conservative crop 생성
- oracle/automatic mask 구분
- coarse/UVDoc geometry variant 생성
- 원본과 warp 이미지 모두 보존
- interpolation 및 후보정 metadata 기록

### WP-3. Document Parser batch adapter

- 기존 `PaddleOcrVlAdapter`와 cache 계약 재사용
- model batch 1회 load
- variant 한 건 실패 시 나머지 계속 실행
- cache key에 image hash/engine/device/config 포함
- 자동 model download 차단

### WP-4. Paired comparator

- Page IR flatten text 정규화
- node sequence/type/count 비교
- capture/side별 variant matrix
- 반복 촬영 pair 비교
- golden ROI 수동 검토용 crop/overlay/contact sheet
- 점역 coverage를 OCR 회귀와 분리

### WP-5. Staged runner

- `--phase extraction|geometry|postprocess`
- 이전 phase manifest 입력
- screening rule을 통과하지 않은 후보의 전체 batch 실행 차단
- `--force-full-postprocess` 같은 우회 옵션은 이번 범위에서 만들지 않음

### WP-6. 결과 보고서

예정 파일: `PAIRED_OCR_INPUT_EXPERIMENT_REPORT.md`

보고서에서 다음을 분리한다.

1. 실제 OCR 실행 사실
2. 같은 source paired 차이
3. 사람이 확인한 golden ROI 관찰
4. downstream 혼합 점역 coverage
5. 정확도·일반화·Pi 성능 미검증 사항

## 11. 테스트 범위

### Unit tests

- fallback 거부 입력은 OCR queue에 들어가지 않음
- 라벨 8면 × extraction variant artifact ID 안정성
- seam confirmed/conservative mask와 crop lineage
- full-frame 좌표 round-trip
- coarse/UVDoc/no-warp variant가 정확히 한 축만 바꿈
- 중복 interpolation 방지
- image/config/engine 변화에 따른 cache invalidation
- 한 OCR 실패가 다른 variant를 중단하지 않음
- fake PaddleOCR-VL adapter model 1회 재사용
- Page IR node/text paired comparator
- 반복 촬영 pair 집계
- screening 미통과 후보의 Phase C 확대 차단
- 비ASCII Windows 경로
- 기존 seam/UVDoc/OCR/braille 회귀 테스트

### 실제 검증

- 라벨 4장 × 좌우 8면 Phase A
- oracle/seam-conservative Phase B
- `174958 right` 포함 Phase C screening
- fallback stress 5장과 빈 받침대 2장의 OCR skip
- `175110` automatic-only control
- Page IR/JSON/overlay/contact sheet/hash 존재
- `pytest`, `compileall`, `git diff --check`

## 12. 완료 조건

다음을 모두 만족한 항목만 완료로 처리한다.

- fallback gate가 stress/empty 입력을 OCR 전에 제외하고 reason을 기록함
- Phase A의 8면 × 4 extraction artifact 또는 명시적 실패가 존재함
- Phase B의 oracle/seam-conservative geometry paired artifact가 존재함
- 실제 PaddleOCR-VL Page IR이 생성되고 schema validation이 기록됨
- model이 variant마다 다시 load되지 않음
- extraction/geometry/postprocess 축이 manifest에서 분리됨
- Page IR 구조·텍스트·반복 촬영·점역 진단이 생성됨
- screening 확대/중단 결정이 사전 규칙에 따라 기록됨
- 실제 측정과 정답 부재에 따른 미검증 사항이 분리됨
- 기존 session/transmit/Document Parser production source가 변경되지 않음
- 전체 테스트와 정적 검증이 통과함

특정 crop, warp 또는 후보정의 승자가 나오는 것은 완료 조건이 아니다. 결과가 상충하면
`INCONCLUSIVE_NO_GROUND_TRUTH`로 완료할 수 있다. PaddleOCR-VL assets 또는 GPU 실행이
불가능하면 production paired 검증을 완료로 표시하지 않고 `BLOCKED_MODEL_ASSETS`로 둔다.

## 13. 명시적 비범위

- session loop, stability/quality judge, transmit client 통합
- Document Parser production source 수정
- 혼합 점역 지원 구현
- 전체 페이지 수작업 transcription
- OCR/UVDoc model fine-tuning
- 새 ML model 또는 checkpoint 다운로드
- CLAHE/deblur/denoise/SR 및 후보정 parameter sweep
- B 방식 spread 전체 homography 재평가
- p030을 새 촬영본의 동일 원문 정답으로 사용
- TTS/datapack/외부 전송
- Raspberry Pi 성능 판정
- stress 이미지의 OCR 강제 실행

## 14. 의존성과 저장 정책

- 기존 `tmp/uvdoc-runtime`과 checkpoint를 재사용한다.
- 기존 `document-parser/data/debug/model_home_vl` cache를 read-only preflight한다.
- 새 model download를 시도하지 않는다.
- 대형 이미지/Page IR/cache는 `experiment_outputs/paired_ocr_*` 또는 workspace `tmp`에
  두고 Git에 추가하지 않는다.
- 코드, 테스트, manifest schema, summary와 보고서만 검토 대상으로 둔다.
- 기존 사용자 변경과 원본 이미지/LabelMe JSON을 보존한다.

## 15. 예상 변경 파일

신규 후보:

- `src/book_scanner/evaluation/paired_ocr_inputs.py`
- `src/book_scanner/evaluation/paired_page_ir.py`
- `tools/run_paired_ocr_input_experiment.py`
- `tests/unit/test_paired_ocr_inputs.py`
- `tests/unit/test_paired_page_ir.py`
- `PAIRED_OCR_INPUT_EXPERIMENT_REPORT.md`

최소 수정 후보:

- `src/book_scanner/evaluation/document_parser_braille.py`
- `README.md`
- `.gitignore`의 대형 paired 출력 제외 규칙

재사용하며 기본 동작을 변경하지 않는 파일:

- `src/book_scanner/correct/coarse_perspective.py`
- `src/book_scanner/correct/uvdoc_adapter.py`
- `src/book_scanner/correct/postprocess.py`
- `src/book_scanner/detect/spine_seam.py`
- `src/book_scanner/evaluation/fallback_assessment.py`

수정 금지:

- `src/book_scanner/session/loop.py`
- `src/book_scanner/transmit/client.py`
- 기존 원본 이미지와 LabelMe JSON
- `document-parser` production source
- UVDoc checkpoint와 model cache

## 16. 중단 및 재승인 조건

다음 상황에서는 범위를 임의로 넓히지 않고 결과를 보고한다.

- PaddleOCR-VL cache가 없거나 현재 GPU/device에서 실행할 수 없음
- UVDoc runtime/checkpoint가 선행 hash와 일치하지 않음
- Document Parser production source 변경이 필요함
- golden ROI transcription 없이는 후보 선택이 불가능하고 사용자의 확인이 필요함
- CLAHE, deblur, SR 또는 외부 복원 모델이 필요함
- 신규 model/weight 다운로드가 필요함
- 전체 페이지 transcription 또는 외부 OCR 정답 데이터가 필요함
- fallback stress 이미지를 OCR에 강제 투입해야 함
- 실험 조합이나 screening 규칙을 결과를 본 뒤 변경해야 함

## 17. 승인 요청

이 패킷 승인 시 다음을 허용하는 것으로 해석한다.

1. 위 범위의 paired artifact/OCR 비교 코드와 테스트를 추가한다.
2. fallback을 통과한 라벨 4장의 좌우 8면과 `175110` control을 사용한다.
3. 기존 local UVDoc/PaddleOCR-VL runtime과 유효 cache를 재사용한다.
4. Phase A 최대 32건, Phase B 최대 신규 32건의 PaddleOCR-VL 실행을 수행한다.
5. Phase C는 고정 screening 2면만 먼저 실행하고 사전 기준 통과 시에만 확대한다.
6. Git 제외 경로에 이미지, Page IR, overlay, contact sheet, cache를 생성한다.
7. 결과가 불충분하면 특정 입력을 채택하지 않고 `INCONCLUSIVE`로 보고한다.
