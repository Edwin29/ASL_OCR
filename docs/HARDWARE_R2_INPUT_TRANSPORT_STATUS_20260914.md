# R2 입력·전송 검증 진행 상태

> 2026-09-15: [최소 수정 실행 결과](MINIMAL_CORRECTIONS_RESULT_20260915.md)에 무응답 open 재시도, 초기 MODE 후 최신FRAME1회 재전송, 셀 mapping 보정 및 검증을 기록했다. 첫 FRAME의 원시 소실은 복구로 완화했으며 제거했다고 주장하지 않는다. 아래 실험 당시 실패/미확인 증거는 보존한다.

## 확인된 결과

| 경계 | 결과 | 근거와 제한 |
|---|---|---|
| 일곱 버튼 기본 입력 | 관측 확인 |52 unique NAV,52 ACK,sequence2..53 연속. UP 등 반복,DOWN A/R,CONFIRM3 SHORT+1 LONG. 페이지 순서 차이는 사용자의 조작 순서 혼동 확인으로 정리 |
| MODE 전환 | 양방향 전환 확인 |R,A,R,A. 물리 위치 표시와 반대 위치 startup은 미확인. 아래 reset에서A startup만 관측 |
| 실제 ACK 손실·재전송·host 중복 제거 | PASS |UP sequence54를 두 번 수신,첫 ACK1회 의도적 누락,재전송 ACK1회 송신,production host application event1개. 모터 FRAME0개; host 생성 FRAME1개는 입력 경계 격리를 위해 진단 adapter에서 억제 |
| 첫 reset 시도 | harness 영향 |Serial factory 안에서 reset CLI 종료를 기다려 host read가 늦게 시작됨. V2 연결·초기 CLEAR 파싱은 관측됐으나V3 startup acceptance로 사용하지 않음 |
| Host reader 선행 후 reset | V3/MODE 성공,첫 FRAME FAIL |실제 production host가ACK,HELLO,3 직후 보낸 초기 CLEAR의 `FR`이 STM 로그에서 누락. `BT RX: AME,...` / `BT RX UNKNOWN`. NAV,V,A,1은host에 전달되고ACK됨 |

첫 FRAME 실패는 앞선 R2-O 직접 송신 실험뿐 아니라, host reader가 활성화된 상태에서 실제 production `StmSerialControlSource`로도 재현됐다. 이 실험에서는 FRAME을 억제하거나 readiness 이후로 지연하지 않았다. 따라서 직접 송신 도구만의 현상이라는 가설은 지지되지 않는다. 최초 reset 시도의 V2 fallback은 별도의 harness 영향을 받았으므로 혼동하지 않는다.

First failing boundary: host의 완전한 FRAME write → STM의 완전한 line 수신. 관련 source는 handshake의 polling read 이후 debug 출력과 IRQ 시작으로 이어지는 전환 및 IRQ 시작 시 RX register 정리 경로다. 해당 경로가 구체적인 원인 후보지만 정확한 byte 소실 지점은 추가 계측/재현으로 확정해야 한다. 본 실험만으로 UART 핀/baud/FRAME 문법을 변경하지 않는다.

## 증거

- [R2-I 결과](evidence/hardware-resume-20260914-r2i/RESULT.md), [분석](evidence/hardware-resume-20260914-r2i/analysis.json)
- [ACK-loss 결과](evidence/hardware-resume-20260914-r2t-ack/result.json), [raw](evidence/hardware-resume-20260914-r2t-ack/events.jsonl)
- [첫 reset 결과](evidence/hardware-resume-20260914-r2t-reset/result.json)
- [수신 선행 reset 결과](evidence/hardware-resume-20260914-r2t-reset-ready/result.json), [raw](evidence/hardware-resume-20260914-r2t-reset-ready/events.jsonl)

Firmware는 기존 검증 ELF `4e415e19ffcdbcc845d2b8f27d6e719812dcbc4ed6e26082c2478e4334d4220e`, production host module SHA256 `9cec3f2ec6bde29925385af5324a4ce05e824c649b3aa34509dbdbf3fd974a2d`. Host import가Laptop C integration을 가리키는지 실행 중 확인했다. 이 후속 시험에서 product 수정·flash0, SWD reset2회, 실제 초기 CLEAR FRAME2개(각 시도1개), 모든 port/process 종료. 두 번째 CLEAR의 물리 적용은 parser가 거절했으므로 미확인이다.

