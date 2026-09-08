# Proposed bounded implementation packet B — STM receive integrity

상태: **제안만 작성; 구현/flash 미승인·미실행**. 근거: [진단 보고서](../H1_H2_H3_SOFTWARE_DIAGNOSTIC_RESULT_20260908.md) §2/3/6/7.

## 두 독립 correction 범위

**B0 — host release ordering (confirmed_product_defect).** Real host worker가 HELLO3→UP×16→DOWN A/R를 ACK한 뒤, release 우선 queue가 poll16 배치 경계를 넘어 activation을 추월한다. Physical release 뒤 HoldRepeatController가 다시 활성화되는 새 확인 결함이다. 이는 RX byte loss와 다른 root이며 **별도 subcommit/독립 승인 항목**이다.

**B1 — MCU receive integrity (probable_product_risk; 사건 exact root 미확정).** Production 및 direct burst/3 ms FRAME이 손상되고20 ms는 exact다. Polling receive와 debug/control-TX/servo batch delay가 충돌할 가능성은 높지만 UART ORE/FE/NE 또는 HC-05 wire comparison이 없다. Interrupt/DMA patch를 선결정하지 않는다.

## Inputs

- Host `device-runtime/src/asl_device/adapters/stm_serial.py`, `hold_repeat.py`, `application.py`.
- Authoritative `hardware/stm32/kitel2026final/Core/Src/main.c`, UART IRQ/MSP files. Legacy `document-parser/hardware/stm_pi_bridge` 사용 금지.
- [Raw evidence bundle](../evidence/software-diagnostic-20260908/raw-evidence.json), [H2 hash reconciliation](../evidence/software-diagnostic-20260908/h2-hash-reconciliation.json), [Laptop reproducer results](../evidence/software-diagnostic-20260908/laptop-reproduction-results.json).
- [Firmware models](../evidence/software-diagnostic-20260908/firmware-model-results.json)은 **compiled MCU test가 아니다**. 현재 H0 flash ELF identity는 역사적 evidence이며 fresh artifact/readback 확인이 필요하다.

## B0 minimal patch / regression

Host adapter1 production파일 우선; 실제 필요성이 재현될 때 hold_repeat까지 최대2파일. Batch 전체에서 temporal/epoch order를 보존하거나 이미 release된 activation이 나중에 hold를 켜지 못하게 한다. release responsiveness를 늦춰 해결하지 않는다.

Regression: backlog15/16/17/128, multi A/R cycles, same-sequence retry, BUSY/full queue, HELLO/reconnect force release, process namespace, old-epoch activation. ACK semantics 유지, physical release 후 late repeat0, accepted command order 보존. 기존650/180 ms cadence와 all button mappings 유지.

## B1 diagnosis prerequisite

1. Exact host write bytes와 STM receive bytes를 동시에 계측한다. ORE/FE/NE/line overflow counter와 timestamp를 별도 둔다.
2. Handshake→ACK+FRAME back-to-back, motor-change0/일부/20개, bounded sustained traffic을 분리한다.
3. Same baud/grammar로 HC-05 경로와 direct UART 경로를 비교한다. Source 모델의 loss count를 실측 count로 인용하지 않는다.
4. Compiled current-C/HAL stub test에서 line split/oversize/suffix/newline recovery를 먼저 재현한다. `X×256 + FRAME… + LF` suffix acceptance model을 actual code test로 승격한다.
5. PCA I2C HAL_ERROR/TIMEOUT이 current parse/log와 실제 application을 어떻게 구분하는지 stub으로 확인한다. 현재 clear residual을 calibration 오류로 미리 단정하지 않는다.

## B1 conditional implementation budget

Receive defect가 확정될 때만 main.c + 필요한 UART IRQ/MSP를 포함해 최대3 production파일. IRQ 또는 DMA의 bounded byte ring은 측정 근거로 선택한다. ISR/callback은 enqueue/error flag만, main context가 completed line/parser/PCA를 수행한다. Overflow는 affected line 전체 폐기, 다음 newline에서 복구한다. Line parser의 side effect 이전 validate 필요성도 compiled test로 입증된 경우만 별도 작은 변경에 포함한다.

동일 packet의 B0 host ordering patch와 독립적으로 검토/회귀한다. RX reliability를 host20 ms pacing, baud 변경, ACK 지연·dedupe 완화, FRAME grammar/cell encoding 변경으로 대신하지 않는다. New architecture layer/광범위 driver 교체는 budget 초과다. Pin map, LUT, servo angle, stable device ID 변경0.

## Hardware validation declaration — 실행 전에 재보고

Evidence root: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics\stm-rx-<fresh-id>`. Exact board/ST-Link, image source/build/ELF hash, flash verification, COM mapping, baud를 고정한다.

예상 packet: `HELLO,3`→`ACK,HELLO,3`; physical input에는 `ACK,<seq>`. Approved normal-math fixture는 `FRAME,0,16,0,0,110,11,38,45,52,18,18,54,55,60,1\n`; clear는 `FRAME,0,17,0,0,111,0,0,0,0,0,0,0,0,0,0\n`. 고정 generation은 isolated diagnostic fixture이며 S0 fresh transaction을 뜻하지 않는다. 실제 actuation 전에 operator가 pattern/stop 준비를 확인할 수 있게 제시한다.

Stop: 첫 malformed/lost frame, UART overflow/error, unexpected actuation, jam/heat/noise, incomplete clear, missing release/extra repeat. Controlled failure가 발생하면 root를 기록하고 자동 재시도로 PASS를 만들지 않는다. Flash/actuation은 이 문서 생성 자체로 실행 승인되지 않는다.

## Completion

B0 targeted+device subsystem PASS; B1 production-rate back-to-back/max-valid FRAME exact parse 및 motor-change20 중 다음 최신 frame 보존; malformed/overflow recovery; V3 handshake/ACK/dedupe/release/reconnect 모두 재검증. Direct UART만 PASS하고 HC-05가 FAIL이면 radio/power/bridge boundary로 재분류하고 firmware redesign을 중단한다. Fresh H2/H3와 physical clear 측정 전 H4 blocker 유지.
