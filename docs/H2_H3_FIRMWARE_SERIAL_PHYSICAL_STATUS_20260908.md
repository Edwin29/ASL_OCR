# H2/H3 Firmware·Serial·Physical 실행 상태

작성일: 2026-09-08  
상태: **USART1 RX 기본·stress·authoritative alignment PASS / physical CLEAR FAIL**

결정 보류: 2026-09-08 사용자 지시에 따라 확인된 PCA 좌우 role reversal은 기록만 유지한다. Firmware address routing, bit reversal, servo LUT, angle, channel 또는 hardware wiring은 변경하지 않는다.

## 1. 현재 결론

Normal-rate HC-05 FRAME 손상의 first failing boundary는 STM32 USART1 수신 register와 polling consumer 사이로 확정했다. 기존 polling 구현에서는 9600-baud FRAME마다 ORE가 증가했고 실제 조립 문자열에서 바이트가 빠졌다. USART1 RX interrupt와 bounded SPSC ring 후보는 같은 normal-rate 기본 packet 네 개를 손실 없이 수신·파싱했다.

물리 CLEAR는 별도 실패다. All-zero generation 111은 firmware에서 parse·commit됐고 PCA HAL 호출도 성공했으며 RX/error counter는 모두 0이었다. 사용자 관측은 후속 10-second video 판독으로 C1을 정정했으며, 최종 집계는 60점 중 43점 돌출, 16점 수납, 1점 불확실이다. 따라서 이 run에서 CLEAR의 first failing boundary는 PCA HAL 성공 이후의 PWM 출력, servo 방향·영점, horn/cam 또는 기구부다. PCA HAL 성공은 물리 적용 완료가 아니다.

## 2. RX 결함과 후보 수정

| 항목 | 결과 |
|---|---|
| 기존 firmware normal-rate | FRAME 2개 모두 손상; ORE가 각 FRAME에서 1씩 증가; parser atomic reject; 물리 이동 없음 |
| 원인 | blocking PCA/main-loop 작업 중 1-byte polling이 USART1을 제때 비우지 못함 |
| 분류 | `confirmed_product_defect / P1` |
| architecture | `architecture_change_required`, 승인된 bounded 4-file packet |
| 후보 | RXNE/error ISR은 byte/error만 ring에 적재; parser/PCA는 main context에 유지 |
| 계약 유지 | FRAME grammar, V3 ACK/dedupe/press/release, baud, PCA mapping 불변 |
| 정적/fixture | exact extracted-function ring fixture PASS; STM contract/serial tests 40 PASS |
| target build | clean build PASS; ELF SHA-256 `a6405b334bff58825fdef335f0c26607d334c6b0c835f8eba53c5cd9a2ca3ca7` |
| target basic | HELLO3/V3 initial NAV 및 normal-rate FRAME 4개 exact; format error 0; ORE/FE/NE/PE/overflow 0 |

변경 파일은 `main.c`, `stm32f4xx_it.c`, `main.h`, `stm32f4xx_it.h` 네 개다. 후보의 basic 및 50 ms blocking stress가 통과한 뒤 Laptop authoritative integration source에 expected-old-hash 조건으로 반영했다. 실제 aligned source를 isolated clean build한 ELF `1d4a2d9a24cad2a5a856ebf88b6565ddc1d81d3c5b1fd5f811f1551786555d56`를 download/verify/reset했고, FRAME 0개 smoke에서 V3 handshake·initial mode ACK·PCA 0x40/0x41 init가 통과했다.

## 3. CLEAR 물리 관측

점 번호는 각 셀에서 아래와 같다.

```text
D1 D4
D2 D5
D3 D6
```

사용자 표기의 `1=돌출`, `0=수납`, `?=불확실`을 적용했다.

| Cell | 돌출 | 불확실 |
|---|---|---|
| C1 | D1,D2 | 없음 |
| C2 | D3,D4,D5,D6 | 없음 |
| C3 | D1-D6 | 없음 |
| C4 | D5,D6 | D4 |
| C5 | D1-D6 | 없음 |
| C6 | D1-D6 | 없음 |
| C7 | D1-D6 | 없음 |
| C8 | D1,D2,D3,D4,D5 | 없음 |
| C9 | D1-D6 | 없음 |
| C10 | D3,D4,D6 | 없음 |

이 패턴은 특정 한 채널이나 한 PCA만의 단순 불량과 맞지 않는다. 좌우 dot column 모두 여러 cell에서 잔류한다. 현재 증거만으로 PWM pulse가 잘못됐는지, state 0의 방향·영점이 잘못됐는지, horn/cam이 수납 위치를 만들지 못하는지 구분할 수 없다.

