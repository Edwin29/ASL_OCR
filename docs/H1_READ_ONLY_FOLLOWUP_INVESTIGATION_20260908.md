# H1 후속 독립 조사 — 2026-09-08

상태: **offline/현재 Laptop 재현 완료, live raw identity 추가 관측 대기, H1 미해결**.

사용자가 기존 코드 수정은 금지하고 새 조사 코드는 허용했다. 기존 product/firmware/harness/test/config 파일을 수정하지 않았다. 새 진단은 `docs/evidence/h1-investigation-20260908` 및 Laptop `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics\h1-investigation-20260908`에서 수행했다. Camera/서버 업로드/STM/audio 실행은 이번 조사에서 아직 없다.

## 1. 실행 identity와 fidelity

`diagnose_engine.py`는 보존된 replay의 import/class/function 정의만 AST로 읽고 top-level 실행과 수정 전 assertion은 실행하지 않는다. 실제 설치된 engine/collector와 기존 test fixture의 fake camera/analyzer/provider/manual clock을 사용한다. Collector subclass는 production method를 그대로 호출하고 epoch/reference/raw pair/consensus/match/timeout을 기록한다. Product file 수정은 없으며 process 종료 전 원래 class binding으로 돌린다.

Desktop과 Laptop 각각에서 실행했다. Engine hash는 Desktop `6ee44d42cae3456544e58c183c193f970b1467ef26a616feeb9ad6e563dfc380`, Laptop `f223f744fe2fd6a6818ea7bed4ed4f522e27f90590fc2c477fcb40fdbe8e427f`다. 각 결과에 실제 engine/collector/fixture hashes를 저장하고 이 네 파일의 실행 전후 불변을 확인했다. 이것이 repository 전체에 대한 hash 감사라는 뜻은 아니다.

Desktop/Laptop의 collector byte hash는 다르지만 이번 사례의 결과는 같았다. 최근 Desktop의 stale-latch/late-preparation 수정은 Laptop에 미배포이며 이번 사례로 그 수정의 live 수용을 주장하지 않는다.

이 replay는 원 H1의 camera/model/accepted bank/실행 instance를 복구하지 않는다. Record timing 사례는 별도 native query 진단의 elapsed/raw/status를 사용한다. Scope는 실제 코드의 조건별 동작 재현이다.

## 2. Actual-engine 결과

모두 N5/Ksame1/Kdifferent0/8000ms 유지. 표의 시각은 fixture query 시작 기준이며 live SLA가 아니다. 시작 offset, engine sampling tick과 phase도 결과에 영향을 준다.

| 시나리오 | Desktop/Laptop 공통 결과 | 의미 |
|---|---|---|
| 저장 native rows11개 | 8.007초 N1, 19.210초 N4, 27.219초 N2 timeout UNKNOWN; page change0 | 원 native stream timing으로 무진전 재현 |
| exact28/29, 간격1.5초 | 6.34초 N5 DIFFERENT/PAGE_CHANGED | Engine이 모든 changed page를 거부하는 것은 아님 |
| exact28/29, 간격1.8초 | 7.54초 N5 DIFFERENT/PAGE_CHANGED | 더 빠른 입력에서 진행 가능 |
| exact28/29, 간격1.95초 | 첫 window N4 timeout, 다음15.94초에 N5 통과 | 단순 평균 cadence 외에 window phase도 중요 |
| exact28/29, 간격2.0/2.05초 | 8.02/16.04/24.06/32.08초 각각 N4 timeout, PAGE_CHANGED0 | 지속적으로 정확한 pair가 와도 반복 폐기 가능 |
| exact28/29, 간격2.2초 | N4/N4/N3/N4 timeout, PAGE_CHANGED0 | 더 느린 입력에서도 무진전 |
| 2.05초 간격 + 추론800ms | N4 반복, PAGE_CHANGED0 | 20ms fixture만의 결과가 아님; 실제 acquisition 재현은 아님 |
| clean reference26/27에 query26/27 | N1 SAME 반복 | Ksame1의 계약상 예상 동작 |
| 서로 다른 pair5개 | N5 UNKNOWN timeout | valid count는 정확한 pair 합의와 다름 |
| 5번째 inference가 deadline 직전 시작, 직후 완료 | 8.5초 N5 DIFFERENT | 현 deadline은 추론 완료시각의 hard cutoff가 아님 |

