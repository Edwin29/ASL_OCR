# Scanner Video V3-A.1 — Bottom ROI Page Number Identity 작업 패킷

상태: **승인·부분 구현 — production recognizer 선발 gate 미통과**
작성일: 2026-08-31
선행 조건: V2 `seam-conservative + UVDoc bilinear` atomic artifact, V3-A local identity·single in-flight·page-change gate
후속 조건: Integration V0 coordinator 연결, V3-B durable outbox·HTTP 전송, V4 Document Parser spread ingest

## 1. 배경

V3-A의 visual identity는 서로 다른 페이지를 중복으로 버리지 않도록 보수적으로 구현됐다.
사용자가 동일 p30 촬영이라고 확인한 세 spread의 세 pair 중 한 pair만
`VISUAL_DUPLICATE`, 두 pair는 `AMBIGUOUS`였다. 임곗값을 완화해 이 결과만 통과시키면 서로
다른 교재 페이지를 중복으로 오인할 위험이 있다.

본 프로젝트는 카메라와 펼친 교재의 구도가 고정되고, 페이지 번호가 통상 페이지 바깥쪽
하단에 존재한다. 전체 Document Parser를 호출해 페이지 번호를 얻으면 로컬 page-change 및
중복 판정이 서버 OCR 완료에 종속된다. V3-A.1은 Scanner가 좌우 페이지의 하단 외곽 ROI만
경량 인식해 page number를 주 identity로 사용하고, 기존 visual identity를 fallback 및 충돌
검출 근거로 재배치한다.

V3-A.1 완료는 일반 문서 OCR, 서버 저장 중복 방지, 재부팅 후 중복 방지 또는 모든 교재의
페이지 번호 형식 지원 완료를 뜻하지 않는다.

## 2. 목표

- 전체 페이지 OCR 없이 좌우 페이지 번호 후보를 로컬에서 추출
- 보정된 V2 artifact에서 전송 전 authoritative local `SpreadPageKey` 생성
- ACK 이후 저비용 preview ROI 관찰로 같은 페이지 유지와 페이지 변경 후보를 구분
- 같은 datapack에서 같은 좌우 page key의 중복 전송 요청을 억제
- 번호 미검출·부분 검출·visual 충돌을 명시적으로 fallback 또는 `AMBIGUOUS` 처리
- recognizer를 session 동안 한 번만 load하고 표본 주기 및 ROI cache로 반복 비용 제한
- page number observation과 최종 parser 결과를 후속 Integration에서 대조할 수 있는 계약 제공

## 3. 범위와 전제

### 3.1 고정 구도 전제

- 입력은 위에서 내려다본 펼친 양면 교재다.
- left/right는 같은 source frame의 seam 기준으로 구분된다.
- V2 corrected page는 읽는 방향으로 정렬된 좌우 개별 이미지다.
- 페이지 번호는 우선 Arabic digit 1~4자리만 지원한다.
- 왼쪽 페이지 번호는 좌하단 외곽, 오른쪽 페이지 번호는 우하단 외곽을 우선 탐색한다.
- 좌우 번호의 연속성, 홀짝, 증가 방향은 판정 근거로 사용하지 않는다.

p30/p309처럼 좌우 번호가 연속되지 않은 실제 spread도 정상 key여야 한다. 페이지 번호가 없는
표지·간지·목차, Roman numeral, 부록별 중복 번호는 V3-A visual fallback 또는 후속 확장 범위다.

### 3.2 Datapack scope

페이지 번호만으로 전역 identity를 만들지 않는다.

```text
SpreadPageKey = (
    schema_version,
    data_pack_id,
    left_page_label,
    right_page_label,
    recognizer_version,
)
```

- `data_pack_id`가 같을 때만 page number duplicate를 판단한다.
- coordinator가 datapack을 아직 확정하지 못한 단계에서는 session-local namespace를 사용한다.
- datapack context가 없는 key를 다른 session/datapack의 accepted key와 비교하지 않는다.
- 좌우 순서를 보존하며 `(30, 309)`와 `(309, 30)`은 다르다.

## 4. 두 종류의 관찰 경로

### 4.1 Corrected artifact ROI — 전송 전 로컬 확정

