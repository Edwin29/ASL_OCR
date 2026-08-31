# Scanner Video V1.2 자동 선택 보강 중간 보고서

상태: **부분 구현·development 라벨 통과 / held-out·Raspberry Pi 미검증**
실행일: 2026-08-30

## 결론

frame-edge 접촉을 단독 `OUT_OF_FRAME` hard gate에서 분리하고, 광도 정규화와 제한된
translation 정렬 뒤 residual motion을 계산하도록 V1 후보 판정을 보강했다. 이 변경으로
사용자 확정 `CLEAN_TRANSFERABLE` 720·780·2220번 중 780번을 포함한 구간에서 stable window가
생겼다. 기존 MediaPipe 2표본은 clean 3/3을 회복하지만 손 가림 2400·2580을 수락했다.
고정 구도용 model-free `edge-chroma intrusion`을 추가한 2표본 replay는 clean 3/3 회복과
negative false accept 0/9를 동시에 만족했다. 다만 같은 영상에서 threshold를 정한 development
결과이므로 기본 `stable_sample_count=3`, `validated=False`는 유지한다.

motion-only 실영상 replay는 stable window 4건을 만들었지만 32.16초의 정지 손 프레임
1920번을 자동 선택하는 false accept가 있었다. MediaPipe hand landmarker를 명시적으로 주입한
개발 replay에서는 이 구간이 `CONTENT_OCCLUDED`로 거부돼 stable window가 3건, 자동 선택은
750번 1건으로 줄었다. 750번은 기존 production V2 `seam-conservative + UVDoc bilinear`에서
좌우 같은 source frame으로 `PREPARED`까지 성공했다.

이는 V1.2 완료 선언이 아니다. 별도 held-out 영상과 실제 본문 잘림 negative label이 남아 있다.
배포는 계획하지 않으므로 model 재배포 조건은 완료 조건에서 제외했다. 기본 runtime은 모델 없는
edge-chroma detector를 사용하며 MediaPipe는 명시적으로 선택하는 비교 경로에만 남아 있다.

## 구현 내용

### Frame-edge

- `PageMask.touches_outer_frame` 및 방향별 접촉을 metric으로 보존했다.
- mask 접촉만으로 `OUT_OF_FRAME`을 만들지 않는 것이 기본값이다.
- 이전 동작이 필요한 비교 실험만 `reject_outer_frame_contacts=True`로 명시한다.
- 접촉 strip에서 mask 길이, 밝은 종이 지지율, local-background 대비 잉크 비율을 별도 기록한다.
- 밝은 종이 지지와 잉크 경계 접촉이 함께 있으면 기존 metric 이름
  `confirmed_content_clipping`에 provisional 신호를 남기지만, 기본 정책에서는 hard reason으로
  사용하지 않는다. 이름과 달리 실제 본문 잘림의 ground truth가 아님을 보고서에 명시한다.
- 비교 실험에서만 `--reject-content-edge-clipping`으로 opt-in할 수 있다.
- 실제 본문 잘림 negative와 held-out이 없으므로 production 검증 완료로 처리하지 않았다.

### Motion

인접 500ms preview 표본에 다음 순서를 적용한다.

1. 공통 page mask support
2. 5/95 percentile 광도 정규화
3. Gaussian blur
4. ECC translation 정렬
5. 전체 residual 및 최대 connected residual

정렬 correlation과 이동량도 JSON metric으로 남긴다. 전역 밝기 변화, frame-edge warning,
비정상 정렬에 대한 단위 테스트를 추가했다.

### Obstruction 경계

- `ObstructionDetector`와 provenance를 가진 결과 계약을 추가했다.
- classical YCrCb/HSV+contour baseline은 오탐 가능성을 명시하고 `content_occluded=False`만
  반환한다.
- 선택적 MediaPipe adapter는 로컬 model path와 expected SHA-256를 모두 요구한다.
- SHA 불일치 시 runtime import 전에 실패하며 network/model 자동 다운로드가 없다.
- MediaPipe 비교 adapter는 검출 bbox가 page interior proxy와 겹칠 때만
  `CONTENT_OCCLUDED` hard reason을 만든다.
- 고정 상부 카메라에서 손이 frame 외부에서 들어온다는 제약을 이용한
  `EdgeChromaIntrusionObstructionDetector`를 기본으로 추가했다.
- YCrCb/HSV 저비용 mask, 연결요소의 frame-border 접촉, dilated page mask 근접성을 결합한다.
- 최소 연결요소 면적은 preview 전체의 0.3%다. clean 직전 2190의 책 가장자리 오탐 0.092%와
  partial finger 2580의 0.94% 사이에 10배 이상 여유를 둔 development threshold다.