Source boundary: `engine.py::_poll_opaque_page_change`는 sample 획득 전에 `collector.decision(now)`를 검사하고 timeout이면 collector를 새로 만들어 기존 partial observations를 버린다. SAME 및 hard reject에도 reset 경로가 있다. `opaque_identity.py::decision/_unknown`은 valid count 외 novel consensus와 reference match를 판정한다.

**확정 범위:** 실제 Laptop에서도 slow exact stream에 대한 수집 폐기 메커니즘이 재현됐다. H1 전체 incident root는 raw bank 부재 때문에 여전히 일부 미확정이다. 기존 `probable_product_risk / P1` severity를 유지하며 H1 해결 PASS로 바꾸지 않는다.

## 3. SAME/N5 UNKNOWN competing hypotheses

Synthetic reference bank를 `26/27` 네 개와 `28/29` 한 개로 만들고 query `28/29` 한 개를 넣으면 SAME N1, match1이 나온다. 이는 reference 내 모든 raw pair에 대해 Ksame1을 적용하는 현 계약상 동작이다. 실제 accepted bank에 이 오염이 있었다는 증거는 아니다.

따라서 원 run의 SAME은 실제 동일 페이지, query 오인식, reference의 잘못된 raw pair 중 어느 것으로도 가능하다. N5 UNKNOWN은 consensus 부족으로도 가능하다. Timeout 숫자만 조절해서 이 원인들이 해결된다고 볼 수 없다. Threshold 변경은 제안하지 않는다.

원 accepted bank가 보존되지 않았다면 새 진단도 과거 사실을 복구하지 못한다. 다음 live 수집은 현재 scene의 재현 가능한 원인을 좁히는 증거로만 사용한다.

## 4. Native recognizer 비용과 오류 계약

Laptop의 실제 hash-pinned M1을 사용해 보존된 production-native footer ROI4개를 각2회 처리했다. 새 `profile_saved_rois.py`는 실제 `_predict`를 호출하며 시간과 반환값만 기록한다. 어떤 inference도 생략하지 않았다. Network camera/서버/서보 없이 저장 PNG만 입력했다.

| 입력 | 결과 | 반환값에 쓰이지 않는 후속 predict 시간 |
|---|---|---|
| reference-left | 두 번 모두 `2441`, conflict, bbox458/294/72/22 | 0ms |
| reference-right | 두 번 모두27 | 약105/113ms |
| query-left | 두 번 모두28 | 약169/156ms |
| query-right | 두 번 모두29 | 약106/88ms |

Query pair 전체 인식 시간은 약437/378ms, 그중 후속 predict는 약275/243ms였다. 이는 이 두 PNG의 비용 회계이며 live sample cadence를 그만큼 개선한다는 보장은 없다. Snapshot latency, candidate processing, CPU 경합, 다른 ROI의 후보 수, provider cache도 다르다. Reference-left 오인식에는 후속 후보가 없어 이 최적화로 고쳐지지 않는다.

`PaddleRoiDigitRecognizer.recognize`는 후보를 최대4개 추론한 뒤 첫 valid candidate를 반환한다. 새 `check_late_exception.py`는 실제 recognize 메서드에 fake predictor를 주입했다. 처음 두 variant가 valid28이어도 세 번째 predict에서 RuntimeError를 던지면 현재 recognize는 예외를 전파한다. First-valid early return이면 이 예외가 실행되지 않는다.

**결론:** 결과 정상 경로의 불필요 비용은 실제 측정됐지만 early return은 exception-equivalent가 아니다. 이 변화가 허용 가능한 오류 계약인지 먼저 결정해야 한다. 원 native failure가 발생했다는 증거는 아니며 새 product defect로 승격하지 않는다.

