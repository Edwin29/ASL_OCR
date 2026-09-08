# 현재 상태 진단과 한정 실제 시연 경로 완성을 위한 우선순위

작성일: 2026-09-08. 기준: [첫 구현 결과](H123_IMPLEMENTATION_RESULT_20260908.md), [T-close/Host read bound 후속 결과](H123_FOLLOWUP_TCLOSE_HOST_READ_RESULT_20260908.md), [최신 source/test 검증](evidence/h123-followup-20260908/final-validation.json), [최신 G3-A](evidence/h123-followup-20260908/g3a-evidence/e0b-production-full-model-report.json).

**현재는 “확인된 software 결함의 국소 수정과 회귀 완료, 실제 시연 경로의 재수용 준비” 단계다. H4는 BLOCKED이며 integration ready가 아니다. 다음 주력은 실제 configuration·audio·camera·serial·firmware·physical cells에서 evidence를 확보하고, 그 결과에 따라 필요한 수정만 추가하는 것이다.**

이번 상태 정리에서는 product source를 변경하거나 live/hardware 시험을 실행하지 않았다. Desktop product246개 파일을 최신 검증 hash와 다시 비교해 drift0을 확인했다. Laptop 동일성은 마지막 반영 직후 검증 evidence를 근거로 하며 이번 턴에서 원격 상태를 새로 관측한 것은 아니다.

## 1. 검증된 현재 상태

| 경계 | 현재 확보한 사실 | 아직 주장할 수 없는 사실 |
|---|---|---|
| Source/environment | 마지막 Laptop 반영 후246 product hash 일치, Device/Scanner/Parser import가 `C:\ASL_OCR_INTEGRATION`, 기존 환경 manifest 보존 | 이후 실제 production process가 올바른 interpreter/config/audio session으로 실행됐다는 확인 |
| Software regression | Device301 + Scanner206 = **507 PASS** | Physical input, native speaker+network 결합, 실제 MCU/PCA/servo 수용 |
| G3-A | 최신 source로 고정 replay 두 receipt, 네 fragment, fresh READY revision1, 네 accessible/nonempty-braille pages, Piper audio136개 검증 | Live pages26/27·28/29 capture, 물리 CONFIRM LONG, 실제 청취와 cells. Status는 `manual_pending` |
| Native audio | Realtek/MME interactive session에서 synthetic PCM20과 [1B actual audio run](AUDIO_CONSOLE_1B_RUN_20260908.md): authenticated Piper/system cues, 정상·빠른 이동, latest completion, catalog 재진입, stable cursor restart, worker 종료 PASS | 과거 AV의 exact root는 여전히 insufficient_evidence. Physical STM presenter와 결합한 fresh H2/H3는 별도 필요 |
| Host serial | Fake split/ACK/release/reconnect 회귀 및 실제 pyserial loopback read/close 검증 | HC-05/COM/STM 물리 링크의 V3 acceptance와 내려가는 FRAME 무손상 |
| Firmware | Exact C 함수 host compile/HAL stub에서 malformed atomic reject, overflow 회복, PCA 실패 관측·동일 frame 재시도 검증 | STM target binary build/flash, 현재 board와 source 일치, 실제 bus/PWM/servo 적용 |
| Android camera | Fresh run C1에서 4000×3000 snapshot 3/3 PASS, 1.344–1.859초. Strict source/fallback0 유지 | 두 번째 spread page-change identity liveness와 cancel/worker 종료의 실제 지연 |

누적 수정은 **product 고유12파일, test 고유7파일**이다. 후속2 product 파일은 첫12파일 안의 `coordinator.py`와 `stm_serial.py`이므로14파일로 합산하지 않는다. 기존 unrelated working-tree 변경과 과거 evidence는 보존한다.

## 2. 수정한 문제와 종결 수준