이어진 C1/C2 isolation run은 다음을 확인했다.

| Step | 요청 | 기대 | 물리 관측 |
|---|---|---|---|
| B | C1 `63`, D1-D6 활성 | D1-D6 | D4,D5만 돌출 |
| D | C2 `7`, D1-D3 활성 | D1,D2,D3 | D3,D4 돌출 |
| F | C2 `56`, D4-D6 활성 | D4,D5,D6 | D1,D2,D4,D5,D6 돌출 |
| A/C/E/G | all-zero clear | 돌출 0 | 매번 정정된 43점 잔류 pattern과 정확히 동일 |

각 FRAME은 firmware에서 정확히 수신·파싱됐고 최종 generation 136, apply success, PCA failure 0, UART/ring error 0이었다. 특히 D와 F는 C2의 firmware top 또는 bottom servo 중 하나만 state 7로 변경하지만 물리적으로 양쪽 dot column의 pattern이 달라졌다. 따라서 설치 상태가 `PCA1 CHn→Cell n D1-D3`, `PCA2 CHn→Cell n D4-D6` contract와 맞는지, 또는 한 cam/slider의 이동이 반대 열까지 기계적으로 결합되는지 먼저 확인해야 한다.

사용자의 cell별 비교로 C1은 D/F 동안 CLEAR와 동일했고 C2만 변했다. C2의 변화 방향도 분리됐다. Firmware top(PCA1 CH1)만 변경한 D에서는 C2 오른쪽 D5/D6이 변했고, firmware bottom(PCA2 CH1)만 변경한 F에서는 C2 왼쪽 D1/D2/D3 pattern이 변했다.

별도 C1 분리 run에서 packed 7, 즉 firmware top/PCA1 CH0만 state 7로 바꾸자 C1 오른쪽 D4,D5가 돌출했고, packed 56, 즉 firmware bottom/PCA2 CH0만 state 7로 바꾸자 C1 왼쪽 D1,D2가 수납되어 전체 0이 됐다. 이 결과는 C1과 C2 모두에서 실제 열 역할이 `PCA1=right`, `PCA2=left`이며 firmware의 `PCA1=left/top`, `PCA2=right/bottom` contract와 반대임을 확인한다. 나머지 CH2..9는 전원-off lead trace 또는 추가 sampling 전까지 동일하다고 추정만 한다.

또한 C2 state 0은 D3,D4,D5,D6 잔류, state 7 요청은 각 열의 세 점 요청과 다른 pattern을 만들었다. 이는 열 역할 swap만 고쳐도 CLEAR/active pattern이 맞지 않으며 servo horn/cam의 state calibration을 별도로 측정해야 함을 뜻한다.

C5/C10 span sampling은 다음 결과를 추가했다.

| Cell/path | 관측 변화 | 다른 cell 변화 | 판정 |
|---|---|---|---|
| C5 firmware top/PCA1 CH4 | CLEAR 대비 오른쪽 D5 변화 | 없음 | C1/C2와 같은 role reversal |
| C5 firmware bottom/PCA2 CH4 | CLEAR 대비 왼쪽 D2 변화 | 없음 | C1/C2와 같은 role reversal |
| C10 firmware top/PCA1 CH9 | CLEAR 대비 오른쪽 열만 변화 | 없음 | C1/C2/C5와 같은 role reversal |
| C10 firmware bottom/PCA2 CH9 | CLEAR 대비 왼쪽 열만 변화 | 없음 | C1/C2/C5와 같은 role reversal |

따라서 CH0, CH1, CH4, CH9에서 동일한 board-wide role reversal이 확인됐고 channel-to-cell index 및 열 독립성은 네 표본에서 일치한다. 앞선 C10 coupling 판정은 잘못된 CLEAR 기준과 비교한 분석 오류였으며 철회한다. CH2/3/5/6/7/8은 아직 직접 sampling하지 않았지만 배열의 시작·중간·끝 네 channel이 동일하게 동작하므로 전역 PCA-role reversal은 확인된 것으로 판정한다.

분류는 `hardware_or_wiring / P1`이며 calibration/mechanics를 포함한다. Cell별 PWM 실측과 servo shaft/cam 관측 전에는 LUT, angle, channel mapping, pin mapping을 변경하지 않는다.

## 4. 완료 상태의 분리

| 완료 수준 | 현재 결과 |
|---|---|
| Host write completed | PASS |
| Firmware frame accepted/parsed | PASS, generation 111 |
| PCA HAL write returned success | PASS, failure count 0 |
| PWM waveform verified | 미측정 |
| Servo/cam applied | FAIL 또는 insufficient evidence |
| Physical all-zero observed | FAIL, 43/60점 돌출·1점 불확실 |

