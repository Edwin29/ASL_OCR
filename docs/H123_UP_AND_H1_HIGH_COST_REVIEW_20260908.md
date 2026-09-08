# H1 및 physical UP 독립 고비용 검토 — 2026-09-08

상태: **read-only investigation 완료 / product source modification 0 / integration ready 아님**

범위는 fresh H1 page-change liveness, 현재 aligned firmware의 UP 무응답, 그리고 그 두 경로에 직접 인접한 lifecycle/test gap으로 제한했다. Camera threshold, production 8초 값, FRAME/V3, UART IRQ 구조, servo mapping/LUT, authentication/TLS는 변경하지 않았다.

## 1. 판정 요약

| 항목 | 분류 / severity | first failing boundary | 결론 |
|---|---|---|---|
| 현재 aligned firmware UP 3회 무응답 | `insufficient_evidence / P1` | physical actuation → PA0 sampled/debounced LOW → `UP STEP` | 현재 run에는 UP debug/NAV가 없다. 보존된 H0·pre-IRQ·aligned source의 PA0/init/debounce는 같고 과거 H3 raw log에는 UP 성공이 있어 source regression이나 영구 wiring failure 중 하나로 확정할 수 없다. |
| UP recheck harness packet cap | `test_harness_artifact / P1` | required unique UP 3개 → total NAV cap | boot/reset mode NAV 2개와 total cap 4 조합은 성공해도 UP 3개를 모두 기록할 수 없다. 기존 zero-UP 원인은 아니지만 3/3 수용을 불가능하게 한다. |
| UP recheck readiness marker | `test_harness_artifact / P1` | port open → handshake-complete observation window | `ready`가 final HELLO3와 initial-mode ACK보다 약 13초 빠르다. 연결 전 short press 유실 가능성이 있다. 이번 사용자 조작이 reset 뒤였으므로 incident root로는 확정하지 않는다. |
| Fresh H1 page-change | `probable_product_risk / P1`, runtime profile incompatibility와 reset mechanism 재현 | `WAITING_FOR_PAGE_CHANGE` opaque identity admission → `PAGE_CHANGED` | N5/K1/K0/8000ms 그대로 slow exact stream과 recorded timing을 실제 engine에 주입했을 때 timeout별 partial observation 폐기와 무진전을 재현했다. 원 run의 valid=5 UNKNOWN/SAME까지 설명하려면 raw pair/reference bank가 더 필요하다. |
| Opaque SAME 뒤 stale visual latch | `confirmed_product_defect / P1`, **local correction PASS** | SAME identity → visual evidence invalidation | 과거 visual-change latch가 SAME 이후 남아 후속 일관된 OCR 오인식과 결합해 false `PAGE_CHANGED`를 만들 수 있었다. SAME에서 latch 폐기와 baseline re-arm을 적용했다. H1 incident의 직접 원인으로는 연결하지 않는다. |
| close 뒤 late preparation cleanup | `confirmed_product_defect / P1`, **local correction PASS** | engine ownership close → late preparation result disposal | post-close poll 없이 late success/exception staging을 once-only 폐기하도록 engine-owned completion callback을 적용했다. Fresh H1 page-change first cause는 아니다. |
| synchronous footer OCR input blocking | `probable_product_risk / P1` | DeviceApplication/engine poll lock → native footer inference | provider가 막히면 cancel과 camera stop도 같은 lock 뒤에서 대기한다. 실제 사용자 지연의 상한은 아직 미측정이다. |
| page-number recognizer unused inference | `probable_product_risk / P1` | candidate localization → variant inference | 첫 valid 결과를 반환하면서도 후속 후보를 모두 추론한다. 실제 latency 절감과 output/exception 동등성 검증 전 수정하지 않는다. |

## 2. Physical UP evidence와 버전 비교

현재 recheck는 final reset의 HELLO3, initial mode 및 ACK가 끝난 뒤에도 종료 시점까지 `UP STEP`과 `NAV,U,S`가 없었다. FRAME은 전송하지 않았고 COM5/COM9 오류나 후속 reset도 없었다. Host routing, ACK 또는 PCA blocking은 이 run의 first cause가 아니다.

