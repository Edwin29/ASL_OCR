# Device Input — DOWN Hold-to-Repeat Contract Correction Work Packet

상태: **소프트웨어 구현 완료 — STM 빌드·실기 수용시험 대기**

기준일: 2026-09-05

성격: **물리 버튼 hold/release 수명주기와 반복 `DOWN SHORT` 생성 계약 교정**

선행 조건:

- STM v2 즉시 입력 ACK 및 비동기 `FRAME` 출력 구현 완료
- Device Runtime reading audio latest-generation 중단/재생 구현 완료
- `CONFIRM SHORT` replay, `CONFIRM LONG` reading/capture 종료 계약 유지

## 1. 목적

사용자가 DOWN 버튼을 짧게 누르면 한 항목 이동하고, 계속 누르고 있으면 빠른 DOWN 이동이 반복되며,
버튼을 떼는 즉시 반복이 멈추는 사용자 계약을 정식 입력 경로 전체에서 보장한다.

여기서 사용자가 부르는 **DOWN LONG**은 별도의 navigation action이 아니다. 물리 버튼이 오래 눌린
상태를 뜻하며, 서버에 전달되는 의미 이벤트는 계속 독립적인 `DOWN SHORT`들의 반복이다.

```text
짧게 누름
  -> DOWN SHORT 1회

계속 누름
  -> DOWN SHORT 즉시 1회
  -> 650 ms 대기
  -> 누르고 있는 동안 180 ms마다 DOWN SHORT 1회

버튼을 뗌
  -> 반복 timer 취소
  -> release 이후 새 DOWN SHORT 생성/dispatch 0회
```

이 작업은 음성 재생 완료에 따라 자동으로 이동하는 연속 읽기를 구현하지 않는다. 따라서 playback
completion ACK는 이 입력 기능의 선행 조건이 아니며, `DOWN LONG = continuous reading toggle` 해석을
제거한다.

## 2. 현재 상태와 결함

현재 STM 소스의 `ButtonPollStep`은 최초 입력 후 650 ms가 지나면 180 ms마다 `NAV,D,S`를 보내고,
release 뒤 생성을 멈춘다. 정식 STM serial adapter도 방향/쪽 이동에서 `SHORT`만 허용한다. 이 부분은
사용자 의미와 대체로 일치한다.

그러나 다음 불일치와 race가 남아 있다.

1. Document Parser `SpeechController`는 `DOWN LONG`을 아직 continuous-reading toggle로 해석한다.
2. `DatapackTtsEngineAdapter`는 실제 재생이 아니라 WAV 조회 직후 completion callback을 실행하므로,
   잘못 들어온 `DOWN LONG` 하나가 문서 끝까지 즉시 이동시킬 수 있다.
3. Device catalog에는 과거의 `LONG = 고정 칸수 burst` 분기가 남아 있다.
4. console 입력은 `down long`처럼 하드웨어가 만들지 않는 조합도 허용한다.
5. STM이 반복 `SHORT`를 모두 wire event로 보내고 Host가 즉시 ACK하여 큐에 넣는 방식은 서버 응답이
   180 ms보다 느릴 때 backlog를 만들 수 있다. 이 backlog는 물리 release 뒤에도 처리될 수 있어
   “떼면 중단”이라는 체감 계약을 위반한다.

마지막 문제 때문에 단순히 현재 펌웨어의 반복 송신만 테스트하는 것으로는 충분하지 않다. press와
release를 Host가 알아야 하며, 처리 지연 동안 놓친 반복 tick을 release 뒤 몰아서 실행해서는 안 된다.

## 3. 고정할 사용자 계약

### 3.1 필수 동작

- debounced DOWN press는 현재 화면에서 유효한 `DOWN SHORT` 한 번을 즉시 실행한다.
- DOWN이 계속 눌린 경우 press 시점부터 650 ms 뒤 repeat를 시작한다.
- 이후 DOWN이 눌린 동안 180 ms마다 최대 한 번의 `DOWN SHORT`를 실행한다.
- DOWN release를 Host가 관측한 뒤에는 새로운 repeat를 만들거나 서버에 보내지 않는다.
- 처리 지연이 있었더라도 누락된 tick을 계산해 catch-up burst로 몰아서 보내지 않는다.
- catalog 끝 또는 문서 끝에서는 기존 clamp/boundary 동작을 유지한다.
- release 자체는 navigation command가 아니며 generation을 올리거나 음성을 중단하지 않는다.
- 마지막으로 도착한 유효 DOWN 결과의 점자와 음성을 정상적으로 표시한다.

