# Scanner Video V3-A.5 — M1 Default Opaque Identity Integration 작업 패킷

상태: **구현·회귀 검증 완료 — M1 기본 채택 / 일반화 검증 후속 분리**  
작성일: 2026-08-31  
선행 조건: V2 `seam-conservative + UVDoc bilinear` atomic artifact, V3-A identity·single
in-flight·ACK lifecycle, V3-A.3 persistent Paddle recognition-only backend, V3-A.4 opaque footer
statistical replay  
후속 조건: Server S0/S1, Scanner V3-B + Server V4 durable outbox·HTTP ingest, held-out M1 validation

## 1. 결정

중복 페이지 구분의 Scanner 기본 전략으로 **M1 — 좌우 selected raw OCR token pair**를 채택한다.
페이지 번호의 의미·정확한 정수 복원은 중복 판정의 필수 조건에서 제외한다.

V3-A.4의 현재 두 spread 진단 결과는 native preview, 100ms, N=5에서 다음과 같다.

- same-spread query match: 9/10 (`p_same=0.90`)
- p30↔p316 양방향 collision: 0/10 (`p_diff=0.00` 관찰)
- `K_diff=0`, `K_same=1`: 네 relation의 오판·UNKNOWN 0
- relation별 sequential first-decision median: 3 observations, 약 300ms
- 기존 full-page VisualGate: `p_same=0.70`, 관찰 `p_diff=0.00`
`
서로 다른 identity가 p30과 p316뿐이므로 일반화 검증은 완료되지 않았다. 그럼에도 표본 확보가
전체 개발 흐름을 막지 않도록 다음 두 상태를 분리한다.

- **기본 채택·runtime 사용**: 본 패킷에서 구현
- **통계적 일반화 검증**: 추가 held-out spread 확보 뒤 후속 수행

따라서 기본 config는 M1 enforce이며 `validated=false`와 현재 provenance를 그대로 노출한다.
`validated=false`를 이유로 semantic page number나 VisualGate로 조용히 기본 복귀하지 않는다.

## 2. 본래 흐름 복원

현재까지의 구현 흐름은 다음과 같다.

```text
V0 계약
  → V1/V1.1 sampled-frame engine·runtime hardening
  → V1.2 automatic best-frame selection
  → V2 seam-conservative + UVDoc atomic spread artifact
  → Integration V0 DeviceFlowCoordinator 계약
  → V3-A identity·single in-flight·ACK 이후 page-change
  → V3-A.1~A.4 page-number/backend/stage/opaque identity 실험
```

V3-A.1~A.3은 정확한 page number와 backend 선발 문제로 확장되면서 본래 목표인 “같은 spread를
다시 보내지 않기”보다 OCR semantic accuracy가 중심이 됐다. V3-A.4는 raw token pair만으로 현재
표본을 분리해 이 우회를 종료했다.

본 패킷은 V3-A.5로 M1을 runtime에 연결하고 V3-A를 닫는다. 이후 우선순위는 기존 integration
roadmap으로 복귀한다.

1. Server S0 persistent catalog·scan session·reading progress
2. Server S1 incremental fragment append·seal·atomic datapack revision
3. Device Connectivity C0 + Scanner V3-B + Server V4를 LAPTOP PC에서 통합:
   stable endpoint·presence·durable outbox·실제 HTTP ingest·idempotency
4. LAPTOP STM/camera/audio E2E
5. 동일 계약의 Raspberry Pi 4 이식과 systemd·자원·하드웨어 검증

추가 M1 표본 수집·검증은 위 흐름의 선행 blocker가 아니라 병행 backlog다.

## 3. 현재 runtime과 목표 runtime의 차이

현재 engine은 다음 순서다.

```text
candidate select
  → seam crop + UVDoc artifact
  → full-page visual identity
  → optional semantic SpreadPageKey
  → duplicate/new/ambiguous
  → ACK
  → VisualGate 중심 WAITING_FOR_PAGE_CHANGE
