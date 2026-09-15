# H3 이후 최소 수정·재검증 우선순위

> 2026-09-15 실행 갱신: 사용자 승인으로1·2·3 최소 수정을 적용했다. 2는 firmware RX 변경 대신 초기 MODE 후 FRAME1회 재전송을 채택했고,4는 재발 시까지 보류한다. 적용·검증·남은 한계는 [실행 결과](MINIMAL_CORRECTIONS_RESULT_20260915.md)를 따른다. 아래는 실행 전 후보 계획을 보존한 것이다.

## 현재 결론

H1의 기존 bounded 촬영/READY 결과와 1B 결과를 보존한다. H2 정상 읽기·수식 창 offset·오디오 및 cursor 복구 증거가 있고, H3 production 직접 실행의 물리 버튼 읽기 정상 관측을 마쳤다. H3의 원시 packet/generation 연쇄 및 종료 코드가 없고 알려진 결함이 남아 있으므로 전체 통합 READY 또는 H4 PASS는 아니다.

현재 Laptop Python 프로세스 없음. 이번 정리는 제품 수정·flash 없이 수행했다. 기존 main.c/main.h/ioc 및 관련 테스트의 adaptation working-tree 변경은 유지한다. 아래 우선순위는 실행 순서이며 기존 P1 severity를 새로 높이는 것이 아니다.

## 1. 연결·재시작 계측 공백 해소 — 진단 패킷

- 근거: R2-T production reopen 후 RX0, raw reopen은 수신 성공. H2 Restart1 사용자 정상 관측과 serial 기록0이 충돌한다. H3 최초 MODE 무반응은 재전환 후 회복했으나 원인 미확정.
- 분류: insufficient_evidence. 셋을 동일 원인으로 합치지 않는다.
- 코드 경계: `device-runtime/src/asl_device/adapters/stm_serial.py`의 `_io_loop`(198), serial factory(222), OSError retry(225), protocol 초기화(247), handshake(277). 현재 open 실패 retry가 상위 읽기 동작과 독립적으로 계속될 수 있어 음성 정상만으로 COM 연결을 증명할 수 없다.
- 먼저 run-only 계측에 open 시작/성공/예외 종류, handle 식별, thread alive, read 진입/복귀, bounded in_waiting, protocol 상태, close 종료를 기록한다. credential 기록 금지. 생산 프로토콜/전송 지연/FRAME 억제는 추가하지 않는다.
- 변경 상한: 진단 파일3개, 제품0개. 하나의 제한된 신규 실험에 앞서 보존 로그 및 wrapper 생명주기를 검토한다. 사용자 버튼 반복 요구보다 fake adapter 재현과 계측 준비 우선.
- 완료 조건: 정상 연결과 reopen을 구분해 첫 실패 경계가 식별되거나, 어느 추가 관측이 필요한지 특정. 정상 H3 관측으로 reopen 실패를 삭제하지 않는다.
- 제품 수정은 원인 확인 뒤 별도 최소 패킷으로 정의. broad pyserial/Windows driver 업그레이드 금지.

## 2. handshake→IRQ 수신 바이트 보존 — 국소 수정 후보

- 근거: 실제 production ACK,HELLO 직후 FRAME의 `FR`이 사라져 STM `AME,...`/UNKNOWN. 직접 시험과 H2 시작 모두 재현.
- 분류: confirmed_product_defect(전송 경계); 정확한 소실 시점은 추가 확인 필요. 기존 P1 유지.
- 코드: `hardware/stm32/kitel2026final/Core/Src/main.c:1064`에서 RX 시작 중 DR을 읽어 버림; 1214 등의 blocking debug 출력 뒤1255에서 IRQ 수신 시작. 이미 손실된 overrun 바이트를 DR 보존만으로 복구할 수는 없다.
- 후보 범위: 성공 handshake 직후 수신 공백 최소화, pending 정상 바이트 전달, 오류 시 기존 line recovery 유지. 새 READY layer나 고정 sleep으로 우회하지 않는다.
- 파일 상한: 제품 main.c1개, 회귀 fixture/테스트2개. 기존 IRQ ring 구조, V3 ACK/dedupe/DOWN A/R, FRAME grammar 유지. LUT/GPIO/threshold 변경 없음.
- targeted regression: ACK newline 직후 첫 FRAME 연속 입력, debug 출력 지연, RXNE와 ORE 조합, 다음 정상 행 복구, V2/legacy 분기, reconnect 초기 FRAME. host의 첫 payload를 지연시키지 않고 확인.
- 실물: 시작/재연결 각각 첫 FRAME 완전 수신과 nonzero→CLEAR 물리 변화 대조. 이미 수납된 상태의 유지로 CLEAR PASS 처리하지 않는다.
- rollback: 현재 검증 ELF 및 source diff 보존 후 이전 ELF로 복귀 가능. Flash 실행 전 목적·packet·stop 조건 공지. 새 protocol migration 없음.

