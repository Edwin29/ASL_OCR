# Pi4 / Laptop 동일 ROI·스레드 비교 — 2026-09-15

## 판단

후속 [현재 조건 Laptop 라이브 재검증](LAPTOP_LIVE_RECHECK_20260915.md)에서는 실제 Scanner90초 검사에서 첫 산출물0/identity timeout5회를 관측했다. 현재 scene의 품질/공통 전처리와 부하 조건을 Pi의 성능 차이와 별도로 조사해야 한다. 이전 H1 성공은 유지한다.

**현재 Pi 실행 환경의 연산 성능 차이가 identity timeout의 주요 기여 요인이라는 가설을 강하게 지지한다.** 동일 무손실 ROI를 인식하는 데 Pi는 Laptop 기존 설정보다 약5.27배, 단일 스레드 Laptop보다도 약3.80배 오래 걸렸다. 단일 스레드 제한만이 원인이라는 설명은 불충분하다.

CPU 자체만의 배율로 단정하지 않는다. ARM/x86, Paddle3.2.2/3.3.1, native kernel/backend 차이가 함께 남아 있다. 이를 확률 수치로 환산할 근거는 없다. 이번 결과는 코드 변경/부팅 복구/전체 H4 수용 결과가 아니다.

## 실험 계약

- 동일한 lossless source PNG에서 Pi production candidate/preview ROI 함수를 한 번 실행해 left/right PNG를 만들었다. 각 호스트는 같은 파일을 직접 읽었으며 PNG 파일 SHA256, 디코딩한 픽셀 SHA256을 assert했다. 원본 영상으로부터 ROI를 호스트마다 다시 추출하지 않았다.
- 기존 `PaddleRoiDigitRecognizer.recognize()`와 `_predict()`를 사용했다. 두 함수의 source hash, 모델 파일5개 hash, 판정 policy, 각 `_predict`의 입력 픽셀 hash까지 세 조건에서 일치했다.
- Pi: 승인된 ARM CPU 단일 스레드 제품 어댑터 그대로. Laptop 기존: 생성자 옵션을 추가하지 않음. Laptop 단일 스레드: 해당 진단 프로세스 안에서 `TextRecognition` 생성자에만 `cpu_threads=1`을 주입한 뒤 생성자 함수를 복구했다. 제품/설정 파일 수정 없음.
- 각 조건 별 독립 프로세스. 모델 로드 및 최초1회/cold를 분리하고 추가2회 예열, 이후 좌우 각각7회 측정. 매번 `recognize()` 직접 호출; provider cache로 추론을 생략하지 않음. 입력 배열이 변경되지 않았는지도 매회 assert했다.
- 실제 모델 추론은 매 round 좌4회/우2회였다. 재생산된 같은 ROI 반복을 서로 다른5개 live frame이나 capture acceptance로 사용하지 않는다.
- Pi와 Laptop 기존 조건은 서로 다른 장치에서 동시 실행, Laptop 단일 스레드는 기존 조건 종료 후 같은 호스트에서 별도로 실행했다. Laptop 상시 미리보기는 세 조건 동안 유지했다. 실험 코드의 카메라/업로드/serial/audio 호출은0이다.

## 측정 결과

단위 초. 좌우 합계는 같은 round의 좌/우 소요시간 합을 구한 뒤 중앙값을 냈다.

| 조건 | 왼쪽 중앙값 | 오른쪽 중앙값 | 좌우 합계 중앙값 | 합계 범위(7회) |
|---|---:|---:|---:|---:|
| Laptop 기존 설정 | 0.272 | 0.163 | **0.422** | 0.390~0.470 |
| Laptop `cpu_threads=1` | 0.382 | 0.204 | **0.586** | 0.537~0.636 |
| Pi production `cpu_threads=1` | 1.479 | 0.748 | **2.227** | 2.225~2.238 |

- Pi / Laptop 기존 = **5.271배**.
- Pi / Laptop 단일 스레드 = **3.797배**.
- Laptop 단일 스레드 / Laptop 기존 = **1.388배**. 이 조건에서 단일 스레드는 약39% 느렸으나 Pi의 전체 차이를 설명하지 못한다.
- 세 프로세스 모두 exit0. native crash/추론 예외/입력 변경 assertion 실패 없음.

모델 로드 시간은 각각 약0.688/1.113/0.429초이며 위 steady-state 합계에 포함하지 않았다. import/DLL 로드/시스템 파일 cache가 통제되지 않아 모델 로드 시간으로 장치 우열을 해석하지 않는다. 기존 조건의 숫자상 유효 thread count는 계측 객체에서 얻지 못했고, 검증한 것은 생성자 옵션 생략과 명시1의 차이다. 기존 설정을 임의로 '10 threads'라 표기하지 않는다.

## 인식 결과의 일치와 제한

