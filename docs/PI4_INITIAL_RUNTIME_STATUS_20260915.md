# Pi4 실행 환경 이식 및 최초 검증 — 2026-09-15

최신 후속 상태: 사용자가 OCR 단일 스레드 수정을 승인했고 적용·초기 검증을 수행했다. 이전 절의 '미적용/변경 0'은 당시 기록이다. 현재 변경은 제품 파일 1개이며 [수정 결과 및 미리보기 조정 단계](PI4_OCR_THREAD_CORRECTION_RESULT_20260915.md)를 참조한다.

## 범위와 현재 판정

사용자 지시에 따라 Pi에 실행 환경을 먼저 만들고, production 파이프라인의 최소 동작을 확인한다. 전원 투입 자동 시작, 전원 차단 복구 및 H4 최종 수용은 이후 단계로 둔다.

**환경 설치와 일부 경계 검증은 완료했으나 production 파이프라인은 미통과다.** 기본 설정의 Paddle 숫자 인식 첫 추론에서 SIGSEGV가 재현됐다. 모델 로드 성공을 실제 추론 성공으로 대체하지 않았다. 촬영·업로드·finalize·물리 출력 시험은 아직 실행하지 않았다.

## 설치한 환경

| 항목 | 실제 값 |
|---|---|
| SSH / 호스트 | `user@100.69.169.17` / `raspberrypi-Edwin29` |
| OS / CPU | Debian 13.5 trixie / aarch64 |
| 실행 루트 | `/home/user/ASL_OCR_PI` |
| Python | `/home/user/ASL_OCR_PI/.venv/bin/python`, 3.13.5 |
| 소스 | 위 루트의 `source/device-runtime`, `source/book-scanner`, `source/document-parser` |
| 런타임 | `/home/user/ASL_OCR_PI/runtime/initial-20260915` |
| 서버 | 기존 Desktop production 서버. Pi에서 health HTTP 200 및 인증된 catalog 28개 조회 |
| 장치 ID | 기존 `laptop-device-001` 유지. Laptop 앱과 동시 실행하지 않는다. |
| 모델 | Laptop integration의 기존 UVDoc 및 hash-pinned Paddle 모델 |
| 주요 패키지 | Torch 2.13.0+cpu, PaddlePaddle 3.2.2, PaddleOCR 3.7.0, OpenCV 4.10.0 |

Laptop의 Python 3.11/PaddlePaddle 3.3.1과 플랫폼 차이가 있다. 3.3.1의 공식 PyPI 배포 목록에 ARM64 wheel이 없어 Pi에서 설치 가능한 3.2.2를 후보로 사용했다. 이 차이를 기존 Laptop 인증과 동일하다고 간주하지 않는다. CPU Torch는 공식 CPU wheel index에서 설치했다. 첫 CUDA 의존성 다운로드 시도는 설치 전에 중단했으며 로그는 보존했다.

기존 SSH 인증만 사용했다. 기존 API/camera secret을 SSH로 전달하여 사용자 전용 루트 및 권한 600 파일로 보관했다. 보고서·저장소에 secret 내용은 저장하지 않았다. 소스·모델 249개 파일 해시를 비교했고 세 패키지의 `__file__`이 Pi의 위 source를 가리킴을 확인했다. 전달 zip SHA-256: `279b3c07b468d2a4592f08cfdd231a770bbd79b543b70b654df881a6e2199e0b`.

## 확인 결과와 evidence 범위

| 경계 | 결과 | 증명하지 않는 사항 |
|---|---|---|
| pip dependency check | PASS, broken requirements 없음 | 네이티브 ABI 및 모델 실행의 안전성 |
| production Scanner factory 구성, 모델 로드 | PASS | 실제 추론, live identity 결정 |
| UVDoc 실제 CPU 계산 | 합성 320×480 영상에서 success, 약 6.35초(최초 로드 포함) | 실제 책 보정 품질·고해상도 처리시간 |
| 인증된 S0 catalog 조회 | PASS, 28개 | cursor 변경·audio fetch/play·V4 전송 |
| 기본 Paddle 추론 | FAIL, SIGSEGV | 원시 C++ crash 지점은 확보하지 못함 |
| AUX | ALSA Headphones 카드 확인 | PortAudio 라이브러리 미설치, 실제 청취 미검증 |
| Android snapshot | connection refused | 현재 앱/휴대폰 상태 미확인, source 대체하지 않음 |
| Bluetooth | 어댑터 soft block 해제, 기존 HC-05 주소 확인 | Pi pairing/RFCOMM/V3 handshake 미검증 |

