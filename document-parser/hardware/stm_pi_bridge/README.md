# STM32 <-> 호스트(라즈베리파이/PC) 점자 디스플레이 브리지

이 폴더는 이 저장소(`document_parser.server`)와 팀이 만든 STM32 점자 디스플레이 보드를 연결하는 부분입니다.

**"라즈베리파이"라고 부르지만, 실제로는 STM32와 블루투스(HC-05)로 연결될 수 있는 아무 컴퓨터나 됩니다** — 지금 팀 테스트에서는 이미지를 원격 ingest 서버로 보내는 그 팀원 PC가 이 역할을 그대로 겸합니다. 아래 "윈도우 PC에서" 항목이 그 경우입니다.

**중요 — 실제 시연 구조 (별도 저장장치 없음)**: 호스트(이 브리지가 실행되는 컴퓨터)는 데이터팩을 로컬에 저장하지 않습니다. 데이터팩은 GPU 서버에만 있고, 호스트는 버튼 입력이 있을 때마다 **네트워크로 서버에 물어봐서** 응답만 받아 STM에 전달합니다. 아래 "서버 실행"과 "브리지 실행" 두 단계가 다 필요합니다.

## 이 폴더에 있는 것

- **`main.c`** — 팀이 전달한 STM32 펌웨어 소스. **로직은 그대로 저장했고**, `BRAILLE_CELL_COUNT` 위치에 주석 하나만 추가했습니다(왜 서버 쪽 뷰포트 크기가 반드시 10이어야 하는지 설명). 그 외 동작은 전혀 안 바꿨습니다.
- **`pi_bridge.py`** — 호스트에서 실행하는 브리지. STM32가 쓰는 `FRAME,...`/`NAV,...`/`HELLO` 텍스트 프로토콜과, 서버의 HTTP/JSON 사이를 통역합니다. **이 파일 자체는 데이터팩도 내비게이션 상태도 전혀 갖고 있지 않습니다** — 매 버튼 입력마다 서버에 실제로 물어봅니다. 서버 응답에는 `state`/`braille_frame`과 함께 `audio`도 같이 들어있는데, 이 브리지는 FRAME 줄을 STM에 보내는 바로 그 순간 **같은 응답의 오디오도 같이 재생을 트리거**합니다(윈도우에서는 `winsound`로) — 점자판에 뜬 것과 지금 재생 중인 소리가 항상 같은 항목을 가리키게 되는 이유입니다. 다만 `audio_ref`는 서버 로컬 파일 경로라서, 브리지가 서버와 다른 컴퓨터에서 돌면 파일을 못 찾아 재생은 안 되고 로그만 남습니다(점자 표시 자체는 영향 없음) — `--no-audio`로 아예 끌 수 있습니다.
- **`test_client.py`** — **테스트 PC에서 실행하는 원스톱 스크립트**: 이미지 업로드(선택) → 완료 대기 → 서버에 저장된 데이터팩 목록 조회 → 선택 → 디스플레이 테스트 모드 진입까지 한 번에 처리합니다. 아래 "실행 방법"이 이 스크립트를 씁니다. `pi_bridge.py`의 부품(`HttpRemoteSession`/`SerialLineTransport`/`run_bridge`/오디오 재생)을 그대로 재사용하고, `--port`가 없으면 실제 보드 없이 콘솔에서 점자를 유니코드로 보여주는 시뮬레이션 모드로 진행합니다. 콘솔 시뮬레이션의 명령어에는 `c`(확인/리플레이)·`cl`(선택 화면으로 — 지금은 콘솔 모드가 이 오케스트레이션을 안 갖고 있어서 로그만 남고 실제 화면 전환은 없음, 아래 `device_flow.py` 참고)도 있습니다.
- **`device_flow.py`** — **데이터팩 선택 화면과 리딩 세션을 하나의 루프로 묶는 오케스트레이터**. 자세한 내용은 아래 "통합 선택+리딩 흐름" 절 참고. `test_client.py`의 `main()`은 아직 이걸 쓰지 않고 기존 콘솔 `input()` 방식 그대로입니다 — `device_flow.py`는 실제 버튼(`SerialLineTransport`)으로 선택 화면까지 조작하고 싶을 때 쓰는 새 진입점입니다.
- **`test_pi_bridge.py`**, **`test_test_client.py`**, **`test_device_flow.py`** — 각각 `pi_bridge.py`/`test_client.py`/`device_flow.py`의 프로토콜·로직을 가짜 원격 세션/전송/오디오 플레이어로 검증합니다. 실제 내비게이션/점자 동작 자체의 검증은 `tests/unit/test_server_http.py`·`tests/unit/test_combined_server.py`(저장소 루트)에서 실제 데이터팩으로 합니다 — 역할이 나뉘어 있습니다.

