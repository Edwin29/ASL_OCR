# Architecture assurance — bounded local correction packets

상태: **제안만 작성, product 구현 0**. [Architecture 판정](../H123_CRITICAL_PATH_ARCHITECTURE_ASSURANCE_20260908.md)이 선행 계약이다. 아래 항목은 서로 독립 승인·diff·rollback 단위를 갖는다. 기존 진단 packet의 구현 승인을 의미하지 않는다. Source file 상한에는 새 product module도 포함하며 tests/docs는 별도 표시한다.

공통 유지 계약: stable device ID/operation identity, same-frame L/R, N/K/identity/duplicate thresholds, production8초, durable outbox/V4 receipt→accepted identity→READY 순서, FRAME15값/10cell encoding, V3 ACK/dedupe/A-R, auth/TLS, audio interruption, 기존 content waiver/Deferred. Dependency/lockfile/servo LUT/pins/state/DB 변경0.

## L-B. Host edge ordering + complete-line acceptance

- **대상:** B-host 및 CP-H1. `stm_serial.py:129,256–367`의 동일 worker 내부 수정. 별도 transport/scheduler layer 불필요.
- **상한:** product2파일(`adapters/stm_serial.py`, 필요할 때만 `hold_repeat.py`); targeted test3파일 이하. `application.py`나 protocol 변경이 필요해지면 이 packet 상한 초과로 다시 설계 검토한다.
- **변경 invariant:** newline-delimited record 전체를 수신·검증한 뒤만 sequence 수락/ACK. 모든 read 분할에서 원래 seq와 동일. Release를 이미 관측한 같은 connection/hold의 stale A가 다음 batch에서 hold를 다시 켤 수 없음. Release 긴급 처리와 accepted command ordering을 동시에 보존.
- **최소 방향:** Worker에 bounded partial-line state와 overflow discard-until-delimiter; reconnect/epoch에서 partial record 폐기. Edge drain은 accepted ordinal/epoch 또는 release watermark를 사용한 기존 queue merger/fence 후보를 비교한다. 단순 release 우선순위 삭제, queue 무한 확대, drop-all-backlog는 금지.
- **오류/종료:** Partial timeout은 아직 record 미완성이며 parse/ACK하지 않음. Overflow는 malformed record만 버리고 다음 line에서 복구. Connection failure는 기존 forced release/reconnect/dedupe reset. Driver close 완료와 join timeout을 구분한 probe를 추가한다.
- **Targeted regression:** (1)16개 backlog+A/R across2batches, (2)normal queue full+release, (3)slow S0 중 release, (4)disconnect/re-HELLO와 pending A, (5)각 byte offset에서 HELLO/NAV 분할, 특히 seq78→7/8, (6)CRLF/empty/oversize/Unicode/error/short write, (7)complete duplicate ACK 및 command exactly once, (8)latest-wins FRAME byte ordering/reconnect replay.
- **Migration/rollback:** Stored data/FRAME/V3 변화0. 새 parser는 timeout partial을 성공 packet으로 취급하던 잘못된 동작만 제거한다. Rollback은 승인된 diff만 역적용하고 검증 baseline으로 복원; reset/clean 금지. Old baseline의 host defects도 복귀함을 표기.
- **실제 재검증:** G3-A 뒤 fresh H3 V3 A/R·hold release·reconnect와 fresh H2 normal-rate FRAME. Direct paced test는 보조. Physical packet·stop/evidence 계획을 먼저 보고하고 실행. Host correction으로 firmware byte loss가 고쳐졌다고 선언하지 않는다.

## L-C3. Page-change waiting guidance

