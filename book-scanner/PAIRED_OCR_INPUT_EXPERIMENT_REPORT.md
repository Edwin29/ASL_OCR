# 페이지 추출 × 보정 × 후보정 Paired OCR 실험 보고서

작성일: 2026-08-30
상태: **후속 GPU 실행으로 Phase A 32/32 완료 — 최신 결과는 아래 후속 보고서 참조**

> 2026-08-30 후속 탐색에서 `D:/venvs/gpu_ocr_test` GPU 전용 환경을 재발견하여
> Phase A를 완료했다. 이 문서의 `BLOCKED_DEVICE` 내용은 최초 시도의 역사적 기록이다.
> 최신 판정과 수치는 `PAIRED_OCR_EXECUTION_RECOVERY_REPORT.md`를 기준으로 한다.

## 결론

승인된 staged 실험 runner와 provenance, 비교기, fallback gate를 구현했다. Phase A
32개와 Phase B 48개 영상 record는 모두 생성되었으며 UVDoc은 한 번만 load되었다.
그러나 현재 Windows Python의 PaddlePaddle은 CUDA를 지원하지 않는다. 기존 GPU cache와
정확히 같은 image hash를 가진 oracle 8건만 재사용할 수 있었고, 신규 overlap/seam
24건은 `gpu:0`에서 실행되지 않았다. CPU로 실제 추론을 재시도했으나 첫 페이지가 모델
load 후 약 12분 동안 완료되지 않아 중단했다. 따라서 seam, coarse, UVDoc의 OCR 효과와
후보정 효과는 완료 또는 우승으로 판정하지 않는다.

현재 허용되는 판정은 다음과 같다.

- 입력 생성·fallback·lineage: `VERIFIED`
- seam의 라벨 mask 효과: `SEAM_MASK_CANDIDATE` (작은 4-spread 표본 한정)
- Phase A 추출 OCR: `BLOCKED_DEVICE`
- Phase B 보정 OCR: `BLOCKED_DEVICE`
- Phase C 후보정: `BLOCKED_PREREQUISITE`
- OCR 정확도/CER/WER/점자 정확도: `NOT_VERIFIED_NO_TRANSCRIPTION`

## 구현 범위

추가된 오프라인 코드는 다음을 제공한다.

- stable ID `{capture}_{side}_{extraction}_{geometry}_{postprocess}`
- 원본·label·mask·최종 입력 SHA-256과 crop bbox/full-frame lineage
- oracle/overlap/seam-confirmed/seam-conservative crop
- oracle 및 seam-conservative의 none/coarse/UVDoc bilinear variant
- cached Page IR의 image hash + engine signature 엄격 검증
- batch당 동일 adapter 재사용과 건별 실패 격리
- Page IR text/node sequence/count/parse issue/점역 coverage 비교
- 반복 실험을 위한 단계별 `extraction|geometry|postprocess` gate
- CUDA 불가 시 암묵적 CPU 전환 대신 `BLOCKED_DEVICE`

session loop, transmit client, Document Parser production source, 혼합 점역 구현은 변경하지
않았다. TTS, datapack 및 외부 전송도 실행하지 않았다.

## Phase A — 추출 입력

LabelMe 정답이 있는 4 spread의 좌우 8면에서 4종, 총 32개 입력이 모두 `READY`다.
아래 수치는 OCR 정확도가 아니라 full-frame label mask에 대한 추출 지표다.

| extraction | 면 | mean own recall | min own recall | mean opposite inclusion | max opposite inclusion |
|---|---:|---:|---:|---:|---:|
| oracle | 8 | 1.000000 | 1.000000 | 0.000000 | 0.000000 |
| overlap | 8 | 0.998314 | 0.996507 | 0.113829 | 0.181582 |
| seam confirmed | 8 | 0.996449 | 0.993717 | 0.001587 | 0.004353 |
| seam conservative | 8 | 0.996991 | 0.994046 | 0.005163 | 0.007774 |

seam-confirmed는 overlap에 비해 반대 페이지 유입을 크게 줄였지만 own-page recall도 평균
약 0.186%p 낮다. conservative는 recall 일부를 되찾는 대신 opposite inclusion이
confirmed보다 증가한다. 본문 손상 여부를 OCR로 확인하지 못했으므로 두 seam crop 중
production 후보를 선택하지 않는다.

## Fallback gate

- `175110`: `AUTOMATIC_CONTROL_READY`; oracle 분모에는 포함하지 않음
- `175116`, `175119`, `175120`, `175126`, `175130`: out-of-frame, extent,
  area 또는 조명 진단에 따라 OCR 전에 skip
- `175153`, `175200`: 좌우 모두 `PAGE_NOT_FOUND`, OCR 전에 skip

skip reason은 `extraction_manifest.json`에 면별 feature와 함께 저장되며, stress/empty
이미지는 OCR queue에 들어가지 않았다.

