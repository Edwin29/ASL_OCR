# Prototype Stabilization Gate

작성일: 2026-09-05 · 감사 기준: `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e`

## 1. 결정

현재 상태는 **프로토타입 기능 구현은 대부분 존재하지만, 무조건적인 HW/SW 통합 진입 승인은 보류**다. 아래 두 코드 계약 교정과 시험 데이터 준비를 한 번의 bounded stabilization pass로 닫은 뒤 단계적 통합에 진입한다. 결함을 더 많이 찾거나 전체 테스트를 모두 녹색으로 만드는 것을 선행 목표로 두지 않는다.

- 확인된 P0: **0건**. 이는 결함 부재 보증이 아니라 이번 감사에서 입증한 범위의 판정이다.
- 통합 전 코드 수정 대상 P1: **S-01 STM 입력 ID의 프로세스 간 충돌**, **S-02 pending artifact가 있는 Scanner의 복구 수명주기 불일치**.
- 통합 전 데이터 조치 P1: **S-03 현재 serving 코드와 맞는 demonstration datapack 확보**. 과거 성공 데이터팩 한 개에서 현재 preflight 오류를 재현했다. 모든 데이터팩이 깨졌다는 뜻은 아니다.
- 거부된 spread의 같은 sequence 재촬영, 일반 OCR 정확도 확대, Pi 배포 운영화 등은 명시적으로 Deferred로 둔다.

이 문서는 기준과 후속 수정 범위를 확정한다. **이번 문서 작성 세션에서는 제품 코드·테스트·펌웨어·시험 원본 데이터를 수정하지 않았다.** 실제 모델 재실행, STM 빌드/flash, 물리 수용시험도 수행하지 않았다. 실행한 기존 테스트의 임시 산출물만 별도 시험 디렉터리에 생성했다.

감사 시작 시 작업 트리는 깨끗했고 `main`은 로컬 `origin/main` 추적 ref보다 5 commits 앞서 있었다. 원격 fetch/push 없이 이 로컬 HEAD를 기준으로 검토했다. 두 호스트의 설치 코드가 이미 같다고 가정하지 않는다.

## 2. Prototype scope와 완료 조건

첫 통합 대상은 **Desktop production OCR/Piper server + Laptop Device Runtime + 고정된 카메라 한 종류 + STM32/HC-05 + 10-cell 점자 actuator + Laptop 음성 출력**이다. Raspberry Pi는 같은 계약을 옮기는 후속 target validation이며 Laptop 통합 시작의 선행 조건이 아니다. 최종 시연 플랫폼이 Pi라면 Pi 단계까지 통과해야 최종 프로토타입 완료로 표시한다.

지원 범위는 미리 선정한 교재·촬영 구도·텍스트/수식/표 fixture 및 시연 페이지다. 일반 텍스트 항목의 점자 clear frame은 현재 정책상 정상일 수 있다. 모든 텍스트의 점역, 모든 교재의 OCR 의미 정확도, 모든 카메라 및 OS 지원을 완료 조건으로 삼지 않는다. 다만 선정한 시연 경로의 핵심 내용을 읽지 못하는 것을 단순 품질 문제로 숨기지 않는다.

[프로젝트 인수인계 §3](../PROJECT_HANDOFF_20260831.md)의 실험 조건도 유지한다. 검은 배경 위 펼친 양면을 고정된 위쪽 카메라로 촬영하며, 마커/calibration을 새 선행 조건으로 추가하지 않는다. 채택된 `seam-conservative + UVDoc bilinear` 경로와 본문 보존을 유지한다. opaque identity는 중복 판정 근거이며 정확한 인쇄 페이지 번호를 인식했다는 증거가 아니다.

프로토타입 완료에는 다음 사용자 결과가 필요하다.

1. 실제 모드 레버와 버튼으로 capture/reading catalog를 선택하고, 새 데이터팩 생성 및 기존 READY 데이터팩 append를 수행한다.
2. 동일 source frame의 좌우 페이지가 한 spread로 접수되고, 저장 안내가 실제 durable receipt 및 게시된 revision과 일치한다. 빈 신규 scan은 성공으로 게시하지 않는다.
3. 저장 후 capture catalog로 돌아간다. 사용자가 reading 모드로 전환해 READY 데이터팩을 선택한다. 저장 직후 자동 reading 진입은 현재 계약이 아니다.
4. 항목·쪽·점자 창 이동, CONFIRM SHORT 재생, CONFIRM LONG 종료가 작동한다. DOWN hold/release는 v3 계약으로 검증한다.
5. 같은 focus/generation의 음성과 점자를 실제로 듣고 확인한다. 점자 창 안의 LEFT/RIGHT 이동은 의도적으로 무음일 수 있다. 채널 오류 containment는 시연 성공의 대체 증거가 아니다.
6. 같은 stable device ID로 읽기를 종료·재진입/앱 재시작해 커서를 복구하고, 새 조작이 과거 명령의 재전송으로 오인되지 않는다.
7. 선정한 일시적 전송 장애에서 같은 artifact를 재전송하고 중복 spread 없이 복구한다. 결정적 reject/최종화 실패에서는 성공을 알리지 않고 원본 및 기존 READY revision을 보존한다. 모든 장애의 자동 복구는 요구하지 않는다.