- **대상:** C3, `engine.py:645–831`의 page-change waiting producer. 기존 guidance arbiter와 semantic event 경로를 사용한다.
- **상한:** product1파일 `book-scanner/video/engine.py`; targeted test2파일 이하. 새로운 server cue/content가 필요하면 별도 요청; generic existing guidance를 사용 가능한지 먼저 확인.
- **변경 invariant:** Sustained unknown/eligible rejection/collection timeout은 bounded cadence로 actionable guidance를 생성하며 page-change 성공/receipt/READY로 승격되지 않음. Existing candidate guidance와 rate limiting을 중복하지 않음.
- **최소 방향:** Already observed reason/unknown 결과를 기존 guidance path로 보내고 cancel/state exit/reset 시 cadence state 정리. 반복 timeout마다 audio queue를 무조건 interrupt하거나 spread_sent를 재방송하지 않음.
- **Targeted regression:** Slow valid observations, missing footer, hard rejection, sustained same page, successful change, cancel/freeze/receipt retry에서 guidance count/cadence와 state/accepted bank 불변. Fake sink는 producer 검증이고 speaker 완료 아님.
- **Migration/rollback:** Data/protocol0, feedback event 추가만. 해당 engine diff만 역적용 가능. H1 live guidance와 실제 system cue 확인 비용1회; H2/H3에서는 priority/supersession 회귀만 확인, 최종 H4에서 유지.

## L-C2. Snapshot error taxonomy와 기존 state-machine recovery