### 3.2 허용되는 경계

release가 도착하기 전에 이미 서버로 dispatch되어 commit 중인 navigation 요청은 안전하게 rollback할
수 없다. 따라서 물리 release와 Host 관측 사이에 이미 in-flight였던 요청 **최대 1건**은 완료될 수 있다.

수용 기준은 다음과 같이 명확히 둔다.

- release 관측 뒤 새 navigation dispatch: 0건
- release 시 Host repeat queue에 남은 catch-up event: 0건
- release 전에 이미 dispatch된 in-flight request: 최대 1건
- in-flight 완료 뒤 추가 이동: 0건

이 경계를 더 줄이기 위해 서버 command를 취소하거나 이미 commit된 cursor를 되돌리지는 않는다. cursor
rollback은 중복·순서 오류를 만들 가능성이 더 높다.

## 4. 설계 결정

### 4.1 Host가 반복 시간을 소유한다

엄격한 release 중단을 위해 STM v3에서는 STM이 반복 `SHORT`를 계속 송신하지 않는다. STM은 물리
상태의 경계만 전달하고, Device Runtime의 단일 hold-repeat controller가 monotonic clock으로 반복을
생성한다.

```text
STM button press
  -> NAV,D,A,<sequence>
  -> immediate ACK,<sequence>

Device HoldRepeatController
  -> DOWN SHORT 즉시 한 번
  -> next_due = press_at + 650 ms
  -> held && now >= next_due 이면 DOWN SHORT 한 번
  -> next_due = now + 180 ms

STM button release
  -> NAV,D,R,<sequence>
  -> immediate ACK,<sequence>
  -> held=false, next_due=None
```

`A`는 `ACTIVATED`, `R`은 `RELEASED`다. 이 둘은 Device 입력 수명주기이며 Document Parser/S0
navigation wire로 전달하지 않는다. 서버는 오직 Host가 생성한 `DOWN SHORT`를 받는다.

### 4.2 catch-up 금지

서버 요청이나 렌더링 때문에 event loop가 늦어진 경우 `next_due += 180ms`를 반복하며 과거 tick을
보충하지 않는다. held 상태라면 현재 시각에 한 번만 실행하고 다음 시각을 `now + 180ms`로 다시 잡는다.

```text
잘못된 방식: 900 ms 지연 -> 밀린 SHORT 5개를 연속 실행
정식 방식:   900 ms 지연 -> 아직 held면 SHORT 1개 -> 180 ms 뒤 재평가
```

### 4.3 application 처리 순서

한 application step은 다음 순서를 지킨다.

1. STM/console의 실제 press/release edge를 먼저 drain한다.
2. release를 hold state에 먼저 반영한다.
3. user input에 의해 reading audio를 중단해야 하면 기존 규칙대로 중단한다.
4. 모든 edge 적용 후 hold timer를 평가한다.
5. due repeat가 있고 여전히 held일 때만 synthetic `DOWN SHORT` 하나를 만든다.
6. 서버 응답 후 최신 reading snapshot을 점자, 음성 순으로 present한다.

release edge와 repeat due가 같은 poll에 들어오면 release가 우선이며 repeat는 생성하지 않는다.

## 5. Wire 및 호환성 계약

### 5.1 STM protocol v3

v3 handshake와 directional hold edge를 추가한다.

```text
HELLO,3
ACK,HELLO,3

NAV,D,A,<sequence>   # debounced press
ACK,<sequence>

NAV,D,R,<sequence>   # debounced release
ACK,<sequence>
```

- 각 edge sequence는 1..2^32-1 범위에서 기존 규칙대로 증가한다.
- 같은 sequence 재전송은 ACK를 다시 보내되 edge를 다시 적용하지 않는다.
- reconnect/새 HELLO에서는 held state를 모두 해제한다.
- reconnect 뒤 버튼이 계속 눌려 있더라도 새 debounced `ACTIVATED`를 받기 전에는 repeat하지 않는다.
- DOWN의 `LONG` wire action은 정의하지 않는다.

### 5.2 v2 fallback

