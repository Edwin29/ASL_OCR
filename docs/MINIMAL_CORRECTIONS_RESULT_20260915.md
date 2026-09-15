# 연결·초기 출력·셀 순서 최소 수정 결과

## 결과

사용자 승인에 따라 1→2→3을 시행했다. 제품 변경은 host adapter와 firmware main.c **2개 파일**, 회귀 테스트 변경은1개 파일이다. 기존 다른 working-tree 변경은 보존했다. 4번 무동작/접촉 문제의 추가 실험은 재발 시점까지 보류한다. 새 architecture layer, GPIO/PCA 주소 변경, pulse LUT 수정, camera threshold/timeout 변경은 없다.

| 패킷 | 실행 결과 | 남는 한계 |
|---|---|---|
| 1. 무응답 COM 재연결 | 5초 내 handshake가 없으면 기존 bounded backoff 재연결. 실제 실패 후 세 번째 handle에서 V3/MODE 복구 확인 | Windows/Bluetooth 내부 무수신 원인 자체는 미확정; 이미 handshake한 연결의 모든 무선 고장을 탐지하는 기능은 아님 |
| 2. 초기 FRAME 손실 | versioned HELLO 후 초기 MODE 수신 시 현재 FRAME을 한 번 더 전송.3회 연속 손실 후 재전송 복구 확인 | 원래 첫 바이트 손실을 제거한 것이 아닌 제한된 복구. 수신/APPLIED ACK 신설 없음; MODE 자체가 도착하지 않으면 retry 동작도 성립하지 않음 |
| 3. 셀 역전 | 논리 i→물리9−i. 새 firmware build/flash verify 성공; 양끝 셀 및 CLEAR 사용자 관측 정상 | 모든 물리 셀을 하나씩 다시 관측한 것은 아님. 전 셀 mapping은640패턴 C fixture로 검증 |

## 1번 근거와 수정

Production host에 pass-through serial 계측을 붙였다. 첫 연결의 V3 및 MODE 수신 후 COM close/OSError를1회 주입하고 재개방했다. 두 번째 handle은 열렸지만 read 호출·반환이 계속되고 in_waiting=0, bytes=0이었다. STM reset 뒤 HELLO 송신 로그도 있어 application event queue에서 버린 현상과 구별된다. worker는 살아 있었고 종료 시 정상으로 끝났다.

추가 비교에서 두 번째 handle을 닫고 세 번째로 열자 V3/MODE가 복구됐다. 따라서 `StmSerialControlSource._io_loop`에 open 후 handshake5초 제한을 넣고, 시간 초과를 기존 OSError/backoff 경로로 처리했다. 성공적인 open만으로 backoff를 초기화하지 않고 handshake 후 초기화한다. 정상 handshake 이후 아무 버튼도 누르지 않는 idle 상태는 재접속시키지 않는다.

수정 후보 실제 시험에서는 수동 세 번째 open 없이 자동 세 번째 handle에서 회복했다. 이것은 locally recoverable liveness correction이며 하위 Windows driver의 정확한 root cause를 확정했다는 뜻은 아니다.

증거: `docs/evidence/minimal-corrections-20260915/reconnect-instrumented`, `reconnect-one-extra-open`, `reconnect-candidate`의 events/result.

## 2번 근거와 단순 재전송

기존 반복 실험에 더해 후보 시험3회에서 첫 FRAME `FR` 소실(`AME,...`)이 각각 재현됐다. Firmware는 RX IRQ 시작 후 초기 MODE를 송신한다. Host가 이를 정상 수신/ACK한 뒤 최신 desired FRAME을 한 번 더 보내자3회 모두 완전한 FRAME 및 CELLS dump가 확인됐다.

재전송은 HELLO2/3 handshake당1회만 허용한다. 동일 MODE 재전송/이후 일반 레버 전환마다 반복하지 않는다. 저장해 둔 오래된 첫 payload를 보내지 않고 기존 latest-wins 전송 경로에서 현재 generation을 읽는다. ACK/dedupe, DOWN A/R, 10셀 FRAME 문법은 유지하고 legacy HELLO 동작은 바꾸지 않았다.

사용자 요청의 저비용 복구 대안으로 채택했으며, 원래 우선 후보였던 firmware polling→IRQ 바이트 보존 수정을 이번에 함께 넣지 않았다. 원시 UNKNOWN 로그가 재전송 전에 남을 수 있다. 초기 전송 자체의 무손실 PASS로 표기하지 않는다.

증거: `initial-frame-retry-candidate/events.jsonl`, `result.json`. 각 startup에서 FRAME2개, 처음 손실 후 두 번째 정상 파싱. 모두 CLEAR여서 이 시험만으로 nonzero→CLEAR 물리 변화를 증명하지 않는다.

## 3번 근거와 수정

