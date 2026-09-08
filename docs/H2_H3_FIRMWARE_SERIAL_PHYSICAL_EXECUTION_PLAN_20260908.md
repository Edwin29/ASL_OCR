# 1C / 2A / 4 Firmware·Serial·Physical Controls 및 H2/H3 실행 계획

작성일: 2026-09-08  
상태: **계획·절차 점검 완료 / flash·servo 구동·새 product 수정 미실행**

기준 문서: [현재 우선순위](H123_CURRENT_STATUS_AND_DEMO_PRIORITIES_20260908.md), [공통 run manifest](DEMO_RUN_COMMON_MANIFEST_20260908.md), [H2 결과](HARDWARE_INTEGRATION_H2_STATUS_20260908.md), [H3 결과](HARDWARE_INTEGRATION_H3_STATUS_20260908.md), [H3-R 결과](HARDWARE_INTEGRATION_H3_READING_OUTPUT_STATUS_20260908.md), [STM 진단 work packet](work-packets/H123_DIAG_STM_INTEGRITY_WORK_PACKET_20260908.md).

## 1. 결론과 실행 순서

실행 순서는 **1C firmware/build/rollback·배선 preflight → 2A normal-rate transport boundary 진단 → 원인별 제한 수정 또는 hardware 조치 → fresh H2 → fresh H3**로 고정한다. H2와 H3는 서로 다른 경계를 검증하므로 합산하거나 대체하지 않는다.

1. **1C는 2A의 선행 gate다.** 현재 보드에서 마지막으로 flash/verify된 ELF는 수정 전 이미지다. 최신 `main.c`의 malformed FRAME atomic reject, overflow suffix discard, PCA apply result 관측은 Windows HAL fixture에서만 통과했다. 최신 소스를 STM target으로 빌드하고, rollback ELF를 실제로 보존했는지 확인한 뒤에만 flash한다.
2. **2A는 수정 선택 gate다.** Host TX, HC-05 wire, MCU RX/line assembly, parser, PCA, physical cells를 같은 FRAME으로 연결한다. 측정 전 UART DMA/IRQ 또는 pacing을 해결책으로 선택하지 않는다.
3. **fresh H2는 출력 경계 수용이다.** Console input, production DeviceApplication/Coordinator/S0/audio, production STM presenter, HC-05, STM/PCA/servo를 normal rate로 결합한다. 물리 GPIO는 우회했다고 명시한다.
4. **fresh H3는 production 물리 입력·출력 수용이다.** `python -m asl_device`, V3 physical controls, actual speaker, normal-rate FRAME, physical cells, reconnect/re-entry/restart를 한 run에서 확인한다.
5. 1C/2A/H2/H3가 통과해도 fresh H1의 page-change blocker가 남아 있으므로 H4에는 진입하지 않는다. H4는 동일한 최종 source/config/firmware identity에서 fresh H1/H2/H3가 모두 통과한 뒤에만 수행한다.

비안전 실패가 발생해도 독립적으로 실행 가능한 검사는 계속한다. 예를 들어 PAGE NEXT 배선이 실패해도 UP/DOWN/LEFT/RIGHT와 FRAME/PCA 검사는 계속한다. 다음 단계의 의미를 잃는 의존성은 `skipped_due_to_<issue>`로 기록한다. 제어되지 않는 움직임, 기계적 걸림, 발열, 냄새, 비정상 전원, 통신 폭주만 즉시 전체 구동을 중단한다.

## 2. 현재 identity와 재사용 가능한 증거

