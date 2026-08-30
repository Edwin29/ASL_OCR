# Paired OCR 실행 환경 복구 및 Phase A Pilot — 실행 보고서

작성일: 2026-08-30
환경 상태: **`GPU_ENV_READY`**
Phase A 실행 상태: **32/32 COMPLETE**
최종 판정: **`EXTRACTION_INCONCLUSIVE_NO_GROUND_TRUTH`**

## 1. 결론

초기 PATH/workspace 중심 audit에서는 물리 GPU만 확인하고 CUDA Paddle environment를
찾지 못했다. 사용자의 지적 후 프로젝트 문서와 과거 실행 기록까지 탐색 범위를 넓혀,
프로젝트 밖의 기존 전용 환경 `D:/venvs/gpu_ocr_test`를 발견했다.

이 환경은 2026-08-21에 실제 GPU inference가 검증된 환경이며 현재도 정상 동작했다.
신규 seam-conservative smoke, 지정 12건 pilot, 조건부 나머지 20건을 실행했고 최종
Phase A 32건 모두 기존 Document Parser production 경로에서 Page IR을 생성했다.

seam-conservative는 mask 혼입과 oracle 상대 text similarity에서 가장 유망한 자동 crop
후보다. 그러나 반복 촬영의 node sequence 안정성이 overlap보다 낮은 사례가 있고,
`174958 right`에서 일부 항목/선택지 글자가 oracle OCR과 다르다. 사람이 검증한 golden
transcription도 없으므로 production 기본값으로 확정하지 않는다.

## 2. 기존 GPU 환경 재발견

### 결정적 증거

- `document-parser/docs/gpu-inference-setup.md`
- `document-parser/README.md`의 17페이지 GPU 실측 기록
- 기존 Page IR record의 `device=gpu:0` engine signature
- `D:/venvs/gpu_ocr_test`
- `D:/venvs/paddleocr-vl`

검증된 전용 환경:

| 항목 | 값 |
|---|---|
| Python | `D:/venvs/gpu_ocr_test/Scripts/python.exe` |
| Paddle | `paddlepaddle-gpu 3.2.1` |
| PaddleOCR | 3.7.0 |
| PaddleX | 3.7.2 |
| CUDA compiled | True |
| CUDA device count | 1 |
| GPU | NVIDIA GeForce RTX 4060 |
| torch | 설치되지 않음 |

전용 환경에서 torch를 제외한 이유는 프로젝트 문서에 기록된 cuDNN DLL 충돌 회피다.
package 설치·교체·다운로드 없이 기존 환경과 model cache만 사용했다.

초기 audit 누락 원인은 `D:/venvs`가 workspace, PATH, pyenv, `document-parser/.venv` 밖에
있었기 때문이다. 재발 방지를 위해 audit 도구의 기본 후보에 문서화된 두 환경을 추가했다.

## 3. GPU smoke

cache가 없던 다음 신규 입력을 사용했다.

```text
20260826_174958_right_seam_conservative_none_none
```

결과:

- 실제 device: RTX 4060, `gpu:0`
- model files: 기존 local cache 사용
- model 다운로드: 없음
- cache hit: False
- Page IR schema: valid
- 비공백 문자: 650
- node: 12
- braille opportunity/error: 34/22
- 5분 제한 이내 완료

점역 error는 선행 보고서에서 확인된 혼합 문자열 미지원에 주로 해당하며 영상 후보의
직접 실패로 세지 않는다.

## 4. 지정 Phase A pilot

다음 3면에서 extraction 4종, 총 12건을 실행했다.

- `174958 right`
- `175109 left`
- `175109 right`

12/12 schema-valid였고 `seam-conservative`의 oracle 대비 최대 문자 감소는 5.84%로
사전 20% 기준 이내였다. TABLE/FORMULA도 overlap보다 추가로 더 누락되지 않았으며,
세 면 중 node sequence가 overlap보다 현저히 낮은 경우가 반복되지 않았다.

pilot gate는 `PILOT_NO_CLEAR_REGRESSION`을 반환했고, 이에 따라 패킷 규칙대로 나머지
5면을 확대 실행했다.

단, 이 gate는 정확도 개선 판정이 아니다. `174958 right`의 자동 block 존재 여부만
확인했으며 manual golden은 미검증이다.

## 5. 전체 Phase A 결과

라벨 8면 × extraction 4종 = 32/32 Page IR이 모두 생성됐고 schema-valid였다.

### Oracle 상대 OCR 지표

| extraction | mean text similarity | min text similarity | max 문자 감소 | mean node sequence | min node sequence |
|---|---:|---:|---:|---:|---:|
| oracle | 1.0000 | 1.0000 | 0.00% | 1.0000 | 1.0000 |
| overlap | 0.7709 | 0.5149 | -4.11% | 0.6350 | 0.3704 |
| seam-confirmed | 0.9030 | 0.5622 | 7.48% | 0.8731 | 0.6061 |
| seam-conservative | **0.9430** | **0.9001** | **5.84%** | **0.8608** | 0.4444 |

음수 문자 감소는 oracle보다 문자가 더 많다는 뜻이다. 특히 overlap의 문자 증가는 정확도
향상이 아니라 반대 페이지 유입 또는 block 과분할일 가능성이 있다.

### LabelMe mask 지표

| extraction | mean own recall | min own recall | mean opposite inclusion |
|---|---:|---:|---:|
| overlap | 0.998314 | 0.996507 | 0.113829 |
| seam-confirmed | 0.996449 | 0.993717 | 0.001587 |
| seam-conservative | 0.996991 | 0.994046 | 0.005163 |

