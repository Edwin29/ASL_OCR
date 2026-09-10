# PASS 0 — Scope & Baseline

상태: COMPLETE. 날짜2026-09-10. 입력: ROADMAP_PROMPT.md 및 현재 entrypoint/composition/metadata inventory. 알고리즘 상세 분석이나 최종 본문은 이 단계에서 작성하지 않는다.

## Project Scope

- 문제: 인쇄 교재 spread를 촬영하여 읽기 순서·수학 표현을 음성/10-cell 점자로 탐색하는 한정 prototype.
- 입력: Android snapshot, mode/button events, catalog 선택, server responses, persistent cursor.
- 출력: same-frame L/R artifacts, durable V4 receipt, S1 fragments, READY revision, S0 snapshot/audio_ref/braille cells, speaker 및 STM/PCA 출력.
- 범위: Device production composition → Scanner → Desktop combined server → reading/audio/STM/firmware. Capture/reading lifecycle 및 실패 포함.
- 대표 scene:26/27·28/29. 전 교재 OCR 일반화, broad refactoring, 새 architecture 구현은 제외.
- 배포: Windows Laptop 검증본 + Desktop production server. Pi4는 Laptop 역할의 목표 배포이며 아직 미검증/전원 꺼짐. AUX 이어폰, Bluetooth→HC-05 계획. Server 전체를 Pi로 옮긴다는 뜻은 아님.

## Baseline

- Workspace D:/Projects/OCR; HEAD b6005f13b0283cc6cac128a5016140613b7ee1ae. 이후 uncommitted docs/diagnostics 존재.
- 현재 source 우선. 파일별 SHA-256과 product diff 목록은 baseline.json. 참조는 path+symbol; 줄 번호는 탐색 보조.
- Desktop source read-only 조사. 이번 server/Laptop/Pi 실행·SSH·실물 시험 없음.
- 최근 fresh H1 직전 Laptop engine은 Desktop hash6ee44d42...dfc380으로 정렬. source237개 비교/26tests 기록은 H1_FRESH_ALIGNED_RUN_20260908.md. 현재 process identity를 새로 확인한 증거는 아님.
- Workspace inventory에서 AGENTS.md 발견하지 못함.

## Entry Points

| ID | 대표 실행 | 역할 / 구현 |
|---|---|---|
| E0 | python -m asl_device --config <device.toml> --initial-mode capture 또는 reading | Device production; __main__.py:main → local_composition.py:build_local_device |
| E1 | tools/windows/e0b-start-production-server.bat → python -m document_parser.server.combined_server | persistent server/real OCR/Piper; combined_server.py:main/create_app |
| E2 | STM reset → main | GPIO/HC-05 RX/parser/PCA; hardware/stm32/kitel2026final/Core/Src/main.c, stm32f4xx_it.c |
| E3 | isolated diagnostic/replay/acceptance scripts | 경계별 시험; production entrypoint와 동일시 금지 |

실제 실행에는 검증된 config/model manifest 사용. CLI 이름만으로 model/adapter identity가 정해지지 않음. 인증값은 문서/분석 대상에서 제외.

## Primary Execution Paths

- P-Capture: physical controls(H1은console) → Device app → catalog/new datapack → scan session → live Scanner → durable upload → finalize → READY.
- P-Reading: READY 선택 → S0 open/resume → navigation snapshots → authenticated audio + FRAME → native/physical 출력.
- P-Recovery: network/backpressure/cancel/restart → preserved receipt/state/cursor → retry/resume. 구체 분기는 PASS1에서 추적.
- P-Deploy: Pi4 적합성 검증은 계획. OS/ABI/native model/serial/audio 실측 없음.

## Major Components

| 책임 | 주요 구현 |
|---|---|
| 단말 모드/조작/session owner | device-runtime/src/asl_device/application.py, coordinator.py, catalog.py |
| 촬영 품질/identity/준비 | book-scanner/src/book_scanner/video, seam, correct |
| durable delivery/idempotency | Device delivery*.py, adapters/http_v4.py; server/v4_*.py |
| presence/catalog/reading | Device connectivity*.py, adapters/http_s0.py; server/c0_presence.py, s0_*.py |
| OCR→구조→accessible output | server/s1_*.py; ocr, serialization, structure, accessibility |
| generation 출력 | Device reading_audio.py, adapters/reading_audio.py, adapters/stm_serial.py |
| physical input/output | STM main.c/IRQ, HC-05, PCA9685×2/20servos |