| 문제 | 수정된 동작 / evidence | 현재 상태 |
|---|---|---|
| T1 Android preflight | Production snapshot factory 재사용, IP profile에서 webcam fallback0 | Code defect closed. 실제 source 가용성 별도 |
| T2/CP-T1/T-close | 최초 fatal 유지, fatal/cleanup failure exit2, STOPPED 후에도 cleanup, cancel 실패 후 disconnect/나머지 close, 최초 예외·cleanup 실패 순서 보존 | Code defect closed. **T-close를 다음 수정 후보로 다시 올리지 않음** |
| A1/A2 audio lifecycle | Native stream lifecycle owner 단일화, signal-only interruption, old cancellation을 replacement publish 전에 처리, worker 종료 확인 | Code defect closed. 과거 crash root와 실제 결합 출력 acceptance는 open |
| B-host/CP-H1 | Complete-line 전 ACK 금지, release watermark, accepted initial step 보존·stale repeat 방지, lever 입력 순서 보존 | Code defect closed. Physical V3 재수용 필요 |
| Host read bound | `read_until(size=256)`으로 byte cap/whole-call timeout 검사. Baseline은 지속 입력 중 close 반환 후 worker 생존, candidate는 종료 확인 | Code defect closed. **다음 수정 후보에서 제외**. Native COM driver hard hang까지 보장하지 않음 |
| C2 snapshot recovery | Finite transient retry, permanent/terminal taxonomy, terminal latch, stop 뒤 늦은 frame publish 차단, preview worker transient 생존 | Code defect closed. Production8초/N5에서 liveness·input latency는 미확정 |
| C3 page-change 안내 | 기존 stable samples/time/cooldown으로 UNKNOWN/missing/rejection 대기 안내 | Event producer defect closed. 실제 cue 청취 미수행 |
| Firmware parser/overflow/PCA 관측 | Validate 후 commit, malformed record atomic reject, overflow suffix 폐기, bus 성공/실패와 requested state 구분 | Source correction 및 compiled fixture PASS. **Board에 적용된 수정으로 계산하지 않음** |

`code defect closed`는 해당 before/after invariant를 검증했다는 뜻이며 원래 H1/H2/H3 incident 전체가 해결됐다는 뜻은 아니다.

## 3. 남은 핵심 문제

| 남은 항목 | 분류 / 근거 | 시연에 미치는 영향 | 다음 판정에 필요한 evidence |
|---|---|---|---|
| Live source 가용성 | Fresh C1에서 environment blocker 해소 확인. JPEG SOS warning은 decode 성공과 함께 발생해 별도 관측 항목 | Capture 시작은 통과; warning의 화질 영향은 미확정 | 다음 run에서 같은 strict source probe와 frame hash/해상도 유지 |
| Page-change liveness / input·cancel responsiveness | probable_product_risk_with_confirmed_runtime_profile_incompatibility. Production은 8초 unknown/reset을 반복했고 native threaded query의 첫 exact `28|29`는 11.406초에 출현 | sequence 2와 fresh READY를 직접 차단 | Recorded cadence/token engine replay로 first-valid clock, bounded stabilization, sliding window 후보 비교. N/K/8초 값은 설계 전 변경 금지 |
| Native crash 및 실제 audio 결합 | 과거 AV exact root insufficient_evidence. [1B](AUDIO_CONSOLE_1B_RUN_20260908.md)에서 actual authenticated Piper+system cue+Realtek speaker+supersession/close/re-entry는 PASS | 실제 audio-only 경로의 재현 위험은 낮아졌으나 STM presenter/physical controls 동시 결합은 미검증 | Fresh H2/H3에서 normal-rate audio+braille 결합; crash 재발 시 새 dump stack 확보 |
| MCU 방향 normal-rate FRAME 손상 | insufficient_evidence. Host bounded read는 반대 방향 NAV 수신 lifetime을 고친 것 | 점자 FRAME 누락·손상·잘못된 cells 가능 | Host TX bytes → UART wire → MCU RX → parser를 동일 run/frame에 대응 |
| Firmware servicing/PCA gap | probable_product_risk. 기존 batch delay의 modeled frame500ms, 실제 ORE/FE/NE 미측정 | RX 손실이나 physical input 지연 가능 | UART service gap/error flags와 I2C/PWM 시간 상관. 측정 전 DMA/IRQ 전환 금지 |
| Required controls/lever/clear residual | hardware_or_wiring, 세부 원인 미확정 | Physical mode/CONFIRM/navigation과 실제 clear 미충족 | Label/continuity/GPIO, actual V3 packet, 전원/PWM/셀별 적용·복귀 관측 |
| Stable cursor 및 same-generation 결합 | Acceptance gap. 최신 source/실제 장치에서 full re-entry/restart 경로 없음 | 시연 마지막 사용자 결과를 아직 보장 못함 | 같은 stable device ID에서 종료·재진입·앱 재시작 전후 cursor/focus/generation 및 실제 출력 |
| V4 isolated storage503 | insufficient_evidence. 한 Desktop test 실패, 짧은 path 재시험/Laptop tests/새 G3-A PASS | 반복되면 durable receipt 경로 차단. 현재 상시 장애로 확정할 수 없음 | 원래 OSError의 type/errno/winerror, 실제 demo path layout 재현. `LoseFirstResponse` 문구를 commit evidence로 쓰지 않음 |