| 항목 | 현재 고정 가능한 사실 | 새로 확인할 사실 |
|---|---|---|
| Firmware source | `hardware/stm32/kitel2026final/Core/Src/main.c` SHA-256 `c4bb35e208bf2bdcd4e773c4a40f5a5982ff0333e479340bcd9b6fa1c996371f`; CubeIDE project metadata와 `.ioc`가 repository에 있음 | Laptop source copy의 같은 hash, clean target build 결과 |
| Latest source verification | HAL stub fixture에서 invalid reject, overflow recovery, PCA failure 관측, same-frame bus recovery PASS | STM target binary 실행과 실제 UART/I2C timing |
| Historical flashed image | H0의 `kitel2026final.elf` SHA-256 `62ecee2ccc811cf046466d38e80001f959f27a6f256f803903769289b9556c05`; download/verify/reset PASS | 파일이 원래 C: evidence 위치에 보존됐는지, 현재 board가 여전히 그 image인지 |
| Board/tool identity | NUCLEO-F446RE, device ID `0x421`, ST-Link `0670FF485775495067203341`, H0 전압 3.24 V, CubeIDE 2.2.0, CubeProgrammer 2.23.0 | 새 run의 실제 probe/전압/tool/version |
| Serial | HC-05 `COM9` 9600, debug `COM5` 115200; H0 V3 handshake PASS | 새 run의 port ownership, V3 handshake, normal-rate FRAME integrity |
| Host transport | bounded read, complete-line ACK, release ordering, reconnect/close tests PASS | real COM/HC-05에서 동일 contract |
| Controls | PA0 UP, PA1 DOWN, PA4 LEFT, PB0 RIGHT, PB1 NEXT, PC0 PREVIOUS, PC1 CONFIRM, PC2 MODE; active-low/pull-up | installed labels·continuity·GPIO transition. 과거에는 PB1 무반응, CONFIRM 조작이 PC0, PC2 solder 단선 |
| PCA/cells | `0x40` CH0..9 top, `0x41` CH0..9 bottom; paced known frame physical movement PASS | normal-rate apply, 셀·dot 방향, all-zero clear 잔류 0 |
| Audio | 1B actual Realtek/Piper/system cue/supersession/restart PASS | STM presenter와 physical controls가 함께 활성인 H2/H3 |

기존 H2의 손상된 FRAME과 20 ms/byte 성공은 2A의 비교 evidence로 유지한다. 20 ms pacing 결과를 production 수용으로 올리지 않는다. H3-R의 physical DOWN follow-up packet `NAV,D,S,2`는 V2 SHORT이므로 V3 `ACTIVATED/RELEASED` 수용에 사용하지 않는다.

## 3. 완료 상태의 구분

모든 run은 다음을 별도 열로 기록한다.

| 상태 | 의미 |
|---|---|
| host write completed | Laptop이 FRAME 또는 ACK 바이트 전부를 serial driver에 제출 |
| input accepted | Host가 완전한 V3 NAV를 ACK하고 dedupe/queue에 수락 |
| S0 command completed | 해당 input의 operation/cursor/generation이 server에서 완료 |
| firmware parsed | STM이 완전한 FRAME을 검증하고 requested state를 commit |
| PCA applied | 해당 generation의 모든 필요한 PCA write가 성공하고 `last_frame_apply_ok=1` |
| physically observed | 사용자가 예상 셀의 돌출·복귀 또는 예상 음성을 실제로 관측 |

`ACK,<sequence>`는 input accepted이며 S0 완료나 physical apply가 아니다. Host FRAME write, STM parse, PCA HAL_OK, physical cells도 서로 대체하지 않는다.

## 4. 1C — firmware identity, target build, rollback, bench 준비

### 4.1 Evidence root

Laptop C:에 다음 새 root를 사용한다.

`C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\fw-preflight-<fresh-run-id>`

`C:\ASL_OCR_INTEGRATION`은 read-only source로 사용한다. Target build는 firmware project를 새 evidence root의 `firmware-build\source`로 복사한 뒤, 별도 CubeIDE workspace에서 수행한다. 기존 repository의 `Debug/`, source, state 또는 evidence를 덮어쓰지 않는다. Laptop D:에는 접근하지 않는다.

### 4.2 Flash 전 순서

1. 공통 manifest의 Desktop/Laptop source identity를 재확인하고, Laptop `main.c` hash가 `c4bb...371f`인지 확인한다.
2. H0 rollback ELF 원본이 아래 위치에 존재하고 hash가 `62ec...6c05`인지 확인한다. 없거나 hash가 다르면 flash하지 않는다.
   - `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h0-20260907-205411\firmware-build\source\kitel2026final\Debug\kitel2026final.elf`
