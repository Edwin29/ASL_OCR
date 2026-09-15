# H2 우선 실행 결정과 진단 기록

## 판단

사용자 요청에 따라 R2-T 추가 원인 조사를 뒤로 옮기고 H2 결합 시험을 먼저 수행한다. 정상 수용 조건은 완화하지 않는다. 제품 코드/펌웨어 수정 및 flash는 하지 않는다.

기존 R2-I 기본 입력, ACK 손실·중복 제거, 준비된 연결에서 정상/분할/형식 오류/긴 행 복구/연속 FRAME 수신, 물리 8상태 및 CLEAR 결과는 재사용한다. H2에서 실제로 검증한 정상 출력·음성·navigation 항목은 같은 경계의 반복 시험을 대체할 수 있다.

| 남은 핵심 항목 | H2를 먼저 해도 되는가 | H2 정상 결과로 생략 가능한가 |
|---|---|---|
| 논리 셀 순서와 실제 C1–C10 역전 | 진단 가능. 현재 매핑 그대로 기록 | 아니오. 실제 읽기 순서 오류를 따로 보정·검증해야 함 |
| handshake 직후 초기 FRAME의 FR 손실 | 첫 송수신도 기록하며 진행 | 아니오. warm 연결 정상 결과는 초기화 경합을 증명하지 않음 |
| production 포트 재연결 후 host RX 없음 | 정상 연결 H2와 독립 조사 | 아니오. worker/harness/환경 원인 미확정 |

추가 미검증 항목: 실제 무선 단절, 완전 전원 차단 후 시작, 물리 MODE 라벨 대응, 강제 IRQ ring overflow. H2 정상 경로에 포함되지 않으며 이번 실행 전 필수 반복 단계로 두지 않는다. MCU reset/긴 행 overflow 결과로 대체했다고 기록하지 않는다.

## 실행 구성

- Run: `h2-first-20260914`
- Laptop: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h2-first-20260914`
- 실제 integration Python 및 세 package import 확인. host SHA256 `9cec3f2ec6bde29925385af5324a4ce05e824c649b3aa34509dbdbf3fd974a2d` 확인.
- 검증된 1B harness를 진단 파일로 복제. process별 고유 command namespace, Realtek 출력 guard, interactive desktop, 배터리 실행 허용을 유지.
- ConsoleControlSource → production DeviceApplication/Coordinator/S0 → production audio + STM presenter(COM9/9600). COM11/115200 debug는 읽기 전용.
- 실제 physical NAV는 애플리케이션 조작에 사용하지 않음. 카메라/upload/parser/finalize 우회. 기존 READY 사용.
- 새 로컬 runtime state를 사용하지만 stable device ID 및 서버의 reading cursor는 유지하며 정상 reading 명령에 따라 갱신된다.
- serial wrapper는 실제 read/write를 그대로 전달하고 기록한다. FRAME 억제, readiness 지연, 셀 순서 보정 없음. instrumentation이 있으므로 timing-sensitive 결과의 한계는 유지.
- 생산 module entrypoint 자체가 아닌 명시적인 custom composition이다.

## 사용자 절차

1. Catalog 음성 확인, 대상 READY 선택 및 confirm.
2. down/up, page_next/page_previous를 각각 음성 완료 후 입력.
3. 길이가 10셀을 넘는 수식 focus에서 right/right/left: cursor offset과 실제 셀 변화를 함께 확인.
4. confirm 재청취; 짧은 간격 down/down/up 후 최종 focus의 음성·셀 확인.
5. confirm long으로 catalog 복귀/CLEAR 확인; 같은 READY 재진입.
6. Ctrl+C 정상 종료 후 같은 설정 재시작, stable cursor 및 audio/serial close 확인.

각 단계는 snapshot의 focus/generation, host FRAME, STM parser 상태, 사용자 음성/물리 관측을 분리해 기록한다. known reversed order를 숨기지 않는다. 걸림·비정상 소음이면 추가 구동을 멈춘다. 소프트웨어 실패는 기록하고 독립 가능한 단계는 계속한다. 원인 불명 실패가 남으면 H2/H3/H4 전체 PASS로 선언하지 않는다.

## 증거와 현재 상태

진단 코드: `docs/evidence/h2-first-20260914/`. Remote `run-manifest.json`, `logs/audio-console-events.jsonl`, `logs/serial.jsonl`, `evidence/interactive-lifecycle.json`을 사용한다. 이번 계획 작성 시점에 H2 실제 사용자 관측은 아직 시작 전이다.

## 시작 결과

- Interactive Windows session 4, Realtek 출력 guard 통과. 고유 namespace를 생성했다.
- 첫 orchestration은 PowerShell 실행 정책으로 거절되어 application 실행 전 종료됐다. 기존 방식의 process 한정 ExecutionPolicy Bypass로 재실행했다. 전역 정책 변경 없음.
- Desktop production server 미기동으로 server_retrying을 관측했다. 기존 background launcher로 서버를 기동한 뒤 health 200, presence 201, catalog 200을 확인했다. 기존 state를 초기화하지 않았다.
- Catalog index 0은 `새 데이터팩 2026-09-08 23:47 #28`. Catalog 안내와 제목 audio의 native playback completion을 확인했다. 사용자 실제 청취는 확인 대기.
- 이번 H2 시작에서도 첫 CLEAR가 STM에서 `AME,...` / UNKNOWN으로 기록됐다. 알려진 첫 FRAME 결함이 재현됐으며 정상 reading 단계를 계속한다. 사용자가 이미 수납 상태를 관측해도 이 CLEAR 적용 성공으로 해석하지 않는다.
- 시작 evidence는 `events-startup.jsonl`, `serial-startup.jsonl`로 복사 보존했다. H2 사용자 reading 절차는 진행 대기이며 전체 PASS가 아니다.

