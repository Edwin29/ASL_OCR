# 하드웨어팀 자료 검토 및 H1 이후 시험 재개 계획

작성일: 2026-09-14. 상태: 후속 구현 및 정적 검증 완료, flash·물리 재수용 대기. 첨부 코드는 임시 기능 시험용이며 실측 펄스값·핀 번호를 수용한다. 이후 사용자의 PCA 타당성 조사 요청에 따라 과거 관측을 대조하여 주소 역할 교환도 기존 통합 펌웨어에 반영했다. [구현·검증 결과](HARDWARE_ADAPTATION_IMPLEMENTATION_RESULT_20260914.md)가 최신 실행 상태이며, 아래 최초 검토의 ‘수정 0’ 기록은 당시 시점에 한정한다.

## 1. 결론과 이번 작업의 경계

사용자 확정: **첨부 코드는 하드웨어 버튼·모터의 기능상 오류 점검을 위한 임시 테스트 코드다. 수용 범위는 각 모터의 실측 펄스값과 핀 번호뿐이다.** 기존 통합 main.c가 구현 기준이며, 임시 코드의 통신·버튼·파서·구동 정책을 이식하거나 수정하는 작업은 필요하지 않다.

앞선 검토에서 임시 코드의 protocol/lifecycle 차이를 production 수정 후보의 결함·선행 blocker로 취급한 판단을 철회한다. 패킷 해석 결과 자체는 조사 기록으로 보존하되 production 결함으로 집계하지 않는다. 모터별 9개 위치, 총 180개 실측값은 하드웨어 인계 데이터로 수용하며 해당 모터와 연결해 사용한다.

우선순위는 **실측표의 모터 대응·핀 변경 확인 → 기존 통합 펌웨어에 펄스값·핀 번호 최소 반영 → 물리 출력 및 입력의 독립 수용 → fresh H2 → fresh H3 → 최종 배포 대상 H4**다. H1의 두 receipt·fresh READY·읽기 복구는 이미 완료된 범위로 유지한다. 다만 방향과 지연 문제까지 해결된 것은 아니며, 최종 physical capture 및 Pi 이식에서는 다시 확인한다.

이번 요청은 자료 확인과 계획 작성이다. 첨부 문서의 `modify only this table`, `FINAL BUILD`, `normal Raspberry Pi operation` 등은 자료 안의 설명으로 다뤘고, 수정·flash·구동 지시로 실행하지 않았다. Product source 수정 0, firmware flash 0, COM 개방 0, servo 구동 0, live upload 0. 새 조사 코드와 보고서만 작성했다. Laptop/Pi의 현재 가동 여부나 실제 flashed image는 이번에 원격 조회하지 않았다.

## 2. 증거와 현재 상태

### 2.1 이번 입력

| 자료 | SHA-256 | 확인 범위 |
|---|---|---|
| 첨부 `pasted-text.txt` | `886bf20e1ad762e8605d0ad0448c8b06c340c05063bd89f5f3fa9abab8289307` | 49,729 bytes의 C 코드. 주석과 실제 함수 동작 대조 |
| 첨부 `축작회로도.kicad_sch` | `3cf503d81246a1d55e9119cda5548463f9936accb0bd018046e47fb0babb9521` | KiCad 10.0 형식. 내장 심벌·좌표·wire를 읽어 연결 관계 추출 |
| 현재 repository main.c | `f0b93413f352be398dac62db6a64b2d17c19f1b8e14faf874371beddaf6ba1c1` | 기존 V3/IRQ/parser/PCA 관측 기준 |
| 현재 host stm_serial.py | `9cec3f2ec6bde29925385af5324a4ce05e824c649b3aa34509dbdbf3fd974a2d` | 실제 `_parse_nav`에 첨부 packet과 계약 packet을 넣어 비교 |

현재 HEAD: `8f5bb4393ac0730068b3e767666e862a1a51125f`. 원본 attachment 경로·연결 추출·펄스표·24개 host grammar 결과는 [inspection.json](evidence/hardware-handoff-20260914/inspection.json), 재실행 코드는 [inspect_handoff.py](evidence/hardware-handoff-20260914/inspect_handoff.py)에 보존했다. attachment 원본과 product 파일은 수정하지 않았다.