- evaluator version은 기본 obstruction 변경을 반영해 `opencv-candidate-v1.2.2`다.

## 실제 MP4 순차 replay

입력은 `20260830_133526.mp4`, SHA-256
`16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`이다. 59.699650767 fps,
2,677 frame을 임의 seek 없이 단일 forward pass로 읽었고 30 frame마다 90개를 판정했다.

| 구성 | stable window | 자동 best frame | 해설 |
|---|---:|---|---|
| registered motion + diagnostic chroma | 4 | 750, 1920 | 1920은 정지 손이 오른쪽 본문을 가린 false accept |
| registered motion + MediaPipe, 3표본(현재 기본) | 3 | 750 | 사용자 negative 0/9 선택, positive 1/3 recovery |
| registered motion + MediaPipe, 2표본 실험 | 9 | 510, 720, 750, 780, 2100, 2220, 2400, 2580 | positive 3/3지만 손 가림 2400·2580 false accept |
| 위 구성 + 폐기한 edge-clipping hard gate, 2표본 | 5 | 720, 750, 780, 2220 | 같은 영상에서는 negative 0/9였으나 clean 정적 이미지 104447 오거부 |
| edge-chroma intrusion, 2표본 | 5 | 720, 750, 780, 2220 | positive 3/3, negative false accept 0/9; held-out 전 provisional |

MediaPipe 구성의 candidate 직접 `CONTENT_OCCLUDED`는 16/90 frame이었다. rolling 3표본
assessment에서는 27회 obstruction reason이 나타났다. 사용자 확정 positive 720·780·2220
candidate 자체에는 `CONTENT_OCCLUDED`가 없었다. 사용자 확정 negative는
`HAND_CONTENT_OCCLUSION` 7개와 `PAGE_MOVING` 2개다.

- 720번: 2표본에서는 window ending at 720 stable, best frame 720; 3표본에서는 stable 아님
- 780번: 3표본 window ending at 780 stable, best frame 750
- 2220번: 해당 원본은 사용자 확정 clean이고 candidate hard reason도 없으나, 직전 표본을
  포함한 3표본 residual motion 최대값 0.054855가 0.03을 넘어서 stable은 아님
- 1980번: motion-only window stable, best 1920; MediaPipe 구성에서는 window 내 hand detection으로 거부

2220번 한 장이 clean이라는 사실과 그 직전 약 1.5초가 stable이라는 사실은 다르므로
`stable_sample_count=3`을 이 표본 하나만 근거로 줄이지 않았다. 실제로 2표본으로 줄인 paired
replay는 720·780·2220을 모두 회복했지만 사용자 확정 손 가림 2400과 2580도 선택했다. 따라서
MediaPipe 단독 2표본 정책은 채택하지 않는다. edge-clipping hard gate를 더한 같은 영상 replay가
negative를 막은 것은 사실이나, 아래 clean 정적 이미지를 거부하므로 올바른 obstruction 해결책이
아니다. edge-chroma 2표본은 두 손 프레임을 올바른 `CONTENT_OCCLUDED`로 거부했지만 held-out 전에는
기본 3표본을 변경하지 않는다.

### 실제 clipping probe

p30 촬영 묶음 6개를 같은 640px preview analyzer로 비교했다.

| 파일 | 기존 mask 접촉 | 밝은 종이 최대 비율 | 잉크 최대 비율 | 결과 |
|---|---|---:|---:|---|
| 20260830_104315 | 없음 | 0 | 0 | 통과 |
| 20260830_104447 | left:bottom, right:bottom/outer | 0.9278 | 0.0297 | 진단 warning, 기본 정책 통과 |
| 20260830_104511 | false left:top / right page 미검출 | 0 | 0 | `PAGE_NOT_FOUND + SEAM_FAILED` |
| 20260830_111919 | false right:top | 0 | 0 | 통과 |
| 20260830_112000 | 없음 | 0 | 0 | 통과 |
| 20260830_112042 | 없음 | 0 | 0 | 통과 |

`104447`의 oracle polygon은 왼쪽 페이지가 y=2998.53/3000까지 닿는다. 사용자는 복잡성이 낮고
혼동이 적은 쪽으로 분류 결정을 위임했다. 원본 해상도에서 p30 문제 1~4와 footer가 모두 보존된
것을 확인했고, 기존의 “본문이 보존되면 외곽 크기에 엄격히 집착하지 않는다”는 기준에 따라
`CLEAN_TRANSFERABLE`로 기록했다. 이 결정은
`p030_layout_label_manifest.json`에 provenance와 함께 남겼다.