옛 H1의 acquisition 전체가 application thread를 막았다는 일반화는 수정됐다. Preview-OFF 직접 호출 repro를 Preview-ON H1의 원인 증명으로 재사용하지 않는다. 과거 물리 `NAV,D,S,2`는 V2 SHORT이며 V3 activated/released acceptance가 아니다.

## 4. 우선순위와 실행 의존성

아래 순위는 착수/의존성 순서이며 기존 P1/D01 severity를 올리는 분류가 아니다. 같은 순위의 작업은 독립적으로 준비할 수 있다. Camera가 막혀도 existing READY reading/audio와 firmware bench 준비는 진행할 수 있다.

| 우선 | Work packet | 왜 지금 필요한가 | 완료 조건 / 다음 분기 |
|---|---|---|---|
| **0 — 모든 새 run 선행** | 실제 실행 identity/config 및 evidence 준비 | Source alignment만으로 production process·interactive speaker·flashed firmware identity가 확인되지는 않음 | 아래 공통 manifest 작성. 각 run이 실제로 통과/우회할 boundary를 명시 |
| **1A — 즉시, 낮은 비용** | Android strict read-only probe + D-C timing 준비 | 마지막 explicit FAIL이며 H1 시작 자체를 막음 | 같은 endpoint에서 실제 frame 확보. 실패하면 phone/LAN/app/transport를 분리하고 H1을 성공으로 시작하지 않음 |
| **1B — 실행 결과 PASS** | Existing READY + console + 실제 Piper/system cue/native speaker | [실행 보고서](AUDIO_CONSOLE_1B_RUN_20260908.md): Realtek 실제 청취, 정상/빠른 이동, generation interruption/latest completion, replay, catalog 재진입, cursor restart, exit0/worker close | Audio-only evidence는 확보. H2/H3에서 STM presenter·physical controls와 같은 run으로 결합 |
| **1C — 즉시 착수, 긴 준비 경로** | Flashed firmware identity/rollback/STM target build + hardware bench 준비 | C fixture 수정은 board에 적용되지 않았고 normal-rate RX/physical cells가 최대 잔여 불확실성 | 현재 flash와 build 산출물의 관계·복구 방법 확보. 수정 C의 target build 확인. 전원/배선/측정 준비 후 제한된 hardware run 계획 |
| **2A — 준비된 bench에서 최우선 물리 진단** | Host↔STM V3 및 normal-rate FRAME/RX/parser/PCA 경계 추적 | Console/direct paced PASS가 가린 first failing boundary를 밝혀야 함 | 아래 H2/bench 절차로 손실 위치 판정. Product defect가 재현된 branch만 추가 수정. Hardware 원인은 hardware로 유지 |
| **2B — 실행 결과 FAIL** | Fresh H1: live pages26/27·28/29 + console + 실제 TTS | Sequence 1은 durable receipt PASS, guidance audio는 실제 청취. Page-change identity가 sequence 2 전에 반복 timeout | [Fresh H1 보고서](H1_CAMERA_FRESH_RUN_20260908.md)와 [D-C follow-up packet](work-packets/H1_PAGE_CHANGE_LIVENESS_DESIGN_20260908.md)에 따라 recorded replay→bounded correction 판정→fresh H1 재검증 |
| **3 — 각 원인에 따른 조건부 수정** | D-C/D-A/D-F 또는 V4 최소 수정과 targeted regression | 측정 없이 threshold/architecture를 바꾸면 원인과 acceptance가 다시 섞임 | Concrete trigger/violated invariant/파일 상한을 확정해 수정. 새 source에 affected subsystem tests→G3-A→영향받은 fresh run |
| **4 — 단일 최종 source/config로 결합** | Fresh H2 및 H3 production physical control acceptance | Audio-only, input-only, direct-serial 결과를 합산할 수 없음 | Normal-rate actual audio+braille, V3 필수 controls, hold/release, reconnect, mode change, close/re-entry/restart를 동일 구성으로 확인 |
| **5 — 마지막** | H4 한정된 전체 시연 | 사용자 목표는 한 run의 물리 입력부터 capture·reading·복구까지 연결하는 것 | §7 모든 결과를 관찰. FAIL/insufficient_evidence blocker를 자동 면제하지 않음 |