## 남은 순서

1. R2-T의 bounded 정상/분할/malformed/overflow 복구 및 burst 수신을 독립 수행. 새 packet 목록·상한·실제 구동을 실행 전에 제시한다. 현재 ACK 재전송 시험을 이 경계의 PASS로 대체하지 않는다.
2. 실제 Bluetooth link/host serial reconnect와 반대 MODE 위치 startup을 분리 확인. 이번 시험은 MCU reset이며HC05 radio 단절이 아니다.
3. 셀 역순 보정과 초기 FRAME 수신 결함의 최소 수정·회귀·실물 재검증 후 fresh H2를 정상 수용한다. 미수정 상태에서 수행하는 결합 시험은 알려진 실패를 기록한 진단 run으로만 취급한다. 독립 가능한 남은 시험은 계속하되H2/H3 전체PASS로 합산하지 않는다.
4. Fresh H2(console+S0+실제audio+STM/셀),H3(물리controls+동일출력)를 순서대로 진행한다. 기존 H1/1B PASS와 이번 8상태 물리 관측을 각각 보존한다.

## 사용자 관측 및 수정 방향 질문

사용자는 두 번째 reset 뒤에도 전체 점 수납을 확인했다. 이미 수납된 상태가 유지된 관측이며, 파서가 거절한 초기 CLEAR의 물리 적용 증거로 사용하지 않는다.

고정 딜레이는 handshake 전환 경합을 가리는 진단 비교 후보이나, 검증된 충분 시간은 아직 없다. Host는 ACK,HELLO 직후 FRAME을 쓰고, firmware는 ACK를 polling으로 읽은 뒤 blocking debug 출력 및 IRQ 시작을 수행한다. IRQ 시작은 RX register의 남은 바이트를 읽어 버릴 수 있다. 따라서 우선 후보는 기존 프로토콜에서 handshake→정상 RX 사이의 바이트 보존을 회복하는 국소 수정이다. 단순 IRQ 시작 함수 위치 이동만으로 이미 도착한 바이트 폐기까지 해결되는지는 따로 확인해야 한다.

대안은 firmware의 실제 RX 준비 이후 신호를 host가 기다리는 방식이다. 현재 초기 MODE NAV는 IRQ 시작 후 송신되어 진단에서 준비 기준으로 사용할 수 있었으나, 이를 production 필수 시작 조건으로 채택하려면 MODE 의미, 세션별 초기화, timeout, 중복, V2/legacy 호환성을 검토해야 한다. 새 READY 메시지도 FRAME 출력 준비와 입력 ACK 의미를 섞지 않는 별도 계약 검토가 필요하다. 부팅 때만 기다려서는 reconnect의 같은 전환 문제를 덮지 못한다. 이번 질문에 답하면서 product source는 변경하지 않았다.

사용자 결정: **수신 전환 중 바이트 보존을 우선 적용 방안으로 기록하고 RX 시험을 계속한다.** 이 결정은 이번 RX 시험 중 즉시 제품 코드를 변경하는 지시로 처리하지 않는다. 딜레이 추가나 새 READY 프로토콜은 우선 수정안으로 채택하지 않는다.

## 실제 RX 시험 후속 결과

정상 CLEAR200,3조각 분할 CLEAR201,잘못된 CSV/범위/후행구분자3개,256바이트 초과 행과 같은 행의FRAME suffix,복구 CLEAR202,50ms inter-write wait의20개 전체63/0 교대 FRAME210..229,최종 CLEAR230을 실제HC05로 전송했다. [분석](evidence/hardware-resume-20260914-r2t-rx/analysis.json), [원시 결과](evidence/hardware-resume-20260914-r2t-rx/result.json), [송신 목록](evidence/hardware-resume-20260914-r2t-rx/packets.json).

