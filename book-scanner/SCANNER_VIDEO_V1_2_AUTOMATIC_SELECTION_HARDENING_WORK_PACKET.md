# Scanner Video V1.2 — 자동 전송 후보 선택 보강 작업 패킷

상태: **승인 — 구현 진행 중 (영상 development anchor 12개 확정, held-out 미검증)**
작성일: 2026-08-30
선행 조건: V1.1 sampled-frame engine, V2 `seam-conservative + UVDoc bilinear` artifact 경로

## 1. 배경과 현재 사실

실제 `20260830_133526.mp4`를 500ms 간격으로 재생한 기본 V1 결과는 자동 stable 선택 0건이다.

- 90개 표본 중 후보 직접 사유는 `OUT_OF_FRAME` 82건,
  `PAGE_NOT_FOUND + SEAM_FAILED` 8건이었다.
- `OUT_OF_FRAME`만 진단으로 강등해도 현재 motion 정책에서는 stable 0건이었다.
- 같은 영상에 맞춰 `max_motion_fraction`을 시험적으로 완화하면 정지한 손이 본문 하단을
  가린 프레임도 통과할 수 있었다.
- 13.07초와 37.19초는 Codex가 진단용으로 먼저 제안했고, 이후 사용자가 원본 프레임을
  직접 확인해 두 프레임 모두 `CLEAN_TRANSFERABLE`로 확정했다. 따라서 두 프레임은
  positive anchor로 사용하되, 사용자가 처음부터 선택했다는 식으로 기록하지 않는다.

따라서 문제를 단순 임계값 완화로 해결하지 않는다. `물리 잘림`, `시간적 안정성`,
`정지 물체에 의한 본문 가림`을 서로 다른 신호와 실패 사유로 분리한다.

## 2. 목표

고정된 상부 카메라·검은 배경·양면 펼침 구도에서 다음 계약을 만족하는 자동 선택기를 만든다.

1. 사용자가 확인한 clean stable 구간에서는 bounded window 안에서 최소 한 프레임을 선택한다.
2. 페이지 이동·넘김·손의 본문 가림 구간에서는 프레임을 선택하지 않는다.
3. mask가 frame 경계에 닿았다는 사실만으로 페이지 잘림을 확정하지 않는다.
4. 전역 노출 변화와 작은 카메라 진동을 페이지 이동으로 과대평가하지 않는다.
5. 선택된 원본 full-resolution frame만 기존 V2 preparer에 전달한다.

V1.2 완료는 로컬 자동 선택 보강을 뜻한다. Document Parser 서버 전송 성공이나 Raspberry Pi
성능 검증을 뜻하지 않는다.

## 3. 정답 자료와 평가 분리

### 3.1 사용자 확인 anchor set

현재 영상에서 12개의 대표 원본 프레임을 추출해 manifest와 contact sheet를 만들었고 사용자가
다음 label로 모두 확정했다.

- `CLEAN_TRANSFERABLE`: 양쪽 본문이 보이고 손이 본문을 가리지 않으며 책이 정지
- `PAGE_MOVING`: 책 위치 조정 또는 페이지가 움직이는 중
- `HAND_CONTENT_OCCLUSION`: 정지 여부와 무관하게 손/물체가 본문을 가림
- `LAYOUT_INVALID`: 페이지가 실제로 잘렸거나 한쪽 페이지를 찾을 수 없음
- `AMBIGUOUS`: 정답으로 사용하지 않음

확정 분포는 `CLEAN_TRANSFERABLE` 3개(720, 780, 2220),
`HAND_CONTENT_OCCLUSION` 7개, `PAGE_MOVING` 2개다.
이 12개 anchor는 threshold 학습용 대량 데이터가 아니라 development 회귀·검증 근거로만
사용한다.

정적 p30 이미지 `20260830_104447.jpg`는 사용자가 분류 결정을 위임했고, 원본 해상도에서
본문 문제 1~4와 footer가 보존됨을 확인해 `CLEAN_TRANSFERABLE`로 정했다. 종이 외곽선이
frame에 닿는 것과 OCR 대상 본문이 잘리는 것을 같은 label로 취급하지 않는다.

### 3.2 development와 held-out

- 현재 MP4: 구현·오류 재현용 development replay
- 기존 그림자/오배치 이미지: layout/illumination 보조 negative
- 별도의 후속 영상: held-out replay

현재 MP4에 맞춰 계산된 threshold를 곧바로 `validated=True` production 기본값으로 만들지 않는다.
held-out 영상이 없으면 구현 상태는 `PROVISIONAL_AWAITING_HELD_OUT_VIDEO`로 남긴다.

## 4. 구현 범위

### 4.1 Frame-edge contact와 실제 잘림 분리

현재 `PageMask.touches_outer_frame`은 diagnostic으로 보존하되 단독 hard gate에서 제외한다.
preview 후보 단계는 다음 신호를 별도로 기록한다.

- 좌우 page mask의 top/bottom/outer 접촉 방향
- 페이지 외부에서 확인되는 검은 배경 band
- 외곽 contour가 frame 경계에서 종료되는 길이와 비율
- 인쇄 content bbox가 frame 경계에서 잘리는지 여부
- page mask confidence와 contour/ROI 누출 징후

