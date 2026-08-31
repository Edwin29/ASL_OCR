# ASL OCR 프로젝트 인수인계 — Scanner · Integration · Server · Connectivity

작성일: 2026-08-31  
인수인계 브랜치: `codex/asl-ocr-integration-c0-handoff`  
분기 기준: `e90156f` (`Validate V2 artifacts on captured MP4`)  
목적: 새 Codex 세션이 Scanner·Integration·Server·Connectivity의 현재 상태뿐 아니라 선행
Document Parser의 목적과 책임, 이 통합 작업이 시작된 이유까지 파악하고, 기존 결정을 되묻거나
완료되지 않은 범위를 완료로 오인하지 않은 채 바로 후속 작업을 시작할 수 있게 한다.

## 1. 프로젝트 전체 맥락과 작업의 시작 이유

ASL OCR의 전체 목표는 종이 수학 교재의 페이지를 구조화하고 점자·음성 데이터팩으로 변환하여,
시각장애 학생이 점자 디스플레이와 스피커가 달린 장치에서 버튼/레버로 탐색하며 읽을 수 있게 하는
것이다. 프로젝트는 무거운 OCR/TTS를 미리 끝내는 사전 점역화와, 저장된 결과만 빠르게 탐색하는
실시간 읽기를 분리한다.

```text
A. 사전 점역화
Book Scanner page image
  -> Document Parser OCR / Page IR
  -> 접근성 변환: 문서 구조, 수학·한글·표 점자, 낭독 규칙
  -> 가능한 발화 전수 열거 + Piper TTS 사전 합성
  -> immutable datapack revision

B. 실시간 읽기
STM button / lever
  -> Coordinator / Server reading state
  -> 저장된 braille frame + 미리 합성된 audio
  -> 점자 디스플레이 / 스피커
```

현재 작업은 **기존 Document Parser 파이프라인 개발을 완료한 뒤, 그 입력에 실제 책 페이지를
안정적으로 공급할 Book Scanner가 필요해져 시작됐다.** Scanner 개발은 고정 카메라 영상에서
snapshot을 선별하고, 좌우 페이지를 분리·crop·UVDoc 보정하여 Document Parser가 받을 수 있는
두 페이지 artifact를 만드는 문제에서 출발했다.

선행 Document Parser 개발에서는 OCR, 구조화, 점역, 낭독/TTS와 데이터팩을 실제로 검증하고
시연하는 것이 우선이었다. 그 과정에서 remote ingest, 임시 HTTP 서버, 데이터팩 생성과 읽기
session이 한 저장소·실행 경로에 함께 놓였고, 서버도 실행할 때마다 주소가 달라질 수 있는 임시
형태로 구축됐다. 이는 파이프라인 타당성을 확인하는 데 유용했지만 최종 제품의 책임 분리나 장치
재시작·네트워크·append·중복 송신 계약을 확정한 구조는 아니었다.

따라서 지금의 Integration/Server/Connectivity 작업은 새 기능을 단순히 덧붙이는 것이 아니라,
시연을 위해 결합됐던 책임을 다음 경계로 정리하는 작업이다.

- Book Scanner: 촬영, 후보 선택, 좌우 crop/보정, 로컬 중복 억제와 송신 artifact 생성
- DeviceFlowCoordinator: 버튼/레버 입력과 Scanner/server/reading lifecycle 조율
- Device Connectivity: 안정 endpoint bootstrap, 인증된 presence, heartbeat와 연결 gate
- Server: 업로드 수신, 영속 catalog/scan/reading 상태, parser 작업 orchestration, append/publish
- Document Parser: 페이지 이미지에서 접근 가능한 문서/점자/낭독 데이터로의 내용 변환
- 온디바이스 출력 adapter: 점자 프레임, audio/TTS feedback, STM/camera 하드웨어 연결

같은 Python process나 `combined_server.py`가 Server와 Document Parser 객체를 함께 구성할 수는
있다. 이는 GPU 모델 재사용과 직렬 실행을 위한 배치 선택이지 책임의 동일화를 뜻하지 않는다.
public upload/idempotency, 장치 presence와 데이터팩 catalog는 Server 책임이고, 이미지 내용 해석과
접근성 변환 규칙은 Document Parser 책임이다.

### 1.1 Document Parser의 현재 책임