완료 판정은 [HW/SW Integration Plan](HW_SW_INTEGRATION_PLAN.md)의 단계 6까지 실제 증거로 닫는다. 그 전의 Entry Gate는 물리 통합을 **시작할 자격**이며 최종 제품 수용이 아니다.

## 3. Critical end-to-end path와 boundary inventory

정식 경로: `python -m asl_device` → `local_composition.build_local_device` → `DeviceApplication` / `DeviceFlowCoordinator`, Scanner는 `book_scanner.video.runtime_composition`, 서버는 production `combined_server`의 C0/S0/V4/S1이다.

`document-parser/hardware/stm_pi_bridge`, Scanner의 이전 `session/loop.py`/`transmit/client.py`, bench server와 acceptance harness는 정식 장치 runtime의 대체물이 아니다. `RasberryPITest`는 부하 시험 도구다. `combined_server`의 오래된 module docstring에 남은 `/jobs` → `/sessions` 예시는 현재 Device의 `/api/v1` 경로를 설명하지 않는다.

| ID | Boundary와 입력 → 출력 | 소유권·실패 전파·최소 관측 |
|---|---|---|
| B00 | 설정/모델/host → C0 health, boot handshake, presence → catalog | stable `device_id`는 진행 상태 소유자, `boot_id`는 실행 식별자. endpoint/API key 오류와 카메라 오류를 분리. 공개 health 성공은 인증/Piper 성공을 뜻하지 않음 |
| B01 | STM GPIO/레버 → HC-05 COM → Device input | v3 `HELLO,3`; DOWN A/R, 나머지 navigation SHORT, CONFIRM S/L, 레버 A/R. STM sequence dedupe와 서버 operation ID는 별개. ACK는 입력 수락이며 HTTP 완료/점자 출력 완료가 아님 |
| B02 | mode/catalog/CONFIRM → S0 create/open 또는 reading open | Coordinator가 모드·선택·scan/read 수명주기를 소유. operation key는 재시도에는 같고 새 실행의 새 작업에는 달라야 함. S-01 영향 |
| B03 | live camera/고정 replay → sampled frame → candidate/identity | backend·회전·crop·실효 해상도·frame ID 관측. `candidate_verification`과 `page_change`의 N=5 관측을 혼합하지 않음. local reject는 upload가 아님. startup failure는 FatalPortError로 전달 |
| B04 | 선택한 full spread → seam/crop/UVDoc → atomic `SpreadArtifact` | left/right가 동일 source frame, manifest/hash/side 및 경로 계약 일치. artifact 준비 전 실패에는 서버 ACK 없음. freeze 시 이미 소유권을 넘긴 pending artifact를 버리지 않음 |
| B05 | artifact → ScannerRuntimeAdapter → durable outbox → V4 receipt | scan/sequence/artifact/hash/upload digest lineage 유지. server durable ACK 후 local ACK commit 및 cleanup. 응답 유실 시 같은 key 재전송. `spread_sent`는 이 ACK 후에만 발생. S-02 영향 |
| B06 | V4 received bundle → S1 fragment parser → Page IR → accessible page | 입력 계약 검증 후 비동기 OCR/flattening. V4 ACK는 OCR 성공이 아님. fragment ready/rejected/error 및 parser engine 관측. 거부 페이지를 조용히 생략하지 않음 |
| B07 | CONFIRM LONG → freeze → flush through N → seal → assemble/TTS/preflight → publish | `[1..N]` ACK 후 seal. client sequence/left-right 순서로 append하고 기존 page/item ID 유지. staging 검증 실패 시 기존 current revision 유지. 저장 안내는 READY 게시 후. S-03 영향 |
| B08 | READY revision + device ID → S0 reading session/progress → command/snapshot | S0가 transaction 안에서 cursor와 command receipt 저장. revision 고정, page/node/span/offset/generation 유지. 잘못된 LONG은 wire 거부; CONFIRM LONG은 Device에서 소비 |
| B09 | snapshot audio_ref / system cue → 인증 WAV → RAM cache → playback | 서버 local path를 Laptop에서 열지 않음. ReadingAudioController가 system/document 음성 우선순위와 latest generation을 조율. 다운로드/중단/재생 로그와 실제 청취는 별도 증거 |
| B10 | snapshot braille → asynchronous `FRAME` → STM parse → PCA9685/모터 → 물리 점자 | cursor 5필드 + 10셀, 각 0..63. 최신 FRAME 합치기와 실제 actuator 적용을 구분. 정상 clear frame과 번역/드라이버 실패의 clear를 diagnostics로 구분 |
| B11 | disconnect/restart/scan-stop/reading-exit → 복구 또는 명시적 stop | C0 네트워크 복구, Scanner freeze/resume, durable outbox, stable cursor, serial re-handshake, hold cancel, stale audio/frame을 각각 확인. 데이터 보존과 자동 재개 성공은 별도 |