**전용 페이지 넘김 버튼(다음 쪽/이전 쪽 2개) + 중앙 확인(CONFIRM) 버튼**: 소프트웨어 쪽은 이미 준비돼 있습니다(`PAGE_NEXT`/`PAGE_PREVIOUS`, 현재 페이지에 남은 항목을 건너뛰고 바로 다음/이전 페이지 첫 항목으로 이동; `CONFIRM`, 리딩 중엔 현재 항목 리플레이·선택 화면에선 선택 확정). `NAV,<문자>,<S|L>` 프로토콜에서 `pi_bridge.py`는 지금 `N`/`P`/`C`를 각각에 매핑해뒀는데, 이건 실제 펌웨어가 아직 없어서(또는 배선 전이라서) 정한 **임시 문자**입니다 — 하드웨어팀이 이 버튼들을 배선하고 실제로 어떤 문자를 보낼지 정하면, `pi_bridge.py`의 `_DIRECTION_TO_BUTTON` 딕셔너리 몇 줄만 바꾸면 됩니다(다른 곳은 손댈 필요 없음).

## 통합 선택+리딩 흐름 (`device_flow.py`)

기존에는 데이터팩 선택(어떤 책을 읽을지)이 `test_client.py`의 콘솔 `input()`으로만 가능했고, 고른 뒤의 리딩 모드는 별도 단계였습니다. `device_flow.py`는 이 둘을 실제 버튼 입력만으로 오가는 하나의 루프로 묶습니다:

- **선택 화면**: 시작 시 `GET /datapacks`로 저장된 책 목록(제목/제목 음성 포함)을 가져와 첫 번째 책 제목을 재생합니다. UP/DOWN SHORT로 한 칸, LONG으로 5칸씩(잠정치, `_BURST_STEP_COUNT`) 이동하며, 이동할 때마다 새로 선택된 책 제목을 재생합니다(끝/처음에서는 그 자리에 멈추고 재생 안 함 — clamp). CONFIRM SHORT를 누르면 공용 확인음(`assets/audio/confirm_beep.wav`)을 재생하고 그 책으로 서버에 세션(`POST /sessions`)을 만들어 리딩 화면으로 넘어갑니다. LEFT/RIGHT/PAGE_NEXT 등 이 화면에서 의미 없는 입력은 로그만 남기고 무시합니다.
- **리딩 화면**: 기존 `run_bridge`와 같은 동작(HELLO/NAV 처리, FRAME 전송, 오디오 트리거) — 진입 즉시 현재 항목을 한 번 읽어줍니다. CONFIRM LONG을 누르면 지금 세션을 버리고 선택 화면으로 돌아갑니다(서버 세션 자체는 그대로 남지만 더는 쓰지 않음 — `DatapackSession`은 book_id 없이 존재할 수 없어서, "아직 선택 안 함" 상태는 서버가 아니라 이 오케스트레이터가 클라이언트 쪽에서만 들고 있습니다).

