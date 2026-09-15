# V2 연결 원인 및 V3 재접속 조건: 읽기 전용 조사

## 결론과 증거 범위

B의 V2 연결은 host의 V3 미지원 때문이 아니다. 펌웨어는 V3→V2→legacy 순으로 시도하며, 해당 V3 HELLO는 host read trace에 없고 다음 V2 HELLO만 수신됐다. COM 재시도와 펌웨어 협상의 시점 불일치가 직접적인 fallback 경로다. 첫 HELLO가 Windows Bluetooth/HC-05/UART 어느 구간에서 사라졌는지는 미확정이다. V2 연결 후 자동 V3 upgrade는 구현되어 있지 않다.

Laptop host SHA256 `2de4388da3912dc2098191ca4ca668db5c761f9ac606606348f0aba1facaf6fe`, 마지막 flash에 사용한 isolated main.c SHA256 `9bcb9ddf15342240697f1cff9bdd30ceaa1395f0588eb07e3ec69aa08e4ad6eb`를 다시 확인했다. 이번에 flash 메모리를 읽거나 reset하지 않았다. 이전 flash identity evidence를 유지한다.

## B 타임라인

동일 Laptop monotonic clock의 host/debug 수집 시각이며 STM 출력은 수집 지연이 있을 수 있다. 원본은 `docs/evidence/h3-validation-20260915/restart-b-host-serial-33408.jsonl`과 `restart-b-debug.jsonl`, 기존 hash 목록을 사용한다.

| 시각 | 관측 |
|---|---|
| 261491.859 | host 첫 COM open 성공, RX 없음 |
| 261496.859 | 5초 handshake deadline으로 close |
| 261497.531 | 두 번째 open 성공, RX 없음 |
| 261501.125–261502.625 | STM 이전 NAV,V,A,82를 초기1회+재시도3회 전송 |
| 261502.531 | host 두 번째 5초 deadline으로 close |
| 261503.125 | STM NO ACK → disconnected |
| 261503.140 | STM HELLO V3 출력/송신 경로 |
| 261503.546–261504.093 | host 세 번째 open 진입→성공 |
| 261504.359 | STM V3 실패 → HELLO V2 |
| 261504.390 | host HELLO2 수신, ACK2 및 초기 FRAME 송신 |
| 261504.453 | STM HOST CONNECTED V2 ASYNC |

V3 HELLO는 세 번째 open 완료보다 약0.953초 앞선다. open 완료 후 V3 대기 종료까지 약0.266초가 남았지만, host는 HELLO3를 받은 적이 없어 ACK3를 보낼 계기가 없었다. 더 오래 기다리는 host timeout만으로 누락된 HELLO가 다시 생기지는 않는다. 처음 두 COM 연결의 RX0은 확인됐지만 당시 STM 자체가 아직 이전 연결로 판단하고 있었으므로, 이를 모두 Windows silent-COM 결함으로 단정하지 않는다. NAV82 debug 송신이 host RX에 없는 정확한 물리 손실 구간도 미확정이다.

## V2 / V3 의미

| 항목 | V2 ASYNC | V3 EDGES |
|---|---|---|
| 협상 | HELLO2 / ACK2 | HELLO3 / ACK3 |
| DOWN | firmware가 SHORT를 생성하고 유지 시 firmware에서 반복 | firmware가 ACTIVATED/RELEASED 각 edge 전송, 반복은 host가 소유 |
| 해제 통지 | 별도 DOWN release packet 없음 | release packet/ACK, firmware queue release 자리 예약, host release 우선 처리 |
| 나머지 버튼 | UP/L/R/페이지 SHORT, CONFIRM SHORT/LONG, MODE A/R | 동일; 모든 버튼의 반복을 host로 옮긴 버전이 아님 |
| 공통 | sequenced NAV, ACK/dedupe, 비동기 FRAME | 동일 |
| 표시·음성 | 동일 10-cell FRAME grammar/PCA/LUT, S0/audio | 동일 |

근거: main.c:610 ButtonPollStep, :761 ButtonPollEdge, :884 ServiceControlTransmit, :1187 TryBluetoothHandshake, :1407 DOWN 분기. host stm_serial.py:258 이후 협상 및 DOWN edge V3 검사. V2 상태에서 DOWN A/R 수신 시 host는 UNSUPPORTED NACK을 보내며 정상 V3 edge처럼 적용하지 않는다. ACK는 입력 수락이고 셀 적용 증명이 아니다.

