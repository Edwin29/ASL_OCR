# Device Integration E0-B — Laptop runbook

E0-B는 서로 다른 네트워크에 있는 두 컴퓨터를 사용한다. Windows Laptop은 camera, STM/HC-05와
speaker를 구동하고, 현재 개발용 desktop은 Server를 구동한다. 두 컴퓨터는 같은 LAN이나 VPN에
있을 필요가 없지만 둘 다 외부 인터넷에 접속할 수 있어야 한다.

처음 설치할 때는 저장소 root의 `LAPTOP_E0B_QUICKSTART.md`와
`tools/windows/e0b-laptop-setup.bat`를 사용한다. Setup wrapper는 Python 환경, pinned runtime,
config/state/secret, model bundle 검증, remote health와 hardware preflight를 순서대로 수행한다.

```text
Laptop Device -- HTTPS/Internet --> Cloudflare Tunnel -- localhost --> Desktop Server
 camera + STM + audio                                  127.0.0.1:8421
```

Server는 desktop의 `127.0.0.1`에만 bind한다. `cloudflared`가 outbound tunnel을 만들기 때문에
공유기 port forwarding이나 Windows firewall inbound rule을 추가하지 않는다. Laptop config에는
`device-connectivity.e0b.remote.example.toml`을 복사해 tunnel의 공개 `https://` origin을 기록한다.
API key는 TOML에 넣지 않고 양쪽의 별도 secret file에 같은 값으로 둔다.

## 1. Desktop Server 준비와 실행

E0-B physical acceptance에는 실제 C0/S0/V4 route, SQLite journal, S1 worker와 reading API를 쓰되
OCR/TTS 결과만 deterministic fixture로 만드는 bench Server를 권장한다. 저장소 root에서 다음을
실행한다.

```powershell
python -m pip install -e '.\document-parser[remote-ingest]'
python -m document_parser.server.e0b_bench_server `
  --state-root D:\device-config\state\e0b-bench `
  --api-key-file D:\device-config\secrets\device-api-key.txt
```

기본 origin은 `http://127.0.0.1:8421`이다. Server terminal은 acceptance가 끝날 때까지 유지한다.
아래 명령으로 desktop 자체 health를 먼저 확인한다.

```powershell
Invoke-RestMethod http://127.0.0.1:8421/api/v1/health
```

현재 저장소의 Windows batch wrapper를 사용할 수도 있다.

```powershell
.\tools\windows\e0b-start-server.bat `
  D:\device-config\secrets\device-api-key.txt `
  D:\device-config\state\e0b-bench
```

실제 PaddleOCR-VL/Piper 변환까지 시험해야 할 때만 bench 대신 `combined_server`를 사용한다. GPU와
model 준비가 선행되어야 하며, 외부 tunnel을 붙일 때는 반드시 `--host 127.0.0.1`로 덮어쓴다.

```powershell
$e0bApiKey = (Get-Content D:\device-config\secrets\device-api-key.txt -Raw).Trim()
python -m document_parser.server.combined_server `
  --host 127.0.0.1 --port 8421 `
  --api-key $e0bApiKey `
  --datapacks-dir D:\device-config\state\datapacks `
  --jobs-dir D:\device-config\state\jobs `
  --model-home D:\models\paddleocr-vl `
  --device gpu:0 `
  --piper-model D:\models\piper-korean\ko_KR-kss-medium.onnx `
  --piper-espeak-data D:\models\espeak-ng-data
Remove-Variable e0bApiKey
```

현재 `combined_server` CLI는 API key argument를 요구하므로 E0-B 기본 절차는 secret-file 입력을 쓰는
bench Server다. 실제 model Server의 장기 운영/credential hardening은 별도 패킷으로 둔다.

## 2. Desktop HTTPS tunnel 실행

### 권장: 고정 hostname의 named tunnel

C0 재접속과 app 재시작까지 같은 endpoint로 검증하려면 고정 hostname이 필요하다. Desktop에
[`cloudflared`](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/)를
설치하고 Cloudflare dashboard에서 tunnel을 만든 뒤 Published application route의
Service URL을 `http://localhost:8421`로 지정한다. 발급된 Windows 설치 명령 또는 token run 명령을
desktop에서 실행하고 tunnel이 `Healthy`인지 확인한다. 이 방식은 Cloudflare에 연결된 domain이
필요하다.

Laptop의 connectivity config에는 dashboard에서 정한 공개 origin만 기록한다.

```toml
server_base_url = "https://e0b.example.com"
allow_insecure_http = false
```

### 1회 acceptance 대안: Quick Tunnel

고정 domain이 아직 없으면
[Quick Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)로
desktop의 두 번째 terminal에서 다음을 실행한다.

```powershell
cloudflared tunnel --url http://localhost:8421
```

