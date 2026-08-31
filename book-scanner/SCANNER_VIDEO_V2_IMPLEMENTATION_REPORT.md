# Scanner Video V2 구현 보고서

상태: **V2 로컬 artifact 경로 및 실제 MP4 수동 안정 프레임 GPU 검증 완료 / V1 자동 선택 회귀 발견**
기준일: 2026-08-30

## 구현 결과

V1.1 엔진의 기본 준비 경계에 `seam-conservative → UVDoc bilinear → atomic artifact bundle`을 연결했다.
한 spread의 좌우 페이지는 하나의 full-resolution source frame에서 생성되며, 한쪽이라도 추출·보정·readiness에 실패하면 `PreparedSpreadArtifact`를 만들지 않는다. UVDoc 실패를 무보정 이미지로 대체하지 않는다.

- production extraction: `detect/spread_extraction.py`
- V2 preparer/bundle writer: `video/spread_preparer.py`
- atomic store의 manifest 파일/hash/이미지 decode 검증 강화: `video/artifacts.py`
- engine이 일반 local retry/fatal에서도 processing-job staging을 정리하도록 보강
- 명시적 `session_id`가 preparer까지 전달되며 manifest lineage와 대조됨
- 재현 도구: `tools/run_scanner_video_v2_p030_regression.py`
- 실제 MP4 재현 도구: `tools/run_scanner_video_v2_replay.py`

Bundle은 `source_frame.jpg`, 좌우 `mask.png`, `crop.jpg`, `uvdoc.jpg`, `diagnostics.json`, `manifest.json`으로 구성한다. Manifest에는 frame/session/spread/job lineage, 모든 파일 hash/크기, crop bbox/padding/contact, seam 전체 경로·confidence, UVDoc runtime/checkpoint/model hash/device/sampling/load count, local readiness가 포함된다.

외곽 frame 접촉은 본문 잘림의 충분조건이 아니므로 기본값에서는 경고로 기록한다. 명백한 최소 해상도 또는 비정상 종횡비만 hard gate이며, 필요하면 `reject_outer_frame_contacts`를 켤 수 있다.

## 검증 결과

- 전체 unit: **189 passed**
- V2/extraction 포함 집중 unit: **68 passed**
- p30 3장 4000×3000, RTX 4060, CUDA, 기존 checkpoint: **3/3 prepared 및 atomic commit**
- UVDoc 호출 6회 동안 model `load_count=1`
- 기존 paired 실험과 crop bbox: p30 세 장 모두 픽셀 단위 동일
- 기존 p30 left UVDoc PNG 대비 runtime JPEG decode:
  - MAE 0.3258–0.4979
  - PSNR 48.464–51.276 dB
  - 출력 크기 3/3 동일
- bundle 크기: 약 5.13 MB, 7.07 MB, 5.25 MB
- 10 ms sampling 기준 process RSS peak: 약 1.13–1.31 GB
- CUDA peak allocated: 약 290–314 MB, peak reserved: 약 359 MB

최초 capture의 4.90초에는 checkpoint load와 첫 GPU 실행이 포함된다. 이후 두 spread는 1.53초와 1.51초였다. 이 수치는 PC 측정값이며 Raspberry Pi 4 성능 근거가 아니다.
RSS는 Python/OpenCV/Torch와 bundle encoding을 모두 포함한 프로세스 관측치이며 extraction만의 메모리 사용량으로 해석하면 안 된다.

세부 수치와 hash는 `experiment_outputs/scanner_video_v2_p030_20260830/summary.json`에 기록했다.

## 실제 MP4 replay

Drive의 `20260830_133526.mp4`를 로컬에 확보하고 SHA-256과 컨테이너 메타데이터를 확인했다.