Document Parser의 권위 있는 설명은 `document-parser/README.md`다. 현재 기본 content path는
다음과 같다.

```text
accepted page image
  -> PaddleOCR-VL structured OCR
  -> `serialization/vl_page_ir.py` Page IR
  -> 문제/수식/표/그림 구조와 reading order
  -> 한글·수학·표 점자 및 speech rule
  -> navigation/focus 가능한 AccessibleDocument
  -> 발화 목록과 Piper TTS audio
  -> datapack content
```

`document_parser.layout`, `structure`, `reconciliation.py`, `pipeline.py`에는 token OCR 중심의 이전
접근도 남아 있지만 현재 기본 경로로 오인하지 않는다. 현재 기준은 PaddleOCR-VL의 structured
block을 `serialization/vl_page_ir.py`가 직접 Page IR로 만드는 경로다.

Document Parser가 소유하는 것:

- 허용된 페이지 이미지의 OCR과 text/formula/table/image block 구조화
- Page IR/AccessibleDocument schema와 reading order, 문제·항목·focus 구조
- 한국어·수학·표 점역과 점자 viewport 표현
- 낭독 문장 분류·생성 규칙, navigation state machine에 필요한 content semantics
- 발화 전수 열거, Piper TTS 합성과 datapack content/schema/loader
- 동일 입력에 대한 parser 품질·회귀 검증과 실패의 명시적 보고

Document Parser가 소유하지 않는 것:

- 카메라 제어, snapshot cadence, 손/이동/흐림 판정
- 좌우 페이지 검출, seam crop, UVDoc와 전송 후보 선택
- 같은 페이지 재송신 방지용 Scanner identity bank
- 장치의 서버 발견/presence/heartbeat
- public upload body, network retry, durable outbox와 upload ACK
- STM serial, 비프/TTS 조정 안내와 실제 점자 디스플레이 I/O

Server S1은 Document Parser adapter를 호출해 각 page fragment를 얻고 revision을 조립한다. 즉
Document Parser가 페이지 내용을 변환하고, Server가 작업 순서·영속성·idempotency·publish를
소유한다. 과거 `remote_ingest.py`와 임시 server가 두 역할을 한 실행 경로에 담았다는 사실을 미래
API의 책임 근거로 사용하지 않는다.

Document Parser를 파악할 때 함께 읽을 자료:

- `document-parser/README.md`: 전체 제품 목적, 사전 점역화/실시간 읽기 분리, 현재 완료 상태
- `document-parser/docs/datapack-schema.md`: precomputed document/audio와 reading 경계
- `document-parser/docs/gpu-inference-setup.md`: 실제 PaddleOCR-VL/Piper 환경과 실측
- `document-parser/src/document_parser/serialization/vl_page_ir.py`: 현재 기본 OCR -> Page IR
- `document-parser/src/document_parser/accessibility/`: 점역, speech와 navigation semantics
- `document-parser/src/document_parser/datapack/`: ingest/schema/loader와 사전 TTS
- `document-parser/src/document_parser/server/`: 과거 reading server와 현재 S0/S1 composition

## 2. 새 세션 시작 순서

다음 순서로 읽는다.

1. 이 문서 전체
2. `document-parser/README.md`
3. `document-parser/docs/datapack-schema.md`
4. `INTEGRATION_ARCHITECTURE_REASSESSMENT_20260830.md`
5. `book-scanner/SCANNER_VIDEO_V3_A_5_IMPLEMENTATION_REPORT.md`
6. `INTEGRATION_V0_IMPLEMENTATION_REPORT.md`
7. `SERVER_S0_IMPLEMENTATION_REPORT.md`
8. `SERVER_S1_IMPLEMENTATION_REPORT.md`
9. `DEVICE_CONNECTIVITY_C0_IMPLEMENTATION_REPORT.md`
10. 다음 작업을 설계할 때 각 구현 보고서가 가리키는 승인 작업 패킷

`book-scanner/CODEX_IMPLEMENTATION_CONTEXT.md`는 페이지 검출·UVDoc 작업의 역사적 출발점과
Stage 0~2 배경을 이해하는 데 유용하다. 그러나 V자형 45도 책받침, 마커 또는 calibration 가능성을
기술한 부분은 현재의 우선 물리 조건보다 오래됐다. 아래 확정 결정을 우선한다.