보존된 firmware identity 비교 결과는 다음과 같다.

- H0 `main.c`: SHA-256 `064afa1d024506fc145acb4cea0d66111ec685e390d2473965ae87a434bbf27a`
- H0 ELF: SHA-256 `62ecee2ccc811cf046466d38e80001f959f27a6f256f803903769289b9556c05`
- current Desktop/Laptop/aligned `main.c`: SHA-256 `f0b93413f352be398dac62db6a64b2d17c19f1b8e14faf874371beddaf6ba1c1`

H0와 current의 `ButtonPollStep`, `ButtonPollConfirm`, `ButtonPollEdge`, `ModeLeverPoll`, `MX_GPIO_Init`, `.ioc`, HAL MSP는 UP 경계에서 동일하다. Current contract는 `main.h`의 PA0, `main.c`의 active-low 30ms debounce, PA0 input/pull-up, 그리고 `UP STEP`을 `SendControlAction('U','S')`보다 먼저 출력하는 순서다.

과거 H3 raw COM5 log에는 여러 `UP STEP → NAV,U,S → ACK`가 존재한다. PAGE NEXT도 최소 한 번 `PAGE NEXT STEP → NAV,N,S,19`까지 도달했으나 ACK를 받지 못하고 reconnect했다. 따라서 기존 H3 보고서의 PAGE NEXT가 항상 GPIO/debug/NAV 이전에 실패했다는 표현은 trial별로 한정해야 한다. Physical label과 trace timestamp의 직접 결합이 없으므로 PAGE NEXT wiring PASS로 승격하지 않는다.

남은 competing hypotheses는 PA0 접촉·배선의 간헐성, 실제 press LOW 시간, observation window, main-loop sampling이다. 현재 확보한 source 사이의 pin/init regression은 반증 방향이며, 별도의 비보존 과거 파일까지 반증한 것은 아니다. 다음에는 production source를 바꾸기 전에 harness를 고치고, 계속 실패할 때 PA0 raw level/IDR·MODER·PUPDR와 poll heartbeat를 비침습적으로 계측한다.

## 3. Fresh H1 independent replay

실제 `SampledFrameEngine`과 collector에 fake camera/analyzer/provider 및 manual clock을 주입했다. N=5, `k_same=1`, `k_different=0`, `max_collection_ms=8000`을 유지했다.

| 입력 | 결과 |
|---|---|
| 저장된 native 진단의 elapsed/raw/status 11행 | 8.007초 N1 UNKNOWN → 19.210초 N4 UNKNOWN → 27.219초 N2 UNKNOWN, `PAGE_CHANGED=0` |
| exact `28|29`가 2.05초마다 계속 도착 | 8.02/16.04/24.06/32.08초마다 N4 UNKNOWN reset, `PAGE_CHANGED=0` |
| 서로 다른 incorrect pair 5개 | majority가 없어 N5 UNKNOWN |
| accepted reference와 같은 pair | N1 SAME, collector restart |
| 다섯 번째 sample이 deadline 직전에 시작해 직후 완료 | 약 8.5초 N5 DIFFERENT 및 `PAGE_CHANGED`; deadline은 sample-start 기준 soft deadline |

따라서 문제는 “모든 OCR이 8초 안에 끝나지 않아서”보다 구체적이다. `engine.py`는 sampling 전에 deadline을 검사하고 partial collector를 폐기한다. 실측 cadence가 2초 안팎이면 안정된 exact pair도 각 attempt에서 N4로 나뉘어 영구히 N5에 도달하지 못한다.

Fresh H1에서는 sequence 1 durable receipt 뒤 이 경계가 sequence 2 artifact, receipt, finalize 및 fresh READY를 막았다. Camera acquisition/decode, candidate eligibility의 후반 구간, production-native `28|29` 반복 인식, V4 sequence 1 receipt와 guidance audio는 관측됐으므로 first cause에서 제외한다.

원 run의 한 attempt는 valid 5인데 UNKNOWN이었고 다른 attempt에는 SAME이 있었다. `valid_observations`는 정확한 숫자 합의라는 뜻이 아니며, 양쪽 raw text가 있는 conflict pair도 포함한다. 그 attempt의 raw pairs와 accepted reference bank가 보존되지 않아 전체 incident를 단일 timeout defect로 확정하지 않는다.