현재 desktop의 `cloudflared` 절대 경로와 Server health 선행 확인을 포함한 wrapper는 다음과 같다.

```powershell
.\tools\windows\e0b-start-quick-tunnel.bat
```

출력된 `https://<random>.trycloudflare.com` origin을 Laptop config에 수동 복사한다. Quick Tunnel은
개발/시험 전용이고 process를 재시작할 때 URL이 바뀐다. 따라서 한 번의 E0-B physical flow에는 쓸
수 있지만, 고정 endpoint를 요구하는 reboot/restart recovery의 완료 증거로는 쓰지 않는다. Runtime이
tunnel stdout을 읽어 endpoint를 자동 채택하게 만들지 않는다.

외부 네트워크에서 다음 health 요청이 성공해야 Laptop 설치로 넘어간다.

```powershell
Invoke-RestMethod https://<tunnel-host>/api/v1/health
```

또는 `.\tools\windows\e0b-check-server.bat https://<tunnel-host>`를 사용한다.

공개 URL과 API key를 함께 아는 사용자는 Server API에 접근할 수 있다. 둘은 신뢰하는 시험자에게만
별도 채널로 전달하고, 시험 후 Quick Tunnel process를 종료한다. tunnel credential/token은 desktop
밖으로 복사하지 않는다.

## 3. Laptop 설치와 설정

Laptop은 인터넷에 연결되어 있으므로 동일 revision의 저장소를 checkout하거나 승인된 bundle을
복사한 뒤 의존성을 직접 설치할 수 있다.

권장 경로는 clone 뒤 setup batch를 한 번 실행하는 것이다.

```powershell
.\tools\windows\e0b-laptop-setup.bat
```

```powershell
python -m pip install -e '.\document-parser[remote-ingest]' -e .\book-scanner -e '.\device-runtime[laptop]'
```

UVDoc runtime/checkpoint와 Paddle M1 directory/manifest도 config 경로에 맞게 준비한다. HC-05를
Windows에서 pair하고 생성된 COM port를 기록한다. 다음 두 example을 실제 config로 복사한다.

- `device-runtime/device-app.e0b.laptop.example.toml` -> `device-app.e0b.toml`
- `device-runtime/device-connectivity.e0b.remote.example.toml` -> `device-connectivity.e0b.remote.toml`

공개 HTTPS origin, COM port, camera index/width/height/FPS와 model 경로를 수정한다. 현재 firmware에서는
`viewport_size`와 STM `cell_count`가 모두 10이어야 한다. Desktop Server가 읽는 key와 같은 내용을
Laptop의 `secrets/device-api-key.txt`에 저장한다.

자동 Setup의 model bundle은 `uvdoc/runtime`, `uvdoc/checkpoint.pth`, `paddle/page-number`와
`paddle/page-number-manifest.json` 구조를 요구한다. Manifest가 열거한 모든 파일의 SHA-256을 복사
전에 검사한다. Model은 Git에 포함되지 않으며 runtime download도 하지 않는다.

## 4. Preflight

Laptop에서 실행한다.

```powershell
python -m asl_device `
  --config D:\device-config\device-app.e0b.toml `
  --preflight `
  --report D:\device-config\reports\e0b-preflight.json
```

Preflight는 remote HTTPS/non-loopback profile, Scanner model load, remote Server health, camera 한 frame,
serial port open, Windows beep/SAPI speech를 독립적으로 확인한다. 한 check가 실패해도 나머지를 실행하며
report에는 API key를 기록하지 않는다. `server_health` 실패 시 desktop Server, tunnel process/Healthy
상태, Laptop의 공개 origin 순으로 확인한다. Laptop에서 desktop의 사설 `192.168.x.x` 주소를 사용하지
않는다.

## 5. Full acceptance run

```powershell
python -m asl_device --config D:\device-config\device-app.e0b.toml
```

Firmware는 10-cell FRAME을 받을 때까지 `HELLO`를 보낸다. Reading 전에는 Laptop이 blank FRAME으로
응답하고, reading 중에는 valid NAV마다 현재 Server-backed cursor/cell을 보낸다. camera open, first
artifact, V3-B queue, remote V4 ACK, seal, READY와 resource release 시각을 기록한다. sent beep은 ACK 뒤,
saved speech는 READY 뒤에만 발생해야 한다.

Process를 종료한 뒤 다른 program이 camera와 COM port를 열 수 있는지 확인한다. Desktop에서는 tunnel과
Server를 순서대로 종료하고 state/log/report를 보존한다.

E0-B는 서로 다른 인터넷 network 사이의 기본 HTTPS reachability와 한 physical flow를 검증한다.
Cloudflare 장애 matrix, production Access policy/mTLS, 장기 service auto-start, credential rotation,
multi-region/다중 writer hardening, Raspberry Pi 이식과 exhaustive network/crash matrix는 포함하지 않는다.
