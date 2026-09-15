# 최소 수정 후 H3 재검증

## 후속 종료·재시작 확인 반영

[종료·재시작 결과](H3_RESTART_RECOVERY_PLAN_20260915.md)의 A/B에서 cursor 복구와 계측된 application/COM/audio 정리 정상 반환, application.exit_code0 및 Python atexit/프로세스 종료를 확인했다. 따라서 아래 R2 당시의 정리 미확인은 후속 계측 범위에서 보완됐다. PowerShell native exit code null은 계속 미확인이고 종료 CLEAR는 현 구현에서 전송하지 않아 셀 잔류했다. B는 자동3회 open 후 V2 연결이므로 V3 재접속 수용은 미해결이다. 기존 R2 V3 물리 reading 기능 PASS와 구분한다.

## 최종 실행 결과: 물리 reading 기능 PASS, 종료 lifecycle 미확인

2026-09-15 사용자가 마지막 묶음까지 정상 관측을 보고하고 Ctrl+C 종료 완료를 확인했다. Launcher 실행 시각은 08:56:00.586–09:06:10.122 UTC(17:56–18:06 KST), 약10분10초다. 종료 후 Laptop Python 프로세스가 없고 `debug_exited=true` 및 debug-stop 파일이 확인됐다.

최종 원본 사본은 `docs/evidence/h3-validation-20260915/r2-closed-*`, SHA256 목록은 `r2-closed-hashes.json`, 기계 대조 요약은 `r2-result-summary.json`이다. 기존 중간 사본은 보존했다. NAV sequence1–76의 수신과 ACK, reading generation134–192 FRAME의 STM debug 대조, 재청취와 동일 cursor/generation 재진입 및 사용자 실제 음성/셀 관측을 근거로 **이번 계측된 production entrypoint + 기존 READY 물리 reading 기능 범위 PASS**로 판정한다. 추가 이동도 generation192까지 기록됐다.

종료에서는 `native_exit_code=null`, host `closed` 이벤트0이며 audio close 완료 로그도 확보되지 않았다. 따라서 **프로세스 종료 확인과 orderly resource shutdown 검증을 구분**한다. Ctrl+C가 PowerShell pipeline/자식 프로세스와 정리 관측에 미친 영향은 미확정이며 clean exit0 또는 native crash로 단정하지 않는다. 마지막 읽기 음성 interruption은 이전 RIGHT 입력에 대응하므로 shutdown close 증거로 사용하지 않는다. 최종 STM debug는 generation192 FRAME이고 종료 CLEAR 수납은 관측되지 않았다. 이미 검증한 catalog CLEAR와 분리한다.

남은 사항: (1) native exit/COM/audio close를 관측할 수 있는 실행기 종료 경로의 bounded 점검 및 이후 프로세스 재시작 cursor 복구, (2) R1 시작 무응답과 최초 FRAME 손실의 근본 원인/재접속 신뢰성은 기존 미해결 상태 유지, (3) 준비 조건을 갖춘 뒤 H4 live capture부터 실제 버튼·음성·점자 전체 경로 검증. 이번 결과로 H4 또는 전체 integration-ready를 선언하지 않는다. 이번 기록/대조 작업의 product source 변경0, 추가 flash/reset/serial 송신0.

## 최신 상태: R2 V3 연결 확인, 물리 reading 절차 진행 대기

R2 실제 실행에서 COM9 첫 open이 성공했다(t260245.343). `HELLO,3` 수신과 `ACK,HELLO,3` 송신, 나뉘어 수신된 `NAV,V,R,1`의 복원 및 `ACK,1` 송신이 확인됐다. 초기 all-zero FRAME과 초기 MODE 수신 후 한 번의 FRAME 재송신도 기록됐다. Device는 capture 기본 화면에서 reading catalog로 전환했고 catalog 음성의 playback completion이 기록됐다. STM debug에서도 all-zero CELLS 해석을 확인했다. 물리 수납 여부는 별도 사용자 관측 대상이다.

시작 증거 사본: `docs/evidence/h3-validation-20260915/r2-host-startup.jsonl`, `r2-device-startup.log`, `r2-debug-startup.jsonl`. 원격 원본 run은 실행 중이며 이 파일들은 종료 결과가 아닌 중간 사본이다. 추가 product 수정/flash/reset 없이 연결됐다. 계측으로 실행 timing이 달라질 수 있으므로 R1 무응답 원인의 해결이나 재접속 일반 수용을 의미하지 않는다. 다음은 기존 H3 물리 reading 묶음 절차이며 완료 판정은 아직 보류한다.

