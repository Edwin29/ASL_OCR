# Laptop Conditional E0-B Runbook

## 1. 호스트 구분

이 절차는 두 컴퓨터를 사용한다. 명령 앞의 `[DESKTOP]`과 `[LAPTOP]` 표기를 반드시 확인한다.

| 호스트 | 책임 |
|---|---|
| `DESKTOP` | 실제 PaddleOCR-VL/Piper production 서버, 영속 server state, Tailscale Serve HTTPS origin |
| `LAPTOP` | 웹캠/Android UVC 입력, Device Runtime, 콘솔 또는 STM 입력, 점자 frame, Piper WAV 다운로드·재생 |

Desktop 서버가 준비된 뒤 Laptop을 설정한다. API key 값은 두 호스트에서 같아야 하지만 Git, TOML,
콘솔 인자 또는 evidence에 기록하지 않는다.

## 2. 시험 프로필

| Laptop 프로필 | 카메라 | 조작 입력 | STM/모터/점자 출력 | 음성 |
|---|---|---|---|---|
| `webcam` | Laptop 웹캠 또는 준비된 UVC 카메라 | 콘솔 명령 | 열지 않음 | Desktop Piper WAV → Laptop `sounddevice` |
| `hardware` | Laptop 웹캠 또는 준비된 UVC 카메라 | STM Bluetooth COM | STM frame/모터/점자 포함 | Desktop Piper WAV → Laptop `sounddevice` |

`webcam` 콘솔 명령은 `up`, `down`, `left`, `right`, `next`, `prev`, `confirm`,
`lever activated`, `lever released`다. 실제 모드 레버가 없어도 두 lever 명령으로 capture/reading 전환을
검증한다. `hardware`는 COM 포트를 열기 때문에 STM이 없으면 의도적으로 preflight에 실패한다.

## 3. 저장소 디렉터리 책임

- `book-scanner/`: production 카메라·dewarp·candidate/identity 처리
- `document-parser/`: production V4/S1/S0 서버, OCR, 접근성 변환, Piper 합성
- `device-runtime/`: production Coordinator, console/STM 입력, 점자 frame, 인증 오디오 다운로드·RAM cache·재생
- `hardware/stm32/kitel2026final/`: 현재 STM32CubeIDE authoritative firmware
- `tools/windows/`: 설치, preflight, 실행, evidence 도구
- `docs/work-packets/`: 승인된 작업 패킷 기록
- `tmp/`와 준비 루트의 `reports/`, `state/`: 실행 산출물이며 production source가 아님

`document-parser/hardware/stm_pi_bridge/`는 `LEGACY / TEST-ONLY`이고 정식 실행 경로가 아니다.
`RasberryPITest/`는 Pi 부하·자원 도구이며 Device Runtime 대체물이 아니다. 정식 Laptop 실행 진입점은
`python -m asl_device --config <toml>`이다.

## 4. Desktop — production 서버 준비와 실행

### 4.1 Desktop 선행 파일

다음 기본 경로를 사용한다. 다른 경로는 같은 이름의 `E0B_*` 환경 변수로 wrapper 실행 전에 재정의한다.

```text
D:\venvs\gpu_ocr_test\Scripts\python.exe
D:\ASL_OCR_E0B\models\paddleocr-vl\.paddlex\official_models\PP-DocLayoutV3
D:\ASL_OCR_E0B\models\paddleocr-vl\.paddlex\official_models\PaddleOCR-VL-1.6
D:\models\piper-korean\ko_KR-kss-medium.onnx
D:\models\piper-korean\ko_KR-kss-medium.onnx.json
D:\espeak-ng-data
D:\device-config\secrets\device-api-key.txt
```

deterministic E0-B bench server는 OCR/전송 회귀용이며 Piper preflight 권한이 아니다. 아래 production
`combined_server`를 사용해야 `SystemAudioService`가 같은 Piper voice로 system/document WAV를 만든다.

### 4.2 Desktop 서버 시작

별도 Desktop PowerShell을 열어 저장소 루트에서 실행하고 E2E가 끝날 때까지 유지한다.

