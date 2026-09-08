# H1/H2/H3 diagnosis + architecture assurance 기반 작업 우선순위

작성일: 2026-09-08. 상태: **작업 정리·우선순위 제안. Product 구현0. H4 BLOCKED 유지.**

근거는 [독립 진단](H1_H2_H3_SOFTWARE_DIAGNOSTIC_RESULT_20260908.md), [critical-path architecture assurance](H123_CRITICAL_PATH_ARCHITECTURE_ASSURANCE_20260908.md), [local correction packets](work-packets/H123_ARCH_LOCAL_CORRECTIONS_20260908.md), [diagnostic/design packets](work-packets/H123_ARCH_DIAGNOSTIC_DESIGN_20260908.md)다. 충돌하는 수정 방향은 더 최근 assurance의 선행 조건을 따른다. 특히 과거 진단의 30초 비교 제안은 production8초 변경 승인이 아니다.

아래 순위는 **작업 착수·의존성 순위**이며 기존 P1/D01 severity를 P0 등으로 올리는 분류가 아니다. 코드 수정, 계측, 실제 hardware 조치는 서로 다른 승인·검증 단위로 유지한다.

## 1. 권장 우선순위

| 순위 | 필요한 작업 | 지금 필요한 행동 | 근거와 우선 이유 | 완료 조건 |
|---|---|---|---|---|
| 선행·소규모 | **T1/T2 + CP-T1: source 확인·fatal 결과·종료 정리** | L-T1/L-T2의 국소 수정 범위 확정 후 구현 승인 단위로 제출 | IP preflight가 webcam을 probe할 수 있고, handled fatal은 CLI0, fatal STOPPED는 connectivity.stop을 생략한다. 후속 시험을 잘못 PASS로 판독할 수 있으므로 먼저 바로잡을 가치가 크다. 다만 기존 raw-evidence 분석/fake 진단을 막는 필수 의존성은 아님 | IP source 실패 시 webcam 호출0, fatal child nonzero, 정상 종료와 구분, fatal 뒤 cleanup exactly once, 원래 failure 보존 |
| **1 — 최우선** | **D-A → A1/A2: native audio lifecycle** | 먼저 stream owner/cancel target/teardown 설계와 native 격리 시험 계획. 설계 확인 뒤 두 모듈 안의 correction | 실제 process AV가 있었고 A1 native-call overlap 및 A2 replacement late-stop은 독립 재현됐다. Python containment로 native AV를 막을 수 없다. 단, 두 crash의 exact root는 미확정이므로 단순 lock patch로 종결 불가 | Current generation을 old stop이 중단하지 않음, native lifetime 중첩·use-after-close0, interruption 유지, worker/stream 종료 확인, 실제 Laptop speaker 재검증 |
| **2 — 최우선** | **L-B: host edge ordering + complete-line acceptance** | 기존 I/O worker 안의 bounded local correction을 독립 packet으로 구현 준비 | Release가 앞 batch, activation이 뒤 batch이면 release 후 hold가 다시 활성화된다. Partial `NAV,D,A,78`에서 seq7을 ACK하는 것도 재현됐다. 필수 physical control semantics를 직접 위반하며 수정 범위와 증거가 명확하다 | 모든 read split에서 원래 seq만 수락, cross-batch A/R·BUSY·reconnect에서 release 후 stale repeat0, V3/FRAME/dedupe 보존 |
| **3 — 최우선 진단** | **D-F: firmware receive / parser / PCA 및 hardware 측정** | 현재 flash identity·rollback 가능성 확인, compiled fixture와 RX/I2C 계측 계획부터 작성. 필요한 실제 시험은 packet/stop/evidence를 먼저 보고 | Normal-rate FRAME 손상이 있고 paced/direct 시험만으로 root를 확정할 수 없다. RX polling gap, HC-05/전원, parser, PCA를 분리해야 한다. Host 수정만으로 내려가는 FRAME 손상을 닫을 수 없음 | First failing boundary 측정, parser reject atomicity·overflow recovery 확인, PCA write 결과와 physical cells 구분. 증거에 따라 local parser patch/수신 구조 설계/hardware 조치로 분기 |
| **4 — 높음** | **D-C → L-C2: live camera liveness·input response·transient recovery** | N=5/8초를 고정한 시간·reset·cancel 계측과 taxonomy 설계. 그 결과에 따라 국소 recovery 또는 제한된 owner 변경 선택 | H1 두 번째 spread 이후 경로가 완성되지 않았고, timeout/401/503가 같은 fatal 경로로 간다. 동기 acquisition은 input/cancel도 지연시킨다. Liveness 원인을 profile, missing/rejected observations, scheduling 중 하나로 아직 확정할 수 없음 | Two-spread 진전, retryable/permanent 분리, finite recovery와 cancel, late result 차단, durable artifact 보존. Input/collection 시간 의미와 실제 관측값을 일치시킴 |
| **5 — 필수 보완** | **L-C3: page-change waiting guidance** | 기존 engine/guidance 경로의 독립 국소 수정 | UNKNOWN/reset 동안 producer가 guidance를 emit하지 않는다. 사용자 침묵을 설명하는 확인 결함이다. 그러나 안내 추가만으로 page-change liveness나 HTTP fatal을 해결하지는 못함 | Bounded cadence 안내, false page-change/receipt/READY0, 정상 회복·cancel 시 reset, 실제 cue playback 확인 |
| **통합 단계** | **Targeted → subsystem → G3-A → fresh H1/H2/H3 → H4** | 각 승인 packet의 evidence를 새 source identity에 연결하고 full acceptance 순차 수행 | Fake tests, 기존 G3-A, V2 physical SHORT, paced FRAME 성공은 서로 다른 경계 증거다. 결과를 합쳐 full pipeline PASS로 간주할 수 없음 | 각 실험의 fidelity와 성공 신호를 분리하고 모든 blocker가 닫힌 후 H4 전체 사용자 경로 통과 |

