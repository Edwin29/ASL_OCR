# Paired OCR 실행 환경 복구 및 Phase A Pilot — 작업 패킷

상태: **승인됨 — 기존 GPU 환경 재발견, smoke/pilot/전체 Phase A 실행 완료**
작성일: 2026-08-30
선행 문서:

- `PAIRED_OCR_INPUT_EXPERIMENT_WORK_PACKET.md`
- `PAIRED_OCR_INPUT_EXPERIMENT_REPORT.md`
- `SPINE_SEAM_DETECTION_EXPERIMENT_REPORT.md`
- `CODEX_IMPLEMENTATION_CONTEXT.md`

## 1. 배경

선행 paired 실험에서 다음 항목은 완료되었다.

- 라벨 8면 × extraction 4종, Phase A 입력 32개 생성
- oracle/seam-conservative × geometry 3종, Phase B record 48개 생성
- fallback stress/empty 입력의 OCR 전 제외
- UVDoc batch당 model 1회 load
- 기존 Document Parser의 PaddleOCR-VL → Page IR → 접근성 flatten/점역 진단 연결

그러나 현재 Python 환경의 PaddlePaddle이 CUDA로 compile되지 않아 신규 overlap/seam
24건이 OCR 단계에 진입하지 못했다. CPU 재시도는 model load 후 첫 페이지가 약 12분
동안 완료되지 않아 중단했다. 기존 GPU cache와 exact image hash가 일치한 oracle 8건만
재사용되었으므로, 신규 seam crop의 OCR·점역 실효성은 아직 검증되지 않았다.

## 2. 목적

이 패킷의 목적은 다음 두 가지다.

1. 새 package나 model을 받기 전에 현재 호스트 또는 기존 로컬 실행 환경에서
   PaddleOCR-VL GPU 실행이 가능한 경로가 있는지 확인한다.
2. GPU 실행이 가능한 경우 가장 판별력이 높은 3면의 extraction-only pilot을 기존
   Document Parser production 경로로 실행하고, 사전 규칙에 따라 전체 Phase A 확대 여부를
   결정한다.

이 패킷은 새로운 페이지 검출 알고리즘, UVDoc 후보정, 점역 기능을 개발하는 패킷이 아니다.

## 3. 핵심 질문

1. 현재 호스트에 PaddleOCR-VL이 실제로 사용할 수 있는 CUDA device와 기존 Python
   environment가 있는가?
2. seam-confirmed/seam-conservative crop은 oracle 및 overlap 대비 Page IR의 핵심
   문자·표·수식 구조를 보존하는가?
3. seam-conservative가 반대 페이지 mask 유입 감소를 유지하면서 치명적인 OCR 회귀를
   일으키지 않는가?
4. `174958 right`의 알려진 표·회색 영역에서 구조적 누락 또는 이웃 페이지 혼입이
   관찰되는가?

## 4. 단계와 중단 조건

```text
기존 실행 환경 read-only audit
→ GPU-capable environment 발견 여부
→ model/cache hash preflight
→ 3면 × extraction 4종 pilot
→ Page IR/점역 진단 및 제한적 golden 검토
→ 사전 gate
→ 통과 시에만 나머지 5면 Phase A 확대
```

GPU-capable environment가 없으면 OCR을 CPU로 자동 전환하지 않는다. 상태를
`BLOCKED_EXECUTION_ENVIRONMENT`로 기록하고 중단한다.

## 5. WP-1 — 기존 실행 환경 audit

### 읽기 전용 확인

- `nvidia-smi` 존재 여부와 GPU/driver/CUDA 표시
- 현재 Python executable 및 architecture
- `paddle.__version__`
- `paddle.is_compiled_with_cuda()`
- `paddle.device.cuda.device_count()`
- `paddleocr` version
- 프로젝트 내 기존 `.venv`, pyenv, Conda, WSL, Docker 실행 경로의 존재 여부
- 각 후보 환경의 Paddle CUDA compile 여부
- model cache 및 UVDoc checkpoint 존재/hash
- 기존 OCR cache의 engine signature