```powershell
# [DESKTOP]
Set-Location D:\Projects\OCR
tools\windows\e0b-start-production-server.bat
```

기본 origin은 `http://127.0.0.1:8421`, state는
`D:\device-config\state\e0b-production`이다. 다른 state/API key/port가 필요하면 순서대로 지정한다.

```powershell
# [DESKTOP]
tools\windows\e0b-start-production-server.bat `
  D:\device-config\state\e0b-production `
  D:\device-config\secrets\device-api-key.txt `
  8421
```

### 4.3 Desktop local health와 Tailscale Serve

두 번째 Desktop PowerShell에서 확인한다.

```powershell
# [DESKTOP]
Invoke-RestMethod http://127.0.0.1:8421/api/v1/health
tools\windows\e0b-start-tailscale-serve.bat
```

wrapper가 출력한 `ORIGIN=https://<desktop>.<tailnet>.ts.net`을 Laptop setup에 사용한다. Serve는
`127.0.0.1:8421`을 같은 tailnet에만 공개한다. local health의 `server_instance_id`와 HTTPS health의
값이 같아야 한다. Desktop 서버 terminal은 전체 Laptop 시험이 끝난 뒤 `Ctrl+C`로 종료한다.

## 5. Laptop — 공통 준비

Laptop은 같은 저장소 revision, model bundle, Desktop과 같은 API key 및 같은 tailnet 연결이 필요하다.
먼저 Desktop이 출력한 HTTPS origin에 접근 가능한지 확인한다.

```powershell
# [LAPTOP]
Invoke-RestMethod https://<desktop>.<tailnet>.ts.net/api/v1/health
Set-Location D:\ASL_OCR
```

## 6. Laptop — 프로필별 설치

두 프로필은 서로 다른 TOML과 report를 만들므로 같은 `D:\ASL_OCR_E0B`에 함께 둘 수 있다.

STM·모터 없이 Laptop + 서버 + 웹캠으로 시험:

```powershell
# [LAPTOP]
tools\windows\e0b-laptop-setup.bat `
  -ConfigRoot D:\ASL_OCR_E0B `
  -TestProfile webcam `
  -OpaqueIdentityMaxCollectionMs 8000
```

전체 하드웨어가 연결된 시험:

```powershell
# [LAPTOP]
tools\windows\e0b-laptop-setup.bat `
  -ConfigRoot D:\ASL_OCR_E0B `
  -TestProfile hardware `
  -OpaqueIdentityMaxCollectionMs 8000 `
  -ComPort COM5