## R2 마지막 묶음 보완: 정상 관측 및 상관 로그 확보

사용자가 마지막 묶음도 “전부 정상”으로 보고했다. `r2-final-actions-host-serial-37200.jsonl`, `r2-final-actions-device-output.log`, `r2-final-actions-debug.jsonl` 중간 사본 및 `r2-final-actions-hashes.json`을 보존했다. 아직 앱 종료 사본은 아니다.

- DOWN `NAV,D,A,42`(260677.843) → `NAV,D,R,43`(260679.187), 각각 ACK. 실제 host 관측 유지 간격은 1.344초로, 안내한 약2초와 구분한다. 유지 중 generation166–168로 반복 이동했고 마지막 FRAME은 release 수신 약31ms 뒤 나왔다. 이후 다음 UP 입력(260682.828) 전까지 추가 FRAME 없음: 마지막 진행 중 결과를 반영한 뒤 반복 이동이 멈춤을 확인했다. 정확히2초 유지 시험으로 기록하지 않는다.
- CONFIRM SHORT sequence48 → generation173에서 직전 generation172와 동일 audio_ref_digest `5c697952e9e9` 재생 및 completion.
- CONFIRM LONG sequence53 → reading catalog 및 all-zero FRAME. 사용자 전체 수납 정상 관측.
- 동일 READY CONFIRM SHORT sequence54 → `reading_resumed`, page_index0/node_index6/offset10/generation176 복구. 퇴장 전과 동일 FRAME 재전송, 해당 generation176 음성 completion(260742.031) 및 사용자 음성/점자 정상 관측.

기존 READY의 물리 reading 기능 묶음은 사용자 관측과 상관 로그가 확보됐다. 현재 남은 이번 run 절차는 Ctrl+C 종료 후 serial/audio/collector lifecycle 확인이다. 정확한2초 유지, process 재시작 복구, reconnect 일반 수용, H4 live capture 전체 경로를 이번 결과로 대체하지 않는다. R1 무응답 원인 및 첫 FRAME 손실의 근본 원인은 미해결로 유지한다. 제품 변경0.

## R2 사용자 정상 관측 및 로그 대조

사용자는 안내한 묶음에 대해 “전부 정상”으로 보고했다. 물리 음성/점자 내용·수정된 셀 순서 등의 사용자 관측으로 보존한다. 실행 중 사본 `r2-observation-*`와 SHA256/요약 `r2-observation-summary.json`을 수집했다.

Host RX에서 NAV sequence1–41 및 각각 ACK를 확인했다. V3 DOWN A/R, UP, LEFT/RIGHT, NEXT/PREV, 최초 CONFIRM SHORT가 존재한다. Generation134–165 FRAME의 STM debug 해석을 확인했고 offset40→30→20→10→0 및 0→10→20→30 변화를 확인했다. 여러 reading audio interruption/start/completion도 기록됐다. 초기 첫 FRAME은 여전히 `AME`로 손실되지만 MODE 후 한 번 재송신한 FRAME은 정상 해석됐다. 이는 기존 알려진 손실의 완화 성공이며 원인 제거가 아니다.

사본 시점에는 최초 CONFIRM SHORT 이후 추가 CONFIRM SHORT/LONG, catalog 복귀/재진입 이벤트가 없고 DOWN A/R 최대 간격도 약0.77초다. 따라서 사용자 전 항목 정상 보고와 별개로 2초 hold/release·재청취·목록/CLEAR·재진입의 상관 로그는 미확인이다. 이미 확인된 이동 항목은 반복하지 않고 마지막 묶음만 보완하도록 안내한다. 종료 및 close lifecycle도 아직 미검증이며 H3 전체 PASS는 보류한다. 이번 대조에서 product source 변경0.

## 실행기 수정 후 재시도

사용자 오류는 `python.exe : INFO: Could not find files for the given pattern(s).` / `NativeCommandError`였다. PowerShell ErrorActionPreference=Stop과 native stderr 병합이 INFO 출력을 종료 오류로 승격한 run harness 결함이다. 실제 제품 초기화의 최종 성공 여부는 이 메시지만으로 판단하지 않는다.