## 5. 다음 gate

1. **RX stress PASS:** 50 ms 간격 normal-rate 2-FRAME 반복에서 COM5는 generation 120과 121을 exact order로 완전 조립했다. SWD는 최종 `last_frame_apply_ok=1`, `last_applied_generation=121`, PCA failure 0, ORE/FE/NE/PE/ring overflow 모두 0을 확인했다. 첫 계측의 `-g` 초기화 gap은 동일 bounded run의 반복으로 닫았다.
2. **Authoritative source alignment PASS:** 네 파일의 old hash 확인, C: backup, atomic guarded copy, post-copy hash, actual-source clean build, flash verify, FRAME-0 smoke를 완료했다.
3. **Physical mapping/calibration repair gate:** 복잡한 wiring photo trace는 불가능한 것으로 확인했다. 기능적 mapping은 CH0/1/4/9에서 동일한 board-role reversal과 정상적인 cell/column 독립성을 확인했다. Firmware PCA role correction은 bounded local change 후보가 됐지만, CLEAR와 state pattern을 실제로 맞추려면 servo별 state 0..7 calibration 또는 horn/cam 재정렬 evidence가 추가로 필요하다.
4. **Control source/version diagnosis and repair/retest:** 현재 aligned firmware에서 UP SHORT 3회는 `UP STEP`과 `NAV,U,S`를 한 번도 만들지 않았다. 과거 H3 raw log에는 `UP STEP → NAV,U,S → ACK`가 여러 번 존재한다. 보존된 H0·pre-IRQ·aligned source의 PA0/init/debounce는 동일해 해당 identity 사이의 GPIO source regression은 반증 방향이다. Exact root는 PA0 raw level·press timing·poll heartbeat가 없어 `insufficient_evidence`로 유지한다. CONFIRM→PAGE PREVIOUS와 MODE solder 문제는 별도 물리 blocker다.
5. **Fresh H2/H3:** normal-rate physical clear와 V3 controls가 통과한 동일 final identity에서 시행한다.

Physical CLEAR와 controls blocker가 남아 있으므로 현재 상태는 H2/H3 또는 H4 integration ready가 아니다.

## 6. 남은 시험과 gate

| 우선순위 | 시험 | 목적 | 진입 조건 |
|---|---|---|---|
| P0 | 단일-dot orientation diagnostic | C1/C10의 D1·D3·D4·D6으로 PCA role correction에 필요한 bit order를 확정 | 사용자가 physical observation 재개를 승인할 때 |
| P0 | Servo/cam clear calibration | 20 servo 각각에서 실제 `000` 위치와 8-state pattern을 정하거나 horn/cam을 공통 영점으로 재정렬 | mapping 방식 결정 및 물리 안전 확인 |
| P0 | Physical control source/version diagnosis and repair/retest | 현재 aligned firmware의 UP 3회 무패킷과 과거 다른 firmware의 UP 정상 관측을 비교하고, CONFIRM→PAGE PREVIOUS 및 MODE solder 문제를 해결해 V3 A/R/S/L packet을 재수용 | preserved firmware/source 비교 및 배선·스위치 점검 완료 |
| P0 | Fresh H2 | Console→S0→actual audio→normal-rate FRAME→STM/PCA→physical cells, offset·supersession·clear·restart | 정확한 dot mapping과 all-zero physical clear PASS |
| P0 | Fresh H3 | Production physical controls→S0→audio/braille, hold/release·reconnect·restart | 8개 controls와 fresh H2 PASS |
| P0 | Fresh H1 completion | Live camera의 second spread/page-change, durable V4, finalize, fresh READY 및 fatal exit 재확인 | camera liveness blocker correction 결정·적용 |
| P0 | G3-A regression | 최종 software/firmware identity에서 기존 software contract 보존 | 모든 bounded correction 반영 후 |
| P0 | H4 acceptance | Live camera+physical controls+TTS+physical braille 전체 경로 | 동일 identity의 fresh H1/H2/H3와 G3-A PASS |

현재 바로 실행해도 독립적인 의미가 있는 다음 시험은 단일-dot orientation뿐이다. 다만 사용자가 기록만 지시했으므로 실행하지 않는다. Servo calibration·fresh H2/H3는 현재 CLEAR와 controls blocker를 해결하기 전에는 acceptance가 될 수 없다.

### Hardware-team 정렬 전 보류와 독립 작업 평가

2026-09-08 사용자 결정에 따라 물리 정렬·재세팅으로 결과가 바뀔 가능성이 큰 시험은 hardware team 조치 전 실행하지 않는다.

