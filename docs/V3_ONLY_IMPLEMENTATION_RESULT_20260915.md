# Production V3 전용 적용 결과

## 사용자 운용 제약 수용 및 최종 재접속 결과

2026-09-15 사용자는 재접속 후 조작 정상 작동을 보고하고 무조작 재접속/첫 입력 소모를 프로토타입 제약으로 기록해 시연 주의사항으로 관리하도록 제안했다. 해당 제한은 해결로 처리하지 않고 운용 제약으로 수용하며 추가 자동화 수정은 보류한다. 구체적인 시작/재시작/종료 절차는 [시연 운용 주의사항](PROTOTYPE_DEMO_OPERATION_NOTES_20260915.md)에 기록했다. 다른 미해결 문제 또는 H4 acceptance까지 일괄 면제하는 결정은 아니다.

Production-02 재연결 이후 CONFIRM sequence2→page0/node6/offset0/generation218 복구 FRAME, LEFT/RIGHT sequence3–5 및 generation219–221을 확인했고 사용자가 조작 정상이라고 보고했다. 종료 stop262879.890→COM/audio 정리 정상 반환262880.015→application exit_code0/cleanup_failures[]→python_atexit262880.031, Python0/collector 종료를 확인했다. Native exit null은 별도 미관측으로 유지한다. 최종 사본 `closed02-*` 및 `closed02-hashes.json` 보존. 이번 문서화 단계 제품 변경0, 추가 serial 송신/reset/flash0.

## Production-01 시작 관측

### Production-02 무조작 재접속 관측

후속 UP1회 완료 보고 후 STM UP STEP262750.046, NAV,U,S,17 초기전송+3회 retry, NO ACK disconnected262752.062 → HELLO3 → host ACK3(262752.078) → STM V3 EDGES(262752.125) → MODE R/ACK1을 확인했다. 버튼 이후 약2.08초에 V3 회복했고 MCU reset/전원 재투입은 없었다. 최초 UP는 host의 handshake 전 입력 차단으로 읽기 명령으로 전달되지 않았다. 시작 FRAME AME 손실 후 한 번 재송신한 blank FRAME은 정상 해석됐다. 원본 사본 `reconnect-triggered-*` 보존.

판정: **입력 유발 V3 재접속 PASS**, 무조작 자동 재접속 미성립은 별도 유지. 이는 STM의 이전 연결 생존 판단과 ACK 실패에 의한 재협상 경로를 실행 증거로 뒷받침한다. 재접속을 깨우는 첫 버튼은 의도한 읽기 동작을 수행하지 않으므로 사용자 경험상의 제한이다. V3-only/retry 변경은 fallback 문제를 해결했으나 host 종료 감지 계기 자체를 추가하지 않았다. 이번 단계에서 heartbeat/새 protocol/추가 firmware 변경은 적용하지 않는다. 이어서 같은 READY의 위치·음성·셀 복구를 확인하고 Ctrl+C 종료 로그를 수집한다.

사용자 시작 보고 후 첫 open262699.000, 5초 RX0 뒤 close, 두 번째 open262704.609와 5초 RX0 close, 세 번째 open262711.281을 확인했다. 262712.765까지 수신bytes0, STM debug0bytes, 앱/collector 생존. `reconnect-idle-*` 사본 보존. 현재 무조작 재접속은 미성립이며, source상 STM이 이전 connected 상태에서 host 종료를 감지할 입력 ACK 실패 계기를 기다리는 경로와 일치한다. 단 debug 무출력만으로 MCU 내부 상태를 직접 입증하지는 않는다.

다음 분리 시험은 physical UP 짧게1회로 이전 연결의 sequenced NAV를 유발하는 것이다. 미협상 host는 NAV를 처리/ACK하지 않으므로 firmware500ms ACK timeout/최대3회 재시도 후 disconnected→V3 재협상을 기대한다. 새 협상 초기 FRAME/CLEAR와 MODE ACK 외 별도 FRAME 패턴 없음. 버튼1회 이후10초 관측하고 성공 여부와 관계없이 반복 입력하지 않는다. 이것은 입력 유발 재접속이며 무조작 자동 재접속으로 승격하지 않는다. 아직 이 입력 단계 결과는 없다.

### 물리 reading 묶음 관측