- SHA-256: `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
- 크기: 242,882,956 bytes
- 3840×2160, 59.699650767 fps, 2,677 frames, 44.841 seconds

OpenCV의 임의 `CAP_PROP_POS_MSEC` seek는 이 파일에서 후반부 decode에 실패했다. 실제 runtime
source는 원래 순차 sampling이므로 영향을 받지 않지만, 실험 도구도 임의 seek를 사용하지 않고
요청 timestamp들을 한 번의 forward decode로 먼저 확보하도록 고쳤다.

Codex가 진단용으로 제안한 두 프레임을 production V2 preparer로 처리했고, 이후 사용자가
두 프레임 모두 `CLEAN_TRANSFERABLE`이라고 확인했다. 이는 V2 artifact 경로와 positive anchor를
확인한 결과이며 자동 안정 프레임 선택 성공을 뜻하지 않는다.

| frame | 내용 | V2 상태 | 총 처리 | 좌/우 UVDoc | bundle | seam confidence |
|---|---|---|---:|---:|---:|---:|
| 780 / 13.065s | p30 / p309 | PREPARED | 2,875.657ms | 255.686 / 68.684ms | 2,794,024 bytes | 0.016174 |
| 2220 / 37.186s | p316 / p317 | PREPARED | 1,032.237ms | 63.635 / 69.994ms | 2,665,800 bytes | 0.030280 |

- 2/2에서 좌·우 artifact가 동일 source frame ID를 공유했다.
- 네 페이지 전체에서 UVDoc `load_count=1`이었다.
- 한쪽 실패 또는 partial ready artifact는 없었다.
- crop과 UVDoc 결과를 육안 확인했다. 본문은 읽을 수 있고 좌우 페이지는 분리됐으나, crop의
  inner edge에 제본부/맞은편 페이지의 좁은 띠가 남고 UVDoc 결과에 선명도 저하가 있다.
- 재현 결과는 `experiment_outputs/scanner_video_v2_mp4_20260830_forward_decode/summary.json`과
  두 immutable bundle에 기록했다.

## 실제 영상에서 발견된 V1 회귀

기본 500ms cadence로 90개 프레임을 분석했을 때 자동 선택은 0건이었다.

- 82개 후보가 `OUT_OF_FRAME`, 8개가 `PAGE_NOT_FOUND + SEAM_FAILED`였다.
- 안정 화면에서도 preview foreground가 검은 천 질감과 연결되어 상단/하단 frame 경계까지
  번졌다. 따라서 mask 경계 접촉은 실제 페이지 잘림의 충분조건이 아니었다.
- `OUT_OF_FRAME`만 진단으로 강등해도 현재 `max_motion_fraction=0.03`에서는 stable 0건이었다.
  영상의 미세 진동/노출 변화가 전체 pixel-motion 비율을 0.1~0.25 수준으로 만들었다.
- 임계값을 이 영상에 맞춰 시험적으로 완화하면 안정 프레임뿐 아니라 1.5초 이상 정지한 손이
  페이지 하단을 가린 프레임도 통과할 수 있었다. 따라서 이 실험값을 production 기본값으로
  채택하지 않았다.

이는 V2 패킷의 threshold 즉석 수정 금지 조건에 따라 별도 후속 문제로 남긴다. 다음 안정 선택
패킷은 `frame-edge contact의 진단/하드 게이트 분리`, `전역 노출 변화에 강한 motion`,
`정지 손/가림 검출`을 함께 검증해야 한다.

## 완료하지 않은 항목

- 실제 MP4의 V2 수동 안정 프레임 replay는 완료했지만, V1 자동 선택은 검증 실패 상태다.
- 이번 V2는 Document Parser 서버 전송/OCR을 다시 실행하지 않았다. V2의 책임은 parser 입력용 로컬 artifact 준비까지이며, 사람이 검증한 기존 p30 parser 결과는 golden으로 유지한다.
- Raspberry Pi 4 camera/GPIO, durable outbox/upload, page-change 중복 방지, TTS/beep는 후속 패킷 범위다.
- exact OS rename 시각은 immutable manifest가 rename 전에 동결되므로 기록하지 않는다. 대신 atomic promotion 가능 시각과 same-filesystem rename semantics를 기록한다.

따라서 V2의 수동 선택 실영상 로컬 artifact 경로는 검증 완료다. 자동 선택부터 전송까지의 PC
영상 통합은 V1 회귀와 후속 전송 모듈이 남아 있으므로 완료로 처리하지 않는다.