Audio를 1순위로 두는 이유는 프로세스 생존성과 실제 음성 출력에 걸친 위험 때문이다. Host는 구현 불확실성이 작아 audio 설계를 기다리는 동안 독립적으로 준비할 수 있다. Firmware와 camera는 계측 준비에 장비·사용자 조작이 필요할 수 있으므로 높은 순위 작업과 함께 준비한다. 이 표는 모든 작업을 한 줄로 직렬 처리하거나 하나의 거대한 patch로 합치라는 뜻이 아니다.

## 2. 두 종류의 실행 backlog

### A. 기존 구조를 유지하는 bounded local corrections

| Packet | Product 파일 상한 | 선행 조건 | 경계·주의점 |
|---|---:|---|---|
| L-T1 | 2 | 별도 구조 설계 불필요 | `laptop_acceptance.py` 중심, 필요한 기존 factory 재사용만. Auth/TLS/profile 설정 변경0 |
| L-T2 + CP-T1 | 3 | 별도 supervisor 설계 불필요 | Coordinator terminal outcome/cleanup + Application finally + CLI. Exit code만 바꾸고 종료 누락을 남기지 않음 |
| L-B + CP-H1 | 2 | Serial worker 내 ordered drain/line buffer 설계 검토 | `stm_serial.py`, 필요한 경우 `hold_repeat.py`. V3 release 긴급 처리와 accepted order 모두 유지 |
| L-C3 | 1 | Existing guidance 의미·cadence 확인 | `engine.py`. L-C2와 같은 파일을 수정하므로 diff와 tests를 별도로 추적하되 최종 source에서 함께 검증 |
| L-C2 | 3 | **D-C error/clock/cancel 설계 선행** | `sources.py`, `engine.py`, 필요한 Scanner adapter mapping. 동기 retry 누적으로 input 지연을 악화시키지 않음 |
| L-A2 | 1 | **D-A cancellation target/activation 설계 선행** | `reading_audio.py`. Native A1 수정과 함께 검증·rollback하며 A2 단독 PASS로 AV blocker를 닫지 않음 |