HC-05 주소는 Laptop `Get-PnpDevice`의 HC-05 및 COM9 InstanceId가 일치한 `98:D3:02:96:9C:8C`이다. Pi에서 임의 주변 장치를 pairing하지 않았다. Pi config의 `/dev/rfcomm0`은 현재 아직 생성되지 않은 예정 장치 경로다.

## 새 장애: Pi Paddle 첫 추론 SIGSEGV

- First failing boundary: `PaddleRoiDigitRecognizer._predict()` → PaddleOCR `TextRecognition.predict()`의 첫 native 추론.
- 동일 모델·합성 입력 `28`로 별도 프로세스 시험. 카메라·STM·서버 변경·Torch 동시 로드 없이도 기본 설정에서 재현됐다.
- 설치된 PaddleOCR의 기본 `cpu_threads=10`, `enable_mkldnn=True`. ASL 제품 어댑터는 현재 `cpu_threads`를 전달하지 않는다.

| 독립 시험 | 결과 |
|---|---|
| 기본 옵션 | SIGSEGV, subprocess returncode -11 |
| `enable_mkldnn=False`만 적용 | SIGSEGV -11 |
| `cpu_threads=1`만 적용 | PASS, `28`, confidence 약 0.9985, 추론 약 0.50초 |
| `cpu_threads=1` 독립 재실행 | 동일 PASS |
| CPU 명시 + MKLDNN off + 1 thread | PASS |
| 제품 옵션 그대로, OMP/OPENBLAS/MKL 환경 변수만 1 | SIGSEGV -11 |

**분류:** 이 ARM runtime 조합의 native inference failure는 확인됐다. `cpu_threads=1`은 재현된 최소 회피 후보다. threading 관련 내부 결함, Paddle/PaddleX 버전 조합 또는 ARM kernel의 정확한 원인은 C++ stack이 없어 확정하지 않는다. MKLDNN off만으로 해결된다는 가설은 반증됐다. 인식 임계값/모델 변경은 필요 근거가 없다.

제품 소스를 유지한 채 환경 변수만 조절한 시험은 해결하지 못했다. 임시 monkeypatch/wrapper를 production PASS로 사용하지 않는다.

### 필요한 최소 수정 후보 — 미적용

- Pi/ARM CPU에서만 인식 어댑터가 `cpu_threads=1`을 명시하도록 제한한다. MKLDNN, 모델, N/K/identity/duplicate 기준 및 timeout은 유지한다.
- 예상 변경 상한: 제품 어댑터 1개(`book-scanner/src/book_scanner/video/page_number_recognizer.py`), targeted test 1개, 이식 기록/manifest. 새 architecture layer나 broad upgrade는 불필요하다.
- 테스트: ARM CPU에서 해당 인자 전달, 기존 x86 경로의 인자 유지, production factory로 동일 모델 반복 추론, 실제 footer ROI 인식, live Scanner 동일 N/K 처리시간 및 페이지 변경, 이후 두 spread의 durable V4→READY 확인.
- 호환성: 모델 및 입력/출력 타입·프로토콜 유지. 스레드 선택에 따른 처리시간은 Pi에서 재측정해야 한다.
- Rollback: 어댑터 변경만 복구하고 기존 source identity 재확인. state·모델·database는 변경하지 않는다.
- 기존 코드 수정이 필요한 경우 보고하라는 사용자 조건에 따라 우선 후보와 근거만 기록했다.

## 다음 실행 순서