3. 현재 board flash identity는 standalone verify가 가능하면 historical ELF의 load sections와 비교한다. 그렇지 않으면 flash load-address 범위를 새 C: evidence로 read back하여 byte 비교한다. readback이 불가능하면 현재 image는 `unverified`로 유지하며 추정으로 바꾸지 않는다.
4. 최신 project copy를 CubeIDE 2.2.0 headless clean build한다. build log, source tree hash, `.elf/.bin/.map` 길이와 SHA-256, error/warning count를 기록한다.
5. 최신 ELF와 historical rollback ELF를 모두 immutable evidence로 식별하고 rollback 명령·대상 ST-Link serial을 기록한다.
6. 다른 process가 COM5/COM9를 점유하지 않는지 확인한다. 과거 H3에서 남은 H2 process가 COM9를 경쟁한 일이 있으므로 port owner가 하나가 아니면 시작하지 않는다.
7. 전원을 끈 상태에서 실제 label과 continuity를 아래 표로 확인한다. 배선이 contract와 다르면 software pin map을 바꾸지 않고 hardware/wiring issue로 기록한다.

| 물리 기능 | MCU pin | 기대 idle/active | 필수 관측 |
|---|---|---|---|
| UP | PA0 | HIGH / LOW | isolated press에서 PA0만 전이 |
| DOWN | PA1 | HIGH / LOW | press와 release 모두 전이 |
| LEFT | PA4 | HIGH / LOW | isolated press에서 PA4만 전이 |
| RIGHT | PB0 | HIGH / LOW | isolated press에서 PB0만 전이 |
| PAGE NEXT | PB1 | HIGH / LOW | 과거 무반응 원인 분리 |
| PAGE PREVIOUS | PC0 | HIGH / LOW | CONFIRM 조작과 교차되지 않음 |
| CONFIRM | PC1 | HIGH / LOW | short/long 동안 PC1만 전이 |
| MODE | PC2 | maintained LOW/HIGH | solder 복구와 두 안정 상태 확인 |

### 4.3 Flash와 smoke check

Flash는 위 항목이 모두 준비되고 사용자가 공통 전원 비상 스위치와 board 상태를 확인한 뒤 수행한다. 최신 ELF를 지정 ST-Link에 download/verify/reset하고, COM5에서 PCA `0x40/0x41` presence/init를 확인한다. 이 smoke 단계는 servo FRAME을 보내지 않는다.

예상 packet과 상한:

- STM→Host `HELLO,3\n`: 정상 1회, reset/reconnect 포함 최대 3회.
- Host→STM `ACK,HELLO,3\n`: HELLO마다 1회, 최대 3회.
- STM→Host 초기 maintained lever `NAV,V,A,1\n` 또는 `NAV,V,R,1\n`: reset당 1회.
- Host→STM `ACK,1\n`: 초기 mode packet을 수락한 경우 1회.
- 이 단계의 FRAME: **0개**.

Smoke 실패 시 최신 image 재시도 반복으로 통과시키지 않는다. 로그를 보존한 뒤 historical ELF `62ec...6c05`를 지정 ST-Link에 다시 download/verify/reset하고, rollback 결과를 새 evidence에 기록한다. Historical image로 돌아간 상태에서는 H2/H3를 합격 처리하지 않는다.

### 4.4 1C 완료 조건

- latest source copy → clean target ELF → flashed image의 chain과 hash가 일치한다.
- rollback ELF가 실제로 존재하고 verify 가능한 절차가 기록된다.
- COM5/COM9 owner, baud, ST-Link, PCA startup이 고정된다.
- 8개 control의 label/continuity 결과가 채워진다.
- 안전 관측과 stop switch가 준비된다.

## 5. 2A — Host↔STM normal-rate transport/RX/parser/PCA 진단

### 5.1 목적과 원칙