세 조건에서 측정7회 모두:

- 왼쪽: raw `26`, `observed`, variant agreement2.
- 오른쪽: raw `1`, `conflict`, variant agreement1. 최종 유효27 판정이 아니다.
- 모델 입력 crop/variant의 픽셀 hash와 호출 순서가 일치했다. confidence의 완전한 bitwise 일치까지 주장하지 않는다.

따라서 **이 표본의 오른쪽 인식 실패는 Pi CPU가 느리다는 이유만으로 생기는 현상이 아니다.** Laptop에서도 같은 결과를 냈다. 동시에 이 표본은 양쪽 인식 성공 fixture가 아니므로, 다른 입력에 대한 정확도/일반화를 이 결과로 판단하지 않는다.

## 환경 확인

| 항목 | Laptop | Pi |
|---|---|---|
| CPU | Intel Core i5-1135G7, 4 cores / 8 logical | Raspberry Pi4 ARM64 |
| Python | 3.11.9 | 3.13.5 |
| Paddle | 3.3.1 | 3.2.2 |
| PaddleOCR | 3.7.0 | 3.7.0 |
| NumPy | 2.3.5 | 2.3.5 |
| OpenCV | 5.0.0 | 4.10.0 |
| Torch | 2.13.0 | 2.13.0+cpu |

실측 import는 Laptop `C:\ASL_OCR_INTEGRATION`, Pi `/home/user/ASL_OCR_PI/source` 아래의 device/scanner/parser를 확인했다. Laptop 제품 소스에는 ARM thread correction을 배포하지 않았다. 두 핵심 메서드는 동일 hash였다. OpenCV 버전은 다르지만 이번에 실제 모델에 전달한 crop/variant 픽셀은 같았다.

Pi spot check는51.1°C, throttled0x0, 현재1.8GHz였다. 전체 실험 동안 온도/클럭을 연속 기록하지 않았으므로 sustained thermal 영향의 완전 배제는 아니다. Laptop 미리보기 부하·전원 정책, CPU ISA/native backend/Paddle 버전은 순수 CPU 성능만 추출하는 실험에서는 추가 통제가 필요하다. 이번 prototype 판단에 앞서 broad dependency 교체를 할 필요는 없다.

## 실제 촬영 문제에 주는 의미

앞선 live A/B에서 카메라 수신·해독 약1.7초, 번호 provider 약2.8초가 관측됐다. 이번 동일 ROI 비교는 그중 인식 단계의 장치 성능 차이를 분리해 확인한 것이다. Camera acquisition 전체의 장치 간 배율이나 complete pair rate는 비교하지 않았다.

새 페이지의 유효 관측5개가 필요한 경로에서 Pi의 이 인식 연산만5회 수행해도 단순 합산 약11.1초다. 이는 실측한8초 수집 실패와 부합하는 처리 예산 문제의 근거다. 동일 ROI 반복11.1초를 실제5개의 fresh frame 처리 시간으로 대체하거나, 마지막 관측/timeout의 정확한 경계 동작을 이 산술만으로 확정하지 않는다.

## 다음 우선순위

1. **Pi 성능 예산에 맞는 국소 연산 감소 검토**: 후순위 후보 계산을 줄여도 반환값/variant/confidence/예외 contract가 유지되는지 동일 lossless ROI로 비교. 지금은 제안이며 제품 조기 반환을 적용하지 않았다.
2. **우측 후보/판정 불일치 진단을 분리**: 같은 ROI가 Laptop에서도 실패하므로 CPU 최적화의 성공 조건에 올바른27 인식까지 자동 포함하지 않는다. 입력/후보 선택 원인을 별도 재현한다.
3. **수신 중첩만으로 충분한지 계산 후 검증**: 기존 최신-frame acquisition 재사용을 검토할 수 있으나, 인식 자체가 느린 만큼 수신 스레드 하나 추가로8초/N5가 해결된다고 가정하지 않는다.
4. 국소 수정으로 예산이 충족되지 않으면 Pi local OCR 유지와 Desktop OCR 활용 등 실행 위치 변경을 별도 설계 packet으로 보고한다. 새 architecture를 즉시 구현하지 않는다.

N/K/8초/두 variant/identity/duplicate 기준, 인증/TLS, firmware, 모델 파일 및 패키지는 변경하지 않았다. 이번 product source modification count **0**. [이전 지연 진단](PI4_SCANNER_LATENCY_DIAGNOSIS_20260915.md)과 함께 bounded correction 판단 근거로 사용한다.

Evidence: [pi-laptop-roi-comparison-20260915](evidence/pi-laptop-roi-comparison-20260915/), `comparison-summary.json`, `comparison-checks.json`, 세 원시 result/log, 공유 PNG 및 manifest, 두 진단 script. 기존 state/DB/receipt/evidence는 보존했다.
