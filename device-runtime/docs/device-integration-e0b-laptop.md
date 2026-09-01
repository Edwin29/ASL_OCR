# Device Integration E0-B — Laptop runbook

Laptop은 Device Runtime을, 개발용 Desktop은 Server를 실행한다. 두 컴퓨터는 같은 LAN일 필요가 없고
각각 외부 인터넷에 접속할 수 있으면 된다. 기본 연결은 무료 개인 Tailscale tailnet의 private HTTPS
Serve endpoint다.

```text
Laptop Device -- Tailscale private HTTPS --> Desktop Tailscale Serve
 prepared MP4 or camera/STM                 -> http://127.0.0.1:8421
                                             -> E0-B bench Server
```

E0-B.1은 MP4 + console로 하드웨어 직전의 remote flow를 검증한다. Physical E0-B는 이후 같은 Server
경로에 camera + STM/HC-05 + speaker를 붙여 검증한다. 시작 절차는 저장소 root의
`LAPTOP_E0B_QUICKSTART.md`를 우선한다.

## 1. Desktop Server

기본 acceptance에는 실제 C0/S0/V4 route, SQLite journal, S1 worker와 reading API를 사용하되 OCR/TTS
content만 deterministic fixture로 만드는 bench Server를 사용한다.

```bat
tools\windows\e0b-start-server.bat D:\device-config\secrets\device-api-key.txt D:\device-config\state\e0b-bench
```

Server는 `127.0.0.1:8421`에만 bind한다. API key는 repository/TOML이 아닌 별도 secret file에 둔다.

```powershell
Invoke-RestMethod http://127.0.0.1:8421/api/v1/health
```

실제 PaddleOCR-VL/Piper content 품질까지 시험할 때만 `combined_server`를 사용한다. 그것은 E0-B.1
transport acceptance의 선행 조건이 아니다.

## 2. Tailscale Serve 고정 endpoint

Desktop과 Laptop에 Tailscale을 설치하고 같은 계정/tailnet에 로그인한다. Desktop Server health가
성공한 뒤 다음 wrapper를 실행한다.

```bat
tools\windows\e0b-start-tailscale-serve.bat
```

Wrapper는 다음을 순서대로 검사한다.

1. Tailscale binary, daemon 연결과 local device online 상태
2. local E0-B health 및 `server_instance_id`
3. `tailscale serve --bg 8421` 적용
4. local Tailscale status에서 stable MagicDNS FQDN 획득
5. `https://<fqdn>/api/v1/health`가 같은 Server instance인지 확인

Tailnet에서 Serve를 처음 쓰면 CLI가 `https://login.tailscale.com/f/serve?node=...` 활성화 링크를
출력하고 대기한다. Browser에서 Desktop Tailscale과 같은 tailnet 소유 계정으로 로그인해 Serve를
enable한 뒤 wrapper를 다시 실행한다. 이 단계는 API key/auth key 생성이 아니고 tailnet의 Serve 기능을
최초 한 번 허용하는 관리 설정이다. 로그인이나 CAPTCHA는 사용자가 직접 완료한다. CLI pipe 접근 또는
Serve 적용 권한 오류가 나면 wrapper를 관리자 권한으로 실행한다.

출력된 `ORIGIN=https://<desktop>.<tailnet>.ts.net`만 Laptop의 `server_base_url`에 기록한다. 실제 FQDN,
tailnet credential이나 login token을 repository example에 hard-code하지 않는다. Serve는 public
Funnel이 아니며 같은 tailnet device만 접근할 수 있다. 기존 `X-API-Key` application authentication도
계속 필수다.

Serve 설정을 제거할 때만 다음을 실행한다.

```bat
tools\windows\e0b-stop-tailscale-serve.bat
```

Cloudflare Quick Tunnel wrapper는 Tailscale을 사용할 수 없는 1회 fallback으로 유지한다. Quick Tunnel은
public이고 재시작 시 URL이 바뀌므로 fixed-endpoint acceptance에는 사용하지 않는다.

2026-09-01 Desktop smoke에서 Serve activation, private HTTPS same-instance health, reset 후 empty config와
재적용 뒤 동일 MagicDNS hostname/health를 확인했다. 실제 FQDN은 private 식별자이므로 repository에
기록하지 않는다. 남은 endpoint 검증은 실제 Laptop에서 같은 tailnet을 통한 health/auth/C0다.