첫 불일치를 `Host payload → serial write → HC-05/PA10 wire → MCU receive/line assembly → parser commit → PCA result → physical cells` 중 하나로 고정한다. Debug UART의 blocking 출력이 timing을 바꿀 수 있으므로 per-byte debug 출력은 추가하지 않는다.

우선 현행 production image로 passive trace를 수행한다. 외부 logic analyzer/USB-UART tap이 있으면 PA10 wire를 읽기 전용으로 관측한다. 장비가 없고 COM5 assembled-line log만 확보되면 wire와 MCU byte service 사이 root는 `insufficient_evidence`로 남긴다. 그 경우 DMA/IRQ를 구현하지 않는다.

### 5.2 Deterministic packet set

Fresh reset/handshake 뒤 다음 packet을 normal 9600-baud write로 보낸다. byte pacing override는 사용하지 않는다.

1. `HELLO,3\n` → `ACK,HELLO,3\n`
2. 초기 mode `NAV,V,A,<seq>\n` 또는 `NAV,V,R,<seq>\n` → `ACK,<seq>\n`
3. known math:
   `FRAME,0,16,0,0,110,11,38,45,52,18,18,54,55,60,1\n`
4. 위 known math를 동일 bytes로 1회 반복해 unchanged-motor/cache 경로를 확인한다.
5. clear:
   `FRAME,0,17,0,0,111,0,0,0,0,0,0,0,0,0,0\n`
6. 위 clear를 동일 bytes로 1회 반복한다.

Reset 직후 첫 valid FRAME은 firmware motor cache가 unknown이므로 최대 20 motor update 경로다. 동일 FRAME 반복은 0-change 경로, math→clear는 일부/다수 change 경로다. 실제 changed count와 PCA call/result를 측정해 기록하고 미리 추정값으로 채우지 않는다.

HC-05 path의 deterministic FRAME은 handshake 후 최대 8개, reset은 최대 2회다. HC-05에서 손상이 재현될 때만 같은 네 payload를 direct UART 9600 path에서 최대 8개 비교한다. 전체 2A에서 servo를 바꾸는 FRAME은 최대 16개이며, 예상 밖 반복이나 queue 폭주는 즉시 중단한다.

### 5.3 기록 항목

- Host: monotonic/UTC, payload bytes/length/SHA-256, write start/end, write return length, source snapshot/generation.
- Wire: 가능하면 PA10 bytes와 timestamp. Logic analyzer가 없다는 사실도 기록한다.
- MCU: COM5 assembled `BT RX`, `FRAME FORMAT ERROR`, nav state, `last_frame_apply_ok`, `last_applied_generation`, `pca_apply_failures` 전후.
- Timing: FRAME 사이 간격, parser 진입/종료, PCA batch 적용 시간. 현행 source로 직접 관측할 수 없는 ORE/FE/NE 또는 max service gap은 `not_observed`로 둔다.
- Physical: 10 cell 각각 top/bottom의 expected/raised/cleared를 사용자 관측표에 기록한다. `unknown`을 PASS로 바꾸지 않는다.

### 5.4 First-failure 분기

| 최초 불일치 | 분류와 다음 작업 |
|---|---|
| Host payload/write 이전 | Host local defect. `stm_serial.py` serializer/ordering/reconnect만 bounded reproducer 후 수정 |
| Host write exact, PA10 wire 손상 | HC-05/radio/power/baud/wiring environment 또는 hardware. Direct UART 비교 후 firmware 변경 보류 |
| PA10 wire exact, MCU assembled line 손상 | Firmware servicing risk. ORE/FE/NE와 service gap을 관측하는 diagnostic-only counter 설계를 먼저 제출 |
| MCU line exact, parser reject/state mutation | `main.c` parser local defect. 한 파일 targeted fixture/target build 후보 |
| Parser exact, PCA apply failure | I2C/power/address/timing boundary. HAL 결과와 bus를 분리하고 applied로 보고하지 않음 |
| PCA apply success, 물리 pattern/clear 실패 | hardware/wiring/mechanics/calibration. cell/top/bottom/PWM 실측 전 LUT·각도·channel 변경 금지 |

