# Scanner Video V3-A.1 구현 및 backend 선발 보고서

작성일: 2026-08-31  
상태: **부분 구현 완료 — production recognizer 선발 보류**

## 결론

Bottom ROI page-number 계약, 좌우 ROI, bounded cache, datapack-scoped key ledger,
V3-A visual identity fusion, ACK 이후 stable-K page-change consensus는 구현했다.
전체 Book Scanner 회귀 234개가 통과했다.

다만 production recognizer는 아직 기본값으로 선택하지 않았다. p30 세 artifact에서 Paddle
recognition-only가 좌 `30` 3/3, 우 `309` 3/3을 재현했지만 PC warm spread median
159.956ms로 작업 패킷의 잠정 50ms 목표를 넘었고 Raspberry Pi 4에서 실행 가능한지도
검증하지 않았다. 오른쪽 `309`는 공급 이미지에서 읽히지만 사용자가 명시적으로 확인한
golden label은 아니므로 diagnostic으로만 집계했다.

## 구현 범위

- corrected UVDoc page와 preview mask/seam에 동일한 side-aware bottom-outer ROI 정책 적용
- ASCII digit 1~4자리 정규화와 raw text/confidence/bbox/version/ROI SHA-256 보존
- source kind까지 포함한 exact-ROI bounded LRU cache(capacity 32)
- `(data_pack_id, left, right, recognizer version)` page key와 accepted ledger(capacity 32)
- corrected ROI의 두 preprocessing variant 합의
- 같은 key + visual new, 다른 key + visual duplicate를 자동 처리하지 않는 conflict gate
- 검증 전 번호-only duplicate 억제 비활성화
- ACK 후 같은 complete key는 visual page-change 오탐 reset
- 다른 complete key는 eligible frame에서 연속 3회 후에만 candidate 수집 재개
- partial/missing/provider error는 기존 V3-A visual gate로 fallback
- page-number observation/key/conflict/page-change evidence 구조화 event
- provider를 명시적으로 주입하지 않으면 기존 V3-A 동작을 그대로 유지

## Backend 비교

동일 runner와 동일한 세 p30 V2 `seam-conservative + UVDoc bilinear` artifact를 사용했다.

| 후보 | 좌 p30 | 우 p309 진단 | spread median | 판단 |
|---|---:|---:|---:|---|
| OpenCV synthetic HOG baseline | 2/3 | 0/3 | 96.155ms | 정확도 부족, 제외 |
| Tesseract 5.5.3 CLI | 2/3 | 3/3 | 215.214ms | confidence 없음, 호출당 process 기동, 제외 |
| Paddle `en_PP-OCRv5_mobile_rec` persistent | 3/3 | 3/3 | 159.956ms | 정확도 후보, 성능/Pi gate 미통과 |

Tesseract는 `winget`의 `tesseract-ocr.tesseract` 5.5.3을 설치해 평가했다. component locator와
3배 확대를 포함한 재현 runner에서는 5/6이었으나 왼쪽 golden 한 건을 오인했다. 또한
recognizer confidence를 제공하지 않는 CLI 출력에 임의로 1.0을 부여하지 않았다. 따라서
production adapter로 편입하지 않았다.

Paddle 모델은 text detector나 Document Parser pipeline 없이 prelocalized component에
recognition만 수행했다. 모델은 한 recognizer instance에서 한 번 load된다. 평가 시 cold
constructor는 9457.455ms였으며 첫 spread 240.504ms, 이후 122.670ms와 159.956ms였다.
모델 파일 합계는 8,012,929 bytes다. dependency 전체 RSS와 Pi latency는 측정하지 않았다.

이전 MP4 replay에서 보존한 사용자 라벨 anchor도 별도 진단했다. identity용 960px preview는
footer glyph가 너무 작아 clean 3개가 모두 `missing`이었다. 이에 전체 OCR을 실행하는 대신 기존
page mask를 최대 1920px grayscale frame에 투영하고 동일한 bottom ROI만 읽도록 수정했다.
그 결과 clean-transferable 720은 `30/309` complete, 780은 좌 `30` partial, 2220은
`316/317` complete였다. 손 가림/이동 1170·1500·2400·2580은 기존 candidate gate가
`content_occluded`로 제외하여 recognizer에 들어가지 않았다. sparse anchor이므로 연속 K회
temporal accuracy나 false page-change의 실측 완료를 뜻하지 않는다.

## Fusion 정책

현재 `allow_number_only_duplicate=false`, `validated=false`다.

- 같은 complete key + visual duplicate: 기존 visual 근거로 중복 억제
- 같은 complete key + visual ambiguous: 자동 억제하지 않고 기존 ambiguous retry
- 같은 complete key + visual new: identity conflict, 자동 전송·삭제 없음
- 다른 complete key + visual new/ambiguous: new spread 후보
- 다른 complete key + visual duplicate: identity conflict
- 번호 partial/missing/error: 기존 visual fallback

이 정책 때문에 p30만 맞춘 결과로 false duplicate safety를 완료 처리하지 않는다.

## 검증 결과

- V3-A.1 core/fusion focused tests: 16 passed
- 전체 `book-scanner/tests`: 234 passed
- compileall: passed
- pytest cache directory 권한 warning 1건은 test failure가 아님
- Document Parser/PaddleOCR-VL 전체 pipeline 호출: 0
- preview UVDoc 호출: 0
- Tesseract production dependency 추가: 0
- Paddle production dependency 추가: 0

평가 산출물:

- `experiment_inputs/scanner_video_v3a1_p030_page_numbers.json`
- `experiment_outputs/scanner_video_v3a1_page_number_20260831/opencv_hog_summary.json`
- `experiment_outputs/scanner_video_v3a1_page_number_20260831/tesseract_cli_summary.json`
- `experiment_outputs/scanner_video_v3a1_page_number_20260831/paddle_roi_summary.json`
- `experiment_outputs/scanner_video_v3a1_page_number_20260831/paddle_model_asset_manifest.json`
- `experiment_outputs/scanner_video_v3a1_page_number_20260831/preview_anchor_diagnostic.json`

## 미완료 및 다음 gate

1. 같은 페이지 positive만이 아니라 서로 다른 페이지 negative를 포함한 좌우 번호 golden 확보
2. 오른쪽 `309` 사용자 확인 또는 별도 사람 검수
3. 번호가 사람이 라벨된 연속 preview timeline으로 stable-K false/true page-change 평가.
   sparse clean anchor에서는 2 complete·1 partial을 관찰했지만 temporal 정확도는 미검증
4. Raspberry Pi 4에서 Paddle runtime 설치 가능성, warm latency와 RSS 측정
5. Pi가 부적합하면 digits-only ONNX/TFLite recognizer를 동일 runner로 평가
6. false duplicate 0 gate 뒤에만 번호-only duplicate 억제 활성화 검토

따라서 V3-A.1의 계약과 engine 연결은 사용 가능하지만, production page-number provider는 아직
Coordinator 기본 구성에 넣으면 안 된다. provider 미주입 시 V3-A visual fallback이 유지된다.
