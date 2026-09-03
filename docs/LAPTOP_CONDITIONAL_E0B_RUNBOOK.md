# Laptop Conditional E0-B Runbook

## 목적

동일한 Device Runtime과 서버 계약을 유지하면서 물리 입출력 준비 상태에 따라 두 가지 live-camera 시험을
분리한다. 두 프로필 모두 실제 카메라, 원격 S0/C0/V4/S1 서버, 인증된 시스템 WAV 전송과 Laptop 기본
출력장치를 사용한다. SAPI는 성공 조건이나 fallback이 아니다.

| 프로필 | 카메라 | 조작 입력 | STM/모터/점자 출력 | 음성 |
|---|---|---|---|---|
| `webcam` | Laptop 웹캠 또는 준비된 UVC 카메라 | 콘솔 명령 | 열지 않음 | 서버 Piper WAV → Laptop `sounddevice` |
| `hardware` | Laptop 웹캠 또는 준비된 UVC 카메라 | STM Bluetooth COM | STM frame/모터/점자 포함 | 서버 Piper WAV → Laptop `sounddevice` |

`webcam` 프로필의 콘솔 명령은 `up`, `down`, `left`, `right`, `next`, `prev`, `confirm`,
`lever activated`, `lever released`다. 실제 모드 레버가 없어도 두 lever 명령으로 capture/reading 전환을
검증할 수 있다. `hardware` 프로필은 COM 포트를 열기 때문에 STM이 없으면 의도적으로 preflight에
실패한다.

## 디렉터리 책임

- `book-scanner/`: production 카메라·dewarp·candidate/identity 처리
- `document-parser/`: production V4/S1/S0 서버, OCR, 접근성 변환, Piper 합성
- `device-runtime/`: production Coordinator, console/STM 입력, 점자 frame, 인증 오디오 다운로드·RAM cache·재생
- `hardware/stm32/kitel2026final/`: 현재 STM32CubeIDE authoritative firmware
- `tools/windows/`: 설치, preflight, 실행, evidence 도구
- `docs/work-packets/`: 승인된 작업 패킷 기록
- `tmp/`와 준비 루트의 `reports/`, `state/`: 실행 산출물이며 production source가 아님

`document-parser/hardware/stm_pi_bridge/`는 `LEGACY / TEST-ONLY` 자료이고 정식 실행 경로가 아니다.
`RasberryPITest/`는 Pi 부하·자원 도구이므로 Device Runtime 대체물이 아니다. 루트의 과거 구현 보고서는
추적 문서이며 실행 모듈이 아니다. 따라서 production 실행 진입점은 계속
`python -m asl_device --config <toml>`이다.

## 서버 선행 조건

Piper preflight에는 `SystemAudioService`가 연결된 production `combined_server`가 필요하다. deterministic
E0-B bench server는 OCR/전송 회귀용이며 Piper 권한이 아니므로 이 preflight의 `piper_audio` 검사를
통과시키는 서버로 사용하지 않는다. Desktop 서버는 실제 Piper model과 eSpeak data를 지정해 실행하고,
Laptop에는 그 서버의 private HTTPS origin과 같은 API key를 설정한다.

## 프로필 설치

저장소 루트에서 실행한다. 두 프로필은 서로 다른 TOML과 report를 만들므로 같은 준비 루트에 함께 둘 수
있다.

```powershell
Set-Location D:\Projects\OCR

tools\windows\e0b-laptop-setup.bat `
  -ConfigRoot D:\ASL_OCR_E0B `
  -TestProfile webcam
```

STM과 전체 하드웨어가 연결된 뒤에는 다음을 별도로 실행한다.

```powershell
tools\windows\e0b-laptop-setup.bat `
  -ConfigRoot D:\ASL_OCR_E0B `
  -TestProfile hardware `
  -ComPort COM5
```

생성 파일은 각각 `device-app.e0b.webcam.toml`, `device-app.e0b.hardware.toml`이다. 이전 wrapper와의
호환성을 위해 마지막으로 준비한 프로필은 `device-app.e0b.toml`에도 복사되지만, 아래 명령처럼 프로필을
항상 명시하면 어느 설정을 실행하는지 모호하지 않다.

## Preflight

Piper 시스템 안내 한 문장을 실제로 듣는 기본 점검:

```powershell
tools\windows\e0b-laptop-preflight.bat D:\ASL_OCR_E0B webcam
tools\windows\e0b-laptop-preflight.bat D:\ASL_OCR_E0B hardware
```

소리를 내지 않고 인증·WAV 형식·크기 제한까지만 자동 확인하려면 세 번째 인자를 사용한다.

```powershell
tools\windows\e0b-laptop-preflight.bat D:\ASL_OCR_E0B webcam --no-audio-playback
```

`webcam` report에는 `e0b_profile`, `scanner_models`, `server_health`, `camera`, `piper_audio`가 있어야 한다.
`hardware`에는 여기에 `stm_serial`이 추가된다. 성공 report 경로는 각각
`reports/e0b-preflight-webcam.json`, `reports/e0b-preflight-hardware.json`이다. 실제 재생을 요청한 경우
`piper_audio.details.playback_requested=true`와 함께 Laptop의 3.5 mm 기본 출력장치에서 안내가 들려야
물리 오디오를 수동 합격으로 판단할 수 있다.

## Live E2E 실행

하드웨어 없이 카메라·서버·Piper 경로를 시험한다.

```powershell
tools\windows\e0b-laptop-run.bat D:\ASL_OCR_E0B webcam
```

콘솔에서 lever와 navigation 명령을 입력해 capture catalog → scan → save → capture catalog 복귀,
reading catalog → 첫 node → node/braille-window/page 이동 → 종료·재진입 cursor 복구를 점검한다.

전체 하드웨어에서는 다음을 실행하고 같은 시나리오를 물리 버튼·모드 레버로 수행한다.

```powershell
tools\windows\e0b-laptop-run.bat D:\ASL_OCR_E0B hardware
```

이때 확인 대상은 COM 입력, SHORT 반복 간격, confirm, lever A/R, `FRAME` 10셀, 모터 구동, 점자 출력,
3.5 mm 음성이다. `webcam` 통과는 STM/모터/점자 합격을 대신하지 않고, `hardware` preflight 통과만으로
두 사용자 workflow의 상태 전이가 끝까지 통과했다는 뜻도 아니다. 각 full run 로그와 서버 evidence를
별도로 보존한다.

Android 휴대폰 UVC를 사용할 때는 `ANDROID_UVC_CAMERA_HOST_RUNBOOK.md`에 따라 stable selector와
fallback index를 먼저 probe한다. `scanner.profile="android_uvc"`는 장치 정체성이 일치하지 않으면 다른
웹캠으로 조용히 fallback하지 않는다.