```

M1은 현재 offline evaluation에만 있고 runtime 중복 판정자는 아니다.
`allow_number_only_duplicate=false`이며 page-number provider도 explicit opt-in이다.

목표 순서는 다음과 같다.

```text
candidate stable
  → VERIFYING_IDENTITY
  → native bottom ROI M1 query bank
       ├─ accepted reference 없음: 첫 spread 처리 허용
       ├─ SAME: crop/UVDoc 없이 중복 억제
       ├─ DIFFERENT: 선택 frame을 V2 처리
       └─ UNKNOWN: 추가 관찰 또는 local guidance/retry
  → seam crop + UVDoc atomic artifact
  → artifact-level exact/visual safety check
  → pending M1 bank + single in-flight
  → server ACK
  → pending bank를 accepted bank로 승격
  → WAITING_FOR_PAGE_CHANGE에서 M1 반복 관찰
```

M1을 V2 이후에만 놓으면 같은 페이지를 확인할 때마다 crop과 UVDoc을 다시 실행한다. 따라서
primary M1 gate는 안정 후보 선택 뒤, V2 full-resolution 처리 전에 둔다. Artifact-level identity는
lineage·exact duplicate·conflict safety를 위해 유지한다.

## 4. 도메인 계약

### 4.1 `OpaqueFooterTokenPair`

한 eligible full-spread frame에서 다음을 생성한다.

```text
OpaqueFooterTokenPair
  left_raw_token: non-empty string
  right_raw_token: non-empty string
  source_frame_id
  captured_at_monotonic
  recognition_stage
  recognizer_id/version/preprocessing_version
  left/right ROI SHA-256
```

규칙:

- provider의 selected raw text를 사용하고 숫자 의미·범위·연속성을 검사하지 않는다.
- 좌우 모두 non-empty인 pair만 유효 observation이다.
- semantic `COMPLETE/CONFLICT`는 진단값이다. raw pair가 완성되면 M1 observation으로 사용할 수 있다.
- 한쪽 또는 양쪽 missing은 mismatch 시행이 아니라 **관측 미성립**이다.
- missing-to-missing, empty-to-empty는 SAME evidence가 아니다.
- 로그에는 raw token 원문 대신 pair digest, 길이, status, match count를 기본 기록한다.

### 4.2 Reference/query bank

```text
OpaqueReferenceBank
  artifact_id / receipt_id
  data_pack_id / scan session lineage
  token pairs up to reference_bank_size
  accepted_at
  policy snapshot/version

OpaqueQueryWindow
  valid token pairs up to query_sample_count
  started_at / last_observed_at
  exclusion counters
```

- reference/query는 같은 frame ID를 공유하지 않는다.
- query observation 하나가 시행 한 번이다.
- 한 query pair가 reference bank의 pair 중 하나와 exact-equal이면 match 1이다.
- reference×query N² 비교 횟수를 N²개의 독립 시행으로 세지 않는다.
- current accepted reference는 ACK 이후 page-change를 판단한다.
- bounded accepted-bank ring은 같은 scan/data pack에서 이전에 보낸 spread 재등장을 찾는다.
- image pixel 전체는 identity bank에 장기 보관하지 않는다.

### 4.3 3상태 판정

유효 query observation 수를 `n`, 그중 reference bank와 match한 수를 `S`라고 한다.

- `SAME`: `S >= K_same`
- `DIFFERENT`: N개가 모두 수집됐고 `S <= K_diff`
- `UNKNOWN`: 그 외, timeout, 유효 pair 부족, provider 오류

기본값 `N=5`, `K_same=1`, `K_diff=0`에서는 첫 match에 SAME을 조기 확정할 수 있지만
DIFFERENT는 유효 pair 5개가 모두 mismatch일 때만 확정한다. OCR missing 5회를 DIFFERENT 5회로
가장하지 않는다.

여러 accepted bank를 비교할 때 bank 하나라도 SAME이면 duplicate다. 모든 비교 가능한 bank가
DIFFERENT일 때만 new candidate로 진행한다. 하나 이상 UNKNOWN이 남으면 전체 결과도 UNKNOWN이다.

## 5. Config 계약

새 설정은 기존 semantic `PageNumberPolicy.allow_number_only_duplicate`를 재사용하지 않고 별도
정책으로 둔다.

```python
class OpaqueIdentityStrategy(str, Enum):
    M1_SELECTED_RAW_PAIR = "m1_selected_raw_pair"
    LEGACY_VISUAL = "legacy_visual"       # 명시적 rollback 전용

class OpaqueFooterInputStage(str, Enum):
    PREVIEW_1920 = "preview_1920"
    PREVIEW_NATIVE = "preview_native"