Wire exact + RX loss가 확인되어 IRQ/ring이 필요해 보이면 즉시 구현하지 않는다. Design packet은 최대 4 production files(`main.c`, 필요한 IRQ/MSP/header), ISR의 byte enqueue/error flag와 main-context parser/PCA 책임, V3/FRAME grammar 완전 호환, old image rollback, H2/H3/H4 재수용 비용을 먼저 제시한다. DMA/IRQ 선택은 ORE/service-gap 계측 결과로 결정한다.

### 5.5 2A 완료 조건

- 최소한 Host TX와 STM assembled line, parser state, PCA result, physical observation이 같은 payload/generation으로 연결된다.
- HC-05 normal-rate deterministic set가 무손상이어야 한다.
- known math의 셀 방향이 일치하고 exact clear 뒤 raised residual이 0이어야 H2 수용으로 진입한다.
- transport는 통과하지만 clear만 실패하면 fresh H2의 나머지 독립 검사를 수행할 수 있으나 H2 verdict는 FAIL이다.
- 원인 경계가 부족하면 `insufficient_evidence`이며 architecture 변경을 승인된 것으로 보지 않는다.

## 6. Fresh H2 — console control + actual audio + production STM output

### 6.1 Production fidelity

기존 READY revision과 stable device ID를 사용한다. Bounded custom composition에서 `ConsoleControlSource`만 input으로 주입하고, production DeviceApplication/Coordinator/S0/audio와 `StmSerialControlSource` presenter를 유지한다. Live camera/V4/S1/finalize와 physical GPIO는 우회한다. TTS OFF, FRAME suppression, byte pacing을 사용하면 해당 run은 diagnostic이며 H2 acceptance가 아니다.

### 6.2 실행 순서

1. Run-specific config/source/import/audio/COM/firmware identity와 시작 datapack/revision/cursor를 기록한다.
2. `HELLO,3 → ACK,HELLO,3`, initial/current FRAME을 확인한다.
3. Console에서 READY를 선택하고 waiver 밖 정상 수식까지 이동한다.
4. normal math snapshot의 focus/generation/audio_ref/cells와 실제 음성·Host FRAME·STM parse·PCA·physical cells를 연결한다.
5. LEFT/RIGHT로 10-cell window offset을 양 방향 이동한다. Offset은 snapshot/FRAME 숫자와 함께 기록하며 단순 음성 cue만으로 성공 처리하지 않는다.
6. PAGE NEXT/PREVIOUS, item navigation, normal text/selection의 clear를 확인한다.
7. 빠른 DOWN 5회 뒤 최종 generation의 audio와 physical FRAME만 남는지 확인한다.
8. CONFIRM replay, reading exit/re-entry, 앱 1회 재시작 뒤 stable cursor와 stale output 0을 확인한다.
9. 정상 종료의 exit code 0, serial/audio worker stopped, connection/stream close를 기록한다.

상한: console command 30회, Host FRAME 40개, 앱 재시작 1회, STM reset/reconnect 1회. 상한 초과가 필요하면 현 run을 끝내고 새 목적·상한으로 별도 run을 만든다.

### 6.3 H2 PASS

- Console event → S0 → snapshot → actual audio와 normal-rate FRAME → parser → PCA → physical cells가 같은 focus/generation이다.
- 각 FRAME은 정확히 10 cells, 각 값 0..63이다.
- known cell/dot/top/bottom 방향과 LEFT/RIGHT offset이 물리적으로 일치한다.
- rapid input 뒤 stale audio/FRAME의 최종 덮어쓰기 0이다.
- exact clear 뒤 residual raised cell 0이다.
- graceful close/restart와 stable cursor가 통과한다.

H2는 physical control acceptance가 아니며 fresh H3를 대체하지 않는다.

## 7. Fresh H3 — production physical V3 controls + audio + braille

### 7.1 진입 조건

- 1C latest firmware flash/verify와 2A normal-rate transport가 통과한다.
- PB1/PC0/PC1/PC2를 포함한 8개 control continuity가 contract와 일치한다.
- H2 actual audio+braille와 exact clear가 통과한다.
- COM5/COM9 owner가 각각 하나이며 interactive Windows audio session에서 실행한다.