이 왕복은 전송이 완전히 끊길 때까지(`transport.read_line()`이 `None`) 계속됩니다. 상하좌우 버튼의 LONG 프레스가 목적지까지 한 번에 이동하는 "일괄 이동"인 것은 리딩 화면 내부의 노드/점자 스크롤과 동일한 이유입니다 — 펌웨어는 눌렀다 뗄 때 SHORT/LONG 이벤트 하나만 보고하고 "누르고 있는 동안" 신호가 없어서, 진짜 hold-to-repeat 대신 고정 횟수만큼 소프트웨어가 대신 반복합니다.

## 왜 서버가 이렇게 구성돼 있는가

1. **셀 개수 불일치**: STM 보드는 물리적으로 점자 셀이 10개(`BRAILLE_CELL_COUNT`)인데, 서버 쪽 `BraillePresenter`는 기본값이 20칸입니다. `pi_bridge.py`/`test_client.py`가 서버에 세션을 만들 때 `viewport_size=10`을 명시적으로 요청해서 맞춥니다.
2. **로컬 저장 없음**: 처음엔 `pi_bridge.py`가 로컬에 다운로드된 데이터팩 폴더를 직접 읽는 방식이었는데, 실제 시연 환경엔 별도 저장장치가 없어서 이 방식이 안 맞았습니다. 그래서 서버가 데이터팩을 메모리에 들고 있고, 브리지/클라이언트는 매번 HTTP로 물어보는 구조입니다.
3. **HELLO 처리**: STM이 부팅/재연결 시 보내는 `HELLO`는 버튼 입력이 아니라 "지금 상태 다시 보여줘"라는 뜻입니다. `pi_bridge.py`는 이걸 서버에 `GET /sessions/<id>`로 물어봐서(상태 전진 없음) 그대로 재전송합니다.
4. **이미지 업로드 서버와 점자 서빙 서버가 하나로 합쳐짐**: 원래 별도 프로세스(이미지→데이터팩 생성 / 데이터팩→내비게이션)였는데, 그러면 데이터팩을 zip으로 받아서 손으로 다른 서버가 읽는 폴더에 옮겨야 했습니다. `document_parser.server.combined_server`가 이 둘을 한 프로세스, 한 공유 폴더로 합쳐서 — ingest가 끝나는 즉시(다운로드/압축 해제 없이) 바로 선택·서빙 가능해집니다.

## 실행 방법 (한 번에)

### 1단계 — 통합 서버 실행 (GPU 머신)

```bash
pip install document-parser[remote-ingest]   # flask
python -m document_parser.server.combined_server \
  --api-key <아무 문자열> --datapacks-dir datapacks/ \
  --piper-model D:/models/piper-korean/ko_KR-kss-medium.onnx \
  --piper-espeak-data D:/espeak-ng-data
```
기본 포트는 8420입니다(기존 `remote_ingest`와 같은 주소를 그대로 씀). 팀원이 다른 네트워크에 있다면 [docs/remote-ingest.md](../../docs/remote-ingest.md)의 Cloudflare Tunnel 방법을 그대로 적용하면 됩니다.

### 2단계 — 테스트 PC에서 `test_client.py` 실행

**필요 조건**: `remote_ingest_client.py`와 달리 이 저장소(`document_parser`)를 실제로 불러다 씁니다 — 이 저장소가 그 컴퓨터에도 있어야 하고(`git clone` 또는 폴더 복사) `document_parser`가 임포트 가능해야 합니다(`pip install -e document-parser` 또는 `PYTHONPATH`에 `document-parser/src` 추가). 실제 보드로 테스트하려면 `pip install pyserial`도 필요합니다(콘솔 시뮬레이션만 할 거면 필요 없음).