사용자 후속 확인: **“테라텀 단독 시험. 첨부 코드가 그대로 올라가있음. 전원 투입 및 clear 확인까지만 된 것으로 알고 있음.”** 따라서 첨부 코드의 적용은 사용자 보고로 확인하고, binary hash 검증과 구분한다. 전원/CLEAR는 보고된 관측 결과이며 60점별 기록·state 0/8 출발 조건·반복 횟수는 미제공이다. 버튼과 실제 HC-05 연결, production 입력/출력은 검증됐다고 간주하지 않는다. CLEAR가 부팅의 자동 초기화인지 USART2 FRAME 명령인지도 아직 구분되지 않는다. `TERATERM_TEST_MODE=0`에서도 startup CLEAR와 USART2 debug 출력이 있으므로, Tera Term 사용 자체가 test mode=1을 증명하지 않는다.

회로 연결 추출은 독립 조사 도구의 기하학적 읽기 결과이며 KiCad ERC, 회로 시뮬레이션, 실제 continuity 또는 header 사양 검증이 아니다. 검사 도구는 이번 자료의 내장 심벌·회전·mirror·wire endpoint·junction을 사용했다. 측정 장비·원시 파형·전체 firmware project·ELF/flash hash는 첨부되지 않았다.

### 2.2 과거 시험에서 재사용할 결과와 남은 부분

| 경계 | 보존할 사실 | 새로 필요한 사실 |
|---|---|---|
| [정렬 후 fresh H1](H1_FRESH_ALIGNED_RUN_20260908.md) | 두 durable V4 receipt, 네 S1 fragment ready, 새 datapack revision 1 게시, 생성/저장 안내 청취; 새 READY의 이동·재진입·앱 재시작 cursor/audio 복구 | 물리 CONFIRM/lever 경로, 당시 portrait 변화와 긴 두 번째 spread 대기, 해당 launcher 종료 코드·한글 로그 fidelity |
| [1B audio](AUDIO_CONSOLE_1B_RUN_20260908.md) | actual Piper/system cue, 정상·빠른 이동, offset 10→20→10, 재진입·재시작·정상 close PASS | 같은 run에서 STM 및 physical controls와 결합 |
| [기존 1C/2A](H2_H3_FIRMWARE_SERIAL_PHYSICAL_STATUS_20260908.md) | 기존 polling RX 손실 원인과 IRQ ring 후보 basic/stress·aligned image PASS | 새 최종 firmware에서도 보존됐는지 확인. 기존 PASS는 첨부 펌웨어의 PASS가 아님 |
| 기존 CLEAR·mapping | 정정된 잔류 패턴과 PCA role 관측을 보존 | 새 정렬·실측표에서 정확한 점 출력과 CLEAR 복귀. 주소/열 역할 변경은 자동 수용 대상 아님 |
| UP·기타 버튼 | 기존 UP 무응답, 이전 시점 UP 정상, CONFIRM/PREV 교차·MODE 문제를 기록 | 새 GPIO/배선에서 각 버튼의 packet→app 의미와 hold/release 재수용 |
| H2/H3/H4 | 독립 진단/부분 경계 증거만 있음 | 최종 identity에서 전체 결합 수용 |
| Pi 4 | Laptop 검증 뒤 Pi로 Device/Scanner 역할을 이식하는 계획 | OS/ABI/의존성·AUX·Bluetooth·camera cadence·서비스 실행과 실제 H4 |

9월 8일 초기 우선순위의 “H1 미완료”, “RX 아직 원인 미확정”은 이후 결과로 갱신해서 읽어야 한다. 오래된 계획의 hash/COM/PID를 지금의 identity로 복사하지 않는다.

## 3. 하드웨어 변경 검토

### 3.1 펄스표와 기구 상태