@dataclass(frozen=True, slots=True)
class OpaqueFooterIdentityPolicy:
    strategy: OpaqueIdentityStrategy = M1_SELECTED_RAW_PAIR
    input_stage: OpaqueFooterInputStage = PREVIEW_NATIVE
    observation_interval_ms: int = 100
    reference_bank_size: int = 5
    query_sample_count: int = 5
    k_same: int = 1
    k_different: int = 0
    max_collection_ms: int = 1500
    accepted_bank_capacity: int = 32
    max_recognition_in_flight: int = 1
    validated: bool = False
    provenance: str = "v3a4_two_spread_default_validation_deferred"
```

Validation:

- 모든 interval/count/capacity는 양수
- `0 <= k_different < k_same <= query_sample_count`
- `reference_bank_size <= accepted_bank_capacity`는 요구하지 않되 각 차원의 bounded 상한을 검증
- M1 기본 활성 상태에서 recognition provider가 없으면 start/composition에서 fail-fast
- runtime model download나 자동 backend 교체 금지
- 한 scan session 중 policy snapshot 변경 금지

100ms는 요청 하한이다. 이전 recognition이 끝나지 않았으면 새 요청을 queue에 누적하지 않는다.

```text
effective interval = max(config interval, prior inference completion)
```

skip count와 실제 timestamp 간격을 diagnostics에 남긴다.

## 6. Recognition backend와 composition

- 기본 backend는 V3-A.3에서 사용한 hash-pinned local `en_PP-OCRv5_mobile_rec` recognition-only다.
- 모델은 process/session당 한 번 load하고 좌우 bottom ROI만 입력한다.
- 네트워크 모델 다운로드는 허용하지 않는다.
- Paddle/PaddleOCR을 순수 domain 모듈이나 기본 단위 테스트 import 경로에 넣지 않는다.
- engine은 protocol에만 의존하고 단위 테스트는 fake provider를 사용한다.
- PC runtime composition은 M1 기본 config일 때 explicit model path·manifest와 provider를 주입한다.
- model asset 또는 provider가 없으면 visual default로 silent fallback하지 않고 구성 오류를 낸다.

`PageNumberVerificationScheduler`의 VisualGate-triggered mode는 M1 기본 경로에서 사용하지 않는다.
M1 observation은 eligible identity verification cadence가 직접 소유한다. 기존 scheduler는 legacy
semantic 실험/rollback 호환을 위해 유지하거나 deprecated 경계를 명시한다.

## 7. 상태기계 변경

### 7.1 `VERIFYING_IDENTITY`

안정 candidate가 선택되면 즉시 V2 processing으로 가지 않고 M1 bank를 수집한다.

```text
SEARCHING/SETTLING
  → stable candidate selected
  → VERIFYING_IDENTITY
       ├─ motion/hand/layout hard failure: query 폐기 → SETTLING
       ├─ SAME: DUPLICATE_SUPPRESSED → WAITING_FOR_PAGE_CHANGE
       ├─ DIFFERENT: PROCESSING_CANDIDATE
       ├─ first spread bank complete: PROCESSING_CANDIDATE
       └─ timeout/provider unavailable: UNKNOWN → LOCAL_RETRY/guidance