## Phase B — 보정 입력

oracle 8면과 seam-conservative 8면에서 다음 48개 record가 모두 준비되었다.

| geometry | record | 결과 |
|---|---:|---|
| none | 16 | Phase A 입력 재사용 |
| coarse | 16 | `READY` |
| UVDoc bilinear | 16 | `READY` |

UVDoc checkpoint SHA-256은
`7e90861b8a516eb4bc51f84bd889cb77275743d2d1d3ca8091951ec9f2b7da23`이고 model
load count는 1이다. coarse에는 source/destination quad, matrix, output size와 interpolation이
기록된다. UVDoc mask는 보정 후 pixel truth로 오해하지 않도록
`source_crop_unwarped_lineage_only`로 명시했다.

이 준비 성공은 보정의 OCR 실효성을 뜻하지 않는다.

## 실제 PaddleOCR-VL 실행

실제 production 경로는 다음과 같이 호출했다.

```text
paired artifact
→ PaddleOcrVlAdapter
→ build_document_ir_from_vl
→ evaluate_page_ir_braille (flatten + math/table braille diagnostics)
```

첫 `gpu:0` Phase A 실행 결과:

- 기존 exact hash + exact GPU engine signature oracle cache: 8건 `COMPLETE`
- 신규 overlap/seam: 24건 `OCR_FAILED`
- 원인: 설치된 PaddlePaddle이 CUDA로 compile되지 않음

그 뒤 runner에 device preflight를 추가하여 같은 상태에서는 건별 24회 실패 대신 즉시
`BLOCKED_DEVICE`를 기록한다. CPU 재실행은 모델을 한 번 load했으나 첫 신규 페이지가
약 12분 동안 완료되지 않았고, 32+32 staged batch에 현실적인 실행 환경이 아니어서
사용자가 기다리는 foreground 실행을 중단했다. CPU Page IR은 한 건도 완료되지 않았고
결과로 계산하지 않는다.

Phase A 비교 8건은 candidate도 oracle 자신인 cache self-control뿐이다. seam 비교가
아니므로 positive evidence로 사용하지 않는다.

## Phase C — 후보정

Phase B OCR summary가 `COMPLETE`가 아니므로 사전 gate가
`BLOCKED_PREREQUISITE`를 반환했다. 고정 unsharp 또는 bicubic screening을 실행하지
않았고, `NO_POSTPROCESS_EVIDENCE`라는 결론도 내리지 않는다. 이는 후보정이 불필요하다는
뜻이 아니다.

`174958 right`의 수동 golden transcription manifest도 없으므로 상태는
`MANUAL_GOLDEN_NOT_VERIFIED`다.

## 테스트 및 정적 검증

- 신규 paired unit tests: 11 passed
- 전체 `book-scanner/tests`: **108 passed**
- fallback OCR queue 제외, stable ID, bbox round-trip, hash/cache invalidation,
  건별 OCR 실패 격리, Page IR 비교 및 Phase C gate를 검증
- 실제 Phase A 입력 32개 및 Phase B record 48개 존재 확인
- UVDoc load count 1 확인

- `python -m compileall -q book-scanner/src book-scanner/tools`: 통과
- `git diff --check`: 통과 (기존 Windows CRLF 변환 warning만 출력)

## 재개 조건과 명령

CUDA 지원 PaddlePaddle과 GPU가 보이는 동일 workspace에서 아래 순서로 재개한다. 모델을
새로 다운로드할 필요는 없으며 기존 manifest/cache hash 계약을 그대로 사용한다.

```bash
python tools/run_paired_ocr_input_experiment.py --phase extraction --device gpu:0
python tools/run_paired_ocr_input_experiment.py --phase geometry --device gpu:0
python tools/run_paired_ocr_input_experiment.py --phase postprocess --device gpu:0
```

Phase A/B가 실제로 `COMPLETE`된 뒤에만 comparator 결과와 수동 golden 검토를 사용해
후보정 screening 여부를 정한다. 검증된 transcription이 추가되지 않는 한 결과 표현은
`NO_CLEAR_REGRESSION`, `OCR_REGRESSION`, 또는 `INCONCLUSIVE_NO_GROUND_TRUTH`로 제한한다.

## 산출물

대형 산출물은 Git 제외 경로 `experiment_outputs/paired_ocr_20260830`에 있다.

- `extraction_manifest.json`
- `geometry_manifest.json`
- `extraction_gpu_0_ocr_summary.json`
- `geometry_gpu_0_ocr_summary.json`
- `postprocess_gpu_0_screening.json`
- `images/`, `masks/`, `ocr/`

GPU 첫 실패 시도의 상세 8 complete/24 failure record는 보존되어 있다. 이 record와 현재
device-block summary를 혼동하지 않는다.