## 4. 인접한 confirmed defect와 risk

### 4.1 Opaque visual latch invalidation

Reachable trigger는 accepted reference 뒤 일시적 visual change가 stable count를 채우고, footer identity가 SAME으로 복귀한 다음, 같은 spread에서 안정된 다른 OCR pair가 N5를 채우는 순서다. Opaque SAME branch는 collector만 재시작하고 `_opaque_visual_page_changed`와 visual gate를 초기화하지 않는다.

실제 engine replay에서 current visual은 baseline/eligible false인데 과거 latch를 사용해 false `PAGE_CHANGED`와 SEARCHING 전이를 만들었다. 위반 invariant는 SAME으로 확인된 시점 이전의 visual evidence가 이후 identity attempt를 승인해서는 안 된다는 것이다. 기존 opaque test는 prior latch 없는 오인식만 다루고, SAME reset 회귀는 non-opaque 경로에만 있다.

Architecture 판정은 `architecture_sound_with_local_defect`다. Threshold와 external event contract를 유지한 채 `engine.py` 한 파일과 targeted test 한 파일에서 evidence epoch를 정리할 수 있다.

### 4.2 Close 뒤 late preparation result

Preparation이 실행 중일 때 adapter freeze/engine close가 ownership을 제거하면 future는 취소되지 않을 수 있다. Late completion 정리는 `_poll_cancelling()`에만 있으나 adapter는 close 뒤 다시 poll하지 않는다. Barrier reproducer에서 late success 뒤 `commits=0`, `discards=0`, `discarded_jobs=0`이었다.

위반 invariant는 engine이 소유한 uncommitted preparation result가 close 뒤 정확히 한 번 폐기돼야 한다는 것이다. 기존 test는 future를 푼 뒤 IDLE까지 계속 poll해 production adapter 경로의 gap을 가린다. `architecture_sound_with_local_defect`로 판정하며 `engine.py` 한 파일과 engine/adapter test 최대 두 파일이 상한이다. 이미 committed artifact는 보존해야 한다.

### 4.3 Synchronous footer OCR와 recognizer work

`engine.poll()`은 lock을 보유한 채 native footer provider를 동기 호출한다. Barrier provider가 150ms 막힌 동안 cross-thread cancel과 camera stop도 끝나지 않았다. 이 메커니즘은 재현됐지만 실제 최악 지연과 native corruption은 나타나지 않았다. Worker/ownership 변경은 local patch로 가정하지 않고 별도 diagnostic/design packet으로 둔다.

Saved native reference-left ROI에는 시각적으로 `26`이 있으나 `_candidate_regions()`는 교재명 쪽 component 하나만 선택해 `2441|27`을 만들었다. 이는 그 frame의 localization miss 증거지만 accepted reference bank 전체 root로 일반화하지 않는다.

Recognizer는 첫 valid 후보가 있어도 뒤 후보의 모든 variant를 추론했다. Spy에서 query 좌4/우3 후보가 총 14 `_predict` 호출을 만들었고 반환에 필요한 첫 후보 두 variant씩은 4회였다. 성능 위험은 구체적이나 early-exit이 result 선택, diagnostic, exception semantics를 보존하는지와 실제 timing 효과를 먼저 측정한다.

## 5. Bounded work packets

### A. 기존 구조를 유지하는 local correction

1. **UP harness correctness** — **적용 완료**, production 0, harness 1.
   - `ports_open`과 `observation_ready`를 분리한다.
   - final HELLO3 + initial mode ACK 뒤 observation epoch를 연다.
   - boot/mode/retry packet과 unique UP success를 별도로 센다.
   - UP 3개를 모두 담을 수 있는 독립 total safety cap을 둔다.
   - PowerShell parse와 invalid `2 HELLO + 3 UP / total cap 4` preflight rejection을 확인했다. 실제 hardware 재수용은 새 observation epoch에서 별도 수행한다.
2. **Opaque stale visual latch** — **적용 및 targeted PASS**, product `engine.py` 1, targeted test 1.
   - SAME 또는 동등한 invalidating boundary에서 이전 visual evidence epoch를 폐기한다.
   - false `PAGE_CHANGED=0`, real page change 유지, reference/receipt ordering을 검증한다.
