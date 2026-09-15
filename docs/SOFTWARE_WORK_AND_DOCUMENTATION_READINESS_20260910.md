# Hardware 대기 기간의 software 작업 및 문서화 판단

작성일: 2026-09-10. 근거는 보존된 구현·실험 기록이다. 오늘 새 hardware/software acceptance를 실행한 결과가 아니다. 사용자는 hardware team이 버튼 입력 불능 및 관련 로직을 수정할 계획이며, 당분간 실제 버튼/디스플레이 시험이 불가능하다고 알렸다. 이 문서는 작업 제안이며 product 수정 승인이 아니다.

## 판단

Software 작업을 멈출 필요가 없다. 상위 software stack/architecture/workflow는 지금 as-built 문서로 작성할 수 있다. H1에서 실제 두 receipt, four parser-ready fragments, fresh READY1, 실제 cue/reading audio와 재시작 커서 복구를 확보했다. 다만 hardware 대체 경계를 제거한 H4와 실물 timing/clear correctness는 미수용이다.

기존 architecture assurance는 수정 전 평가다. 그 문서의 audio architecture_change_required를 현재 미구현 상태로 인용하면 안 된다. 후속 구현에서 native stream single owner와 cancellation ordering을 적용했고, firmware는 이후 normal-rate ORE 재현에 근거한 RX interrupt/ring으로 변경했다. 최종 문서는 이 이력을 분리해야 한다.

근거 문서:

- [초기 assurance](H123_CRITICAL_PATH_ARCHITECTURE_ASSURANCE_20260908.md)
- [구현 결과](H123_IMPLEMENTATION_RESULT_20260908.md), [T-close/host read 후속](H123_FOLLOWUP_TCLOSE_HOST_READ_RESULT_20260908.md)
- [실제 audio 1B 결과](AUDIO_CONSOLE_1B_RUN_20260908.md)
- [firmware/physical 결과](H2_H3_FIRMWARE_SERIAL_PHYSICAL_STATUS_20260908.md)
- [hardware team 인계](CONTROLS_HARDWARE_TEAM_HANDOFF_20260908.md)
- [최신 H1 및 reading/restart 결과](H1_FRESH_ALIGNED_RUN_20260908.md)

## Hardware 없이 가능한 작업 — 우선순위

아래 P0/P1은 마감 작업의 순서이며 기존 defect severity를 재분류하지 않는다.

| 순서 | 작업 / 근거 | 완료 조건 | 필요한 환경 |
|---|---|---|---|
| P0-A | As-built stack/architecture와 HW/SW boundary 계약 문서. 상위 흐름 실증 완료, hardware 로직 변경 예정 | 실제 파일/owner/API/state/오류 경로와 evidence가 연결됨. 미검증과 설계 의도가 명시됨. 하드웨어팀과 반환 packet 의미를 합의할 수 있는 표 완성 | Desktop source와 기존 evidence |
| P0-B | Launcher의 문자 인코딩·종료 코드 관측 분리 진단. Tee stdout JSON2줄 손상, Ctrl+C exit_code=null | 동일 PowerShell/native pipe에서 한글 JSON byte/문자 round-trip 확인; 정상/fatal/Ctrl+C child 결과와 wrapper 결과 별도 기록. 승인 후 tooling만 수정하고 회귀 | Desktop/Laptop, fake child; COM 불필요 |
| P1-A | Page-change 장시간 대기 진단. N5 DIFFERENT 반복 뒤 별도 조작 없이 진전; compact feedback은 visual/coherent 조건을 생략 | 보존 bank/raw token/visual latch/coherent numeric/collector reset/cadence를 하나의 timeline으로 연결. deterministic 재현 또는 insufficient_evidence 범위 명시; 최소 correction 후보 제안 | 저장 evidence, actual-engine replay. 부족하면 Android만 사용한 isolated 계측 |
| P1-B | Camera orientation의 운용 계약. 실제4000×3000→3000×4000으로 바뀜 | frame orientation metadata/책 방향/허용 profile 구분과 사전 확인 절차; fixed scene 복구 절차 문서화. 원인 확인 전 자동회전 정책 수정 금지 | 저장 snapshot, 필요 시 Android; STM 불필요 |
| P1-C | 선정 교재26/27·28/29의 서버 보존 artifact→4 pages→S0 결과 대조 | source frame/side/order/인쇄 페이지 대응, 필수 문제·수식·braille window 확인. 누락/오인식과 기존 waiver 분리. 이번 새 READY에서 실제 양수 offset 시험은 별도 수행 | Desktop 서버 보존 artifact, console. 전 교재 일반화 아님 |
| P1-D | Hardware 변경 수용용 contract replay 준비 | representative V3 short/hold/release/ACK/dedupe/reconnect trace 및 malformed/split/overflow/FRAME ordering fixture, expected result 고정. 이미 있는 tests 재사용; 같은 조건의 반복 테스트 신설 금지 | fake serial, 기존 C/HAL fixture |
| P2 | 최종 후보 software 회귀와 새 READY console/audio 시험 | 변경된 subsystem targeted tests → 인접 integration → final source의 G3-A. 콘솔 제어·기존 actual-audio 증거를 실물 수용으로 승격하지 않음 | Software runtime; 실제 청취는 사용자 필요 |