## 5. 다음 packet과 기존 코드 수정 필요 여부

| 우선순위 | packet | 현재 판단 / 승인 경계 |
|---|---|---|
| 1 | Live reference/query raw 관측 | 기존 코드 수정 불필요. 새 `collect_live_phase.py`로 각30초 bounded 수집. 사용자 scene 준비 필요 |
| 2 | 실제 raw reference를 반영한 engine replay | 기존 코드 수정 불필요. 현재 synthetic bank에 의존하는 SAME 가설을 더 좁힘. Diagnostic reference는 V4 accepted bank라고 부르지 않음 |
| 3 | Recognizer early-return 설계 | 실제 이익은 있으나 오류/diagnostic/counter semantics 선택 필요. 구현한다면 recognizer1파일 및 targeted tests 범위의 별도 승인 대상. 카메라 안정적 liveness를 단독 보장하지 않음 |
| 4 | Collector budget/lifecycle 설계 | 정확한 입력에도 N4 반복 폐기 재현. 단순 first-valid clock으로도 4×2.05=8.2초라 충분하지 않음. Across-window 유지/sliding window는 reset·epoch contract 변화 가능성이 있어 국소 수정으로 가정하지 않음 |
| 5 | App input/cancel scheduling 계측 | 기존 기록상 synchronous provider가 lock을 보유한다. 실제 지연 상한과 late-result fencing을 먼저 측정. Worker 도입은 별도 design 승인 대상 |

**현재 조사에는 기존 코드 수정이 불가피하지 않다.** 해결을 구현하려면 product 변화가 필요할 수 있지만 아직 원인 전체와 후보 계약을 닫지 못했다. 따라서 코드 수정 요청/적용은 하지 않는다. 새 layer·8초 증가·N/K 완화는 구현하지 않는다.

## 6. Live 진단 준비 및 한계

새 phase collector는 Android production source + ThreadedPreviewCameraSource + native-preview ROI/M1을 사용한다. GUI preview 대신 no-op preview이며 DeviceApplication/actual engine scheduling/V4/S1을 실행하지 않는다. Sample start 간격은 policy observation interval을 사용하지만 full production cadence와 같다고 주장하지 않는다.

Phase별 최대30초(진행 중 동기 read/inference/stop은 deadline 뒤 끝날 수 있음), source image 최대3개, raw pair/status/ROI hash/analyzer·recognition timing을 새 C: runtime에 기록한다. 저장 I/O도 cadence에 영향을 줄 수 있으므로 recorded timing으로 full app SLA를 직접 판정하지 않는다. 모델 load는 phase 시간 밖이다. 기존 endpoint/auth/TLS 설정을 읽으며 변경하지 않는다. 예외 메시지에 credential이 들어갈 가능성을 피하려고 예외 class만 result에 남긴다.

26/27 reference부터 관측하고 결과 확인 후 사용자가28/29로 넘긴 뒤 query를 수집한다. FAIL은 기록하고 독립 phase 진행 여부를 판정하며 자동으로 camera/threshold를 바꾸지 않는다. 현재 사용자 준비 응답을 기다리고 있고 live 요청은 아직 보내지 않았다.

## 7. Evidence index / 완료 상태

- `docs/evidence/h1-investigation-20260908/desktop-result.json`
- `docs/evidence/h1-investigation-20260908/laptop-result.json`
- `docs/evidence/h1-investigation-20260908/native-cost-result.json`
- `docs/evidence/h1-investigation-20260908/late-exception-result.json`
- 새 코드: `diagnose_engine.py`, `profile_saved_rois.py`, `check_late_exception.py`, `collect_live_phase.py`(syntax 확인만; live 미실행)

Actual-engine 11 scenarios×2환경 및 synthetic bank probe, native ROI8회, late-exception fixture 실행 완료. 체크 PASS는 결함 메커니즘 재현 성공이지 integration PASS가 아니다. H1 sequence2/fresh READY는 미검증이며 H4 BLOCKED 유지. **기존 코드 수정0 / firmware flash0 / live camera 요청0 / upload0 / FRAME0**.

