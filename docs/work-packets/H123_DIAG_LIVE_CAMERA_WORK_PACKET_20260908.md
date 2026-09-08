# Proposed bounded implementation packet C — Live-camera liveness / recovery

상태: **제안만 작성; product/config 수정·live 실행 미승인/미실행**. 근거: [진단 보고서](../H1_H2_H3_SOFTWARE_DIAGNOSTIC_RESULT_20260908.md) §2–7.

## Scope와 진단 결론

- C2 confirmed: timeout/5xx/auth 실패가 모두 SnapshotTransportError→generic frame_decode_failed로 합쳐지고 transport retry가 없다.
- C3 confirmed: page-change UNKNOWN timeout은 diagnostic만 발생하고 guidance cue를 생성하지 않는다.
- LIVE liveness: fake all-valid2.5 s는8초에서 reset, bounded30초에서 성공한다.1.9 s는9.58초에 성공한다. 이는 sample-start clock임을 드러내며 **현재 engine이 항상 N5를8초 안에 완료해야만 accept한다는 주장은 틀리다**.
- 실제 H1의 valid1/0 tail에는 missing/quality reject 원인이 남아 있다.30초 fake PASS를 실제 camera/profile PASS나 engine redesign 명령으로 취급하지 않는다.

## Inputs / unchanged contracts

Current source `book_scanner/video/sources.py`, `engine.py`, config/runtime composition, device scanner adapter/guidance mapping. [Reproducer/results](../evidence/software-diagnostic-20260908/laptop-reproduction-results.json), [H1 raw bundle](../evidence/software-diagnostic-20260908/raw-evidence.json), [durable outbox](../evidence/software-diagnostic-20260908/state-evidence.json).

Strict Android IP Camera profile, existing endpoint/credential-file reference/TLS profile만 사용. Credential 값 출력·저장/변경0, global TLS disable0, webcam fallback0. Scanner N5, K/identity/duplicate/candidate threshold, same-frame L/R, durable receipt-before-spread_sent, READY-before-saved와 stable device ID 유지.

## C1 discrimination before engine change

Live 실행 전에 검증 invariant를 “동일 eligible changed spread에서 N5를 유한 시간에 수집하고 실제 reset/latency 원인을 설명할 수 있음”으로 명시한다. 새 C: isolated runtime만 사용한다.

각 frame acquisition start/end, analyze latency/retry reasons, recognition latency/valid/missing, collection start/reset reason/deadline을 secret-safe 동일 clock에 기록한다. 기존8초와 finite30초를 **진단 profile**로 비교하되 N5/gates는 동일하게 둔다. Whole-response/cancel wall-clock bound와 sample-start budget 의미를 먼저 정의한다.

30초에서도 missing/quality reject가 원인이면 capture condition/환경으로 분류하고 threshold를 바꾸지 않는다.30초에서 실제 valid N5가 안정적으로 확보되면 profile/document 변경이 최소 후보이며 engine scheduling patch를 자동 포함하지 않는다. Processing 시간을 장부에서 무조건 제외해 무한 대기시키지 않는다.

## C2/C3 minimum product patch budget

우선 sources.py + engine.py 최대2파일. 기존 scanner feedback adapter mapping이 반드시 필요하면 최대3파일. 필요한 tests만 추가한다. 새 cue server feature/architecture layer가 필요하면 별도 budget 요청한다. 기존 generic scan.guidance cue로 필요한 안내가 가능한지 먼저 확인한다.

Transport taxonomy는 timeout/connection/retryable5xx와401/403/설정·TLS 실패를 구분한다. Retry count/backoff/overall elapsed ceiling을 유한하게 정하고 last error class/stage/status/attempt와 recovery를 관측 가능하게 한다. Decode에는 이미3회 retry가 있으므로 중복 nesting으로 상한을 무심코 곱하지 않는다. Sustained loss는 명시 fatal이어야 한다.

Page-change timeout은 rate-limited existing guidance로 전달하되 UNKNOWN을 DIFFERENT로 만들지 않는다. Same reference/accepted bank/durable lineage를 유지한다. Retry/cancel/stop 후 stale frame을 새 session이나 collector로 넣지 않는다.

## Targeted acceptance

Timeout→success,503→success, bad JPEG→good, 지속 transport/decode 실패,401/403, TLS/auth-read error, response/session close, stop/cancel during acquisition/retry; strict source identity/fallback0. Retry와 transient recovery에서 duplicate artifact/receipt0.

Page-change unknown/missing/quality-reset마다 guidance rate/내용·audio mapping 검증, 같은 page false-change0. Clock1.9/2.5 s 및 deadline 전 시작·후 completion, variable latency, finite budget, N/K unchanged. Existing Scanner/video/adapter tests→book-scanner/device subsystem→G3-A 순서.

## Fresh H1 validation declaration

Evidence root `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics\camera-<fresh-id>`. Diagnostic snapshot-only 단계에는 serial packet/production upload **없음**. Source URL과 requested/effective resolution, interpreter/profile/hash를 기록하고 어떤 stage를 우회하는지 명시한다.

Fresh full H1은 별도로 실행 계획을 보고한 후 새 datapack에 pages26/27→28/29를 capture한다. Expected network lineage는 seq1/2 artifact→durable V4 receipt→CONFIRM LONG→fresh READY revision이다. 구 scan을 resume하거나 DB를 reset하지 않는다. 실제 안내 청취를 feedback 이벤트와 별도로 기록한다.

Stop: finite camera failure ceiling, identity 혼입, duplicate/sequence/left-right mismatch, receipt 전 send cue, false READY, password 노출 위험, source fallback, 예상 밖 server mutation. 실패 증거를 보존하고 timeout 무한 확대 또는 thresholds 완화로 통과시키지 않는다.

## Completion

확인 결함 C2/C3 targeted/subsystem PASS, C1의 환경/profile vs engine 판단 근거, G3-A 유지, fresh two-spread H1/READY 성공을 각각 보고한다. 카메라 개선이 native audio/STM controls/clear acceptance를 대체하지 않으며 H4는 별도다.