Host는 배포 전환 동안 기존 v2 `NAV,D,S,<sequence>`를 계속 수용한다. v2 firmware는 기존처럼
STM에서 반복 SHORT를 만들므로 기본 이동 기능은 유지되지만, release edge가 없어 backlog 이후 중단
상한을 엄격히 증명할 수 없다.

따라서 이 작업 패킷의 physical acceptance는 v3 handshake에서만 합격 처리한다. v2는 호환 모드이지
최종 “release 즉시 중단” 증거가 아니다.

### 5.3 다른 버튼

DOWN을 필수 기준으로 구현한다. 같은 hold-repeat primitive는 UP/LEFT/RIGHT/PAGE_NEXT/PAGE_PREVIOUS에
재사용할 수 있으나 각 control의 실제 UX가 승인된 경우에만 v3 edge 송신을 활성화한다. `CONFIRM`은
계속 release 시점에 `SHORT` 또는 `LONG`을 정확히 한 번 보내며 반복하지 않는다. 레버 계약도 변경하지
않는다.

## 6. 계층별 변경

### 6.1 STM firmware

대상:

- `hardware/stm32/kitel2026final/Core/Src/main.c`
- `hardware/stm32/kitel2026final/README.md`

작업:

- DOWN용 debounced press/release edge를 분리한다.
- v3에서는 `NAV,D,A`와 `NAV,D,R`만 송신한다.
- v2 fallback에서만 기존 `NAV,D,S` repeat를 유지한다.
- confirm과 lever의 기존 의미를 보존한다.
- ACK 대기/재전송이 물리 버튼 poll을 장시간 막지 않도록 기존 bounded v2/v3 송신 상태 머신을 유지한다.

### 6.2 STM serial adapter

대상:

- `device-runtime/src/asl_device/adapters/stm_serial.py`
- `device-runtime/src/asl_device/app_config.py`

작업:

- protocol v3 negotiation을 추가한다.
- DOWN에서 `ACTIVATED/RELEASED`를 허용하고 v3 sequence dedupe를 적용한다.
- edge를 bounded queue에 수락한 즉시 ACK한다.
- duplicate edge는 ACK하되 repeat state를 다시 시작/종료하지 않는다.
- disconnect/close에서 active hold를 강제로 release한다.

### 6.3 HoldRepeatController

권장 신규 대상:

- `device-runtime/src/asl_device/hold_repeat.py`
- `device-runtime/tests/unit/test_hold_repeat.py`

책임:

- monotonic press timestamp와 `next_due` 관리
- 즉시 SHORT 한 번 생성
- 650/180 ms scheduling
- release 취소
- catch-up 금지
- state/session/mode 전환 시 cancel
- synthetic event ID를 activation sequence와 repeat counter에서 결정적으로 생성

초기 설정값:

```toml
[local_io.hold_repeat]
initial_delay_ms = 650
interval_ms = 180
```

값은 구성 가능하게 하되 안전 범위를 둔다. 권장 범위는 initial delay 300..1500 ms, interval
100..1000 ms다. 100 ms보다 빠른 반복은 HTTP/음성 중단 폭주를 만들 수 있으므로 거부한다.

### 6.4 Device application/coordinator

대상:

- `device-runtime/src/asl_device/application.py`
- `device-runtime/src/asl_device/coordinator.py`
- `device-runtime/src/asl_device/adapters/local_controls.py`

작업:

- application이 edge를 먼저 반영하고 이후 due repeat를 평가하도록 한다.
- synthetic repeat는 기존 입력과 동일하게 `Coordinator.handle_input()`을 통과시킨다.
- reading에서는 매 SHORT 전에 이전 음성을 중단하고 latest generation만 재생한다.
- catalog의 `LONG = _BURST_STEPS` 분기를 제거한다.
- mode 전환, selection 이탈, application stop, fatal/recoverable transition에서 hold를 취소한다.
- release만으로 최종 항목 음성을 중단하지 않는다.
- console에 `down press`, `down release`를 제공하고 `down`은 단일 SHORT로 유지한다.
- `down long`은 잘못된 조합으로 거부한다.

### 6.5 Document Parser/S0

대상:

- `document-parser/src/document_parser/accessibility/application/speech_controller.py`
- `document-parser/src/document_parser/accessibility/domain/commands.py`
- `document-parser/src/document_parser/server/wire.py`
- 관련 session/S0 테스트

