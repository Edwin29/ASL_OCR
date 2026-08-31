# Scanner Video V3-A — Page identity·중복 억제·page-change gate 작업 패킷

상태: **구현 완료 — 로컬 lifecycle·결정론적 회귀 통과 / identity 임곗값·실영상 page-change 검증 미완료**
작성일: 2026-08-30
선행 조건: Integration V0 coordinator 계약, Scanner V0 계약, V1/V1.1/V1.2 후보 선택, V2 `seam-conservative + UVDoc bilinear` atomic artifact
후속 조건: V3-B durable outbox·전송 상태기계, V4 Document Parser spread ingest API

## 1. 목표

동일하게 펼쳐진 책을 연속 관찰할 때 같은 좌우 페이지를 두 번 처리·전송하지 않도록 다음
로컬 계약을 구현한다.

- V2 좌우 artifact에서 경량·버전 고정 page/spread identity를 산출
- 한 spread가 전송 대기 또는 전송 중이면 새 후보 확정을 막는 single in-flight gate
- 동일 pending/accepted spread를 다시 만나면 새 전송 요청 대신 중복으로 분류
- 서버 접수 확인 뒤 `WAITING_FOR_PAGE_CHANGE`에서 저비용으로 페이지 변경을 감시
- 변경 중인 프레임을 선택하지 않고, 새로운 spread가 안정된 뒤에만 후보 수집을 재개

V3-A의 전송 단위는 `left_page` 단독이 아니라 같은 source frame에서 생성된
`spread(left + right)`다. A spread의 left/right를 송신하는 동안 A와 같은 spread를 다시
선택하거나 별도 left upload를 생성하지 않는다.

V3-A 완료는 실제 HTTP 송신, 재부팅 후 재전송 또는 서버 멱등성 검증 완료를 뜻하지 않는다.

## 2. 확정 설계 결정

### 2.1 Identity와 artifact ID를 구분

`session_id`, `spread_id`, `frame_id`, `artifact_id`는 실행 lineage다. 같은 페이지를 다시
촬영하면 값이 달라지므로 page identity로 사용하지 않는다.

각 corrected page에 다음 versioned fingerprint를 생성한다.

- 파일 SHA-256: 완전히 같은 byte 검출
- grayscale perceptual hash: 노출·미세 위치·JPEG 차이가 있는 동일 페이지 후보 검출
- 구조 보조 fingerprint: 축소 이미지의 수평/수직 명암 projection 또는 동등한 저비용 특징
- 정규화 입력 크기, 알고리즘·파라미터 버전, 원본 page hash

spread identity는 left/right page fingerprint를 좌우 순서를 보존해 결합한다. left와 right를
바꾸어도 같은 pair로 취급하지 않는다.

perceptual hash 하나와 임의의 거리 임곗값만으로 중복을 확정하지 않는다. 교재 페이지는
레이아웃이 유사하므로 다음 순서로 보수적으로 판정한다.

1. 좌우 byte hash가 모두 같으면 `EXACT_DUPLICATE`
2. 좌우 모두에서 perceptual/구조 특징이 합의하면 `VISUAL_DUPLICATE`
3. 일부 특징 또는 한쪽 페이지만 일치하면 `AMBIGUOUS`
4. 좌우가 충분히 다르면 `NEW_SPREAD`

한쪽 page fingerprint 일치는 diagnostics와 향후 parser page identity에 사용하되, pair 전체를
중복 확정하는 유일한 근거로 사용하지 않는다.

### 2.2 Fingerprint 입력

기본 page identity는 V2가 atomic commit한 `uvdoc.jpg`에서 생성한다. 다음 lineage도 함께
기록한다.

- source frame hash
- conservative crop hash
- corrected page hash
- extractor, UVDoc, fingerprint version
- page side와 출력 크기

정규화는 decode, grayscale, 고정 크기 축소와 제한된 illumination normalization만 허용한다.
새 ML 모델, OCR, 네트워크 호출 또는 학습 데이터 다운로드를 identity 경로에 넣지 않는다.

UVDoc/crop 설정 버전이 달라지면 fingerprint가 직접 호환된다고 가정하지 않는다. 서로 다른
fingerprint version은 기본적으로 `AMBIGUOUS`이며 migration 또는 재계산 경로가 있을 때만
비교한다.

### 2.3 Single in-flight spread

V2 artifact commit 성공 직후 해당 identity를 `PENDING`으로 등록하고 engine 소유권을 고정한다.

```text
PROCESSING_CANDIDATE
  -> ARTIFACT_READY
  -> IDENTITY_CHECK
       |- accepted/pending duplicate: DUPLICATE_SUPPRESSED
       |- ambiguous: IDENTITY_AMBIGUOUS
       `- new: READY_FOR_SERVER_PREFLIGHT + PENDING