특히 세 가지 완료 신호는 서로 대체할 수 없다: **STM `ACK,seq` = 조작 입력 수락**, **`spread_sent` = bundle durable 접수**, **`datapack_saved(revision)` = 읽을 revision 게시**. 어느 것도 실제 소리나 점자 돌출의 완료 ACK가 아니다.

## 4. 근거와 수정 이력의 해석

검토 범위는 세 Python 패키지의 production composition/핵심 경계 코드와 관련 tests, STM authoritative firmware, 배치 실행 도구, docs/work-packets, implementation reports, runbooks, 최근 commits 및 로컬 보존 evidence다. 모든 vendored driver·실험 도구를 한 줄씩 검증했다는 의미는 아니다.

증거는 `현재 코드 재현`, `현재 회귀`, `과거 원시 실행 산출물`, `과거 보고서`, `물리 미검증`으로 구분한다. 과거 성공을 최신 HEAD의 무조건적 성공으로 승격하지 않는다.

| 근거 | 발견·수정 이유와 현재 해석 |
|---|---|
| [구조 재점검](../INTEGRATION_ARCHITECTURE_REASSESSMENT_20260830.md), [V0 report](../INTEGRATION_V0_IMPLEMENTATION_REPORT.md), S0/S1/V4 reports 및 work packets | 촬영·저장·읽기 수명주기를 분리하고 durable upload/atomic revision/persistent progress 계약을 추가한 배경. 당시 미구현 목록을 현재 결함 목록으로 복사하지 않음 |
| [E0-B.2 report](../DEVICE_INTEGRATION_E0_B_2_IMPLEMENTATION_REPORT.md) | CPU footer 인식 시간이 collection budget을 넘고 EOF 전달이 누락된 실제 실패. replay budget/EOF 명시화 후 2 spreads/4 fragments/0 duplicates. 과거 physical 1500ms 제한 설명은 이후 8000ms profile보다 오래됨 |
| [E0-B.3.1 report](../DEVICE_INTEGRATION_E0_B_3_1_IMPLEMENTATION_REPORT.md) | console process가 동일 operation key를 재사용해 기존 datapack을 반환한 실제 실패. console은 boot namespace로 수정됨. 현재 STM에는 동일 문제가 남아 S-01로 재현 |
| [E0-B.3 verification](../DEVICE_INTEGRATION_E0_B_3_VERIFICATION_REPORT.md) | candidate와 page-change 역할 혼동 및 ACK callback diagnostic 누락을 수정. 잘못된 4/5·1/5 기대를 맞추기 위해 Scanner threshold를 완화하지 않았음 |
| [baseline closure packet](work-packets/INTEGRATION_BASELINE_CLOSURE_WORK_PACKET.md), `3411bcd` | startup session_error를 성공으로 오인하던 경계를 수정하고 정식/legacy 경로 명시 |
| `9e2fe38`, `15f91bb`, `dfc7b25`, `da5ac87`, `84aa71b` | physical collection 시간, Windows backend, startup preview, OpenCV GUI 의존성, main-thread rendering 교정. 창이 뜨는 것과 live capture→READY의 성공은 다름 |
| `b6ed3e4`, `0af0a39`, `c8fc8ef`, `ea7e6f2` | OCR/발음·수식 지원 변경, STM ACK 비동기화, 점자 예외 containment/serving preflight, DOWN v3 edge/repeat 변경. 과거 생성 데이터 및 v2 물리 증거의 재사용 범위를 재검토해야 함 |
| [DOWN correction packet](work-packets/DEVICE_INPUT_DOWN_HOLD_REPEAT_CONTRACT_CORRECTION_WORK_PACKET.md) | Device 260 passed, Parser 648 passed/4 skipped, Scanner 334 passed/3 golden 실패라는 과거 기록. STM build/hash/physical은 대기. 이번 감사의 집중 테스트 결과와 혼합하지 않음 |

### 직접 확인한 과거 실행 자료

