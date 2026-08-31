# Scanner 연속 영상·전송 준비도 아키텍처 결정 및 설계

상태: **방향 채택 — 구현 전 설계 기준**  
작성일: 2026-08-30  
대상: PC 프로토타입 → Raspberry Pi 4/Linux 배포  
기준 실험: p30 human golden 검증 및 수식 셀 분리 평가

## 1. 확정 결정

### D-001. 기본 페이지 처리 경로

**채택:** `seam-conservative + UVDoc bilinear`

```text
full-spread frame
→ luminance-valley spine seam
→ union-preserving conservative 좌우 소유권/crop
→ 좌우 페이지별 UVDoc bilinear
→ 전송 준비도 평가
```

채택 근거:

- p30 자동 crop 3/3에서 문제 1~4와 선택지 구조 보존
- p30 human golden 공통 수식 span 93/93 보존
- p30 human golden 공통 점자 셀 624/624 일치
- golden-only 수식 누락 0 span/0 cell
- 반대 페이지 포함 0, own-page recall 1.0인 p30 라벨 결과
- 기존 20260826 라벨에서 overlap 대비 반대 페이지 유입을 크게 줄임

이 결정은 더 이상 단순 실험 후보 선택이 아니다. 영상 Scanner 구현의 기본 경로로 사용한다.

그러나 다음 사실도 함께 기록한다.

- 현재 production session loop에는 아직 통합되지 않았다.
- 다른 책·조명·그림자·잘림과 Raspberry Pi 4 성능은 미검증이다.
- 실험에서 실패가 발견되면 실패 artifact를 보존하고 정책을 재검토한다.
- `none` crop은 비교·진단 경로로 유지하며 기존 코드를 삭제하지 않는다.

### D-002. 버튼의 의미

**채택:** 버튼은 단일 사진의 셔터가 아니다.

- IDLE에서 버튼 입력: 연속 캡처·판정 loop 시작
- loop 실행 중 버튼 입력: 현재 loop 취소
- 전송 완료 뒤: loop는 유지되고 다음 페이지 넘김을 기다림
- 다음 spread가 안정되면 같은 절차를 자동 반복

버튼을 누른 순간의 한 프레임을 정답으로 간주하지 않는다.

### D-003. 판단 시점

**채택:** 촬영 전에 “촬영 가능한가”를 보장하려 하지 않는다.

카메라는 loop 동안 계속 프레임을 생성한다. 판단 대상은 이미 획득한 frame과 그 frame에서
만든 crop/UVDoc artifact다. 실패하면 다음 frame을 계속 평가한다.

## 2. 핵심 제안: `전송가능여부`를 단일 bool로 만들지 않는다

`전송가능여부` 한 값에 다음 서로 다른 질문을 합치면 오류 복구와 책임 경계가 불명확해진다.

1. 이 frame은 비싼 처리를 시도할 가치가 있는가?
2. 좌우 crop과 UVDoc artifact가 생성됐는가?
3. artifact가 Scanner의 영상·구조 gate를 통과했는가?
4. Document Parser가 입력으로 인수할 수 있는가?
5. 서버가 artifact를 내구성 있게 저장하고 작업을 접수했는가?

따라서 다음 세 계층으로 분리한다.

### 2.1 Candidate readiness

저비용 frame 단계다. 최종 전송 판정이 아니라 UVDoc/업로드 후보를 고르는 단계다.

- frame decode 성공
- 책/페이지 후보 존재
- 물리 frame 잘림 없음
- 손·페이지 넘김 등 큰 motion 없음
- 최근 frame과 mask/bbox가 안정
- blur·노출이 후보군 안에서 상대적으로 양호

실패하면 아무것도 “촬영 실패”로 확정하지 않고 다음 frame을 본다.

### 2.2 Artifact readiness

선택한 full-resolution frame을 실제 처리한 뒤의 로컬 판정이다.

