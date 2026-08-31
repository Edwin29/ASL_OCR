# Held-out 좌우 crop + UVDoc 반복·내용 일반화 검증 — 작업 패킷

상태: **보류 — 기본 경로 채택 후 회귀 검증 패킷으로 재분류, 미구현·미실행**  
작성일: 2026-08-30  
기준 커밋: `4dd0a2f4bf2ea50345c3fba3606da819f2e4e294`  
선행 판정:

- p30 한정 geometry 후보: `ORACLE_AND_AUTOMATIC_GEOMETRY_CANDIDATE_UVDOC_BILINEAR`
- p30 한정 자동 crop 판정: `SEAM_CONSERVATIVE_NO_CLEAR_REGRESSION_P030`
- p30 기준: `HUMAN_VERIFIED_GOLDEN`
- 영상 Scanner 기본 경로: **`seam-conservative + UVDoc bilinear` 채택**
- production 일반화와 Pi 4 성능: **미검증**

## 1. 이번 패킷의 우선순위

현재 가장 큰 증거 공백은 `seam-conservative + UVDoc bilinear`가 **다른 내용과 반복
촬영에서도** 안정적인가이다.

기존 자료만으로 이 질문에 답할 수는 없다.

- 20260826 라벨 4장은 seam 후보 선택과 paired OCR 평가에 이미 사용했다.
- 이 가운데 `174943`과 `174953`은 동일한 p300~301 spread의 반복 촬영이다.
- 나머지는 p302~303, p150~151로 총 3개 고유 spread이며 모두 같은 계열의 책이다.
- 20260830 p30 라벨 3장은 같은 p30/p309 spread의 반복 촬영이다.
- p30 reference는 Document Parser 개발 과정에서 사람이 직접 검증한 p30 golden이다.

따라서 기존 결과를 다시 섞어 held-out 일반화 성능으로 표현하지 않는다. 이번 패킷은
**새로운 라벨 반복쌍**을 주 정량 분모로 사용한다.

별도 보조 트랙에서는 p30 촬영본의 오른쪽 p309가 `UNEVEN_ILLUMINATION`으로 모두 거부된
문제를 조사한다. 이 결과는 주 held-out 분모와 합치지 않으며 production threshold를 같은
패킷에서 수정하지 않는다.

## 2. 검증할 가설

### H1. 자동 페이지 소유권·crop 보존

고정 구도의 정상 촬영에서 `seam-conservative`가 좌우 페이지의 인쇄 영역을 보존하면서
반대 페이지 유입을 1% 이하로 제한한다.

### H2. UVDoc 보정의 내용 독립성

수식, 표·색상 블록, 장문 본문, 혼합 레이아웃에서도 UVDoc bilinear가 문제·제목·표·선택지·
footer 같은 주요 구조를 치명적으로 누락시키지 않는다.

### H3. 반복 촬영 안정성

같은 spread를 두 번 촬영했을 때 자동 crop + UVDoc의 OCR text, Page IR 구조와 점역 결과가
사전 기준 안에서 반복된다.

### H4. 오른쪽 조명 gate의 의미

p309의 `UNEVEN_ILLUMINATION` 거부가 실제 Document Parser 회귀와 함께 나타나는지, 아니면
현재 임시 영상 threshold의 과민 거부 가능성이 있는지 구분한다.

이번 실험은 H1~H4에 대한 제한된 증거를 수집한다. 작은 표본으로 production 일반화가
완료됐다고 주장하지 않는다.

## 3. 신규 입력 요구사항

### 3.1 주 정량 세트: 신규 라벨 이미지 8장

권장 구성은 **서로 다른 spread 4개 × 각 2회 반복 촬영**이다.

