# H3 종료·프로세스 재시작 복구 확인

## B 결과 및 이번 검증 결론

사용자는 두 번째 복구 정상, Ctrl+C 종료 코드 미표시, 셀 잔류를 보고했다. 최종 사본은 `docs/evidence/h3-validation-20260915/restart-b-*`, `restart-b-hashes.json`, `restart-b-result.json`에 보존했다. 이번 단계의 새 제품 코드 변경/flash/reset/추가 serial 송신0.

- 최초 읽기 FRAME은 page0/node6/offset20/generation194로 A의 마지막 상태와 일치하고 STM에도 동일하게 해석됐다. 사용자 복구 관측과 함께 재시작 cursor 복구 PASS. 추가 LEFT/RIGHT 조작 후 최종 generation204/offset20까지 기록됐다.
- 261561.281 application.stop 진입, 261561.375 serial closed 및 player/controller.close 정상 반환, application.stop 반환(exit_code0, cleanup_failures[]), 261561.390 python_atexit 확인. 사용자 종료 후 Python0, collector 종료 확인. A/B 모두 계측된 앱·COM·audio 정리 경로 PASS.
- OS native exit code는 두 번 모두 null. 제품 내부 exit_code0과 별개인 launcher 관측 부족으로 유지한다. B transcript도 native stdout을 담지 못하므로 B가 정확히 audio idle에서 중단됐는지는 별도 로그로 확인하지 못했다. idle 종료를 독립적으로 입증한 것으로 확대하지 않는다.
- B는 V3가 아닌 **V2 ASYNC**였다. COM open은 세 번 모두 성공했으나 처음 두 번은 수신 없이5초 handshake deadline 후 닫혔다. 세 번째에서 HELLO2/ACK2가 확인됐다. STM debug에는 이전 NAV82 ACK 재시도 후 disconnected, V3 시도→V2 fallback이 보인다. 자동 재시도의 회복 사례로 기록하되 재시작에서 V3 유지/복구 PASS로 사용하지 않는다. 이전 H3 R2의 V3 DOWN edge 증거는 별도로 유지한다.
- 최초 FRAME `RAME` 손실 후 MODE ACK와 한 번의 완전 FRAME 재송신으로 회복했다. 기존 최초 FRAME 손실의 근본 원인은 해결되지 않았다.
- A/B 종료 시 blank FRAME은 송신하지 않았고 셀이 남았다는 관측은 현재 종료 구현과 일치한다. Catalog CLEAR의 물리 정상 수납과 혼동하지 않는다.

이로써 두 차례 process 재시작 cursor 복구와 계측된 자원 정리 확인은 완료한다. 반복적인 Ctrl+C 재시험은 종료한다. 남은 bounded 항목은 (1) V3 재접속/시작 보장과 최초 FRAME 손실, (2) 필요 시 종료 자동 CLEAR 계약 및 구현, (3) native exit status를 보존하는 launcher 관측 보완이다. H4 진입 전 V3 연결을 gate로 확인하며 전체 integration-ready 판정은 여전히 하지 않는다.

## A 실행 결과

사용자는 위치 복구, 종료 시 음성 정지를 확인했고 셀은 수납되지 않았으며 별도 종료 코드를 보지 못했다. 원본/콘솔 사본은 `docs/evidence/h3-validation-20260915/restart-a-*`, hash 목록은 `restart-a-hashes.json`이다. PowerShell transcript는 native stdout을 충분히 담지 못했으므로 첨부 사용자 콘솔을 별도 원본으로 보존했다.

- `reading_resumed`는 이전 R2의 page_index0/node_index6/offset10/generation192 및 같은 focus와 일치. 사용자 음성/점자 복구 정상 관측으로 프로세스 재시작 복구 확인.
- 261326.531 DeviceApplication.stop 진입 → 261326.671 serial closed → 261326.703 SoundDeviceWavPlayer.close 및 ReadingAudioController.close 정상 반환 → DeviceApplication.stop 반환(exit_code0, cleanup_failures[]) → 261326.718 python_atexit. 종료 후 Python0, debug_exited=true. 현재 계측 범위의 COM/audio/application 정리 성공을 확인했다. 중복 close/stop 기록은 idempotent 호출과 구분하며 실패로 세지 않는다.
- launcher native_exit_code는 여전히 null. 제품 application.exit_code0과 OS native exit status 관측을 구분한다. 파이프라인 제거만으로 exit 관측이 회복되지 않았으므로 이전 Tee pipeline 단독 원인 가설은 충분하지 않다. PowerShell Ctrl+C 제어 흐름 등 경쟁 가설은 남고 source 수정 없이 보존한다.
- 종료 시 CLEAR 미전송: application.stop은 coordinator.stop 후 자원을 close하며 presenter.present(None)을 호출하지 않는다(application.py:134). STM close는 stop flag와 worker join을 수행하고 blank FRAME을 enqueue/전송하지 않는다(adapters/stm_serial.py:171). 따라서 마지막 점자 유지가 관측된 현 구현 동작이다. catalog 복귀 CLEAR는 앞서 통과했고 이번 현상을 PCA/servo CLEAR 실패로 분류하지 않는다. 종료 자동 수납을 원한다면 별도 bounded 계약/수정 후보로 다루며 이번에 구현하지 않는다.
- A 복구 이후 RIGHT 입력(sequence80)으로 offset10→20/generation193, 재청취(sequence81)로 generation194가 기록됐다. 따라서 B의 복구 기준은 A의 최종 page_index0/node_index6/offset20/generation194다. 원래 offset10을 강제 복구 기준으로 쓰지 않는다.
- B는 준비된 새 프로세스로 동일 위치 복구 후 idle 종료를 확인한다. A의 앱/COM/audio 정리는 증거를 확보했으므로 동일 active 종료를 반복할 필요는 없다. B에서도 native exit null이면 동일 계측 한계로 기록하고 무한 재시도하지 않는다.