## External Dependencies

- 세 pyproject.toml: Python>=3.11. 선언 dependency와 실제 설치 lock/model manifest는 구분.
- Scanner: numpy, OpenCV-contrib4.10.0.84, Pillow, requests. Runtime M1 Paddle native model, UVDoc/PyTorch/checkpoint는 PASS1에서 composition 추적. mediapipe는 optional 선언이며 active 여부 보류.
- Server: Flask, PaddleOCR-VL/PP-DocLayout, Piper ONNX/eSpeak, SQLite/filesystem. legacy OCR optional 선언 존재.
- Device: pyserial, sounddevice/PortAudio; authenticated HTTP, camera profile-local TLS exception.
- Firmware: STM32F446 HAL/Cube toolchain, UART/I2C/PCA/servo supply. OS Bluetooth/audio session은 외부 환경.

## Tests / Evidence

- Scanner tests/unit/video: candidate/engine/identity/recovery; 별도 seam/correction/pipeline tests.
- Device tests/unit+integration: coordinator/audio/serial/delivery/composition/hold/fatal.
- Parser tests/unit+integration: OCR conversion/structure/math/reading/S0/S1/V4.
- C fixtures/build/physical traces: docs/evidence/h23-1c-20260908 등. pytest PASS와 실물 acceptance 구분.
- 최신 H1 receipt2/fragment4/READY1/audio/cursor recovery 확인. physical controls/clear 미완료. 초기 assurance는 수정 전이므로 후속 구현/실험과 구분.
- 이번 새 테스트 실행 없음. 과거 result는 당시 source의 증거로만 사용.

## Legacy / Unused Areas

| 영역 | 이번 범위에서의 처리 / 근거 |
|---|---|
| RasberryPITest | 독립 Pi scripts/service. E0/E1이 호출하는 production 경로 아님; Pi 이식 완료로 취급 금지 |
| document-parser/hardware/stm_pi_bridge | 별도 bridge. E0 StmSerialControlSource와 구분. repository 전체 미사용으로 단정하지 않음 |
| server/e0b_bench_server, experimental_reset | bench/experimental entry. production launcher는 combined_server |
| acceptance/replay modules, docs/evidence의 source copy | harness/evidence. actual source 대신 사용 금지 |
| Scanner replay/image_sequence/pc_camera/android_uvc, 다른 page-number 전략 | 대체 config; 현 H1 android_ip_camera/m1_selected_raw_pair와 분리 |
| EasyOCR/기존 pipeline/barrier-review 계열 | active reachability 보류. 이름/README로 legacy 확정하지 않고 PASS1에서 E1→S1 추적 |

## Open Questions

| ID | 질문 | 다음 단계 |
|---|---|---|
| Q1 | V4 durable 수신과 S1 finalize/publish 순서·재시도 owner | PASS1 workers/services/store |
| Q2 | active OCR 출력이 layout/math/reading 순서로 변환되는 경로 | PASS1 reachability, PASS2 알고리즘 |
| Q3 | 실제 identity/visual gate·candidate ranking·UVDoc accept | PASS2 config/engine |
| Q4 | S0 cursor/math-window/audio_ref와 FRAME generation 대응 | PASS1/2 navigation/presenters |
| Q5 | failure result/exception/fallback의 실제 회복·포기 조건 | PASS3 |
| Q6 | Pi 성능/ABI, hardware 수정 뒤 mapping/calibration | 외부 미검증; PASS4 한계로 이월 |
| Q7 | H1 장기 대기/encoding/exit, 과거 AV root | 현재 mechanism과 증거 공백 구분; root 추측 금지 |

Gate: 필수 산출물 완료. PASS1 입력은 본 문서 E0/E1/E2, P-Capture/P-Reading, Q1/Q2/Q4.
