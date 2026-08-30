# Scanner Video V2 구현 보고서

상태: **로컬 artifact 경로 구현 및 p30 GPU 검증 완료 / 실제 MP4 replay 미검증**
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

## 완료하지 않은 항목

- `20260830_133526.mp4`가 로컬 workspace에 없어 실제 영상 replay는 `BLOCKED_VIDEO_NOT_AVAILABLE`이다.
- 이번 V2는 Document Parser 서버 전송/OCR을 다시 실행하지 않았다. V2의 책임은 parser 입력용 로컬 artifact 준비까지이며, 사람이 검증한 기존 p30 parser 결과는 golden으로 유지한다.
- Raspberry Pi 4 camera/GPIO, durable outbox/upload, page-change 중복 방지, TTS/beep는 후속 패킷 범위다.
- exact OS rename 시각은 immutable manifest가 rename 전에 동결되므로 기록하지 않는다. 대신 atomic promotion 가능 시각과 same-filesystem rename semantics를 기록한다.

따라서 V2의 로컬 JPEG/GPU 경로는 구현 완료이나, PC 영상 통합 완료로는 처리하지 않는다.