## 3. 사용자가 확정한 제품·실험 조건

- 카메라 구도는 고정이다. 항상 검은 배경 위에 펼쳐진 책 양면을 위에서 내려다본다. 다른 구도를
  일반화 대상으로 삼지 않는다.
- 현재 마커를 사용할 수 없다. 마커/사각형 calibration을 현재 경로의 전제로 만들지 않는다.
- Canny 자체는 금지하지 않는다. 단순히 가장 큰 사각형이나 사각형 크기만으로 페이지라고 판단하는
  방식은 금지한다. 외부/내부 contour, 색·명도, seam, 시간축 안정성 등 복합 근거를 사용한다.
- 좌우 결과 크기가 정확히 같을 필요는 없다. 본문을 훼손하지 않는 conservative crop이 우선이다.
- 페이지 검출/좌우 구분과 곡면·원근 보정은 분리된 문제다.
- 현재 채택 경로는 **`seam-conservative + UVDoc bilinear`**다. p30 golden 비교에서 golden 수식
  span 93/93을 보존했다. 이 선택은 문서에 기록돼 있지만 다른 책·구도 일반화를 입증한 것은 아니다.
- 수능특강 수학 I 왼쪽 p30 reference는 사람이 직접 검증한 golden으로 취급한다. 오른쪽 309와
  후속 p316/317 표기는 일부 실험에서 diagnostic label이며 모두 사람 golden은 아니다.
- 영상 판단은 매 프레임일 필요가 없다. 일정 cadence로 snapshot을 뽑아 반복 판정하며, 핵심 개념은
  촬영 가능 여부가 아니라 **후보정 후 서버에 전송할 수 있는지**다.
- 버튼은 단발 촬영 버튼이 아니라 촬영·선별·전송 루프 진입/취소 경계다. 완료는 서버 ACK와 후속
  계약에 맞춰 음/TTS로 알려야 한다.
- 개발 단계에서는 LAPTOP PC가 Raspberry Pi 4의 Device Runtime/Scanner/Coordinator/HTTP client
  역할을 대신한다. 배포 계획은 없으며 경량 모델·알고리즘과 지연/메모리를 우선한다.
- 사용자 변경과 기존 session/transmission 구조를 보존한다. 실제로 검증하지 않은 항목은 완료로
  처리하지 않는다.

사용자가 확인한 영상 anchor:

- `CLEAN_TRANSFERABLE`: frame 720, 13.07초, 37.19초
- `HAND_CONTENT_OCCLUSION`: 900, 1170, 1380, 1920, 1980, 2400, 2580
- `PAGE_MOVING`: 1500, 2040

## 4. 현재 아키텍처와 책임

```text
Camera / sampled snapshots
  -> Book Scanner candidate gate
  -> identity verification / duplicate suppression
  -> seam-conservative crop
  -> UVDoc bilinear correction
  -> immutable two-page artifact bundle
  -> [아직 미구현: Scanner durable outbox + Server V4 upload]
  -> Server S1 verified spread acceptance
  -> Document Parser OCR / Page IR / accessibility page fragments
  -> atomic datapack revision publish

STM buttons / lever
  -> DeviceFlowCoordinator
       -> catalog / scan / reading control (Server S0)
       -> Scanner lifecycle
       -> delivery/finalize lifecycle

Device Connectivity C0
  -> configured server health
  -> authenticated presence / heartbeat
  -> Coordinator ONLINE gate
```

책임 원칙:

- `book-scanner`는 snapshot 처리, 전송 후보 선택, 페이지 중복 억제, crop/UVDoc artifact 생성을
  소유한다. datapack catalog, reading cursor와 서버 publish를 소유하지 않는다.
- `device-runtime`의 `DeviceFlowCoordinator`는 버튼/레버와 Scanner/server 상태를 조율하지만
  OpenCV, OCR, HTTP, SQLite, TTS 구현을 직접 import하지 않는다.
- Server S0는 catalog, scan intent, seal cutoff, reading cursor를 영속화한다.
- Server S1은 서버 소유 bundle을 검증한 뒤 fragment 생성과 immutable revision append/publish를
  orchestration한다. 실제 페이지 내용 변환은 Document Parser adapter에 맡기며, 외부 upload body
  수신은 소유하지 않는다.