환경을 찾기 위해 시스템 전체를 무제한 탐색하지 않는다. workspace, 현재 pyenv/Conda
목록, 등록된 WSL/Docker environment 등 명시적으로 열거 가능한 후보만 확인한다.

### 허용하지 않는 변경

- PaddlePaddle/PaddleOCR 재설치 또는 upgrade/downgrade
- CUDA toolkit·driver 설치
- 새 venv/Conda/WSL/Docker image 생성
- model/checkpoint 다운로드
- 환경변수 영구 변경
- 기존 model cache 삭제·이동

위 변경이 필요하면 필요한 package/version/예상 용량/위험을 보고하고 재승인받는다.

### audit 판정

- `GPU_ENV_READY`: 기존 환경에서 CUDA PaddleOCR-VL smoke test 가능
- `GPU_PRESENT_ENV_MISSING`: GPU는 있으나 CUDA 지원 Paddle environment가 없음
- `GPU_NOT_AVAILABLE`: 사용할 수 있는 NVIDIA GPU가 없음
- `MODEL_ASSETS_INCOMPLETE`: 실행 환경은 있으나 기존 local model cache가 불완전
- `ENVIRONMENT_INCONCLUSIVE`: 후보 환경을 안전하게 판별하지 못함

`GPU_ENV_READY` 외에는 WP-2로 넘어가지 않는다.

## 6. WP-2 — 비파괴 smoke test

GPU environment가 확인되면 기존 paired oracle artifact 한 건을 사용한다.

권장 입력:

```text
20260826_174958_right_oracle_none_none
```

검증 조건:

- model은 local cache에서만 load
- device가 실제 `gpu:0`으로 유지되고 CPU fallback이 발생하지 않음
- image hash + engine signature가 기존 cache와 일치하면 cache를 먼저 검증
- 강제 신규 smoke가 필요하면 동일 입력 1건만 별도 output에서 실행
- Page IR schema valid
- 접근성 flatten이 성공
- 점역 opportunity/error 진단이 생성
- model load count와 wall time 기록

smoke test가 5분 이내 완료되지 않거나 GPU 대신 CPU를 사용하면 pilot을 시작하지 않고
`BLOCKED_SMOKE_TEST`로 중단한다. 이 시간 제한은 OCR 품질 기준이 아니라 잘못된 device에서
대규모 batch를 시작하지 않기 위한 실행 안전장치다.

## 7. WP-3 — 최소 Phase A OCR pilot

### Pilot 표본

| capture/side | 역할 |
|---|---|
| `174958 right` | 표·회색 문제 영역, 선행 UVDoc 회귀 관찰 면 |
| `175109 left` | 다른 spread의 일반 텍스트/수식 면 |
| `175109 right` | 동일 spread 반대 면, 좌우 seam 대칭성 확인 |

각 면에서 다음 네 extraction을 geometry/postprocess 없이 비교한다.

| extraction | 역할 |
|---|---|
| `oracle` | LabelMe anchor; 정답 OCR은 아님 |
| `overlap` | 본문 보존 우선 baseline |
| `seam_confirmed` | 반대 페이지 유입 최소 후보 |
| `seam_conservative` | uncertainty band 보존 후보 |

총 12개 입력이며, exact hash + engine signature가 일치하는 oracle cache는 재사용한다.
신규 최대 OCR 실행은 9건이다.

### 고정 실행 경로

```text
paired artifact
→ PaddleOcrVlAdapter
→ build_document_ir_from_vl
→ validate Page IR
→ flatten_document
→ math_focus_item_to_braille / table_cell_braille
```

다음은 실행하지 않는다.

- TTS
- datapack write
- session loop
- transmit client
- 외부 전송
- Phase B coarse/UVDoc OCR
- Phase C 후보정

## 8. WP-4 — 제한적 golden ROI 준비

전체 페이지 transcription을 요구하지 않는다. `174958 right`에서 기존 회귀 관심 영역의
검토용 ROI와 manifest를 준비한다.

manifest 항목:

- ROI full-frame bbox 및 source hash
- 원본/oracle/overlap/seam-confirmed/seam-conservative ROI 이미지
- ㄱ/ㄴ/ㄷ/ㄹ 존재 여부
- 선택지 번호·조합 존재 여부
- TABLE/TEXT 구조
- `정답`, `해설` 등 핵심 표기
- 중요한 수식의 사람이 확인한 transcription 입력란
- 검수자와 검수 시각