문서 초안은 P1 root-cause 종결을 기다리지 않고 작성한다. 해결된 내용/실행된 실제 구조/남은 위험을 분리하면 나중에는 해당 절만 갱신하면 된다. Camera/source나 audio를 사용할 수 없더라도 P0-A/P0-B 일부/P1-C/P1-D는 기존 파일과 fake adapter로 진행할 수 있다.

## 문서화할 현재 구조

| 구성 | 현재 책임 / 소스 기준 | 확정도 및 변경 가능 부분 |
|---|---|---|
| Laptop DeviceApplication / Coordinator | `device-runtime/src/asl_device/application.py`, `coordinator.py`; event scheduling, catalog/capture/reading/finalize orchestration, stable device identity | 현재 구조 문서화 가능. Slow synchronous call의 input latency 상한은 미검증 |
| Scanner | `book-scanner/src/book_scanner/video/runtime_composition.py`, `sources.py`, `engine.py`; strict Android acquisition, candidate, N5 identity, selected same-frame L/R preparation, pending/accepted bank | owner/state contract는 문서화 가능. Native OCR cadence, numeric/visual corroboration, orientation 운용은 조건부 |
| Durable delivery / server | delivery outbox와 V4 receipt, S1 fragments, finalize/READY publication, C0/S0 서비스 | fresh H1 경계 실증. API별 요청/응답·idempotency·retry·경로는 해당 source와 계약 문서로 확인하여 작성 |
| Reading / audio | S0 focus/generation/cursor, authenticated audio_ref, `reading_audio.py`, `adapters/reading_audio.py` single native owner | 실제 speaker/재시작 커서 실증. 과거 AV exact dump root 및 이번 close 관측 공백은 분리 |
| Host serial | `adapters/stm_serial.py`, `hold_repeat.py`; V3 handshake, complete record, ACK/dedupe, edge ordering, FRAME serialization | software contract와 tests 문서화 가능. 새 firmware와의 실시간 재검증 필요 |
| Firmware | `hardware/stm32/kitel2026final/Core/Src/main.c`, `stm32f4xx_it.c` 및 headers; RX IRQ/ring, validate-before-commit, PCA apply counters, GPIO events | 현재 구현은 as-built로 기록. 핀/배선/debounce/calibration과 하드웨어팀 후속 수정은 revision별 별도 부록 |

주 workflow: physical control → DeviceApplication/Coordinator → live candidate/page-change → same-frame artifact → durable outbox/V4 → S1 fragments → CONFIRM LONG → fresh READY → S0 cursor/focus → authenticated audio + same-generation FRAME → STM/PCA/cells.

문서의 completion 표는 다음을 별도 칸으로 둔다: STM ACK(input accepted), local outbox durable, V4 receipt/spread_sent, READY revision/datapack_saved, audio playback completion, 사용자 청취, PCA I2C apply success, physically observed cells. 순서나 이름이 비슷해도 서로 대체하지 않는다.

## Hardware 통합 시 변경 규모 추정

아래는 conditional engineering estimate이며 hardware 수정 설계/마감일/가용 인력 미확정 상태에서 일수나 확률을 확정하지 않는다.