**새 이미지를 보내고 바로 테스트** (실제 STM 보드, 윈도우에서 페어링된 COM 포트 사용):
```bash
python hardware/stm_pi_bridge/test_client.py \
  --server <서버 주소 (LAN IP 또는 터널 주소)> --api-key <1단계와 동일한 값> \
  --port COM5 --upload-book-id my_test p001.png
```
업로드 → 완료 대기 → 저장된 데이터팩 번호 목록 표시(방금 만든 것도 포함) → 번호 입력 → 디스플레이 테스트 모드 진입까지 한 번에 진행됩니다.

**이미 서버에 있는 데이터팩으로 바로 테스트** (업로드 생략):
```bash
python hardware/stm_pi_bridge/test_client.py --server <서버 주소> --api-key <값> --port COM5
```

**보드 없이 소프트웨어만 테스트** (`--port` 생략 → 콘솔에서 유니코드 점자로 시뮬레이션):
```bash
python hardware/stm_pi_bridge/test_client.py --server <서버 주소> --api-key <값>
```

**리눅스(진짜 라즈베리파이 등)에서**: `--port`에 `/dev/rfcomm0`처럼 지정(먼저 `sudo rfcomm bind rfcomm0 <HC-05의 블루투스 MAC 주소>`로 OS 단에서 페어링 필요), 나머지는 동일합니다.

**수동으로 두 단계 서버로 나눠 쓰고 싶다면** (예: 이미지 업로드는 GPU 없는 팀원용으로 따로, 하드웨어 서빙은 별도로): `document_parser.datapack.remote_ingest`와 `document_parser.server.http_server`를 각각 독립적으로 그대로 쓸 수 있습니다(둘 다 안 바뀜) — 이 경우 `pi_bridge.py`를 `--book-id`로 직접 실행하면 됩니다(`test_client.py`의 업로드/목록/선택 단계 없이). [docs/remote-ingest.md](../../docs/remote-ingest.md) 참고.

## 검증 상태 — 솔직하게 말씀드립니다

**검증한 것**:
- `pi_bridge.py`의 프로토콜 로직(HELLO/NAV 처리, FRAME 줄 포맷팅, 셀 개수 항상 10개 보장) — 가짜 원격 세션으로 자동화 테스트(`test_pi_bridge.py`, 전부 통과).
- `document_parser.server.http_server`의 실제 동작(세션 생성/조회/버튼 처리, `viewport_size` 반영, 인증, 에러 응답) — 실제 데이터팩으로 자동화 테스트(`tests/unit/test_server_http.py`, 전부 통과).
- **실제 서버를 진짜로 띄우고, 진짜 curl로 세션 생성 → 버튼 입력 → 수식 있는 항목까지 이동 → 정확히 10칸 응답 확인 → `format_frame_line()`으로 STM이 기대하는 정확한 `FRAME` 줄이 나오는지까지 전부 실제로 확인했습니다.**
- **오디오 재생 트리거**: 같은 응답의 `audio`가 FRAME 줄과 같은 시점에 재생되는지, 무음 스크롤(`audio: null`)일 때 재생이 안 트리거되는지, 플레이어가 없거나 재생이 실패해도 FRAME 줄 전송 자체는 영향 안 받는지 — 가짜 플레이어로 자동화 테스트(`test_pi_bridge.py`의 `AudioTriggerTests`). **`WinsoundAudioPlayer`는 실제로 이 컴퓨터에서 진짜 데이터팩의 실제 wav 파일을 재생시켜 확인**했고(`data/debug/demo_p030/audio/*.wav`), 존재하지 않는 경로를 주면 `winsound.PlaySound`가 (SND_ASYNC 여부와 무관하게) **조용히 아무 일도 안 하고 예외도 안 던진다는 걸 실측**해서, 파일 존재 여부를 직접 확인하고 `FileNotFoundError`를 던지도록 고쳤습니다 — 그래야 이 브리지의 로그에 재생 실패가 실제로 찍힙니다.
- **`device_flow.py`의 선택↔리딩 왕복**: 인덱스 clamp, LONG 일괄 이동, CONFIRM SHORT의 확인음+세션 생성, CONFIRM LONG의 선택 화면 복귀, 전송 종료 시 정상 종료까지 전부 가짜 전송/원격 세션/오디오 플레이어로 자동화 테스트(`test_device_flow.py`, 전부 통과). **실제 STM 보드나 실제 서버로는 아직 안 돌려봤습니다** — 아래 "검증 못 한 것" 참고.