- 한 full-spread 원본에서 좌우 페이지 모두 생성
- seam-conservative 진단·crop lineage 존재
- 좌우 UVDoc 완료
- 본문/외곽 잘림, 반대 페이지 유입, 비정상 크기·aspect 진단
- blur, exposure, glare/shadow, resolution과 encode 검증
- 원본/crop/UVDoc hash와 metadata 기록
- 같은 spread 중복 여부 확인

이 단계가 통과하면 `READY_FOR_SERVER_PREFLIGHT`다. 아직 사용자 완료음의 근거는 아니다.

### 2.3 Parser acceptance / delivery confirmation

Document Parser 또는 그 앞의 ingest service가 판단한다.

- 파일 decode와 hash 검증
- Document Parser 입력 quality contract 통과
- 필요하면 저비용 parser/OCR preflight 통과
- 서버 저장 완료와 idempotency key 접수
- page pair/spread job ID 발급

서버가 내구성 있는 접수를 확인한 뒤 `DELIVERY_CONFIRMED`가 된다. 사용자 완료음은 이 상태에서
한 번만 낸다.

## 3. 권장 전체 흐름

```text
button START
  ↓
ARMED / continuous camera acquisition
  ↓ configured sample cadence
latest-frame sampling + cheap spread detection + motion/stability
  ├─ poor candidate → guidance scheduler → next frame
  └─ promising candidate
       ↓
select best frame from a short stable sample window
       ↓
same full-spread frame
  → seam-conservative left/right crop
  → UVDoc left/right
  → local artifact readiness
       ├─ retryable failure → guidance → next frame
       └─ READY_FOR_SERVER_PREFLIGHT
            ↓
durable outbox + upload/preflight
       ├─ network failure → local retry; physical guidance 금지
       ├─ parser rejection → structured reason → guidance/retry
       └─ DELIVERY_CONFIRMED → success sound
            ↓
WAITING_FOR_PAGE_CHANGE
  ├─ same spread → do not resend
  └─ stable new spread → next capture cycle

button CANCEL at any active state
  → stop new work, cancel cancellable inference, preserve durable artifacts
  → IDLE
```

## 4. 한 frame에서 좌우를 함께 처리한다

기존 loop는 왼쪽을 먼저 처리·전송한 뒤 이후 frame에서 오른쪽을 처리한다. 사용자가 중간에
책을 움직이거나 페이지를 넘기면 서로 다른 spread의 좌우가 한 쌍이 될 수 있다.

영상 확장에서는 다음을 기본으로 한다.

- 안정된 full-spread frame 하나를 고해상도로 선택
- 그 동일 frame에서 spine seam 계산
- 좌우 crop과 UVDoc을 모두 생성
- `SpreadArtifact(left, right, source_frame_id)`로 묶음
- 좌우가 모두 준비됐을 때 같은 idempotent batch로 접수

한쪽만 실패했을 때 다른 frame의 한쪽과 임의로 조합하지 않는다. 새 full-spread frame에서
두 쪽을 다시 평가한다. 서버 API가 단일 페이지만 받더라도 Scanner 내부 lineage는 같은
spread ID를 유지한다.

## 5. 프레임 처리 전략

### 5.1 카메라는 유지하되 매 frame을 판정하지 않는다

연속 session은 애플리케이션이 카메라의 모든 frame을 판정한다는 뜻이 아니다. 실시간성이
핵심 요구가 아니므로 일정 주기로 최신 frame만 표본화한다.

- camera backend는 warm-up과 노출 안정화를 위해 열린 상태를 유지
- backend가 영상을 계속 생성하더라도 애플리케이션 queue에는 설정된 주기의 최신 frame만 넣음
- PC `VideoCapture`의 오래된 내부 buffer는 비우고 가장 최근 frame을 표본화
- timestamp와 monotonic frame ID를 붙여 짧은 bounded sample window에 보관
- 저해상도 preview에서 mask, seam, motion, blur, 노출을 계산
- 연속 K개 표본이 안정 조건을 만족할 때 그 window에서 가장 좋은 full-resolution frame을 선택
- 선택 frame만 crop/UVDoc/서버 preflight 대상으로 사용
- 실패하면 cooldown 뒤 다음 후보를 선택

