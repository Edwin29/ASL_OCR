# Hardware Input & Mode Contract Closure Implementation Report

## 결과

작업 패킷의 소프트웨어/소스 범위 1~8을 구현하고 자동 검증했다. 물리 GPIO, STM build/flash,
HC-05, PCA9685 검증은 장비 단계로 남아 있다.

## 하드웨어 인계물 정리

- 입력 ZIP SHA-256:
  `a109ae0a7317b207e91c1b6f8fd960e3d9413074a77e70214b96c1b5b22bc072`
- source-only STM32CubeIDE 프로젝트:
  `hardware/stm32/kitel2026final/`
- 원본 `Debug/`의 ELF/object/list/map은 현재 소스와 혼동하지 않도록 제외했다.
- 원본은 `main.c`에서 PB1을 사용했지만 `.ioc`에 PB1이 없고 PC0만 미사용 입력으로 설정되어
  있었다. 수정본은 `main.c`, `main.h`, `.ioc`에서 여덟 입력을 동일하게 정의한다.

## 닫힌 입력 계약

- 상/하/좌/우/다음/이전: `NAV,U|D|L|R|N|P,S`
- 확인: release 시 `NAV,C,S|L` 한 번
- 모드 레버: LOW/capture=`NAV,V,A`, HIGH/reading=`NAV,V,R`
- handshake: `HELLO`
- 응답: 각 유효한 `HELLO`/`NAV`에 `FRAME,page,node,span,offset,generation,c0..c9`
- `PAGE,NEXT`는 제거했다.
- 이동 반복은 650 ms 후 180 ms마다 SHORT다. 이는 초당 약 5.56 step이며 각 step은 host
  FRAME 왕복을 기다리므로 실제 속도는 느린 쪽으로 제한된다. CONFIRM은 반복하지 않는다.

핀은 PA0 UP, PA1 DOWN, PA4 LEFT, PB0 RIGHT, PB1 NEXT, PC0 PREVIOUS, PC1 CONFIRM, PC2 MODE다.
모두 active-low/pull-up이다. PC0/PC1/PC2의 실제 Morpho 헤더 위치는 제작 전에 보드 schematic과
대조해야 한다.

## Device/Server 동작

- Coordinator는 capture/reading 운용 모드를 별도로 보존한다.
- capture catalog에는 READY/DRAFT와 새 데이터팩 항목이 있고 기존 스캔/추가 촬영 경로를 유지한다.
- reading catalog에는 READY 데이터팩만 있다. READY 선택은 create/open-scan/scanner-start 없이
  reading open으로 간다.
- capture finalize 뒤 reading을 자동으로 열지 않고 capture 데이터팩 선택창으로 돌아간다.
- capture/reading 모드에 새로 진입하면 해당 모드의 데이터팩 선택창을 기본으로 표시한다. 부팅 중
  서버 연결을 기다릴 때 수신한 레버 상태도 보존하여 catalog가 열릴 때 적용한다.
- 데이터팩 선택/capture/reading 화면 전환마다 `screen_changed` 의미 이벤트를 내보내 현재 창을
  음성으로 안내한다.
- durable spread ACK 뒤 기존 high beep와 함께 “페이지 전송이 완료되었습니다. 다음 페이지로 넘겨
  주세요.”를 안내한다. 중복 ACK는 기존 terminal guard 때문에 다시 안내되지 않는다.
- reading의 CONFIRM LONG 또는 capture 레버 입력은 catalog로 돌아가며 재생 중인 음성을 먼저
  중단한다.
- 서버 재시작 후 같은 `(device_id, datapack_id)`를 열었을 때 기존 reading session과 저장 cursor,
  audio lineage가 복원됨을 테스트했다.

## 검증

- Device Runtime 전체: `178 passed`
- Document Parser unit 전체: `591 passed, 4 skipped`
- STM 실제 wire + source/CubeMX contract: `2 passed`
- S0 집중 커서 복원: 전체 Document Parser unit suite에 포함되어 통과
- Python/pytest 임시 경로는 한글 사용자명에 의한 Windows temp 권한 문제를 피하려고 저장소 아래
  ASCII `--basetemp`를 사용했다.

현재 데스크탑에는 `arm-none-eabi-gcc` 또는 STM32CubeIDE headless compiler가 발견되지 않아 firmware
binary는 새로 만들지 않았다. 체크인된 이전 ELF를 재사용하지 않았으며, 실제 build/flash는
`hardware/stm32/kitel2026final/README.md`의 source-only 프로젝트로 수행해야 한다.

화면/페이지 안내는 Coordinator의 정식 의미 이벤트와 한국어 문구까지 검증됐다. 현재
`windows_audio` sink의 문구 재생 구현은 기존 SAPI 기반 진단 어댑터이므로 최종 제품 음성으로
간주하지 않는다. 생산 환경에서는 이 동일한 이벤트를 Piper로 미리 합성한 짧은 시스템 WAV와
Raspberry Pi ALSA/PipeWire 출력에 연결하는 물리 오디오 어댑터 검증이 남아 있다.

## 남은 물리 수용 절차

1. 하드웨어 팀과 PC0/PC1/PC2 Morpho 헤더/전압/배선표를 확정한다.
2. CubeIDE에서 `.ioc`를 열어 재생성 diff가 pin contract를 보존하는지 확인하고 clean build한다.
3. NUCLEO에 flash한 뒤 각 버튼 tap/hold, CONFIRM short/long, 레버 양 상태를 UART log로 확인한다.
4. HC-05 연결에서 모든 명령마다 FRAME이 한 번 반환되고 timeout/disconnect가 없는지 확인한다.
5. PCA9685와 10-cell actuator를 연결해 page/node/offset와 실제 점자 cell 출력이 일치하는지 확인한다.