## 8. Live reference-01 실행 및 phase 불일치

위 live 미실행 상태 이후 사용자가 준비를 보고하여 새 `live-reference-01`을 실행했다. Exit0, 30초 budget, sample26개, 4000×3000 원본, eligible14개, page_not_found/seam_failed12개다. Pair는28/29 8회, 기타 좌측 오인식 pair6회, missing12회였다. TLS warning과 `Invalid SOS parameters for sequential JPEG`가 출력됐으나 process는 정상 종료했고 source images를 decode·저장했다. Warning만으로 fatal 원인을 확정하지 않는다.

보존된 source-0.png를 직접 확인한 결과 실제 인쇄 페이지 번호가 **28/29**다. 따라서 이 run은26/27 reference 수용에는 INVALID(scene mismatch)이며 product의26→28 오인식 증거가 아니다. 기존 phase label과 파일은 유지하고 이 정정으로 연결한다. 실제28/29 candidate/recognizer 관측은 별도 제한 evidence로 보존한다. 나머지 모든 frame의 육안 검증은 하지 않았다.

26/27로 변경한 새 reference phase를 제안한다. 실패한 파일을 덮어쓰거나 이 phase를 accepted reference bank로 사용하지 않는다. 이후28/29 query를 새로 수집하여 시간 순서를 명확히 한다. 카메라 설정/threshold/code 기존 파일 변경0, upload0, FRAME0은 유지되며 camera 요청은 이번 phase부터 발생했다.

Evidence: `docs/evidence/h1-investigation-20260908/live-reference-01-result.json`, `live-reference-01-source-0.png`; Laptop 원본 root는 diagnostics/h1-investigation-20260908/live-reference-01이다.

### Live reference-02: 실제26/27 확인

사용자 재준비 후 새 live-reference-02 실행은 exit0, sample25개로 종료됐다. source-0.png의 인쇄 번호26/27을 직접 확인했다. Candidate eligible11개 중 complete raw pair8개는 모두26/27이며 나머지3개는 pair 없음이다. Candidate reject14개(page_not_found/seam_failed12개, content_occluded2개)를 포함하면 전체 pair 없음17개다. 처음10개 관측에는 complete pair가 없었다. 따라서 정확한 reference raw 관측을 확보했지만 acquisition/gating 지연도 함께 기록하며 fresh capture PASS로 표기하지 않는다.

TLS/JPEG SOS 경고는 반복됐지만 이번에도 process는 정상 종료했다. 다음28/29 query phase는 이 reference 수집과 별도 run으로 진행한다. 두 phase 사이 continuous production engine/state/V4가 없다는 fidelity 한계를 유지한다. 기존 코드 변경0, upload0, FRAME0.

Evidence: `live-reference-02-result.json`, `live-reference-02-source-0.png`(동일 Desktop evidence root); Laptop diagnostics/h1-investigation-20260908/live-reference-02.

### Live query-01 및 두 phase actual-engine replay

사용자가28/29 준비 후 query30초 수집을 실행했다. Exit0, sample25개, eligible15개, candidate reject10개(page_not_found/seam_failed)다. Eligible15개 중 완전한 raw pair는5개로,28/29 3개(10.812/15.375/25.437초),248/29 1개(17.687초),28/0214 1개(26.719초)다. 나머지10개 eligible sample도 좌우 pair를 만들지 못했다. 저장 source-0의 인쇄28/29를 직접 확인했다.

`replay_live_pair.py`를 새로 작성해 Laptop actual engine에 query row의 raw/status/timing/rejection을 재생했다. Reference phase의 첫5개 완전한 pair는 모두26/27임을 assert했고, fixture는 이 다섯 값과 같은 reference를 만든다. 실제 V4 receipt/원 bank/frame hash/visual fingerprint를 복원한 것은 아니다.

