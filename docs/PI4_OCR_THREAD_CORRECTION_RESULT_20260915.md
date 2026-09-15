# Pi OCR 추론 스레드 수정·검증 결과

## 적용 결과

사용자 승인 후 페이지 인식 어댑터에서 **ARM64(`aarch64`/`arm64`)의 암시적 기본 장치 또는 명시적 CPU 장치에 `cpu_threads=1`**을 전달하도록 수정했다. x86/AMD64 및 명시적 GPU 옵션은 유지한다. 모델, hash validation, 인식/중복/identity 기준, 관측 수, timeout, FRAME/V3, 오디오 코드는 변경하지 않았다.

- 제품 변경: `book-scanner/src/book_scanner/video/page_number_recognizer.py` 1개 파일, 7줄 추가·1줄 교체.
- 회귀 테스트: `book-scanner/tests/unit/video/test_paddle_runtime_threads.py` 추가. ARM 자동/CPU, ARM64 대소문자, x86 자동/CPU, ARM GPU 옵션 및 모델 hash 검증 유지 확인.
- 배포 대상: Desktop 저장소 및 `/home/user/ASL_OCR_PI/source/book-scanner/src/book_scanner/video/page_number_recognizer.py`. Laptop 제품 소스는 이 작업에서 변경하지 않았다.
- Pi 배포 전 SHA-256 `28f40e925cb0883d184e7f46fbcf929075af3cf04d9da2bff2899b35610b32a6`; 배포 후 Desktop/Pi 동일 `18d287218c164164a61266612c01e694966cf1a7d1e51efce919355f1ab43596`.
- Desktop/Pi의 배포 전 raw hash 차이는 줄바꿈 차이였고, `git diff --no-index --ignore-space-at-eol`에 의미 있는 차이는 없었다.
- 원본은 Pi evidence의 `page_number_recognizer.before-thread-fix.py` 및 Desktop evidence의 `page_number_recognizer.pi-before.py`에 보존했다. 기존 source-model manifest는 덮어쓰지 않았다. 249개 source/model 파일 재검사에서 승인된 제품 파일 1개만 달랐다.

## 검증

| 검사 | 결과 / 범위 |
|---|---|
| 새 runtime 옵션 테스트 + 기존 composition + page-number 테스트 | **21 passed** |
| 수정된 production Scanner factory로 합성 `28` 추론 | **PASS**, 약 0.501초, confidence 0.9984958. 임시 옵션 주입 없음 |
| 같은 프로세스 UVDoc 계산 | **PASS**, 모델 로드 포함 약 3.17초, 실제 계산 약 2.51초 |
| 실시간 카메라 5회 read-only 표본 | 최초 2회 no_frame 후 세로 3000×4000 프레임 3개. 모두 footer missing. 종료코드 0이나 **인식 수용 FAIL** |
| 이전 정상 방향 snapshot의 production preview/ROI 경로 5회 | 모두 footer missing. 후속 표본은 cache hit이므로 5회의 독립 native inference 성공으로 세지 않음 |
| 이후 새 snapshot | 다시 가로 4000×3000. 시각 확인상 책이 화면 일부를 차지하고 흐리게 보임. 초점/배치 조정을 요청 |

Windows 테스트 초기 실패는 pytest 기본 임시 폴더 권한과 한글 경로의 OpenCV 저장 실패, 새 임시 경로의 부모 폴더 미생성 때문이었다. 테스트/assertion을 바꾸지 않고 독립 영문 임시 경로를 마련해 21개를 모두 통과시켰다. 로그는 evidence에 보존한다.

**확인한 것은 기본 설정에서 재현되던 native crash를 수정된 production adapter의 합성 계산에서 피했다는 점이다.** 실제 footer 번호 인식·연속 Scanner liveness·fresh READY 생성은 아직 미통과다. 미인식 원인을 전부 초점이나 방향으로 단정하지 않는다. 이번 단일 스레드 변경이 입력 영상의 방향·품질을 교정하는 것은 아니다.

## 실제 미리보기 재사용