폐기한 hard gate는 영상 candidate 65/90, rolling assessment 72회에 `OUT_OF_FRAME`을 추가했다.
clean anchor를 직접 거부하지 않으면서 hand/motion negative와 상당히 중복돼 같은 영상 점수만
개선했지만, `104447` 오거부로 일반화되지 않음이 확인됐다. 따라서 기본값은 diagnostic-only다.
evaluator는 metric 추가 이력을 보존하기 위해 `opencv-candidate-v1.2.1`로 기록한다.

## 경량성 비교와 MediaPipe provenance

같은 PC, 같은 4K forward decode, 같은 90개 preview 표본에서 1회 측정했다.

| detector | 후보 분석 평균 | 후보 분석 합계 | 전체 replay | anchor 결과 |
|---|---:|---:|---:|---|
| edge-chroma intrusion | 26.19 ms/표본 | 2.357초 | 32.489초 | positive 3/3, negative FA 0/9 |
| MediaPipe hand landmarker | 34.08 ms/표본 | 3.067초 | 32.456초 | positive 3/3, negative FA 2/9 |

edge-chroma 후보 분석은 이 1회 PC 측정에서 약 23.1% 짧았다. 전체 시간은 4K 순차 decode가
지배해 거의 같았다. edge-chroma는 별도 model file이 없고, MediaPipe 비교 모델은 7,819,105
bytes다. 실제 peak memory와 Raspberry Pi 시간은 측정하지 않았으므로 개선으로 단정하지 않는다.

- SDK: `mediapipe==0.10.35`, 임시 격리 설치
- 공식 sample model URL:
  `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`
- 파일 크기: 7,819,105 bytes
- SHA-256: `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`
- 실행: PC CPU, preview 최대 640px, detection/presence confidence 0.10
- 저장소 포함: 안 함

배포 계획이 없으므로 model bundle의 재배포 조건은 채택 blocker가 아니다. model은 저장소에
commit하지 않았고 optional adapter는 model path/hash가 외부에서 주입될 때만 동작한다.

## V2 선택 프레임 회귀

자동 best 750번을 exact forward decode한 뒤 GPU V2로 처리했다.

- frame/timestamp: 750 / 12.562887561초
- V2: `PREPARED`
- 좌우 동일 source frame: 참
- UVDoc model load count: 1
- bundle: 2,722,148 bytes
- left/right UVDoc SHA-256:
  `bacc9ce2a60f95e9de6568560430141766c29633dba991f91555aa06736f82da`,
  `97d544883a19013cbef64f724aca072b0d9ccfa8db1d60b94cdb0b7323d40841`

이 결과는 local artifact 준비 성공이며 Document Parser 서버 전송 성공을 뜻하지 않는다.

2표본+clipping replay에서 실제 엔진이 처음 만나는 stable window는 720번에서 끝나고 best frame도
720번이다. 이 원본도 GPU V2에서 `PREPARED`, 좌우 동일 source frame, UVDoc load count 1을
만족했다. bundle은 2,892,964 bytes였다. 사용자는 이후 720번을 직접
`CLEAN_TRANSFERABLE`로 확정했다. 이는 해당 프레임의 V2 local artifact 준비를 검증하지만,
2표본 자동 선택 정책 전체를 검증하지는 않는다.

전체 `tests/unit` 회귀는 **204 passed**, focused obstruction/candidate/config 테스트는
**29 passed**였다.

## 남은 완료 조건

1. 실제 OCR 본문이 프레임 밖으로 잘린 negative label 추가
2. 별도 영상에서 positive recovery와 negative reject 재현
3. edge-chroma를 서로 다른 피부색·조명·갈색 물체/배경에서 검증
4. Raspberry Pi 4 후보 분석 시간과 peak memory 측정
5. camera runtime 통합

재현 자료는 `experiment_outputs/scanner_video_v1_2_selection_20260830/` 아래 manifest,
3표본·2표본 비교 replay JSON 및 750번 V2 bundle에 있다.
정적 라벨 probe는 `p030_edge_chroma_default_probe.json`, 최신 3표본·2표본
replay는 각각 `replay_user_confirmed12_mediapipe_stable3/summary.json`,
`replay_user_confirmed12_mediapipe_stable2/summary.json`에 있다. 폐기한 hard-gate 비교 결과는
`replay_v1_2_1_clipping_stable2_final/summary.json`, 첫 선택 720번 V2 결과는
`v2_first_selected_frame_720/summary.json`에 보존했다.

최신 model-free 결과와 시간 측정은
`replay_user_confirmed12_edge_chroma_tuned_stable2_timed/summary.json`, 같은 조건의 MediaPipe
비교는 `replay_user_confirmed12_mediapipe_stable2_timed/summary.json`에 있다.
