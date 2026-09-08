# H1 page-change liveness diagnostic/design work packet — 2026-09-08

상태: **추가 계측·설계 우선. Product 수정 미실행.** 근거는 [fresh H1 보고서](../H1_CAMERA_FRESH_RUN_20260908.md)와 [liveness summary](../evidence/h1-camera-fresh-20260908-101447/footer-liveness-analysis.json)다.

## 판정

First failing boundary는 `SampledFrameEngine._poll_opaque_page_change()`의 opaque footer identity admission이다. Production은 8초마다 collector를 reset했고 sequence 2를 만들지 못했다. 같은 배치의 28/29는 production-native threaded 진단에서 안정화 뒤 `28|29` 6회를 냈지만 첫 exact pair가 11.406초에 나타났다. 최초 8초에는 complete pair 1개뿐이었다.

분류는 **probable_product_risk_with_confirmed_runtime_profile_incompatibility / P1**이다. Camera transport, candidate visibility, V4 receipt와 audio guidance는 이 failure의 first cause가 아니다. 다만 query-only 진단이 원래 engine instance의 collector/reset을 실행하지 않았으므로 특정 patch를 confirmed root correction으로 바로 채택하지 않는다.

위반 invariant는 다음과 같다. 고정 Android source와 선정 demo pages에서 선명하고 정지한 새 spread는 same-frame/N5/K/identity/duplicate 계약을 유지하면서 유한 시간 안에 page-change를 통과해야 한다. 현재 8초 attempt는 첫 유효 pair 이전의 acquisition/recognition 불안정 시간까지 소비하고 전 attempt의 관측을 폐기한다.

## 변경 전 필수 replay

Product 수정 없이 recorded timing/token sequence로 실제 engine/collector를 재생한다.

1. 첫 8초 complete pair 1개, 11.406초부터 `28|29`가 반복되는 sequence.
2. Production console의 1.656–3.281초 effective interval과 valid 4 timeout sequence.
3. Valid 5지만 novel consensus가 부족한 sequence.
4. Same-page reference, alternating false tokens, 영구 missing 및 candidate hard rejection sequence.
5. Deadline 직전 시작·직후 완료 sequence로 기존 C-clock soft-deadline 동작 확인.

각 replay는 false `DIFFERENT` 0, false `PAGE_CHANGED` 0, accepted-bank/receipt ordering 유지, finite guidance를 검사한다. 기존 unit test는 빠른 fake observation만 사용해 실제 cadence+stabilization+반복 reset을 결합하지 않으므로 이 gap을 먼저 닫는다.

## 비교할 bounded correction 후보

후보 A는 identity attempt clock을 첫 complete pair에서 시작하고, 그 전 missing/hard-reject 시간은 별도의 기존 WAITING guidance/liveness 관측으로 남기는 방식이다. N5, majority consensus, duplicate/reference bank를 바꾸지 않는다. 영구 missing이 무한 silent wait가 되지 않도록 별도 finite operator guidance와 terminal/supervisor 정책을 명시해야 한다.

후보 B는 max age가 있는 sliding query observation window를 timeout 경계 사이에 유지하는 방식이다. Post-turn 이전 token이나 서로 다른 물리 배치가 섞일 위험이 있어 frame age, motion/hard-reject reset, visual-change epoch가 모두 필요하다. 이 조건을 증명하지 못하면 후보 A보다 범위가 크므로 채택하지 않는다.

후보 C는 page-turn 뒤 bounded stabilization gate를 두고 identity clock을 연다. Candidate eligibility만으로 OCR footer 안정화를 보장하지 못한다는 이번 evidence를 반영해 fresh-frame count와 complete-pair readiness를 구분해야 한다. 고정 sleep 추가는 허용하지 않는다.

1920 input 전환은 이번 30초 lower-resolution 비교에서 초기 token 변동이 남았고 production contract도 달라지므로 단독 fix 후보가 아니다. 8초 단순 연장, N/K/threshold 완화, camera 설정 변경도 후보에서 제외한다.

## Change budget과 호환성

- Diagnostic replay: product 파일 0, test/tooling 최대 2파일.
- 후보 A 또는 C의 local lifecycle correction: `book-scanner/src/book_scanner/video/engine.py` 최대 1파일, 기존 tests 또는 새 targeted test 최대 2파일.
- 새로운 전체 liveness budget/config가 필요할 때만 `video/config.py`와 device runtime config mapping을 추가해 product 최대 3파일로 확대한다. 이 경우 **architecture_change_required**로 재승인한다.
- 새 camera queue, 새 service/process, OCR model/dependency 변경은 change budget 밖이다.

Migration 영향은 기본 후보 A/C에서는 없다. Event names, N5/K, frame identity, reference bank, same-frame artifact, V4 receipt 및 READY 계약을 그대로 유지한다. 새 config가 필요하면 기존 8초 값의 의미와 default를 보존하고 manifest schema 및 example profile migration을 별도 보고한다.

Rollback은 해당 engine/config 변경과 targeted tests만 되돌리는 단일 bounded patch다. Existing state/SQLite/artifact/reference bank migration은 없어야 하며 rollback 시 reset이나 evidence 삭제를 수행하지 않는다.

## Targeted regression과 재검증 비용

1. Recorded sequence engine tests: 약 5–8 cases, 수 초.
2. Book-scanner targeted/subsystem suite와 device scanner adapter tests.
3. 새 source identity에서 G3-A replay: receipt2/fragment4/fresh READY/N5 유지.
4. Fresh H1 재시험 1회: camera preflight, pages26/27·28/29, receipt2, CONFIRM LONG, fresh READY. 실패 시 같은 계측으로 1회 bounded repeat만 허용.
5. H2/H3는 scanner event/order 또는 application turn latency가 바뀐 경우에만 fresh 영향 회귀를 수행한다. H4는 H1과 독립 audio/STM/hardware blocker가 모두 닫힌 뒤 1회 전체 수용한다.

예상 비용은 software replay/subsystem 반나절 이내, fresh H1 operator run 약 15–30분, G3-A 기존 절차 1회다. H1 수정만으로 H2/H3/H4 완료를 선언하지 않는다.

## 종료 조건

설계 선택 전에는 product source를 수정하지 않는다. Replay에서 후보가 N5와 false-change 0을 유지하고 recorded slow/stabilizing sequence를 유한하게 통과시켜야 local correction으로 승격한다. 그렇지 않으면 `insufficient_evidence`로 남기고 native OCR frame별 ROI/hash 및 camera freshness 계측을 추가한다.
