# H1 / controls 순차 실행 상태 — 2026-09-08

사용자 실행 지시에 따라 G0 read-only preflight를 수행했다. 코드 수정 금지는 유지한다. Product/firmware/harness/config 수정 0, flash/reset/FRAME/카메라 upload 0이다.

## G0 결과

| 항목 | 결과 |
|---|---|
| SSH | 기존 BatchMode 인증으로 접근 성공. Laptop C:만 접근 |
| Python/import | `.venv-e0b/Scripts/python.exe`; asl_device/book_scanner/document_parser 모두 `C:\ASL_OCR_INTEGRATION` 아래 |
| Engine | Laptop `f223f744fe2fd6a6818ea7bed4ed4f522e27f90590fc2c477fcb40fdbe8e427f`, Desktop `6ee44d42cae3456544e58c183c193f970b1467ef26a616feeb9ad6e563dfc380`. 최근 local correction 미배포 확인 |
| Opaque collector | Laptop byte hash `aeac3eea75245675a08e7d643dc73ee569cce0db6cf05326841e7bc46273af59`, Desktop `03d11754231e24ad0ffe731c4ecc2c013f009fc48b4193f1a57c638ca1ae2acf`. LF 정규화 후에도 hash는 다르지만 PowerShell line 비교 차이 0. Byte identity 불일치만으로 동작 regression이라 하지 않음 |
| Firmware source | 4개 source hash 모두 aligned-firmware-build.json과 일치. 현재 flash 내용은 이번 turn에서 직접 읽지 않았음 |
| Process/ports | 열거 시 Python/pythonw/STM32_Programmer_CLI process 없음. COM5/COM9 존재. 포트 독점 소유·handshake는 아직 미검증 |
| Fresh H1 config | SHA256 `4fb36bf39030201da69e16ced8ee9e595e42287f8e1af96507bf524c6249f3a8`; console, android_ip_camera, preview true, sample750ms, collection8000ms, min3000×2000, stable device `laptop-device-001`, profile TLS exception true |
| Environment manifest | 기존 `30a41312c5218e357ae4bb351dbce33e15f69e6cbe2749f26f11266391590aa7` 유지 |
| Physical harness | Laptop `95737a9a9ba559abc7727ac824387c99bbda95b2468cc2e7a160f901421ead86`, Desktop `bd5a7e544432242b2f5b375a3b32b107731315dc405de7b3a9ef0e510fafd228`. Laptop은 기존 ports-open 시점 ready marker 버전 |

G0는 **부분 완료**다. 수정 후 fresh H1 acceptance의 source alignment는 BLOCKED이며 코드를 복사하지 않았다. 현 Laptop source에 대한 진단은 별도로 가능하다. UP input-only 시험은 camera engine delta와 독립적이다.

## H1 기록 재검토

기존 result.json의 engine hash가 현 Laptop engine과 같다. Slow exact pair의 N4 timeout/reset 재현은 유지할 조사 근거다. 다만 collector의 byte identity는 다르고 원 accepted bank/raw pairs도 없으므로 전체 원 run을 완전히 복원했다고 주장하지 않는다. 과거 결과를 이번 재실행 PASS로 세지 않았다.

Desktop engine source의 `_poll_opaque_page_change`는 timeout 때 collector를 새로 만들고 이후 sample을 읽는다. 최근 SAME epoch/late cleanup 수정은 이 liveness 정책을 닫지 않는다. 원인·해결 후보 결정은 N5 UNKNOWN/SAME의 raw identity evidence 확보 및 scheduling/recognizer 후보 검증이 남았다. Live 반복만으로 기존 무진전을 다시 보이는 시험은 시작하지 않았다.

## 다음 UP 시험 준비

Laptop 기존 harness를 변경 없이 사용할 수 있다. `ready` 파일을 준비 완료로 쓰지 않고 raw COM5/COM9에서 HELLO3→ACK HELLO→initial mode→STM ACK 수신을 직접 확인해야 한다. 새 run root, 충분한 packet cap, 한 boot epoch, release 후 tail을 사용한다. 중간 reset/reconnect는 trial INVALID로 처리한다.

