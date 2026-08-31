# Scanner Video V3-A.2 구현·실험 보고서

상태: **corrected backend 후보 구현 / preview temporal gate 실패 / production 선발 보류**  
실행일: 2026-08-31

## 결론

기존 OpenCV dependency만으로 실행되는 71,718-byte digits-only ONNX 모델과 hash-pinned
`cv2.dnn` recognizer를 구현했다. p30의 사람이 확인한 corrected 왼쪽 라벨은 4/4 exact였고,
모델 load·지연·메모리 budget도 PC에서 충족했다. 그러나 1920px spread preview에서는 footer
숫자가 약 12px 높이로 축소되며 인접 숫자가 한 connected component로 합쳐졌다. 보수적인
variant 합의 때문에 clean anchor 720·780·2220은 모두 complete key가 되지 않았고, 세 cadence
중 page-number consensus가 `PAGE_CHANGED`를 낸 경우는 0건이었다.

따라서 이 backend는 **corrected artifact 진단 후보**이지 Scanner production page-number
provider로 선발하지 않는다. 기존 visual identity fallback, `validated=false`,
`allow_number_only_duplicate=false`와 명시적 provider 주입을 그대로 유지한다. 서버·Coordinator·
Document Parser·전송 계약은 변경하지 않았다.

## 구현 범위

- 결정론적 synthetic glyph generator와 split/폰트/license manifest
- 0~9 tiny CNN 학습 도구, ONNX export 및 OpenCV DNN parity 검사
- local model path와 expected SHA-256를 모두 요구하는 persistent recognizer
- corrected ROI의 반대 페이지 띠를 고려한 glyph-height 우선 숫자열 선택
- 저해상도에서 붙은 component의 제한적 projection split
- adaptive raw와 scale-dependent morphology 두 variant의 합의
- corrected·preview·hard-negative 동일 runner
- accepted corrected artifact key로 arm하는 500/750/1000ms visual/number fusion replay

학습용 PyTorch·ONNX는 production import graph나 `pyproject.toml` dependency에 추가하지 않았다.
ONNX export 패키지는 `tmp/page-number-training-deps`에만 격리했고 runtime은 기존 OpenCV/NumPy만
사용한다. runtime model download 경로는 없다.

## 자료 및 모델 provenance

Synthetic dataset은 seed `20260831`로 생성했다.

- train: 12,000 glyph, DejaVu Sans / Liberation Sans / Ubuntu / Noto Sans KR
- validation: 3,000 glyph, Source Code Pro / Inconsolata
- font-family overlap: 0
- font 파일은 재배포하지 않고 이름, license, SHA-256만 기록
- augmentation: 회전·크기·이동·shear·blur·JPEG·형태학·salt/pepper
- synthetic validation best accuracy: 0.9680
- 모델: `conv12-conv24-conv32-maxpool-linear10`, 17,370 parameters
- 모델 크기: 71,718 bytes
- 모델 SHA-256: `729dd868d622a28a9486d7edccc7351cc5ca8e995e4ca5dfe1e96efb47837c4c`
- ONNX/OpenCV argmax parity: 128/128
- 최대 logit 절대 오차: `1.52587890625e-05`

Synthetic 수치는 실제 페이지 정확도 근거로 승격하지 않았다.

## Corrected 평가

`seam-conservative + UVDoc bilinear` 결과 다섯 spread를 평가했다.

| 자료 | 왼쪽 | 오른쪽 | spread 상태 |
|---|---|---|---|
| p30 정적 capture 1 | `30`, observed | `309`, observed | complete |
| p30 정적 capture 2 | `30`, observed | `309`, conflict | conflict |
| p30 정적 capture 3 | `30`, observed | `309`, conflict | conflict |
| 영상 frame 780 | `30`, observed | `309`, observed | complete |
| 영상 frame 2220 | `316`, conflict | `317`, observed | conflict |

사람이 golden으로 확인한 것은 p30 왼쪽이다. 정적 세 장과 영상 frame 780의 왼쪽은 4/4
exact였다. 오른쪽 `309` 및 `316/317`은 여전히 diagnostic이며 golden 분모로 넣지 않았다.
variant conflict의 raw text가 맞더라도 complete key로 승격하지 않았다.

Frame 2220 corrected 왼쪽에는 seam-conservative가 보존한 이전 p30 페이지의 좁은 띠가 있다.
단순 outermost-first는 그 띠의 `30`을 선택했으나, 실제 페이지의 `316` glyph가 더 크다는 고정
구도 신호로 후보 순위를 보완했다. 이는 crop을 덜 보수적으로 바꾼 것이 아니며 본문 보존 정책도
변경하지 않는다.

## Preview anchor 평가

원본 4K frame과 기존 mask를 최대 1920px로 투영한 실제 결과다.

| frame | 사람 상태 | raw left/right | spread 상태 |
|---:|---|---|---|
| 720 | CLEAN_TRANSFERABLE | `30` / `303` | conflict |
| 780 | CLEAN_TRANSFERABLE | `33` / `1` | conflict |
| 2220 | CLEAN_TRANSFERABLE | `313` / `313` | conflict |