페이지 외곽 접촉과 edge-strip 잉크가 함께 있어도 preview 단계에서는 clipping 후보 신호로만
기록한다. `104447`에서 이 조합이 실제 본문 잘림 없이 발생했기 때문이다. 검증된 본문 잘림
근거가 없으면 `OUT_OF_FRAME` hard reason을 만들지 않고 V2 full-resolution readiness가 다시
검사할 기회를 준다. 본문이 보존된다면 좌우 crop 크기의 동일성을 요구하지 않는다.

### 4.2 노출·미세진동에 강한 motion

현재 프레임별 histogram equalization 뒤 raw pixel difference를 hard gate로 쓰는 경로를
대체하거나 진단으로 강등한다.

인접 sampled preview마다 다음 순서를 적용한다.

1. 공통 page support 영역 계산
2. page 내부 percentile/median 기반 광도 정규화
3. 허용 범위가 제한된 translation/affine 정렬
4. blur pyramid에서 residual motion 계산
5. 전체 residual, 최대 connected residual, mask IoU, centroid/area/seam shift 기록

정렬이 실패하거나 추정 이동량이 허용 범위를 넘으면 안정으로 가장하지 않고
`PAGE_MOVING`으로 처리한다. 손·페이지 넘김은 큰 connected residual로 분리하고, 전역 노출
변화는 별도 diagnostic으로 남긴다. 기존 metric도 A/B 비교를 위해 기록한다.

### 4.3 정지 손·물체에 의한 본문 가림

시간적 motion만으로 정지 손을 검출할 수 없으므로 `ObstructionDetector` 경계를 추가한다.
검출 결과는 최소 다음 정보를 가진다.

- obstruction 존재 여부와 confidence
- page side
- obstruction mask/bbox
- 추정 content 영역과의 overlap
- detector/version/runtime provenance

손이나 물체가 검출되어도 페이지 외부 또는 안전 여백에만 있으면 warning으로 둘 수 있다.
본문·수식·선택지 영역과 겹치면 `CONTENT_OCCLUDED` hard reason으로 거부한다.

사용자가 배포를 계획하지 않고 지연·리소스를 우선 고려하라고 지정했으므로 구현 우선순위는
다음과 같이 확정한다.

1. 고정 카메라·검은 배경을 이용한 model-free edge ingress 알고리즘
2. 저해상도 경량 hand detector는 비교·fallback 후보
3. 모델/checkpoint를 사용할 경우 출처, SHA-256, 입력 크기와 runtime을 고정
4. runtime network 의존과 자동 다운로드 금지

채택한 `edge-chroma intrusion`은 피부색 계열 연결요소가 frame 경계에서 시작하고 page mask
근방으로 침입하는지를 640px preview에서 판정한다. 이는 partial finger도 처리하고 모델 메모리와
추론 의존성이 없다. 현재 12개 anchor에 맞춘 threshold이므로 held-out 피부색·조명·갈색 배경에서
오탐/누락을 확인하기 전에는 production 성공으로 포장하지 않는다. 사용자 anchor를 학습 데이터로
사용하지 않는다. MediaPipe는 비교용 선택지로만 유지한다.

### 4.4 Stable window와 best-frame 선택

stable window는 다음을 모두 만족한 관측치만 eligible로 본다.

- page pair 및 seam proxy 존재
- 검증된 OCR 본문 clipping 없음(edge 접촉 proxy만으로 reject하지 않음)
- 정렬 후 geometry/residual motion 안정
- content obstruction 없음
- stale/duplicate frame 아님

첫 stable 판정을 즉시 전송하지 않고 bounded window 안에서 다음 순위로 원본 프레임을 고른다.

1. 검증된 content clipping/obstruction hard gate
2. 낮은 residual motion과 높은 mask/seam 일관성
3. 본문을 보존하는 physical margin
4. blur/exposure/glare diagnostic
5. 최신 timestamp는 최종 tie-breaker

선택 이후 V2 local retry가 발생하면 같은 이미지를 반복하지 않고 cooldown 뒤 새 sampled window를
구성한다. V1 preview mask를 V2 final crop에 재사용하지 않는다.

### 4.5 Replay와 provenance

`tools/run_scanner_video_v1_2_selection_replay.py`를 추가해 다음을 한 번에 기록한다.

- 원본 video hash/metadata와 정확한 forward-decoded frame index
- 각 표본의 candidate hard reason/warning/metric
- stable window 판정과 best-frame 선택 근거
- anchor label과 predicted state의 비교
- 선택된 frame의 V2 준비 결과와 동일-frame lineage
- false accept, false reject, recovery time

OpenCV 임의 timestamp seek는 현재 MP4 후반부에서 실패했으므로 평가 도구는 순차 decode만
사용한다.

## 5. 예상 변경 파일