```

- 기존 best frame은 verification 동안 소유하되, page motion/hard failure가 나오면 폐기한다.
- verification frame을 기존 selected frame과 다른 left/right artifact로 조합하지 않는다.
- M1 bank는 artifact lineage에 연결하지만 V2 좌우 artifact는 기존 selected source frame 하나에서만
  생성한다.
- 같은 spread SAME이면 preparer call, UVDoc call, artifact commit, outbox request 모두 0이다.

### 7.2 Pending/ACK/reject

- DIFFERENT 또는 첫 spread의 query bank를 artifact와 함께 pending으로 소유한다.
- delivery ACK만 pending bank를 accepted bank로 승격한다.
- reject, local preparation failure, cancel-before-ACK는 pending bank를 폐기한다.
- stale/repeated ACK는 현재 bank를 교체하지 않는다.
- single in-flight 중에는 새 M1 collection·V2 processing을 시작하지 않는다.

### 7.3 `WAITING_FOR_PAGE_CHANGE`

ACK 뒤 M1이 page-change의 primary 근거다.

- SAME: 대기 유지, 동일 page에 대한 완료음/TTS 반복 0
- DIFFERENT: query를 폐기한 뒤 candidate window도 비우고 SEARCHING으로 전환
- UNKNOWN: 계속 관찰; visual DIFFERENT만으로 release하지 않음
- motion/hand/page-turn frame: valid M1 trial에 포함하지 않음
- source exhaustion/cancel/error: query state와 in-flight recognition 정리

SEARCHING에서 실제 안정 candidate가 다시 선택되면 M1 verification을 재수행한다. WAITING 단계의
변경 관측을 그대로 artifact reference로 승격하지 않는다.

## 8. Visual identity의 보조 역할

M1 채택 뒤 full-page VisualGate는 기본 duplicate 판정자가 아니다.

유지:

- CandidateGate의 motion/hand/page-turn/geometry 안정성
- artifact byte-exact duplicate safety
- M1/visual conflict diagnostics
- M1 DIFFERENT 뒤 artifact visual duplicate가 발생한 경우 automatic send 대신 conflict/UNKNOWN
- 기존 identity ledger와 lineage, rollback 비교

금지:

- M1 missing/UNKNOWN을 visual `NEW_SPREAD`로 대체해 전송 허용
- VisualGate가 Paddle 호출 여부를 기본 결정
- visual fingerprint가 raw token을 수정하거나 의미적 page number를 생성
- disagreement를 조용히 M1 또는 visual 한쪽 성공으로 강제

Artifact-level exact duplicate는 항상 억제할 수 있다. M1 DIFFERENT와 visual duplicate가 충돌하면
기존 `IDENTITY_CONFLICT` 계열 local retry로 보수 처리한다.

## 9. Event·diagnostics

추가 event 또는 동등한 structured details:

- `OPAQUE_IDENTITY_COLLECTION_STARTED`
- `OPAQUE_IDENTITY_OBSERVED`
- `OPAQUE_IDENTITY_DECIDED`
- `OPAQUE_IDENTITY_BANK_PENDING`
- `OPAQUE_IDENTITY_BANK_ACCEPTED`
- `OPAQUE_IDENTITY_BANK_DISCARDED`
- 기존 `DUPLICATE_SUPPRESSED`, `PAGE_CHANGED`, `ARTIFACT_READY`

최소 diagnostics:

- strategy, policy/provenance/validated
- source frame/timestamp/stage/provider version
- valid, missing, hard-rejected, busy-skipped observation count
- reference/query bank depth
- match count, `K_same/K_diff/N`, decision, first-decision count/time
- compared bank artifact/receipt ID
- raw token pair digest와 side별 token length; 원문 token은 기본 log에 미출력
- visual conflict와 최종 automatic action
- recognition processing ms, effective interval, provider load/call/cache count

## 10. Guidance와 사용자 경험

- SAME은 정상 대기 상태이므로 반복 음성 안내를 만들지 않는다.
- DIFFERENT 자체는 성공이 아니다. 새 artifact가 서버 ACK될 때만 기존 완료 feedback을 낸다.
- valid pair 부족·timeout은 `FOOTER_IDENTITY_UNAVAILABLE` 또는 동등한 semantic guidance reason으로
  표현한다.
- 구체적인 TTS renderer는 Device Integration 범위지만, Scanner는 “책 하단 노출/손 제거/잠시
  대기”로 매핑 가능한 reason을 제공한다.
- network retry는 identity/물리 guidance와 분리한다.

## 11. 캐시·메모리·복구

- query: 최대 `query_sample_count`
- reference bank: bank당 최대 `reference_bank_size`
- accepted: 최대 `accepted_bank_capacity` bounded ring
- recognition cache: 기존 ROI SHA/version/side/stage key와 bounded capacity 유지
- full ROI pixels는 accepted identity ledger에 보존하지 않음
- raw pair·ROI digest·timestamp·provider version만 보존

현재 in-memory bank는 같은 process/scan session 범위다. 프로세스 재시작 또는 기존 datapack append
시 서버에 이미 저장된 전체 페이지 identity를 자동 복원하지 않는다. 이는 V3-B/Server V4의 durable
outbox·identity metadata 계약에서 해결하며 본 패킷에서 crash-safe 완료로 표시하지 않는다.

## 12. 구현 단계

### Phase 0 — 기록과 roadmap 정합화

- M1 default·validation deferred 결정을 설계/README에 기록
- `SCANNER_CONTINUOUS_TRANSFER_READINESS_DESIGN.md`의 V1/V2 `미구현` 상태를 실제 완료 상태로 수정
- semantic page number 실험과 M1 runtime identity의 책임을 분리
- V3-A.5 이후 Server S0/S1로 복귀하는 우선순위 기록

### Phase 1 — Pure domain/config

- strategy/stage/policy와 validation
- immutable token pair, reference/query bank, decision/diagnostics
- bounded accepted bank ledger
- query 1건=시행 1건, SAME early decision, DIFFERENT complete-N decision
- missing/invalid observation exclusion과 timeout UNKNOWN

### Phase 2 — Engine integration

- `VERIFYING_IDENTITY` 상태와 poll cadence
- stable candidate 이후, V2 전 M1 collection
- SAME의 zero-preparer suppression
- DIFFERENT/first-spread의 pending bank lineage
- ACK promote, reject/cancel/failure discard
- WAITING_FOR_PAGE_CHANGE의 M1 primary 전환
- source exhaustion, stale callback, retry reset

### Phase 3 — Paddle composition

- local hash-pinned persistent backend injection
- native/1920 input-stage selection
- recognition single-in-flight와 busy skip
- backend/model 부재 fail-fast
- no-download guard와 provenance diagnostics

### Phase 4 — Safety fusion·rollback

- artifact exact/visual identity 유지
- M1 DIFFERENT↔visual duplicate conflict에서 local retry
- 명시적 `LEGACY_VISUAL` rollback config
- legacy semantic PageKey path 보존 및 기본 비활성
- 기존 public session/delivery/Coordinator contract 변화 최소화

### Phase 5 — Replay·회귀·보고

- V3-A.4 frozen observation으로 default N/K 결과 재현
- runtime state machine fake-camera replay
- 전체 Book Scanner 및 Integration V0 회귀
- performance/call/cache diagnostics
- implementation report와 실제 미검증 항목 기록

## 13. 테스트 행렬

### 13.1 Config/pure decision

- default strategy M1, stage native, N=5, K=1/0
- 모든 invalid N/K/interval/capacity 거부
- valid query 한 건만 trial 1 증가
- missing/empty pair는 trial 증가 0
- left-only/right-only equality는 match 0
- 좌우 exact pair가 reference 중 하나와 같으면 match 1
- first match에서 SAME early decision
- N개 all mismatch에서만 DIFFERENT
- N 미충족 timeout은 UNKNOWN
- reference/query frame overlap 거부
- accepted bank ring bounded eviction

### 13.2 Engine lifecycle

- 첫 spread: N valid bank 후 V2 preparer 1회
- accepted A 뒤 A same: preparer/UVDoc/artifact/outbox 0
- accepted A 뒤 B all mismatch: V2 processing 1회
- A pending/upload/retry 중 candidate/M1/V2 새 작업 0
- ACK만 pending bank를 accepted로 승격
- reject/cancel/preparation failure는 pending bank 폐기, 기존 accepted 유지
- stale/repeated ACK/reject가 bank 상태 변경 0
- hard-gate/motion/hand frame은 M1 trial 0
- provider busy는 queue 증가 없이 skip
- provider missing/error timeout은 DIFFERENT가 아니라 UNKNOWN
- source exhaustion/cancel/close에서 provider/camera/worker 정리

### 13.3 Conflict/fallback

- M1 DIFFERENT + artifact visual duplicate → automatic send 0, conflict retry
- M1 UNKNOWN + visual new → automatic release/send 0
- artifact exact duplicate → 중복 억제
- legacy visual은 explicit rollback에서만 기본 authority
- semantic `allow_number_only_duplicate`가 M1 기본값을 바꾸지 않음
- provider/model 없는 M1 composition은 silent fallback 없이 fail-fast

### 13.4 Frozen replay

- p30 same N=5 native: 5/5 match
- p316 same N=5 native: 4/5 match
- p30→p316, p316→p30: 각 0/5 collision
- p316 left stale `30` 한쪽 충돌이 pair SAME을 만들지 않음
- runtime missing-exclusion semantics의 별도 결과 기록
- N=10 이상은 실제 표본 부족 상태를 유지하고 완료 처리하지 않음

### 13.5 Regression

- 현재 Book Scanner 전체 264 tests 기준 회귀
- existing identity/page-change/page-number/scheduler tests 보존
- V2 same-frame atomic artifact, UVDoc lineage 변화 0
- single in-flight, ACK/reject/cancel 의미 변화 0
- Integration V0 Coordinator callback 계약 변화 0
- Document Parser/server import/call 0
- runtime model download/network 0

## 14. 성능 기준

PC provisional 계측:

- native Paddle recognition median 약 46ms/side
- footer visual descriptor median 약 0.754ms/side
- V3-A.4 capture에서 persistent load 1, ROI call 640, download 0

본 패킷에서 확인할 것:

- M1 spread recognition median/p95/max
- busy skip와 effective observation interval
- SAME 결정 전 call 수/지연
- DIFFERENT 결정 전 call 수/지연
- M1 SAME으로 절약한 preparer/UVDoc/artifact count
- peak reference/query bank depth
- PC CPU/RSS와 process model load count

100ms를 hard realtime 보장으로 쓰지 않는다. Pi 4 latency/RSS는 `NOT_MEASURED`로 남긴다.

## 15. 완료 기준

- M1 selected raw 좌우 pair가 default duplicate strategy
- 주요 N/K/cadence/stage/capacity/timeout이 validated config로 구조화
- 여기서 validated config란 **값 validation을 통과한 config type**을 뜻하며 정책 일반화
  `validated=false`와 구분
- stable candidate 뒤 V2 전에 M1 identity verification 수행
- SAME에서 V2 preparer/artifact/outbox 0
- DIFFERENT는 N valid all-mismatch 또는 일반 K 규칙을 충족할 때만 처리
- UNKNOWN/missing을 new page로 가장하지 않음
- ACK 기반 pending→accepted bank 전이
- single in-flight 및 stale callback 불변식 유지
- VisualGate는 safety/diagnostic, semantic page number는 legacy/diagnostic 역할
- hash-pinned local Paddle, load 1, network download 0
- frozen replay와 전체 회귀 통과
- roadmap 문서의 실제 구현 상태 정합화
- 일반화 false-duplicate, N=10, Pi 4, crash recovery를 완료 처리하지 않음

## 16. 비범위

- 추가 이미지/영상 수집 또는 사람 label 생성
- M1 일반화 검증 완료·`validated=true`
- 새로운 OCR 모델 학습, fine-tuning, 외부 dataset/model download
- 의미적 페이지 번호 정확도 개선
- CandidateGate, seam, crop, UVDoc threshold 재튜닝
- 실제 HTTP server, durable outbox, SQLite identity persistence
- Server S0/S1 catalog·append·seal 구현
- Document Parser OCR·점역 pipeline 변경
- STM/GPIO, 실제 TTS/beep, Pi camera/systemd 배포
- 원격 branch push, PR, release

## 17. 승인 경계

승인 시 다음 변경을 수행한다.

- `video/config.py`, `types.py`, `protocols.py`, `events.py`의 M1 계약
- 새 M1 bank/tracker 모듈과 fake provider
- `video/engine.py`의 `VERIFYING_IDENTITY`, ACK bank lifecycle, M1 page-change 연결
- PC explicit Paddle composition 경계와 fail-fast/no-download guard
- 단위·state-machine·frozen replay 테스트
- README/연속 Scanner 설계/구현 보고서 갱신

다음은 별도 승인 없이는 수행하지 않는다.

- `validated=true` 선언
- Server S0/S1 또는 V3-B/V4 HTTP/outbox 구현
- Document Parser/server/Coordinator public contract 확대
- 신규 dependency의 production 자동 설치·모델 다운로드
- Pi 4 배포
- commit/push/PR

## 18. 중단 조건

다음이 발생하면 visual/semantic 방식으로 몰래 되돌리지 않고 원인과 영향 범위를 보고한다.

- 기존 engine poll 구조에서 M1 collection을 넣으려면 좌우를 서로 다른 selected artifact frame으로
  조합해야 함
- M1 SAME인데도 preparer/UVDoc/artifact가 먼저 실행되는 구조를 피할 수 없음
- ACK 전에 bank를 accepted로 승격해야만 lifecycle이 동작함
- provider missing을 DIFFERENT로 처리해야만 다음 페이지로 진행 가능함
- single-in-flight, stale ACK/reject, cancel 소유권을 약화해야 함
- Paddle를 domain 기본 import 또는 runtime download dependency로 넣어야 함
- Coordinator가 raw token/bank/recognizer 구현을 직접 소유해야 함
- V3-A.4 결과 재현 실패 또는 기존 전체 회귀 실패

중단 시 구현 완료로 표시하지 않고, M1 기본 결정과 해결되지 않은 integration blocker를 분리해
보고한다.
