# Scanner Video V1 — PC 표본 프레임 엔진 작업 패킷

상태: **구현·결정론적 검증 완료 — 실제 MP4 replay 차단**
작성일: 2026-08-30
선행 조건: V0 계약·상태·테스트 더블 완료
후속 조건: V2 seam+UVDoc artifact 통합

## 1. 목표

PC에서 버튼 start/cancel로 동작하는 연속 session을 구현하되, 애플리케이션은 카메라의
매 frame을 판정하지 않는다. 설정 주기로 최신 frame을 표본화하고 짧은 안정 window의 최선
frame을 선택하며, 같은 full-spread frame에서 좌우 처리 요청을 하나의 작업으로 만든다.

V1의 `SpreadProcessor`는 fake 또는 경량 stub이다. seam과 UVDoc의 정확도는 V2에서 검증한다.

## 2. 구현 범위

### 2.1 Camera와 replay adapter

- 기존 `CaptureSource`를 깨지 않고 새 `VideoCameraSource` adapter 추가
- PC OpenCV camera start/read/stop
- MP4 또는 frame sequence replay adapter
- 각 frame에 session-local monotonic `frame_id`, capture timestamp, 원본 크기 부여
- decode 실패와 EOF를 구분
- 취소·EOF·예외에서 camera resource 해제

프레임 producer는 I/O를 담당하고 판정·UVDoc·전송을 직접 실행하지 않는다.

### 2.2 표본화 주기, bounded window와 backpressure

- camera backend는 warm-up·노출 유지를 위해 열어 두되 판정 queue에는 지정 주기의 최신
  frame만 넣음
- 검색 중 초기 권고값은 `sample_interval_ms=500`
- 안정성 확인 초기 권고값은 `stable_sample_count=3`; 약 1초 동안의 세 표본을 비교
- local retry 뒤에는 별도 cooldown을 적용
- 위 값은 production 확정값이 아니라 replay 전에 선언하는 provisional config
- 짧고 고정된 sample window
- consumer가 느릴 때 최신 표본을 우선하고 오래된 미처리 표본을 폐기
- 처리 중인 원본 frame은 참조가 끝날 때까지 보존
- drop count와 queue depth를 diagnostics에 기록
- 모든 frame을 디스크에 저장하지 않음

PC `VideoCapture`가 내부에 오래된 frame을 쌓는 경우 최신 frame을 읽도록 backend에서 drain
또는 grab/retrieve 전략을 캡슐화한다. Pi adapter의 방식은 V5에서 별도로 결정한다.

### 2.3 Candidate scheduler

저해상도 preview에서 다음을 평가한다.

- decode/페이지 후보 존재
- frame 외곽 접촉과 심한 위치 이탈
- frame 간 motion
- sampled settling window의 안정성
- blur·노출의 상대 점수

이 값은 최종 전송 gate가 아니다. 안정 구간에서 비싼 처리를 시도할 frame을 고르는 ranking
입력이다. 한 조건의 순간 실패만으로 session을 종료하지 않는다.

### 2.4 안정 판정 기준

“안정”은 한 장의 blur 점수가 높다는 뜻이 아니다. 연속 K개 표본이 다음 hard condition을
모두 만족해야 안정 window로 인정한다.

- 좌우 page/spread 후보가 모두 존재
- 물리 frame 외곽에 페이지가 닿지 않음
- page mask IoU 변화가 작음
- 좌우 bbox 중심, 면적, outer boundary 변화가 작음
- spine seam 위치 변화가 작음
- 밝기 정규화한 page ROI의 frame difference 또는 optical flow가 작음
- 손이나 넘어가는 종이처럼 넓고 연결된 변화 영역이 없음
- timestamp/frame ID가 달라 stale frame 반복이 아님

IoU, 이동량, motion의 구체적인 합격 수치는 현재 영상에서 측정하지 않았으므로 확정하지 않는다.
V1 구현 전 provisional 값을 config에 명시하고 Drive 영상의 human timeline과 비교해 false select와
miss를 보고한다. 같은 영상 결과를 본 뒤 값을 수정하면 그 실행은 calibration으로 기록하고,
별도 고정 replay에서 다시 검증한다.