상한은 packet별 최대치이며 합계를 실제 변경 파일 수나 공수로 취급하지 않는다. A1/A2는 같은 두 product module에 걸칠 수 있다. 각 patch는 before/after reproducer와 targeted regression을 갖고, 다른 subsystem의 threshold/protocol을 변경하지 않는다.

### B. 구조 선택·추가 계측이 먼저 필요한 diagnostics/design

| Packet | 반드시 얻을 evidence | 결과에 따른 분기 | 조건부 correction 상한 |
|---|---|---|---:|
| D-A | Native call별 stream/epoch/thread/enter-exit; blocked write/drain/close; native-only·HTTPS-only·combined; 가능한 dump stack과 symbol 상태 | 기존 worker 소유권으로 interruption을 만족하면 해당 내부 lifecycle 수정. 불가능하면 callback/nonblocking 후보를 설계 검토. 새 process/backend/layer는 별도 예산 | 2 product파일; port signature/dependency 변경은 상한 밖 |
| D-F | 실제 flash identity, UART wire와 MCU RX, ORE/FE/NE·service gap, exact parser fixture, HAL failure/PWM/physical 결과 | RX loss→servicing 구조 설계, parser-only→국소 validate/commit/recovery, bus 이후 physical failure→hardware 측정/교정 | 계측 build3 / 이후 구조 correction4 이하, 별도 승인·identity 필요 |
| D-C | Acquisition/analyzer/recognizer별 시간, valid/missing/hard-reset, input queue age, cancel 도착→lock→release, deadline 경계 | 기존 state machine으로 충분→L-C2. Source/environment 원인→환경 문제로 유지. Input/cancel 계약 미충족→engine 내부 bounded owner 후보 검토 | 구조 후보4 이하; 전역 Application/S0 async 재설계는 상한 밖 |

현재 D-A만 architecture_change_required로 판정됐다. D-C/D-F의 insufficient_evidence를 구조 변경 확정으로 바꾸지 않는다. 구조 설계가 위 cap을 넘으면 구현 전에 파일 목록·migration·contract 호환성·rollback·H1–H4 비용을 다시 제출한다.

## 3. Hardware 작업을 별도 필수 경로로 관리

다음은 software correction의 성공으로 자동 해소되지 않는다. D-F 준비와 함께 진행할 측정 backlog이며, 지금 pin/LUT/각도 변경을 지시하는 목록이 아니다.

| 항목 | 먼저 할 일 | 이유 / 종료 조건 |
|---|---|---|
| STM-REQUIRED-CONTROL-INPUT-P1 | 실제 버튼 label·continuity·GPIO 전압·flash identity 대응 | 입력 부재만으로 broken pin/잘못된 pin map을 확정할 수 없음. Mode/CONFIRM SHORT·LONG/PAGE NEXT·PREV/필수 navigation의 physical packet 확인 |
| MODE-LEVER-SOLDER-P1 | 연결 상태·고정/전환 동작 측정 후 필요한 배선 작업 결정 | H3의 고정 lever state가 실제 mode 전환 acceptance를 대체하지 못함. 전환 입력과 host mode state를 함께 확인 |
| ACTUATOR-CLEAR-RESIDUAL-P1 | 셀별 top/bottom residual, I2C 결과, PWM/전원과 물리 복귀 상태 대응 | Zero FRAME parse≠실제 clear. 측정 결과에 따라 기계/배선/전원/calibration을 분리하고 승인된 국소 조치 후 재측정 |

Servo 구동·flash·live upload는 실제 목적/예상 packet/최대 횟수/stop condition/evidence 위치를 먼저 보고한다. 기존 source/state/evidence는 보존하고 Laptop D:는 접근하지 않는다.

## 4. 권장 착수 순서와 의존성

