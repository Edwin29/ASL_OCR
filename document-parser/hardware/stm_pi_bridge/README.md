# STM32 <-> 호스트(라즈베리파이/PC) 점자 디스플레이 브리지

이 폴더는 이 저장소(`document_parser.server`)와 팀이 만든 STM32 점자 디스플레이 보드를 연결하는 부분입니다.

**"라즈베리파이"라고 부르지만, 실제로는 STM32와 블루투스(HC-05)로 연결될 수 있는 아무 컴퓨터나 됩니다** — 지금 팀 테스트에서는 이미지를 원격 ingest 서버로 보내는 그 팀원 PC가 이 역할을 그대로 겸합니다. 아래 "윈도우 PC에서" 항목이 그 경우입니다.

**중요 — 실제 시연 구조 (별도 저장장치 없음)**: 호스트(이 브리지가 실행되는 컴퓨터)는 데이터팩을 로컬에 저장하지 않습니다. 데이터팩은 GPU 서버에만 있고, 호스트는 버튼 입력이 있을 때마다 **네트워크로 서버에 물어봐서** 응답만 받아 STM에 전달합니다. 아래 "서버 실행"과 "브리지 실행" 두 단계가 다 필요합니다.

## 이 폴더에 있는 것

- **`main.c`** — 팀이 전달한 STM32 펌웨어 소스. **로직은 그대로 저장했고**, `BRAILLE_CELL_COUNT` 위치에 주석 하나만 추가했습니다(왜 서버 쪽 뷰포트 크기가 반드시 10이어야 하는지 설명). 그 외 동작은 전혀 안 바꿨습니다.
- **`pi_bridge.py`** — 호스트에서 실행하는 브리지. STM32가 쓰는 `FRAME,...`/`NAV,...`/`HELLO` 텍스트 프로토콜과, GPU 서버의 `document_parser.server.http_server`(HTTP/JSON) 사이를 통역합니다. **이 파일 자체는 데이터팩도 내비게이션 상태도 전혀 갖고 있지 않습니다** — 매 버튼 입력마다 서버에 실제로 물어봅니다.
- **`test_pi_bridge.py`** — `pi_bridge.py`의 프로토콜 로직(줄 포맷팅/파싱, HELLO·NAV 처리)만 검증합니다(가짜 원격 세션 상대로). 실제 내비게이션/점자 동작 자체의 검증은 `tests/unit/test_server_http.py`(저장소 루트)에서 실제 데이터팩으로 합니다 — 역할이 나뉘어 있습니다.

## 왜 이렇게 두 단계(서버+브리지)로 나뉘어 있는가

1. **셀 개수 불일치**: STM 보드는 물리적으로 점자 셀이 10개(`BRAILLE_CELL_COUNT`)인데, 서버 쪽 `BraillePresenter`는 기본값이 20칸입니다. `pi_bridge.py`가 서버에 세션을 만들 때 `viewport_size=10`을 명시적으로 요청해서 맞춥니다.
2. **로컬 저장 없음**: 처음엔 `pi_bridge.py`가 로컬에 다운로드된 데이터팩 폴더를 직접 읽는 방식이었는데, 실제 시연 환경엔 별도 저장장치가 없어서 이 방식이 안 맞았습니다. 그래서 `document_parser/server/http_server.py`(서버 쪽에 새로 추가)가 데이터팩을 서버 메모리에 들고 있고, `pi_bridge.py`는 매번 HTTP로 물어보는 구조로 바뀌었습니다.
3. **HELLO 처리**: STM이 부팅/재연결 시 보내는 `HELLO`는 버튼 입력이 아니라 "지금 상태 다시 보여줘"라는 뜻입니다. `pi_bridge.py`는 이걸 서버에 `GET /sessions/<id>`로 물어봐서(상태 전진 없음) 그대로 재전송합니다.

## 실행 방법 (두 단계)

### 1단계 — 서버 실행 (GPU 머신, 데이터팩이 있는 곳)