작업:

- `_continuous_reading`, `_toggle_continuous_reading`, completion 기반 자동 `next_node`를 제거한다.
- 서버 navigation에서는 이동/쪽 버튼의 `LONG`을 거부한다.
- `CONFIRM SHORT` replay는 유지한다.
- `CONFIRM LONG`은 계속 Device Coordinator가 reading/capture 종료로 소비하며 서버 navigation에 보내지
  않는다.
- 반복된 `DOWN SHORT` 각각에 대해 기존 generation/idempotent command 계약을 유지한다.

## 7. 음성·점자 동작

hold repeat의 각 tick은 일반 `DOWN SHORT`와 완전히 동일하다.

```text
synthetic DOWN SHORT
  -> 현재 reading audio interrupt
  -> S0 command 1회
  -> cursor generation 증가
  -> 같은 generation의 braille frame + audio_ref 수신
  -> 점자 present
  -> 최신 audio 재생
```

빠르게 이동하는 동안 중간 음성은 중단될 수 있다. 이것은 사용자가 계속 DOWN을 누르고 있다는 명시적
탐색 의도다. release 뒤에는 마지막으로 선택된 항목의 점자와 음성이 남아야 한다.

playback 완료 여부는 repeat 생성 조건이 아니다. 음성이 길거나 실패하더라도 버튼이 눌린 동안의 이동
속도는 hold timer가 결정한다.

## 8. 오류 및 race 정책

- DOWN `RELEASED`를 받지 못하고 serial 연결이 끊기면 즉시 local release로 처리한다.
- 잘못된 순서의 `RELEASED`는 idempotent no-op이지만 ACK는 정상 반환한다.
- active hold 중 두 번째 DOWN `ACTIVATED`는 duplicate/no-op으로 처리한다.
- 다른 navigation hold가 시작되면 기존 hold를 먼저 취소하여 대각/복수 반복을 만들지 않는다.
- confirm, lever 변경, reading/capture 종료는 active hold를 취소한다.
- 서버 command가 recoverable failure면 밀린 tick을 재생하지 않는다. 여전히 held면 정상 recovery 뒤 현재
  시각을 기준으로 repeat 한 번부터 다시 시작한다.
- 서버 command가 fatal이면 hold를 즉시 취소한다.
- ACK는 STM edge 입력 수락만 뜻한다. 서버 cursor 적용이나 음성 재생 완료를 뜻하지 않는다.

## 9. 테스트 행렬

### 9.1 Firmware/source contract

- DOWN press 30 ms debounce 뒤 `ACTIVATED` 정확히 1회
- DOWN release 30 ms debounce 뒤 `RELEASED` 정확히 1회
- v3에서 held duration과 무관하게 STM발 반복 `SHORT` 0회
- confirm SHORT/LONG과 lever A/R 회귀 없음
- edge sequence 증가 및 ACK 재전송 확인

### 9.2 HoldRepeatController unit

- press 즉시 SHORT 1회
- 649 ms에는 repeat 0회
- 650 ms에는 repeat 1회
- 이후 180 ms 간격
- release 직전 due tick과 release가 같은 poll이면 repeat 0회
- release 뒤 clock을 아무리 진행해도 repeat 0회
- 1초 event-loop 정지 뒤 catch-up 1회 이하
- duplicate activation이 timer를 리셋하거나 즉시 step을 중복 생성하지 않음
- disconnect/mode change/stop에서 cancel
- fake clock으로 wall-clock sleep 없이 결정론적으로 검증

### 9.3 Serial/Application unit

- v3 `NAV,D,A/R,seq` parse와 즉시 ACK
- 같은 sequence 재전송 시 ACK 2회, edge 적용 1회
- release를 repeat timer보다 먼저 처리
- release 이후 server command call 0회
- in-flight command 최대 1회 경계
- rapid repeat 중 이전 음성 interrupt와 최신 snapshot 재생
- release가 마지막 항목 음성을 불필요하게 interrupt하지 않음
- input queue가 full이면 기존 명시적 backpressure/error 정책을 따르고 ACK로 유실을 숨기지 않음

### 9.4 Server unit/integration