1. **첫 착수 묶음:** L-T1/L-T2, L-B의 concrete implementation 범위를 준비하고 D-A owner 설계를 시작한다. D-C/D-F의 계측 계획과 장비/identity 확인도 준비한다. 구현은 별도 승인 전에는 하지 않는다.
2. **설계 후 구현:** D-A에서 확정된 A1/A2 lifecycle을 같은 계약으로 구현·검증. D-C 결과에 따라 L-C2 또는 제한된 구조 후보를 선택. D-F는 원인이 확인된 branch만 correction으로 전환한다. L-C3은 국소 수정으로 진행 가능하나 actual cue 검증은 audio 결과와 연결한다.
3. **Targeted 검증:** Packet마다 기존 결함을 실패 assertion으로 전환하고 correction 뒤 통과시킨다. 정상 경로뿐 아니라 cancel/reconnect/close/fatal/overflow를 해당 경계에서 검사한다. 관련 subsystem tests를 이어서 실행한다.
4. **통합 software 검증:** 승인된 변경들이 합쳐진 source identity에서 G3-A를 재실행한다. 기존 PASS evidence를 덮어쓰거나 이미 새 source가 PASS한 것으로 취급하지 않는다.
5. **Fresh H1/H2/H3:** H1은 두 spread/durable receipt/CONFIRM LONG/fresh READY, H2는 existing READY의 normal-rate audio+braille, H3는 production entrypoint/physical V3 A-R 및 필수 controls/reconnect/re-entry를 각각 검증한다. 준비된 개별 경계 시험은 앞서 수행할 수 있지만 최종 수용은 통합 source로 남긴다.
6. **H4:** Hardware 잔여 blocker까지 닫힌 뒤 full live capture→READY→same-focus/generation audio+physical braille→exit/re-entry/app restart stable cursor를 검증한다.

필수 의존성은 `D-A → A1/A2`, `D-C → C2 recovery/구조 선택`, `D-F → firmware 구조/physical correction 선택`이다. T1/T2는 시험 신뢰도를 높이는 선행 작업이며 read-only source 진단의 hard dependency가 아니다. L-B는 audio/camera 설계와 독립적이다. Hardware 측정은 software patch 완료를 기다릴 필요가 없지만 physical 실행 조건은 먼저 제출한다.

## 5. 지금 작업화하지 않을 항목

- Scanner N/K/identity/duplicate threshold 완화, production8초 연장으로 PASS 처리.
- 원인 측정 없는 UART DMA/IRQ 전환, FRAME grammar/V3 semantics 변경.
- 근거 없는 pin/channel swap, servo LUT/angle 조정, 인증/TLS 변경.
- Broad dependency upgrade, lockfile 재생성, 전역 async/scheduler/새 service 도입.
- 기존 content P1 waiver/Deferred, OCR 일반화, Raspberry Pi, 일반 refactoring.

이 항목들은 우선순위가 낮은 예정 작업이 아니라 **현재 승인 범위에서 제외된 작업**이다. 새 원인 증거가 생기면 별도 검토한다.

## 6. 추적할 완료 신호

각 작업은 code defect closed, incident root confirmed, 실제 hardware acceptance를 별도로 기록한다. A1/A2 code correction 성공은 두 AV 원인 확정이 아니며, L-B 성공은 MCU FRAME loss 해소가 아니다. C3 event 생성은 실제 음성 안내 완료가 아니다.

STM ACK=입력 수락, outbox/V4 receipt=durable delivery, datapack_saved(revision)=fresh READY, playback completion=해당 audio software lifecycle 완료, 실제 speaker/physical cells=별도 관찰을 유지한다. 이 신호나 H1/H2/H3 일부 PASS를 서로 대체하지 않는다.

**권장 결정:** 작은 tooling/exit 및 host local corrections를 먼저 구체화하고, 가장 중요한 audio owner 설계를 동시에 선행한다. Firmware·camera·hardware는 계측으로 수정 범위를 닫는다. 이후 packet별 구현/검증과 통합 G3-A/fresh H1–H3를 거쳐 H4로 진행한다. 현재 product source 변경0, integration ready 아님.