- `tmp/e0b-production-runs/e0b-production-full-model-20260902T144027Z-0760dc80/evidence/`: full-model `automated_status=passed`, server summary `2/4/0`, 하지만 full-model report의 `manual_listening_status=not_run`, `status=manual_pending`.
- `tmp/e0b-production-runs/e0b-production-full-model-20260902T115946Z-f32227d0/evidence/e0b-production-audio-replay-report.json`: `status=passed`, 수동 `content_matched/no_stale_audio/not_fixture_audio/p030_problem_heard=true`, 4 pages, playback 7 starts/6 completions/1 interruption/0 failures. **이 별도 실행에서의 Desktop 청취 증거**는 존재한다. 이를 Laptop·Pi 스피커 또는 STM 수용으로 확대하지 않는다.
- p030 보고서의 11-cell 결과는 20-cell transport viewport에서의 결과이며 10-cell console은 첫 10셀을 보였다. 길이 차이 자체는 결함이 아니다. 물리 시험은 server viewport와 STM 모두 10으로 고정한다.
- 위 원시 자료는 로컬 ignored `tmp/` evidence이므로 다른 checkout에는 없을 수 있다. 후속 실행은 run ID와 hash를 포함한 evidence 묶음을 별도로 보존한다.

### 이번 감사에서 실행한 검증

Windows `.venv-e0b/Scripts/python.exe` (Python 3.11 환경), 현재 세 `src`를 명시적으로 PYTHONPATH에 연결하고 bytecode/cache 출력을 끈 기존 테스트를 실행했다. 신규 테스트 파일은 만들지 않았다.

| 실행 범위 | 이번 결과 |
|---|---:|
| Device `test_stm_serial`, `test_hold_repeat`, `test_application`, `test_coordinator`, `test_book_scanner_runtime`, `test_delivery_v3b` 및 `tests/integration` | 102 passed |
| Scanner `tests/unit/video`, `test_p030_reference`, `test_document_parser_braille_evaluation` | 204 passed |
| Parser `test_server_s0`, `test_server_s1_finalize`, `test_server_v4_upload`, `test_datapack_preflight`, `test_server_wire`, `accessibility/test_speech_controller` | 78 passed |
| Device `test_reading_audio`, `test_reading_audio_adapters` | 20 passed |

합계 404 passed. 처음 Parser/Device tests를 한 pytest 프로세스에 섞은 호출은 `tests.unit` namespace 충돌로 collection error 2개가 났다. 패키지별 별도 실행으로 교정한 위 결과를 채택한다. 제품 assertion failure가 아니며 제품 수정은 하지 않았다. 후속 명령도 패키지별 cwd/명시적 target/별도 ASCII basetemp를 사용한다.

과거 보고서의 p030 golden 실패 3개는 이번 `test_p030_reference.py` 실행에서 재현되지 않았다. 환경별 dependency/import 차이 원인까지 확정하지 않았으므로 기대값을 바꾸거나 제품을 수정할 근거로 사용하지 않는다. 실제 모델·physical test·전체 repository 테스트를 새로 통과했다고 주장하지 않는다.

## 5. P0 / P1 / Deferred 판정 규칙

| 분류 | 판정 기준 | 요구 증거와 조치 |
|---|---|---|
| P0 | 현재 범위의 critical journey를 중단하거나 데이터/상태를 손상시키며 통합 자체를 진행할 수 없음 | 실제 코드 경로/재현/실패 로그/보고서/하드웨어 증거 중 하나 이상. 해당 단계 중단, 데이터 보존, 해결 또는 명시적 범위 변경 전 진입 금지 |
| P1 | 정상 사용·선정한 복구 동작에서 통합 성공 가능성 또는 핵심 신뢰성이 크게 낮아지고, 사전 수정의 이익이 분명함 | trigger→boundary→영향을 구체적으로 연결. 좁은 수정 및 수용시험을 지정하고 pass budget 안에서 해결 |
| Deferred | 핵심 시연을 막지 않는 edge case, 실행 가능한 workaround가 있는 실패, polish/production hardening | workaround·허용 범위·재분류 trigger 기록. 발견만으로 수정 목록에 추가하지 않음 |

단순 code smell, naming/파일 크기, 이론상 경쟁 가능성, 미래 다중 장치 확장성만으로 P0/P1을 만들지 않는다. 미실시 hardware acceptance는 **증거 공백**이며 그 자체로 새 코드 결함은 아니다. 반대로 fake test 성공도 concrete adapter의 실패를 무효화하지 않는다.

새 문제를 발견하면 ID, 재현 조건, 영향받은 B-ID, 근거 경로/commit/run, 데이터 손상 여부, workaround, 분류, 수정 상한을 먼저 적는다. 기존 bounded set에 자동 추가하지 않는다. P0이면 즉시 stop, 새 P1이면 기존 예산 내 범위 교체 또는 별도 다음 단계의 승인 판단을 기록한다. 예산 증가를 암묵적으로 허용하지 않는다.