| 그룹 | 권장 내용 | 촬영 | 필요한 라벨 |
|---|---|---:|---|
| G1 | 수식·선택지가 많은 페이지 | 같은 spread 2회 | `left_page`, `right_page` |
| G2 | 표·색상 블록이 많은 페이지 | 같은 spread 2회 | `left_page`, `right_page` |
| G3 | 장문·다단 본문 페이지 | 같은 spread 2회 | `left_page`, `right_page` |
| G4 | 그림·도형 또는 혼합 레이아웃 | 같은 spread 2회 | `left_page`, `right_page` |

표본 구성 원칙:

- 가능하면 물리적으로 다른 책을 최소 2권 포함한다.
- 한 그룹의 두 촬영은 페이지를 넘기지 않고 같은 원문을 촬영한다.
- 카메라와 고정 구도는 실제 사용 조건을 유지한다.
- 두 촬영은 완전히 같은 파일 복사가 아니라 실제 재촬영이어야 한다.
- 정상 처리 능력을 평가하는 주 세트이므로 심한 잘림·큰 그림자·의도적 오배치는 넣지 않는다.
- 페이지 위치와 조명의 자연스러운 작은 차이는 허용한다.
- 원본 JPEG 해상도와 EXIF 방향을 보존한다.
- LabelMe polygon은 페이지 모서리 네 점이 아니라 실제 곡선 외곽을 따라 작성할 수 있다.
- JSON의 `imageData`는 불필요하며, 대응 JPG와 크기·파일명이 일치해야 한다.

사용자가 손수 작성해야 하는 것은 좌우 페이지 polygon까지다. 전체 OCR transcription이나
점자 정답 작성은 요구하지 않는다.

### 3.2 구조 anchor

각 페이지에 다음 최소 anchor manifest를 실험 준비 과정에서 작성한다.

- 보이는 페이지 번호
- 큰 제목 또는 단원명 1개 이상
- 순서가 있는 문제 번호 또는 주요 block 식별자
- 표·그림·선택지 block의 존재 여부
- footer가 OCR 대상인지 여부

anchor는 원본을 육안으로 확인해 작성하고 review sheet와 함께 보존한다. 이는 전체 문장
transcription이 아니며 CER/WER이나 절대 OCR 정확도의 근거로 사용하지 않는다.

### 3.3 입력 acceptance gate

신규 8장은 다음을 모두 만족해야 주 정량 queue에 들어간다.

- 대응 JPG/JSON 존재 및 SHA-256 manifest 생성
- `left_page`, `right_page`가 정확히 하나씩 존재
- 좌표가 image bounds 안에 있음
- polygon 자기교차 없음
- 물리 frame 외곽에 의도하지 않은 접촉 없음
- 동일 그룹 두 장의 페이지 번호·원문이 동일함
- 동일 그룹 두 JPG의 SHA-256이 서로 다름
- fixed-layout 정상 입력 gate 통과

좌표 clamp, polygon 자동 수리, 누락 라벨 자동 생성은 하지 않는다. 실패 입력은
`BLOCKED_INPUT_VALIDATION`으로 남기고 정량 분모를 조용히 줄이지 않는다.

## 4. 데이터 분리 정책

| 세트 | 용도 | threshold/파라미터 조정 허용 |
|---|---|---:|
| 기존 20260826 라벨 | 과거 개발·회귀 control | 아니요, 현재 값 고정 |
| 기존 p30/p309 3장 | p30 회귀와 조명 진단 | 아니요 |
| 신규 8장 | 이번 held-out 확인 세트 | **아니요** |
| 기존 비라벨 stress/empty | accept/reject 진단 | 아니요 |

신규 결과를 본 뒤 seam cost, center band, padding, fixed-layout threshold, UVDoc sampling 또는
OCR 설정을 바꾸어 같은 세트에서 다시 성공 판정하지 않는다. 변경이 필요하면 이번 결과는
실패/예외로 보존하고 별도 개발 세트와 새 held-out 세트를 요구한다.

## 5. 고정 비교군과 실행량

### 5.1 주 held-out 행렬

신규 8장 × 좌우 2면 = 16개 page observation이다.

모든 16면에서 실행:

