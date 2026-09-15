# 현재 배치의 Laptop 라이브 Scanner 재검증

## 결과

사용자가 배치를 유지한 상태에서90초 실행했다. **첫 local artifact 생성 실패**, identity timeout5회. 프로세스는 정상 종료(exit0)했고 source release 및 증거 파일 저장 성공을 확인했다. 종료코드0은 촬영 PASS가 아니다.

현재 조건에서 Laptop에서도 실패가 재현되므로 Pi의 느린 연산만으로 현상을 설명할 수 없다. 하지만 이번 결과만으로 전처리 제품 결함을 확정하지 않는다. 원본 선명도/페이지 마스크/ROI 및 후보 선택/카메라 추가 요청 부하가 분리되지 않았다. 이전 H1의 두 durable receipt 및 fresh READY 성공은 유지한다.

## 범위와 source identity

- Laptop `C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe` 및 device/scanner/parser imports가 모두 `C:\ASL_OCR_INTEGRATION` 아래임을 확인.
- 기존 성공 H1 config: `hardware-integration/h1-fresh-aligned-20260908-2350/config/device-app.h1-camera-console.toml`.
- config SHA256 `847f07d87f65789359902b4545168a85e513bc6aeed070bdf984d61ce723e11c`: Desktop의 당시 `docs/evidence/h1-fresh-aligned-20260908/run-manifest.json`과 일치.
- 실행 engine SHA256 `6ee44d42cae3456544e58c183c193f970b1467ef26a616feeb9ad6e563dfc380`: 당시 aligned H1 기록과 일치. repository 전체 source/environment 동일성을 새로 재구축한 검사는 아니다.
- production `LocalBookScannerEngineFactory` 및 실제 Scanner state machine/Android acquisition/provider/preparer를 사용했다. Factory subclass는 GUI sink만 NullPreview로 바꾸고 설정된 `ThreadedPreviewCameraSource` acquisition을 유지했다. 별도의 상시 미리보기05는 유지됐다.
- staging/ready는 새 isolated run으로 변경. 원본3개/마스크3개, 첫 ROI6개, 첫 모델 입력12개를 제한된 별도 writer로 저장했다. 배열 copy/디스크 작업 부하가 포함된다. HTTP/Paddle/판정값/예외를 바꾸지 않았다.
- **DeviceApplication/Coordinator, console/물리 입력, outbox, V4, S1, TTS, STM은 미실행**. 따라서 이 결과는 현재 조건의 Scanner 첫 산출물 경계이며 전체 H1 재수용이 아니다. 실제 artifact 이후 경계는 선행조건 미충족으로 실행하지 않았다. 가짜 receipt 없음.

## 유지한 기준과 관측

`preview_native`, query N5, reference bank5, Ksame1/Kdifferent0, max_collection8000ms, opaque observation_interval100ms, max_recognition_in_flight1 유지. candidate sampling과 opaque sampling의 간격은 서로 다른 설정이다. 간격 설정이 실제 처리 완료 속도를 보장하지 않는다.

| 항목 | 결과 |
|---|---|
| frames received/evaluated | 25/25 |
| candidates selected | 5 |
| frames processed / artifact | 0 / 0 |
| opaque valid / missing | 4 / 6 |
| timeout 시 유효 관측 | 0, 0, 2, 1, 1 |
| unknown timeout | 5 |
| 마지막 recognition processing | 약1.067초 |
| 마지막 effective interval | 약3.765초 |
| 종료 직전 상태 | local_retry |
| cancel latency | 약1.297초 |
| camera_resource_released | true |
| evidence_writes_ok | true |

첫 실패 경계는 **candidate identity collection**이다. 후보를 찾지 못하는 상태만 지속된 것이 아니며, 유효 쪽 식별 관측이 충분히 모이지 않아 준비/산출물 단계로 넘어가지 못했다.

## 영상 관찰과 해석 한계