## 정상 reading 및 수식 창 이동 관측

사용자는 여러 차례 이동에서 정상 동작, 실제 음성과 내용 일치, left/right 정상 동작과 offset 변경을 확인했다. 기존 셀 순서 역전은 동일하게 관측됐다. 이는 음성 및 navigation의 사용자 관측 PASS이며 물리 읽기 순서까지 PASS라는 의미는 아니다.

`events-navigation.jsonl`, `serial-navigation.jsonl`, `navigation-analysis.json`을 보존했다. 대상은 `datapack-b7d5a769ad5347738d491f1b39e5e909`. Reading snapshot 21개의 page/node/span/offset/generation/10셀 padded payload가 모두 host 송신과 STM RX의 FRAME에 일치했다. Debug read는 timeout으로 행이 분할될 수 있어 순서대로 결합한 뒤 비교했다. 개별 read chunk가 불완전한 것을 FRAME 손실로 판단하지 않았다. 이 비교는 수신 일치이며 모든 점의 실제 적용을 독립 계측한 것은 아니다.

수식 focus `pg-a11ebe27eb63-00000001-R-vl004`에서 generation16–24의 offset은 `0→10→20→30→40→30→20→10→0`. Offset40에서는 3셀과 7개의 padding zero를 송신했다. 수식 창 이동 snapshot은 spoken_text/audio_ref가 null이며 별도 음성 재생 없이 창을 이동하는 경로다. 관측 구간 reading_audio_failed 0건. Generation14 중단 이후15 완료,16 완료를 확인했으나 정해진 빠른 세 명령 결합 및 재진입/종료/재시작은 별도 검증을 남긴다.

사용자의 `11−n` 제안은 기존 사진 기준 물리 번호와 논리 번호의 대응 표기로 기록한다. 기존 물리 Cn은 논리 C(11−n)에 대응한다. 번호 표기만 변경하면 실제 점자 문자열의 좌→우 배치는 바뀌지 않는다. 독자 기준 정상 읽기 방향에서 논리 C1이 어디에 와야 하는지와 구분하며, 펌웨어 매핑 또는 LUT는 이번에 수정하지 않는다.

## 사용자 후속 묶음 관측과 종료

사용자는 재청취/빠른 이동/catalog CLEAR/재진입/종료 안내 후 모두 정상 작동했다고 보고했다. `events-before-restart.jsonl`과 `lifecycle-before-restart.json`을 보존했다. 실제 로그에는 generation27의 page1/node5 재진입(`reading_resumed`)과 이후 generation28 page1/node4 수식 이동, catalog 복귀가 있다. Generation27과28의 음성 중단을 확인했지만, 요청한 0.5초 간격 down/down/up 세 명령의 완전한 snapshot 연속열은 확인되지 않아 정확한 rapid-three-command 절차 PASS는 아직 부여하지 않는다.

종료는 application_exit_code0, presentation_failures braille0/audio0, audio worker 종료 및 close_complete=true, error=null. Python 프로세스 없음. 종료 시 catalog여서 cursor_at_exit=null이며 cursor 손실로 해석하지 않는다. 재시작 복구 비교 기준은 마지막 reading snapshot인 generation28/page_index1/node_index4/offset0, focus `pg-a11ebe27eb63-00000001-R-vl004`이다.