초기 prototype 권고값은 검색 중 500 ms 간격, 3개 표본으로 약 1초 안정성을 확인하는 것이다.
이는 production 확정값이 아니며 Drive replay와 PC camera 측정으로 조정한다. 이 구조는 Pi 4에서
비싼 연산을 제한하면서도 버튼 순간의 우연한 frame 한 장에 의존하지 않는다.

### 5.2 후보 선택과 최종 판정을 분리한다

geometry/stability는 최종 통과 gate라기보다 candidate scheduler의 입력이다. 예를 들어 blur가
조금 높은 frame을 즉시 “전송 불가”로 고정하지 않고 최근 N개 중 더 선명한 frame을 고른다.

권장 candidate record:

```text
FrameCandidate
  frame_id, captured_at_monotonic
  full_resolution_handle
  left/right mask diagnostics
  seam diagnostics
  motion_score, sharpness_score, exposure_score
  physical_edge_contacts
  rank_score
  retry_reasons[]
```

### 5.3 안정 frame 판정과 선택

안정성은 “화질이 좋은가”와 분리한다. 다음 hard condition을 연속 K개 표본에서 먼저 확인한다.

- 좌우 page/spread 후보가 모두 존재
- 물리 frame 외곽 잘림 없음
- page mask IoU, bbox 중심·면적, spine seam 위치 변화가 허용 범위 안
- 정규화한 page ROI의 frame difference 또는 optical-flow motion이 허용 범위 안
- 손이나 넘어가는 종이처럼 넓은 변화 영역이 없음
- capture timestamp가 서로 달라 같은 stale frame 반복이 아님

hard condition을 통과한 window 안에서만 다음 순서로 한 frame을 고른다.

1. physical edge margin과 page-mask 보존
2. glare/black·white clipping이 적은 frame
3. shadow/illumination 불균형이 작은 frame
4. Tenengrad/Laplacian 등 선명도가 높은 frame
5. 동률이면 가장 최근 frame

가중합 하나로 잘림을 높은 선명도가 상쇄하게 하지 않는다. 각 metric의 수치 임곗값과 K는
현재 미검증이며 replay 결과를 보기 전에 provisional config로 표시한다. OCR 결과는 candidate
선택에 사용하지 않는다.

## 6. 상태 머신

권장 상태:

| 상태 | 의미 |
|---|---|
| `IDLE` | 카메라 loop 비활성 |
| `ARMING` | 카메라 warm-up, 설정 및 worker 준비 |
| `SEARCHING` | frame 수집·저비용 후보 평가 |
| `SETTLING` | 책/페이지 motion이 끝나기를 기다림 |
| `PROCESSING_CANDIDATE` | seam crop + UVDoc 실행 |
| `LOCAL_RETRY` | artifact gate 실패 후 다음 frame 대기 |
| `READY_FOR_SERVER_PREFLIGHT` | 로컬 artifact 준비 완료 |
| `UPLOADING` | outbox artifact 전송 중 |
| `REMOTE_RETRY` | 네트워크/서버 일시 오류 재시도 |
| `PARSER_REJECTED` | parser가 구조화된 이유로 거부 |
| `DELIVERY_CONFIRMED` | 서버 접수 확인, 완료음 발생 |
| `WAITING_FOR_PAGE_CHANGE` | 같은 spread 중복 방지 및 페이지 넘김 감시 |
| `CANCELLING` | worker 정리 중 |
| `ERROR` | 자동 복구 불가능한 장치/runtime 오류 |