## 6. 통합 전 bounded issue set

### S-01 · P1 · STM 새 실행의 입력 ID가 과거 서버 receipt와 충돌

근거: [stm_serial.py](../device-runtime/src/asl_device/adapters/stm_serial.py) `_io_loop`는 인스턴스마다 `connection_epoch=0`으로 시작하여 첫 연결의 입력을 `stm-0001-<sequence>`로 만든다. [local_composition.py](../device-runtime/src/asl_device/local_composition.py)는 console에만 C0 `boot_id`를 전달한다. [coordinator.py](../device-runtime/src/asl_device/coordinator.py)는 이를 `:create`, `:scan-open`, `:reading-open` 및 reading command ID로 전달한다. [s0_services.py](../document-parser/src/document_parser/server/s0_services.py)의 `_receipt`는 영속적이고 reading open도 같은 revision의 session을 재사용한다.

현재 코드 재현: 기존 `test_stm_serial.py`의 FakeSerial로 **서로 다른 source 인스턴스**에 `HELLO,3`와 `NAV,C,S,2`를 보냈다. ID 두 개가 모두 `stm-0001-0000000002`였다. 임시 실제 S0Store/ControlPlane에 같은 device ID로 각 ID의 `:create`를 보냈을 때 새 작업 둘이 **같은 datapack ID**를 반환했다. 네트워크나 물리 STM을 흉내 내 성공 판정을 만든 것이 아니라 입력 ID와 실제 영속 receipt의 충돌을 재현한 것이다.

영향: 앱 재시작/STM 재접속을 반복하는 통합 과정에서 새 scan/create가 과거 작업으로 오인되거나 reading command가 과거 snapshot을 돌려줄 수 있다. 단일 fresh happy path는 가능하므로 P0로 올리지 않는다.

수정 범위: STM event ID에 프로세스 namespace를 부여하고 composition에서 C0 boot identity와 연결한다. 한 연결의 동일 sequence 재전송 dedupe, 새 HELLO의 epoch 구분, stable device ID를 유지한다. **서버 receipt 삭제·device ID 매번 교체·서버 idempotency 약화 금지.**

수용: 같은 실행/sequence 재전송은 한 번만 적용; 새 source/boot의 같은 입력 순서는 다른 operation ID; 실제 S0Store를 재사용한 두 번의 create는 다른 datapack; 같은 device/book 읽기 재진입은 커서를 복구하면서 새로운 DOWN을 적용. suffix/hold ID 포함 server ID 길이 제약도 확인한다.

### S-02 · P1 · pending artifact 보존과 Scanner 재개 계약이 불일치

근거: [coordinator.py](../device-runtime/src/asl_device/coordinator.py)의 연결 유실/queue recoverable error는 Scanner를 `freeze()`하고 `_retry_recovery`에서 `scanner.start(self.scan_session)`을 호출한다. [book_scanner_runtime.py](../device-runtime/src/asl_device/adapters/book_scanner_runtime.py)의 `freeze()`는 pending artifact가 있으면 engine을 보존하지만 `start()`는 engine이 있으면 무조건 `FatalPortError("Book Scanner engine is already active")`다. 이 복구의 start 예외는 해당 분기에서 잡지 않는다. recoverable 상태에서는 정상 scanning delivery poll도 진행하지 않는다.

현재 코드 재현: 기존 test의 FakeFactory와 실제 BookScannerRuntimeAdapter에 pending artifact를 두고 `start(scan) → freeze() → start(same scan)`을 호출하여 위 FatalPortError를 확인했다. 실제 카메라/네트워크 시험이 아니라 **concrete adapter 수명주기 재현**이다. `test_freeze_waits_for_pending_terminal_then_closes_engine`는 보존을 검증하지만 Coordinator의 fake Scanner는 실제 start 거부 조건을 구현하지 않는다.

영향: ACK 대기 중 일시적 연결 유실이나 local queue retry에서 사용자가 CONFIRM으로 복구하려고 할 때 앱이 종료될 수 있다. durable artifact 존재가 in-process 복구 성공을 보증하지 않는다.

수정 범위: **동일 scan의 보존된 engine 재개**와 **닫힌 engine의 신규 생성**을 구분하는 최소 계약을 정하고 Coordinator/adapter에 적용한다. 보존된 engine을 무조건 cancel/recreate하여 pending lineage 또는 accepted identity를 지우지 않는다. 다른 scan의 start 거부는 유지한다.

수용: 실제 adapter + 가짜 camera/engine 경계 + 실제 outbox를 조합하여 pending/ACK 전 연결 유실→복구→같은 artifact/key 재전송→ACK→seal을 확인한다. queue 일시 실패도 같은 sequence를 유지해야 한다. pending 없는 freeze, terminal ACK 후 닫힘, 잘못된 scan 재개 거부를 함께 확인한다. ACK 전에 완료 안내/새 artifact 중복/기존 파일 삭제가 없어야 한다.