Production-01 사용자 Ctrl+C 종료 확인: stop262631.718 → serial closed/player/controller close 정상 반환262631.843 → application exit_code0/cleanup_failures[] → python_atexit262631.859, 종료 후 Python0/collector 종료. Launcher native exit null은 기존 관측 한계로 유지한다. 원본 사본 `closed01-*` 보존. 다음 production-02는 MCU reset 없이 먼저 무조작 재시작을 관측한다. STM이 이전 연결을 유지해 HELLO가 없으면 이를 기록한 뒤 단일 physical input으로 ACK 실패/재협상을 유도하는 별도 단계를 안내한다. 그 경우 입력 유발 재접속으로 분류하며 무조작 자동 재접속으로 주장하지 않는다.

사용자는 전 항목 정상 가동을 보고했다. `reading-host-serial-32508.jsonl`, `reading-debug.jsonl` 중간 사본에 NAV1–16/ACK, generation204–218 FRAME, V3 DOWN A9/R10, catalog CLEAR 및 동일 generation218/page0/node6/offset0 재진입이 확인됐다. DOWN 실제 host A/R 간격은1.187초이고 release 이후 다음 UP 입력 전 추가 FRAME이 없어 반복 정지를 확인했다. 정확한2초/3초 대기 시험으로 확대하지 않는다. 음성과 물리 수납/내용 일치는 사용자 관측으로 기록한다. 추가 자동 packet/flash/reset 없이 정상 기능을 확인했고, 다음은 앱 종료와 새 프로세스 V3 재접속이다. close/reopen 전까지 전체 재접속 PASS는 보류한다.

사용자 시작 보고 후 host 첫 COM open 성공(262420.203), HELLO3 수신/ACK3 송신(262420.859), STM V3 EDGES 연결(262420.890), MODE reading NAV,V,R,1/ACK1을 확인했다. STM은 앞선 V3 시도 실패 뒤 V2로 내려가지 않고 다음 V3 시도를 통해 연결됐다. 이는 첫 production startup 실증이며 close/reopen 재접속 전체 수용은 아직 아니다. 시작 사본은 `docs/evidence/v3-only-20260915/startup-host-serial-32508.jsonl`, `startup-debug.jsonl`.

첫 FRAME은 여전히 AME로 수신돼 UNKNOWN 처리됐지만 MODE 후 한 번 재송신된 전체 FRAME과 CELLS all-zero 해석을 확인했다. 기존 수신 전환 손실은 미해결로 유지한다. 물리 수납은 사용자 관측과 분리한다. 앱을 유지한 채 물리 reading/DOWN A-R 및 catalog CLEAR/재진입 묶음 검증을 안내한다. 이번 시작 확인 시 추가 제품 수정/flash/reset/직접 serial 송신0.

## 구현 및 배포

사용자의 적용 승인에 따라 제품 파일2개를 변경했다. 기존 working-tree의 셀 역순 보정·실측 LUT/GPIO·serial bounded read/retry 변경은 보존했다. 별도 host tests 파일1개와 integration contract tests 파일1개를 갱신했다.

- `device-runtime/src/asl_device/adapters/stm_serial.py`: 기본 V3-only. V2/legacy HELLO에는 ACK/FRAME을 보내지 않으며 handshake 전 NAV는 전달하지 않는다. 연결된 V3에서 구버전 재협상이 들어오면 기존 reconnect 경로로 돌아가고 active DOWN 강제해제를 유지한다. 구버전 코드는 `allow_legacy_protocols=True`라는 명시적 진단용 생성자 옵션에서만 유지하며 production composition은 이를 사용하지 않는다. 기존5초 host handshake deadline과 reconnect backoff는 유지한다.
- `hardware/stm32/kitel2026final/Core/Src/main.c`: V3 HELLO를 최대3회, 각 응답 구간1200ms로 시도한다. 구간 내 다른 줄은 무시하지만 전체 deadline을 갱신하지 않는다. 모두 실패하면 disconnected로 반환하고 기존 outer reconnect loop가 나중에 재시도한다. V2/legacy handshake fallback 송신을 제거했다. internal bt_protocol_v2 flag는 기존 async transport 공용 코드 활성화 플래그로 남으며 V2 협상 허용을 뜻하지 않는다.
- FRAME grammar, 셀 mapping/LUT/펄스값, 버튼 debounce/press/release/ACK/dedupe, firmware RX IRQ 구조, camera thresholds 및 credential은 변경하지 않았다. 최초 FRAME 손실 후 MODE에 맞춰 한 번 재송신하는 기존 완화책은 유지한다.