2A의 console+STM 출력 시험은 fresh H2의 앞부분으로 재사용할 수 있지만, TTS OFF나 FRAME suppression/pacing override가 있으면 진단 evidence로만 분류한다. Firmware/source 수정 뒤의 최종 H2/H3는 새 identity에서 다시 수행한다. H1/bench는 준비가 된 경계부터 진행하며 번호 때문에 불필요하게 서로 대기하지 않는다.

## 5. 다음 시험의 구체적 구성과 evidence

### 0. Run 공통 manifest

고정할 정보는 Desktop 실제 server executable/import/config/API endpoint, Laptop interpreter/3 package import/hash, production `python -m asl_device` 사용 여부, parsed config/override, controls/presenter/audio implementation, initial mode, stable device ID, 시작 datapack/revision/cursor, Windows interactive session/audio device, COM/baud/read timeout, firmware source/build/flash identity다. Credential 값은 포함하지 않는다.

새 run은 Laptop C:의 isolated evidence/state 하위 root를 사용한다. 안정된 cursor 복구는 지정한 동일 runtime/state를 이어서 사용하고 DB reset으로 시험하지 않는다. 기존 production/evidence를 덮어쓰지 않는다. Desktop 실제 server runtime과 loopback server를 구분한다. G3-A의 HTTP loopback 인증 성공이 production HTTPS certificate/auth/audio-ref 연동 확인을 대신하지 않는다.

### 1A / 2B. Camera와 fresh H1

1. 현재 고정 source를 소수의 read-only snapshot으로 확인한다. 실패 시 HTTP status/timeout 단계·소요시간을 비밀정보 없이 기록한다. Webcam fallback0. Phone 화면의 앱 동작·같은 Wi-Fi 상태 등 사용자 관측은 이 단계에서 요청한다.
2. Probe가 성공하면 실제 H1의 preview 설정을 유지한 engine 경로에서 acquisition/analyzer/recognizer·observation/reset·input queue age를 측정한다. Preview-OFF 비교가 필요하면 별도 diagnostic run으로 표시한다.
3. 새 datapack에서26/27과28/29를 촬영한다. Frame ID→L/R artifact hashes→outbox sequence→V4 receipt→S1 fragment→READY revision을 연결한다. 잘못된 side/order, duplicate 또는 false receipt는 즉시 FAIL이다.
4. 첫 receipt 뒤 안내 cue를 실제로 듣고 page-change 진전을 확인한다. Console `DeviceInputEvent` LONG은 downstream finalize 의미만 검증한다. Physical CONFIRM LONG은 H3/H4에서 별도 확인한다.
5. 통제된 source transient/cancel/stop 시험은 isolated runtime에서 수행하고 late frame/worker exit와 durable artifact 보존을 확인한다. Production timeout8초/N5를 유지한다. Input latency의 수용 기준이 계약에 숫자로 정의되지 않았다면 시험 전 기대치를 명시하고 측정 뒤 유리하게 바꾸지 않는다.