| extraction | geometry | 신규 GPU OCR | 목적 |
|---|---|---:|---|
| oracle | UVDoc bilinear | 16 | 페이지 검출 오차가 없는 보정 기준 |
| seam-conservative | UVDoc bilinear | 16 | 실제 후보 조합 |

각 그룹의 첫 번째 촬영 4장 × 좌우 2면에서만 control 실행:

| extraction | geometry | 신규 GPU OCR | 목적 |
|---|---|---:|---|
| oracle | none | 8 | UVDoc 자체의 구조 회귀 확인 |
| seam-conservative | none | 8 | 자동 crop의 무보정 control |

주 held-out 합계: **48건**.

### 5.2 p309 조명 진단 행렬

기존 p30 세 촬영본의 오른쪽 p309에서 실행:

| extraction | geometry | 신규 GPU OCR |
|---|---|---:|
| oracle | UVDoc bilinear | 3 |
| seam-conservative | UVDoc bilinear | 3 |

조명 진단 합계: **6건**.

자동 p309는 기존 full-spread gate의 거부 상태를 manifest에 그대로 보존한다. 오프라인
진단 queue에만 `diagnostic_override=true`를 명시해 실행하며 이를 production accept로
기록하지 않는다.

### 5.3 총 상한

- 주 held-out: 48건
- p309 조명 진단: 6건
- 총 신규 GPU OCR 상한: **54건**

이번 패킷에서는 coarse warp, bicubic, unsharp, CLAHE, threshold sweep, 다른 seam 알고리즘을
추가하지 않는다. 실패가 발생해도 54건을 넘겨 사후 후보를 탐색하지 않는다.

## 6. 측정 항목

### 6.1 페이지 추출

- own-page mask recall
- opposite-page inclusion
- oracle/automatic bbox와 면적 차이
- seam 위치·confidence·fallback reason
- 물리 frame contact와 spine-side contact의 구분
- 본문, 제목, 선택지, 표·그림, page number, footer 잘림의 육안 검토
- 원본, mask, crop overlay와 contact sheet

### 6.2 실제 Document Parser

실제 production 경로를 사용한다.

```text
prepared page image
→ PaddleOcrVlAdapter
→ build_document_ir_from_vl
→ Page IR schema validation
→ flatten_document
→ 수식/표 점역 진단
```

기록 항목:

- OCR 실행 상태, image hash, engine signature, device
- Page IR schema validity
- node type sequence와 type별 수
- 정규화 text와 비공백 문자 수
- parse issue code와 수
- anchor 존재와 순서
- braille opportunity/translated/withheld/error 수
- 전체 packed braille cell sequence 보조 지표
- canonical AST 정렬 기반 공통 수식 span/cell
- oracle-only 누락 수식과 automatic-only 추가 수식
- 추가 수식 표현의 oracle 일반 텍스트 존재 여부
- automatic UVDoc 대 oracle UVDoc 동일 원문 비교
- 동일 spread 반복 촬영 간 text/node/cell 비교
- 대표 촬영에서 none 대 UVDoc 구조 비교

### 6.3 영상 보조 지표

- Laplacian variance
- Tenengrad
- 명도 분포와 grid luminance range
- 이중 edge, halo, 획 소실의 육안 진단

영상 지표는 OCR·구조 gate를 대체하지 않는다.

## 7. 사전 판정 기준

### 7.1 Mask hard gate

정상 신규 16면 각각에서:

- own-page recall ≥ 0.99
- opposite-page inclusion ≤ 0.01
- 명백한 본문·선택지·표·그림·footer 절단 0
- automatic reject를 oracle로 대체해 성공 처리하지 않음

### 7.2 Automatic UVDoc hard gate

- 16/16 실제 GPU OCR 완료 또는 각 실패가 명시적으로 기록됨
- 16/16 Page IR schema-valid여야 완전 통과
- 수동 anchor의 치명적 누락 0
- automatic이 oracle보다 새 braille error를 만들지 않음
- automatic 대 oracle UVDoc text similarity:
  - 각 페이지 0.90 이상
  - 전체 median 0.96 이상