Laptop host 파일 배포 완료 SHA256 `d2ff49463dcdb103150ff8312f0a5ef6128cb513acde98cfb3bf6da753fcdf34`. actual Python/device-runtime/book-scanner/document-parser import root도 C integration으로 재확인했다.

새 isolated firmware main SHA256 `6e36d4b31834e5493407dd60bcbbac2a42e1a35e396b8bf9cc919288a4eadc7a`, ELF SHA256 `e216f93d30b326ef1c390986483f2d487c58ae531dc2d21ecd735cabce4da3fc`. ST-LINK `066EFF505071655067246025`로 download/verify/reset exit0 및 Download verified successfully 확인. Laptop의 source tree firmware는 덮어쓰지 않고 C runtime `v3-only-20260915/source/kitel2026final`에서 build/flash했다. Desktop source가 변경 기준이다.

## 검증

- Host/동작 identity/MODE tests 47PASS. 구버전 기존 tests는 명시적 diagnostic opt-in으로 보존하고 새 production-default tests에서 구버전 차단/handshake 전 NAV 차단/이후 V3 연결/구버전 rehandshake 단절을 확인했다.
- 인접 H123 boundary/followup tests22PASS.
- 추출한 실제 firmware handshake C를 MSVC로 compile/run: no host, immediate V3, first HELLO miss then recovery, unrelated ACK then V3, V2-only rejection, tick rollover6조건 PASS. UART line/HAL은 deterministic stub이며 실제 Bluetooth 증거가 아니다.
- parser/PCA application/motor/버튼/host line parser/async TX 함수의 이전본문 동일성 검증 PASS. STM target cleanBuild exit0, errors0. Git diff whitespace check PASS.
- 첫 host tests 실행은 document_parser import path 누락, 인접 첫 실행은 pytest temp 권한 오류로 불완료였다. 각각 source path 및 새 ASCII basetemp 지정 후 위 tests가 통과했다. 기존 실패 XML은 보존하며 제품 회귀로 분류하지 않는다.

증거: `docs/evidence/v3-only-20260915/`의 before source, handshake fixture/result, tests XML, build-result.json, deployment.json, flash.log.

## 현재 한계 및 다음 실제 시험

Production 실행 폴더 `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\v3-only-20260915\production-01` 준비. 기존 R2 config/state/device ID를 그대로 참조한다. 새 host hash guard와 Serial/lifecycle pass-through 관측을 사용하며 실제 module entrypoint/physical controls/audio/presenter를 유지한다. 아직 이 production run은 시작 전이다.

사용자는 관측 가능하다고 응답했다. 먼저 startup에서 HELLO3/ACK3 및 STM V3 EDGES 확인 후 물리 DOWN edge/정지, 기존 READY 음성·점자와 재접속을 검증한다. 이미 V3인 척하거나 V2 compatibility를 acceptance로 대신하지 않는다. 초기 COM의 RX0, 최초 FRAME 손실의 하위 계층 원인은 이번 변경으로 제거됐다고 주장하지 않는다. V3 연결이 안 되면 계속 disconnected 상태로 재시도하며 현재 사용자 안내는 기존 catalog/feedback이다. 별도 V3-ready 음성이나 새 UI는 추가하지 않았다.

## Rollback

사용자 필요 시 앱이 모두 종료된 상태에서 Laptop `v3-only-20260915/stm_serial.before.py`를 integration host 파일로 복구하고, 이전 `minimal-corrections-20260915/source/kitel2026final/Debug/kitel2026final.elf`(SHA256 `9a3e9941b6823af6104968a1b69bdd63a4d43f3377bcc49d77c009fe9e35bd4a`)를 verify/reset한다. host/firmware를 짝으로 복구하며 production state/SQLite는 reset하지 않는다. 본문과 tests의 이번 변경은 before 사본과 비교하여 국소적으로 되돌릴 수 있고 전체 git reset은 사용하지 않는다.