### S-03 · P1 · 과거 시연 데이터팩을 현재 코드에 그대로 재사용할 수 없음

근거: `20260902T115946Z-f32227d0/work/state/server`의 실제 보존 DB/datapacks를 현재 `preflight_catalog(..., viewport_size=10)`로 읽기 전용 점검했다. `datapack-660f28f931054859b1bccd1c8d48df5e`, revision 1, 4 pages/69 focus items에서 **error 3, warning 21**이었다.

오류는 `AUDIO_UTTERANCE_MISSING`이며 utterance keys는 다음과 같다.

- `pg-cfd29be0af27-00000001-L-vl007-L01`
- `pg-cfd29be0af27-00000001-L-vl007-L01#3`
- `pg-cfd29be0af27-00000002-R-vl004`

21개 warning은 `BRAILLE_TARGET_EMPTY`다. [session.py](../document-parser/src/document_parser/server/session.py)의 `DatapackTtsEngineAdapter.speak`는 exact/normalized lookup 모두 실패하면 KeyError를 발생시킨다. 따라서 이 데이터팩의 과거 청취 성공은 현재 전 항목 serving 성공을 보증하지 않는다. 개별 누락이 어느 과거 commit에서 생겼는지, 현재 운영 catalog 전체에도 같은 오류가 있는지는 이번에 확정하지 않았다.

조치: 현재 코드/모델로 **선정한 fresh demo datapack 한 세트**를 만들고 실제 사용 catalog와 10-cell 전체 preflight를 통과시킨다. 기존 archived revision은 evidence로 보존하고 시연에서 제외한다. 기존 revision을 직접 고치거나 누락 utterance를 비슷한 다른 WAV로 대체하지 않는다. 모든 과거 datapack migration 및 OCR 규칙 추가는 범위 밖이다. fresh 데이터가 통과하면 이 항목은 제품 코드 변경 없이 닫는다.

수용: 사용될 READY revision 목록과 수를 명시하고 각 error 0; warning은 항목별 의미 확인; 선정 페이지의 핵심 발화/수식/표를 직접 확인. `checked_revision_count=0`인 빈 catalog의 녹색은 합격이 아니다.

## 7. Deferred 및 미검증 사항

| ID / 분류 | 근거·영향 | 이번 통합의 workaround / 재분류 조건 |
|---|---|---|
| D-01 / Deferred | Coordinator는 REJECTED sequence 재촬영을 계획하지만 실제 `DurableDeliveryPort.queue`와 SQLite UNIQUE(scan,sequence)는 다른 artifact를 거부. 실제 outbox에 422 reject 후 artifact-2를 같은 sequence로 queue하여 `delivery position already belongs to different content` 재현. fake Coordinator test의 재촬영 성공은 concrete 경로 성공이 아님 | 결정적 reject는 해당 scan 시험을 종료하고 원본/evidence 보존 후 **새 datapack으로 재촬영**. 같은 sequence 복구/receipt 교체/DB 수정 금지. 선정 시연 입력에서 reject가 반복되거나 같은 scan 재촬영이 필수 UX로 정해지면 P1 재분류. replacement protocol/schema redesign은 pass 제외 |
| D-02 / Deferred | S1 parser reject와 V4 ACK는 시점이 다름. ACK 뒤 parser 실패는 finalization을 막으며 자동 partial publish하지 않음 (`s1_services.py`, S1 tests) | 실패 scan을 보존하고 새 데이터팩 사용. 기존 READY는 유지. 실패 페이지를 삭제해 성공 수를 맞추지 않음. 같은 핵심 시연 페이지가 fresh 실행에서도 실패하면 P1 |
| D-03 / Deferred | FLUSHING/FINALIZING에서 C0 loss는 recoverable→catalog로 돌아갈 수 있어 이전 intent의 자동 재개는 완전하지 않음 (`_handle_connectivity_events`, `_retry_recovery`) | scan ID로 서버 상태/receipt 조회 후 operator가 절차를 재개. READY면 읽고, sealing이면 완료 관측, open이면 같은 scan/through N 확인 후 종료 절차. 자동 finalize-intent persistence는 제외. 데이터 유실/중복 게시 재현 시 P0/P1 |
| D-04 / Deferred | v2/legacy에는 DOWN release edge가 없고 다른 방향 버튼은 아직 firmware repeat. HC-05 radio 단절이 OS COM exception으로 즉시 드러나는지는 미확인 | 필수 hold UX는 v3 DOWN만. 나머지는 짧은 조작, 다중 hold/chord 제외. silent radio loss/ACK latency는 물리 단계에서 관측하며 실패가 재현되기 전 새 watchdog 설계를 추가하지 않음. v3 단일 DOWN release 후 지속 이동이면 즉시 해당 단계 stop/P1 이상 |
| D-05 / Deferred | OCR 의미 정확도, generalization, 카메라 보정·page recall 확대, 점역 지원 확대는 과거 p030/full-model reports에도 후속 품질 범위 | 고정 교재/구도/시연 내용 확인 및 local recapture 사용. 시연 핵심 내용 누락·다른 쪽 혼입·필수 수식 오독은 단순 polish로 면제하지 않고 재분류 |
| D-06 / Deferred | 과거 p030 span-count 실패 3개는 이번 204개 Scanner 집중 시험에서 재현되지 않음 | 결과/환경을 남기고 expectation 또는 제품 코드 변경 금지. target interpreter에서 재현되면 현재 의미 정책과 실제 데이터로 재분류 |
| D-07 / Deferred | 최신 v3와 상충하는 runbook의 v2 기본 설명, 오래된 저장 후 자동 reading 설명, `session.py` continuous-reading docstring | 이 문서의 B01/B07/B08 및 최신 firmware README/DOWN packet을 이번 시험의 계약으로 사용. 전체 문서/naming cleanup은 제외 |
| D-08 / Deferred | general exception catch 확대, multi-writer/멀티 디바이스 확장, quota/GC, accepted identity persistence, secret/배포 운영화, 광범위 dependency 정리 | single-host/single-sender, bounded session, 준비된 저장공간과 격리된 시험 state로 진행. 구체적인 critical failure 없이는 구조 변경하지 않음 |
| D-09 / Deferred | Pi runtime/systemd/ALSA/PipeWire/열·전원 acceptance는 아직 Laptop 증거로 대체 불가 | Laptop 통합 후 별도 Pi target 단계. `RasberryPITest` 합격을 제품 runtime 합격으로 쓰지 않음 |