```

setup 질문에는 Desktop의 HTTPS origin, 고유 Device ID, Laptop model bundle과 Desktop과 동일한 API key를
입력한다. 생성 파일은 `device-app.e0b.webcam.toml`, `device-app.e0b.hardware.toml`이다. 호환용
`device-app.e0b.toml`도 마지막 profile로 갱신되지만 이후 명령에는 profile을 항상 명시한다.

실카메라의 footer identity OCR은 Laptop CPU에서 프레임당 수백 ms가 걸릴 수 있다. `N=5`를 유지하면서
기존 1.5초 수집창을 쓰면 유효 관측 1~3개만 모은 채 timeout될 수 있으므로 physical profile의 E0-B
기본값은 8초다. 카메라가 고정돼 있어도 OCR 처리시간과 frame sampling 간격 때문에 이 제한은 필요하다.

## 7. Laptop — Preflight

Piper system cue를 실제 Laptop 기본 출력장치로 재생하는 기본 점검:

```powershell
# [LAPTOP]
tools\windows\e0b-laptop-preflight.bat D:\ASL_OCR_E0B webcam
tools\windows\e0b-laptop-preflight.bat D:\ASL_OCR_E0B hardware
```

소리를 내지 않고 인증·WAV 형식·크기 제한까지만 확인:

```powershell
# [LAPTOP]
tools\windows\e0b-laptop-preflight.bat D:\ASL_OCR_E0B webcam --no-audio-playback
```

`webcam` report에는 `e0b_profile`, `scanner_models`, `server_health`, `camera`, `piper_audio`가 있어야 한다.
`hardware`에는 `stm_serial`이 추가된다. report는 각각 `reports/e0b-preflight-webcam.json`과
`reports/e0b-preflight-hardware.json`이다. `playback_requested=true`만으로 실제 청취를 증명하지 않으므로
3.5 mm 출력장치에서 안내가 들렸는지는 사용자가 직접 판정한다.

## 8. Laptop — Live E2E

Laptop setup이 만드는 `webcam`/`hardware` 설정은 기본적으로 operator camera preview를 켠다. 새 데이터팩을
확정하여 scan이 시작되면 `ASL OCR Camera Preview` 창이 열리고, 이 창은 OCR에 전달되는 것과 같은
회전·미러링 적용 후 프레임을 카메라 속도로 표시한다. `Q`, `Esc` 또는 창 닫기로 미리보기만 닫을 수 있으며
scan은 계속된다. 창 크기는 `operator_preview_max_width`로 제한되고 원본 OCR 프레임 해상도는 줄지 않는다.
GUI 없는 자동 시험에서는 setup에 `-DisableCameraPreview`를 추가한다.

미리보기 상단에는 실제 source/backend/index, 협상된 해상도·FPS·FourCC, Scanner 상태와 현재
`reason`이 표시된다. 녹색 영역은 검출된 좌우 페이지 마스크이고 빨간 사각형은 페이지 내용과 겹친
손·가림 검출 영역이다. `reason=ready`가 유지되어야 후보 검증으로 진행할 수 있다. 음성 안내는 같은
사유가 최소 3회·1초 동안 유지된 뒤 출력되며, 동일 사유는 15초 이내에 반복하지 않는다. 사유가
바뀌어도 순간적인 한 프레임 변화만으로 재생 중인 안내를 교체하지 않는다.

Windows Laptop 설정은 backend마다 OpenCV index의 의미가 달라지는 것을 막기 위해 기본적으로
`camera_backend = "msmf"`를 사용한다. 미리보기 제목의 `[pc_camera:msmf:N]`은 실행 중인 backend와
index를 그대로 보여준다. DirectShow에서 확인한 장치를 사용해야 할 때만 setup에
`-CameraBackend dshow`를 명시한다.

하드웨어 없이 실행:

```powershell
# [LAPTOP]
tools\windows\e0b-laptop-run.bat D:\ASL_OCR_E0B webcam
```

콘솔 명령으로 capture catalog → scan → save → capture catalog 복귀, reading catalog → 첫 node →
node/braille-window/page 이동 → 종료·재진입 cursor 복구를 점검한다.

이번 physical acceptance에서는 아래 순서를 지킨다.

1. 새 데이터팩을 선택하고 `candidate_selected` 뒤
   `identity_collection_progress`의 `valid_observations`가 5까지 도달하는지 확인한다.
2. `identity_collection_decided`가 `different`로 끝난 뒤 `spread_sent`가 나오는지 확인한다.
   `artifact_ready`는 내부 Scanner event이며 기본 console feedback에는 따로 출력되지 않는다.
   `spread_sent`는 서버 ACK까지 끝났다는 뜻이다.
3. 최소 한 건의 `spread_sent`를 확인한 뒤에만 `confirm long`으로 스캔을 끝낸다.
4. `finalizing` 뒤 `datapack_saved`에 READY `revision`이 표시되고 capture catalog로 돌아오는지 확인한다.
5. 점퍼/모드 레버 없이 아래 reading 전용 명령으로 READY 데이터팩을 다시 연다.

```powershell
# [LAPTOP]
tools\windows\e0b-laptop-read.bat D:\ASL_OCR_E0B webcam
```

reading catalog에는 READY 데이터팩만 보인다. 저장한 데이터팩을 선택한 뒤 `up`/`down`으로 항목을
이동한다. 각 `reading_snapshot`에는 OCR/LaTeX 원문인 `source_text`, 실제 합성 음성 대본인
`spoken_text`, 같은 generation의 `braille_cells`가 함께 출력된다. 원문과 발음을 보면서 음성을
청취하고, 수식 항목에서는 `left`/`right`로 현재 점자 창을 이동한다. 리딩 중 `confirm`은 현재
항목을 새 generation으로 다시 재생하고, `confirm long`은 리딩을 끝내고 데이터팩 선택창으로
돌아간다. 이 명령은 시작 모드만 reading으로 지정하며 카메라나 STM 점퍼를 요구하지 않는다.

원문과 OCR 결과를 직접 대조할 때는 `datapack_saved`에 나온 ID로 Desktop의
`D:\device-config\state\e0b-production\datapacks\<datapack-id>\document.json`을 연다. 같은 폴더의
`manifest.json`에 페이지 순서와 검증 요약이 있으며, `audio_index.json`에는 실제 합성된 발화문이 있어
본문 누락·오인식과 음성 품질을 함께 확인할 수 있다.

전체 하드웨어로 실행:

```powershell
# [LAPTOP]
tools\windows\e0b-laptop-run.bat D:\ASL_OCR_E0B hardware
```

COM 입력, SHORT 반복 간격, confirm, lever A/R, `FRAME` 10셀, 모터 구동, 점자 출력, 3.5 mm 음성을
확인한다. `webcam` 통과는 STM/모터/점자 합격을 대신하지 않으며, preflight만으로 두 workflow의 E2E가
완료된 것도 아니다. 각 full run 로그와 Desktop server evidence를 보존한다.

Android 휴대폰 UVC는 `docs/ANDROID_UVC_CAMERA_HOST_RUNBOOK.md`에 따라 stable selector와 fallback
index를 먼저 probe한다. `scanner.profile="android_uvc"`는 선택 장치가 없을 때 다른 카메라로 조용히
fallback하지 않는다.

## 9. OCR 품질 판정과 유선 비교

Bluetooth/Wi-Fi 가상 카메라는 앱 자체의 해상도 축소, 비트레이트 제한, H.264 재압축, 지연·frame drop을
동반할 수 있다. 이 영향은 서버 송신 구간이 아니라 Windows가 Scanner에 제공하기 전의 영상 입력에서
발생한다. 반면 USB UVC/MJPEG도 무압축 원본은 아니지만 대체로 전송 지연이 작고 협상된 해상도와
프레임률을 재현하기 쉬워 비교 기준으로 적합하다.

우선 8초 수집창으로 현재 연결을 시험한다. 저장 후 reading 결과에서 본문 누락, 심한 오인식, 페이지
번호/좌우 순서 오류가 있으면 같은 책·거리·조명·회전 조건으로 휴대폰의 USB UVC 모드를 연결하고
`android-uvc` profile로 한 번 더 찍는다. 두 실행의 미리보기 헤더에 표시되는 effective
해상도/FPS/FourCC, `recognition_processing_ms`, 유효 관측 5개 수집 여부, 최종 OCR 텍스트를 비교한다.
유선에서도 동일하면 전송 방식보다 구도·초점·노출 또는 footer crop/OCR 정책 문제일 가능성이 높다.

## 10. 실험 데이터팩 전체 초기화

현재 API에는 개별 데이터팩 삭제를 노출하지 않는다. 실험 데이터 전체를 비울 때는 **Desktop
production 서버를 먼저 `Ctrl+C`로 완전히 종료**한 뒤 저장소 루트에서 실행한다.

```powershell
# [DESKTOP] server가 중지된 상태에서만 실행
tools\windows\e0b-reset-experimental-datapacks.bat `
  D:\device-config\state\e0b-production `
  RESET-E0B-EXPERIMENT
```

도구는 local health가 응답하면 초기화를 거부한다. 확인 문자열이 정확해야 하며, DB·datapacks·jobs를
삭제하지 않고 `D:\device-config\state\e0b-production-reset-backups\<timestamp-id>`로 옮긴 뒤 빈
`datapacks`와 `jobs`를 다시 만든다. 출력된 `backup_root`로 복구할 수 있다. 초기화 뒤 production
서버와 Tailscale Serve를 다시 시작한다. 이 명령은 개별 항목 삭제가 아니라 해당 state root의 실험
데이터 전체 초기화다.