예정 순서: DOWN 대조 1회 → UP SHORT 3회(각 200–300ms, 간격2초) → DOWN 대조 1회. 예상 입력은 DOWN A/R 두 쌍과 UP S 세 개이며 host는 handshake/sequence ACK만 전송한다. FRAME 0. 실제 시작 전 사용자에게 안내한다.

현재 **사용자 전원 상태 확인 대기**다. Servo 전원이 연결되어 있거나 구성이 불명확하면 boot/reset으로 셀이 움직일 수 있어 조작하지 않는다. 보드/버튼은 아직 조작 요청하지 않았다.

### 후속: 서보 전원 분리 확인 및 capture 대기

사용자가 서보 전원만 분리 완료를 확인했다. 첫 `Start-Process` 실행은 로그 생성 전 process가 종료되어 INVALID startup으로 남겼다(버튼 trial 없음). SSH foreground 유지 방식으로 기존 harness를 변경 없이 재실행했다.

- Active run: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\up-controlled-20260908-222003-retry`
- Host exec session: 65273. Capture 최대900초, NAV safety cap128, FRAME0.
- COM port open marker는 확인했으나 raw log는 비어 있어 handshake 완료가 아니다. 수동 RESET 후 HELLO3/initial mode/ACK 확인을 다음 단계로 요청한다. Servo 전원은 분리 유지한다.

### RESET 후: PCA init에서 input 시험 진입 차단

사용자 RESET 완료 뒤 UTC 13:22:00.880854에 `PCA 0x41 INIT ERROR`를 수신했다. 직전에 0x40/0x41 모두 FOUND였지만 HELLO3/initial-mode ACK 또는 button debug는 없다. `main.c:1317`의 PCA_Init 실패 분기는 Error_Handler로 이동하고 `main.c:1588` handler는 IRQ를 끈 채 무한 대기한다. 따라서 이 run은 **boot prerequisite FAIL / UP trial BLOCKED(미실행)**이다. 과거 UP 무응답 원인으로 소급하지 않는다.

Host stop marker로 새 capture만 종료하고 raw logs를 보존했다. FRAME 전송 0. 분리된 전원이 PCA logic/I2C에도 영향을 주는지, 독립적인 I2C/init 실패인지 원인은 `insufficient_evidence`다. FOUND는 이후 모든 register transaction 성공을 뜻하지 않는다. 전원 복구·재배선·반복 RESET은 아직 요청하지 않는다. H1 문서/기록 조사 분기는 이 하드웨어 실패와 독립적으로 유지한다.

Evidence: `docs/evidence/h1-controls-g0-20260908/up-reset-handshake.txt` 및 위 active run의 COM5/COM9 raw logs.

### 전원 구성 정정 및 원배선 복구

사용자 확인: 분리했던 것은 STM→두 motor driver의 VCC/GND 두 쌍이며 별도 외부 전원 공급은 없다. 서보만 공급 차단하는 것은 현재 구성에서 불가능하다. 앞선 `servo_power=operator_confirmed_disconnected`는 실제 분리 범위를 잘못 해석한 기록이므로 이 설명으로 정정한다. PCA 제어 전원/공통 접지 분리 상태의 init 실패이며 UP 불량 근거가 아니다. 정확한 실패 transaction과 전원 상태는 미측정이다.

사용자가 전원을 차단한 뒤 원래 연결을 복구했다고 보고했다. 코드·배선 mapping 변경 없이 전체 전원 상태의 input-only 재시험을 준비한다. Host FRAME0은 유지하지만 boot 초기화의 물리 움직임 가능성은 별도로 안내했다. 원배선 복구 뒤 현재 전원 ON 여부는 아직 확인되지 않았다.

- 새 capture: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\up-restored-20260908-a`
- Host exec session 89311; 기존 Laptop harness 무수정, 최대900초/NAV128.
- 전원/RESET 후 정상 PCA init와 HELLO3 및 STM ACK 수신을 확인하기 전 버튼 trial을 시작하지 않는다.