```bash
pip install document-parser[remote-ingest]   # flask, 이미 remote-ingest 서버 써봤다면 이미 있음
python -m document_parser.server.http_server --api-key <아무 문자열> --datapacks-dir datapacks/
```
기본 포트는 8421입니다(이미지 업로드용 `remote_ingest` 서버의 8420과 겹치지 않게). 팀원이 다른 네트워크에 있다면 [docs/remote-ingest.md](../../docs/remote-ingest.md)의 Cloudflare Tunnel 방법을 이 포트에도 똑같이 적용하면 됩니다(터널은 포트별로 따로 열어야 합니다).

### 2단계 — 브리지 실행 (호스트: STM과 블루투스로 연결된 컴퓨터)

**필요 조건**: `pi_bridge.py`는 `remote_ingest_client.py`와 달리 이 저장소(`document_parser`)를 실제로 불러다 씁니다 — 이 저장소가 그 컴퓨터에도 있어야 하고(`git clone` 또는 폴더 복사) `document_parser`가 임포트 가능해야 합니다(`pip install -e document-parser` 또는 `PYTHONPATH`에 `document-parser/src` 추가). `pip install pyserial`(시리얼 통신용)도 필요합니다. (서버와 브리지가 같은 컴퓨터에서 돌아간다면 `--server`는 `http://127.0.0.1:8421`로 두면 됩니다.)

**윈도우에서**:
1. **윈도우 설정 → 블루투스 및 기타 디바이스**에서 STM 보드의 HC-05를 페어링합니다(핀 코드는 보통 `1234` 또는 `0000`).
2. **장치 관리자 → 포트(COM & LPT)**에서 방금 페어링된 장치의 COM 포트 번호를 확인합니다(예: `COM5`, "발신(Outgoing)" 포트).
3. 실행:
```bash
pip install pyserial
python hardware/stm_pi_bridge/pi_bridge.py --port COM5 \
  --server http://127.0.0.1:8421 --api-key <1단계와 동일한 값> --book-id my_book
```

**리눅스(진짜 라즈베리파이 등)에서**:
```bash
pip install pyserial
sudo rfcomm bind rfcomm0 <HC-05의 블루투스 MAC 주소>   # 한 번만, OS 설정
python pi_bridge.py --port /dev/rfcomm0 --server http://<서버 주소>:8421 --api-key ... --book-id my_book
```

## 검증 상태 — 솔직하게 말씀드립니다

**검증한 것**:
- `pi_bridge.py`의 프로토콜 로직(HELLO/NAV 처리, FRAME 줄 포맷팅, 셀 개수 항상 10개 보장) — 가짜 원격 세션으로 자동화 테스트(`test_pi_bridge.py`, 전부 통과).
- `document_parser.server.http_server`의 실제 동작(세션 생성/조회/버튼 처리, `viewport_size` 반영, 인증, 에러 응답) — 실제 데이터팩으로 자동화 테스트(`tests/unit/test_server_http.py`, 전부 통과).
- **실제 서버를 진짜로 띄우고, 진짜 curl로 세션 생성 → 버튼 입력 → 수식 있는 항목까지 이동 → 정확히 10칸 응답 확인 → `format_frame_line()`으로 STM이 기대하는 정확한 `FRAME` 줄이 나오는지까지 전부 실제로 확인했습니다.**

**검증 못 한 것 (이 컴퓨터에 실제 STM 보드/블루투스가 없어서)**:
- `SerialLineTransport`(실제 시리얼/블루투스 통신 코드) 자체는 한 번도 실행해본 적 없습니다.
- STM32 쪽 `main.c`가 실제로 이 브리지가 보내는 `FRAME` 줄을 받아서 서보를 제대로 움직이는지는 확인 못 했습니다 — 이건 실제 하드웨어에서 팀이 직접 테스트해야 하는 부분입니다.

실제 보드로 테스트하실 때 뭔가 안 맞으면, Tera Term(USART2)에 뜨는 `BT RX`/`FRAME FORMAT ERROR` 같은 로그와, `pi_bridge.py`가 콘솔에 찍는 `RX ... ->` 로그를 같이 보여주시면 바로 원인 찾는 데 도움 드릴 수 있습니다.