- Document Parser는 accepted page image를 OCR/Page IR/점자·낭독 content로 변환한다. 카메라,
  upload protocol, network retry와 장치 presence는 소유하지 않는다.
- C0는 서버 연결/presence만 소유한다. heartbeat 성공은 artifact upload ACK가 아니다.
- 다음 Server V4가 byte upload와 server-owned atomic bundle writer를 소유하고, 검증 완료 후 S1의
  `accept_verified_spread()`를 호출해야 한다.
- Scanner sender/outbox는 전송 전 파일 보존, idempotency key, retry/backoff, ACK 반영, cache quota와
  재시작 복구를 소유해야 한다.

## 5. 구현 완료 상태

### 5.1 Book Scanner V1~V2

- sampling/candidate/stability/readiness state machine과 자동 선택 보강이 구현됐다.
- seam-conservative 좌우 crop, UVDoc bilinear, 양면 atomic artifact bundle 경계가 구현됐다.
- 실제 4K MP4에서 사용자가 확인한 clean frame 2개는 V2 artifact 생성에 성공했다.
- 기존 V1 기본 gate가 해당 영상 표본을 전부 거부한 이력이 있으므로 “자동 선택이 모든 상황에서
  안정적”이라고 주장하면 안 된다. V1.2의 obstruction/page-moving 보강과 보고서를 함께 본다.
- p30 Document Parser/golden 결과는 `book-scanner/P030_MATH_BRAILLE_ALIGNMENT_REPORT.md`가
  가장 중요한 OCR 근거다.

주요 코드:

- `book-scanner/src/book_scanner/video/engine.py`
- `book-scanner/src/book_scanner/video/candidate.py`
- `book-scanner/src/book_scanner/video/obstruction.py`
- `book-scanner/src/book_scanner/video/page_change.py`
- `book-scanner/src/book_scanner/video/spread_preparer.py`
- `book-scanner/src/book_scanner/detect/spine_seam.py`
- `book-scanner/src/book_scanner/correct/uvdoc_adapter.py`

### 5.2 Scanner V3-A.5 중복 페이지 판정

기본 전략은 M1 opaque footer identity다. 정확한 페이지 번호를 복원하는 대신 좌우 bottom ROI에서
얻은 Paddle raw OCR token pair를 N번 수집해 accepted reference bank와 비교한다.

- 기본: native preview, 100ms cadence, `N=5`, `K_same=1`, `K_diff=0`
- 같은 accepted spread면 V2 crop/UVDoc와 송신 요청 전에 억제한다.
- N개의 유효 query가 모두 불일치하면 새 spread 후보로 진행한다.
- missing/provider error는 불일치로 세지 않고 UNKNOWN/local retry로 처리한다.
- ACK 전 identity는 pending이며 서버 ACK 뒤 accepted bank로 승격한다.
- A ACK -> B ACK -> A 재등장도 bounded accepted ring과 비교해 억제한다.
- exact page-number 정확도는 authority가 아니다. 기존 full-page VisualGate도 기본 authority가 아니다.
- 로컬 Paddle asset은 hash-pinned하고 runtime download/silent fallback을 금지한다.

중요한 제한은 `validated=false`다. 같은 영상의 p30/p316 두 identity에서는 native raw pair가
`p_same=0.90`, 관찰 `p_diff=0.00`이었지만 held-out spread가 부족하다. N=10은 실제 충분한 window가
없어 검증하지 못했다. 주요 파라미터는 config에서 바꿀 수 있게 구현돼 있다.

주요 문서와 코드:

- `book-scanner/SCANNER_VIDEO_V3_A_4_IMPLEMENTATION_REPORT.md`
- `book-scanner/SCANNER_VIDEO_V3_A_5_IMPLEMENTATION_REPORT.md`
- `book-scanner/src/book_scanner/video/opaque_identity.py`
- `book-scanner/src/book_scanner/video/page_number_provider.py`
- `book-scanner/src/book_scanner/video/composition.py`
- `book-scanner/experiment_inputs/scanner_video_v3a4_footer_identity_manifest.json`

### 5.3 Integration V0 Coordinator

`device-runtime`은 catalog selection, append/new scan, scanner lifecycle, monotonic sequence,
delivery/retry, freeze/flush/seal, finalize READY, reading cursor와 버튼 의미를 순수 상태기계로 고정한다.
실제 adapter는 protocol 뒤에 둔다. C0가 주입되면 authenticated ONLINE 전에 catalog를 읽지 않는다.