V2 atomic commit 뒤 `left/uvdoc.jpg`, `right/uvdoc.jpg`에서 각각 하단 외곽 ROI를 추출한다.
초기 configurable ROI는 다음과 같다.

| side | x 범위 | y 범위 |
|---|---:|---:|
| left | 0.00~0.35 | 0.80~1.00 |
| right | 0.65~1.00 | 0.80~1.00 |

비율은 p30 및 추가 라벨 자료의 overlay로 검증한 뒤 고정한다. ROI 밖의 본문을 OCR backend에
전달하지 않는다. corrected observation은 V3-A visual identity와 함께 최종 local identity
fusion에 사용한다.

### 4.2 Preview ROI — ACK 이후 page-change hint

`WAITING_FOR_PAGE_CHANGE`에서는 V2 preparer와 UVDoc을 호출하지 않는다.

1. 기존 preview page mask와 seam으로 좌우 page 영역을 나눈다.
2. 각 page mask bounding region의 바깥쪽 하단 비율 ROI를 구한다.
3. mask 밖 배경은 제거하고 중간 해상도 grayscale ROI만 recognizer에 전달한다.
4. 같은 번호 관찰이 연속 표본에서 합의될 때만 stable observation으로 인정한다.
5. 번호가 읽히지 않거나 conflict이면 기존 V3-A visual page-change gate로 fallback한다.

preview observation은 artifact page number를 대체하는 authoritative identity가 아니다. preview
번호 변화는 candidate 수집 재개 근거이며, V2 artifact 생성 후 corrected ROI에서 다시 확인한다.

## 5. ROI 추출 및 숫자 후보

ROI extractor는 OpenCV/NumPy 경로로 구현한다.

- grayscale 및 제한된 CLAHE
- Otsu와 adaptive threshold 후보를 별도 variant로 생성
- mask 밖 배경 제거
- 작은 border/noise component 제거
- 같은 baseline에 놓인 1~4개 glyph 후보를 sequence로 묶음
- left는 외곽의 왼쪽 numeric sequence, right는 외곽의 오른쪽 numeric sequence를 우선
- 원본 ROI 좌표계 bbox, 전처리 variant, ROI hash를 observation에 보존

component 크기 하나만으로 page number를 확정하지 않는다. 위치, baseline/간격, recognizer
결과, variant 간 합의가 함께 있어야 한다. 본문의 문제 번호나 footer의 연도·단원 번호가 page
number로 선택되지 않는지 overlay로 검증한다.

ROI가 너무 잘렸거나 active mask가 부족하면 숫자를 추측하지 않고 명시적 `NOT_OBSERVED`를
반환한다.

## 6. Recognition backend 선발 gate

현재 `book-scanner` 기본 의존성에는 범용 OCR 또는 경량 digit recognizer가 없다. V3-A.1은
Document Parser의 PaddleOCR-VL/전체 layout pipeline을 import하거나 호출하지 않는다.

production backend는 다음 계약을 만족해야 한다.

```python
class PageNumberRecognizer(Protocol):
    engine_id: str
    engine_version: str

    def recognize(
        self,
        roi: np.ndarray,
        side: PageSide,
    ) -> PageNumberRecognition:
        ...
```

필수 조건:

- text detector 없이 prelocalized ROI에 recognition만 수행
- 출력 vocabulary는 `0`~`9`로 제한
- 모델/엔진은 session 동안 한 번만 load
- CPU 실행 가능, 네트워크 호출 없음
- runtime 중 자동 모델 다운로드 없음
- 모델을 사용할 경우 asset path, SHA-256, license/provenance, input normalization을 manifest에 기록
- confidence가 없는 backend 결과를 임의의 `1.0`으로 가장하지 않음

구현 시작 시 실제 corrected/preview ROI corpus로 다음 후보를 동일 runner에서 비교한다.

1. OpenCV segmentation + deterministic numeric recognition baseline
2. offline persistent recognition-only 경량 backend

특정 패키지나 모델은 pilot 측정 전에 production 기본값으로 고정하지 않는다. backend 선발
보고서에는 cold load, warm latency, 좌우 정확도, abstention, peak memory와 dependency 크기를
기록한다. 어떤 후보도 정확도·속도 gate를 만족하지 못하면 전체 OCR로 조용히 확대하지 않고
중단 조건으로 보고한다.