배선 실패가 남으면 가능한 독립 입력은 계속 기록하되 H3 acceptance run으로 시작하지 않고 `H3 diagnostic`으로 표시한다.

### 7.2 Production path

- launcher: `python -m asl_device --config <run-specific-copy>`
- controls/presenter: production `StmSerialControlSource`
- audio: production authenticated `SoundDeviceWavPlayer`, 실제 Laptop speaker
- initial mode: 실제 maintained PC2 상태로 결정
- data: 기존 READY; live capture는 수행하지 않음
- runtime override: 없음

### 7.3 예상 V3 packets

| 조작 | STM→Host | Host→STM |
|---|---|---|
| boot/reconnect | `HELLO,3\n` | `ACK,HELLO,3\n` |
| initial/toggled mode | `NAV,V,A,<seq>\n` 또는 `NAV,V,R,<seq>\n` | `ACK,<seq>\n` |
| UP/LEFT/RIGHT/NEXT/PREVIOUS short | `NAV,U|L|R|N|P,S,<seq>\n` | `ACK,<seq>\n` |
| DOWN press/release | `NAV,D,A,<seq>\n`, `NAV,D,R,<seq+1>\n` | 각 sequence의 ACK |
| CONFIRM short/long | `NAV,C,S,<seq>\n`, `NAV,C,L,<seq>\n` | 각 sequence의 ACK |
| presentation | 없음 | `FRAME,page,node,span,offset,generation,c0..c9\n` |

Fresh reset에서 sequence는 1부터 단조 증가한다. Retry는 같은 sequence를 재사용하고 Host는 다시 ACK하되 command를 두 번 적용하지 않는다. V3에서 `NAV,D,S,<seq>` 또는 firmware-origin DOWN repeat가 하나라도 나오면 V3 acceptance FAIL이다.

### 7.4 한 번에 수행할 조작 순서

1. Boot handshake와 초기 mode packet을 확인한다.
2. Lever를 capture↔reading으로 각 1회 전환해 catalog와 음성을 확인한다.
3. UP 1회, DOWN short 5회, LEFT 1회, RIGHT 1회, PAGE NEXT 1회, PAGE PREVIOUS 1회를 non-clamp 구간에서 수행한다.
4. CONFIRM SHORT 1회로 selection/replay를 확인하고 CONFIRM LONG 1회로 reading exit 또는 selection 복귀를 확인한다.
5. DOWN을 2초간 1회 유지한다. STM A/R 각 1, STM SHORT 0, Host 즉시 1회와 650 ms 뒤 180 ms cadence, release 뒤 새 dispatch 0, 이미 in-flight 최대 1을 확인한다.
6. 정상 수식에서 same-generation audio/FRAME/physical cells, LEFT/RIGHT offset, PAGE transition, text/selection clear를 확인한다.
7. HC-05 연결을 1회 통제하여 reconnect한다. Active DOWN 없이 수행하고, 새 HELLO3/epoch 뒤 stale activation/frame/audio가 복원되지 않는지 확인한다.
8. Reading exit/re-entry 뒤 stable cursor를 확인하고 앱을 1회 재시작한다. boot/process namespace는 새 값이고 stable device cursor는 유지되어야 한다.
9. 정상 종료 exit0와 worker/serial/audio close를 확인한다. 예기치 않은 fatal이면 첫 fatal과 cleanup 결과, CLI exit2, 새 crash dump를 보존한다.

상한: 사용자 physical operation 18회, STM NAV packet 30개, Host FRAME 40개, reconnect 1회, 앱 재시작 1회. Retry를 포함해 NAV 30개를 넘거나 release 뒤 지속 전송되면 safety가 정상인 범위에서 로그를 닫고 FAIL로 종료한다.

### 7.5 H3 PASS

