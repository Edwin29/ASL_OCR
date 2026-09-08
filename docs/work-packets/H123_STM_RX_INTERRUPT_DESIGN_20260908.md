# STM normal-rate RX integrity — bounded interrupt design packet

작성일: 2026-09-08  
상태: **원인 계측 완료 / architecture 변경 설계 확정 / product 구현 전**

## 1. 판정과 first failing boundary

`STM-FRAME-TRANSPORT-INTEGRITY-P1`의 현재 분류는 `confirmed_product_defect / P1`이다. Host가 COM9에 기록한 정확한 정상 속도 payload와 STM COM5의 조립 라인 사이에서 바이트가 소실됐고, 각 소실과 USART1 `ORE` 증가가 일치했다.

첫 실패 경계는 **HC-05가 구동하는 STM32 USART1 receive data register → main-loop polling consumer**다. 수동 계측에서 PA10 wire waveform 자체는 확보하지 못했으나, STM USART peripheral이 overrun을 직접 관측했으므로 firmware가 수신 바이트를 기한 내 소비하지 못한 사실은 확정된다. HC-05 전기적 품질에 추가 문제가 없는지는 별개이며 현재 수정의 필요조건이 아니다.

| 입력 | Host write | MCU 조립 | MCU 계측 | 결과 |
|---|---:|---|---|---|
| generation 120, alternating full-cell FRAME | 44 bytes, SHA-256 `179773dd...a2e6` | 43 bytes; `...,63,0,63,063,...` | ORE `0→1`, FE/NE 0 | atomic format reject, PCA apply 0 |
| generation 121, clear FRAME | 39 bytes, SHA-256 `23665b43...30ec` | 37 bytes; cell fields 부족 | ORE `1→2`, FE/NE 0 | atomic format reject, PCA apply 0 |

Raw evidence는 `docs/evidence/h23-1c-20260908/rx-counter-20260908-191131/runs/attempt2/`에 있다. 계측 ELF SHA-256은 `4b96a00b...2a84b`; 시험 직후 production ELF `4dada4bf...a997`로 download/verify/reset 복원했다.

계측 출력은 완성 라인을 처리한 뒤 COM5에 한 번 기록되므로 같은 라인 내부의 ORE를 만들 수 없다. 두 FRAME 사이에는 4초가 있어 앞 라인의 출력이 뒤 라인 수신과 겹치지 않았다. 최초 flash 시 target voltage 0.06 V였던 시도와 COM open timeout 시도는 FRAME 0개인 environment/harness failure다. 전압은 이후 3.25 V와 device ID `0x421`로 정상 확인됐다.

## 2. 기존 구조가 국소 patch만으로 회복되는가

판정은 `architecture_change_required`다. 현 구조는 `PumpBluetoothInput()`이 main loop에서 `HAL_UART_Receive(..., 1 byte, 1 ms)`를 반복한다. STM32F446 USART에는 수신 FIFO가 없고, parser 뒤 `ApplyBrailleFrame()`은 최대 다섯 번의 100 ms batch delay와 I2C write를 main context에서 수행한다. 정상 9600 baud에서는 약 1.04 ms마다 새 문자가 도착하므로, polling 빈도나 64-byte drain 상한을 조정하는 국소 수정은 blocking actuator lifecycle과 동시에 무손실 수신을 보장하지 못한다.

20 ms host pacing은 진단 비교에서만 통과했으며 production contract가 아니다. baud, FRAME grammar, V3 ACK/dedupe/press/release, servo delay·LUT·angle·channel을 바꾸는 방법도 이 defect의 수정 범위가 아니다.

## 3. 선택 구조와 책임

USART1 RXNE/error interrupt와 bounded single-producer/single-consumer ring을 사용한다. DMA는 9600-baud line protocol에 비해 lifecycle과 generated configuration 영향이 크므로 이번 범위에서 선택하지 않는다.

- USART1 ISR: status/data register를 한 번 읽고 byte 또는 resynchronization marker를 ring에 enqueue한다. ORE/FE/NE와 ring overflow counter만 갱신한다. 문자열 parsing, debug UART, I2C/PCA, servo 동작은 호출하지 않는다.
- Main context: ring을 drain하고 기존 CR/LF/line-length 규칙, `ProcessHostLine`, parser와 PCA 적용을 순서대로 실행한다.
- Handshake owner: 기존 blocking V1/V2/V3 negotiation을 유지한다. Versioned handshake가 성공한 뒤 interrupt RX를 시작하며 disconnect/reconnect 전에 중단·flush한다. Legacy V1은 기존 blocking response semantics를 유지한다.
- Backpressure: Host presenter의 latest-wins coalescing과 bounded line size를 유지한다. Ring은 정상 최대 actuator apply interval 동안 도착하는 여러 FRAME을 흡수한다. Ring overflow나 UART error가 발생하면 손상된 line 전체를 버리고 resynchronization marker 뒤의 다음 line부터 회복한다.
- Completion: ISR enqueue는 `received`, complete-line parse는 `accepted`, PCA HAL success는 `applied`다. 물리 셀 관측만 `physically_observed`다. FRAME에는 ACK가 없으므로 error 발생 run은 physical presentation acceptance FAIL이며 debug counter로 숨기지 않는다.