## 7. Page number 계약

예상 production type은 다음 의미를 보존한다.

```text
PageNumberObservation
  side
  raw_text
  normalized_label       # leading zero 제거 후 "1"~"9999", 실패 시 None
  confidence             # backend confidence; 없으면 None
  bbox                    # 해당 ROI 원본 좌표
  roi_sha256
  source_kind             # corrected | preview
  source_frame_id
  artifact_id             # corrected인 경우
  engine_id/version
  preprocessing_version
  status                  # observed | not_observed | invalid | conflict

SpreadPageNumberObservation
  left
  right
  consensus_count
  key | None
  status                  # complete | partial | missing | conflict
```

- 원문과 normalized label을 모두 보존한다.
- 빈 문자열, 음수, 소수, 수식 token은 page label이 아니다.
- `000`, `0`, 5자리 이상은 기본 범위에서 invalid다.
- confidence threshold와 consensus K는 config에 두고 `validated=false`로 시작한다.
- 로그에는 작은 ROI image/base64를 넣지 않고 label, confidence, bbox, version만 기록한다.

## 8. Consensus와 identity fusion

### 8.1 Corrected artifact

하나의 corrected ROI에서도 grayscale/Otsu/adaptive 등 둘 이상의 전처리 variant가 같은 숫자에
합의해야 high-confidence 후보가 된다. backend confidence 단독으로 확정하지 않는다.

V3-A visual comparison과 결합 규칙은 다음과 같다.

| page number evidence | visual evidence | 결과 |
|---|---|---|
| same complete key | exact/visual duplicate | `PAGE_KEY_DUPLICATE` |
| same complete key | visual ambiguous | provisional 기간에는 `PAGE_KEY_DUPLICATE_CANDIDATE` |
| same complete key | visual new spread | `IDENTITY_CONFLICT` |
| different complete key | new/ambiguous | `NEW_SPREAD` |
| different complete key | exact/visual duplicate | `IDENTITY_CONFLICT` |
| partial/missing | exact/visual duplicate | 기존 V3-A duplicate 규칙 |
| partial/missing | ambiguous | `AMBIGUOUS` |

`PAGE_KEY_DUPLICATE_CANDIDATE`를 자동 억제로 승격하는 것은 labeled false-duplicate gate 통과
뒤에만 허용한다. 검증 전에는 visual conflict를 무시하고 번호만으로 artifact를 버리지 않는다.

### 8.2 Preview page-change

- accepted baseline과 같은 complete key가 관찰되면 변화 stable count를 reset하고 계속 대기
- accepted baseline과 다른 complete key가 연속 K회 관찰되고 candidate hard gate도 통과하면
  page-change 후보 확정
- 한쪽만 읽힌 경우 그 한쪽의 변화만으로 release하지 않고 visual pair-change 합의를 요구
- 숫자 observation이 missing/conflict이면 기존 visual gate가 계속 책임짐
- 손 가림, `PAGE_MOVING`, blur, 한쪽 page mask 누락 표본은 consensus에 포함하지 않음
- 한 표본의 `30 → 80 → 30` 같은 spike는 page change가 아님

page-change 확정 후에도 corrected artifact page number가 이전 key와 같으면 중복 전송을 억제하고
preview 오해제 진단 event를 남긴다.

## 9. Cache와 메모리 경계

페이지 번호 인식 cache는 bounded in-memory LRU로 둔다.

- key: recognizer/preprocess version + side + source kind + normalized ROI hash
- value: immutable observation과 처리시간
- 기본 capacity 후보: 32 observations, 실제 측정 전 provisional
- exact ROI hash hit는 recognizer 재호출 없이 결과 재사용
- perceptual-near cache hit는 자동 확정하지 않고 diagnostics로만 기록
- full frame, corrected page 또는 ROI pixel array는 cache에 보관하지 않음
- session/datapack 변경 시 preview consensus와 cache namespace를 분리
- accepted page key는 V3-A ledger metadata에 결합하되 durable 저장은 V3-B 범위

## 10. Engine 및 Integration 경계

예상 파일 경계:

```text
src/book_scanner/video/
  page_number.py           # observation/key/fusion/cache
  page_number_roi.py       # corrected/preview side ROI
  page_number_recognizer.py# backend protocol 및 선택된 adapter
  config.py                # ROI, consensus, cache, provisional confidence
  protocols.py             # recognizer/key provider 계약
  events.py                # observation/conflict/cache event
  engine.py                # V3-A identity 및 page-change 우선순위 연결
```

최소 event 또는 동등한 구조화 details를 제공한다.

- `PAGE_NUMBER_OBSERVED`
- `SPREAD_PAGE_KEY_CREATED`
- `PAGE_NUMBER_CACHE_HIT`
- `PAGE_NUMBER_IDENTITY_CONFLICT`
- `PAGE_CHANGE_NUMBER_EVIDENCE`

Coordinator는 `data_pack_id`를 Scanner session context에 주입한다. Document Parser 전체 OCR은
V3-A.1 호출 경로에 포함하지 않는다. 후속 서버 응답이 확정 page number를 반환하면 local
observation과 비교하되, 불일치를 조용히 overwrite하지 않고 reconciliation event로 남긴다.

기존 `session/`, `judge/`, `transmit/` public API와 Integration V0의 delivery lifecycle 의미는
변경하지 않는다.

## 11. 구현 단계

### Phase 0 — Ground truth와 backend audit

- p30 세 corrected artifact의 좌우 page number label manifest 작성
- 실제 MP4의 clean representative 및 hand/page-moving 표본에서 preview ROI 추출
- 추가 라벨 이미지가 있으면 page number와 `not_visible`을 구분해 기록
- backend availability, asset provenance, cold/warm 비용 점검

사람이 확인하지 않은 OCR 출력을 ground truth로 다시 사용하지 않는다.

### Phase 1 — ROI 및 offline pilot

- side-aware corrected/preview ROI extractor 구현
- ROI overlay와 numeric candidate overlay 생성
- backend adapter와 fake recognizer 구현
- 동일 corpus에 후보 backend 실행
- 정확도·abstention·latency·memory 보고 후 한 backend만 production default 후보로 선택

### Phase 2 — Identity fusion 및 cache

- observation/key immutable type과 normalization
- preprocessing variant agreement
- bounded cache
- V3-A ledger match와 page-number/visual fusion
- conflict·missing·partial 처리 및 event

### Phase 3 — Page-change engine 연결

- ACK 이후 sampling cadence에 preview ROI observation 연결
- stable consensus와 invalid frame reset
- 번호 변화 우선, visual fallback
- corrected ROI 재확인 뒤에만 새 artifact 전송 요청 허용

### Phase 4 — Replay·회귀·보고

- labeled image 및 MP4 replay
- 같은 페이지 duplicate, 다른 페이지, 손 가림, page-moving, 숫자 spike 검증
- 전체 Book Scanner unit 회귀
- PC latency/cache hit/peak memory 보고
- 실제 검증하지 않은 Pi 수치는 미완료로 기록

## 12. 검증 행렬

### 12.1 ROI 및 recognizer

- p30 corrected left ROI가 `30`, right ROI가 확인된 실제 번호를 포함
- 동일 p30 세 촬영의 corrected observation이 같은 key
- left/right ROI를 바꾸면 같은 key로 취급하지 않음
- footer의 연도·단원·문제 번호를 page number로 선택하지 않음
- 밝기/JPEG/작은 translation variant에서 결과 또는 안전한 abstention
- ROI 잘림, 번호 없음, 빈 mask는 `NOT_OBSERVED`
- recognizer load count는 session당 1
- full page image가 recognizer 입력으로 들어가지 않음

### 12.2 Identity 및 lifecycle

- 같은 datapack + 같은 complete key + 일치 visual은 중복 전송 요청 0
- 다른 datapack + 같은 번호는 중복 억제하지 않음
- 같은 key + visual new는 conflict이며 자동 삭제 0
- 다른 key + visual duplicate는 conflict이며 자동 전송/삭제 0
- partial/missing은 visual fallback
- stale ACK/reject 및 repeated confirm의 V3-A 불변식 유지

### 12.3 Page-change replay