- 첨부 190–216행: PCA별 10×9 표. 각 행은 증가하며 전체 범위는 513–2598 μs. 행마다 증가 간격이 다르다. 기존 `700–2300 μs` 공통 선형 계산을 개별 실측값 조회로 바꾼 것이 실제 코드 차이다.
- 첨부 824–882행의 state 5/6/7→CLEAR 시 180도 index8 선택과 PWM 반올림은 **임시 코드의 로직으로 수용 범위 밖**이다. 180도 실측값은 데이터로 보존하되, 기존 state 0..7 대응을 유지하고 논리 CLEAR는 기존 0도 위치의 실측값을 사용한다. 이전 상태에 따른 CLEAR 끝점 전환은 도입하지 않는다.
- CLEAR는 낮은 상태·높은 상태 뒤 모두 확인한다. 기존 흐름의 최종 수납·반복 CLEAR를 검증하는 것이며 180도 wrap 동작의 수용 시험은 아니다. 실제 모터와 실측표 행의 대응 및 최종 통합 경로의 물리 정확성은 재확인한다. 측정 자체를 재수행하는 것을 선행 조건으로 삼지 않는다.
- `BOTTOM_REVERSE_LUT={0,4,2,6,1,5,3,7}`와 `SERVO_STATE_LUT=0..7`은 기존 source에도 있다. 오른쪽 bit reversal을 이번에 처음 추가한 수정으로 계산하거나 host에서 한 번 더 뒤집지 않는다.
- 첨부 2196–2206행의 부팅 자동 CLEAR도 수용하지 않는다. 기존 통합 main.c는 cache를 초기화하고 처음 수신한 FRAME에서 모터를 갱신한다. 아직 임시 코드가 올라간 보드를 reset하면 자동 구동될 수 있다는 운용상 주의와, 반영 후 통합 코드의 시작 동작을 구분한다. Handshake의 host 초기 FRAME도 포함해 실제 packet/구동 범위를 계획한다.

### 3.2 배선·GPIO 대응

| 기능 | 기존 통합 source | 첨부 코드/회로의 의도 | 회로 reference |
|---|---|---|---|
| UP | PA0 | PA0 | SW6 |
| DOWN | PA1 | PA1 | SW5 |
| LEFT | PA4 | PA4 | SW4 |
| RIGHT | PB0 | PB0 | SW3 |
| PAGE NEXT | PB1 | PB1 | SW7 |
| PAGE PREVIOUS | PC0 | **PB2** | SW8 |
| CONFIRM | PC1 | **PC0**, 이름 FUNC | SW2 |
| MODE | PC2, LOW=capture/HIGH=reading | **PC8**, LOW=reading/HIGH=scanning | mode |
| PCA top/left | 0x40 CH0..9 | **0x41 CH0..9** | U3/U4 중 어느 보드인지는 실물 확인 필요 |
| PCA bottom/right | 0x41 CH0..9 | **0x40 CH0..9** | 동일 |

이 표에서 수용하는 변경은 PAGE PREVIOUS=PB2, CONFIRM=PC0, MODE=PC8 등 **핀 번호**다. 표의 MODE polarity 반전, PCA 주소/역할 swap은 임시 코드의 비교 정보로만 유지하고 자동 반영하지 않는다. 기존 LOW=capture/HIGH=reading과 버튼 의미를 보존한다. 실제 lever label이나 보드/채널 대응이 이 계약과 맞지 않으면 그 사실을 별도로 기록하고 변경 필요성을 판단한다. MCU pin과 심벌 header 표기는 제출 자료를 읽은 것이며 독립 pinout 인증이 아니다.

회로에서는 U4 CH0..9가 M1..M10, U3 CH0..9가 M20..M11에 연결된다. 모터 reference 번호가 곧 cell 번호라고 추정하면 안 된다. `보드 reference → 실제 I2C 주소 → 채널 → 부착 모터/실측표 행 → C1..C10 좌우 열` 대응표가 필요하다. A0..A5 및 OE는 이 파일에서 외부 wire 연결이 없으므로 회로만으로 주소 strap이나 OE 실물 상태를 확정할 수 없다. 모듈 내부 연결의 유무도 이 자료만으로 판단하지 않는다.

회로의 servo 심벌은 `SG90_SIGNAL_ONLY`라 신호선만 표현한다. PCA VCC(logic)는 U1 +3V3, V+(servo)는 스위치를 거친 5V/E5V 및 Pi 5V 입력과 연결된 표현이다. SW1은 그 공급 경로에 있고, 별도 servo-only 차단이 가능하다는 증거는 없다. 이전 시험에서도 사용자에게서 servo-only 분리가 불가능하다고 확인했다. 이번에도 임의로 STM→PCA VCC/GND를 빼도록 지시하지 않는다. 가동 전 실제 공급·공통 GND·전체 비상 차단 방법만 하드웨어팀과 확인한다.