### 2.5 안정 window 안의 best frame 선택

hard condition을 통과한 frame끼리만 다음 lexicographic priority로 선택한다.

1. 페이지 잘림이 없고 physical edge margin이 큰 frame
2. mask/seam confidence가 높은 frame
3. white/black clipping과 glare가 적은 frame
4. grid illumination range와 shadow 불균형이 작은 frame
5. Tenengrad/Laplacian 기준으로 더 선명한 frame
6. 동률이면 더 최근 frame

단일 가중합으로 만들지 않는다. 예를 들어 선명도가 높아도 페이지가 잘린 frame은 선택할 수 없다.
OCR·Document Parser 결과는 V1의 frame ranking에 사용하지 않는다.

### 2.6 상태 머신과 취소

- 버튼 start: `IDLE → ARMING → SEARCHING`
- motion: `SEARCHING ↔ SETTLING`
- 후보 선택: `PROCESSING_CANDIDATE`
- fake processor 실패: `LOCAL_RETRY → SEARCHING`
- fake artifact ready: `READY_FOR_SERVER_PREFLIGHT`
- active 상태에서 버튼 cancel: `CANCELLING → IDLE`

취소 후에는 새 candidate를 시작하지 않는다. 이미 실행 중인 취소 불가능 작업이 있으면 결과를
전송하지 않고 정리한 뒤 IDLE로 간다.

### 2.7 동일 frame 좌우 불변식

- processor 입력은 full-spread frame 하나
- 좌우를 별도 capture 호출로 얻지 않음
- `SpreadArtifactRef.left/right.source_frame_id`가 항상 동일
- 한쪽 실패 시 다음 frame의 한쪽과 조합하지 않음

### 2.8 관찰성

- 상태 전이 event
- frame 수신/폐기/선택 수
- candidate 점수와 retry reason
- sample interval, stable window와 각 hard metric
- 처리 latency
- cancel latency와 resource-release 결과

원본 영상이나 frame 내용을 기본 로그에 넣지 않는다.

## 3. Drive 영상의 사용

승인된 보조 입력:

- Drive 폴더: `Ocr_scan`
- 파일: `20260830_133526.mp4`
- MIME: `video/mp4`
- 크기: `242,882,956` bytes
- Drive ID: `1bEDc9_JGi-E50RpP0N22SIfsF6-S2xo5`
- 알려진 의도: 페이지 구도를 잡는 장면과 페이지를 넘기는 장면 포함

2026-08-30 현재 Drive 재생 변환이 끝나지 않아 영상 장면은 아직 직접 검증하지 못했다.
따라서 아래 장면 구분을 현재 사실로 미리 기록하지 않는다.

영상 사용 절차:

1. 재생 또는 다운로드 가능 상태 확인
2. 로컬 분석 사본의 SHA-256, codec, 해상도, FPS, duration 기록
3. 원본을 Git에 추가하지 않고 ignored test-data 위치에 보관
4. 사람이 timeline을 검토해 다음 구간을 manifest에 표시
   - `POSITIONING`
   - `STABLE_SPREAD`
   - `PAGE_TURN`
   - `POST_TURN_SETTLING`
   - 다음 `STABLE_SPREAD`
5. timeline을 보지 않고 계산한 motion/candidate 결과와 사람이 작성한 구간을 비교
6. 재현 가능한 소형 파생 frame sequence가 필요하면 개인정보·저작권 범위와 크기를 검토한
   뒤 별도 fixture로 만들며, 원본 MP4는 commit하지 않음

사람이 timeline을 확정하기 전에는 이 영상을 기준으로 page-turn 검출 완료를 주장하지 않는다.

## 4. 테스트 행렬

### 4.1 Deterministic unit/replay

- 빈 source/즉시 EOF
- 안정 frame 연속
- motion 후 안정화
- blur가 다른 안정 frame 여러 개 중 best selection
- camera backend가 sample cadence보다 빠른 경우
- stale buffered frame을 반복하지 않는지
- 2개 안정 + 1개 motion 표본은 안정으로 판정하지 않는지
- 선명하지만 잘린 frame이 덜 선명한 완전한 frame을 이기지 않는지
- processing 중 cancel
- source read 예외
- fake processor의 retry 후 다음 candidate 성공
- 한쪽 실패 후 다른 frame과 섞지 않는지