seam-conservative는 overlap의 평균 반대 페이지 유입을 약 11.38%에서 0.52%로 줄이면서
평균 99.70%의 자기 페이지 mask recall을 유지했다.

### 반복 촬영 `174943` ↔ `174953`

| extraction | mean text similarity | mean node sequence similarity |
|---|---:|---:|
| oracle | 0.9529 | 0.9366 |
| overlap | 0.6309 | **0.9317** |
| seam-confirmed | **0.9451** | 0.9000 |
| seam-conservative | 0.9289 | 0.7500 |

seam-conservative의 text 안정성은 overlap보다 높았지만 node sequence 안정성은 낮았다.
주된 원인은 반복 촬영 왼쪽 면에서 동일 내용이 더 많은 TEXT node로 분할된 사례이며,
해당 pair의 node sequence similarity는 0.5였다. 반대쪽 면은 1.0이었다.

따라서 text 내용은 안정적이어도 구조 분할이 촬영마다 흔들릴 가능성이 남아 있다.

## 6. `174958 right` 구조 관찰

oracle OCR은 회색 전자상거래 표를 TABLE로 인식하고 ㄱ/ㄴ/ㄷ/ㄹ, 선택지, 정답, 해설을
보존했다.

seam-conservative도 해당 block을 TABLE로 유지하고 핵심 문장·정답·해설을 모두 포함했다.
그러나 다음 차이가 있다.

- 첫 `ㄱ` 항목이 `7`로 인식됨
- 선택지 ④가 oracle의 `ㄴ, ㄹ`과 다르게 `ㄴ, ㄷ`으로 인식됨
- oracle 대비 TABLE 1개 감소

overlap 및 seam-confirmed에서는 ㄱ/ㄴ/ㄷ/ㄹ이 `7`, `L`, `C`, `2` 등으로 더 많이
오인식되거나 표가 다수 TEXT block으로 분해됐다.

이 관찰은 seam-conservative가 상대적으로 유망함을 보여주지만, oracle OCR 자체가
사람이 검증한 정답은 아니다. 정확도 개선 근거로 사용할 수 없다.

## 7. 최종 gate 판정

| 기준 | 결과 |
|---|---|
| Phase A 32건 complete | 통과 |
| schema 32/32 valid | 통과 |
| seam-conservative 문자 감소 ≤20% | 통과 |
| overlap 대비 반대 페이지 유입 감소 | 통과 |
| 반복 촬영 text 안정성 ≥ overlap | 통과 |
| 반복 촬영 node 안정성 ≥ overlap | **미통과** |
| manual golden transcription | **미검증** |

따라서 최종 판정은 다음과 같다.

```text
EXTRACTION_INCONCLUSIVE_NO_GROUND_TRUTH
```

`seam-conservative`는 후속 검토의 선두 후보지만 `SEAM_OCR_CANDIDATE` 또는 production
기본값으로 승격하지 않는다. 기존 overlap도 OCR 정확도가 우수하다고 판정하지 않는다.

## 8. Golden ROI

- capture/side: `20260826_174958 right`
- full-frame ROI: `[2090, 1260, 1120, 720]`
- variant: raw/oracle/overlap/seam-confirmed/seam-conservative
- contact sheet 육안 범위 확인 완료
- 상태: `MANUAL_GOLDEN_NOT_VERIFIED`

manifest의 transcription, 존재 여부, reviewer, reviewed_at은 모두 null이다. 기존 OCR을
정답으로 복사하지 않았다.

## 9. 구현 및 검증

추가/보완된 도구:

- `audit_paired_ocr_environment.py`
- `prepare_paired_golden_roi.py`
- `evaluate_phase_a_pilot.py`
- `evaluate_phase_a_full.py`
- `run_paired_ocr_input_experiment.py`의 `--capture-side`, `--artifact-id`

환경 audit, smoke, pilot, full evaluation JSON을 Git 제외 경로에 보존했다.

session loop, transmit client, Document Parser production source는 수정하지 않았다. TTS,
datapack, 외부 전송도 실행하지 않았다.

- 전체 `book-scanner/tests`: **113 passed**
- `compileall`: 통과
- `git diff --check`: 통과 (Windows CRLF 변환 warning만 존재)

## 10. 산출물

`experiment_outputs/paired_ocr_execution_recovery_20260830/`

- `environment_audit.json`
- `phase_a_pilot_gate.json`
- `phase_a_full_evaluation.json`
- `golden_roi_174958_right/golden_roi_manifest.json`
- `golden_roi_174958_right/contact_sheet.png`

전체 Page IR과 최종 summary:

- `experiment_outputs/paired_ocr_20260830/extraction_gpu_0_ocr_summary.json`
- `experiment_outputs/paired_ocr_20260830/ocr/extraction/*.json`

## 11. 다음 작업

우선순위는 다음과 같다.

1. `174958 right` golden ROI를 사람이 검수하여 정확한 항목/선택지 transcription 입력
2. `174943/174953 left`의 node 과분할 차이를 block bbox와 원문 기준으로 진단
3. 위 두 결과로 seam-conservative를 채택할지, seam-confirmed 또는 overlap fallback을
   유지할지 결정
4. extraction 결정 후에만 Phase B coarse/UVDoc OCR 비교 진행

페이지 검출 학습이나 후보정 확대보다 이 두 불확실성을 먼저 해소해야 한다.