후속 사용자 완료 응답 뒤 UTC 13:29:45 재확인: capture PID23556(Session0)는 살아 있고 COM5/COM9가 열거되지만 COM5 debug와 serial JSONL은 모두 0 byte다. `ready=true`는 포트 open만 뜻한다. Boot/PCA/HELLO/ACK는 아직 관측되지 않았다. 전원 ON과 RESET 중 어떤 조작을 수행했는지 및 보드 표시등을 사용자에게 확인하며 버튼 trial은 계속 미시작이다. 무로그만으로 firmware crash나 UP 실패를 확정하지 않는다.

### 재부팅 및 포트 재오픈 후 V3 준비 완료

다음 사용자 재부팅 뒤 run a에서 `PCA INIT OK`와 button mapping banner를 확인했다. STM은 HELLO를 반복했지만 host COM9 rx는 없었다(COM5 rx42 records만 존재). Capture를 정상 종료하고 동일 무수정 harness로 새 run b에서 포트를 재오픈했다. Firmware reset/flash는 추가 실행하지 않았다.

- 현재 run: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\up-restored-20260908-b`, exec session71099.
- UTC13:31:29.893 HELLO3 수신 → ACK HELLO 송신 → STM HOST CONNECTED(V3 EDGES) → NAV,V,R,1 → host ACK1 → UTC13:31:30.0029769 STM `BT ACK: 1` 확인.
- 이 시점을 수동 observation-ready 기준으로 사용한다. Boot mode R은 lever 동작 PASS가 아니다.
- Port 재오픈 뒤 연결은 회복됐으나 stale port/전원 재인가/BT link의 정확한 원인은 미확정이다. UP trial 전의 환경 준비 문제로 분리한다.
- Evidence: `up-restored-reboot-check.txt`, `up-restored-b-handshake.txt`.
- 다음 사용자 조작: DOWN SHORT1 → UP SHORT3 → DOWN SHORT1, 각 조작 간2초. Host FRAME0, ACK only. 기대 distinct NAV7개(DOWN A/R 4개, UP S3개), 재전송은 별도 집계.

### UP SHORT 결과: 대조군 성공, UP 미수신

사용자가 전체 순서 완료를 보고했다. UTC13:32:44.844~45.080의 첫 DOWN은 `D,A,2`/`D,R,3`, UTC13:32:56.082~56.397의 마지막 DOWN은 `D,A,4`/`D,R,5`이며 모두 host 수신과 STM ACK가 있다. 사이에 `UP STEP`/`NAV,U,S`는 0개다. Observation-ready 뒤 재연결/RESET과 sequence 재전송은 관측되지 않았다.

- DOWN SHORT 대조: 2/2, V3 A/R와 ACK PASS(input-only).
- UP SHORT: 요청3회 대비 debug/NAV0회, acceptance FAIL. 사용자 누름 자체의 전기적 LOW와 개별 시각은 미측정.
- First missing boundary: physical UP→PA0 sampled/debounced event. Host ACK/routing 이후의 실패가 아니다. 정확한 원인은 계속 `insufficient_evidence / P1`이다.
- 이전 ready/cap 문제 없이 재현됐다. 다만 과거 run의 원인을 소급 확정하지 않는다. UP HOLD/production action은 의존 조건 미충족으로 SKIP하고 PA0 level/continuity/poll 측정을 별도 준비한다. 코드·핀 교체는 하지 않는다.
- 독립 LEFT/RIGHT/PAGE NEXT/PAGE PREVIOUS SHORT를 계속한다. 각3회, 간격2초, 종류 사이5초. CONFIRM/MODE는 기존 수리 전 보류 유지.
- Evidence: `up-restored-b-short-observation.txt`, `up-restored-b-after-short-serial.jsonl`(live log의 해당 시점 보존본).

### 나머지 버튼 SHORT batch 결과

사용자 완료 응답 뒤 raw COM5/COM9를 보존했다. LEFT seq6–8은 3/3, RIGHT seq9–11은 3/3 debug→NAV→STM ACK까지 확인됐다. PAGE NEXT는 seq12–13 두 개만 확인됐으며 각각 ACK됐다(UTC13:34:29,13:34:33). PAGE PREVIOUS debug/NAV는 없다. 이 구간 HELLO 재연결 및 같은 sequence 재전송은 없다.

LEFT/RIGHT는 SHORT input-only PASS, PAGE NEXT는 요청3회 대비2개로 FAIL, PAGE PREVIOUS는 요청3회 대비0개로 FAIL이다. Production math/page action PASS로 승격하지 않는다. 마지막 수신 이후의 main-loop/연결 생존 여부를 입증할 끝 대조군이 이 batch에는 없으므로 두 page 버튼의 원인은 미확정이다.

다음 bounded 추가 trial은 DOWN→NEXT3→PREVIOUS3→DOWN으로 앞뒤 생존 대조를 추가한다. 누름을 약0.3초로 유지하고 간격2초/종류 전환5초로 한다. 기존 실패는 지우지 않으며 결과가 달라도 간헐성/조작 차이로 구분한다. FRAME0 유지, RESET/CONFIRM/MODE 조작 없음.

Evidence: `up-restored-b-other-short-observation.txt`, `up-restored-b-after-other-short-serial.jsonl`.

### Page 버튼 앞뒤 DOWN 대조 재시험

사용자 완료 뒤 첫 DOWN `D,A,14`/`D,R,15`, 마지막 DOWN `D,A,17`/`D,R,18` 모두 debug/NAV/STM ACK가 확인됐다. 사이의 PAGE NEXT는 `N,S,16` 한 개만 있고 PAGE PREVIOUS는 debug/NAV0개다. 따라서 NEXT는 이번3회 중1회, PREVIOUS는3회 중0회이며 SHORT 수용 FAIL을 유지한다. NEXT는 두 trial 합계 요청6회/수신3회이나 전기적 누름 시각이 없어 단일 고정 실패 원인으로 확정하지 않는다.

앞뒤 DOWN 성공은 관측 구간 전후 input loop와 양방향 transport가 동작했다는 근거다. 모든 순간의 sampling/접점 상태까지 증명하지 않는다. 첫 누락 경계는 page 버튼 sampled/debounced event 이전이며 host 수신 이후 유실 evidence는 없다. Hardware/wiring 확정 대신 `insufficient_evidence`로 유지한다. NEXT/PREV 반복 SHORT 및 HOLD는 추가 계측 전 보류한다.

독립적인 남은 serial lifecycle trial은 LEFT HOLD1회, RIGHT HOLD1회, DOWN HOLD1회(각 약1.5초 후 완전히 release, 종류 사이5초)다. LEFT/RIGHT는 firmware S 반복과 release 후 종료, DOWN은 V3 A/R 한 쌍만을 기대한다. Direct serial harness에는 DeviceApplication host hold-repeat가 없으므로 DOWN 연속 reading 동작은 검증하지 않는다. FRAME0을 유지한다.

Evidence: `up-restored-b-page-bracket-observation.txt`, `up-restored-b-after-page-bracket-serial.jsonl`.

### HOLD 결과 및 capture 종료

LEFT HOLD는 S seq19–23 다섯 개, RIGHT HOLD는 S seq24–28 다섯 개이며 전부 STM ACK가 있다. 각 묶음 이후 같은 버튼의 추가 반복이 없고 다음 버튼 동작이 관측됐다. 사용자 release 보고와 합쳐 반복 발생/종료의 기능 관측 PASS로 기록한다. 별도 release edge가 없는 L/R의 정확한 release→중단 latency와 650/180ms timer 정밀도는 이번 host trace로 수용하지 않는다.

DOWN은 `D,A,29`/`D,R,30` 한 쌍과 ACK, S 반복0이다. Host 수신 시각 간격은 약1.087초로 안내한 약1.5초보다 짧지만 long-held A/R 기능은 관측됐다. 정확한 물리 hold 시간은 미측정이다. Host reading auto-repeat는 이 harness가 우회한다.

사용자 완료 뒤 정상 stop marker로 capture를 종료했다(UTC13:38:18.4783827). 최종 HELLO3 1개, NAV30개, ACK30개, FRAME0, error null, stop_reason requested다. Boot mode1 + DOWN SHORT4회의 edge8 + LEFT/RIGHT SHORT6 + NEXT SHORT3 + LEFT/RIGHT HOLD10 + DOWN HOLD edge2 = NAV30이며 PREVIOUS/UP는0이다. 동일 seq 재전송이나 handshake 후 재연결은 기록되지 않았다.

| 입력 | 이번 관측 최종 상태 |
|---|---|
| UP | SHORT0/3 FAIL, 원인 미확정; HOLD/app SKIP |
| DOWN | SHORT4/4 A/R와 ACK, HOLD A/R1쌍 PASS(input-only) |
| LEFT/RIGHT | 각각 SHORT3/3, HOLD 반복5개와 종료 관측 PASS(input-only) |
| PAGE NEXT | SHORT3/6 FAIL, 간헐 수신; HOLD/app 보류 |
| PAGE PREVIOUS | SHORT0/6 FAIL; HOLD/app 보류 |
| CONFIRM/MODE | 기존 수리 전 보류, 이번 조작 없음; initial mode는 lever 시험 아님 |

다음 physical 조사에는 PA0/UP, PB1/NEXT, PC0/PREV의 idle→press→release 전압/continuity와 물리 label 연결 확인이 필요하다. 단순 누름 반복으로 대체하지 않는다. 측정 가능 여부를 사용자에게 확인한 뒤 구체적인 안전한 측정 절차를 제시한다. GPIO 상태/firmware polling 계측이 필요하면 별도 diagnostic 단계이며 코드 변경은 여전히 금지다.

최종 raw/result: `up-restored-b-final-serial.jsonl`, `up-restored-b-final-result.json`; hold snapshot: `up-restored-b-hold-observation.txt`. 이번 전 과정 product/firmware/harness/config 수정0, flash0. Full H3/H4 PASS 아님.

### Hardware team 측정 대기로 전환

사용자가 물리 측정은 하드웨어팀에 맡겨야 한다고 확인했다. 사용자에게 추가 배선/전압 측정을 요청하지 않는다. [인계 문서](CONTROLS_HARDWARE_TEAM_HANDOFF_20260908.md)에 UP/페이지 버튼과 기존 CONFIRM/MODE의 측정 요청, 기대 GPIO, 반환 양식, 재개 조건을 정리했다. 팀에 메시지를 전송하지는 않았다. Controls physical 진단은 결과 대기, H1 독립 조사와 코드 변경 금지는 유지한다.

## Evidence와 실행 오류 구분

- `docs/evidence/h1-controls-g0-20260908/laptop-identity.txt`: source hashes. 첫 config probe는 remote Python argument quoting 오류로 실패했다. SSH 마지막 명령 exit0을 config PASS로 사용하지 않았다.
- `laptop-config-retry.txt`: quoting 수정한 read-only 명령에서 config/import 수집 성공, Python exit0.
- `laptop-opaque-identity-source.txt`: read-only source inspection 사본; product source가 아님.

첫 SSH Get-Date quoting 오류와 첫 config quoting 오류는 진단 명령 오류이며 product incident로 분류하지 않는다. 이후 정상 read-only 호출로 각각 대체했다. H1/H3/H4 PASS 선언은 없다.