| Replay | 결과 | 해석 |
|---|---|---|
| 실제 row timing/rejection 유지 | WAITING_FOR_PAGE_CHANGE, PAGE_CHANGED0 | 이번 scene의 무진전 메커니즘 재현 |
| Candidate reset만 가정상 제거 | N0/N2/N1/N2 timeout 반복, PAGE_CHANGED0 | Candidate gate만 우회해도 충분하지 않음 |
| 완전한5 pair를1초 간격으로 압축한 counterfactual | 4.3초 N5 DIFFERENT/PAGE_CHANGED | 같은 raw값도 보존·집계될 경우 consensus3으로 통과 가능 |

후자의 두 조건은 원인 분리를 위한 **counterfactual**이며 acceptance가 아니다. Gate/timeout/threshold를 변경하라는 제안도 아니다. 이번 live pair는 reference와 일치한 query가 없어 SAME을 재현하지 못했다. 원 H1의 SAME 원인은 계속 미확정이다.

### Saved source에서 candidate 실패 위치 추가 확정

새 `inspect_saved_candidates.py`는 Laptop actual analyzer와 segmenter를 그대로 실행하고 Python trace로 조건식의 locals만 읽었다. Reference/query 각각 source-0 PNG에서 live와 같은 page_not_found/seam_failed를 재현했다.

- 두 장 모두 오른쪽 page mask는 존재하고 왼쪽 page mask가 없다.
- 왼쪽 segmenter는 external contour1개/candidate1개를 찾았지만 최종 multi-signal score가 reference **0.590718**, query **0.605396**로 현 min_score **0.62** 미만이라 mask를 반환하지 않았다.
- 그 결과 analyzer의 page_pair_found=false, seam_proxy=None이 되어 PAGE_NOT_FOUND/SEAM_FAILED를 추가한다. 이 두 sample에서 seam 자체가 별도의 최초 실패는 아니다.
- Threshold를 낮추지 않았다. 육안 가독성과 mask 계약은 다르며, 이 결과만으로 threshold defect로 확정하지 않는다. Scene 구성/명암/경계 support와 고정 detector의 적합성 문제는 추가 분리가 필요하다. 이두 저장 frame의 first failing boundary는 확인됐지만 나머지 실패 frame 전체에 일반화하지 않는다.

현재 H1은 **(1) candidate mask 탈락 → (2) eligible frame에서도 footer pair 누락/오인식 → (3) partial identity timeout/reset**의 복합 경로로 조사 범위가 좁혀졌다. 기존 slow-exact liveness 재현은 유효하지만 이번 scene에 대해 그 수정만으로 충분하다고 주장할 수 없다.

### 다음 우선순위와 사용자 상태

1. 저장 frame에서 왼쪽 contour score 구성과 footer ROI 선택을 비교해 scene 경계·localization 영향을 분리한다. 기존 코드 수정 없이 새 계측으로 가능하다.
2. 필요하면 사용자에게 한 번의 bounded scene 조정을 제안하되 조정 전후를 다른 run으로 기록한다. Camera 설정/해상도/threshold는 바꾸지 않는다. 무기한 위치 조정 반복은 하지 않는다.
3. Candidate/identity 품질과 cadence를 확인한 뒤 liveness correction packet을 선정한다. Early-return, collector lifecycle, app scheduling은 서로 다른 계약으로 검토한다.

수집·replay process는 모두 종료됐다. 사용자의 추가 조작은 지금 요구하지 않는다. 기존 코드 수정0, upload0, FRAME0이며 새 진단 파일2개 추가(`replay_live_pair.py`, `inspect_saved_candidates.py`). Fresh H1/READY/H4는 미수용이다.

Evidence: `live-query-01-result.json`, `live-query-01-source-0.png`, `live-pair-replay-result.json`, `saved-candidate-result.json`.

## 9. 실제 snapshot 비율 미리보기 재사용