`GuidanceEvent`, `CandidateProcessedEvent`, `UploadQueuedEvent`, `DeliveryConfirmedEvent`,
`PageChangeDetectedEvent`, `SessionCancelledEvent`처럼 관찰 가능한 event를 유지한다.

## 7. 전송 준비도 결과 타입

bool 대신 다음 정보를 가진 결과를 권장한다.

```text
ReadinessDecision
  state: RETRY_LOCAL | READY_FOR_PREFLIGHT | RETRY_REMOTE | ACCEPTED | FATAL
  reason_codes[]
  primary_guidance_action
  side_impacts: left | right | spread
  source_frame_id, spread_id, artifact_id
  metrics
  retry_after_ms
  artifact_paths + hashes
  evaluator_versions
```

필요한 reason 계층:

- acquisition: `CAMERA_UNAVAILABLE`, `FRAME_DECODE_FAILED`
- motion: `PAGE_MOVING`, `HAND_OR_PAGE_TURN`
- layout: `PAGE_NOT_FOUND`, `MOVE_LEFT`, `MOVE_RIGHT`, `MOVE_UP`, `MOVE_DOWN`,
  `ROTATE_CW`, `ROTATE_CCW`, `OUT_OF_FRAME`
- illumination: `UNDEREXPOSED`, `OVEREXPOSED`, `GLARE`, `SHADOW_UNEVEN`
- quality: `BLUR`, `INSUFFICIENT_RESOLUTION`, `WARP_ARTIFACT`
- correction: `SEAM_FAILED`, `UVDOC_FAILED`
- parser: `PARSER_QUALITY_REJECTED`, `STRUCTURE_PREFLIGHT_FAILED`
- transport: `NETWORK_UNAVAILABLE`, `SERVER_BUSY`, `AUTH_FAILED`, `UPLOAD_CORRUPT`

단순 `LOW_QUALITY` 하나로 합치면 사용자가 무엇을 조정해야 하는지 결정할 수 없다.

## 8. 사용자 가이드와 음성 정책

### 8.1 한 번에 하나의 행동만 안내

양쪽에 여러 문제가 있어도 다음 순서로 primary action 하나를 선택한다.

1. 책/페이지 없음
2. frame 밖 잘림과 위치 이동
3. 손·페이지 움직임
4. 심한 회전
5. 그림자·반사·노출
6. blur/focus
7. parser rejection

예:

- `MOVE_RIGHT`: “책을 오른쪽으로 조금 옮겨주세요.”
- `MOVE_UP`: “책을 위쪽으로 조금 옮겨주세요.”
- `PAGE_MOVING`: “잠시 손을 떼고 기다려주세요.”
- `SHADOW_UNEVEN`: “페이지 위 그림자를 줄여주세요.”

### 8.2 TTS flooding 방지

매 frame마다 같은 문장을 말하지 않는다.

- reason이 연속 K frame 또는 일정 시간 유지될 때만 안내
- 동일 문구 cooldown
- primary reason이 바뀌거나 악화될 때만 즉시 갱신
- `SEARCHING/SETTLING`은 짧은 비프음 또는 무음
- 위치·조명처럼 행동 가능한 경우에만 TTS
- network retry는 물리적 책 조정 안내와 분리
- 성공음은 spread당 한 번

### 8.3 비프음과 TTS 역할

- 비프음: loop 시작, 처리 중, 성공, 취소, 장치 오류처럼 언어가 필요 없는 상태
- TTS: 방향 이동, 그림자 제거, 페이지 펼침 등 구체적 행동
- PC prototype: console/event log + optional desktop audio
- Pi: buzzer/GPIO와 TTS adapter를 같은 `GuidanceSink` protocol 뒤에 둠

## 9. Scanner와 Document Parser의 책임

### Scanner가 가져야 할 책임