유효 FRAME24개가 모두 순서와 셀 값이 일치하는 state dump로 확인됐다. 잘못된 형식3개는FORMAT ERROR,긴 행1개는LINE TOO LONG으로 거절되고 해당 suffix node903은 적용되지 않았으며, 다음 정상 FRAME으로 복구했다.20개 연속 FRAME도 누락 없이 파싱됐다. 이번 연결 준비 후 RX/parser 경계는PASS이며, 최종 물리 수납은 사용자 관측 대기다. Source 수정/flash/reset0회,포트 종료.

긴 행 거절은 IRQ ring 강제 overflow 시험이 아니다. 실제 UART error/IRQ ring counter는 직접 읽지 않았고 TRANSPORT ERROR 출력은 없었다. 따라서 그 counter가 모두0이었다거나 강제 overflow 복구를 실물 검증했다고 확대하지 않는다. 별도 초기 FRAME 실패와 셀 역순 보정은 미해결로 유지한다.

사용자 최종 관측: 모든 점 수납 완료, 걸림·이상 동작 없음. 위 bounded RX 시험의 최종 물리 CLEAR 관측을PASS로 갱신한다. 연속 전송 중 매 intermediate pattern의 정확한 물리 적용 시각까지 측정한 것은 아니다. 다음 독립 단계는 반대 MODE 위치 전환과 startup/reconnect 확인이다.

## 반대 MODE 위치 재시작 확인

사용자 레버1회 전환에서NAV,V,R,2와ACK를 확인했다. 그대로 유지한 상태에서 active-reader-first production host를 사용해SWD reset1회 수행: V3 연결,초기NAV,V,R,1,host `lever/released` 이벤트와ACK 모두 확인했다. [전환 기록](evidence/hardware-resume-20260914-r2t-mode/result.json), [재시작 기록](evidence/hardware-resume-20260914-r2t-mode-reset/result.json).

앞선A/capture와 이번R/reading의 양쪽 전기적 위치에서 software-reset 후 초기MODE 보고가 일치한다. 물리 라벨 대응과 완전 전원 차단 후 startup은 미검증이며 이 결과로 대신하지 않는다. 이번에도 production 초기 CLEAR는 `AME,...`으로 거절됐다. 수신 전환 바이트 보존 우선 수정안은 그대로 유지하며 아직 product 변경하지 않았다.

이번 추가 단계: FRAME1개,SWD reset1회,flash0,모든포트종료. 현재 레버는R/reading 위치다. 다음 남은 전송 경계는host serial/실제Bluetooth link의 단절·재연결이며MCU reset 시험과 구분한다. Fresh H2/H3 정상수용 전에는셀 역순 및초기FRAME 오류 수정·재검증이 필요하다.

## Host 포트 재연결 실패와 독립 비교

실제COM9 핸들 close 및 OSError1회 주입 뒤 production 재연결 루프가 다시 open하는 것은 확인됐다. 그러나 DOWN 송신이 host에 수신되지 않아입력 복구FAIL이었다. 단절 전 protocol이None이고 기준 입력도 없던 시험이므로 established-V3 recovery의 확정 결함으로 확대하지 않았다.

같은UP 버튼으로 기준 입력을 확보한 비교에서도 단절 전sequence2는수신/ACK/app event가 있었으나,재연결 후sequence3은STM에서4회송신됐음에도host RX/app event0이었다. 이때 단절 전host는sequenced NAV에 따른V2상태였으며V3handshake를검증한것은아니다. [비교 결과](evidence/hardware-resume-20260914-r2t-port-paired/RESULT.md).

Production 밖 raw pyserial 비교에서는첫open read_until30bytes,500ms뒤재open read_until52bytes,같은handle 비차단읽기22bytes의실제HELLO수신을확인했다. [Raw 결과](evidence/hardware-resume-20260914-r2t-raw-reopen/result.json). 따라서보편적인COM재개방불능이나read_until자체실패로단정할수없다. 현재분류는`insufficient_evidence`:production worker lifecycle,장애주입harness,Windows/Bluetooth타이밍을추가분리해야한다. Product 수정0,추가모터FRAME0,reset/flash0,모든collector종료.

다음작업은동일단절조건에서worker read진입/종료·살아있는thread·실제handle·수신대기바이트를계측하는bounded software diagnostic이다. 더이상의동일버튼반복을사용자에게요구하지않고원인을좁힌다. R2-T전체PASS와fresh H2/H3수용은아직미완료다.
