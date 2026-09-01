# E0-B Laptop 빠른 시작

이 절차는 Laptop과 Desktop Server가 같은 LAN에 없고 각각 인터넷에 연결된 환경을 기준으로 한다.
Laptop에는 camera, STM/HC-05와 speaker가 연결되고, Desktop은 Server와 Cloudflare Tunnel을 실행한다.

## 1. Laptop 필수 프로그램

Windows Terminal 또는 명령 프롬프트에서 다음을 실행한다. 이미 설치돼 있으면 건너뛴다.

```bat
winget install --id Git.Git -e
winget install --id Python.Python.3.11 -e
```

설치 후 터미널을 닫았다 다시 열고 다음을 확인한다.

```bat
git --version
py -3.11 --version
```

## 2. 저장소 받기

E0-B에는 대형 과거 실험 LFS blob이 필요하지 않다. 다음 명령은 LFS 자동 다운로드를 생략한다.

```bat
set GIT_LFS_SKIP_SMUDGE=1
git clone --branch codex/asl-ocr-integration-c0-handoff --single-branch https://github.com/Edwin29/ASL_OCR.git D:\ASL_OCR
cd /d D:\ASL_OCR
```

GitHub Desktop을 쓰는 경우 `File > Clone repository > URL`에서 위 URL을 입력하고 `D:\ASL_OCR`에
clone한 뒤 `codex/asl-ocr-integration-c0-handoff` 브랜치를 선택한다.

## 3. Model bundle 준비

Model은 저장소에 포함되지 않는다. Desktop 또는 이동식 저장장치에서 다음 구조의 한 폴더를 Laptop에
복사한다. 예시는 `E:\e0b-models`다.

```text
E:\e0b-models\
  uvdoc\
    runtime\
      model.py
      ...
    checkpoint.pth
  paddle\
    page-number\
      inference.json
      inference.pdiparams
      inference.yml
      ...manifest가 열거한 나머지 파일
    page-number-manifest.json
```

Setup은 manifest의 모든 Paddle asset SHA-256을 검사하고 하나라도 없거나 다르면 중단한다. Runtime
download나 임의 model 대체는 하지 않는다.

## 4. Desktop Server 주소와 API key 준비

Desktop에서 다음 두 파일을 각각 다른 terminal에서 실행한다.

```bat
tools\windows\e0b-start-server.bat D:\device-config\secrets\device-api-key.txt D:\device-config\state\e0b-bench
tools\windows\e0b-start-quick-tunnel.bat
```

두 번째 terminal에 출력된 `https://*.trycloudflare.com` origin과 Desktop Server가 읽는 API key를
Laptop 설정에 사용한다. Quick Tunnel은 terminal을 닫으면 종료되고 다음 실행에서 주소가 바뀐다.

## 5. Laptop 자동 Setup

`D:\ASL_OCR\tools\windows\e0b-laptop-setup.bat`를 더블클릭한다. 또는 terminal에서 실행한다.

```bat
cd /d D:\ASL_OCR
tools\windows\e0b-laptop-setup.bat
```

화면에서 다음 값을 입력한다.

- 공개 HTTPS Server origin
- Device ID
- HC-05가 사용하는 COM port
- camera index, width, height와 FPS
- 위 model bundle 경로
- Desktop과 동일한 API key

Setup이 자동으로 수행하는 항목:

1. repository의 `.venv-e0b` Python 3.11 환경 생성
2. pinned Torch/Paddle/serial runtime과 세 local package 설치
3. `D:\ASL_OCR_E0B` config/state/report/secret/model directory 생성
4. remote HTTPS, camera와 COM 설정 반영
5. API key를 TOML과 분리된 UTF-8 secret file로 저장
6. model bundle 구조와 Paddle SHA-256 검증 후 복사
7. Desktop Server HTTPS health 확인
8. camera/STM/audio/model hardware preflight와 JSON report 생성

하드웨어를 아직 연결하지 않아 preflight만 미루려면 terminal에서 다음을 사용한다.

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\e0b-laptop-setup.ps1 -SkipPreflight
```

## 6. 재실행

Setup 이후에는 다음 파일을 더블클릭하거나 terminal에서 실행한다.

```bat
tools\windows\e0b-laptop-preflight.bat
tools\windows\e0b-laptop-run.bat
```

기본 config root가 아닌 경우 뒤에 경로를 전달한다.

```bat
tools\windows\e0b-laptop-preflight.bat D:\my-e0b-config
tools\windows\e0b-laptop-run.bat D:\my-e0b-config
```

Preflight report는 기본적으로 `D:\ASL_OCR_E0B\reports\e0b-preflight.json`에 생성된다. 여섯 check가
모두 `passed`가 아니면 full run 성공으로 판정하지 않는다.