- 카메라와 버튼/GPIO
- frame buffer와 후보 선택
- 같은 frame의 좌우 소유권·crop
- 기본 경로인 UVDoc 실행 위치의 orchestration
- 물리 배치·motion·잘림 진단
- 사용자 안내와 세션 상태
- outbox, retry, idempotency key
- 원본/crop/보정본 provenance
- page change와 중복 전송 방지

### Document Parser가 가져야 할 책임

- 이미지 입력 contract의 authoritative validation
- OCR/VL, Page IR, 읽기 순서와 접근성 처리
- content/structure 수준의 accept/reject
- parser version과 reason code 반환
- job 저장·상태 조회

### 권장 책임 배치

판정 구현을 Scanner와 Document Parser 중 한곳에 통째로 넣지 않는다.

- Scanner: `ArtifactReadinessEvaluator`로 로컬 영상/기하 판단
- Document Parser server: `ParserPreflightEvaluator`로 실제 입력 계약 판단
- 둘 사이: versioned JSON schema인 `ParserAcceptanceResult`
- Scanner의 전송 client는 서버 결과를 세션 event와 사용자 guidance로 변환

Document Parser의 내부 Python 클래스를 Scanner가 직접 import해 권위를 복제하는 방식은
prototype에서는 가능하지만 장기적으로 version drift가 생긴다. 서버 preflight API가
authoritative source가 되는 편이 낫다.

## 10. 전송과 장애 복구

### 10.1 Durable outbox

로컬 artifact가 준비되면 먼저 outbox manifest와 파일을 원자적으로 저장한다.

- spread ID와 artifact hash 기반 idempotency key
- raw/crop/UVDoc lineage
- upload attempt와 last error
- server job ID와 accepted timestamp
- 전원 재부팅 후 재시도 가능

네트워크 오류는 새 촬영이나 책 위치 조정을 요구하지 않는다. 이미 좋은 artifact를 보존하고
같은 idempotency key로 재전송한다.

### 10.2 완료의 정의

단순 HTTP 연결 성공이나 request body 송신 완료를 완료로 보지 않는다.

최소 완료 조건:

- 서버가 hash를 확인하고 파일을 내구성 있게 저장
- 동일 idempotency key 중복 여부 처리
- parser preflight가 accept 또는 명시된 비동기 접수 상태 반환
- Scanner가 job ID를 outbox에 기록

가능하면 페이지를 넘기기 전에 빠른 parser preflight까지 끝낸다. 전체 OCR이 너무 느리면
완료음을 `INGEST_ACCEPTED`에 낼지 `PARSER_PREFLIGHT_ACCEPTED`에 낼지는 실제 지연시간을 측정해
결정한다. 기본 권고는 후자다.

## 11. 후보정 정책

UVDoc은 채택된 기본 경로지만 “모든 후보정은 항상 필수”라는 의미는 아니다.

권장 정책:

- 기본: `seam-conservative → UVDoc bilinear`
- raw와 unwarped crop은 항상 lineage로 보존
- UVDoc 실패를 조용히 none으로 대체하지 않음
- 명시적 fallback을 사용하려면 unwarped crop도 동일 Parser preflight를 통과해야 함
- fallback 사용 여부와 이유를 metadata에 기록
- sharpen/denoise/SR은 실제 parser 회귀 trigger가 있을 때만 별도 추가

Pi 4에서 UVDoc local inference가 허용 시간·메모리를 넘으면 다음 두 배치를 비교한다.

1. Scanner/Pi에서 seam crop까지, 서버에서 UVDoc + parser preflight
2. Scanner/Pi에서 UVDoc까지, 서버에서 parser preflight

정확도뿐 아니라 end-to-end 완료시간, peak RAM, 전력과 network payload를 측정해 위치를
결정한다. Pi 4 local UVDoc 가능 여부는 현재 완료로 표시하지 않는다.

## 12. 페이지 변경과 중복 방지

완료 직후 같은 spread가 카메라에 남아 있어도 다시 전송하면 안 된다.