## 3. Laptop E0-B.1 replay setup

Laptop은 같은 revision의 저장소, 준비된 MP4, model bundle, Desktop과 동일한 API key가 필요하다.
Model bundle은 아래 GitHub Release에서 Laptop으로 직접 받을 수 있다.

- `https://github.com/Edwin29/ASL_OCR/releases/tag/e0b-model-bundle-2026-09-01`
- ZIP SHA-256: `44fa79a338d397e31519474c87db60eaed73025198a7c5673ecc1424ced0f817`

Model directory 계약:

```text
E0B_MODEL_BUNDLE/
  uvdoc/runtime/model.py
  uvdoc/checkpoint.pth
  paddle/page-number/{inference.json,inference.pdiparams,inference.yml,...}
  paddle/page-number-manifest.json
```

다음 setup wrapper에 준비된 영상 경로를 첫 argument로 준다.

```bat
tools\windows\e0b-replay-setup.bat D:\Downloads\scanner-replay.mp4
```

Setup은 Python 3.11 venv/dependency, remote HTTPS config, local secret, model manifest/hash, MP4 첫 frame
decode와 SHA-256, Server health를 검사한다. Replay config는 `scanner.profile="replay"`,
`local_io.controls="console"`, `feedback="jsonl"`이고 camera field와 STM table을 사용하지 않는다.
Physical hardware preflight도 실행하지 않는다.

생성되는 주요 파일:

- `D:\ASL_OCR_E0B\device-app.e0b.toml`
- `D:\ASL_OCR_E0B\device-connectivity.e0b.remote.toml`
- `D:\ASL_OCR_E0B\inputs\scanner-replay.mp4`
- `D:\ASL_OCR_E0B\reports\e0b-replay-input.json`
- `D:\ASL_OCR_E0B\secrets\device-api-key.txt`

## 4. Replay acceptance

```bat
tools\windows\e0b-replay-run.bat
```

Console command는 `up`, `down`, `left`, `right`, `next`, `prev`, `confirm`, `lever`와 optional action
`short|long|activated|released`다. 기본 short action은 생략할 수 있다.

Fresh bench state에서 확인할 순서는 다음과 같다.

1. authenticated C0 ONLINE과 catalog event
2. 새 데이터팩을 선택하고 `confirm`하여 scan 시작
3. replay에서 artifact 생성, durable V3-B enqueue와 valid V4 ACK 뒤 `spread_sent`
4. 다시 `confirm`하여 freeze/flush/seal
5. S1 finalization 뒤 `datapack_saved`와 reading 진입
6. `reading_snapshot` JSON에 `cursor`, `braille_cells`, `audio_ref`
7. `right`/`next` navigation 후 변경된 Server snapshot
8. `Ctrl+C` 종료와 SQLite/log/report 보존

동일 snapshot polling은 중복 JSON을 만들지 않는다. Presenter write failure는 Server ACK나 domain state를
되돌리지 않는다. Replay EOF는 자동 seal authority가 아니며 사용자의 `confirm`이 stop intent다.

E0-B.1 성공은 Scanner/V3-B/V4/S1/reading transport를 입증하지만 실제 OCR/TTS 품질과 camera,
HC-05/STM, 점자 frame, speaker/audio resource를 입증하지 않는다.

## 5. Physical E0-B setup

하드웨어를 연결할 수 있게 되면 기존 physical wrapper를 사용한다.

```bat
tools\windows\e0b-laptop-setup.bat
tools\windows\e0b-laptop-preflight.bat
tools\windows\e0b-laptop-run.bat
```

Physical setup에서는 Tailscale Serve origin, Device ID, HC-05 COM port, camera index/width/height/FPS,
model bundle과 API key를 입력한다. Preflight는 model load, remote health, camera 한 frame, serial open,
Windows beep/SAPI speech를 독립적으로 검사한다. 실제 Laptop report가 모두 passed이기 전에는 physical
E0-B를 완료로 표시하지 않는다.

## 6. 범위 경계

이번 경로는 기존 REST/heartbeat/V4 multipart/finalize polling/reading API를 변경하지 않는다.
SSE/WebSocket, Tailscale Funnel, ACL/auth-key rotation, Windows service 자동 시작, production credential
정책, multi-writer/lease/quarantine/quota와 exhaustive WAN/crash matrix는 별도 hardening 범위다.