## 범위와 준비 상태

이전 R2는 실제 reading 기능 관측과 NAV/FRAME/audio 증거를 확보했지만 Ctrl+C 뒤 native exit는 null, COM/audio close 완료 로그는 없었다. 해당 결과를 성공 종료로 바꾸지 않는다. 이번에는 같은 제품 코드·설정·상태·stable device ID로 새 프로세스를 실행해 cursor 복구와 정리 종료를 구분하여 확인한다.

Laptop C runtime에 `h3-restart-20260915-a`, `h3-restart-20260915-b`를 준비했다. 각각 별도 one-shot evidence 폴더다. 설정은 원본 R2 `config/device-app.stm-reading.toml`을 그대로 참조한다. 기존 SQLite/artifact/cache/credential을 삭제하거나 복제 초기화하지 않는다. 서버 health200, 준비 시 Python0, launcher PowerShell 구문과 진단 Python 컴파일 PASS. 제품 변경0, flash/reset0, 준비 과정 COM 열기/FRAME 송신0.

## 실행 경로 및 계측 차이

- production `python -m asl_device --config ...`, 물리 STM controls/presenter 및 실제 음성 유지. initial-mode override 없음.
- 기존 PowerShell `2>&1 | Tee-Object`를 없애고 직접 native 명령을 실행한다. 콘솔 transcript와 native exit를 보존한다. Ctrl+C signal handler를 변경하지 않는다. 따라서 direct 실행에서도 종료 코드가 미관측이면 null을 그대로 유지한다.
- run-only sitecustomize에서 기존 Serial pass-through 관측과 DeviceApplication.stop / ReadingAudioController.close / SoundDeviceWavPlayer.close의 enter/return/error를 추가한다. 원래 메서드를 한 번 호출하고 반환값과 예외를 보존한다. early import와 관측 비용으로 timing이 달라질 수 있으며 계측되지 않은 startup/reconnect 일반 수용을 증명하지 않는다.
- COM11 수집기는 숨김 프로세스로 실행하며 종료 시 stop 파일로 정리한다. 진단 코드 사본: `docs/evidence/h3-validation-20260915/run-h3-restart.ps1`, `restart-sitecustomize.py`.

## 사용자 절차

1. A run 실행. reading catalog가 안내되면 같은 `새 데이터팩 2026-09-08 23:47 #28` 선택 후 CONFIRM 짧게. 이동 버튼은 사용하지 않는다. 시작 연결/모드 이상이면 별도 재시작·레버 조작을 반복하지 말고 보고한다.
2. 이전 R2 마지막 위치(page_index0, node_index6, braille_offset10, generation192)를 기준으로 수식 음성 및 점자 창 복구를 확인한다. generation은 후속 명령으로 증가할 수 있으므로 위치/내용과 함께 대조한다.
3. 음성 완료 뒤 CONFIRM 짧게로 재생하고 약3초 뒤 Ctrl+C 한 번. 명령 프롬프트 복귀까지 최대40초 기다린다. 음성 정지와 종료 시 셀 상태를 관측한다. 창 닫기/강제 종료/두 번째 Ctrl+C를 사용하지 않는다.
4. A 결과를 수집·검증한 후 B 실행을 안내한다. B에서 같은 READY의 위치/내용을 재확인하고 음성이 끝난 뒤 Ctrl+C 한 번으로 idle 종료를 비교한다. A가 미종료면 B를 열지 않는다.

화면/reading에 따른 정상 FRAME 및 CLEAR 외 별도 패턴을 보내지 않는다. 비정상 기계 동작 시 사용자는 시험을 중지하고 보고한다. 접촉/전원 진단은 재발 시에만 다시 다룬다.

## 완료 기준 및 판정 경계

- 복구: reading_resumed 위치·점자 offset 및 FRAME이 이전 durable cursor와 일치하고 사용자가 음성/셀 내용 복구를 확인한다. 새 세션/generation 값 자체의 동일성은 요구하지 않는다.
- 종료: stop 반환, cleanup_failures 없음, COM closed, audio controller/player close 반환, worker 종료를 보장하는 기존 close 경로 정상 반환, Python atexit, native exit0, collector 종료 및 남은 app 프로세스0을 각각 기록한다. 하나가 없으면 관측 부족/실패로 구분한다.
- Ctrl+C 후 최종 CLEAR의 실제 수납은 별도 관측이며 ACK 또는 프로세스 종료로 대체하지 않는다.
- H4 camera→fresh READY 전체 경로, power-loss recovery, Bluetooth reconnect 일반 신뢰성은 이 시험의 수용 범위가 아니다.