주요 코드:

- `device-runtime/src/asl_device/coordinator.py`
- `device-runtime/src/asl_device/types.py`
- `device-runtime/src/asl_device/protocols.py`
- `device-runtime/src/asl_device/adapters/http_s0.py`

### 5.4 Server S0/S1

- S0 SQLite schema v1: catalog, scan session, seal intent, reading progress/command receipt
- S1 schema v2: spread/fragment/finalize journal, verified local bundle acceptance, parser worker,
  append assembly와 immutable revision publish
- 기존 datapack append 실패 시 기존 READY revision을 보존한다.
- S1 ACK는 parser 완료가 아니라 서버 소유 bundle 검증과 spread/fragment DB commit 완료다.
- `/jobs`, `/sessions`, `/datapacks` legacy 경로는 보존됐다.

주요 코드와 문서:

- `document-parser/src/document_parser/server/s0_*.py`
- `document-parser/src/document_parser/server/s1_*.py`
- `document-parser/src/document_parser/server/combined_server.py`
- `document-parser/docs/server-s0-api.md`
- `document-parser/docs/server-s1.md`

### 5.5 Device Connectivity C0

- secret-safe TOML/env config와 stable provisioned device ID
- public health compatibility 뒤 authenticated presence start/heartbeat
- retryable/fatal 오류 분리, exponential backoff+jitter
- SQLite schema v3 presence persistence와 server-clock `online/stale/offline`
- Coordinator ONLINE gate와 실제 LAPTOP loopback server stop/restart session recovery

주요 코드와 문서:

- `device-runtime/src/asl_device/connectivity_config.py`
- `device-runtime/src/asl_device/connectivity.py`
- `device-runtime/src/asl_device/adapters/http_connectivity.py`
- `device-runtime/docs/device-connectivity-c0.md`
- `document-parser/src/document_parser/server/c0_presence.py`

## 6. 최신 검증 기준선

2026-08-31 C0 완료 시점의 최신 전체 결과:

| 범위 | 결과 |
|---|---:|
| Book Scanner 전체 | 288 passed |
| Device Runtime 전체 | 47 passed |
| Document Parser 전체 | 552 passed, 4 skipped, 3 subtests passed |
| S0/S1/C0/combined 집중 | 38 passed, 1 existing warning |
| C0 server 집중 | 6 passed |

Document Parser의 기존 `latex_ast.py` invalid escape warning은 이번 계열에서 생긴 것이 아니다.
Book Scanner는 Windows 한글 사용자 temp 경로가 깨져 OpenCV 파일 생성이 실패할 수 있다. 이 경우
제품 실패로 처리하지 말고 저장소 내부 ASCII `--basetemp`로 재실행한다. 실제로 그 방식으로 288개가
통과했다.

각 과거 보고서의 test count는 그 패킷 당시의 기준선이라 최신 총계보다 작을 수 있다. 최신 총계와
해당 패킷의 집중 검증을 함께 해석한다.

## 7. Git에 포함한 리소스와 로컬 전용 리소스

Git 포함 대상:

- 소스, 단위/통합 테스트, 작업 패킷, 구현/실험 보고서
- `book-scanner/experiment_outputs`의 기존 추적 산출물과 최신 요약
- `book-scanner/experiment_inputs`의 label/manifest/provenance
- 작은 경량 숫자 모델 `book-scanner/models/page_number_digit_v1.onnx`

기존 실험 산출물은 Git LFS를 사용한다. 인수인계 브랜치 최초 push에서 LFS 객체 226개, 약 808MB가
원격에 전송됐다. 새 clone/worktree에서 실제 산출물이 필요하면 Git LFS가 설치돼 있는지 확인하고
`git lfs pull`을 실행한다. 소스·테스트·Markdown만 읽는 작업에 원본 LFS blob 전체가 항상 필요한
것은 아니다.

의도적으로 Git에서 제외한 로컬/Drive 원본:

- `.codex-remote-attachments/`
- `book-scanner/TESTIMAGES/`, `book-scanner/TESTIMAGES.zip`
- `tmp/`의 UVDoc/Paddle/MediaPipe runtime, pytest, 영상 replay 중간 파일
- Google Drive `Ocr_scan`의 `20260830...` 원본 이미지/LabelMe zip과 페이지 넘김 MP4