## 4. 임시 시험 코드와 통합 코드의 차이 — 이식 제외 기록

아래 비교는 최초 자료 검토에서 수행한 사실 확인이다. 사용자 정정에 따라 이 차이를 해결하는 수정 packet은 취소한다. 기존 통합 코드를 사용하므로 임시 코드의 프로토콜을 고치거나 host에서 받아들일 필요가 없다.

### 4.1 실제 host grammar 검사

| 첨부 코드 출력 | 현재 host 결과 | 영향 |
|---|---|---|
| `HELLO` | source상 legacy v1 연결 후 FRAME 응답 지원 | 연결 자체가 무조건 실패하는 것은 아님. V3 연결 증거는 아님 |
| `NAV,U,S`, `NAV,D,S`, `NAV,L,S`, `NAV,R,S` | 네 가지 모두 parse 성공, sequence 없음 | 구형 단발 입력은 가능; V3 ACK/dedupe/edge 수용은 아님 |
| `NAV,U,L`, `NAV,D,L`, `NAV,L,L`, `NAV,R,L` | 네 방향 LONG 모두 parse 결과 None | 첨부의 hold 후 LONG과 host 반복 입력 계약이 다름 |
| `PAGE,PREV,S/L`, `PAGE,NEXT,S/L` | 네 가지 모두 None | 페이지 버튼을 눌러도 host input event 없음 |
| `BTN,FUNC,S/L` | 두 가지 모두 None | 자료 선택·replay·finalize/종료 불가 |
| `MODE,READING/SCANNING` | 두 가지 모두 None | 실제 lever의 모드 선택 불가 |
| 대조 `NAV,P/N/C/V,...,<seq>`, `NAV,D,A/R,<seq>` | 여덟 대조 packet 모두 parse 성공 | 기존 계약의 대응 형태 확인 |