complete wrong key는 0건이지만 complete correct key도 0건이다. 이는 성공이 아니라 conservative
abstention이다. 사용자 확정 negative 9개(손 가림 7, 페이지 이동 2)는 기존 edge-chroma hard
gate에서 recognizer 호출 전 모두 제외됐고, negative anchor recognizer call은 0이었다.

Synthetic footer-year, chapter-number, text-only probe에서도 high-confidence complete는 0건이었다.
실제 unlabeled footer 전체에 대한 false positive 근거로 일반화하지 않는다.

## PC 성능

동일 프로세스에서 corrected 양쪽 한 spread 단위 warm latency를 100회 관찰했다.

- cold load: 6.451 ms
- warm spread median: 9.514 ms
- warm spread observed p95: 10.466 ms
- 750ms 기준 p95 duty cycle: 1.396%
- load RSS 증가: 약 3.1 MiB
- warm RSS 증가: 약 11.4 MiB
- model load count: 1
- runtime download: 0

PC prototype budget인 median 50ms, p95 100ms, cold 1,000ms, model 2MiB, RSS 75MiB 이하는
충족했다. Raspberry Pi 4는 `NOT_MEASURED`이며 이 수치를 Pi 성능으로 해석하지 않는다.

## Temporal replay

원본은 SHA-256
`16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`,
3840×2160, 59.699650767 fps, 2,677 frame이다. Frame 780의 accepted corrected artifact가
complete `30/309` key를 제공하므로, 실제 엔진과 같이 corrected key를 baseline으로 arm했다.

| cadence | baseline | false release | transition 뒤 release | 근거 | page-number release |
|---:|---|---:|---:|---|---:|
| 500ms | complete `30/309` | 0 | 1, frame 2220 | visual fallback | 0 |
| 750ms | complete `30/309` | 0 | 0 | 없음 | 0 |
| 1000ms | complete `30/309` | 0 | 0 | 없음 | 0 |

500ms의 frame 2220 release는 3-sample visual gate 결과이지 숫자 인식 성공이 아니다. 진단용
transition envelope 끝에서 1,507.55ms 뒤였지만 그 경계 자체가 사람 확인값이 아니므로 정식
latency로 승격하지 않는다. 세 cadence 모두 사용자 negative anchor의 number stable-count 증가는
0이었다.

750ms에서 unlabeled frame 1665가 한 번 `312/313` complete로 관찰됐으나 연속 합의가 없어 release는
없었다. 정답 라벨이 없으므로 이를 정확 또는 오인으로 단정하지 않는다. 이 관찰과 clean anchor
abstention 때문에 cadence 기본값을 변경하지 않는다.

## 실패 원인과 다음 경계

per-glyph classifier 자체보다 preview component segmentation이 병목이다. corrected 숫자는 23~31px
높이로 분리되지만 preview에서는 약 12px이며 `30`이 한 덩어리가 된다. projection split을 제한적으로
추가했지만 morphology variant 사이에서 `0/3`, `6/8`이 불안정했다. confidence threshold를 낮추거나
variant 합의를 1로 줄이면 wrong-complete 위험이 커지므로 적용하지 않았다.

다음 실험은 패킷의 조건부 후보였던 작은 digits-only CRNN/CTC ONNX를 tight sequence crop에
적용하는 것이 우선이다. classifier와 같은 ROI locator를 유지하고 glyph 분할만 제거해야 한다.
그 전에 필요한 사람 검수는 p316/p317 좌우 번호와 p30→p316 stable-run 경계다. 이 둘 없이
different-page same-key와 release delay를 production gate로 평가할 수 없다.

대안으로 page number를 corrected artifact 이후 진단·서버 멱등 보조에만 사용하는 설계는 가능하지만,
UVDoc 이전의 Scanner 중복 억제 속도 문제는 해결하지 못한다. 번호-only suppression 활성화는 별도
승인 전까지 금지한다.

## 검증

- Book Scanner 전체: **236 passed**
- focused page-number + V3-A.1 engine: **13 passed**
- model hash mismatch 및 missing asset 실패 검증
- model load 1, 10개 digit smoke, bounded cache 기존 회귀 통과
- Document Parser import/call: 본 패킷 runner에서 0
- 서버/API/Coordinator 변경: 0

## 산출물

- `models/page_number_digit_v1.onnx`
- `experiment_inputs/scanner_video_v3a2_synthetic_dataset_manifest.json`
- `experiment_inputs/scanner_video_v3a2_model_manifest.json`
- `experiment_inputs/scanner_video_v3a2_temporal_labels.json`
- `experiment_outputs/scanner_video_v3a2_20260831/backend_evaluation.json`
- `experiment_outputs/scanner_video_v3a2_20260831/temporal_replay_750.json`
- `experiment_outputs/scanner_video_v3a2_20260831/temporal_replay_500_1000.json`
- `experiment_outputs/scanner_video_v3a2_20260831/temporal_replay_summary.json`

최종 판정은 `CORRECTED_CANDIDATE_PREVIEW_TEMPORAL_FAIL`이다. 구현은 완료됐지만 V3-A.2
production 선발 gate는 통과하지 않았다.