- automatic 대 oracle UVDoc의 ordered canonical AST 정렬:
  - oracle 공통 수식 span coverage 각 페이지 0.95 이상
  - 전체 median span coverage 0.98 이상
  - 정렬된 공통 수식 cell similarity 각 페이지 1.0
- automatic-only 수식 span/cell은 전체 셀 유사도 벌점으로 합치지 않고 별도 목록화
- automatic-only 수식이 oracle 일반 텍스트에 존재하는지 별도 기록
- oracle 대비 braille opportunity 감소가 각 페이지 20%를 넘지 않음

전체 packed cell similarity는 진단용으로 계속 기록하지만 hard gate로 사용하지 않는다.
cell 수와 block alignment가 달라 비교 불가능한 경우 1.0이나 0으로 강제하지 않고
`ALIGNMENT_FAILED`로 기록하며 hard gate 미통과로 처리한다.

### 7.3 반복 촬영 gate

동일 spread의 두 촬영에서 좌우 각각 비교한다.

- automatic UVDoc text similarity 각 페이지쌍 0.90 이상, median 0.95 이상
- node sequence similarity 각 페이지쌍 0.70 이상, median 0.85 이상
- 반복쌍 ordered AST 공통 span coverage 각 방향 0.90 이상, median 0.95 이상
- 정렬된 공통 수식 cell similarity 1.0
- 한 촬영에만 존재하는 수식 span/cell은 누락과 추가로 분리 기록
- 전체 packed cell similarity는 보조 지표로만 기록
- 두 촬영 중 한쪽에서만 발생한 치명적 anchor 누락 0
- 새 braille error 증가 0

node 분할 수가 달라도 anchor와 text가 보존된 경우 그 차이는 별도 over-segmentation 진단으로
남긴다. node sequence만으로 전체 실패를 확정하지 않는다.

### 7.4 UVDoc 대 none 판정

대표 8면에서 oracle-none과 oracle-UVDoc을 비교한다.

- UVDoc의 schema/anchor hard pass 수가 none보다 낮아지면 geometry 회귀
- UVDoc에서만 새 braille error 또는 치명적 block 누락이 생기면 geometry 회귀
- 둘 다 hard pass이면 text 유사도만으로 절대 정확도 우승을 주장하지 않음
- UVDoc이 더 많은 구조 gate를 통과하거나 반복 안정성이 높을 때만 제한적 보정 근거로 기록

신규 held-out 페이지에는 p30과 같은 human golden transcription이 없으므로 none과 UVDoc
중 어느 쪽이 문자 단위로 절대 정확한지는 판정하지 않는다.

### 7.5 최종 verdict

`HELD_OUT_COMBINATION_SUPPORTED`

- 신규 16면에서 mask, automatic UVDoc, 반복 촬영 hard gate를 모두 통과
- 대표 none control 대비 UVDoc hard regression 없음

`HELD_OUT_COMBINATION_SUPPORTED_WITH_EXCEPTIONS`

- 전체 median과 실행·schema gate는 통과하지만 일부 페이지별 floor 또는 비치명적 구조 gate 실패
- 실패 artifact와 원인을 명시하며 production 승격 금지

`HELD_OUT_COMBINATION_NOT_SUPPORTED`

- 본문/anchor 치명적 누락, mask hard failure, 새 점역 오류, 반복 불안정 또는 median 기준 실패

`BLOCKED_INPUT_OR_RUNTIME`

- 신규 라벨 세트 부족·불일치 또는 실제 GPU/model runtime 사용 불가

어떤 positive verdict도 `PRODUCTION_GENERALIZATION_COMPLETE`를 의미하지 않는다.

## 8. p309 조명 gate 판정

기존 `UNEVEN_ILLUMINATION` 결과를 유지한 채 oracle과 automatic UVDoc을 비교한다.