- 성공한 좌우 crop의 perceptual hash/feature fingerprint 저장
- full-spread mask와 중심선 주변 변화량 감시
- 큰 motion 후 새로운 안정 구간이 나타나야 다음 후보 허용
- 새 후보가 직전 spread와 충분히 다를 때만 처리
- 가능하면 Parser가 반환한 page number/문서 fingerprint도 보조 사용

단순 file SHA-256은 같은 페이지의 재촬영을 구분하지 못하므로 중복 판정에 충분하지 않다.

## 13. PC와 Raspberry Pi 4 adapter

공통 protocol:

```text
CameraSource.start/read/stop
ButtonSource.events
GuidanceSink.emit
FrameProcessor.evaluate
ArtifactStore.commit
ParserClient.preflight_and_submit
```

PC prototype:

- OpenCV webcam 또는 플랫폼 camera backend
- 키보드/GUI 버튼 adapter
- console + WAV/TTS adapter
- local filesystem outbox

Raspberry Pi 4:

- Linux `libcamera`/Picamera2 기반 camera adapter 우선
- GPIO button과 debounce
- buzzer 또는 audio device adapter
- systemd service, graceful shutdown, journal logging
- 카메라 해상도·노출·focus 고정 가능 여부 실측

OpenCV `VideoCapture`는 PC prototype에는 충분하지만 Pi camera의 노출·buffer·고해상도 still
제어를 위해서는 전용 adapter가 필요하다.

## 14. 구현 순서

### Phase V0. 결정·계약 고정

상태: **2026-08-30 구현·검증 완료** (`SCANNER_VIDEO_V0_CONTRACT_WORK_PACKET.md`)

- 본 문서와 reason/state schema 확정
- 기존 loop를 `legacy`로 유지
- `seam-conservative + UVDoc` 기본 pipeline config 추가
- fake camera/button/guidance/parser client 작성

### Phase V1. PC sampled-frame engine

상태: **2026-08-30 V1/V1.1/V1.2 구현·PC 회귀 검증 완료**

- configurable cadence의 latest-frame sampler와 bounded sample window
- timestamp/frame ID
- start/cancel 상태 머신
- 저비용 candidate ranking
- 같은 full-spread frame에서 좌우 처리
- fake UVDoc로 orchestration test

### Phase V2. 실제 seam + UVDoc artifact

상태: **2026-08-30 구현·PC 영상 replay 검증 완료**

- 현재 오프라인 seam/ownership 코드를 runtime adapter로 연결
- UVDoc model process-wide lazy reuse
- 원본/crop/UVDoc atomic artifact bundle
- local artifact readiness와 diagnostics
- 실제 PC 영상 replay와 webcam 검증

### Phase V3. Guidance와 page change

상태: **V3-A/V3-A.5 identity·single in-flight·ACK bank·M1 page-change 구현 완료; 실제 TTS/device adapter는 후속**

- reason aggregation, hysteresis, cooldown
- 방향성 guidance
- 비프/TTS sink
- 성공 후 같은 spread 중복 방지
- 다음 페이지 안정화 자동 재개

V3-A.5 기본 중복 전략은 좌우 bottom ROI의 opaque raw OCR pair(M1)다. 기본값은 native preview,
100ms, N=5, `K_same=1/K_diff=0`, `validated=false`이다. SAME은 seam/UVDoc 전에 억제하고,
DIFFERENT만 V2로 보낸다. 서버 ACK 전 bank는 pending이며 reject/cancel 시 폐기한다. 현재 p30/p316
두 spread에서만 후보 선발이 이뤄졌으므로 일반화 검증, N=10, Pi 4 성능은 완료가 아니다.

### Phase V4. Server preflight와 outbox

- versioned acceptance API 협의
- atomic outbox와 idempotent upload
- network/server retry 분리
- 완료 ack와 job 상태
- parser reject reason을 guidance로 매핑