사용자가 camera 앱 화면비와 snapshot 실제 pixel 비율 차이 때문에 조정이 어렵다고 보고하여 기존 preview 재사용을 검토했다. `OpenCVOperatorPreview.show`는 입력 width 기준 동일 배율로 height도 resize하며 `_annotate_preview`는 전체 raw frame에 mask/상태를 그린다. Candidate preview640×480과 M1 native4000×3000은 구분한다. 기존 코드만으로 스마트폰 앱 자체 화면비를 교정할 수는 없지만 실제 snapshot 전체 시야를 표시할 수 있다.

새 `show_candidate_preview.py`는 기존 snapshot/threaded source/analyzer/annotation/OpenCV window를 조합한다. 같은 analyzed frame에 mask를 표시하여 latest frame과 과거 mask 혼합을 피한다. 화면1920×1080에서 비율 유지 display width1123, 입력4:3이면 height842를 사용한다. OCR/서버/STM은 우회하고 Q로 종료 또는 최대600초다. Native4000 입력 자체를 변경하지 않는다. 임의 window 수동 resize 후 비율 동작은 아직 사용자 수용 전이다.

수동 실행 전용 scheduled task `ASL_H1_CandidatePreview_20260908_01`을 Interactive user로 생성해 실행했다(반복 trigger 없음). Python PID31952/session3으로 실행됐지만 첫 sample 전에 `SnapshotTransportError`로 종료됐다. UTC14:04:30 시작→14:05:11 종료, sample0. 따라서 창 표시 성공으로 보고하지 않는다. Endpoint/auth/TLS/config 변경은 없고 camera 접근 복구가 선행 조건이다. 원인은 전화 앱/네트워크/endpoint 중 미확정이며 credential을 다시 요청하지 않는다.

Laptop evidence: diagnostics/h1-investigation-20260908/candidate-preview-01/result.json 및 stderr.txt. 기존 코드 수정0, 새 진단 실행기1개. 다음은 사용자에게 Android camera 앱 실행/동일 Wi-Fi 상태 확인을 요청하고 새 run으로 재시도하는 단계다.

사용자 준비 응답 뒤 기존 진단 실행기를 새 `preview-retry02` 폴더에 복사해 원본·실패 evidence를 보존한 채 동일 interactive task의 action만 갱신했다. PID26132/session3, UTC14:06:40 시작. `ready.json`에서 실제4000×3000 sample1과 display max_width1123을 확인했다. 사용자가 화면을 볼 수 있는지 및 전체 page 경계가 표시되는지 확인할 단계다. 미리보기의 ready는 candidate 단일 frame 상태이며 Scanner N5/identity/receipt/READY 수용을 뜻하지 않는다. Q/창닫기 또는600초 budget으로 종료하며 upload/STM/OCR0이다.

### 사용자 미리보기 확인·위치 조정 후 결과

사용자는 창 표시와 위치 조정을 보고했다. 확인 시 최근25 frame(UTC14:10:40~14:11:10) 모두 page_pair=true/reasons없음, mask_confidence_min 약0.835~0.864였다. `preview-adjustment-observation.txt`로 보존했다. 미리보기는 stop marker로 정상 종료(총236 sample)한 뒤 다른 camera consumer 없이 OCR phase를 실행했다.

새 `live-query-adjusted-01`은 exit0,22 sample 모두 candidate eligible,28/29 pair21개, pair없음1개였다. source-0.png에서 실제28/29와 달라진 배치를 확인했다. 처음5 pair 시작은1.625/3.157/4.407/5.704/6.704초다. 설정·threshold·production source 변화 없이 개선됐다.

같은 Laptop engine replay에서 recorded adjusted timing/raw/rejections를 그대로 넣으면 **7.385초 N5 DIFFERENT/PAGE_CHANGED**가 나왔다. 이는 기존26/27 raw값 기반 fixture bank를 사용한 isolated replay다. Reference 영상은 조정 전이므로 같은 배치의 real reference/visual epoch 및 continuous production pipeline 수용이 아니다. Live V4/READY 성공으로 승격하지 않는다.