물리 증거 공백: 현재 STM compiler는 PATH에서 찾지 못했고 최신 packet도 build/hash/flash 대기를 명시한다. 최신 v3 firmware + Laptop + HC-05 + PCA/actuator + live camera의 결합 수용 자료를 이번 검토에서 확인하지 못했다. 이는 아래 단계별 증거 수집 대상이며 "하드웨어가 고장났다"는 판정은 아니다.

## 8. Integration Entry Gate: 최소 증거

아래 G0~G4를 만족하면 Laptop 중심 단계적 통합 진입을 허용한다. G5는 STM 전원을 포함한 단계 진입 직전 조건이다. 물리 통합을 시작하려고 먼저 전체 물리 E2E를 요구하는 순환 gate를 만들지 않는다.

| Gate | 최소 증거 | 현재 판정 |
|---|---|---|
| G0 범위·baseline | Desktop/Laptop commit, interpreter/dependency/model hash, profile, viewport=10, stable device ID, state root 및 선정 교재/페이지 고정. 기존 데이터를 보존한 격리 run 준비 | 문서 기준 고정; 실제 두 host의 동일 baseline 확인 대기 |
| G1 bounded issues | S-01/S-02의 concrete regression과 제한된 코드 review 완료, S-03 사용 데이터 조치 | 미충족 |
| G2 automated contracts | 변경 경계 tests + ACK/dedupe/hold, artifact/receipt retry, seal/append/publish failure preservation, cursor idempotency, audio/braille containment 통과. 발견한 모든 테스트 실패를 integration 영향으로 분류 | 현재 404개 집중 회귀 통과, 새 두 결함의 회귀는 후속 pass에서 필요 |
| G3 replay | 고정 MP4 SHA-256 `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`; 최신 Device 경로에서 candidate 역할별 N=5, spread `[1,2]`, Server `2 receipts/4 fragments/0 duplicates`, cutoff=2, READY와 4페이지 읽기. role-aware boundary report는 server summary를 포함해 passed | 과거 성공 존재, pass 이후 한 번 갱신 필요 |
| G4 serving/model 데이터 | 현재 production OCR/Piper로 만든 선정 fresh dataset의 lineage, 실제 사용 catalog의 preflight error 0 및 검사 대상 수>0, 전 항목/표 셀/점자 span viewport/필수 audio mapping. Desktop 인증 WAV의 smoke와 선정 핵심 내용 확인 | archive 1개에서 error 3 확인; fresh 준비 대기 |
| G5 STM 단계별 준비 | authoritative main.c의 CubeIDE build log/firmware hash, 실제 flashed hash 대응, pin/header/전원/10-cell 배선표, v3 협상 관측 장비. 사전 전체 actuator E2E는 요구하지 않음 | 대기; G0~G4 후 software/live-camera 단계는 독립 진행 가능 |