Native 실행 구간에만 Continue를 적용해 stderr는 보존하고 실제 프로세스 exit를 기록한다. Laptop 독립 probe에서 INFO stderr 이후 실행이 계속되고 의도적 exit7이 그대로 관측됨을 확인했다. 제품 코드 변경 없음. 기존 run은 보존하고 `h3-validation-20260915-r1`에 전체 config/secrets, 새 state 경로, 수정 launcher를 준비했다. 사용자 실행 대기이며 아직 H3 재시험 결과는 없다.

상태: 준비 완료, 사용자 실행 대기. 이전 H3와 동일한 physical reading 절차를 사용한다.

- 새 run: Laptop C runtime `h3-validation-20260915`.
- production `python -m asl_device`; physical controls/presenter, 실제 audio 유지.
- 설정 전체를 secrets 하위 폴더까지 복제하고 run 경로만 바꿨다. 설정 parse/기존 API key 읽기/COM9·audio 설정 확인. 인증값 출력/변경 없음.
- 새 host hash 확인, 이전 턴 새 ELF flash verification을 재사용. 이번에 flash/reset하지 않았다.
- Laptop→server health200, Python프로세스0. COM11 실제 exclusive open은 launcher 시작 때 확인.
- 이번에는 read-only debug collector와 production console 출력 파일을 남긴다. COM9 host 전송 자체의 별도 wrapper는 없다. protocol V3를 로그로 확인한 후 DOWN A/R 판단.
- 증거: `docs/evidence/h3-validation-20260915/manifest.json`, launcher/collector. Runtime device-output.log, debug.jsonl, launcher-lifecycle.json은 실행 후 생성된다. 미생성 로그를 PASS로 가정하지 않는다.

절차: MODE reading/READY 선택 → CONFIRM 열기 → UP/DOWN/LEFT/RIGHT 및 수식 offset/셀 순서 → 다음/이전 페이지 → DOWN2초 유지/해제 → CONFIRM짧게 재청취 → CONFIRM길게 catalog/CLEAR → 동일READY 재진입/복구. 이전 H3와 동일하며 정상 완료 후 Ctrl+C 종료 및 로그 수집.

화면 변경에 따른 정상 FRAME 및 CLEAR만 전송한다. 별도 자동 모터 패턴 없음. 실패가 발생하면 해당 경계를 기록하고 독립 단계는 가능한 범위에서 계속한다. H4 촬영→freshREADY 전체 경로와 분리한다.

## 첫 실행 상태

### R1 실제 입력 무응답

INFO 이후 product는 server/capture catalog/audio completion까지 진행했다. STM debug에는 HELLO V3→V2→legacy 대기가 반복되고 HOST CONNECTED가 확인되지 않는다. Controls 설정(COM9/9600/read20ms/reconnect500–5000ms)은 정상. 실제 app1개와 debug collector1개(각 venv launcher 자식 포함)가 있었으며 다른 reading app 중복 실행 증거는 없다. 따라서 capture 표시 자체는 기본값이고 물리 MODE 미반응은 아직 연결되지 않은 경계와 구분한다.

무응답 로그를 `r1-debug-unresponsive.jsonl`, `r1-device-unresponsive.log`로 보존했다. 이전 timeout 재시도 패치의 isolated recovery 성공을 이번 production 실행 성공으로 확대하지 않는다. 실제 open error인지 open-success/no-RX인지 현재 trace만으로 미확정이다.

사용자 종료 확인 후 R2(`h3-validation-20260915-r2`)를 준비했다. 원래 production module entrypoint를 유지하며 해당 run의 sitecustomize로 pass-through serial subclass를 추가해 COM9 open enter/success/error, read/return/bytes, TX/RX를 기록한다. timeout/retry/FRAME/controls semantics를 변경하지 않고 기존 evidence를 보존한다. 추가 firmware/reset/FRAME 송신 없음. 사용자가 재실행하면 원인 경계를 확인한다.

사용자의 시작 보고 후 확인 결과, launcher는08:47:51–08:48:04 UTC에 실행/종료됐다. native_exit_code=null, debug_exited=true. debug-ready는 생성됐지만 debug.jsonl0bytes, debug-stderr0bytes, device-output.log 없음, Python 프로세스 없음. 시작 후 V3나 버튼 시험을 확인할 수 없다. Launcher 구문 오류는 PowerShell parser에서 발견되지 않았다. 사용자 콘솔의 오류 문구를 요청했다. 이 정보만으로 production/firmware 실패 또는 정상 종료를 확정하지 않는다. 원본 사본 launcher-first-attempt.json 보존. 추가 reset/FRAME/flash0.