```

- active pending spread는 최대 하나
- `READY_FOR_SERVER_PREFLIGHT`, `UPLOADING`, `REMOTE_RETRY` 동안 full-resolution 후보 수집 중지
- 같은 pending identity 요청은 새 artifact/outbox 항목을 만들지 않고 기존 pending 항목에 병합
- pending 중 network 결과가 불명확하면 새 촬영이 아니라 같은 artifact 재시도가 원칙
- parser reject는 accepted ledger에 넣지 않으며, pending을 해제하고 더 좋은 frame 재촬영을 허용
- delivery confirm만 `PENDING -> ACCEPTED` 전이를 허용

V3-A에는 실제 upload worker가 없으므로, V3-B가 사용할 명시적 lifecycle 입력 계약을 둔다.

```text
delivery_queued(artifact_id)
delivery_confirmed(artifact_id, receipt_id)
delivery_rejected(artifact_id, reason)
delivery_retrying(artifact_id)
```

다른 artifact ID의 늦은 ACK/reject가 현재 pending identity 상태를 변경하지 못해야 한다.

### 2.4 ACK 이후 page-change gate

`delivery_confirmed`가 로컬 상태에 기록된 뒤에만 완료 event를 내고
`WAITING_FOR_PAGE_CHANGE`로 이동한다. 이 상태에서는 V2 seam/UVDoc을 실행하지 않고 축소
preview만 읽는다.

초기 정책:

- sampling: provisional 750ms
- page pair, motion, obstruction, preview spread fingerprint만 평가
- 직전 accepted spread와 충분히 유사하면 계속 대기
- 차이가 모호하면 계속 대기하고 전송하지 않음
- 큰 motion/page-turn 뒤 새로운 안정 표본 K개가 나타나면 변경 후보
- sampling 사이에 page turn을 놓칠 수 있으므로, motion이 관찰되지 않아도 충분히 큰 변화가
  연속 K개 안정 표본에서 지속되면 page-change 허용
- page-change 확정 시 기존 candidate window를 전부 비우고 `PAGE_CHANGED`를 한 번만 발행한 뒤
  `SEARCHING`으로 전환

페이지 변경 gate의 K는 우선 기존 `stable_sample_count=3`을 재사용한다. 750ms, K=3은 첫 표본과
세 번째 표본 사이 약 1.5초다. 이 값은 Pi 또는 실제 사용성 검증을 거치기 전까지
`validated=false`로 기록한다.

중간 page-turn, 손 가림, 그림자 급변, 한쪽 페이지만 검출된 frame은 새 페이지 증거가 아니다.

### 2.5 Identity ledger와 캐시 경계

V3-A는 다음 protocol과 bounded in-memory 구현을 제공한다.

```text
PageIdentityLedger.register_pending(identity, artifact_id)
PageIdentityLedger.find_match(identity)
PageIdentityLedger.confirm(artifact_id, receipt_id)
PageIdentityLedger.reject_or_release(artifact_id)
PageIdentityLedger.recent_accepted()
```

- pending entry: 한 개
- accepted entry: 최근 N개 bounded ring
- 저장 내용: fingerprint와 lineage/receipt metadata이며 full image 사본을 만들지 않음
- artifact 파일은 기존 `ArtifactStore`가 소유하며 identity cache가 삭제하지 않음
- session cancel은 실행 중 작업을 중단하지만 이미 accepted인 기록을 잘못 pending으로 되돌리지 않음

V3-A의 in-memory ledger는 동일 process/session 안의 중복 방지를 검증하기 위한 것이다. 프로세스
재시작 뒤에도 pending upload와 accepted identity를 보존하는 SQLite WAL 구현은 V3-B 범위다.
따라서 V3-A만 완료한 상태에서 crash-safe 중복 방지를 완료로 표시하지 않는다.

## 3. 구현 범위

예상 production 경계:

```text
src/book_scanner/video/
  identity.py       # page/spread fingerprint와 비교 결과
  page_change.py    # preview observation과 hysteresis gate
  types.py          # identity/gate immutable 계약
  protocols.py      # fingerprint/ledger/lifecycle 경계
  config.py         # provisional identity/page-change policy
  events.py         # identity 및 page-change 관찰 event
  engine.py         # pending 소유권과 WAITING_FOR_PAGE_CHANGE 실행