### Phase V5. Raspberry Pi 4

- Picamera2/libcamera adapter
- GPIO/button/buzzer
- local seam/UVDoc 및 server UVDoc A/B benchmark
- systemd와 전원 장애 복구
- 실제 장비 end-to-end 측정

각 Phase는 별도 승인 패킷으로 구현한다. 승인된 첫 구현 묶음은 다음처럼 분리했다.

- V0: `SCANNER_VIDEO_V0_CONTRACT_WORK_PACKET.md`
- V1: `SCANNER_VIDEO_V1_FRAME_ENGINE_WORK_PACKET.md`
- V2: `SCANNER_VIDEO_V2_SEAM_UVDOC_ARTIFACT_WORK_PACKET.md`

V0~V3-A.5의 Scanner 로컬 경로를 완료했다. 다음 구현 우선순위는 Server S0 persistent catalog,
Server S1 incremental append·seal, Scanner V3-B + Server V4 durable outbox·HTTP ingest,
STM/camera/audio/Pi 4 device integration이다. M1 held-out 검증은 병행 backlog로 유지한다.

## 15. 검증 기준

PC prototype 최소 기준:

- 버튼 시작/취소가 deterministic
- 카메라 frame producer가 취소 후 자원을 해제
- 같은 full-spread frame에서 좌우 artifact 생성
- 한쪽 실패 시 서로 다른 frame의 좌우를 섞지 않음
- artifact 실패 후 loop가 다음 frame으로 회복
- 같은 페이지 중복 전송 0
- guidance가 frame rate로 반복되지 않음
- upload 실패가 물리 guidance를 발생시키지 않음
- outbox 재시작 복구와 idempotent resend
- 서버 ack 전 성공음 0
- 원본/crop/UVDoc hash lineage 100%

Pi 4 완료 기준은 실제 장비에서 별도로 측정한다.

- camera 장시간 안정성
- candidate 처리 FPS
- UVDoc 위치별 latency/peak RAM
- 버튼·음향 응답
- network 단절·복구
- 페이지 넘김 연속 세션

## 16. 현재 미결정 사항

- UVDoc을 Pi에서 실행할지 서버에서 실행할지
- 완료음을 ingest ack와 parser preflight ack 중 어디에 연결할지
- 양쪽 중 하나만 parser reject일 때 전체 spread를 재촬영할지 한쪽 artifact를 보존할지
- parser preflight의 정확한 동기 실행 범위와 latency budget
- camera sensor, 해상도, focus/노출 제어 방식
- TTS engine과 오프라인 한국어 음성 asset
- Pi 4 허용 대기시간과 전력 예산
- accepted artifact와 raw 원본의 보존 기간

이 항목은 측정이나 서버 contract 없이 임의로 확정하지 않는다.

## 17. 기존 구현에 대한 판정

보존:

- `CaptureSource` 추상화
- generator/event 기반 세션 관찰 방식
- raw/corrected hash와 atomic write 원칙
- 얇은 transmit client 경계
- 실패 reason을 guidance로 변환하는 책임 분리
- 기존 테스트와 legacy loop

교체 또는 확장:

- 첫 frame을 빈 배경으로 강제하는 흐름
- background subtraction + minAreaRect 기본 검출
- geometry/stability 통과 전 artifact를 만들지 않는 단일 동기 loop
- 왼쪽 전송 후 다른 frame에서 오른쪽 처리
- `TransmitBlockReason`의 지나치게 넓은 `LOW_QUALITY`
- 성공 뒤 즉시 같은 spread를 다시 처리할 수 있는 상태
- 메모리 내 단발 upload만 있고 durable outbox가 없는 구조

현재 코드를 즉시 삭제하지 않는다. 새 영상 engine이 replay test와 PC webcam에서 검증될 때까지
legacy 경로를 비교 기준으로 유지한다.