- ACK 뒤 같은 번호가 유지되면 artifact 추가 생성 0
- 다른 complete key의 안정 K 표본 뒤 `PAGE_CHANGED` 1회
- 한 표본 OCR spike는 release 0
- 한쪽 숫자만 변경됐을 때 visual pair 합의 없이는 release 0
- hand/page-moving/blur frame은 stable consensus에 포함되지 않음
- page-change 후 corrected key가 baseline과 같으면 전송 요청 억제
- 번호 미검출 구간에서 기존 visual fallback이 유지됨

### 12.4 성능 및 회귀

- Document Parser/PaddleOCR-VL import 및 호출 0
- preview에서 UVDoc 호출 0
- warm 좌우 ROI recognition latency와 sampling duty cycle 기록
- cache hit 시 recognizer 호출 0
- cache가 full-resolution pixel array를 보유하지 않음
- 전체 Book Scanner unit test 회귀 없음
- Pi 4 latency/RSS는 실제 장치 측정 전 완료로 표시하지 않음

PC provisional 목표는 warm 좌우 ROI 처리 median 50ms 이하, p95 100ms 이하다. 이 값은 backend
선발을 위한 초기 budget이며 Pi 4 성능 보증이 아니다. 목표를 만족하지 못해도 측정값을 숨기거나
샘플을 제외하지 않는다.

## 13. 완료 기준

- side-aware corrected 및 preview ROI extractor 구현
- digits-only persistent recognizer backend 하나를 근거와 함께 선택
- p30 세 촬영에서 사람이 확인한 좌우 page label 재현
- versioned `SpreadPageKey`와 datapack scope 구현
- page number 우선 + visual fallback/conflict fusion 구현
- ACK 이후 page number consensus page-change gate 구현
- 같은 key의 새 전송 요청 억제와 번호 실패 fallback test 통과
- backend load count, warm latency, cache hit, peak memory 기록
- 전체 Book Scanner unit 회귀 통과
- threshold/backend/자료가 부족한 항목은 provisional 또는 blocked로 기록

`validated=true`는 확인된 same-page positive와 different-page negative를 분리해 false duplicate를
평가한 뒤에만 허용한다. p30 한 spread만 맞춘 결과로 일반 페이지 번호 identity를 완료 처리하지
않는다.

## 14. 비범위

- Document Parser 전체 OCR 또는 layout model 실행
- 서버 HTTP endpoint, DB schema, receipt/idempotency 구현
- SQLite durable outbox와 process restart recovery
- 범용 문서의 page number 위치 탐색
- Roman numeral, 한글 페이지명, 부록별 복합 page label
- 페이지 번호가 없는 문서의 semantic identity
- 대규모 수동 라벨링 또는 새 범용 OCR 학습
- ROI 인식을 이유로 seam/crop/UVDoc threshold 재튜닝
- Pi camera/GPIO/TTS 배포

## 15. 중단 조건

다음이 발생하면 범위를 조용히 확대하거나 임곗값을 즉석 변경하지 않고 보고한다.

- p30 또는 검증 대상의 실제 page number가 선언한 하단 외곽 ROI에 안정적으로 포함되지 않음
- 정확한 번호 인식을 위해 전체 페이지 text detection 또는 Document Parser 호출이 필요함
- 후보 backend가 runtime 자동 다운로드나 출처 불명 모델을 요구함
- high-confidence false page number가 confirmed negative에서 발생함
- 같은 key와 visual `NEW_SPREAD` 충돌을 자동 duplicate로 강제해야 함
- preview 번호 인식이 손/페이지 이동 frame을 stable page로 반복 승인함
- 성능을 맞추기 위해 frame/artifact lineage 또는 좌우 동시성 불변식을 깨야 함
- datapack scope 없이 전역 page-number dedup을 해야 함

중단 시 ROI/recognizer 실측, 실패 표본, 필요한 추가 라벨 또는 다음 설계 선택지를 보고하고 승인을
다시 받는다.

## 16. 승인 후 예상 산출물

- production 코드와 unit/replay test
- 사람이 확인한 page-number label manifest
- corrected/preview ROI 및 candidate overlay
- backend 선발 비교표와 asset manifest
- identity fusion 및 page-change replay summary JSON
- PC latency/cache/memory 결과
- `SCANNER_VIDEO_V3_A_1_IMPLEMENTATION_REPORT.md`