`ILLUMINATION_GATE_PROVISIONAL_OVERREJECT_EVIDENCE`

- 6/6 실행·schema valid
- page number 309와 주요 수동 anchor 보존
- automatic 대 oracle text similarity 각 촬영 0.90 이상
- automatic 대 oracle ordered AST 공통 span coverage 각 촬영 0.95 이상
- 정렬된 공통 수식 cell similarity 각 촬영 1.0
- automatic-only 수식 span/cell은 별도 진단
- 새 braille error 없음

`ILLUMINATION_GATE_QUALITY_CORRELATED_REJECT`

- 조명이 어두운 영역과 일치하는 치명적 OCR/구조 누락 또는 반복 실패가 확인됨

`ILLUMINATION_GATE_INCONCLUSIVE`

- 촬영별 결과가 상충하거나 p309 human golden 부재로 원인을 구분하지 못함

이 판정 뒤에도 기존 threshold `35`를 자동으로 바꾸지 않는다. threshold 조정은 정상·그림자·
실제 실패 표본이 포함된 별도 calibration 패킷에서 한다.

## 9. 기존 stress/empty 샘플 처리

기존 비라벨 이미지에는 OCR을 실행하지 않고 입력 gate 회귀만 확인한다.

- `175110`: 기존 정상 control 판정 유지 여부
- `175116`, `175119`, `175120`, `175126`, `175130`: 기존 abnormal reject 유지 여부
- `175153`, `175200`: `PAGE_NOT_FOUND` 유지 여부

사용자가 각 이미지의 정확한 의도 reason을 지정한 manifest는 없으므로 reason별 정확도는
계산하지 않는다. accept/reject가 바뀌면 자동 threshold 조정 없이 review 대상으로 남긴다.

## 10. 실행 단계

### WP-0. 구현·설정 freeze

- 기준 commit, seam 설정, crop padding, fallback threshold, UVDoc checkpoint hash 기록
- Paddle/PaddleOCR/PaddleX/GPU/engine signature 기록
- 기존 `D:/venvs/gpu_ocr_test`와 model cache만 사용
- 신규 package 설치, model 다운로드, checkpoint 교체 금지

Gate: 기준 hash가 달라졌으면 변경 내용을 검토하기 전 실행하지 않는다.

### WP-1. 입력 audit와 split 고정

- 신규 8장 JPG/JSON pairing과 strict validation
- 4개 `source_spread_id`, 각 2개 `repeat_id` manifest 생성
- 책/내용 category는 개인 식별 정보 없이 실험용 ID로 기록
- 주 held-out, p309 diagnostic, stress audit를 서로 다른 manifest partition으로 고정
- 원본과 라벨은 수정하지 않음

Gate: 8/8 strict pass가 아니면 주 실험은 `BLOCKED_INPUT_VALIDATION`.

### WP-2. Anchor와 review sheet

- 각 신규 16면과 p309 오른쪽의 최소 anchor 작성
- 원본+라벨 overlay 생성
- 동일 spread 반복쌍 contact sheet 생성
- page number와 원문 동일성 확인

Anchor가 불명확한 페이지는 임의로 채우지 않고 `ANCHOR_NOT_VERIFIED`로 둔다.

### WP-3. Artifact 준비

- oracle/seam-conservative crop 생성
- 지정된 none/UVDoc만 생성
- stable artifact ID와 full-frame lineage 기록
- UVDoc model batch 1회 load
- 원본, crop, mask, geometry 결과 hash 기록

Gate: 예상 record 48개와 exact queue cap 검증.

### WP-4. 주 GPU OCR

- 16개 oracle UVDoc 실행·검토
- oracle 완료 후 16개 automatic UVDoc 실행
- 대표 8면 oracle-none과 automatic-none 실행
- adapter는 batch당 1개 instance 재사용
- artifact 실패를 다른 record의 cache나 oracle로 대체하지 않음