사람이 transcription을 입력하지 않은 항목은 반드시
`MANUAL_GOLDEN_NOT_VERIFIED`로 남긴다. 기존 OCR 출력이나 선행 보고서의 육안 관찰을
정답으로 복사하지 않는다.

## 9. 비교 지표

### 영상/추출 지표

- own-page recall
- opposite-page inclusion
- crop bbox와 mask coverage
- 입력 image/mask SHA-256

### Page IR/OCR 지표

- schema validity
- EMPTY_PAGE 및 parse issue
- normalized non-whitespace character count
- oracle 대비 character count ratio/drop
- normalized text similarity
- node type count 및 reading-order sequence similarity
- TEXT/TABLE/FORMULA 추가·누락·타입 변경
- 반대 페이지로 의심되는 block 추가

### 점역 진단

- braille opportunity 수
- translated/withheld/error 수
- 수식·표 node 누락에 따른 opportunity 감소
- 혼합 문자열 `NotImplementedError` 별도 집계

점역 coverage는 영상 OCR 품질과 분리한다. 혼합 점역 미지원만으로 extraction 후보를
탈락시키지 않는다.

## 10. Pilot gate

seam-conservative가 다음을 모두 만족하면 `PILOT_NO_CLEAR_REGRESSION`으로 두고 WP-5
전체 Phase A 확대를 허용한다.

- pilot 3면 모두 Page IR schema valid
- EMPTY_PAGE 또는 치명적 parse failure 없음
- 면별 oracle 대비 비공백 문자 수 감소가 20% 이하
- overlap 대비 TABLE/FORMULA node의 명백한 추가 누락 없음
- node sequence similarity가 overlap보다 반복적으로 현저히 낮지 않음
- `174958 right`에서 자동 비교상 핵심 표/항목 block의 명백한 누락 없음
- smoke 및 pilot 동안 model이 batch마다 다시 load되지 않음

다음 경우 확대하지 않는다.

- 본문·수식·표의 명백한 seam 절단: `PILOT_OCR_REGRESSION`
- schema/empty/fatal failure: `PILOT_TECHNICAL_FAILURE`
- 지표 상충 또는 golden 부재로 판단 불가: `PILOT_INCONCLUSIVE`

transcription이 완성되지 않은 상태에서 `OCR_IMPROVED` 판정을 금지한다.

## 11. WP-5 — 조건부 전체 Phase A 확대

Pilot gate가 `PILOT_NO_CLEAR_REGRESSION`인 경우에만 나머지 라벨 5면의 네 extraction을
실행한다. 이미 완료된 12건은 재실행하지 않는다.

전체 Phase A 완료 시 확인한다.

- 라벨 8면 × 4 extraction = 32건의 Page IR 또는 명시적 건별 실패
- oracle 대비 페이지별 paired 비교
- overlap 대비 seam-confirmed/conservative 비교
- `174943` ↔ `174953` 동일 variant 반복 촬영 안정성
- node sequence와 text similarity
- 점역 coverage 오류를 OCR 회귀와 분리

전체 결과의 가능한 판정:

- `SEAM_OCR_CANDIDATE`
- `OVERLAP_FALLBACK`
- `EXTRACTION_INCONCLUSIVE_NO_GROUND_TRUTH`
- `TECHNICAL_FAILURE`

전체 transcription이 없으므로 CER/WER 또는 절대 OCR 정확도는 주장하지 않는다.

## 12. 구현 및 수정 범위

우선 기존 파일을 재사용한다.

- `src/book_scanner/evaluation/paired_ocr_inputs.py`
- `src/book_scanner/evaluation/paired_page_ir.py`
- `tools/run_paired_ocr_input_experiment.py`
- `experiment_outputs/paired_ocr_20260830/*`

필요한 최소 변경 후보:

- 환경 audit/preflight report 도구
- pilot capture/side 선택 option
- 5분 smoke timeout 및 실제 resolved device 기록
- golden ROI manifest exporter
- pilot/full Phase A summary와 재개 가능한 queue
- unit tests와 최종 실행 보고서