이번 evidence는 scene framing을 실제 snapshot preview로 조정하는 것이 이 scene의 후보/인식 품질을 회복할 수 있음을 지지한다. 조정 전 모든 원인을 사용자 조작으로 소급하거나 slow-exact timeout risk가 사라졌다고 결론내리지 않는다. 다음은 현재 카메라/책 위치를 유지한26/27 reference를 확보해 양 spread를 같은 배치에서 검증하는 단계다.

Evidence: `live-query-adjusted-01-result.json`, `live-query-adjusted-01-source-0.png`, `adjusted-pair-replay-result.json`. 기존 코드 수정0, upload0, FRAME0. Preview와 OCR phase process는 종료됨.

### 조정된 배치의26/27 reference 확인 완료

`live-reference-adjusted-01`은30초 budget, exit0,23 sample 모두 candidate eligible이며23/23 raw pair가26/27이다. 첫5 pair sample 시작은1.453/2.797/4.047/5.219/6.532초다. source-0.png의 인쇄26/27을 확인했다. 사용자에게 카메라/책 위치를 유지하고 page만 바꾸도록 안내한 조건이다.

새 reference의 첫5 raw값으로 fixture bank를 검증하고 기존 adjusted query timing을 재생한 `both-adjusted-replay-result.json`도7.385초 N5 DIFFERENT/PAGE_CHANGED였다. 실제 수집 순서는query→reference이며 별도 process 두 개다. 따라서 continuous26/27→28/29 transition이나 실제 accepted bank/receipt 검증이 아니다. 기존 replay와 reference raw값이 같아 결과가 동일한 것이며 독립적인 두 번째 live page-change PASS로 세지 않는다.

| Phase | Candidate eligible | Exact pair |
|---|---|---|
| 조정 전 reference | 11/25 | 8/25 |
| 조정 전 query | 15/25 | 3/25 |
| 조정 후 query | 22/22 | 21/22 |
| 조정 후 reference | 23/23 | 23/23 |

이로써 미리보기를 사용한 scene 조정으로 양쪽 demo spread의 검출/identity 품질이 개선된 증거를 확보했다. General OCR 개선·모든 scene 통과·기존 timeout 위험 해소를 뜻하지 않는다. 기존 코드 수정은 현재까지 불필요했고 하지 않았다. 다음 gate는 동일 배치의 continuous Scanner lifecycle 검증, 이후 source alignment 승인 조건을 충족한 fresh H1의 두 receipt/finalize/READY다. 진단 process는 종료했고 추가 사용자 조작은 지금 요청하지 않는다.

Evidence: `live-reference-adjusted-01-result.json`, `live-reference-adjusted-01-source-0.png`, `both-adjusted-replay-result.json`. 기존 코드 수정0/upload0/FRAME0 유지.

## 10. 동일 배치의 continuous Scanner diagnostic — 완료

Run `continuous-20260908-233514` (UTC 14:35:14~14:36:52), Laptop PID28416. 사용자에게26/27 유지 후 첫 bank 등록을 확인한 시점에28/29로 넘기도록 안내했고 사용자는 완료를 보고했다. `user-turn-completed.txt`는 assistant가 응답을 받은 시각이며 실제 손 움직임 시각이 아니다.

새 `continuous_scanner.py`만 작성했다. 실제 LocalBookScannerEngineFactory의 camera acquisition, analyzer, native M1, UVDoc preparation, filesystem artifact store, SampledFrameEngine을 사용했다. staging/ready만 새 C: run에 격리했다. 설정된 threaded acquisition은 유지하고 GUI sink만 NullPreview로 대체했다. SSH 연결을 유지하는 비대화형 실행으로 DeviceApplication scheduling/audio context는 시험하지 않았다. 최초 Start-Process 시도는 관측 시 run 폴더가 없었으며 정확한 종료 원인은 미확정이다. 연결 유지 방식 실행은 정상 완료했다.