```text
src/book_scanner/video/
  config.py              # provisional edge/motion/obstruction policy
  candidate.py           # contact diagnostic, registered motion, stable ranking
  obstruction.py         # detector protocol 및 선택된 adapter
  types.py               # CONTENT_OCCLUDED 등 명시적 reason/metric
  engine.py              # eligible window/retry 경계가 필요할 때만 최소 수정

tools/
  run_scanner_video_v1_2_selection_replay.py

tests/unit/video/
  test_candidate.py
  test_obstruction.py
  test_engine.py
  test_video_v1_2_replay.py
```

기존 `session/`, `judge/`, `transmit/`, V2 seam/UVDoc public 계약은 변경하지 않는다.

## 6. 검증 행렬

### 6.1 Frame-edge

- 검은 배경 주름 때문에 mask만 상·하단에 닿는 현재 stable 화면: 단독 `OUT_OF_FRAME` 금지
- 실제 페이지/본문이 좌·우·상·하단에서 잘린 합성 및 라벨 표본: hard reject
- spine 접촉: outer-frame clipping으로 오인하지 않음
- 서로 다른 좌우 crop 크기지만 본문이 보존된 경우: 크기 차이만으로 reject하지 않음

### 6.2 Motion

- 동일 장면의 전역 밝기 변화: stable 가능
- 작은 카메라 translation 후 정렬 가능한 장면: residual 기준 stable 가능
- 책 위치 조정: `PAGE_MOVING`
- 페이지 넘김과 움직이는 손: `HAND_OR_PAGE_TURN`
- 정렬 실패/비정상 transform: stable 금지

### 6.3 Obstruction

- 손이 본문 위에 움직임: reject
- 손이 본문 위에서 정지: reject
- 손이 검은 배경에만 있음: content-overlap hard reject 금지
- 손가락이 빈 여백에만 있음: 정책에 따른 warning, 근거 기록
- 파란 박스·수식·삽화를 손으로 오인: false reject 금지
- 서로 다른 피부색·그림자·노출 조건: anchor 또는 공개 검증 자료로 확인

### 6.4 End-to-end replay

- 사용자 확인 `CLEAN_TRANSFERABLE` anchor 묶음마다 자동 선택 최소 1건
- `PAGE_MOVING`, `HAND_CONTENT_OCCLUSION`, `LAYOUT_INVALID` 선택 0건
- 선택된 각 frame의 V2 좌우 `PREPARED` 또는 설명 가능한 명시적 local retry
- 좌우 source frame ID 불일치 0건
- 현재 영상에 맞춘 임계값만으로 held-out 성공을 주장하지 않음
- 기존 V0/V1.1/V2 및 전체 unit test 회귀 없음

## 7. 완료 기준

다음을 모두 만족해야 V1.2 구현 완료로 기록한다.

- 사용자가 확인한 positive anchor에서 자동 선택 사례 존재
- 사용자 확인 negative anchor의 false accept 0
- 정지 손 본문 가림을 motion 안정으로 통과시키지 않음
- frame-edge mask 누출을 실제 clipping으로 오인하지 않음
- 선택 이유와 탈락 이유가 frame별 JSON으로 재현됨
- 선택된 원본이 축소되지 않고 기존 V2에 전달됨
- 전체 unit test 통과

held-out 영상까지 같은 조건을 만족하기 전에는 정책을 `validated=True`로 바꾸거나 실제 카메라
통합 완료로 표현하지 않는다.

## 8. 비범위

- seam-conservative/UVDoc 알고리즘과 padding의 새 sweep
- Document Parser OCR 및 braille 결과 비교
- 서버 preflight, durable outbox, upload retry
- page-change 중복 전송 방지
- TTS/beep 및 사용자 guidance 문구
- Raspberry Pi camera/GPIO/systemd
- 자체 hand detector의 대규모 학습

## 9. 중단 조건

- 현재 MP4 하나에 threshold를 맞춘 뒤 일반화 완료로 선언해야 하는 경우
- 사용자 확인 없는 Codex 시각 선택을 ground truth로 사용해야 하는 경우
- 정지 손 검출 없이 시간적 motion만으로 `HAND_OR_PAGE_TURN` 해결을 가장해야 하는 경우
- 승인·출처·hash 없는 모델을 자동 다운로드해야 하는 경우
- V1 preview 결과를 V2 final mask/crop으로 재사용해야 하는 경우
- 기존 사용자 변경이나 V2 bundle을 덮어써야 하는 경우

중단 시 통과 수를 만들기 위해 기준을 낮추지 않고, 실패 표본·metric·필요한 외부 모델 또는
추가 라벨만 보고한다.

## 10. 승인 후 실행 순서

1. 기존 보고서의 “사람이 선택” 표현을 `Codex 제안 후 사용자 확인`으로 정정
2. 사용자 확정 positive 2개와 proposed negative를 포함한 anchor/contact sheet 및 label manifest 생성
3. frame-edge contact와 confirmed clipping 분리 구현·테스트
4. photometric normalization + 제한 정렬 + residual motion 구현·테스트
5. obstruction baseline 및 경량 detector 평가
6. stable window/best-frame 통합
7. 현재 MP4 순차 replay와 자동 선택 frame의 V2 GPU 검증
8. 결과·실패·미검증 항목을 보고서와 재현 JSON에 기록