### 1B. Servo 없는 실제 audio 결합

Existing READY의 waiver 밖 정상 item을 고정하고 production composition에서 console controls 및 serial을 사용하지 않는 presenter 설정을 명시한다. Custom composition이 필요하면 대체한 class/entrypoint를 기록하고 production-equivalent라고 단정하지 않는다.

정상 page/item/math-window 이동, 짧은 간격의 navigation, cue↔reading supersession, CONFIRM replay/exit, mode 전환, 앱 종료/재시작을 bounded 횟수로 수행한다. Audio ref는 authenticated fetch하고 focus/generation/epoch, fetch/play/interrupt/finish, native owner/stream start-close, worker 종료를 대응한다. Synthetic tone은 이 시험의 실제 Piper 내용을 대체하지 않는다.

사용자에게 내용 일치, 중단 뒤 옛 음성 재출현 여부, 최신 focus 음성, 실제 cue 및 종료 상태를 관측받는다. Crash/hang/stale output가 나오면 즉시 중단하고 새 로그/dump를 보존한다. 기존 dump의 read-only 분석은 도구/symbol 상태와 함께 bounded로 시도한다. Stack을 확보하지 못하면 exact AV root는 미확정으로 유지하며 성공 횟수만으로 면제하지 않는다.

### 1C / 2A / 4. Firmware·serial·physical controls와 H2/H3

상세 실행 순서, packet 상한, stop/rollback, H2/H3 분리 수용 기준은 [1C / 2A / 4 실행 계획](H2_H3_FIRMWARE_SERIAL_PHYSICAL_EXECUTION_PLAN_20260908.md)에 고정했다. 이 계획 작성 시점에는 flash·servo 구동·새 product 수정이 없다.

**실제 servo 구동 또는 flash 전에** 목적, 정확한 예상 packet 목록·최대 frame/input 수, stop condition, evidence 위치, source/build/flash identity·rollback을 제출한다. 이번 문서 자체는 flash나 무제한 반복 구동을 실행한 기록이 아니다.

우선 현재 배선/전원/lever/button label과 flash identity를 확인하고 수정 firmware의 STM target build를 검증한다. Board에 correction을 올리기 전 해당 image와 복구 image를 식별한다. Source만 같거나 MSVC fixture가 PASS라는 이유로 flashed identity를 가정하지 않는다.

실제 incoming V3 `HELLO,3`/ACK와 각 필수 physical input을 trace한다. DOWN A/R, CONFIRM SHORT/LONG, NEXT/PREV/필수 navigation, maintained lever를 구분하고 sequence ACK/dedupe/accepted order와 S0 operation을 연결한다. ACK는 input accepted이며 physical apply가 아니다. COM reconnect/close에서는 worker 종료와 stale activation 재시작 여부를 확인한다.

정상 production rate의 FRAME에서 host serialize/write→UART wire→MCU RX/ORE·FE·NE→parser validation→PCA write result→실제 cells를 비교한다. 기존 debug UART의 blocking 출력 자체가 timing을 바꿀 수 있으므로 계측 영향도 기록한다. Passive trace 또는 제한된 counter를 먼저 검토하고 임의의 per-byte log를 추가하지 않는다.

