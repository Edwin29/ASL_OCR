# Integration Baseline Closure Work Packet

## 목적

Piper System Prompt Transport를 시작하기 전에 현재 통합 변경의 책임 경계를 고정하고, 물리 카메라가
없는 환경에서도 확인 가능한 Scanner 시작 실패 처리와 p030 회귀 기준을 녹색으로 닫는다. 정식 Device
Runtime과 과거 실험용 STM 브리지를 문서상 명확히 구분한다.

## 작업 범위

1. Book Scanner 엔진이 `start()` 중 `session_error`를 반환하면 Device Runtime이 이를 성공으로
   오인하지 않고 `FatalPortError`로 Coordinator에 전달한다.
2. 실패한 엔진은 닫히고 active scan으로 보존되지 않는다.
3. `y축` 같은 인접 어휘 수식의 standalone 접근성 억제 이후 p030 human-golden span 수를 현재 정책과
   일치시킨다.
4. `document-parser/hardware/stm_pi_bridge`를 legacy/test-only로 표시하고 정식 실행 경로를
   `device-runtime`으로 안내한다.
5. Device Runtime, Document Parser, Book Scanner 전체 회귀와 compile/diff 검사를 통과시킨다.
6. 기존 승인 작업과 이 closure를 하나의 기준선 커밋으로 고정한다.

## 정식/비정식 경계

- 정식 Device 진입점: `python -m asl_device --config <toml>`
- 정식 STM 어댑터: `device-runtime/src/asl_device/adapters/stm_serial.py`
- 정식 Scanner 조합: `book-scanner/src/book_scanner/video/runtime_composition.py`
- 정식 서버 조합: `document-parser/src/document_parser/server/combined_server.py`
- legacy/test-only: `document-parser/hardware/stm_pi_bridge`, `e0b_bench_server`, desktop/replay acceptance harness
- Raspberry Pi 부하 측정 전용: `RasberryPITest` (Device Runtime이 아님)

## 수용 기준

- 카메라 open 실패를 반환한 Scanner 엔진이 닫히며 Coordinator가 fatal 전이를 할 수 있다.
- 정상 Scanner 시작과 기존 ACK callback 진단 전달은 변하지 않는다.
- p030 self-comparison은 억제된 standalone span을 제외한 30개 공통 span으로 통과한다.
- 세 Python 패키지의 전체 자동 테스트가 녹색이다.
- 물리 카메라, STM, 점자 actuator, 스피커 검증은 요구하지 않는다.

## 제외 범위

- Android UVC/IP camera adapter와 물리 카메라 품질
- Piper 시스템 안내 음성 전송과 재생 우선순위
- Raspberry Pi systemd 및 ALSA/PipeWire 배포
- OCR·점자 규칙의 지원 범위 확장