1. **현재 막힌 환경 항목 해소:** 사용자 Pi 터미널에서 `sudo apt-get install -y libportaudio2`. 비밀번호는 대화에 제공하지 않는다. 카메라 앱 및 AUX/HC-05 준비 여부 확인.
2. **Paddle 최소 correction 결정 및 검증:** 위 후보 적용이 승인되면 targeted test 후 Pi production factory 추론을 재검증한다. Synthetic PASS와 live camera PASS는 분리한다.
3. **출력·입력 최소 연결:** 정확한 HC-05 pairing/RFCOMM 설정, V3 확인, 기존 READY 선택 후 AUX 실제 음성·동일 focus 셀·버튼 이동 확인. 물리 시험 직전에 packet/관측 순서를 안내한다.
4. **Pi fresh capture:** Android snapshot 해상도·방향 먼저 확인. 같은 production module/config에서 pages 26/27 및 28/29 → spread별 durable receipt → CONFIRM LONG → fresh READY → 읽기 음성/점자 확인. Laptop 앱은 종료 상태여야 한다.
5. 위 최소 기능 검증 후 **자동 시작 및 공동 전원 차단/재공급 복구** 설정으로 넘어간다.

카메라/입출력 준비 여부와 sudo 설치 완료는 사용자 응답 대기 중이다. 이 단계에서 서비스 자동 시작, firmware flash, servo packet 송신, live 업로드는 수행하지 않았다.

## 원시 자료

- [Pi evidence](evidence/pi-initial-20260915/pi/): environment manifest, pip freeze/check/install logs, model probe, native variant logs와 exit codes, snapshot probe, HC-05 identity.
- [기본 모델 검사](evidence/pi-initial-20260915/probe_models.py)
- [연속 추론 검사](evidence/pi-initial-20260915/probe_inference.py): 최초 native crash로 JSON 최종 결과를 쓰지 못한 시도. 후속 독립 프로세스 로그로 보완.
- [독립 native variant 검사](evidence/pi-initial-20260915/probe_native_variants.py)

**본 Pi 이식 작업의 product source modification count: 0.** 새 diagnostic 코드·runtime config·환경 설치·기록만 추가했다. 기존 H1/H2/H3 결과를 Pi H4 수용으로 승격하지 않는다.

## PortAudio 설치 후 재개 확인

사용자가 sudo 설치 완료를 보고한 뒤 Pi를 원격 재확인했다.

- `libportaudio2` 설치 상태: `install ok installed 19.6.0-1.2+b3`.
- `sounddevice` import 성공. 기본 출력 index 0은 `bcm2835 Headphones: - (hw:2,0)`이다.
- 기존 인증 adapter로 catalog 제목 `새 데이터팩 2026-09-08 23:47 #28`의 WAV를 내려받았다. 235,052 bytes, 22,050Hz, mono, 16bit, 5,329ms. `check_output_settings` 통과.
- 이 검사는 stream을 시작하거나 음성을 재생하지 않는다. 실제 재생 완료·사용자 청취는 아직 미확인이다.
- Android IP Camera의 4444 포트는 재검사에서도 connection refused. Pi Bluetooth controller는 powered on이지만 대상 HC-05 정보 조회는 `not available`이고 pairing 목록은 비어 있다. 이것만으로 HC-05 전원 고장을 확정하지 않는다.
- 잔류 ASL/진단 process는 발견되지 않았다. OCR 단일 스레드 제품 수정은 아직 미적용이다.

다음 사용자 관측 준비를 요청했다: AUX 이어폰 청취 가능 여부, STM/HC-05 전원, Android IP Camera 앱 실행. 준비가 확인되면 authenticated catalog 음성 1회 → 정확한 HC-05 연결 → V3 및 물리 출력 순서로 진행한다. 앞서 기록한 자동 시작·전원 복구 보류는 유지한다.

추가 evidence: [음성 검사 스크립트](evidence/pi-initial-20260915/probe_audio.py), `pi/audio-preflight-*.json`, `pi/bluetooth-readiness-*.json`. 제품 source modification count는 계속 0이다.

## 사용자 준비 후 AUX 청취·카메라 재확인

