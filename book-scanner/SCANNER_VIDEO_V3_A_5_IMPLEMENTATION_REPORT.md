# Scanner Video V3-A.5 — M1 Default Opaque Identity Integration 구현 보고서

상태: **구현 및 현재 저장소 회귀 검증 완료**  
작성일: 2026-08-31  
정책 일반화 상태: **`validated=false` — held-out spread 검증 미완료**

## 결과

V3-A.4에서 선발한 M1, 즉 좌우 bottom ROI의 selected raw OCR token pair를 Scanner의 config 기본
중복 전략으로 연결했다. 기본값은 native preview, 100ms, N=5, `K_same=1/K_diff=0`이다.

안정 후보는 즉시 seam crop/UVDoc로 가지 않고 `VERIFYING_IDENTITY`에서 유효 pair를 수집한다.
accepted reference와 SAME이면 V2 preparer·artifact commit·전송 요청 없이
`WAITING_FOR_PAGE_CHANGE`로 이동한다. 첫 spread 또는 N개의 all-mismatch는 기존의 한 selected
full-spread frame을 V2에 넘긴다. missing/provider 오류는 mismatch로 세지 않으며 timeout UNKNOWN은
`FOOTER_IDENTITY_UNAVAILABLE` local retry가 된다.

## 구현 계약

- `OpaqueFooterIdentityPolicy`: strategy/stage/N/K/cadence/timeout/capacity/provenance 구조화
- `OpaqueFooterTokenPair`: raw pair 원문을 판정에 사용하되 event에는 digest와 길이만 기록
- `OpaqueQueryCollector`: SAME 조기 확정, DIFFERENT complete-N 확정, missing 제외
- `InMemoryOpaqueIdentityLedger`: bounded accepted ring과 단일 pending bank
- ACK만 pending bank를 accepted로 승격; parser reject/cancel/error는 pending을 폐기
- ACK 이후 page-change는 현재 accepted bank에 대한 M1 DIFFERENT가 primary 근거
- 이전 accepted bank A가 B 이후 재등장해도 전체 accepted ring과 비교해 V2 전에 억제
- artifact exact duplicate는 억제하고, M1 DIFFERENT와 visual duplicate 충돌은 local retry
- semantic page-number artifact 판정과 VisualGate scheduler는 M1 기본 경로에서 authority가 아님
- `LEGACY_VISUAL`은 명시적 rollback으로만 사용

PC composition은 local `en_PP-OCRv5_mobile_rec`의 필수 asset 세 개를 SHA-256으로 모두 고정해야
provider를 만든다. backend/model 설정이 없으면 fail-fast하며 runtime download와 silent visual
fallback은 금지했다. Paddle import는 pure identity/config/test 경로에 들어가지 않는다.

## 검증

실행 결과:

- Book Scanner 전체: **288 passed**
- Integration V0 `device-runtime`: **26 passed**
- V3-A.5 신규 domain/composition/engine 집중 테스트: **24 passed**
- V3-A.4 frozen replay 재실행: 330 settings 중 22 measured, 308 not measured
- frozen best candidate 재현: native/100ms/N=5/M1, `p_same=0.90`, 관찰 `p_diff=0.00`,
  median first decision 3 observations/300ms

엔진 테스트에서 확인한 대표 경로:

- 첫 spread는 유효 pair 5개 뒤 V2 preparer 1회·artifact commit 1회
- ACK 전 accepted bank 0, ACK 뒤 accepted bank 1
- reject는 pending bank 폐기, accepted bank 오염 0
- A ACK → B ACK → A 재등장에서 세 번째 A의 preparer/commit 증가 0
- M1 DIFFERENT + artifact VISUAL_DUPLICATE에서 `ARTIFACT_READY` 0
- missing-only window는 DIFFERENT가 아닌 timeout UNKNOWN, preparer/commit 0
- stale/repeated ACK는 bank 상태 변화 0

## 관측성과 리소스 경계

event에는 collection/observation/decision/pending/accepted/discarded 전이를 추가했다. diagnostics는
valid/missing/hard-rejected/busy-skipped, SAME/DIFFERENT/timeout 수와 effective interval을 제공한다.
provider가 노출하는 load/call/cache count와 recognition processing time도 structured details에 넣는다.

현재 recognition 호출은 engine poll 경계에서 동기식이다. 따라서 동시에 한 건만 실행되고 queue가
누적되지 않으며 busy-skip은 0이지만, OCR 한 번의 시간만큼 해당 poll 호출은 걸린다. 이 수치는
PC에서만 확인했으며 Pi 4 latency/RSS 보장은 아니다.

## 완료로 처리하지 않은 사항

- p30/p316 외 held-out spread의 false-duplicate/false-new 일반화
- N=10 이상: frozen stable block이 부족해 대부분 `NOT_MEASURED`
- 실제 Pi 4 Paddle latency/RSS, camera/GPIO/audio
- process restart와 기존 datapack append 시 accepted identity bank 복원
- durable outbox, 실제 HTTP ingest, server idempotency
- semantic page-number 정확도 향상
- 실제 TTS/beep feedback

V3-A.5로 Scanner 로컬 중복 판정 우회는 닫는다. 개발 단계 device host는 LAPTOP PC로 고정한다.
다음 우선순위는 Server S0/S1 이후 LAPTOP 기반 Device Connectivity C0, Scanner V3-B + Server V4,
LAPTOP STM/camera/audio E2E, Raspberry Pi 이식·target 검증 순이다. M1 일반화 검증은 병행
backlog로 남긴다.