```

정확한 파일·타입 이름은 저장소 관례에 맞춰 조정할 수 있지만 다음 불변식은 유지한다.

- 좌우 page identity는 같은 V2 source frame에서 생성
- atomic artifact commit 전 fingerprint/pending publish 없음
- accepted 표시는 delivery ACK 뒤에만 가능
- pending spread가 있으면 새 processing job 생성 0
- page-change 확정 전 다음 artifact 생성 0
- ambiguous identity를 자동으로 새 페이지 또는 중복 페이지로 가장하지 않음
- fingerprint failure를 SHA-only 성공으로 silent fallback하지 않음

기존 `session/`, `judge/`, `transmit/` public API는 변경하지 않는다.

## 4. Event와 관찰성

최소 event 또는 동등한 구조화된 details를 제공한다.

- `SPREAD_IDENTITY_CREATED`
- `DUPLICATE_SUPPRESSED`
- `IDENTITY_AMBIGUOUS`
- 기존 `DELIVERY_CONFIRMED`
- 기존 `WAITING_FOR_PAGE_CHANGE`
- 기존 `PAGE_CHANGED`

identity event에는 원본 fingerprint 전체를 로그에 노출하지 않고 다음을 기록한다.

- algorithm/version
- match kind와 거리 지표
- 비교 대상 artifact/receipt ID
- pending/accepted 구분
- 결정에 사용한 좌우 합의 여부
- page-change stable count와 motion/change evidence

같은 polling 결과에서 `PAGE_CHANGED`가 반복 발생하지 않아야 한다.

## 5. 검증 행렬

### 5.1 Fingerprint 단위 검증

- 동일 파일은 exact duplicate
- 같은 p30을 재촬영한 서로 다른 세 JPEG의 좌우 결과는 visual-match 후보
- 밝기, JPEG 재압축, 작은 translation/scale 합성 변형에 identity가 과민하게 바뀌지 않음
- 서로 다른 페이지를 같은 것으로 확정하지 않음
- left/right 순서가 바뀐 pair는 다른 spread identity
- 한쪽만 일치하면 pair duplicate로 확정하지 않음
- fingerprint version 불일치는 명시적 ambiguous/incompatible
- decode 실패와 누락된 좌우 artifact는 명시적 실패

합성 변형은 강건성 개발 자료로만 사용한다. 실제 서로 다른 페이지 negative와 실제 재촬영
positive가 없는 항목을 일반화 검증 완료로 표시하지 않는다.

### 5.2 In-flight 및 race 검증

- artifact A가 pending인 동안 camera/frame evaluator/preparer 재호출 0
- A pending 상태에 A duplicate가 들어와도 새 artifact/outbox 요청 0
- A의 retry 신호가 새 capture를 만들지 않음
- A와 다른 artifact의 늦은 ACK가 A를 accepted로 바꾸지 않음
- confirm event 중복 입력은 idempotent이며 완료 event/완료음 근거 1회
- reject 뒤 accepted ledger 오염 0, window를 비우고 local recapture 허용
- cancel과 confirm race에서 단 하나의 정의된 terminal owner만 상태를 변경

### 5.3 Page-change replay

- ACK 뒤 동일 spread 정지 frame이 계속되어도 artifact 추가 생성 0
- `HAND_CONTENT_OCCLUSION` 및 `PAGE_MOVING` 라벨 frame은 page-change 안정 표본이 아님
- page-turn motion 뒤 새 spread의 안정 표본 K개에서 `PAGE_CHANGED` 1회
- sampling 사이에 motion을 놓쳐도 지속적인 큰 identity 변화 + 안정 K개면 변경 감지
- 한 표본만 달라진 조명/그림자 spike는 page-change가 아님
- 한쪽 page 미검출 또는 ambiguous identity는 계속 waiting
- page-change 확정 직후 candidate window가 비어 있고 이전 표본과 섞이지 않음

기존 MP4의 frame/time 구간을 사용하되, “같은 페이지/새 페이지” identity 라벨이 없는 구간을
임의로 ground truth로 간주하지 않는다. 기존 CLEAN/HAND/PAGE_MOVING 라벨은 frame 상태 검증에만
사용한다.

### 5.4 회귀 및 성능

- V0~V2 video unit test와 legacy 전체 unit test 회귀 없음
- p30 V2 좌우 hash/provenance와 UVDoc 산출물 변화 없음
- fingerprint와 page-change preview latency, peak memory를 PC에서 기록
- WAITING 상태에서 UVDoc load/inference 호출 0
- page identity cache가 full-resolution frame/image 사본을 보유하지 않음
- Pi 4 성능은 실제 측정 전 완료로 표시하지 않음

## 6. Threshold 결정과 검증 자료 분리

perceptual distance 및 page-change threshold는 코드 작성 편의를 위해 임의의 production 값으로
확정하지 않는다.

1. 실제 same-page positive와 different-page negative 목록을 manifest로 고정
2. 개발 집합에서 후보 threshold와 feature 합의 규칙 결정
3. threshold를 고정한 뒤 분리된 replay/이미지에 적용
4. false duplicate와 duplicate miss를 pair/page 단위로 함께 보고
5. false duplicate가 하나라도 나오면 해당 범위를 자동 억제 완료로 표시하지 않고 ambiguous로
   보수 처리

p30 세 재촬영본은 same-page positive로 사용할 수 있다. 영상의 서로 다른 stable frame은 페이지
내용이 실제로 같은지 확인된 경우에만 identity label로 사용한다.

## 7. 완료 기준

- V2 corrected left/right에서 versioned page/spread identity 생성
- single in-flight pending spread 불변식과 race test 통과
- pending/accepted 동일 pair의 새 artifact/전송 요청 0
- delivery confirm 뒤 `WAITING_FOR_PAGE_CHANGE` 진입
- 동일 페이지가 남아 있는 동안 추가 artifact 0
- 새 spread의 안정성이 확인된 뒤 `PAGE_CHANGED` 1회 및 candidate window reset
- page-turn/hand/ambiguous frame을 새 페이지로 확정하지 않음
- p30 same-page positive와 확인된 different-page negative 결과를 분리 보고
- 전체 unit test 회귀 없음
- 실제 threshold 검증을 못한 항목은 provisional/blocked로 기록

V3-A 완료 선언에는 “동일 실행 중 로컬 중복 억제”만 포함한다. 다음 항목은 별도 완료 근거가
필요하다.

- 재부팅 후 중복 방지: V3-B durable ledger/outbox
- lost-response 재전송 멱등성: V3-B client + V4 server
- Document Parser 실제 접수: V4 spread ingest API

## 8. 비범위

- 실제 HTTP/multipart upload와 인증
- SQLite durable outbox, lease, backoff, crash recovery
- 서버 idempotency key/digest/receipt 저장
- Document Parser endpoint 변경과 OCR 실행
- parser가 반환하는 page number 기반 dedup
- Raspberry Pi Picamera2/GPIO/systemd
- 새 ML/hand detection 모델 추가 또는 모델 다운로드
- UVDoc 위치 변경, sharpen/denoise/SR
- 기존 seam/crop/obstruction threshold 재튜닝

## 9. 중단 조건

- 중복 억제를 위해 left/right를 서로 다른 frame에서 조합해야 함
- pending 전송 중에도 새 artifact를 생성해야만 상태기계가 진행됨
- perceptual hash 단일 임곗값만으로 서로 다른 교재 페이지를 자동 삭제해야 함
- ACK 전에 accepted로 기록하거나 완료음을 발생시켜야 함
- ambiguous identity를 성공/중복 중 하나로 조용히 강제해야 함
- V3-B 없이 crash-safe 또는 server-idempotent라고 주장해야 함
- 실제 identity label 없이 영상 구간을 same/different ground truth로 간주해야 함

위 조건이 발생하면 구현 범위를 확대하거나 임곗값을 즉석 변경하지 않고 설계 충돌과 필요한
추가 자료를 보고한다.

## 10. 구현 결과 (2026-08-31)

승인 범위의 production 코드와 결정론적 테스트를 구현했다.

- V2 atomic artifact의 manifest·좌우 corrected page hash를 검증하고 DCT perceptual hash,
  명암 projection, ORB 보조 특징을 결합하는 `page-identity-v3a-1` identity를 생성한다.
- 좌우 순서를 보존한 spread 비교는 exact, visual duplicate, ambiguous, new spread를 구분하며
  decode/lineage 검증 실패를 SHA-only 성공으로 대체하지 않는다.
- 한 개 pending과 최근 32개 accepted를 보관하는 bounded in-memory ledger를 추가했다.
- delivery queued/retrying/confirmed/rejected 입력, stale 또는 반복 ACK 무시, reject/cancel 해제,
  ACK 뒤 `WAITING_FOR_PAGE_CHANGE` 진입을 engine에 연결했다.
- 대기 중에는 V2 preparer/UVDoc을 다시 실행하지 않고 750ms preview 표본과 연속 3개 안정 변화로
  page-change를 판정한다. 변경 확정 event는 latch되어 한 번만 발생한다.
- 전체 Book Scanner unit test는 223개 통과했다. pytest cache 디렉터리 권한 경고 1개는 남았지만
  테스트 실패는 없었다.

실제 p30 재촬영 3장의 동일 페이지 positive 세 쌍에서는 현재 provisional 정책이
`VISUAL_DUPLICATE` 1쌍, `AMBIGUOUS` 2쌍을 냈다. 서로 다른 spread로 보이는 MP4 두 artifact는
`NEW_SPREAD`였으나 해당 비교는 사용자 확인 identity label이 없으므로 negative 정확도에 포함하지
않았다. 따라서 코드 경계와 보수적 실패 처리는 구현 완료지만, 실제 duplicate recall과 false
duplicate 임곗값은 검증 완료가 아니다. 실제 MP4 page-change replay와 Pi 4 latency/RSS도 아직
검증하지 않았다. 상세 수치와 재현 명령은 `SCANNER_VIDEO_V3_A_IMPLEMENTATION_REPORT.md`에 기록한다.