- `DOWN LONG` wire 요청은 4xx `INVALID_READING_COMMAND`
- `DOWN SHORT` N개는 서로 다른 command ID로 정확히 N회 또는 문서 끝 clamp까지 적용
- duplicate command ID는 cursor를 두 번 이동시키지 않음
- 서버 session 생성/command 처리에서 completion callback 자동 이동 0회
- `CONFIRM SHORT` replay와 `CONFIRM LONG` Device-side exit 회귀 없음
- 표/수식/빈 점자 항목을 빠르게 통과해도 예외 containment 유지

### 9.5 Physical acceptance

실제 STM, Laptop, Desktop Server를 연결하고 다음을 영상과 JSONL로 함께 기록한다.

1. DOWN을 짧게 5회 눌러 정확히 5개 항목 이동한다.
2. DOWN을 2초 유지해 즉시 1회, 650 ms 뒤부터 약 180 ms 간격의 이동을 관측한다.
3. 임의 항목에서 버튼을 놓고 추가 cursor 이동이 없는지 확인한다.
4. 서버 응답 지연을 500 ms 이상 주입해도 release 뒤 catch-up burst가 없는지 확인한다.
5. hold 도중 serial을 분리했을 때 반복이 즉시 중단되는지 확인한다.
6. release 뒤 마지막 항목의 점자와 음성이 같은 generation인지 확인한다.
7. STM edge ACK, Server command ID, reading generation의 lineage를 대조한다.

## 10. 수용 기준

- DOWN hold가 서버의 `LONG` navigation 또는 continuous-reading toggle을 만들지 않는다.
- DOWN press는 즉시 한 칸 이동한다.
- 650 ms 이전 repeat는 없다.
- 650 ms 이후 held 상태에서만 180 ms 간격으로 `DOWN SHORT`가 생성된다.
- release 관측 뒤 새 repeat 생성과 dispatch가 0이다.
- event-loop 지연 뒤 catch-up burst가 없다.
- release 이전 in-flight request는 최대 1개이며 완료 후 추가 이동이 없다.
- release 뒤 마지막 focus의 점자와 음성이 유지된다.
- 빠른 반복 중 stale audio 및 stale braille frame이 최종 상태를 덮어쓰지 않는다.
- STM immediate ACK, Server idempotency, `CONFIRM SHORT/LONG`, lever 계약이 회귀하지 않는다.
- Device Runtime, Document Parser 전체 unit/integration test가 통과한다.
- 물리 acceptance가 v3 handshake에서 통과한다.

## 11. 제외 범위

- 음성 재생 완료 후 자동 다음 항목 이동
- playback completion ACK
- OCR/점역/TTS 품질 규칙 변경
- Scanner capture threshold 또는 page ACK 변경
- 이미 commit된 server cursor의 rollback
- 여러 navigation 버튼을 동시에 누르는 chord/diagonal 입력

## 12. 완료 산출물

- 구현 코드와 자동 테스트
- STM CubeIDE build 결과와 firmware hash
- protocol v3 negotiation/edge ACK 로그
- hold/release timing JSON report
- 서버 지연 주입 release acceptance report
- 실제 버튼 조작 영상
- 별도 implementation report

## 13. 구현 기록 (2026-09-05)

구현 완료:

- STM protocol v3 `HELLO,3`, DOWN `ACTIVATED/RELEASED` edge와 v2/legacy fallback
- Device Runtime host-owned `HoldRepeatController`와 650/180 ms 설정
- release 우선 전달, disconnect/re-handshake 강제 local release
- console `down`, `down press`, `down release` 계약과 navigation LONG 거부
- catalog LONG burst 및 Document Parser completion 기반 continuous-reading 제거
- S0 reading wire의 LONG action 거부와 `CONFIRM SHORT` replay 유지
- fake-clock timing, v3 ACK/dedupe, application/audio, configuration 및 source-contract 테스트

자동 검증:

- Device Runtime: 260 passed
- Document Parser: 648 passed, 4 skipped
- Book Scanner: 334 passed, 3개의 기존 p030 golden span-count drift 실패

대기 항목:

- 현재 호스트에 `arm-none-eabi-gcc`가 없어 STM CubeIDE build/hash 생성은 미수행
- STM 케이블 확보 후 flash, protocol v3 ACK 로그, 2초 hold/release 및 지연 주입 실기 시험 필요
- 물리 시험 전에는 본 패킷의 최종 하드웨어 수용 상태를 완료로 판정하지 않는다.