- Production `S0SystemAudioResourceHttpAdapter`와 `SoundDeviceWavPlayer`를 사용한 단독 재생이 약 5.40초 후 정상 반환했다. 사용자가 **정상적으로 끝까지 들림**을 확인했다. authenticated catalog 음성 → Pi AUX → 이어폰 경계 PASS이며, 전체 DeviceApplication/reading generation/셀 결합 수용은 아니다.
- Production `create_snapshot_source`로 인증된 Android source를 읽었다. raw/effective 모두 4000×3000, rotation 0. 26/27쪽이 가로로 올바르게 배치된 영상임을 시각 확인했다. `InsecureRequestWarning` 및 `Invalid SOS parameters for sequential JPEG`가 출력됐지만 프레임 디코딩은 성공했다. Scanner candidate/identity/업로드는 이 시험에 포함되지 않는다.
- Snapshot evidence: `camera-snapshot-1789472030357634216.jpg`, SHA-256 `ad96bc54b1cadfbc92ff4fa64fec0258738fb2b465749678e19ca92fd28de491`.
- Bluetooth scan에서 정확한 대상 `98:D3:02:96:9C:8C / HC-05`를 확인했다. 첫 비대화형 pairing은 완료되지 않아 종료했다. 대화형 default agent를 등록한 후 재시도했고 **기존 HC-05 PIN 요청 단계**에 도달했다. PIN을 임의로 추측하거나 변경하지 않고 사용자에게 요청했다. Pairing/RFCOMM/V3 및 STM 패킷 송신은 아직 미완료다.
- PIN 미입력 상태에서 해당 시도가 `org.bluez.Error.AuthenticationFailed`로 종료됐다. 이는 잘못된 PIN을 입력한 evidence가 아니다. 새로 연 bluetoothctl 세션은 정리했으며, 기존 PIN 확인 후 다시 시도한다.

## HC-05 페어링 및 RFCOMM 등록 완료

사용자가 두 기본 PIN 후보의 순차 시도를 승인했다. 첫 후보로 pairing이 성공하여 두 번째 후보는 시도하지 않았다. HC-05 설정/PIN 변경은 수행하지 않았다.

- 정확한 대상: `98:D3:02:96:9C:8C / HC-05`.
- `Paired: yes`, `Bonded: yes`, `Trusted: yes` 확인.
- SDP 조회: SPP/Serial Port, RFCOMM **channel 1**.
- `sudo -n rfcomm bind 0 98:D3:02:96:9C:8C 1` 성공. `/dev/rfcomm0`은 `root:dialout`, 권한 `660`; 실행 사용자 read/write 접근 가능.
- `rfcomm0 ... channel 1 clean`은 장치 등록 상태이며 지속적인 data link나 V3 완료 증거가 아니다. 아직 port를 production adapter로 열어 handshake하거나 STM FRAME을 보내지 않았다.
- 자동 bind service/부팅 자동 시작은 추가하지 않았다. 재부팅 후 bind 복구는 후속 전원·부팅 설정 범위다.
- 새 bluetoothctl 세션과 검색은 종료했다. 증거는 `pi/bluetooth-pairing-*.json`에 보존한다.

## Pi production STM 어댑터 V3 및 DOWN 경계 확인

동일 `StmSerialControlSource`/`_open_serial`에 입출력을 변경하지 않는 trace wrapper를 붙여 독립 시험했다. DeviceApplication/Coordinator/S0는 이 시험에 포함하지 않았다. Legacy 허용은 false이며 desired FRAME은 전체 수납 상태였다.

- 첫 20초 무조작 시험: RFCOMM 열기 성공, HELLO 미수신, host의 기존 handshake deadline/reconnect 작동. 종료 후 worker 잔류 없음.
- 다음 90초 시험: 사용자 UP 입력의 `NAV,U,S,6` 재전송을 수신했으나 HELLO 이전이므로 ACK하지 않았다. 이후 `HELLO,3` → `ACK,HELLO,3` → 전체 수납 FRAME → 초기 `NAV,V,R,1` → `ACK,1` → 동일 FRAME 한 번 재전송을 확인했다.
- UP 첫 수신 monotonic 6509.4978, HELLO 6520.0804: 약 **10.58초**. 이 Pi 관측을 이전 Laptop의 약 2초와 동일하게 기록하지 않는다. 기존 warm reconnect 제한 및 host retry가 관여할 수 있으나 정확한 지연 분해는 미검증이다.
- 실제 DOWN: `NAV,D,A,2`/`ACK,2`, 약 0.94초 뒤 `NAV,D,R,3`/`ACK,3`. production 입력 이벤트는 각각 activated/released였다. V2 SHORT를 V3 증거로 대체하지 않았다.
- 사용자가 DOWN 조작 완료 및 **정상 수납**을 확인했다.
- 시험 종료 시 serial_closed 및 worker_alive=false. FRAME accepted_bytes는 OS write 수락 증거이며 별도 firmware/PCA 적용 ACK가 아니다. 물리 수납은 사용자 관측으로 분리했다.