| 항목 | 지금 판정 | 근거 / 재개 조건 |
|---|---|---|
| 단일-dot orientation | **보류** | 물리 재정렬 뒤 bit 방향을 확인해야 기존 결과가 stale하지 않다. |
| Servo state 0..7 calibration | **보류** | Hardware team이 horn/cam 공통 영점을 재설정한 뒤 잔여 software calibration 필요성을 판단한다. |
| PCA role software correction | **기록만 / 구현 보류** | 물리 재정렬·재배선 결과에 따라 필요한 address/bit correction이 달라질 수 있다. |
| UP/CONFIRM/MODE controls | **UP harness 교정 후 재진단 / 나머지 수리 전 보류** | 현재 aligned firmware에서 UP SHORT 3회 모두 debug·packet이 없고, 과거 H3 raw log에는 UP 성공이 있다. 보존 source의 pin/init는 같으므로 corrected observation epoch/cap으로 재시험한 뒤 PA0 raw/continuity를 측정한다. CONFIRM/MODE는 repair 뒤 V3 packet 재수용으로 재개한다. |
| Fresh H2 | **보류** | Audio-only 1B는 통과했다. Full H2는 physical CLEAR와 mapping/정렬 후 수행해야 한다. |
| Fresh H3 | **보류** | 필수 physical controls와 physical output이 모두 선행 gate다. |
| Fresh H1 page-change | **즉시 진행 가능 / 다음 software 우선순위** | Camera/page-change/receipt/finalize는 servo와 controls wiring에 독립적이다. 기존 run은 first receipt 뒤 page-change `unknown` timeout 반복으로 막혔다. N/K/identity threshold와 production 8초를 유지한 recorded replay 및 bounded liveness correction 판단을 먼저 수행한다. |
| G3-A | **camera correction 뒤 checkpoint** | 다음 camera product delta가 생기면 targeted tests 뒤 실행한다. 모든 hardware/software correction 뒤 final identity에서 다시 고정한다. |
| H4 | **계속 BLOCKED** | Fresh H1/H2/H3가 같은 최종 source/config/firmware identity에서 모두 통과해야 한다. |

즉시 수행할 독립 work packet은 H1 recorded page-change timing replay와 liveness 원인 확정이다. Live camera 재시험은 deterministic replay에서 correction 필요 여부를 판정한 뒤 수행한다. T-close, Host read bound, 1B audio, USART1 RX basic/stress는 완료 evidence가 있으므로 새 trigger 없이 반복하지 않는다.

## 7. Evidence

- RX counter run: `docs/evidence/h23-1c-20260908/rx-counter-20260908-191131`
- Candidate build/basic run: `docs/evidence/h23-1c-20260908/irq-candidate-20260908-194041`
- Candidate 50 ms stress run: `docs/evidence/h23-1c-20260908/irq-candidate-20260908-194041/runs/2a-stress`
- Candidate 50 ms stress repeat and complete counters: `docs/evidence/h23-1c-20260908/irq-candidate-20260908-194041/runs/2a-stress-repeat`
- Guarded Laptop source alignment: `docs/evidence/h23-1c-20260908/irq-source-alignment-20260908-201845`
- Aligned source build/flash/smoke: `docs/evidence/h23-1c-20260908/irq-aligned-build-20260908-202007`
- C1/C2 10-second physical isolation: `docs/evidence/h23-1c-20260908/irq-aligned-build-20260908-202007/runs/physical-cell-isolation-video`
- C1 top/bottom 10-second isolation: `docs/evidence/h23-1c-20260908/irq-aligned-build-20260908-202007/runs/physical-c1-isolation-video`
- C5/C10 span role sampling: `docs/evidence/h23-1c-20260908/irq-aligned-build-20260908-202007/runs/physical-span-role-video`
- Current aligned firmware physical UP recheck: `docs/evidence/h23-1c-20260908/irq-aligned-build-20260908-202007/runs/physical-up-recheck`
- H1/UP independent high-cost review: `docs/H123_UP_AND_H1_HIGH_COST_REVIEW_20260908.md`
- Ring fixture: `docs/evidence/h23-1c-20260908/rx-ring-fixture/result.json`
- Physical map: `docs/evidence/h23-1c-20260908/irq-candidate-20260908-194041/runs/2a-basic/reports/post-clear-physical-observation.json`
- SWD state: `docs/evidence/h23-1c-20260908/irq-candidate-20260908-194041/runs/2a-basic/reports/post-run-swd-state.json`

이번 RX implementation packet의 product source modification count는 **4 files**다. 전체 진행에서 변경된 unique product source는 현재 **15 files**다.