**`combined_server.py`/`test_client.py`도 실제로 끝까지 돌려서 확인했습니다**: 실제 GPU + Cloudflare Tunnel로 진짜 이미지를 업로드 → 실제 OCR 완료 → `/datapacks`에 뜬 목록에서 선택 → 콘솔 시뮬레이션 모드로 실제 내비게이션(상태/점자/오디오 응답 확인) → 서버·클라이언트가 같은 컴퓨터일 때 오디오가 실제로 재생되는 것까지 확인했습니다. 이 과정에서 실제 버그 하나를 잡았습니다: `winsound.PlaySound`가 없는 파일 경로에 조용히 아무 반응 안 하는 문제(위 오디오 재생 트리거 항목의 `FileNotFoundError` 수정으로 이미 해결됨).

**검증 못 한 것 (이 컴퓨터에 실제 STM 보드/블루투스가 없어서)**:
- `SerialLineTransport`(실제 시리얼/블루투스 통신 코드) 자체는 한 번도 실행해본 적 없습니다.
- STM32 쪽 `main.c`가 실제로 이 브리지가 보내는 `FRAME` 줄을 받아서 서보를 제대로 움직이는지는 확인 못 했습니다 — 이건 실제 하드웨어에서 팀이 직접 테스트해야 하는 부분입니다.
- **오디오는 서버와 브리지가 같은 컴퓨터에 있을 때만 실제로 소리가 납니다** — 팀원 PC가 브리지를 돌리고 서버가 다른(GPU) 컴퓨터에 있는 지금 테스트 구성에서는, `audio_ref` 경로를 브리지 쪽에서 찾을 수 없어 재생되지 않고 로그만 남습니다. 이건 버그가 아니라 오디오 바이트 전달 방식 자체가 아직 설계되지 않아서입니다(트리거 타이밍은 지금 구현으로 확정, 바이트 전달은 별도 과제).
- **CONFIRM(5번째) 버튼의 실제 GPIO 배선은 아직 없습니다** — `main.c`는 여전히 UP/DOWN/LEFT/RIGHT 4개뿐이라, `NAV,C,...`는 소프트웨어 프로토콜상으로만 존재하고 실제 보드에서는 아직 보낼 수 없습니다(`PAGE_NEXT`/`PAGE_PREVIOUS`와 같은 상황). `device_flow.py` 자체도 실제 서버/실제 보드로는 아직 안 돌려봤습니다 — 가짜 전송/원격 세션으로만 검증됐습니다.

**별개로 발견한, 이번 작업과 무관한 이슈**: 실제 페이지 하나(발화 72개)를 처음부터 새로 ingest하는 걸 테스트하다가, Piper TTS 합성 도중(40/72개쯤에서) onnxruntime이 `Failed to allocate memory for requested buffer of size 7675687424`(약 7.6GB)로 죽는 걸 봤습니다. `ingest.py`/`combined_server.py` 쪽 로직과는 무관하고 Piper/onnxruntime 자체의 문제로 보이며, 이번 통합 작업 범위 밖이라 손대지 않았습니다 — 발화 수가 많은 페이지를 새로 ingest할 때 재현되면 별도로 다뤄야 합니다.

실제 보드로 테스트하실 때 뭔가 안 맞으면, Tera Term(USART2)에 뜨는 `BT RX`/`FRAME FORMAT ERROR` 같은 로그와, 브리지/클라이언트가 콘솔에 찍는 `RX ... ->` 로그를 같이 보여주시면 바로 원인 찾는 데 도움 드릴 수 있습니다.