## 3. 논리 셀과 물리 순서 대응 — 국소 수정 후보

- 근거: 논리C1→물리C10, C2→C9 등의 관측 및 사용자 전역 역순 판단, H2/H3에서 동일. 사용자 제안 `11−n`은 대응 표기로 보존.
- 코드: `main.c:564–565`의 `top_motor=i`, `bottom_motor=10+i`.
- 결정할 계약: 독자가 읽는 좌→우 순서에서 논리 첫 셀의 위치. 번호 표기만 바꾸면 실제 문자열의 역순은 해소되지 않는다.
- 후보: 필요 시 논리 i를 물리9−i로 연결하는 단일 mapping 변경. 실측 pulse LUT는 해당 물리 모터에 고정하고 PCA 주소, 좌우 bit 변환, angle 값은 유지한다.
- 파일 상한: 제품 main.c1개, fixture1개. 위 RX 수정과 별도 diff 및 검증 단위로 유지.
- targeted regression: 서로 다른10셀 sentinel의 채널 대응, bit/LUT 불변, 양끝 C1/C10 및 중간 셀의 물리 위치, 전체 CLEAR. 사용자 생략한 전 셀 관측을 이미 PASS였다고 기록하지 않는다.
- rollback: 기존 mapping 복귀. host/server FRAME와 저장 데이터 migration 없음. firmware flash 재검증 필요.

## 4. 무동작 재발 경계 확인 — 하드웨어/런타임 관측 패킷

- 근거: 첫 direct3FRAME은 STM 완전 수신이지만 움직임0. 접촉 점검+재가동 후 같은3FRAME 정상. 두 차례 flash readback은 동일한 검증 image.
- 분류: insufficient_evidence(전원/접촉/런타임 후보). 측정 없이 전원 불량이나 PCA 고장으로 확정하지 않는다.
- 지금 정상 구동을 반복할 필요 없음. 재발 시 전원 상태, STM/PCA 오류와 수신 payload, 실제 구동 관측을 같은 시점에 남긴다. 회로 확인 없는 활선 분리나 servo-only 차단을 지시하지 않는다.
- 제품/각도/LUT 변경0. 필요 측정은 하드웨어팀과 전원 측정 위치를 확인한 뒤 시행. 적용 상태 cache 등은 원인이 입증되지 않은 상태에서 수정하지 않는다.

## 검증 순서 및 생략 범위

1. 패킷1의 계측/독립 재현으로 reconnect 원인과 증거 공백을 좁힌다.
2. 승인된 수정별 targeted 회귀 → firmware build/host subsystem 검사. 서로 다른 결함의 threshold/protocol을 함께 변경하지 않는다.
3. 확정된 source identity로 기존 G3-A 관련 회귀를 수행한다. 변경 영향 밖 H1 content/parser 전체 재조사는 하지 않는다.
4. 물리 첫 FRAME·셀 mapping·재연결을 변경 경계별로 확인한다. 기존 정상 RX/8상태 전체를 무조건 다시 반복하지 않는다. firmware 변경이 RX/PCA에 영향을 주면 해당 최소 회귀는 필요하다.
5. Fresh H2/H3는 긴 탐색 반복 대신 준비된 수식으로 음성+셀, DOWN 해제, catalog CLEAR, 재진입/종료를 짧게 묶고 실제 packet/generation 증거를 보존한다.
6. H4: 고정 Android source, physical capture controls, 두 spread durable receipt, CONFIRM LONG fresh READY, reading 음성/물리셀, cursor 복구를 하나의 fresh 경로에서 검증한다. 기존 H1과 기존READY H3를 합쳐 H4로 대체하지 않는다.
7. Raspberry Pi4 이전은 별도 환경 패킷. AUX/HC05/Linux 설정 변경까지 이번 수정을 확대하지 않는다.

현재 완료된 H3 사용자 정상 관측을 반복하도록 요청하지 않는다. 다음 사용자 관측은 원인을 좁힐 계측 또는 수정 후 물리 acceptance를 위해서만 요청한다. 새 architecture layer가 필요해지면 이 change budget을 넘으므로 별도 design/migration/rollback 검토가 먼저다.