근거: [host mapping](../device-runtime/src/asl_device/adapters/stm_serial.py#L28), [legacy handshake 분기](../device-runtime/src/asl_device/adapters/stm_serial.py#L282), [실제 parser](../device-runtime/src/asl_device/adapters/stm_serial.py#L465). 이번 실행은 순수 해석기 호출이며 실제 COM·S0 명령·GPIO 시험은 아니다.

### 4.2 이전 판단의 재분류

| ID / 분류 | 첨부 source 근거와 reachable trigger | 기존 계약과 차이 / 다음 검증 |
|---|---|---|
| HF-01 / test_harness_artifact | 임시 packet과 host grammar 차이 | production defect/blocker 판단 철회. 임시 packet을 이식하지 않음 |
| HF-02 / test_harness_artifact | 임시 700ms LONG·release 처리 | production 의미 변경으로 수용하지 않음. 기존 반복·V3 DOWN A/R·CONFIRM release 유지 |
| HF-03 / out_of_scope_observation | 임시 polling RX와 FRAME 대기 | 임시 통신 코드를 수정하지 않음. 기존 IRQ/ring/비동기 전송 유지 |
| HF-04 / out_of_scope_observation | 임시 FRAME parser의 범위·구문 검사 차이 | production regression 판단 철회. 기존 strict parser 유지 |
| HF-05 / out_of_scope_observation | 임시 apply의 반환·관측 차이 | production 관측 결함 판단 철회. 기존 PCA 결과/cache 유지 |
| HF-06 / out_of_scope_observation | main.c 전체 교체 시 예상 build 불일치 | 전체 교체 계획이 없어 blocker 아님. 기존 전체 project에서 최소 변경만 build |
| HF-07 / out_of_scope_observation | 180도 wrap CLEAR와 부팅 자동 구동 | 임시 로직 이식 및 그 수용 시험 제외. index8 값은 측정 데이터로 보존 |

보드에 임시 코드가 올라간 상태라는 사용자 보고는 유지한다. 다음 통합 시험에서는 펄스값·핀 번호를 반영해 빌드한 **기존 통합 firmware**의 identity를 확인한다. 임시 코드의 Tera Term 검증과 production H2/H3는 경계가 다르다. 과거 CLEAR/controls의 P1 관측도 지우지 않고, 변경된 통합 firmware에서의 실제 결과로 후속 판정한다.

## 5. 우선순위별 실행 계획과 완료 조건

### R0 — 인계 identity와 시험 환경 고정: 바로 다음 단계

1. 임시 코드의 전체 project나 protocol 검증을 필수 선행 조건으로 요구하지 않는다. 실측표의 행→실물 모터와 핀 번호를 인계 입력으로 고정하고, 기존 통합 project의 source/build 기준을 사용한다. 현재 임시 image는 확보 가능하면 복구용으로 보존하며, flash 전 안전한 rollback 방법은 별도로 확정한다.
2. 검증은 사용자 보고상 Tera Term 단독 전원/CLEAR까지다. 버튼과 실제 Bluetooth 및 반영된 통합 firmware의 물리 출력은 새 시험 대상으로 둔다. 실측값은 재측정 없이 받아들이되, 어느 모터 값인지 대응을 확인한다.
3. 보드/채널/모터/실측표 행과 새 GPIO를 확인한다. 기존 MODE 의미를 유지하고 임시 코드의 polarity·180도 CLEAR 정책은 수용하지 않는다. PCA 주소 역할 교환은 후속 조사에서 C1/C2/C5/C10 관측에 근거해 왼쪽 0x41/오른쪽 0x40으로 반영했다. 현재 하드웨어에서 채널→셀·열 대응을 다시 관측한다.
4. Desktop production server와 Laptop `C:\ASL_OCR_INTEGRATION` interpreter 및 세 package `__file__`, config hash, stable device ID, audio 출력, COM owner/baud를 새 run에 기록한다. 기존 repository와 Laptop D:는 건드리지 않는다.
5. [기존 공통 manifest](DEMO_RUN_COMMON_MANIFEST_20260908.md)를 구조로 재사용하되 새 run의 필드를 수집한다. Desktop evidence root는 `docs/evidence/hardware-resume-<run-id>`; Laptop은 `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\hardware-resume-<run-id>`로 지정한다. credential 값은 기록하지 않는다.

완료: 실측표 행/모터 및 핀 대응, 사용할 기존 통합 source 기준, 실행/차단 조건 확인. 과거 임시 시험의 원시 로그·전체 project 미제공만으로 최소 반영 준비를 막지 않는다.

### R1 — 기존 통합 firmware 최소 반영: 후속 승인으로 구현·빌드 완료, flash 대기

반영 범위는 **기존 통합 main.c의 공통 선형 펄스 계산을 모터별 실측값 조회로 바꾸고, 핀 번호를 새 배선에 맞추는 것**이다. 기존 app/firmware 동작 계약을 유지한다.

- Hardware adaptation packet: `main.c`, `main.h`, `.ioc` 3 product 파일. 모터별 실측표와 PB2/PC0/PC8 핀 정의/init를 일치시켰다. state 0..7의 기존 위치 대응을 유지하고 실측표 8번 값은 데이터로만 보존한다. PCA 주소는 과거 물리 관측에 따라 왼쪽 0x41/오른쪽 0x40으로 교환했다. 채널·bit reversal·MODE polarity·startup 동작은 그대로 유지한다. 기존 GPIO 회귀 시험 1개 파일의 기대 핀 번호도 동기화했다.
- V3 ACK/dedupe, DOWN press/release, 다른 방향의 반복, CONFIRM release semantics, IRQ ring/error recovery, strict parser, PCA result/cache는 유지한다. 5초 FRAME 대기를 새로 도입하지 않는다.
- 기존 IRQ 네 파일을 덮어써 재구축하지 않는다. 세 파일 상한 밖의 실제 필요가 발견되면 변경 목록·이유를 재제출한다. 새 architecture layer, host protocol 변경, DMA 전환은 이 packet에 포함하지 않는다.
- 기존 보드에서 검증된 hardware image를 rollback으로 보존한다. 옛 배선/옛 공통 선형각의 과거 ELF를 새 정렬에 무조건 flash하는 것을 rollback으로 정의하지 않는다. 공급 차단과 배선·calibration 일치 여부를 포함해 되돌림 범위를 고정한다.
- 검증: 각 모터/state가 정확한 실측값을 선택하는지, 기존 PWM 변환과 실패 시 cache/재시도가 유지되는지, GPIO 정의/init 일치 및 기존 host V3/dedupe/release 계약 보존 → clean STM target build → flash identity 확인. 기존 parser/RX suite는 영향받는 build의 회귀 확인으로 사용하며 임시 parser/RX 재구현 테스트로 확대하지 않는다.

완료 조건: 위 invariant를 보존하는 최소 diff와 regression PASS, 전체 source→ELF→flash 연결 확보. 현재 source→ELF 및 회귀는 통과했으며 flash와 물리 검증은 아직 수행하지 않았다.

### R2 — 1C/2A 재수용: 출력과 입력은 독립 하위 시험

**R2-O 물리 출력.** 시작 전 정확한 packet CSV와 최대 수를 run manifest에 고정한다. FRAME grammar는 `FRAME,page,node,span,offset,gen,c0,...,c9\n`, c0..c9=0..63, 10칸 유지. 제안하는 관측 묶음은 다음과 같다.

| 묶음 | 입력과 상한 | 완료 조건 |
|---|---|---|
| 시작/CLEAR | 통합 firmware 전원/리셋 1회, 초기 수신 FRAME을 포함해 CLEAR FRAME 1개. handshake가 보내는 초기 FRAME도 계수 | 기존 시작 동작 유지 및 사람이 모든 60점 수납 관측 |
| Cell/column isolation | C1..C10 각각 다른 셀0, 해당 cell 7→0→56→0: 40 FRAME | 왼쪽/오른쪽 열, 채널→셀 대응 및 비대상 셀 불변 |
| state/CLEAR 확인 | 모든 셀 왼쪽 동일 state 0..7, 오른쪽0; 다음 오른쪽 state 0..7, 왼쪽0. 각 패턴 뒤 CLEAR: 32 FRAME | 20모터의 8상태와 기존 0도 CLEAR 복귀. 오른쪽 raw bit와 물리 reverse를 기대표에서 구분 |

정정된 기본 관측안은 합계 73 FRAME와 시작 1회다. 추가 handshake FRAME이 필요하면 실행 전 packet 목록/상한에 별도로 포함한다. 180도 wrap 전용 12 FRAME 시험은 제외했다. 모든 pattern을 자동 시간 제한으로 넘기지 않고, 상태 유지 후 관측자가 `완료`하면 다음으로 진행한다. 녹화·C1..C10 표기를 제공하고 settle 시간도 기록한다. 전체 상태의 기존 관측 evidence를 재사용할 수 있으면 중복 시험은 줄이되, 최종 production transport의 CLEAR·column·정상 상태 표본 확인은 유지한다.

논리 `1=돌출/0=수납/?=불확실`, 점 배치는 `D1 D4 / D2 D5 / D3 D6`. 기대는 전송한 braille cell 값으로 만들며 시험 뒤 관측에 맞춰 바꾸지 않는다. physical `?`는 PASS로 처리하지 않는다.

**R2-I 물리 입력.** 일곱 버튼+MODE를 검사한다. 각 버튼 짧게 3회, 각 버튼 hold/release 1회, lever 왕복 2회와 양쪽 startup 상태를 기록한다. DOWN은 V3 A/R와 host 반복을, CONFIRM은 release 후 SHORT 또는 LONG 정확히 1회를 검증한다. 다른 방향/쪽넘김 hold는 기존 반복 SHORT 계약을 적용한다. 첨부의 “14 S/L event test”를 그대로 acceptance로 사용하지 않는다.

입력 전용 consumer는 S0 및 presenter를 우회했다고 명시한다. 진단기 ready는 handshake·실제 수신 준비 뒤에만 표시하고, 초기 mode/재시도/반복을 고려한 cap을 두어 마지막 버튼이 로그 한도 때문에 사라지지 않게 한다. 앱 연결 시험과 별도 run으로 구분한다.

**R2-T transport/recovery.** 검증된 V3에서 HELLO/ACK, 입력 동일 sequence 재시도와 dedupe, 정상 속도 완전 FRAME과 부분 read, malformed 거절, overflow 뒤 다음 정상 line 회복을 확인한다. 구조 스트레스는 완전 FRAME 전송 종료 후 50ms 간격으로 최대 20 FRAME, 뒤 CLEAR 1개를 제안한다. byte pacing은 넣지 않는다. 출력이 빠르게 바뀌는 묶음은 영상/MCU counter로 확인하며 육안 메모 시험과 섞지 않는다.

Host 최신 상태 병합 때문에 보내지 않은 intermediate generation과, 실제 선로에 보낸 FRAME의 손실을 구분한다. 실제 전송 byte 순서→MCU 완전 수신/파싱→PCA 결과→최종 물리 상태를 대응한다. UART ORE/FE/NE/PE/ring overflow, bus failure가 0인지와 지연을 기록한다. 100ms batch delay는 유지된 값이며 20모터 갱신 시 delay만 약500ms가 가능하므로, 이 동안 입력 누락·release 지연도 측정한다. 무제한 burst로 바꿔 PASS를 얻거나 새 timeout을 발명하지 않는다.

출력 FAIL이어도 안전하다면 입력 전용 검사는 계속한다. 버튼 하나 FAIL이어도 나머지를 계속한다. 현재 임시 firmware의 startup 구동과 반영 후 통합 firmware의 수신 FRAME 구동을 구분해 각 run의 차단 계획을 세운다. 비안전 실패는 기록·분기하고, 걸림/발열/냄새/비정상 공급/제어 불능 동작은 구동 중단 사유다.

### R3 — fresh H2: console + 실제 audio + STM/PCA/셀

진입: R1과 R2-O/T PASS. 기존 READY에서 시작한다. ConsoleControlSource가 controls를 대체하고 production DeviceApplication/Coordinator/S0/audio/STM presenter는 유지되는지 manifest에 기입한다. STM의 physical input을 동시에 소비하지 않는다.

한 번에 안내할 기본 묶음: catalog/선택 → 정상 item up/down → page next/previous → 10칸을 넘는 정상 수식의 right/left offset 증가·복귀 → replay → 짧은 간격의 3명령 → catalog 복귀/CLEAR → 재진입 → 종료/재시작. 각 단계에서 source text/실제 음성, focus/generation, FRAME, 실제 셀을 대응한다. 빈 cells 때문에 offset0인 항목을 scrolling 양성 표본으로 쓰지 않는다.

완료: 같은 최종 focus/generation의 최신 음성과 점자, stale audio/FRAME 없음, text/exit clear, stable device cursor 복구, native worker close와 명시 exit code 확인. Servo를 끈 1B PASS 또는 별도 paced/direct test를 H2 결합 PASS로 합산하지 않는다.

### R4 — fresh H3: production 물리 입력 + 실제 출력

진입: R2-I와 R3 PASS. Production `python -m asl_device`에서 STM controls/presenter와 actual audio 활성, console override 없음. 기존 READY/catalog에서 시작하여 각 physical control의 packet→ACK→app operation→S0 cursor→audio/FRAME→셀을 한 run에서 추적한다.

DOWN 누르기·유지·놓기, CONFIRM 짧게/길게, lever 전환, 모든 방향/페이지 버튼, COM reconnect 1회, reading 재진입과 앱 재시작을 수행한다. release/모드 전환 후 이전 hold 반복 재시작이 없어야 한다. 링크를 의도적으로 끊는 단계는 송수신 복구 시험으로 기록하고 장치의 전원/구동 조건에 맞춰 실시한다.

완료: 여덟 physical controls의 의미·hold/release·reconnect와 실제 출력/복구 PASS. 이 단계는 camera/upload/finalize를 우회하므로 H4는 아니다.

### R5 — H1 보완 및 G3-A, Pi 이식과 최종 H4

- H1 자체의 bounded completion은 유지한다. Laptop app/camera source가 그대로면 처음부터 H1 진단 전체를 반복할 필요는 없다. 카메라 현재 endpoint·원본 dimensions·orientation·비율 유지 preview를 preflight하고, 수정된 경계와 H4에서 physical capture/finalize를 재검증한다.
- 한글 JSON 원본 보존, native stdout decoding, launcher exit-code/worker-close 기록은 작은 run tooling packet으로 준비한다. 이전 깨진 로그는 보존한다. 1B의 output device·battery task 설정·process별 input namespace 교훈을 재사용한다.
- source correction이 끝난 checkpoint에서 affected subsystem→G3-A를 고정하고, 이후 실행에서는 identity drift를 확인한다. 실패에 따른 새 수정이 없다면 같은 대규모 suite를 매번 반복해 physical evidence를 대신하지 않는다.
- 최종 목표는 Pi 4 Device/Scanner + AUX 유선 이어폰 + Pi Bluetooth→STM HC-05다. 원래 target `user@100.69.169.17`은 과거 정보이며 지금 접속/가동 여부를 확인하지 않았다. Laptop에서 firmware 통합을 먼저 닫고 Pi native dependency/model 설치, API/auth, Bluetooth serial/권한, AUX actual sound, 서비스/SSH 실행 차이를 검증한다.
- Pi camera/recognizer cadence와 input/cancel latency는 별도 위험이다. 기존 N/K·8초·identity/duplicate threshold를 유지하고 측정한다. Laptop venv 복사나 Laptop H1 PASS만으로 Pi 성공을 선언하지 않는다. 여기서 구조 변경이 필요하면 별도 bounded packet으로 보고한다.
- H4는 최종 Pi identity에서 physical lever/button→새 datapack의26/27·28/29 두 spread→same-frame L/R artifact→durable receipt 후 전송 안내→physical CONFIRM LONG→fresh READY→page/item/math-window→같은 generation 음성·셀→재진입·재시작 cursor 복구를 연결한다. Laptop H4를 먼저 하면 Laptop 한정으로 표기하고 Pi 최종 수용을 대신하지 않는다.

## 6. 성공 신호와 기록 규칙

각 단계 기록 열은 `run/identity`, `physical input`, `raw NAV/sequence`, `ACK/dedupe`, `S0 focus/generation`, `host FRAME bytes`, `MCU parser`, `PCA result`, `observed cells`, `audio event`, `human hearing`, `exit/reconnect`, `result/reason`이다. Capture에서는 artifact hash/sequence, outbox durable, V4 receipt, S1 fragment, READY revision을 추가한다.

ACK=input 수락, receipt=artifact durable 수신, READY=읽을 자료 게시, playback completed=재생 backend 완료, 사람 청취=실제 audio 관측, PCA HAL success=bus write 결과, physical cells=실제 적용 관측이다. 서로 대체하지 않는다. 중간 generation이 최신 상태 병합으로 생략된 경우는 실제 전송 여부를 먼저 대조한다.

기존 content waiver/Deferred는 유지하되 새 필수 경로 실패의 자동 면제로 사용하지 않는다. 실패가 나면 독립 가능한 남은 절차는 계속하고 의존 단계만 `skipped_due_to_<issue>`로 기록한다. 전체 취소나 threshold/acceptance 완화로 결과를 바꾸지 않는다.

## 7. 현재 확인 대기 항목과 다음 착수점

사용자 확인 완료: 첨부 code는 보드에 올린 임시 기능 시험용, Tera Term 단독, 전원 투입·CLEAR 확인까지로 알고 있음. 유의미한 수용 대상은 실측 펄스값과 핀 번호뿐이다. 다음 확인은 실측표 행과 실제 모터 대응 및 통합 source에 반영할 핀 변경이다. 임시 코드의 전체 project/프로토콜 수리를 요구하지 않으며 이미 답변된 시험 방식과 적용 여부도 다시 요청하지 않는다.

최종 정적 검증: 현재 baseline의 product source 247개 SHA-256 변화 없음, 이 계획의 로컬 링크 누락 없음. 이번 검토에서 수행한 24개 host packet 해석 결과는 회로·보드·S0 시험 결과가 아니다.

다음 착수점은 **flash 전 현재 image의 복구 방법·차단 수단 확인과 R2-O CLEAR/좌우 열 재수용 준비**다. 실기기 연결·flash·구동 전에는 목적, 정확한 packet 목록/최대 수, startup/수신 FRAME 움직임, stop/rollback, evidence 위치를 제시한다. H2/H3/H4 판정은 반영된 통합 firmware의 실제 시험 결과로 내리며 임시 코드의 protocol 차이를 해결해야 하는 별도 blocker로 남기지 않는다.