- 실제 recognizer로 들어간 `roi-0-left.png`는26이 비교적 선명하고, `roi-1-right.png`의27 및 주변 인쇄는 눈에 띄게 흐리다. 오른쪽 번호는 ROI 안에 존재한다.
- 이것은 현재 입력/공통 전처리 품질을 우선 조사할 근거다. 초점/카메라 흔들림/영상 해독/마스크/후보 선택 중 어디서 차이가 처음 생겼는지는 아직 확정하지 않는다.
- 원본 저장은 첫 analyzer 호출3개, ROI 저장은 첫 recognizer 호출6개라서 둘을 무조건 동일 프레임의 전후쌍으로 연결할 수 없다. 다음 세부 품질 재현에서는 frame ID를 연결해 동일 프레임 원본→mask→ROI→model input을 저장해야 한다. 이번 원본과 ROI를 근거 없이 정확한 전후쌍으로 비교하지 않는다.
- native stderr에 JPEG SOS 경고가 있었다. 이 run에서 fatal decode exception은 보고되지 않았다. 경고를 원인 확정이나 무해 판정으로 사용하지 않는다.
- 상시 미리보기는 별도 source 요청을 하므로 과거 H1의 단일 요청 구조와 부하 차이가 있다. 저장 writer 부하도 있다. 따라서 현재 Laptop 결과의 시간 지연을 전부 영상 품질이나 CPU에 귀속하지 않는다. 이전 Pi A/B의 중복 요청 비교를 이 Laptop 부하 차이의 완전한 반증으로 재사용하지 않는다.

## 다음 판단

1. 현재 scene 품질/공통 후보 선택 문제를 Pi 최적화와 별도 이슈로 유지한다. Laptop에서도 실패했으므로 Pi 성능 수정만으로 완전 해결을 약속할 수 없다.
2. 동일-frame ID로 원본/마스크/ROI/모델 입력을 연결하는 제한된 계측과, 미리보기를 실제 Scanner 프레임으로 공유하는 단일 camera-client 조건이 다음 품질·지연 분리에 필요하다. 제품 코드 변경 전에 진단 실행기에서 확인한다.
3. 품질 개선 후 기존 N5/8초에서 first artifact가 생성되는지 다시 확인하고, 그 다음에만 fresh H1 upload/READY 경계를 검증한다.

기존 H1 성공을 무효화하지 않으며, 이번 FAIL을 `confirmed_product_defect`로 승격하지 않는다. root cause 분류는 **insufficient_evidence**, 현재 조건의 경계 실패는 관측 사실이다. 추가 제품 수정0, credential/config/threshold/firmware 변경0. 미리보기는 계속 유지한다.

Evidence: [laptop-live-recheck-20260915](evidence/laptop-live-recheck-20260915/), run `laptop-live-1789477771141334500`의 manifest/policy/events/result, lossless PNG 및 `run.log`, 재현 스크립트 `probe_laptop_live.py`.

## 추가 비교: 미리보기 종료 후 같은 검사

사용자가 미리보기를 닫고 같은 검사를 요청했다. preview05 stop marker 정상 종료를 확인했고, `pi-focus-20260915` 관련 Python/pythonw 프로세스0개 확인 후 다음 run을 시작했다. 미리보기는 다시 열지 않았다.

Run `laptop-live-1789478171636106300`, `probe_laptop_live_preview_off.py`. 앞선 스크립트와의 변경은 manifest의 미리보기 유무/설명뿐이다. config/engine hash, factory의 configured threaded acquisition,90초 budget 및 동일한 bounded PNG writer를 assert로 비교했다. Scanner 자체의 수신 worker는 끄지 않았다. 제품 변경0, 업로드/receipt/STM/audio0.

| 항목 | 미리보기 켬 | 미리보기 끔 |
|---|---:|---:|
| 90초 첫 local artifact | 0 | 0 |
| frames evaluated | 25 | 29 |
| candidates selected | 5 | 6 |
| opaque valid / missing | 4 / 6 | 3 / 8 |
| unknown timeout | 5 | 5 |
| emitted effective interval 중앙값 | 3.765초(9개) | 3.359초(10개) |
| recognition processing 중앙값 | 1.083초(10개) | 1.040초(11개) |

끔 run의 각 timeout 시 유효 관측0,0,0,1,1. 마지막 검증 회차 도중90초 budget에 도달하여 종료했고, 그 미완료 회차를 timeout으로 추가 집계하지 않았다. exit0, state_before_close=verifying_identity, camera_resource_released=true, evidence_writes_ok=true. 최초 실패 경계는 동일한 candidate identity collection이다.

**미리보기 추가 요청을 제거해도 실패가 지속됐다.** 관측 간격 중앙값은 약0.406초 짧아졌지만, 순차 실행의 영상/환경 변동이 남아 있으므로 이 차이를 전부 미리보기 효과로 단정하지 않는다. 미리보기가 유일한 원인이라는 설명은 지지되지 않는다. 현재 영상/공통 전처리 및 수집 속도 문제를 계속 분리해야 하며, 기존 무손실 ROI의 정확도 실패와 Pi의 별도 성능 차이 결과도 유지한다.

추가 evidence: `preview-closed-result.json`, `preview-off-manifest.json`, `preview-on-off-comparison.json`, 끔 run의 raw events/result/PNG, `run-preview-off.log`. 검사 후 미리보기는 **닫힌 상태**로 유지했다.