영상 원본은 `20260830_133526.mp4`, SHA-256
`16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`로 보고서에 고정했다.
새 환경에서 원본이 필요하면 Drive에서 다시 받아 hash를 먼저 확인한다. Paddle recognition asset은
대형 runtime 자체를 Git에 넣지 않았으며 `book-scanner/experiment_inputs`의 model manifest와 hash를
따른다. 네트워크 자동 다운로드로 다른 모델을 조용히 대체하지 않는다.

## 8. 다음 우선순위

다음 작업은 **Server V4 upload protocol 작업 패킷 작성 및 승인**이다. C0를 더 확장하거나 M1
held-out 검증 때문에 주 흐름을 다시 멈추지 않는다.

V4 패킷에서 먼저 고정할 것:

1. scan session/sequence/artifact identity와 idempotency key
2. streaming body 제한, manifest와 좌우 파일 hash/size 검증
3. server-owned staging -> fsync/atomic promotion -> DB receipt 순서
4. 동일 digest replay와 다른 digest collision
5. ACK의 정확한 의미와 S1 `accept_verified_spread()` 호출 경계
6. timeout/connection loss 때 client가 안전하게 재시도할 응답 계약
7. partial/orphan staging 정리와 quota
8. 인증은 C0/S0와 같은 endpoint/API key 기반으로 시작하되 장치별 credential은 별도 강화 항목

그 다음 **Scanner V3-B sender + LAPTOP durable outbox**를 구현한다. A가 left/right 최선 artifact를
송신 중일 때 같은 spread를 다시 송신하지 않도록 in-flight/pending/ACK ledger를 디스크에 보존해야
한다. M1은 송신 전 로컬 중복 억제이고, V4 idempotency/outbox는 네트워크 재시도 중복 억제이므로
서로 대체하지 않는다.

후속 순서:

```text
Server V4 upload contract/core
  -> Scanner V3-B durable outbox/sender
  -> LAPTOP camera + STM + beep/TTS + real HTTP E2E
  -> fixed external endpoint/TLS/network fault
  -> Raspberry Pi systemd/network-online/camera/GPIO/audio/resource validation
```

## 9. 완료로 오인하면 안 되는 사항

- Scanner에서 서버로 실제 artifact bytes를 보내는 production API는 없다.
- durable outbox, ACK 후 cache eviction, process restart resend는 없다.
- 저장 완료 TTS/beep와 실제 STM serial adapter는 없다.
- 외부 fixed DNS/IP, TLS, VPN/tunnel, 실제 LAN/인터넷 E2E는 없다.
- Windows 자동 시작과 Raspberry Pi systemd/network-online 이식은 없다.
- 실제 Pi 4의 Paddle/UVDoc latency, RSS, 발열과 카메라/GPIO/audio는 측정하지 않았다.
- M1 중복 판정은 held-out spread 일반화가 부족하고 process restart 후 accepted bank 복원도 없다.
- 정확한 semantic page-number recognition은 채택된 authority가 아니다.
- 배포, PR merge와 main 반영은 이 인수인계의 완료 조건이 아니다.

## 10. 새 세션에 전달할 시작 프롬프트

```text
ASL_OCR의 codex/asl-ocr-integration-c0-handoff 브랜치에서 작업을 이어가라.
먼저 PROJECT_HANDOFF_20260831.md와 document-parser/README.md를 전부 읽고, 거기에 지정된 구현
보고서와 현재 코드/테스트를 대조하라. 이 작업은 완성된 Document Parser에 안정적인 Scanner
입력을 연결하고, 과거 검증/시연을 위해 결합된 OCR·점역·TTS·임시 서버 책임을 제품 경계에 맞게
정리하는 통합 작업이다. Document Parser의 content transformation 책임과 Server의 transport/
persistence/orchestration 책임을 혼동하지 마라. 사용자 변경과 기존 Scanner/Coordinator/S0/S1/C0
계약을 보존하라. 현재 다음 우선순위는 Server V4 upload protocol 작업 패킷 작성이며, 승인 전
구현하지 마라. 실제로 검증하지 않은 외부 네트워크, Raspberry Pi, outbox 동작을 완료로 처리하지
마라.
```
