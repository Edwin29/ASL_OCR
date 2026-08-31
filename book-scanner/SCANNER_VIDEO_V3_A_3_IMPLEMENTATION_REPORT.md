# Scanner Video V3-A.3 구현·실험 보고서

상태: **Paddle recognition-only 후보 유지 / 750ms VisualGate 가치 gate 실패 / production 선발 보류**
실행일: 2026-08-31

## 결론

로컬 `en_PP-OCRv5_mobile_rec`을 좌우 bottom ROI에만 적용하는 persistent Paddle backend와,
`EVERY_ELIGIBLE`·`VISUAL_TRIGGERED`·`HYBRID_AUDITED` 호출 scheduler를 구현했다. 기존 VisualGate는
OCR 호출을 줄이지 않고 candidate-eligible 표본마다 provider를 호출한다는 사실도 코드와 계측으로
확정했다. V3-A.3의 기본 scheduler mode는 기존 의미를 보존하는 `EVERY_ELIGIBLE`이며 VisualGate
mode는 명시적 opt-in이다.

동일 영상의 Paddle 결과를 frozen observation으로 고정해 비교한 결과, 현재 기본 750ms에서
VisualGate는 eligible 9건 중 2건만 줄여 추가 억제율이 **22.2%**였다. 사전에 고정한 30% 가치
gate를 통과하지 못했고, `EVERY_ELIGIBLE`과 VisualGate 모두 새 페이지 complete key를 3회 연속
얻지 못해 release가 0건이었다. Hybrid audit도 네 번 연속 visual-same eligible 표본이 없어 audit
호출이 0건이었으므로 별도의 안전성 이득을 증명하지 못했다.

500ms 진단에서는 VisualGate가 8건 중 3건을 줄여 **37.5%**를 절감했고, 기준선과 동일하게 frame
2220에서 `316/317` 세 번 합의로 release 1회를 만들었다. 그러나 `316/317`과 stable-run 경계는
사람 golden이 아니며 cadence 변경도 승인되지 않았다. 따라서 500ms 결과를 production 통과로
승격하지 않는다.

최종 상태는 `PROVISIONAL_VISUAL_GATE_VALUE_FAIL_AT_DEFAULT_CADENCE`다. Paddle은 page-number
recognition 후보로 남지만 기본 composition으로 선발하지 않는다. `validated=false`,
`allow_number_only_duplicate=false`, page-number provider 명시 주입 및 기존 visual fallback을 유지한다.

## 구현 범위

- `PageNumberSchedulerMode`와 provisional `PageNumberSchedulerPolicy`
- provider 호출 전 `PageNumberVerificationScheduler`
  - `EVERY_ELIGIBLE`
  - `VISUAL_TRIGGERED`
  - `HYBRID_AUDITED`
  - bounded verification burst와 timeout
- hard-gate, eligible, visual 분류, spread request, audit, burst를 분리한 engine diagnostics
- 모든 표본의 scheduler request/skip 이유를 남기는 구조화 event
- session start, delivery confirm/reject, source exhaustion, page release, cancel/error의 scheduler reset
- Paddle model의 5개 asset SHA-256 검증, explicit device, session당 load 1
- CPU/GPU frozen observation capture와 paired policy replay
- spread request와 좌우 ROI call, baseline, exact cache hit가 섞이지 않는 집계

Document Parser, PaddleOCR-VL layout pipeline, HTTP/server, Coordinator, crop/UVDoc 및 delivery 의미는
변경하지 않았다. Paddle/PaddleOCR도 `pyproject.toml` production dependency에 추가하지 않았다.

## 자료와 실행 경계