사용자가 초점 조정용 실제 미리보기를 요청했다. 기존 `show_candidate_preview.py`와 production snapshot source/analyzer/annotation/OpenCV window를 재사용하고 새 진단 실행기의 창 제목만 바꿨다. Laptop 제품 코드 수정은 없다.

- Laptop 실행 위치: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics\pi-focus-20260915-01`.
- 수동 1회 실행용 task: `ASL_Pi_FocusPreview_20260915_01`; 시간·반복 trigger 없음, interactive 사용자 세션 5. Pi 자동 시작 서비스와 무관하다.
- 창 제목 `ASL Pi Focus - Actual snapshot ratio - Green=detected - Q=close`.
- ready: PID 11908, screen 1920×1080, display max width 1123, source 4000×3000. 전체 프레임을 비례 축소한다.
- OCR inference/업로드/STM 패킷 없음. 최대 600초, Q/창닫기/stop marker로 종료. 동시에 Pi 카메라 검사는 실행하지 않는다.
- 사용자에게 미리보기 표시 및 초점·배치 조정 완료 확인을 요청했다. **조정 후 preview를 멈추고 동일 배치에서 Pi read-only 인식 → production capture** 순으로 진행한다.
- 사용자가 미리보기 창 표시를 확인했고 현재 조정 중이라고 응답했다. 조정 완료 신호를 받기 전에는 Pi 카메라 검사를 재개하지 않는다.

## 남은 절차와 rollback

1. 미리보기에서 조정 완료 확인, 카메라·책 위치 유지.
2. Pi에서 실제 26/27 footer 인식과 연속 Scanner 기준을 변경 없이 재검증.
3. Production 두 spread capture → durable V4 receipt 각각 확인 → CONFIRM LONG → fresh READY → 물리 버튼/음성/점자 결합.
4. 위 최소 기능 검증 후 자동 시작·공동 전원 차단 복구 설정.

Rollback은 백업된 인식 어댑터 1개를 복구하고 hash를 재확인하는 범위다. state/SQLite/model/credential/펌웨어 변경·삭제는 필요 없다. 단 rollback하면 이 Pi dependency 조합의 기존 native crash가 재발할 수 있다.

Evidence: [pi-ocr-thread-correction-20260915](evidence/pi-ocr-thread-correction-20260915/). 제품 source modification count **1**, 새 targeted test 파일 **1**. H4/integration-ready는 선언하지 않는다.

## 미리보기 1차 조정 후 실제 영상 결과

사용자 조정 완료 후 Laptop preview를 stop marker로 종료했다. 158 samples, 정상 종료 result 및 잔류 대상 프로세스 없음 확인 후 Pi에서 단독으로 같은 배치의 5개 live frame을 처리했다.

- raw/effective 4000×3000, input_stage `preview_native`, maximum 4000 유지.
- 오른쪽 `27`: **5/5**, confidence 약 0.9966~0.9993. variant agreement 2.
- 왼쪽: 미관측 4회, `6491`을 낮은 confidence로 읽고 normalized label이 거절된 conflict 1회. complete pair **0/5**.
- 전체 provider 시간 약 1.43~3.65초, acquisition/analyzer를 포함한 표본 시간 약 3.44~5.90초. native crash 없이 종료코드 0. 이 속도는 8초/N5의 연속 collection에 대한 우려 근거지만, 이 probe는 실제 state machine을 실행하지 않으므로 full liveness 수용 결과로 해석하지 않는다. production 8000ms/sample750ms는 변경하지 않았다.
- 첫 frame의 실제 left ROI와 overlay를 저장해 확인했다. 번호 26은 ROI 안에 포함되지만 흐리게 보였다. ROI threshold/crop 정책은 변경하지 않았다.

### 동일 ROI Laptop 비교

Pi에서 생성한 동일 gray ROI 파일을 Laptop의 기존 인식 어댑터/Paddle 3.3.1로 read-only 처리했다. 왼쪽은 동일하게 `not_observed`, 오른쪽은 `27`/agreement2였다. 따라서 이 표본의 실패는 Pi만의 단일 스레드 변경에 한정되지 않는다. 초점·모든 입력/알고리즘 원인을 이 비교 하나로 확정하지 않는다.

첫 비교 실행은 harness에서 Paddle을 Torch보다 먼저 import하여 shm.dll 로드 실패가 났다. 제품 수정 없이 기존 검증의 import 순서(cv2, Torch, Paddle)로 다시 실행해 비교를 완료했다. 첫 실행 실패를 새 Pi defect로 분류하지 않는다.

### 미리보기 2차: 왼쪽 번호 확대

새 진단 실행기 `show_footer_preview.py`가 production ROI 추출 결과를 확대 표시한다. 원본 표시와 인식 입력은 변경하지 않고, 같은 프레임의 왼쪽 ROI를 별도 `ASL Left footer` 창에 비례 확대했다. 추가 OCR/업로드/STM 없음.

- Laptop runtime: `diagnostics/pi-focus-20260915-02`, 수동 task `ASL_Pi_FocusPreview_20260915_02`.
- ready PID34868, source4000×3000. 기존 600초/Q/stop bounds 유지.
- 사용자에게 왼쪽26이 선명하게 보이도록 조정 또는 더 이상 선명하게 만들기 어려움을 알려달라고 요청했다. Pi 카메라 검사는 대기한다.
- Evidence: `live-footer-thread-fix-1789474010186400144.jsonl`, `adjusted-footer-summary.json`, `adjusted-left-roi.png`, `adjusted-right-roi.png`, `adjusted-roi-overlay.jpg`, `saved-roi-laptop-comparison.json`.

## 미리보기 2차 조정 후 실제 영상 결과

사용자가 조정 완료를 알린 뒤 Pi 단독 read-only probe를 다시 실행했다. `live-footer-thread-fix-1789474752384076576.jsonl` 및 첫 원본 JPEG를 보존했다.

- 가로 4000×3000 영상 5/5, 왼쪽 `26` observed 5/5(confidence 0.9910~0.9976, agreement2), 오른쪽 정상 번호 0/5. 오른쪽은 미관측 3회, 낮은 confidence의 `2`/`29` conflict 2회로 모두 거절됐다. complete pair 0/5.
- provider 2.81~4.23초, 표본 전체 4.67~5.97초. 프로세스 종료코드 0, native crash 없음. 실제 Scanner collection/V4/READY 수용은 미검증이다.
- 첫 원본에서 왼쪽보다 오른쪽 글자/번호가 흐리게 보인다. 초점·평면 정렬은 후속 확인 후보이며 원인 확정은 아니다. 낮은 confidence를 통과시키거나 알려진 27로 대체하지 않는다.
- preview02는 stop marker 이전에 `FrameDecodeError`로 종료된 것으로 확인됐다. 337 samples, 마지막 source shape는 높이4000/너비3000(세로). 정상 종료로 기록하지 않는다. 이후 이번 Pi probe는 가로 영상 5개를 처리했으며 JPEG 경고도 있었다. 이 영상/해독 현상을 native 추론 crash와 구분한다.
- 왼쪽만 맞추면서 오른쪽 선명도를 놓치지 않도록 새 진단 `show_both_footer_preview.py`로 양쪽 production ROI를 함께 확대 표시한다. Laptop `diagnostics/pi-focus-20260915-03`, 수동 task `ASL_Pi_FocusPreview_20260915_03`, 기존 600초/Q/stop bounds 유지. 제품 소스 및 카메라 설정 변경, OCR/업로드/STM 패킷 없음. 조정 완료까지 Pi 카메라 probe는 대기한다.

## 상시 미리보기 요청 반영 및 3차 조정 검사

사용자가 3차 조정 완료와 함께 현재 앵글을 계속 볼 수 있도록 미리보기 유지, 가림 감지와 혼동되는 쪽 영역 빨간 박스 제거를 요청했다.

- 새 진단 실행기 `show_persistent_footer_preview.py`, Laptop `diagnostics/pi-focus-20260915-04`, 수동 task `ASL_Pi_FocusPreview_20260915_04` 사용. 반복 예약/부팅 서비스가 아니다. 600초 및 task 실행 시간 제한을 제거하고 Q/Esc/창닫기/stop marker로 종료한다.
- 메인 영상의 쪽 영역 사각형을 제거했다. 기존 production annotation의 obstruction 빨간 박스는 그대로이며, 쪽 영역은 LEFT footer / RIGHT footer 별도 창으로만 표시한다. 창 제목의 26/27도 제거해 인식 결과처럼 보이지 않게 했다.
- 프레임 대기 시 마지막 영상과 경과 시간을 표시한다. `FrameDecodeError`는 원래 worker 종료 확인 후 진단 미리보기에서만 5초 뒤 같은 source로 재시도한다. 그 밖의 오류는 화면에 오류 종류를 남기고 자동 재시도하지 않는다. 오류를 인식 성공으로 취급하지 않는다. 인증/TLS/해상도/제품 retry 정책 변경 없음.
- ready 이후 PID39816, 가로4000×3000 영상 및 heartbeat samples17 확인. Pi 검사 중에도 미리보기 유지. 따라서 이번 read-only Pi probe의 처리 시간은 동시 snapshot 요청 부하가 포함되며 단독 production cadence 수용에 사용할 수 없다.
- 이번 변경은 진단 실행기/기록에 한정한다. 제품 수정 수는 기존 승인된 OCR 어댑터 1개 그대로다.
- 3차 조정 Pi 표본(`live-footer-thread-fix-1789475431344932089.jsonl`): 가로4000×3000, 왼쪽26 5/5, 오른쪽27 및 complete pair **2/5**. 나머지 오른쪽은 variant agreement1로 conflict였고, raw text가27인 경우도 통과시키지 않았다. provider2.74~2.90초, 전체 표본4.44~5.31초, exit0/native crash 없음. 이 결과는 첫 local artifact/receipt/READY를 증명하지 않는다.
- 다음 검사는 `probe_scanner_first_artifact.py`로 실제 default Scanner factory를 사용한다. staging/ready만 새 isolated directory로 지정하고 첫 local artifact 또는90초 budget에서 종료한다. query N5/8000ms assert 유지. receipt 주입/서버 업로드/STM/audio 없음. 종료 시 해당 진단 engine만 cancel/close한다. 상시 미리보기 동시 요청 조건은 manifest에 명시한다.
- 연속 검사 결과(`scanner-first-artifact-1789475528334360176`): **90초 안에 첫 local artifact 생성 실패**, 프로세스 정상 종료(exit0). frames_received/evaluated31, selected4, processed0. opaque valid 관측4/missing4, unknown timeout4회. 종료 직전 settling, camera_resource_released=true. 종료코드0을 촬영 성공으로 사용하지 않는다.
- first failing boundary는 candidate identity collection이다. 단발26/27 complete가 있어도 실제 collector의 제한 시간 안에 필요한 관측을 모으지 못했다. 진단 마지막 effective interval 약4.78초, page-number latency 약2.86초. Pi 계산량/원본 해독 및 acquisition 지연/동시 미리보기 요청 부하/우측 인식 불일치를 경쟁 요인으로 남긴다. 특정 요인을 단독 원인으로 확정하지 않으며 N/K/8000ms 및 confidence/variant 기준은 유지한다.
- 다음 원인 분리는 미리보기 가시성을 유지하면서 추가 카메라 요청 부하를 분리하는 진단과 단계별 latency 비교가 필요하다. 현재 결과로 production capture/V4/READY 또는 H4 PASS를 선언하지 않는다. 미리보기04는 검사 종료 후에도 계속 유지한다.
- 후속 [Pi Scanner 지연 분리 진단](PI4_SCANNER_LATENCY_DIAGNOSIS_20260915.md) 완료: 상시 미리보기05로 교체하고 A/B/A2 비교를 수행했다. Pi 단독 카메라 요청에서도 표본 처리 중앙값4.965초로, 중복 요청 제거만으로 문제가 해소된다는 근거는 없다. 실제 추가 프레임에서 모델 호출6회/약2.321초를 직접 계측했다. 미리보기05는 독립 수신으로 복귀해 유지하며 제품 추가 수정은0개다.