| Hardware team의 실제 변경 | 예상 software 영향 | 문서/재검증 영향 |
|---|---|---|
| 접촉·납땜·기구 정렬 복구, 기존 논리/packet 유지 | 상위 Python 변경이 필요 없을 수 있음 | hardware wiring/calibration revision 갱신, 실물 H2/H3/H4 재시험 |
| GPIO mapping/polarity/debounce 수정, 외부 V3 의미 유지 | 주로 firmware 국소 변경. Host/Coordinator 재설계 근거 없음 | pin/action map과 timing 갱신; input3/3, hold/release, RX stress 재검증 |
| Servo zero/LUT/channel mapping 보정, FRAME10-cell 계약 유지 | actuator/firmware 국소 변경 예상. 물리 측정 필수 | 물리 셀·clear·열 대응 전수 확인. 소프트웨어 fake PASS로 대체 불가 |
| SHORT/LONG 판정 위치, press/release 또는 ACK/dedupe 의미 변경 | firmware+Host/hold-repeat에 교차 영향; 중간 이상 규모 가능 | stuck repeat/중복 명령/누락/재접속 위험. 구현 전 양팀 contract review와 golden trace 필요 |
| FRAME grammar/cell encoding, MCU/PCA 구조 또는 피드백 protocol 변경 | adapter/protocol/firmware/tests로 변경 범위 확대; 크기 현재 미확정 | 새 design packet, 호환성/rollback/파일 상한/검증 비용 결정이 선행 |

현재 근거로 전체 software stack 재설계가 필요하다고 볼 수 없다. 실제 receipt→READY→reading이 작동하고 hardware 경계는 adapter에 분리돼 있다. 그러나 무조건 plug-and-play라고도 할 수 없다. Controls와 PCA가 shared MCU scheduling/resource를 사용하므로 GPIO 쪽 변경이 RX 서비스 latency를 악화시키지 않는지 반드시 재시험해야 한다. 이미 수정한 IRQ/ring을 예전 polling 구현으로 덮어쓰는 충돌도 확인 대상이다.

가장 큰 일정 불확실성은 상위 구조 문서 작성이 아니라 physical clear/calibration, firmware 수정의 protocol 영향, 실제 input/output 결합 timing이다. 별도로 H1 liveness가 software 내부 구조 변경으로 이어질 가능성도 아직 배제할 수 없다.

## Hardware team과 고정할 인계 경계

- 실제 GPIO/배선은 변경할 수 있더라도, 외부 control별 의미와 V3 edge/sequence/ACK/dedupe contract는 변경 전 합의 대상으로 둔다. 본 문서는 변경 승인이 아니다.
- CONFIRM SHORT/LONG 및 DOWN ACTIVATED/RELEASED 판정 책임을 명확히 둔다. Firmware와 Host가 같은 hold를 중복 해석하지 않도록 한다.
- FRAME grammar/10-cell encoding과 generation 의미 유지. UART 설정 변경 시 양쪽 config와 검증 기록 동반.
- 변경 source diff, 정확한 base/source hash, build toolchain, ELF/flash hash, actual wiring/calibration 표, rollback source/image를 반환한다. Main.c 단독 교체로 기존 RX/parser/PCA corrections를 잃지 않도록 비교한다.
- Hardware팀 수리 완료는 물리 신호/기구 개선 증거이며 곧바로 production controls/physical cells PASS가 아니다.

## 마감 제출용 문서 구성과 완료 기준

1. System overview 및 stack/deployment: Desktop/Laptop/Android/STM/PCA 역할, 실제 interpreter/import/config identity, dependency/version 근거. Hardware target revision은 별도 표.
2. Critical-path architecture: subsystem owner, normal states, queue/backpressure, ordering, timeout/cancel, error/reconnect/shutdown. 현재 구현과 제안 구분.
3. Interface contract: C0/S0/V4/S1 및 V3/FRAME, examples와 completion 의미, 인증정보를 제외한 설정 계약.
4. Core logic: identity/bank/duplicate/corroboration, durable delivery/finalize, generation supersession, stable cursor, native stream ownership, serial edge ordering, firmware validate/apply.
5. Operator workflow: actual snapshot 비율·방향 확인, 두 receipt 후 finalize, reading/re-entry/restart, 오류별 복구/중단 조건. Console 절차와 physical 절차를 별도로 표시.
6. Verification and limitations: run identity, evidence links, software/native/hardware 각각 PASS/FAIL/PENDING, 기존 content waiver, 하드웨어 변경 시 필요한 requalification.