## V3 재접속 필요 조건

1. STM이 disconnected 상태여야 재협상한다. 현재 코드는 연결 중 주기적 HELLO/heartbeat/upshift가 없다. host 종료 후에도 STM은 입력 ACK 실패 등 disconnect 감지 계기가 있기 전까지 연결 상태로 남을 수 있다.
2. STM의 HELLO3가 host가 읽을 수 있는 연결로 전달돼야 한다. host는 자신이 V3 협상을 시작하지 않고 받은 HELLO 버전에 답한다.
3. ACK,HELLO,3 완전한 한 줄이 펌웨어의 1200ms HC05_ReadLine 구간에 도착해야 한다. 현재는 최초 읽힌 한 줄을 비교하며 엉뚱한 줄이면 남은 시간과 관계없이 fallback할 수 있다. HAL 오류/overflow/timeout도 동일 fallback 경로다.
4. STM debug V3 EDGES와 host HELLO3/ACK3, 이어지는 MODE sequence ACK를 함께 확인한다. 실제 DOWN A/R까지 관측해야 V3 물리 입력 acceptance가 된다.
5. 이미 V2로 연결되면 단순 대기나 버튼 정상 동작만으로 V3로 승격하지 않는다. host 재open만 해도 STM이 즉시 재협상한다는 보장도 없다.

## 가설 판정 및 최소 후속

- V3 미지원/다른 FRAME grammar 원인: 반증. 현재 source가 양쪽을 지원하고 R2에서 V3가 검증됐다.
- V3 응답 phase를 놓쳐 V2 fallback: 실행 경로 확인. 낮은 계층에서 HELLO3가 사라진 정확한 이유는 insufficient_evidence.
- 초기 FRAME `RAME` 손실: HELLO2 협상 성공 이후 발생했다. 이번 V3→V2 fallback의 원인이 아니며 별도 알려진 수신 전환 문제다.
- V2 성공 후 계속 V2 유지: expected_behavior(호환 경로), 단 H3 V3/H4 acceptance 관점에서는 probable_product_risk.
- 첫 다른 줄/늦은 ACK3로 즉시 fallback 가능: reachable code risk, B에서 그런 줄을 실제 수신했다는 증거 없음. 제품 defect 확정 전 deterministic firmware handshake 시험 필요.

먼저 하드웨어 없는 fake UART/clock 시험으로 (a) reader가 V3 송신 후 열림, (b) 늦은/다른 첫 줄, (c) 정상 ACK3, (d) 진짜 V2 전용 host를 비교한다. 그 뒤 필요한 경우 COM9 pass-through+COM11 기록을 유지하고 **host read 준비 후 STM 재협상**과 자연 재접속을 각각 bounded1회 비교한다. MCU reset을 선택하면 boot CLEAR/PCA 초기화로 실제 셀이 움직일 수 있으므로 실행 전 목적·예상 FRAME·stop 조건을 별도 안내한다. 이번 조사에서는 물리 시험을 실행하지 않았다.

수정 후보는 V3 HELLO의 bounded 재전송과 해당 phase에서 올바른 ACK를 기다리는 좁은 firmware 변경이다. V2 호환을 삭제하거나 무한 timeout/무한 retry로 바꾸지 않는다. 적용 전 FRAME 연속 수신 영향·늦은 ACK phase 혼선·실제 V2 compatibility를 검증해야 한다. 새로운 architecture layer, GPIO/LUT/baud/grammar 변경은 필요하다고 판단할 근거가 없다. 고정 sleep만 추가하는 것은 현재 한 번의 phase 정렬을 바꿀 뿐 재접속 보장 근거가 아니다.

## 이번 검증

기존 host tests 중 V2 ACK, V3 DOWN edge/dedupe, V3 재협상 forced release, silent-open recovery/established idle 유지 4개 PASS. XML `docs/evidence/h3-validation-20260915/v2-v3-host-checks.xml`. pytest cache 쓰기 권한 warning1은 테스트 결과와 분리한다. 이 tests는 실제 Windows COM 가용 시점과 firmware1200ms phase를 함께 모델링하지 않으므로 B fallback을 막지 못한다. 제품 코드 변경0, firmware reset/flash0, live COM open/packet 송신0.