- 모든 필수 pin/control이 의도한 V3 packet을 생성한다.
- ACK/dedupe/order와 S0 operation/cursor/generation이 연결된다.
- DOWN A/R 및 hold/release invariant가 통과한다.
- 같은 focus/generation의 actual Piper 음성과 normal-rate FRAME/physical cells가 관측된다.
- complete clear, reconnect, reading exit/re-entry, app restart, stable cursor가 통과한다.
- old V2 packet, console/direct-serial/paced result는 이 PASS에 사용하지 않는다.

## 8. Run evidence 구조

각 단계는 새 C: root 아래 다음 파일을 남긴다. Credential 값과 hash는 기록하지 않는다.

- `manifest/run-identity.json`: source/import/config/audio/COM/firmware/board/tool identity
- `manifests/firmware-build.json`: isolated source, build command, ELF/bin/map hash, build log
- `reports/flash-verify.json`: ST-Link, image hash, verify/reset, rollback identity
- `logs/host-serial.jsonl`: exact payload hash/length/write result, ACK/NACK/NAV
- `logs/stm-com5.log`: boot, assembled RX, parser/PCA state
- `captures/uart-wire.*`: passive capture가 있을 때만
- `reports/control-continuity.csv`: switch label, pin, idle/active, pass/fail
- `reports/frame-lineage.jsonl`: snapshot→Host FRAME→MCU parse→PCA generation
- `reports/physical-observation.csv`: cell 1..10 top/bottom expected/applied/cleared와 사용자 관측 시각
- `reports/audio-observation.jsonl`: focus/generation/content heard/interruption/latest completion
- `reports/process-exit.json`: exit code, worker/connection/stream close, dump path if any
- `result.json`: 단계별 PASS/FAIL/skipped, first failing boundary, classification

## 9. 원인별 다음 수정 예산

| 결과 | 허용되는 다음 packet | 금지되는 즉시 변경 |
|---|---|---|
| Host serializer/write defect | 기존 host adapter 최대 1~2 product files, exact COM reproducer | protocol/baud/FRAME grammar 변경 |
| Wire/radio defect | HC-05 전원·배선·baud·module path 진단/교체 판단 | firmware architecture로 승격 |
| Firmware RX service defect | 먼저 counter/design packet; 구조 변경이 필요하면 최대 4 production files와 migration/rollback/H1-H4 비용 보고 | 근거 없는 DMA/IRQ 도입, host pacing |
| Parser defect | `main.c` 1파일 local correction과 compiled fixture/target build | threshold·grammar 완화 |
| PCA bus defect | I2C 전원/주소/timing 계측, 필요 시 local apply/error correction | HAL_OK 추정, channel remap |
| Physical clear/mapping defect | cell별 PWM/기구/horn/cam/continuity 실측 packet | 측정 없는 LUT·각도·channel·pin 변경 |

새 architecture layer가 필요하면 implementation 전에 변경 파일 상한, 기존 V3/FRAME 호환성, image migration, old ELF rollback, H2/H3/H4 재검증 횟수를 별도 보고한다.

## 10. 현재 판정

| 범위 | 현재 판정 | 근거 |
|---|---|---|
| Host STM transport architecture | `architecture_sound_with_local_defect`에서 local correction 완료, physical acceptance open | bounded read/ordering/reconnect tests PASS; real HC-05 미검증 |
| Firmware parser/PCA requested-vs-applied | `architecture_sound_with_local_defect`, source correction 완료·target deployment open | HAL fixture PASS, board image 불일치 |
| Firmware polling RX servicing | `insufficient_evidence` | normal-rate corruption과 paced PASS는 있으나 wire/ORE/FE/NE/service-gap 동시 증거 없음 |
| Physical controls | `hardware_or_wiring` open | PB1 무반응, PC1 대신 PC0 packet, PC2 solder 단선 |
| Physical clear | `hardware_or_wiring` 또는 calibration risk, exact root open | exact zero FRAME/PCA 뒤 동일 residual 2/2 |
| Fresh H2/H3 | `not_run` on corrected final identity | 과거 H2/H3는 각각 transport·controls·audio/clear 실패 |

이번 계획 작성 중 product source modification count는 **0**이다. Firmware flash count와 servo FRAME count도 **0**이다.