원본 종료 evidence를 먼저 보존하고 동일 config/실행기, 새 process command namespace로 Restart1을 시작한다. Catalog에서 같은 READY를 열어 위 cursor와 실제 음성·셀의 복구를 확인한다. 이는 graceful app restart 시험이며 장애주입 COM reconnect 검증을 대체하지 않는다.

## Restart1 사용자 관측과 증거의 한계

사용자는 복구와 후속 조작 모두 정상이라고 보고했다. `events-final.jsonl`에는 generation28/page1/node4/offset0/focus vl004의 정확한 reading_resumed와 음성 완료가 있다. Replay29 후 down30/node5, down31/node6, up32/node5를 확인했다. Generation29/30은 중단,31/32는 완료됐고 마지막32 이후 stale audio 이벤트는 없다. 첫 두 down 처리 간격은 약0.69초, up은 다음 fetch 기준 약3.09초 뒤다. 따라서 두 연속 이동 중 supersession과 마지막 음성 완료는 확인됐으나 모든 세 입력이0.5초 간격이었다고 기록하지 않는다.

중요한 미확인: `serial-final.jsonl`은 Restart1 시작 이후 host_tx/host_rx/stm_debug 항목이 전혀 없다. 사용자 정상 관측만으로 재시작 뒤 실제 FRAME 전송·물리 갱신을 PASS로 승격하지 않는다. 정상 읽기 중 출력 보존과 실제 새 출력 적용은 구분해야 한다. 앞선 port reopen 문제와 연결되는지, handshake 대기인지, harness/driver 문제인지는 미확정이다.

수집 시 `lifecycle-final.json`은 첫 실행의 종료 시각(14:25:37 UTC)이 그대로인 이전 기록이다. Restart1의 종료 증거가 아니다. Laptop Python PID25592/29032가 존재했으므로 새 실행의 정상 종료도 아직 확인 대기다. 파일명 final은 이번 수집 사본 이름이며 run 완료를 뜻하지 않는다. 이번 판단 시점 H2 전체 PASS 아님. 제품 코드 변경0.

## 종료 확인과 현재 판정

후속 질문에 사용자가 정상 작동을 확인했다. 질문 대상이 재시작 뒤 수식→본문 이동 시 물리 점 수납이었으므로 해당 정상 관측으로 기록하되, serial 증거와의 불일치는 유지한다.

Restart1의 종료 기록을 새 이름 `lifecycle-restart1-closed.json`으로 보존했다. 시작14:26:51 UTC, 종료14:29:32 UTC, application_exit_code0, braille/audio presentation_failures0, audio worker 종료 및 close_complete=true, error=null. 마지막 cursor는 generation32/page1/node5/offset0이며 Python 프로세스는 남아 있지 않다. `events-restart1-closed.jsonl` 및 hash 목록도 보존했다. 앞선 첫 실행 종료 사본은 덮어쓰지 않았다.

Serial 파일의 마지막 기록은 여전히 첫 실행 catalog CLEAR(14:25:28 UTC)다. 따라서 Restart1의 실제 host FRAME/STM 적용 연쇄는 미확인이다. 사용자 정상 관측은 보존하지만 기록 부재를 로깅 결함 또는 제품 전송 실패 중 어느 하나로 확정하지 않는다.

현 시점 종료 판정:

- 정상 reading 탐색/수식 창 이동/음성 내용 일치: 사용자 관측 및 첫 실행 송수신 대조 확인.
- 음성 supersession/latest completion, catalog 재진입, 앱 재시작 cursor 복구, 정상 종료: 관측 범위 내 확인. 세 명령의 실제 간격은 위 기록을 따른다.
- 셀 역순, 초기 FRAME prefix 손실: 미해결 유지.
- 재시작 후 물리 동작: 사용자 정상 관측 있음; 대응 송수신 증거 불충분.
- H2 전체 수용/H3/H4: 아직 PASS로 선언하지 않음.

다음 우선 작업은 추가 반복 조작 전에 run-only 계측에서 serial open 성공/실패, worker 상태, handshake 상태와 실제 handle ownership을 남겨 재시작 증거 공백을 좁히는 것이다. 기존 포트 재연결 조사와 묶되 원인을 가정하지 않는다. 셀 순서 보정 및 RX 전환 바이트 보존은 별도의 최소 수정 범위로 유지한다. 이번 후속에서 product 수정/flash/추가 servo 송신0.