문서화 완료 기준은 모든 hardware가 PASS인 상태가 아니라, 현재 실제 동작과 미검증 경계가 source/evidence로 추적되고 후속 hardware 변경 위치가 명확한 상태다. 완료되지 않은 physical clear/input 항목을 설계 완료로 꾸미지 않는다. 제출본 source identity는 b6005f1만으로 대체하지 않고 후속 diagnostic/source deployment 상태와 파일 hash를 함께 남긴다. 이후 새 구현이 승인되면 해당 절과 revision만 갱신한다.

## Hardware 복귀 후 필요한 순서

Hardware diff/identity 검토 → compiled parser/serial fixtures → 실제 GPIO/V3·RX normal/stress → PCA/물리 dot/clear → fresh H2(audio+FRAME) → fresh H3(controls 포함) → 최종 source G3-A 및 영향을 받은 H1 → 단일 identity H4. 기존 단계 증거는 보존하되 수정된 boundary의 과거 PASS로 새 firmware를 승인하지 않는다.

이번 작성 작업의 product source 수정0, firmware flash0, live upload0, hardware 동작0. 현재 실행 중인 Laptop process 여부는 이번 문서 판단에서 새로 점검하지 않았다.

## 사용자 확정: hardware 변경 범위와 Raspberry Pi 목표 배포

2026-09-10 사용자 clarification:

- Hardware team 작업은 배선 정렬·GPIO 등의 버그 수정/기능 복구이며, 기존 버튼 의미와 protocol contract를 유지할 계획이다. 따라서 상위 Python 대규모 변경보다 firmware 국소 변경과 실제 재검증이 중심일 것으로 예상한다. 새 source diff 확인 전 변경 범위를 확정된 결과로 취급하지 않는다.
- 원래 배포 계획은 Laptop에서 검증한 뒤 Raspberry Pi 4로 Device Runtime 설정을 이식하는 것이다. 이전 진단의 Raspberry Pi 배포 제외는 당시 단계 범위이며, 이제 목표 배포 계획에는 포함한다. 실제 설치/이식은 아직 시작하지 않았다.
- SSH target: user@100.69.169.17. 현재 전원 꺼짐. 접속 시도하지 않았다. 기존 인증만 사용하며 새 credential을 생성하지 않는다.
- 실제 audio 출력은 Pi 기본 AUX 포트의 유선 이어폰이다. HC-05는 STM에 연결된 상태를 유지하고, Pi가 Bluetooth host로 연결하는 구성을 의도한다. Bluetooth profile/serial device/권한 및 reconnect 동작은 대상 OS에서 확인해야 한다.
- Desktop production OCR/parser/Piper 서버를 Pi로 옮긴다는 요청은 아니다. 우선 Laptop Device Runtime 역할의 이식을 기준으로 하며, 로컬 Scanner의 M1/footer OCR·UVDoc 의존성과 모델 실행도 포함해 호환성/성능을 확인해야 한다.

Pi의 OS/version, 32/64-bit 및 CPU ABI, RAM, Python/native dependency 지원, 오디오 backend/device route, Bluetooth serial 접근 방식은 미확인이다. Laptop venv/binary/config 경로를 그대로 복사하는 방식으로 이식을 완료했다고 선언하지 않는다. 기존 source와 lock/model hash를 기준으로 플랫폼별 설치 가능성을 먼저 확인하고 broad dependency upgrade는 하지 않는다.

Hardware contract 유지 조건에서 MCU 연동 변경 위험은 줄지만, Pi 이식은 별도 위험 축이다. 특히 기존 H1의 N5/8000ms collector와 synchronous native recognition/preparation은 Pi에서 실제 cadence·input/cancel latency를 측정해야 한다. OS 설정만의 작업으로 단정하거나 Pi에서의 liveness를 Laptop PASS로 보장할 수 없다. 8초/N/K 변경이나 OCR offload/새 worker 구조는 이식의 자동 허용 사항이 아니며, 필요성이 드러나면 별도 bounded design packet으로 보고한다.

전원 인가 후 순서: read-only OS/architecture/import/audio/Bluetooth inventory → isolated Pi runtime의 dependency/model 검증 → Desktop API 및 Android snapshot → console Scanner/H1과 AUX actual playback → cursor persistence/restart → hardware 복귀 후 Bluetooth V3/FRAME 및 H2/H3 → 최종 Pi 기반 H4. 서비스 실행 환경과 SSH interactive 환경의 audio/device 접근 차이도 검증한다. 문서는 Windows as-built, Pi deployment plan, Pi verified result를 별도 상태로 유지한다.