- **대상:** C2. Auth/TLS/config permanent와 transport transient를 구분하는 국소 수정 후보.
- **상한:** product3파일 `book-scanner/video/sources.py`, `book-scanner/video/engine.py`, `asl_device/adapters/book_scanner_runtime.py`; targeted test3파일 이하.
- **선행 조건:** [D-C](H123_ARCH_DIAGNOSTIC_DESIGN_20260908.md#d-c-live-acquisition과-input-scheduling의-시간취소-계약)의 error/clock/cancel 설계 리뷰. Taxonomy 자체는 독립 review 가능하지만 live recovery의 충분성은 설계 결과 없이 승인하지 않음.
- **변경 invariant:** 401/403, credential/config/TLS 문제는 명확한 permanent failure. 허용된 transient는 finite attempt/deadline 후 명확한 failure. Retry 중 accepted bank/outbox/receipt를 유실하거나 같은 frame을 새 관찰로 세지 않음. Cancel/freeze 후 재시도가 다시 살아나지 않음.
- **최소 방향:** Secret-safe typed reason을 보존하고 기존 engine의 polling/retry 상태를 이용한다. `read()` 안에 sleep/retry를 더 넣어 application turn을 늘리지 않는다. Recovery가 acquisition owner 분리를 요구하면 이 packet에서 구현하지 않고 D-C 구조 packet으로 이동.
- **Targeted regression:** Timeout/connection reset/408/429/selected5xx와401/403/TLS/credential error 각각; bounded retry exhaustion, cancel during retry, reconnect response close, same source strictness, late result/session mismatch, 이미 durable인 artifact 보존. Malformed JPEG의 기존3회 동작과 신규 transport retry를 구분.
- **Migration/rollback:** Existing config 의미·production8초·HTTP timeout 수치 변경0. 예외/event 의미 변경이 Device adapter까지 일관되게 이어져야 함. 세 파일 diff를 원자적으로 rollback. Fresh H1 정상 두 spread와 controlled transient/recovery가 필수; G3-A/후속 H4 비용 포함.

## L-T1. IP camera preflight fidelity

- **대상:** T1. `laptop_acceptance.py:105,172` profile validation/probe dispatch.
- **상한:** product2파일(기본 `laptop_acceptance.py`, 공유 factory 호출을 위해 꼭 필요할 때만 `book-scanner/video/runtime_composition.py`); targeted test2파일 이하.
- **변경 invariant:** Parsed android_ip_camera config는 그 source만 probe하며 webcam pass가 IP source failure를 가릴 수 없음. 현재 profile-local auth/TLS/orientation을 그대로 적용하고 secret은 report에서 제외.
- **Targeted regression:** IP profile factory 선택, failed IP의 OpenCV 호출0, password/TLS 정책 전달, sanitized result, existing pc_camera/android_uvc 동작. Read-only snapshot은 source acquisition만 증명함을 report에 명시.
- **Migration/rollback:** Config/API/storage 변화0. Tool probe path 교정. Approved diff만 역적용 가능; historical preflight evidence 덮어쓰기0. 실제 Laptop preflight1회+H1 source manifest 대조. 새 live profile/credential 생성0.

## L-T2. Terminal outcome와 cleanup lifecycle

- **대상:** T2 + CP-T1. `_fatal`, `stop`, CLI return의 연결.
- **상한:** product3파일 `coordinator.py`, `application.py`, `__main__.py`; targeted test3파일 이하. 미래 launch wrapper는 별도 tooling2파일 이하, 보존된 H1/H2/H3 runtime script는 수정하지 않음.
- **변경 invariant:** Fatal outcome은 feedback/cleanup보다 먼저 latch하고 child exit까지 보존. Domain STOPPED와 cleanup-complete는 구분. Normal/fatal/partial startup/KeyboardInterrupt 모두 필요한 resources를 idempotently 정리. Best-effort disconnect 실패는 원래 fatal 이유를 성공으로 바꾸지 않음.
- **최소 방향:** Existing Coordinator outcome property와 cleanup latch, application finally/fanout 확인, CLI의 explicit nonzero mapping. 새로운 supervisor/process manager 불필요. 모든 exception을 handled success로 전환하지 않음.
- **Targeted regression:** Startup fatal, running Scanner fatal, auth fatal, recoverable 후 정상 종료, KeyboardInterrupt, stopped-after-fatal connectivity.stop exactly once, scanner.close 실패에도 host closes, 한 close 실패 시 remaining resource 처리와 first fatal 보존. Real subprocess return code 확인. Tee/scheduled task에서는 child exit와 wrapper state를 각각 기록.
- **Migration/rollback:** Exit-code 소비자가 handled fatal을 이제 실패로 보게 되는 운영상 호환성 변화가 있음. 기존 code0 성공 기대를 수정하되 DB/schema/device ID 변화0. Three-file diff atomic rollback, rollback 시 T2 재발 명시. H1 controlled fatal 종료+fresh H3 exit/re-entry, 마지막 H4 restart/cursor 검증 필요.

## L-A2. Audio replacement publication ordering — 조건부 local packet

- **대상:** A2. `reading_audio.py:_submit/interrupt`에서 old cancellation이 current generation을 abort하는 순서 결함.
- **상한:** product1파일 `reading_audio.py`, targeted test2파일 이하. Native player는 D-A 소유이며 이 packet에서 독자 수정하지 않음.
- **선행 조건:** D-A에서 cancellation target 및 old-owner termination/activation 규칙을 확정. 단순히 notify를 lock 안팎으로 옮기는 patch 승인 금지.
- **변경 invariant:** Replacement를 runnable로 공개할 때 old cancellation은 new stream을 선택할 수 없음. Latest-only completion, cue priorities, cache/last-key/re-entry contract 유지.
- **Targeted regression:** Cached/instant fetch 직후 old stop barrier; queued system cue→reading, reading→catalog/mode exit, double interrupt/close, old fetch late return, stop throws; new generation failure0/stale completion0. Fake test 뒤 actual native validation은 D-A와 결합.
- **Migration/rollback:** External API/data 변화0. A1 owner 계약과 함께 원자적으로 검증·rollback. A2만 PASS로 native AV blocker를 닫지 않음. Fresh H2/H3 speaker 및 H4 same-generation 비용은 D-A에 포함.

## Local 범위의 종료 기준

각 packet은 승인된 diff, before/after targeted evidence, subsystem 결과, 필요한 fresh hardware 결과를 별도로 낸다. 하나의 subsystem에서 PASS를 얻기 위해 다른 subsystem threshold/protocol/acceptance를 변경하지 않는다. 모든 local packet이 닫혀도 D-A/D-C/D-F 또는 hardware blocker가 남으면 H4/integration ready를 선언할 수 없다.