첫 artifact의 delivery_queued/delivery_confirmed는 새 진단 코드가 호출했다. receipt 문자열은 `DIAGNOSTIC-NOT-V4-first-artifact`이며 실제 outbox/V4 durable receipt가 아니다. 다만 bank 자체는 이번 연속 실행에서 관측한 실제5 pair로 생성됐으며 fixture bank를 주입하지 않았다. 두 번째 artifact는 서버 전달 없이 종료했다.

| 경계 | 결과 / monotonic |
|---|---|
| 첫 candidate identity | 183414.562 N5 DIFFERENT, consensus5, timeout=false |
| 첫 local artifact | 183420.156, source frame00000003 |
| 첫 bank 등록 | 183420.171, depth5, 진단용 receipt |
| 동일 페이지 대기 | SAME37회;26/27 digest 일치 |
| 새 페이지 수집 | 183474.230~183479.515,28/29 N1→N5 |
| PAGE_CHANGED | 183479.515, coherent numeric pair, match0/consensus5 |
| 둘째 candidate identity | 183489.187 N5 DIFFERENT |
| 둘째 local artifact | 183493.250, source frame00000063 |
| 종료 | idle, camera_resource_released=true, PID 종료 확인 |

이번 PAGE_CHANGED는 `opaque_footer_coherent_numeric_pair` 경로이며 visual_match_kind=ambiguous/visual_stable_count=0이다. 따라서 visual-only page-change gate 통과를 주장하지 않는다. 첫 유효 query 관측부터 결정까지 약5.285초이며 손 넘김 완료부터의 latency는 아니다.

Frames evaluated61, selected2, processed2, dropped0. Opaque valid52/missing0/unknown timeouts0/hard rejected3. Raw reason은 content_occluded2/page_not_found1이며 이후 회복했다. Native stderr에 `Invalid SOS parameters for sequential JPEG`가 관측됐지만 이 run에서 fatal로 이어지지 않았다. 경고를 숨기거나 decoder root cause를 확정하지 않았다.

각 artifact의 L/R source_frame_id가 일치하고 실제 Laptop 파일4개의 SHA-256이 artifact ref와 일치함을 독립 read-back으로 확인했다. 각 spread manifest와 artifact refs, 전체 events180개, policy/config hash/import identity/result를 Desktop evidence에 복사했다. 이미지 원본은 Laptop isolated ready 경로에 보존되어 있으며 파일 목록/크기/hash는 `artifact-files.json`에 있다. `verification.json`의26/27 및28/29 digest 계산은 production token serialization과 같은 NUL 구분식을 사용했고 live event digest와 일치한다.

**판정: continuous Scanner diagnostic의 두 local artifact + page-change 경계 PASS.** 실제 live camera와 실제 준비·identity lifecycle의 연속성이 이전 recorded replay보다 추가 검증됐다. Slow-exact 8초 timeout risk가 일반적으로 해소됐다는 뜻은 아니다. N5/Ksame1/Kdifferent0/8000ms 및 candidate/duplicate threshold 변경0. 기존 product source 수정0, upload0, FRAME0.

실행 engine hash는 기존 Laptop `f223f744fe2fd6a6818ea7bed4ed4f522e27f90590fc2c477fcb40fdbe8e427f`이며 최신 Desktop checkpoint의 engine과 다르다. Imports는 모두 C:/ASL_OCR_INTEGRATION 아래임을 확인했다. 이 결과를 최신 Desktop source의 hardware acceptance로 재표기하지 않는다.

다음 gate는 배포 source identity를 명시적으로 정렬·검증한 뒤, 같은 scene에서 production DeviceApplication/Coordinator + console controls의 fresh H1 두 durable receipts/CONFIRM LONG/fresh READY를 검증하는 것이다. 별도 승인 없이 source를 배포하거나 upload run을 시작하지 않았다. Audio/physical controls/physical CLEAR 및 H4 미완료 상태는 유지한다. 사용자는 현재28/29 배치이며 추가 조작은 아직 필요 없다.

Evidence: `docs/evidence/h1-investigation-20260908/continuous-20260908-233514/` 및 새 `continuous_scanner.py`.
