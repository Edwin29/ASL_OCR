# Physical controls 하드웨어팀 인계 — 2026-09-08

상태: 사용자 측 측정 불가, hardware team 측정 대기. 문서 인계 준비이며 팀에 메시지를 전송한 것은 아니다. 코드·pin mapping·배선 변경을 승인하는 문서가 아니다.

## 목적과 보존 조건

현재 aligned firmware에서 UP 및 page 버튼의 physical press가 sampled/debounced event로 도달하는지 규명한다. 수리 전 원배선/버튼 label/전원 상태를 기록하고 수리 후 차이를 남긴다. Firmware flash, pin swap, debounce 조절, PCA address/servo LUT 변경으로 원인을 가리지 않는다.

원시 기록은 [실행 상태](H1_CONTROLS_EXECUTION_STATUS_20260908.md)와 `docs/evidence/h1-controls-g0-20260908/up-restored-b-final-serial.jsonl`, `up-restored-b-final-result.json`에 있다. Firmware source identity는 기존 aligned 4-file hash와 일치했고 이번에는 flash하지 않았다. 현재 board image를 직접 재검증한 것은 아니다.

## 관측 사실

한 V3 handshake 이후 정상 종료까지 NAV30개 모두 STM ACK를 확인했다. FRAME0, reconnect/동일 sequence 재전송 없음. Serial-only harness라 DeviceApplication/S0/audio/physical braille의 수용은 아니다.

| 우선순위 | 입력/기대 GPIO | 관측 | 확인할 경계 |
|---|---|---|---|
| 1 | UP / PA0, CN7-28 | SHORT0/3. 앞뒤 DOWN 성공. 과거 별도 run은 UP 성공 | label→스위치 접점→PA0 level→debounce. 간헐 접촉과 연결 상태를 확인 |
| 2 | PAGE NEXT / PB1, CN10-24 | SHORT2/3, 대조 추가 trial1/3; 수신3개 모두 ACK | 눌렀을 때 LOW 누락/불안정 여부. 접점·커넥터·유효 누름 시간 |
| 3 | PAGE PREVIOUS / PC0 | 두 trial 모두0/3, 마지막 trial 앞뒤 DOWN 성공 | 실제 label/연결, PC0 idle/press/release level |
| 4 | CONFIRM / PC1 | 이번 보류. 과거 physical CONFIRM이 PAGE PREVIOUS로 관측 | PC0/PC1 label과 배선 식별. 누름별 두 pin 동시 관측 권장 |
| 5 | MODE / PC2 | 기존 solder 문제로 보류. 이번 initial mode R만 관측 | 납땜/접촉, 두 lever 위치에서 level 안정성 |
| 대조 | DOWN / PA1, CN7-30 | SHORT4회 A/R 및 HOLD1회 A/R 정상 | 동일 조건의 정상 대조군으로 사용 |
| 대조 | LEFT PA4 / RIGHT PB0 | 각각 SHORT3/3 및 HOLD 반복·종료 관측 | 정상 대조군. 이번 정밀 timing 검증은 아님 |

GPIO 위치는 firmware 기대값이며 실제 wiring 일치 증명이 아니다. UP/PREV 무응답과 NEXT 간헐성을 아직 software 또는 wiring 확정 결함으로 분류하지 않는다. 순간적인 loop 정지도 현재 증거만으로 전부 배제하지 않는다.

## 측정 요청과 반환 형식

하드웨어팀은 전원 차단 상태에서 label/연결·continuity를 확인하고, 전원 인가 측정은 STM GND 기준으로 수행한다. 전원 인가 상태에서 저항/continuity 측정을 하지 않는다. GPIO를 임의로 다른 전원/핀에 연결하지 않는다.

각 버튼별로 아래를 반환한다.

| 항목 | 기록할 값 |
|---|---|
| Identity | 날짜, firmware 변경 여부, 수리 전/후, 실제 버튼 label, 실제 연결 GPIO |
| 전원/접지 | STM/PCA 공급 연결 상태 및 측정 기준 GND |
| 접점/선로 | 버튼 양단의 idle/pressed continuity, 버튼→예상 GPIO continuity, 인접 pin 오연결/단락 유무 |
| 동작 level | GPIO idle/누름 유지/release 전압 또는 logic level; 기대 active-low, input pull-up |
| 시간 | LOW 지속시간 및 bounce/간헐 dropout. 멀티미터만으로 짧은 bounce를 배제할 수 없으면 미측정으로 표기 |
| 재현성 | 3회 이상의 개별 결과, NEXT 간헐성, 정상 DOWN과 비교 |
| 수리 | 발견 원인, 실제 조치, 조치 전후 비교. 변경하지 않았으면 명시 |

물리 신호가 충분히 안정된 LOW인데 debug/NAV가 없으면 firmware IDR/MODER/PUPDR와 polling 관측으로 넘긴다. Debugger halt로 얻은 결과는 실시간 debounce/latency 수용과 구분한다. 계측 장비가 없거나 pin 접근이 어려우면 불가능한 항목을 명시하고 원인을 추정으로 채우지 않는다.

## 전원 관련 중요 정정

사용자가 분리했던 것은 STM에서 두 PCA로 가는 VCC/GND 두 쌍이었다. 별도 외부 공급은 없고 현 구성에서 서보만 전원 차단할 수 없다고 확인했다. 이 상태의 `PCA 0x41 INIT ERROR`는 버튼 시험 진입 실패이며 UP 불량 근거가 아니다. 원배선 복구 및 재부팅 후 `PCA INIT OK`가 확인됐다.

FRAME0이라도 boot/PCA 초기화의 물리 움직임 가능성은 남는다. 서보만 차단됐다고 가정한 reset 시험을 반복하지 않는다. Servo 정렬·CLEAR·PCA role correction은 기존 보류를 유지한다.

## 인계 완료와 재개 조건

인계 조사 완료는 위 표에 evidence/미측정/조치가 채워지고 다음 경계가 정해진 상태다. 물리 신호 불량이 확인되면 hardware team 조치 뒤 재측정하고, 신호가 정상이라면 software 계측 packet으로 넘긴다. 수리가 됐다는 보고만으로 V3 PASS로 바꾸지 않는다.

재개 시 같은 방식의 fresh handshake 및 실제 STM ACK 뒤 DOWN→대상 SHORT3→DOWN을 수행한다. UP/PAGE NEXT/PREV는 각각3/3, CONFIRM은 release에서 C,S/C,L 각각3/3 및 P 오발생0, MODE는 왕복3회의 정확한 mode event를 요구한다. 이후 hold/release와 production app action을 별도 수용한다. 기존 failed evidence는 보존한다.

Hardware team 결과 대기 중에도 H1의 raw identity 공백 및 liveness 설계 조사는 독립적으로 가능하다. Camera threshold/8000ms와 코드 수정 금지는 유지하며, 수정 후 fresh H1은 source alignment와 별도 구현 승인 전 실행하지 않는다. H4는 계속 BLOCKED다.