- 원본: `20260830_133526.mp4`
- SHA-256: `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
- 3840×2160, 2,677 frames, 59.699650767fps
- accepted corrected baseline: `30/309` complete
- 사용자 확인 clean anchor: 720, 780, 2220
- 사용자 확인 손 가림: 900, 1170, 1380, 1920, 1980, 2400, 2580
- 사용자 확인 page moving: 1500, 2040

왼쪽 p30은 golden이다. 오른쪽 `309`, 새 spread의 `316/317`, 두 stable-run 경계는 진단 label이며
사람이 명시적으로 확인하지 않았다. 따라서 different-page 정확도, 정식 release recall 및 지연은
production gate로 사용할 수 없다.

## 계측 계약 수정 결과

V3-A.2의 `recognizer_calls`는 baseline 전·후 좌우 ROI 실행과 accepted corrected baseline을 함께
세어 표본 수와 직접 비교할 수 없었다. V3-A.3은 다음을 독립 count로 고정했다.

- sampled spread
- candidate hard-gate rejection
- eligible spread
- visual same/changed/ambiguous/error
- Paddle requested/completed spread
- physical side-ROI call과 exact cache hit
- verification burst, audit, timeout

Capture 전체 구간의 candidate hard-gate 결과는 다음과 같다.

| cadence | sampled | hard rejected | eligible | hard-gate rejection |
|---:|---:|---:|---:|---:|
| 500ms | 66 | 54 | 12 | 81.8% |
| 750ms | 44 | 34 | 10 | 77.3% |
| 1000ms | 33 | 28 | 5 | 84.8% |
| 1500ms | 22 | 16 | 6 | 72.7% |

이는 CandidateGate의 결과이지 VisualGate 절감률이 아니다. 제외율이 높아 Paddle 비용은 이미 크게
제한되지만, 새 페이지에서 연속 complete key를 모을 기회도 함께 적어진다.

## 정책 replay 결과

정책 비교는 accepted baseline 이후 동일 frozen Paddle observation을 사용했다. 500ms는 release에서
engine이 search로 전환한다고 보고 그 시점에 replay를 종료했기 때문에 표본 수가 capture 전체보다
작다.

| cadence | policy | eligible | Paddle request | Visual 추가 억제 | release | 근거 |
|---:|---|---:|---:|---:|---:|---|
| 500ms | every eligible | 8 | 8 | 0% | 1 @2220 | number consensus |
| 500ms | visual triggered | 8 | 5 | 37.5% | 1 @2220 | number consensus |
| 500ms | hybrid audited | 8 | 5 | 37.5% | 1 @2220 | number consensus |
| 750ms | every eligible | 9 | 9 | 0% | 0 | K=3 미달 |
| 750ms | visual triggered | 9 | 7 | 22.2% | 0 | 가치 gate 미달 |
| 750ms | hybrid audited | 9 | 7 | 22.2% | 0 | audit 0회 |
| 1000ms | every eligible | 4 | 4 | 0% | 0 | K=3 미달 |
| 1000ms | visual triggered | 4 | 3 | 25.0% | 0 | 가치 gate 미달 |
| 1500ms | low-rate control | 5 | 5 | 0% | 0 | K=3 미달 |

500ms VisualGate burst는 frame 1860과 2160에서 두 번 시작했고 두 번째만 release로 이어져
관찰된 useful-trigger precision은 50%다. 750ms에서는 1665, 1890, 2160, 2610에서 네 burst가
시작됐지만 release로 이어진 burst가 없었다. 이 결과는 VisualGate가 기본 cadence에서 Paddle
호출을 충분히 희소화하지 못한다는 판단을 지지한다.

사용자 확인 손·이동 anchor의 number consensus 증가는 모든 정책에서 0이었고 p30 진단 stable
window의 false release도 0이었다. 작은 단일 영상 결과를 일반적인 false-release 보장으로
확대하지 않는다.

## Paddle 결과와 리소스

모델 asset은 8,012,929 bytes이며 5개 파일 hash를 모두 검증했다. runtime model download는 0,
load count는 CPU/GPU 각각 1이다.

| 항목 | CPU | GPU:0 |
|---|---:|---:|
| cold load | 2,345.0ms | 2,453.5ms |
| RSS load delta | 211,968,000 bytes | 518,144,000 bytes |
| baseline corrected spread | 319.7ms | 405.8ms |
| 500ms preview median | 82.25ms | 61.87ms |
| 500ms preview observed p95/max | 126.49ms | 192.86ms |

CPU/GPU의 500/750ms eligible observation 22건은 complete/partial/conflict와 key가 모두 같아 mismatch
0이었다. 다만 현재 GPU 환경은 Paddle build cuDNN 9.9와 시스템 cuDNN 9.5 불일치 경고를 냈다.
GPU 수치는 진단값이며 배포 권고가 아니다. 이 작은 ROI workload에서는 GPU가 CPU보다 일관되게
낫다고 볼 근거도 없다.

750ms에서 CPU observed p95 137.56ms는 sampling 간격의 약 18.3%이고 GPU 187.66ms는 약 25.0%로
패킷의 40% duty budget 안이다. 다만 750ms/1000ms/1500ms에는 앞 cadence에서 얻은 exact ROI cache
hit가 포함되므로 순수 물리 추론 대표값은 cache hit 0인 500ms 결과를 우선 본다.

Raspberry Pi 4는 `NOT_MEASURED`다. PC의 load/RSS/latency를 Pi 성능으로 해석하지 않는다.

## 검증

- focused scheduler/config/page-number/engine: **33 passed**
- 전체 `tests/unit/video`: **122 passed**
- 전체 Book Scanner: **242 passed, 4 skipped**
- Paddle CPU/GPU output parity: **22 observations, mismatch 0**
- model asset mismatch/path escape: load 전 실패
- provider 없는 기본 구성: Paddle import/call 0
- Document Parser import/call: V3-A.3 runner에서 0
- HTTP/server/Coordinator 변경: 0

## 산출물

- `experiment_inputs/scanner_video_v3a3_paddle_model_manifest.json`
- `experiment_outputs/scanner_video_v3a3_20260831/frozen_paddle_observations_cpu.json`
- `experiment_outputs/scanner_video_v3a3_20260831/frozen_paddle_observations_gpu.json`
- `experiment_outputs/scanner_video_v3a3_20260831/scheduler_replay_cpu.json`
- `experiment_outputs/scanner_video_v3a3_20260831/summary.json`
- `tools/run_scanner_video_v3a3_paddle_capture.py`
- `tools/run_scanner_video_v3a3_scheduler_replay.py`
- `tools/summarize_scanner_video_v3a3_value.py`

## 남은 경계와 다음 판단

현재 증거만으로는 VisualGate를 Paddle 호출 절감의 기본 전제로 둘 이유가 충분하지 않다. 기본
750ms에서는 `EVERY_ELIGIBLE`을 유지하되 page-number provider 자체는 계속 opt-in으로 둔다.
Paddle 정확도 후보를 production으로 평가하려면 최소한 다음이 필요하다.

1. `316/317` 좌우 번호와 stable-run 경계의 사람 확인
2. 서로 다른 spread를 포함한 추가 영상에서 wrong-complete와 false-same 평가
3. K=3과 candidate eligibility/cadence의 결합으로 page turn을 놓치는 문제를 별도 패킷에서 검토
4. Pi 4 실제 CPU latency/RSS 측정

K를 2로 낮추거나 500ms를 기본으로 바꾸는 것은 이번 결과만으로 자동 수행하지 않는다. 두 변경은
false release와 duty cycle을 바꾸므로 별도 승인과 held-out replay가 필요하다.