`ApplyBrailleFrame`에서 `top_motor=9−i`, `bottom_motor=10+top_motor`로 변경했다. 물리 모터 번호에 연결된 실측 pulse LUT180값, PCA주소, 좌우 bit/state LUT, GPIO, parser, RX 및 버튼 함수는 유지했다. 부팅 channel 안내도 논리순서와 일치하도록 갱신했다.

Windows x64 HAL stub fixture:160 motor states,640 cell patterns, GPIO일치, malformed7개 거절, 실패한 channel만 retry, CLEAR/cache 검사 PASS. 실측180값 정확히 일치. STM target build exit0/error0, flash download verification 성공.

첫 물리 시험 준비에서 V2가 관측되어 V3조건을 통과하지 못했고 양끝 패턴은 보내지 않았다. 이것을 모터 실패로 분류하지 않는다. 수신 worker 선행 후 STM reset1회로 V3를 확보한 재시험에서 production host를 통해 CLEAR→C1왼쪽열→CLEAR→C10오른쪽열→CLEAR를5초 간격으로 보냈다. Generation801–805의 완전한 FRAME/상태 dump를 확인했다. 사용자는 맨 왼쪽/맨 오른쪽 위치와 최종 수납 모두 예상대로 작동했다고 확인했다.

이 사실은 startup 시 항상 V3가 자동 확보된다는 증거는 아니다. Board-first 시작에서는 firmware가 이미V2로 내려간 상태일 수 있으며 protocol을 확인하지 않은 DOWN 유지 시험을 V3 acceptance로 확대하지 않는다.

증거: `fixture-result.json`, `target-build-result.json`, `flash-result.json`, `mapping-physical`, `mapping-physical-v3`.

## 적용 identity와 롤백

- Host source SHA256: `2de4388da3912dc2098191ca4ca668db5c761f9ac606606348f0aba1facaf6fe`.
- Firmware main.c SHA256: `9bcb9ddf15342240697f1cff9bdd30ceaa1395f0588eb07e3ec69aa08e4ad6eb`.
- 새 ELF SHA256: `9a3e9941b6823af6104968a1b69bdd63a4d43f3377bcc49d77c009fe9e35bd4a`.
- 보드 ST-LINK: `066EFF505071655067246025`.
- Host는 실제 `C:\ASL_OCR_INTEGRATION\device-runtime\src\asl_device\adapters\stm_serial.py`에 반영했다. 기존 hash를 검증하고 Python이 없는 상태에서 교체했다.
- 이전 host는 Laptop C runtime `minimal-corrections-20260915/stm_serial_before.py`에 보존. 앱 정지 후 해당 파일로 복귀 가능.
- 새 firmware build/source는 Laptop C runtime `minimal-corrections-20260915/source/kitel2026final`에 있다. 기존 integration firmware source directory는 이번에 덮어쓰지 않았으므로 보드 source identity는 이 isolated build와 Desktop main.c를 따른다.
- 이전 ELF는 `hardware-adaptation-20260914/source/kitel2026final/Debug/kitel2026final.elf`, SHA256 `4e415e19ffcdbcc845d2b8f27d6e719812dcbc4ed6e26082c2478e4334d4220e`. 필요 시 해당 ELF로 flash/verify하여 rollback한다. 자동 rollback을 실행하지 않았다.
- FRAME/server 데이터/SQLite migration 없음. stable device ID 변경 없음. credential 변경·출력 없음.

## 검증 범위와 남은 절차

- Host unit + MODE/operation identity integration46 PASS (`host-tests-final.xml`). 초기 실행의 임시 디렉터리 접근 실패2건은 새 ASCII basetemp에서 재실행해 해소; product 실패가 아니었다.
- Firmware C fixture 및 target build PASS. source 기능 fixture 후 추가한 변경은 boot 안내문2줄이며 target build에 포함됐다.
- 실제 reopen recovery, startup retry3회, 최종 firmware 양끝 출력 및 CLEAR 확인. 모든 diagnostic port와 worker 종료.
- 기존 H1/1B/G3-A evidence는 보존한다. 비용/영향 범위상 OCR 전체 G3-A를 다시 실행하지 않았으며 새 firmware 통합 PASS로 그 결과를 옮겨 쓰지 않는다.
- 새 조합으로 production H3에서 수식 한 항목, 짧은 이동/재청취, DOWN 유지·해제(V3 확인), catalog CLEAR/재진입을 짧게 재검증하는 것이 다음 단계다. full H2를 장시간 반복할 필요는 없다.
- 이후 H4의 물리 capture→두 spread receipt→fresh READY→음성/셀을 하나의 fresh 경로에서 검증해야 한다. 현재 H4 또는 전체 integration ready를 선언하지 않는다.
- 4번 전원/접촉 무동작은 사용자 지시에 따라 보류. 재발 시 재개한다.