추가 script: [probe_stm.py](evidence/pi-initial-20260915/probe_stm.py), raw: `pi/stm-probe-*.jsonl`.

## Pi production 읽기 결합 — 진행 중

기존 Laptop `asl_device` 프로세스가 없음을 확인한 뒤 Pi에서 실제 module entrypoint를 실행했다. `--initial-mode reading`이라는 production CLI 옵션으로 기존 READY catalog부터 시작한다. 따라서 live camera·V4·parser·finalize를 통과한 시험은 아니다. 동일 stable device ID를 유지한다.

- Run: `/home/user/ASL_OCR_PI/runtime/initial-20260915/evidence/production-reading-1789472713233410794`.
- PID 8324, production STM controls/presenter 및 SoundDevice audio. Wrapper는 subprocess 실행·로그·exit 기록만 담당하며 어댑터를 바꾸지 않는다.
- `screen_changed: datapack_selection, mode: reading` 확인. 초기 안내 WAV 재생 완료 및 catalog 제목 음성 재생을 확인했다.
- 사용자에게 UP 한 번 + 15초 대기 → CONFIRM → DOWN → RIGHT/LEFT를 묶어서 안내했다. 물리 음성·점자/버튼 결과는 응답 대기 중이다.
- OCR 기본 추론 SIGSEGV 후보 수정은 여전히 미적용이다. 모델 factory 로드는 성공하므로 기존 READY 읽기 검증을 먼저 진행하며, 촬영 성공으로 승격하지 않는다.

### Production 읽기 사용자 결과 및 로그 대조

사용자는 안내한 조작 전체가 정상 작동했다고 보고했다. **이번에 수행한 Pi production 읽기 subset은 PASS**로 기록한다. 범위는 기존 READY 선택, 물리 CONFIRM/DOWN/RIGHT/LEFT 조작, AUX 음성, 실제 점자 출력이며 모든 버튼·모든 오류 경로를 포괄한 fresh H3 수용은 아니다.

- 앱 로그의 `reading_resumed`: 기존 datapack `datapack-b7d5a769ad5347738d491f1b39e5e909`, page_index 0, node_index 6, braille_offset 10, generation 221. 이는 Laptop에서 사용한 stable device cursor가 Pi 읽기에 복구된 증거다. Pi 전원 차단 복구를 시험한 것은 아니다.
- generation 221/223 음성의 interruption과 후속 generation 음성 재생을 확인했다. generation 222/227/231/232의 완료 로그가 있으며 마지막 232 음성은 약 15.6초 리소스다. 이 구간에 traceback/fatal 기록은 관측되지 않았다.
- 물리 점자의 내용·이동 정상 여부는 사용자 확인이다. 이번 module 실행에는 serial trace wrapper를 삽입하지 않았으므로 개별 production FRAME의 wire-level generation을 로그만으로 모두 증명하지 않는다. 바로 앞 어댑터 독립 시험의 V3 증거와 구분한다.
- 결과를 run의 `operator-observation.json` 및 stdout.log에 보존했다. 원래 안내보다 추가 generation 변화도 기록돼 있으므로 로그만으로 모든 변화가 어느 버튼이었는지 역추정하지 않는다.

다음 남은 핵심 작업은 보고한 Pi OCR 단일 스레드 correction의 적용 결정 및 production factory 재검증, 이후 fresh 두 spread capture→durable V4 receipt→CONFIRM LONG→fresh READY→reading 결합이다. 자동 시작/전원 차단 복구는 사용자 지시대로 그 뒤에 진행한다.

읽기 subset 결과 보존 후 PID/command identity를 확인한 시험 앱에 SIGINT를 보냈다. supervisor의 `exit.json`에서 returncode 0을 확인했고 PID가 사라진 것도 확인했다. 추가 CLEAR는 보내지 않았다. 해당 종료 결과는 공동 전원 차단의 내구성/복구 검증과 별개다.
