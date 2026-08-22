# STM32 <-> Raspberry Pi 점자 디스플레이 브리지

이 폴더는 이 저장소(`document_parser.server`)와 팀이 만든 STM32 점자 디스플레이 보드를 연결하는 부분입니다.

## 이 폴더에 있는 것

- **`main.c`** — 팀이 전달한 STM32 펌웨어 소스. **로직은 그대로 저장했고**, `BRAILLE_CELL_COUNT` 위치에 주석 하나만 추가했습니다(왜 파이썬 쪽 뷰포트 크기가 반드시 10이어야 하는지 설명). 그 외 동작은 전혀 안 바꿨습니다 — 검토 결과 STM 코드 자체에는 고칠 버그가 없었고, 문제는 전부 파이썬(서버) 쪽 기본값과의 불일치였습니다.
- **`pi_bridge.py`** — **새로 작성한 라즈베리파이용 브리지**. STM32가 쓰는 `FRAME,...`/`NAV,...`/`HELLO` 텍스트 프로토콜과, 이 저장소의 `DatapackSession`(`document_parser.server`) 사이를 통역합니다.
- **`test_pi_bridge.py`** — `pi_bridge.py`의 프로토콜 로직(줄 포맷팅/파싱, HELLO·NAV 처리) 검증. 실제 데이터팩(가짜 OCR/TTS로 만든, 이 프로젝트의 다른 테스트들과 같은 방식)을 놓고 문서 전체를 왕복 이동시키면서, **모든 응답이 정확히 10칸짜리 셀을 담고 있는지**까지 확인합니다.

## 왜 이게 필요했는가 (수정 사항 요약)

1. **셀 개수 불일치 (진짜 문제, 고침)**: STM 보드는 물리적으로 점자 셀이 10개(`BRAILLE_CELL_COUNT`)인데, 서버 쪽 `BraillePresenter`는 기본값이 20칸입니다. 그대로 연결하면 STM의 고정 폭 파서(`ReceiveFrameFromPi`, 정확히 `5 + 10`개 필드만 받음)가 전부 거부합니다.
   - **고친 곳**: `document_parser/server/store.py`의 `SessionStore.get_or_create_session()`이 이제 `braille_presenter` 인자를 받습니다(기존엔 없었음, `DatapackSession`엔 이미 있었는데 `SessionStore`에 안 뚫려 있었음). `pi_bridge.py`가 이걸 `BraillePresenter(viewport_size=10)`으로 명시적으로 넘깁니다.
2. **파이썬 쪽 통역기 부재 (새로 만듦)**: `handle_wire_command()`는 JSON dict를 주고받는데, STM은 완전히 다른 텍스트 줄 프로토콜을 씁니다. 이 둘을 잇는 코드가 없었어서 `pi_bridge.py`를 새로 작성했습니다.
3. **HELLO 처리**: STM이 부팅/재연결 시 보내는 `HELLO`는 버튼 입력이 아니라 "지금 상태 다시 보여줘"라는 뜻입니다. `pi_bridge.py`는 이걸 `session.handle_button()`을 호출하지 않고 `session.state`/`session.braille_frame`을 그대로 재전송하는 것으로 처리합니다(상태 전진 없음).

## 실행 방법 (라즈베리파이에서)

```bash
pip install pyserial   # STM32와의 시리얼 통신용, 이 저장소의 기본 의존성이 아님
sudo rfcomm bind rfcomm0 <HC-05의 블루투스 MAC 주소>   # HC-05를 시리얼 장치로 페어링 (한 번만, OS 설정)

python pi_bridge.py --port /dev/rfcomm0 --datapacks-dir /path/to/datapacks --book-id my_book
```

## 검증 상태 — 솔직하게 말씀드립니다

**검증한 것**: `pi_bridge.py`의 프로토콜 로직(HELLO/NAV 처리, FRAME 줄 포맷팅, 셀 개수 항상 10개 보장)은 실제 데이터팩을 놓고 자동화된 테스트로 확인했습니다(11개 테스트, 전부 통과).

**검증 못 한 것 (이 컴퓨터에 실제 STM 보드/블루투스가 없어서)**:
- `SerialLineTransport`(실제 시리얼/블루투스 통신 코드) 자체는 한 번도 실행해본 적 없습니다.
- STM32 쪽 `main.c`가 실제로 이 브리지가 보내는 `FRAME` 줄을 받아서 서보를 제대로 움직이는지는 확인 못 했습니다 — 이건 실제 하드웨어에서 팀이 직접 테스트해야 하는 부분입니다.

실제 보드로 테스트하실 때 뭔가 안 맞으면, `pi_bridge.py`를 `--port`만 실제 포트로 바꿔서 실행해보시고, Tera Term(USART2)에 뜨는 `BT RX`/`FRAME FORMAT ERROR` 같은 로그를 같이 보여주시면 바로 원인 찾는 데 도움 드릴 수 있습니다.