G3의 deterministic parser는 전송·순서·상태기계 증거다. 실제 OCR/Piper 실행을 대신하지 않는다. G4의 preflight는 현재 저장 데이터의 serving 계약 증거이며 OCR 의미 정확도·HTTP transport·실제 청취·돌출을 대신하지 않는다. 같은 fresh full-model run이 G3 lineage도 모두 제공하면 재실행을 중복 요구하지 않는다.

## 9. 한 번의 bounded stabilization pass

**코드 issue budget 2개(S-01/S-02), 데이터 준비 1세트(S-03)**로 고정한다.

- 코드 수정 상한: production Python 파일 6개, production 추가+삭제 실행 코드 합계 400줄 이내. 예상 경계는 `stm_serial.py`, `local_composition.py`, `book_scanner_runtime.py`, `coordinator.py`, 필요 시 `protocols.py`. 새로운 subsystem이나 추상화 계층은 추가하지 않는다.
- test 변경 상한: 관련 test 파일 6개 이내. 단위 fake의 조건만 느슨하게 하지 않고 두 concrete boundary 재현을 검증한다.
- 시간 상한: 구현/분류 12 engineer-hours + 검증/기록 4 engineer-hours, 총 2 작업일 이내의 **한 pass**. 모델 실행/장비 대기 시간은 별도로 기록하지만 코드 예산을 늘리는 이유로 쓰지 않는다.
- 데이터는 fresh demo 세트 1회 생성 및 preflight/내용 확인. 실패하면 원인 분류 후 stop/범위 교체를 결정하며 무제한 재생성하지 않는다.
- STM은 현 소스 build/배포 증거를 수집한다. 빌드/물리 단계에서 새 결함이 나타나면 자동으로 이 pass의 코드 수정에 추가하지 않는다.
- 제외: DB/wire schema migration, 서버 receipt 의미 변경, 대규모 refactor/architecture redesign, naming cleanup, speculative abstraction, 새 OCR/점역 규칙, threshold 완화, Pi 이식, 과거 데이터 일괄 migration.

400줄/6파일 이내라도 구조 재설계를 허용하는 것은 아니다. 반대로 상한 초과 시 잘못된 코드를 억지로 줄여 통과시키지 않는다. 미완료 issue와 원인을 기록하고 통합 범위/다음 작업의 별도 결정을 한다. 두 issue가 닫혔다면 Deferred 정리를 시작하지 않고 검증으로 이동한다.

## 10. Stabilization Exit Gate

다음이 충족되면 pass를 종료하고 Integration Plan 단계 1부터 진행한다.

1. P0 미해결 0; S-01/S-02 재현이 해소되고 concrete adapter/S0Store 경계를 포함한 회귀가 통과한다.
2. S-03을 만족하는 dataset과 catalog preflight가 존재한다. 이전 실패 archive는 지우지 않는다.
3. G0~G4 충족 여부를 baseline/run ID/hash와 연결해 기록한다. old/manual_pending/provisional/skip을 passed로 바꾸지 않는다.
4. 코드·test 변경이 예산 내이며 Deferred가 조용히 섞이지 않았다. 전체 테스트 실행 여부가 아니라 critical contract에 필요한 증거와 남은 비핵심 실패 분류를 검토한다.
5. 실행 담당자는 [Integration Plan](HW_SW_INTEGRATION_PLAN.md)의 단계별 stop/rollback을 사용할 수 있다. G5 및 물리 수용은 아직 대기라고 명시할 수 있다.

예산이 소진됐는데 gate가 미충족이면 "안정화 완료"라고 하지 않는다. 해당 boundary가 필요한 통합 단계만 보류하고 이미 허용된 독립 bench 검증은 진행할 수 있다. 무기한 안정화 연장은 하지 않는다.

## 11. 계획 작성 후 boundary 재대조

2026-09-05 현재 repository에 계획을 다시 대조했다. `local_composition → application/coordinator → Scanner adapter/delivery → http_s0/http_v4 → combined_server/S0/V4/S1 → session/speech → reading_audio/stm_serial → main.c`를 연결했고 B00~B11 각각을 Integration Plan 단계에 배치했다.

재대조에서 특히 다음 누락 가능성을 계획에 반영했다: system prompt와 문서 음성의 공동 재생 경계, 이미 ACK된 뒤의 OCR reject, DB가 가리키는 immutable revision 경로, archive 음성 매핑 drift, pending artifact 복구, mode 레버의 초기 상태, 10-cell viewport, UART FRAME와 실제 PCA/모터 적용의 차이, hold 중 silent radio loss, append 실패 시 기존 revision 보존. 새로운 speculative blocker나 제품 변경을 추가하지 않았다.