실행 순서를 지켜 crop과 geometry의 실패 원인을 분리한다.

### WP-5. p309 조명 진단

- 기존 full-spread reject reason 보존
- oracle UVDoc 3건 실행
- 명시적 diagnostic override로 automatic UVDoc 3건 실행
- 실행 성공을 production gate 통과로 바꾸지 않음

### WP-6. Stress/empty 회귀 audit

- 기존 8개 비라벨 control/stress 이미지에 gate만 실행
- 예상 accept/reject와 실제 결과 기록
- 새로운 OCR queue 생성 금지

### WP-7. 비교·육안 검토·보고서

- 사전 metric과 verdict 생성
- 그룹별 반복 촬영 비교
- oracle/automatic과 none/UVDoc contact sheet
- 실패 페이지의 원본·mask·crop·UVDoc·OCR 구조 diff
- 확인한 사실, 해석, 미검증 사항 분리

## 11. 구현 범위

예정 신규 파일:

- `src/book_scanner/evaluation/held_out_reference.py`
- `tools/run_held_out_crop_uvdoc_validation.py`
- `tests/unit/test_held_out_reference.py`
- `HELD_OUT_CROP_UVDOC_GENERALIZATION_REPORT.md`

예정 수정 가능 파일:

- `src/book_scanner/evaluation/paired_ocr_inputs.py`
- `src/book_scanner/evaluation/paired_page_ir.py`
- 관련 unit test
- `README.md`

구현 원칙:

- p30 전용 runner와 comparator의 기존 결과·기본값을 변경하지 않는다.
- 기존 20260826 capture/fallback 기본 목록과 stable artifact ID를 보존한다.
- 신규 runner가 capture group, repeat, 양쪽 side, partition과 queue cap을 명시적으로 주입한다.
- same-content 비교는 동일 source spread/side라는 assertion이 있을 때만 활성화한다.
- production session gate와 offline diagnostic override를 타입·manifest에서 구분한다.
- 실패 reason, 원본 좌표, model/checkpoint/input hash를 보존한다.

수정 금지:

- `src/book_scanner/session/loop.py`
- `src/book_scanner/transmit/client.py`
- `document-parser` production source
- 원본 JPG/LabelMe JSON
- p030 fixture와 기존 p30 산출물
- seam/UVDoc/fallback의 production 기본값

## 12. 테스트 범위

필수 unit/integration test:

- 4개 spread × 2 repeat × 2 side grouping
- 같은 그룹에서 다른 page number 또는 같은 JPG hash 검출
- strict-invalid 입력의 명시적 block
- held-out/development/diagnostic/stress partition 혼입 방지
- 48개 주 queue와 6개 diagnostic queue 상한
- 대표 repeat에만 none control 생성
- diagnostic override가 production accept를 변경하지 않음
- same-source assertion 없는 cell 비교 비활성
- text/node/cell floor와 median 판정
- alignment failure가 성공으로 계산되지 않음
- 한 artifact 실패 시 나머지 결과 보존
- adapter와 UVDoc model batch 재사용
- 기존 p30 및 20260826 manifest/stable ID 불변
- fake adapter staged end-to-end
- 전체 `book-scanner/tests` 통과
- `compileall`, JSON schema/parsing, `git diff --check`

실제 검증:

- 신규 JPG/JSON 8/8 strict pass
- 주 GPU OCR 최대 48건 실제 실행
- p309 diagnostic GPU OCR 최대 6건 실제 실행
- Page IR와 점역 진단 실행
- 모든 review sheet 육안 검토
- 모델 다운로드 0 확인

실제 GPU 실행이 끝나지 않은 항목은 완료로 표시하지 않는다.

## 13. 완료 조건

전체 패킷 완료에는 다음이 필요하다.

