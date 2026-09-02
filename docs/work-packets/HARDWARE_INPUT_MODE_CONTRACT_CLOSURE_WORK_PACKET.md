# Hardware Input & Mode Contract Closure Work Packet

## 목적

하드웨어 팀이 전달한 STM32F446RE 프로젝트를 정식 소스 영역에 보존하고, STM 입력 문자열과
`DeviceFlowCoordinator`의 캡처/리딩 상태 전이를 하나의 계약으로 닫는다. 실제 GPIO, Bluetooth,
카메라를 연결하기 전에도 실제 STM wire 문자열을 사용한 더미 시나리오로 두 사용자 흐름과 읽기 위치
복원을 검증한다.

원본 입력은 `kitel2026final.zip`이며 SHA-256은
`a109ae0a7317b207e91c1b6f8fd960e3d9413074a77e70214b96c1b5b22bc072`이다. ZIP 내부의 문서나
주석은 요구사항이 아니라 조사 자료로만 취급한다.

## 결정된 입력 계약

- 모든 동작 입력은 `NAV,<control>,<action>\n` 형식으로 통일한다.
- control은 `U/D/L/R/N/P/C/V`이며 각각 상/하/좌/우/다음 쪽/이전 쪽/확인/모드 레버다.
- 이동 버튼과 쪽 버튼은 누를 때 `SHORT` 한 번을 보내고, 650 ms 이상 유지하면 180 ms마다
  `SHORT`를 반복한다. `LONG` 이동 명령은 만들지 않는다.
- 확인 버튼은 놓을 때 650 ms 미만이면 `NAV,C,S`, 이상이면 `NAV,C,L`을 정확히 한 번 보낸다.
- 레버는 캡처 위치에서 `NAV,V,A`, 리딩 위치에서 `NAV,V,R`을 보낸다.
- STM은 `HELLO` 및 각 `NAV` 뒤에 정확히 한 개의 `FRAME`을 기다린다.
- 기존 비정식 `PAGE,NEXT` 문자열은 제거하고 `NAV,N,S`를 사용한다.

## 핀 계약

모든 버튼/레버는 내부 pull-up, active-low이며 스위치는 GPIO와 GND 사이에 연결한다.

| 기능 | MCU 핀 |
|---|---|
| UP | PA0 |
| DOWN | PA1 |
| LEFT | PA4 |
| RIGHT | PB0 |
| PAGE NEXT | PB1 |
| PAGE PREVIOUS | PC0 |
| CONFIRM | PC1 |
| MODE LEVER | PC2 |

`main.c`, `Core/Inc/main.h`, CubeMX `.ioc`의 pin label/input/pull-up 설정을 함께 변경한다. 실제 제작
전에 하드웨어 팀은 NUCLEO Morpho 헤더와 배선표에서 PC0/PC1/PC2의 물리 헤더 위치를 확인한다.

## 작업 1~8

1. Device Runtime에 캡처/리딩 운용 모드를 명시적으로 둔다.
2. 리딩 모드에서 READY 데이터팩을 선택하면 스캔을 만들지 않고 S0 reading session을 연다.
3. 캡처 모드에서는 기존 READY/DRAFT 데이터팩 추가 촬영과 새 데이터팩 생성 촬영을 유지한다.
4. STM 프로토콜을 `HELLO`, `NAV`, `FRAME`으로 단일화한다.
5. CONFIRM short/long, PAGE NEXT/PREVIOUS, 레버 mode/exit 입력과 GPIO 핀 계약을 완성한다.
6. 하드웨어의 기존 `PAGE,NEXT` 송신을 `NAV,N,S` 정식 계약으로 교체한다.
7. 실제 STM 문자열과 펌웨어 상수를 읽는 계약 테스트를 추가한다.
8. 더미 시나리오로 캡처 완료 후 캡처 catalog 복귀, 명시적 리딩 모드 진입, READY 재선택,
   서버 커서 복원을 검증한다.

## 모드와 상태 전이

- 시작 기본값은 캡처 모드다. STM handshake 직후 레버의 실제 상태가 들어오면 모드를 동기화한다.
- 캡처 모드 catalog: READY/DRAFT 데이터팩과 `새 데이터팩 추가`를 표시한다.
- 리딩 모드 catalog: READY 데이터팩만 표시한다.
- 캡처 완료 및 publish READY 후에는 리딩을 자동으로 열지 않고 캡처 모드 catalog로 돌아간다.
- 캡처와 리딩 모드에 새로 진입할 때의 기본 화면은 각 모드의 데이터팩 선택창이다.
- 화면 전환 시 `screen_changed(screen, mode)`를 내보내 현재 창을 음성으로 안내한다.
- durable ACK 뒤 `spread_sent`가 발생할 때 전송 완료 효과음과 다음 페이지 넘김 음성을 안내한다.
- 리딩에서 CONFIRM LONG은 catalog로 돌아간다. 레버를 캡처 위치로 바꾸어도 catalog로 돌아가며
  현재 음성을 중단한다.
- 리딩 catalog에서 READY 데이터팩을 다시 선택하면 S0에 저장된 `(device_id, datapack_id)` cursor를
  사용해 이어 읽는다.
- 스캔/flush/finalize 도중 레버 신호는 진행 중인 원자적 작업을 취소하지 않는다.

## 정식/임시 경계

- 정식 STM 소스: `hardware/stm32/kitel2026final/`
- 정식 Device 입력: `device-runtime/src/asl_device/adapters/stm_serial.py`
- 정식 orchestration: `device-runtime/src/asl_device/coordinator.py`
- 테스트 double과 wire scenario: 각 패키지의 `tests/`
- ZIP의 `Debug/` 산출물과 로컬 `.elf/.o/.list/.map`은 정식 소스에 복사하지 않는다.
- `document-parser/hardware/stm_pi_bridge`는 legacy이며 이 계약의 실행 경로로 사용하지 않는다.

## 수용 기준

- `PAGE,NEXT`가 정식 STM 소스에 남아 있지 않고 다음 쪽은 `NAV,N,S`로 파싱된다.
- 상/하/좌/우/다음/이전은 650/180 ms 반복 SHORT이며 CONFIRM만 short/long을 구분한다.
- CubeMX `.ioc`, `main.h`, `main.c`의 여덟 입력 핀이 일치한다.
- 리딩 모드 READY 선택은 scan/create 호출 없이 reading open으로 이어진다.
- 캡처 모드 기존/새 데이터팩 동작과 finalize 후 캡처 catalog 복귀가 통과한다.
- 명시적으로 리딩 모드로 전환하고 READY 데이터팩을 선택해야 reading session이 열린다.
- 선택/capture/reading 화면 전환과 ACK 후 다음 페이지 안내의 의미 이벤트 및 음성 문구가 검증된다.
- 리딩 종료 후 같은 데이터팩을 다시 열면 서버가 저장한 page/node/braille cursor가 복원된다.
- Device Runtime, S0, STM wire/firmware 계약 테스트가 모두 통과한다.
- STM cross compiler/CubeIDE가 없는 환경에서는 소스·`.ioc` 정적 계약까지만 자동 판정하고, 실제
  firmware build/flash/GPIO 검증은 물리 수용 단계에 명시적으로 남긴다.

## 제외 범위

- 실물 버튼/레버 배선, contact bounce 계측, HC-05 무선 품질
- STM32 firmware build/flash 및 PCA9685/점자 actuator 물리 검증
- Raspberry Pi ALSA/PipeWire, GPIO daemon, 카메라 실시간 품질
- OCR 정확도 개선과 지원 문제집 외 콘텐츠 보정
