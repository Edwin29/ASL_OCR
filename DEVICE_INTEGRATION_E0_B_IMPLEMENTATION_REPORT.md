# Device Integration E0-B — Laptop Acceptance 구현 보고서

상태: **software implementation 및 자동 회귀 완료 / physical acceptance 대기**
기준일: 2026-09-01
승인 패킷: `DEVICE_INTEGRATION_E0_B_LAPTOP_ACCEPTANCE_WORK_PACKET.md`

## 구현 결과

- 실제 `pc_camera` capture mode(width/height/FPS) 적용·검증
- STM `HELLO`/`NAV` parser와 `DeviceInputEvent` 변환
- STM input과 10-cell FRAME output의 single serial writer
- 최소 host debounce와 bounded reconnect backoff
- reading 전 blank handshake, reading 중 current snapshot presentation
- 비동기 Windows beep/SAPI semantic feedback
- E0-B typed TOML config와 sample config
- model/server/camera/serial/audio preflight 및 secret-safe JSON report
- 실제 C0/S0/V4/SQLite/S1 worker를 쓰는 desktop loopback-origin deterministic bench server
- 서로 다른 network의 Laptop에서 desktop Server로 접속하는 HTTPS tunnel acceptance 경로
- preflight/full-run Laptop runbook
- clone 뒤 dependency/config/model/health/preflight를 수행하는 interactive Laptop setup batch

Server API/schema, V3-B persistence와 Coordinator 순서 계약은 변경하지 않았다.

## 자동 검증

| 범위 | 결과 |
|---|---:|
| Device Runtime + 실제 E0-Core HTTP/SQLite integration | 83 passed |
| E0-B config/application/STM/audio/preflight 집중 테스트 | 19 passed |
| Book Scanner 전체 | 289 passed |
| Document Parser 전체 | 573 passed, 4 skipped |
| live camera source 집중 테스트 | 3 passed |
| E0-B desktop bench server 집중 | 2 passed |

Book Scanner 전체 회귀는 Windows 비ASCII user temp path에 대한 OpenCV 제약을 피하기 위해 저장소 아래
ASCII `--basetemp`를 사용했다. Document Parser의 pytest cache write warning은 test failure가 아니다.

## Desktop Server/tunnel smoke

2026-09-01 현재 개발용 desktop에서 다음을 실제로 확인했다.

- 기존 `D:\Tools\cloudflared.exe` 2026.8.2를 공식 최신 2026.8.3으로 갱신
- version: `2026.8.3` (`built 2026-08-31T02:48 UTC`)
- SHA-256: `83E726ED18EA78C5AD5213C4C3A3A27051393950D2BC8ED4DE69BEC12D14EAAE`
- GitHub release asset의 공식 SHA-256 digest와 local file hash 일치
- `tools/windows/e0b-start-server.bat`로 bench Server 기동
- local `http://127.0.0.1:8421/api/v1/health` HTTP 200, `status=ok`, `database=ok`, `writable=true`
- `tools/windows/e0b-start-quick-tunnel.bat`로 Quick Tunnel 생성
- cloudflared connectivity pre-check의 DNS, UDP/QUIC, TCP/HTTP2와 Cloudflare API 모두 PASS
- 임시 `https://*.trycloudflare.com/api/v1/health` HTTP 200과 같은 Server instance 확인
- smoke 종료 뒤 tunnel/Server process와 임시 state/API key 제거

Quick Tunnel URL은 process 종료와 함께 폐기됐으며 Laptop config에 고정하지 않는다. 실제 Laptop과
camera/STM/audio를 포함한 physical acceptance는 이 desktop smoke와 별개로 아직 대기한다.

Laptop setup script는 fake hash-pinned model bundle과 isolated config root를 사용한 non-interactive
smoke에서 venv reuse, TOML 치환, secret 분리, model hash 검증과 복사를 통과했다. 실제 UVDoc/Paddle
model 및 physical I/O 검증은 Laptop preflight에서 수행해야 한다.

현재 Desktop asset audit에서 `tmp/uvdoc-runtime/model.py`와 local Paddle M1 model은 확인했지만 UVDoc
`checkpoint.pth`는 발견되지 않았다. 따라서 실제 Laptop setup을 완료하려면 검증에 사용했던 UVDoc
checkpoint를 별도 보관 위치/Drive에서 먼저 확보해 model bundle에 넣어야 한다.

## Physical Acceptance 대기 항목

- 실제 별도 Laptop과 camera capture
- 실제 COM/HC-05/STM HELLO·NAV·FRAME 왕복
- 실제 speaker의 beep/SAPI 음량·식별성
- 실제 Laptop -> Internet HTTPS tunnel -> desktop C0/V4 round trip
- live Scanner model latency/RSS와 capture-to-ACK 관측값
- app 종료 뒤 camera/serial/audio resource release 실측

따라서 구현 코드는 준비됐지만 E0-B를 최종 완료로 표시하지 않는다. 실제 장치에서 preflight와 한 번의
full acceptance flow를 수행하고 report/log를 첨부하면 완료 판정을 갱신한다.

같은 LAN은 필요하지 않다. 실제 external tunnel health와 remote C0/V4 round trip은 E0-B physical
acceptance 항목이며, production tunnel hardening과 exhaustive WAN fault matrix는 후속으로 이관한다.