## 4. Ordering, cancellation, reconnect invariant

1. ISR이 관측한 byte 순서와 main parser가 소비하는 순서는 동일하다.
2. ORE/FE/NE/ring overflow가 포함된 line은 state/PCA를 전혀 변경하지 않는다.
3. 손상 line의 suffix는 새 command로 해석하지 않으며 다음 newline 뒤에만 회복한다.
4. Versioned reconnect는 interrupt RX를 disable하고 pending/ring/partial line을 flush한 뒤 기존 blocking handshake를 수행한다.
5. Handshake 성공 후 초기 `NAV,V,...` 전송 전에 interrupt RX가 활성화되어 ACK를 놓치지 않는다.
6. ISR은 main context의 parser, control queue, PCA state를 소유하지 않는다.
7. V3 sequence ACK/dedupe 및 DOWN A/R contract, FRAME field 수·encoding은 그대로다.

## 5. 변경 파일 상한과 migration

Production 변경 상한은 **4파일**이다.

1. `hardware/stm32/kitel2026final/Core/Src/main.c`: ring owner, start/stop/drain, error recovery와 counters.
2. `hardware/stm32/kitel2026final/Core/Src/stm32f4xx_it.c`: `USART1_IRQHandler`에서 bounded handler 호출.
3. `hardware/stm32/kitel2026final/Core/Inc/main.h`: ISR handler export.
4. `hardware/stm32/kitel2026final/Core/Inc/stm32f4xx_it.h`: IRQ prototype.

MSP, `.ioc`, DMA 설정, linker script, HAL driver는 변경하지 않는다. NVIC enable/disable은 RX lifecycle owner가 explicit하게 수행한다. 새 persistent state나 host/server migration은 없다. 동일 V1/V2/V3 및 FRAME bytes와 9600/115200 baud를 유지하므로 on-wire compatibility 영향은 0이다.

## 6. Rollback

수정 전 production target build ELF `4dada4bfc79d9d4d387ac2e8b498a1036ac5ad138166c7cb45f5a38a2aa9a997`와 historical H0 ELF `62ecee2c...6c05`를 C: evidence에 보존한다. Candidate flash 전에 source/build/ELF hash와 readback을 기록한다. Candidate 실패 시 먼저 수정 전 production ELF를 지정 ST-Link `0670FF485775495067203341`에 download/verify/reset하고, 그 결과를 새 evidence에 기록한다. DB, Laptop repository와 기존 evidence에는 rollback mutation이 없다.

## 7. Targeted regression과 hardware 재검증 비용

수정 전/후 compiled fixture:

- 한 pump 전에 complete FRAME 여러 개 enqueue 후 원래 순서로 parse.
- motor-change 0/일부/20개 apply 동안 들어온 최신 complete FRAME 보존.
- injected ORE/FE/NE 및 ring overflow line의 atomic reject와 다음 line 회복.
- oversize line과 suffix discard 기존 회귀 유지.
- V3 handshake 뒤 초기 mode ACK, duplicate ACK, DOWN A/R ordering/reconnect 유지.

Target build 및 실제 hardware:

1. CubeIDE clean target build 1회, candidate flash/verify 1회.
2. 2A normal-rate packet set 최대 8 FRAME, reset 최대 2회. ORE/FE/NE/ring overflow 0, exact parse, expected PCA apply가 필요하다.
3. 물리 clear는 별도 cell/top/bottom 관측으로 판정한다. RX 통과가 residual clear를 면제하지 않는다.
4. fresh H2 1회: console→S0→actual audio+normal-rate FRAME→physical cells.
5. fresh H3 1회: 실제 V3 controls+audio+braille+reconnect. 현재 UP/CONFIRM/MODE wiring failure가 먼저 해결돼야 한다.
6. G3-A를 candidate source로 1회 반복한다. Camera code는 건드리지 않지만 H4는 fresh H1 page-change blocker와 H2/H3가 모두 해결된 후 1회 전체 재수용한다.

예상 비용은 target build/flash 1세트, 2A hardware run 1세트, G3-A/H2/H3 각 1회, 최종 H4 1회다. 새 UART error나 overflow가 발생하면 그 run은 FAIL이며 반복 성공으로 덮지 않는다.

## 8. 병행하지 않는 항목

- `ACTUATOR-CLEAR-RESIDUAL-P1`: exact parse/PCA success 뒤 동일 형태가 남는 별도 hardware/mechanics/calibration 경계다. cell/top/bottom 관측과 PWM·전원·기구 측정 전 LUT/angle/channel을 바꾸지 않는다.
- UP, CONFIRM, MODE physical failures: wiring/continuity 작업이며 IRQ 변경에 포함하지 않는다.
- H1 page-change liveness, native audio, CLI fatal 처리는 이 firmware change에 포함하지 않는다.
- Authentication/TLS, scanner N/K/identity/duplicate threshold와 production 8초 timeout은 변경하지 않는다.

이 packet의 product source modification count는 **0**이다.