### 4.2 실제 MP4 보조 replay

Drive 영상을 확인할 수 있게 된 뒤:

- 전체 decode 성공/실패 frame 수
- POSITIONING/PAGE_TURN 구간에서 candidate 선택 여부
- 각 STABLE_SPREAD 구간의 candidate 수와 선택 frame
- page turn 직전·도중 frame 선택 유무
- frame drop, peak ring size, 처리 latency

V1에서는 page-change 이후 자동 재개를 production 기능으로 완료하지 않는다. 영상은 V1의
motion/settling/candidate scheduler 검증과 V3 page-change 패킷의 기준 자료로 재사용한다.

## 5. 완료 기준

- start/cancel 상태 전이가 deterministic
- cancel 뒤 camera resource 해제 및 새 처리 0
- sample window가 설정 상한을 넘지 않음
- 안정 구간에서 candidate를 선택하고 motion 구간에서는 선택하지 않음
- 매 camera frame이 아니라 설정된 cadence 범위에서만 candidate evaluation 실행
- 같은 frame ID로 좌우 processor 요청 생성
- 한쪽 retry가 cross-frame pair를 만들지 않음
- fake processor 실패 뒤 다음 frame에서 회복
- legacy session 전체 테스트 회귀 없음
- 실제 영상 검증을 못 했으면 그 항목은 `BLOCKED_VIDEO_NOT_AVAILABLE`로 남김

## 6. 비범위

- 실제 seam mask 품질
- UVDoc 모델 실행과 화질
- parser preflight·전송·outbox
- TTS·비프음 실제 출력
- 성공 뒤 page-change 자동 재개
- Pi camera와 성능

## 7. 중단 조건

- bounded buffer 없이 모든 frame을 누적해야 함
- 동일 full-spread frame 좌우 불변식을 유지할 수 없음
- 취소 시 camera를 해제할 수 없음
- MP4를 사용하려고 사용자 원본이나 243MB 파일을 Git에 넣어야 함

## 8. 구현 결과 (2026-08-30)

구현 파일:

- `src/book_scanner/video/sources.py`: PC OpenCV camera, MP4, image-sequence source와
  decode/EOF 분리
- `src/book_scanner/video/candidate.py`: 기존 contrast/external-contour page mask를 재사용한
  저비용 관찰값, bounded window, 안정성 판정, lexicographic best-frame 선택
- `src/book_scanner/video/engine.py`: 표본 cadence, 비동기 processor, start/cancel/retry/ready
  상태 전이, resource release, diagnostics
- `tests/unit/video/test_sources.py`, `test_candidate.py`, `test_engine.py`: V1 결정론적 검증

확인된 사항:

- 기본값은 500ms 표본, 3개 안정 표본, 최대 5개 관찰 window이며 모두 provisional config다.
- page mask IoU, 좌우 중심/면적, seam proxy, 밝기 정규화 frame difference, 연결 motion을
  hard stability gate로 사용한다.
- best frame은 hard gate 통과 뒤 margin → mask confidence → clipping → illumination →
  sharpness → 최신 frame 순으로 고른다. 가중합은 사용하지 않는다.
- processor는 한 full-spread frame과 한 spread ID를 받는다. 다른 source frame의 artifact를
  반환하면 session error로 거부한다.
- processing은 단일 worker에서 실행되며 cancel은 즉시 camera를 해제한다. 실행 중 작업이
  취소 불가능하면 완료 결과를 폐기한 뒤 IDLE로 돌아간다.
- V1 단위/계약 테스트 41개 및 전체 unit 회귀 162개가 통과했다.

미검증/차단:

- `20260830_133526.mp4`는 작업 공간에 로컬 사본이 없어서
  `BLOCKED_VIDEO_NOT_AVAILABLE`이다. 따라서 실제 POSITIONING/STABLE_SPREAD/PAGE_TURN
  timeline의 false select/miss와 threshold calibration은 완료로 처리하지 않는다.
- 실제 seam-conservative + UVDoc artifact 생성, Document Parser preflight·전송은 V2 이후
  범위이며 V1 완료 주장에 포함하지 않는다.