손실 위치별 분기는 다음과 같다.

| 최초 불일치 | 후속 조치 |
|---|---|
| Host payload/write 이전 | Host serializer/ordering/reconnect의 국소 reproducer와 수정 |
| Wire는 정상, MCU RX가 손실 | 실제 servicing gap/error flags로 원인 확인 후 RX 구조 설계 검토. DMA/IRQ를 바로 선택하지 않음 |
| RX 정상, parser/state가 잘못됨 | Exact parser fixture와 target build에 재현하여 국소 correction |
| Parse 정상, PCA write 실패 | I2C/전원/주소·bus 시점과 HAL 결과 분리. 성공으로 보고하지 않음 |
| PCA write 성공, 실제 cells/clear 실패 | PWM·전원·기계·wiring·calibration 측정. 근거 없이 LUT/각도/channel/pin 변경 금지 |

Paced/direct-serial 또는 intermediate FRAME suppression은 원인 분리용 비교다. 이를 production normal-rate acceptance로 승격하지 않는다. 마지막에는 actual TTS를 켠 production presenter/control 구성으로 H2/H3를 수행하고 same focus/generation·최종 settled cells·clear를 사용자가 관측한다.

## 6. 추가 수정의 조건과 예산

| Packet | 지금 수정할 것인가 | 조건부 budget / 검증 |
|---|---|---|
| T-close / Host read bound | **아니오. 수정·재현·반영 완료** | 새 실제 trigger가 나오면 해당 경계만 재개 |
| Audio | Actual combined test와 dump evidence 우선 | 기존2 product modules 안의 lifecycle correction 우선. 새 backend/process/dependency/layer는 별도 설계·migration/rollback 검토 |
| Camera / scheduling | Availability 및 production timing/cancel evidence 우선 | Source/engine 국소 correction 또는 기존 계획의4파일 이하 owner 후보. 전역 async redesign 금지 |
| Firmware RX | Board identity·wire/RX 측정 우선 | 기존 계측3파일/구조 correction4파일 상한 검토. Target build/flash rollback, normal-rate H2/H3/H4 비용 포함 |
| V4 storage/harness | 작은 진단을 병행하되 broad fix 없음 | 실제 demo와 같은 path layout에서 underlying OSError 포착. Path가 짧을 때 PASS만으로 root 확정 금지. Harness의 response-loss 주입은 성공 receipt 전제 확인 후 별도 test-only 보완 후보 |
| Content P1/Deferred | **자동 수정하지 않음** | 기존 waiver scope/정상 표본을 run manifest에 명시. 범위 밖 필수 내용 결함 또는 새 crash/false READY로 이어지면 중단·별도 판단 |

V4503은 현재 지속적인 blocker로 확정된 것은 아니므로 native/camera/physical RX보다 후순위다. 다만 실제 H1 경로에서 반복되면 durable receipt가 막히므로 즉시 선행 blocker로 올리고 원인을 분리한다. 전체 repo bug hunting으로 확장하지 않는다.

변경 시 targeted→affected subsystem→G3-A→영향받은 fresh H1/H2/H3 순으로 검증한다. 이미 통과한 source에서 변화나 새로운 실패가 없으면507 tests/G3-A만 반복해 physical evidence를 대신하지 않는다. 새 architecture layer가 필요하면 파일 상한·기존 contract 호환성·migration·rollback·H1–H4 비용을 먼저 제시한다.

### 2026-09-08 UP/H1 독립 검토 반영

[H1 및 physical UP 독립 고비용 검토](H123_UP_AND_H1_HIGH_COST_REVIEW_20260908.md)는 다음 실행 순서를 추가로 고정한다.