기존 artifact ID와 cache 계약을 변경하지 않는다. 이전 실패 record는 덮어쓰지 않고
device/attempt별 summary로 보존한다.

## 13. 테스트 범위

### Unit

- CUDA 미지원 환경에서 OCR queue 진입 전 차단
- GPU 요청 후 CPU fallback을 성공으로 기록하지 않음
- smoke timeout 시 pilot 미실행
- pilot이 정확히 지정 3면 × 4 extraction만 선택
- exact image hash + engine signature cache 검증
- 동일 adapter/model batch 재사용
- 개별 OCR 실패가 다른 입력을 중단하지 않음
- pilot gate의 pass/regression/inconclusive 분기
- golden 미입력 항목은 verified로 승격되지 않음
- 반복 촬영 동일 variant pair 집계
- 비ASCII Windows 경로

### 실제

- 환경 audit JSON
- GPU smoke 1건
- pilot 최대 신규 9건
- gate 통과 시 나머지 최대 신규 15건
- Page IR/점역 진단/paired summary
- `pytest`, `compileall`, `git diff --check`

## 14. 완료 조건

다음 조건을 실제로 만족한 항목만 완료로 처리한다.

- 실행 환경과 resolved device가 증거와 함께 기록됨
- model 다운로드 없이 GPU smoke 성공
- pilot 12건이 cache hit 또는 실제 Page IR로 존재
- pilot의 Page IR/구조/text/점역 진단 비교가 생성됨
- 사전 gate가 결과를 본 뒤 변경되지 않음
- gate 통과 시에만 전체 Phase A가 실행됨
- stress/empty 입력은 계속 OCR queue에서 제외됨
- session/transmit/Document Parser production source 미변경
- 전체 테스트 및 정적 검증 통과
- 정확도 주장과 미검증 항목이 분리됨

GPU 환경을 찾지 못하는 경우 이 패킷의 환경 audit은 완료할 수 있지만, paired OCR 검증은
`BLOCKED_EXECUTION_ENVIRONMENT`로 남는다. 이를 Phase A 완료로 표현하지 않는다.

## 15. 비범위

- CUDA/Paddle package 설치 또는 driver 변경
- 새 Python/Conda/WSL/Docker 환경 생성
- model/checkpoint 다운로드
- 전체 페이지 수작업 transcription
- 페이지 검출 학습·fine-tuning·데이터 증강
- coarse/UVDoc Phase B OCR
- unsharp/bicubic/CLAHE/SR Phase C
- 혼합 점역 기능 구현
- session/quality judge/transmit 통합
- production 기본 extraction 변경
- Raspberry Pi 성능 판정

## 16. 재승인 조건

다음 중 하나라도 필요하면 현재 패킷을 중단하고 별도 승인을 요청한다.

- PaddlePaddle/PaddleOCR package 설치·교체
- CUDA toolkit 또는 driver 설치
- 새 venv/Conda/WSL/Docker environment 생성
- 외부 GPU/클라우드 환경 사용 또는 artifact 업로드
- model/checkpoint 다운로드
- CPU 장시간 batch 실행
- pilot gate 또는 20% 기준 변경
- Phase B/Phase C 실행
- Document Parser production source 수정
- 사람이 확인할 transcription 범위 확대

## 17. 승인 요청

이 패킷 승인 시 다음을 허용하는 것으로 해석한다.

1. 현재 호스트와 열거 가능한 기존 로컬 environment를 읽기 전용으로 audit한다.
2. 기존 GPU-capable environment가 확인된 경우 local model/cache만 사용해 smoke를 실행한다.
3. smoke 성공 시 지정 3면 × 4 extraction pilot을 기존 Document Parser 경로로 실행한다.
4. golden ROI 이미지와 미기입 manifest를 생성한다.
5. 사전 gate 통과 시에만 나머지 라벨 5면 Phase A를 확대 실행한다.
6. Git 제외 경로에 Page IR, cache, ROI, summary를 저장한다.
7. 설치·다운로드·외부 업로드가 필요하면 실행하지 않고 재승인받는다.