- 신규 held-out 8장의 provenance와 strict validation 완료
- 4개 반복쌍의 source identity와 anchor 확인
- 주 48건이 실제 GPU에서 완료되거나 실패 record로 명시됨
- p309 6건이 실제 GPU에서 완료되거나 실패 record로 명시됨
- mask, OCR, 구조, 반복, 점역 metric과 사전 verdict 생성
- stress/empty gate 회귀 결과 생성
- 육안 검토 sheet와 실패 진단 생성
- 신규/기존 테스트 및 정적 검증 통과
- session/transmit/Document Parser production source 비변경 확인
- 보고서가 p30 human golden의 적용 범위, 신규/p309 golden 부재와 production 미검증을 명시

신규 라벨 8장이 제공되지 않으면 코드 골격을 만들 수 있더라도 주 실험은
`BLOCKED_INPUT_OR_RUNTIME`으로 남긴다. 일부 입력만 실행하고 분모를 줄여 완료로 표현하지
않는다.

## 14. 비범위

- segmentation 모델 학습·fine-tuning
- 데이터 증강·오픈데이터셋 도입
- seam·fallback·illumination threshold 재탐색
- coarse warp와 후보정 재실험
- OCR/VL 또는 점역 production 규칙 수정
- 전체 페이지 수동 transcription
- 절대 CER/WER 또는 절대 점자 정확도 주장
- session loop·전송·TTS·datapack 실행
- Raspberry Pi 성능 측정
- production 기본값 채택

## 15. 산출물과 Git 정책

예정 출력:

```text
book-scanner/experiment_outputs/held_out_crop_uvdoc_20260830/
  input_manifest.json
  anchor_manifest.json
  extraction_manifest.json
  geometry_manifest.json
  primary_ocr_summary.json
  illumination_diagnostic_summary.json
  stress_gate_summary.json
  final_summary.json
  images/
  masks/
  ocr/
  comparisons/
  review/
```

최종 보고서, 재현 manifest/summary, Page IR record, 파생 이미지와 review sheet는 검증 후 현재
실험 branch에 포함한다. PNG/JPG는 기존 Git LFS 규칙을 사용한다.

포함하지 않는 항목:

- 중복 원본 JPG/ZIP
- LabelMe `imageData` blob
- model weight와 cache
- Python virtual environment
- 실패 중 생성된 임시 runtime 파일
- 사용자 계정명이나 호스트 종속 절대 경로

## 16. 중단 및 재승인 조건

다음 경우 임의로 범위를 확대하지 않는다.

- 신규 8장 또는 4개 반복쌍 구성이 충족되지 않음
- 라벨 수정·좌표 clamp·자동 복원이 필요함
- threshold, seam cost, padding 또는 UVDoc 설정 변경이 필요함
- 신규 package/model/checkpoint 다운로드나 교체가 필요함
- 54건 GPU OCR 상한을 넘는 실행이 필요함
- Document Parser production source 또는 점역 규칙 수정이 필요함
- 신규/p309 사람 transcription이 없이는 판정할 수 없는 절대 정확도 결론이 필요함
- 결과를 보고 사전 판정 기준을 변경해야 함
- production session/transmit 동작 변경이 필요함

## 17. 승인 요청

이 패킷 승인 시 다음을 허용하는 것으로 해석한다.

1. 신규 라벨 8장이 준비되면 4개 spread 반복쌍의 held-out manifest를 만든다.
2. generic held-out comparator, runner와 관련 테스트를 구현한다.
3. 기존 GPU 환경과 model cache로 주 실험 최대 48건을 실행한다.
4. p309 오른쪽 조명 진단 최대 6건을 별도 partition으로 실행한다.
5. 기존 stress/empty 샘플에는 OCR 없이 gate 회귀만 실행한다.
6. 결과 보고서와 재현 산출물을 현재 실험 branch에 추가·커밋·푸시한다.

승인은 신규 라벨 자동 생성, threshold 재조정, 모델 다운로드, production 기본값 변경,
session/transmit 수정 또는 절대 OCR·점역 정확도 주장을 허용하지 않는다.