1. UP 재수용 전에 diagnostic harness의 early `ready`와 total NAV cap을 교정한다. 현재 zero-UP 결과는 유효하지만 기존 cap으로는 성공한 UP 3/3을 기록할 수 없다.
2. Corrected harness에서도 UP이 무응답이면 PA0 raw/IDR·MODER·PUPDR, press LOW duration, poll heartbeat를 측정한다. 보존된 H0·pre-IRQ·aligned source의 GPIO/init/debounce가 같고 과거 raw log에는 UP 성공이 있으므로 pin mapping이나 permanent wiring defect를 먼저 가정하지 않는다.
3. H1 actual-engine recorded replay를 고정했고, opaque SAME 뒤 남는 visual latch와 post-close late preparation cleanup의 bounded local correction 및 affected tests를 통과했다. 결과는 [H1/UP follow-up implementation](H1_UP_FOLLOWUP_IMPLEMENTATION_RESULT_20260908.md)에 있다.
4. H1 liveness는 N/K/threshold와 production 8초 값을 유지한 후보 비교 뒤 수정한다. Exact pair가 2.05초마다 지속돼도 8초마다 N4를 폐기하는 현행 동작은 재현됐지만, first-valid clock만으로는 5번째 observation이 8.2초이므로 충분하지 않다.
5. 동기 footer OCR worker ownership과 recognizer early-exit은 추가 timing/equivalence 계측 전 architecture 또는 performance correction으로 승격하지 않는다.

이 addendum은 physical CLEAR·servo 정렬 보류를 해제하지 않는다. H4는 fresh H1, hardware repair 뒤 fresh H2/H3, final G3-A가 모두 통과할 때까지 BLOCKED다.

## 7. H4의 최종 수용 조건

단일한 최종 source/config/firmware identity에서 아래 사용자 결과가 이어져야 한다.

1. 실제 lever와 버튼으로 capture/reading catalog 조작.
2. 새 datapack에26/27 및28/29의 두 spread 촬영, 같은 frame L/R/올바른 side·order 보존.
3. 각 artifact의 durable V4 receipt 뒤에만 실제 전송 완료 안내.
4. Physical CONFIRM LONG 뒤 fresh READY revision 게시·저장 안내.
5. READY 선택 후 page/item/math-window 이동, 같은 focus/generation의 실제 Piper 음성과10-cell 점자 관찰.
6. Reading 종료·재진입 및 앱 재시작 뒤 동일 stable device cursor 복구, stale audio/FRAME/hold 재시작 없음.

`ACK accepted`, `outbox durable`, `V4 receipt`, `READY published`, `audio completion`, `PCA bus applied`, `physically observed cells`는 별도 칸으로 판정한다. Native callback 완료와 사람의 청취를 구분한다. Wire write나 PCA HAL_OK만으로 물리 셀 합격을 주지 않는다.

Critical FAIL 또는 insufficient_evidence가 남으면 integration ready라고 선언하지 않는다. 과거 AV root 등의 부족한 evidence를 예외 취급하려면 별도 명시적 판정이 필요하며 이번 우선순위 문서가 면제를 제공하지 않는다. 기존 content waiver/Deferred도 자동 해제하거나 최종 content acceptance PASS로 바꾸지 않는다.

## 8. 권장 다음 실행 묶음

**첫 묶음은 actual runtime manifest 확보, Android read-only 가용성 확인, existing READY의 console+actual Piper 청취, firmware identity/target build·bench 준비다.** 이 네 작업이 각 branch의 다음 시험 가능 여부를 결정한다. Camera가 정상화되면 fresh H1, bench가 준비되면 normal-rate RX/PCA 진단, audio가 통과하면 actual physical controls와 함께 H2/H3를 결합한다. 측정으로 확인된 결함만 수정하고 마지막에 H4를 수행한다.

사용자 관측은 phone 앱/source 상태 확인, actual Piper 내용·중단/완료 청취, physical button/lever 조작, 셀별 적용·clear 확인에서 필요하다. 실행 시 필요한 항목을 묶어 요청하고 각 software trace의 timestamp/focus/generation과 대응한다. 지금은 새 hardware 관측을 했다고 가정하지 않는다.