3. **Late preparation cleanup** — **적용 및 targeted PASS**, product `engine.py` 1, tests 1파일의 2 cases.
   - post-close poll 없이 late success/exception을 정확히 한 번 정리한다.
   - repeated close와 committed artifact 보존을 검사한다.

### B. 추가 계측·설계가 먼저 필요한 packet

1. **H1 liveness replay/design** — product 0, test/tooling 최대 2.
   - slow exact stream, recorded native rows, valid5/no-majority, SAME, missing, hard reject, deadline 전후, visual epoch를 한 suite로 고정한다.
   - first-valid clock만으로는 2.05초 cadence의 N5가 8.2초여서 충분하지 않다.
   - sliding window 또는 readiness/consensus budget 분리를 비교하되 pre-turn evidence 혼입, hard-reject/motion reset, finite operator outcome을 증명한다.
2. **Raw identity observability** — 원 production run에서 hashed/raw-normalized pair, status, reference-bank identity와 attempt epoch를 credential 없이 보존한다.
3. **Synchronous footer scheduling** — blocked provider 중 input arrival→dispatch→cancel→camera stop 시간을 측정한다. Worker ownership과 late result fencing이 필요하면 architecture change로 별도 승인한다.
4. **Recognizer inference cost** — exact output/diagnostic/exception equivalence와 native timing을 측정한 뒤에만 one-file optimization 후보로 승격한다.
5. **Physical UP boundary** — corrected harness에서 재현 후 PA0 IDR/MODER/PUPDR, LOW duration, poll heartbeat와 continuity를 확인한다. Pin mapping 수정 근거는 아직 없다.

## 6. 검증 순서와 demo 영향

1. UP harness correction과 deterministic harness test.
2. H1 recorded engine replay 및 stale-latch regression 고정.
3. Stale latch와 late-result cleanup local correction, affected Scanner/Device adapter tests.
4. Replay가 선택한 H1 liveness correction; 필요 시 별도 architecture 승인.
5. Targeted suite → Scanner/Device subsystem → final identity G3-A.
6. Fresh H1 1회, 실패 시 동일 계측으로 bounded repeat 최대 1회. receipt 2개, fragments 4개, CONFIRM LONG, fresh READY가 모두 필요하다.
7. Hardware team 정렬·controls 수리 뒤 fresh H2와 H3를 같은 final identity에서 각각 수행한다.
8. Fresh H1/H2/H3와 final G3-A가 모두 통과한 뒤 H4 전체 경로를 한 번 수용한다.

현재 H1 sequence 2/fresh READY, physical CLEAR, UP/CONFIRM/MODE controls가 닫히지 않았다. 따라서 H4 진입은 계속 **BLOCKED**다.

## 7. Evidence

- Fresh H1 run: `docs/H1_CAMERA_FRESH_RUN_20260908.md`
- Fresh H1 liveness summary: `docs/evidence/h1-camera-fresh-20260908-101447/footer-liveness-analysis.json`
- Actual-engine replay script/result: `docs/evidence/h1-up-high-cost-20260908/replay_h1_liveness.py`, `docs/evidence/h1-up-high-cost-20260908/result.json`
- UP harness correction result: `docs/evidence/h1-up-high-cost-20260908/up-harness-correction-result.json`
- Local correction result: `docs/H1_UP_FOLLOWUP_IMPLEMENTATION_RESULT_20260908.md`
- Current UP recheck: `docs/evidence/h23-1c-20260908/irq-aligned-build-20260908-202007/runs/physical-up-recheck`
- Historical H3 COM5 trace: `docs/evidence/independent-diagnostic-20260908/raw/h3-20260908-001800/logs/stm-com5-trace.log`, SHA-256 `326fd30aaf6b584be9d80aae14c634a7b4e7a5263b4bf204d2b697edc79bd755`
- Firmware/serial/physical status: `docs/H2_H3_FIRMWARE_SERIAL_PHYSICAL_STATUS_20260908.md`

이번 독립 조사에서 product source modification count는 **0**이다.
