# Device Integration E0-B.1 — Tailscale Fixed Endpoint & Replay Acceptance 작업 패킷

상태: **승인됨 / software implementation과 Desktop Tailscale Serve 검증 완료 / Laptop acceptance 대기**
기준일: 2026-09-01
선행 조건: Device Integration E0-B software implementation, E0-Core, Scanner V3-B, Server V4, C0/S0/S1
후속 조건: Device Integration E0-B physical acceptance(camera + HC-05/STM + speaker)

## 1. 배경과 결정

E0-B software boundary와 Cloudflare Quick Tunnel smoke는 완료됐지만 실제 Laptop 시험 시점에는
Desktop terminal에만 출력되는 임의 `https://*.trycloudflare.com` 주소를 Laptop 사용자가 미리 알 수
없다. Quick Tunnel을 다시 실행하면 주소가 바뀌므로 Laptop의 provisioned `server_base_url`을 안정적으로
유지할 수도 없다. 사용자 요구에는 유료 도메인 구매가 포함되지 않는다.

이번 패킷은 전송 프로토콜을 SSE나 WebSocket으로 바꾸지 않는다. SSE/WebSocket도 최초 연결 URL이
필요하며 주소 고정 문제를 해결하지 않는다. 대신 무료 개인 Tailscale tailnet의 stable MagicDNS와
Tailscale Serve HTTPS reverse proxy를 사용해 다음 고정 경로를 만든다.

```text
Laptop Tailscale client
  -> https://<desktop-machine>.<tailnet>.ts.net
  -> Tailscale Serve HTTPS termination
  -> Desktop http://127.0.0.1:8421
  -> existing E0-B bench Server C0/S0/V4/S1
```

현재 개발용 Desktop에는 Tailscale `1.102.3`이 설치·로그인되어 있고 Windows service가 자동 실행
중이다. 구현 시 실제 DNS 이름은 local Tailscale status에서 읽되 repository 문서나 example config에
개인 tailnet 이름을 hard-code하지 않는다.

실제 STM/HC-05를 사용할 수 없는 동안에는 준비된 MP4와 console controls를 사용해 Laptop에서
`Scanner -> V3-B -> HTTPS -> V4/S1 -> READY -> reading snapshot`까지 검증한다. 이 결과는 physical
E0-B 완료가 아니라 **하드웨어 직전 remote software acceptance** 증거다.

## 2. 목표

다음 사용자 흐름을 추가 도메인 비용과 Server API 재설계 없이 한 번의 승인 단위로 닫는다.

```text
Desktop bench Server start
  -> Tailscale Serve fixed HTTPS origin start
  -> Laptop fixed origin health/auth/presence
  -> prepared MP4 replay Scanner
  -> artifact + V3-B durable queue
  -> existing multipart V4 upload and valid ACK
  -> S1 deterministic fragment/finalization READY
  -> Laptop reading snapshot 수신
  -> cursor/braille_cells/audio_ref secret-safe JSON trace
  -> console navigation command/response
```

핵심 목표:

- Desktop과 Laptop이 같은 LAN에 없어도 같은 Tailscale tailnet을 통해 연결
- 도메인 구매 없이 재실행 후에도 동일한 `*.ts.net` HTTPS origin 사용
- 기존 REST, heartbeat, V4 multipart, finalize polling과 reading command 계약 보존
- camera 대신 기존 `replay` Scanner profile 사용
- STM 대신 기존 `console` controls 사용
- Laptop이 Server reading payload를 실제로 받았다는 관측 가능한 JSON evidence 추가
- 실제 camera/COM 접근 없이 setup, health, model, replay와 remote flow 실행

## 3. 포함 범위

### 3.1 Tailscale Serve 고정 endpoint

- Desktop과 Laptop의 Tailscale 설치·로그인·same-tailnet prerequisite 확인
- Desktop local bench health 성공 뒤 `tailscale serve --bg 8421` 실행
- Tailscale status에서 stable FQDN을 읽어 `https://<fqdn>` origin 출력
- Serve status와 HTTPS `/api/v1/health`를 각각 확인
- Server는 계속 `127.0.0.1:8421`에만 bind
- Laptop C0 config에는 private Tailscale HTTPS FQDN만 저장
- API key는 기존 별도 secret file을 그대로 사용
- Serve stop/reset wrapper와 재실행 뒤 동일 FQDN 확인
- Cloudflare wrapper는 삭제하지 않고 one-run fallback으로만 남김

### 3.2 Hardwareless Laptop profile

- 별도 `e0b-replay` example/config 경로
- Scanner `profile = "replay"`
- explicit MP4 `replay_path`와 positive `sample_interval_ms`
- local controls `console`
- feedback `jsonl`
- camera index/mode와 STM serial table을 runtime authority로 사용하지 않음
- physical `--preflight`를 실행하지 않는 명시적 setup/run 경로
- video file 존재, decode 가능, source SHA-256을 secret-safe report에 기록
- 기존 UVDoc/Paddle model bundle 구조·hash 검증은 그대로 수행

### 3.3 Reading snapshot trace

현재 console/jsonl 경로는 `READING_RESUMED` cursor는 보여주지만 실제 수신한 `braille_cells`와
`audio_ref`를 표시하지 않는다. 하드웨어 없는 acceptance에서 수신 증거를 남기기 위해 bounded
`JsonLineReadingPresenter` 또는 동등한 presenter를 추가한다.

trace 최소 필드:

```json
{
  "type": "reading_snapshot",
  "reading_session_id": "...",
  "datapack_id": "...",
  "cursor": {},
  "braille_cells": [],
  "audio_ref": "..."
}
```

규칙:

- API key, local absolute model path, upload manifest body와 image bytes를 기록하지 않음
- 같은 snapshot의 poll 반복은 중복 출력하지 않음
- reading 전 `None`은 최대 한 번의 명시적 empty 상태로만 기록하거나 생략
- console navigation으로 snapshot이 바뀌면 새 JSON line 출력
- presenter 출력 실패는 domain state와 Server ACK를 되돌리지 않음
- STM presenter의 FRAME semantics는 변경하지 않음

### 3.4 실행·증거 wrapper

- Desktop bench Server 시작 wrapper 재사용
- Desktop Tailscale Serve start/status/stop wrapper
- Laptop replay setup wrapper 또는 기존 setup의 명시적 replay option
- Laptop replay run wrapper
- remote health와 same Server instance 확인
- 실행 로그와 acceptance JSON report 저장
- 성공/실패를 exit code로 구분하고 API key를 stdout/report에 출력하지 않음

## 4. 제외 범위

다음은 이번 패킷에 포함하지 않는다.

- SSE endpoint, EventSource client, `Last-Event-ID`와 event replay
- WebSocket server/client와 장기 duplex connection lifecycle
- V4 multipart upload를 SSE/WebSocket으로 교체
- 실제 camera capture, HC-05 pairing, COM open, STM HELLO/NAV/FRAME
- 실제 점자 셀, speaker beep/SAPI 음량과 hardware resource release 판정
- Tailscale Funnel을 통한 public Internet 공개
- Tailscale account 생성, SSO 자동화와 사용자 credential 저장
- tailnet ACL/device posture/auth-key rotation/MDM 운영 hardening
- Windows service의 새 설치·삭제 또는 Tailscale 자체 auto-update 관리
- production domain, Cloudflare Access/mTLS와 tunnel multi-region
- 실제 PaddleOCR-VL/Piper Server content 품질 검증
- active Coordinator whole-process restart 복구
- V3-B multi-writer, lease, 일반화 quota/GC와 exhaustive crash/WAN matrix

## 5. 환경 계약

### 5.1 비용과 계정

- 개인 prototype acceptance는 현재 Tailscale Personal free plan 범위에서 수행
- Desktop과 Laptop은 같은 사용자 소유 tailnet에 로그인
- 결제 수단, 유료 domain과 paid add-on을 요구하지 않음
- 서비스 요금제 변경은 repository 계약으로 보장하지 않고 acceptance 시점 환경 정보로 기록

### 5.2 Endpoint authority

Laptop의 단일 Server authority는 C0 config의 다음 값이다.

```toml
server_base_url = "https://<desktop-machine>.<tailnet>.ts.net"
allow_insecure_http = false
```

- FQDN은 Desktop `tailscale status --json`의 local status에서 얻음
- example/config template에는 실제 사용자 tailnet suffix를 commit하지 않음
- origin은 path/query/fragment가 없는 HTTPS origin이어야 함
- Laptop에서 origin을 수동 추측하거나 Desktop의 `100.x` 주소를 hard-code하지 않음
- hostname 변경은 별도 명시적 사용자 조작으로 취급하며 runtime이 조용히 다른 origin을 채택하지 않음

### 5.3 Trust boundary

- Tailscale tailnet membership은 network reachability gate
- 기존 `X-API-Key`는 application authentication으로 계속 필수
- Tailscale 로그인/token/certificate를 repository, report 또는 Laptop API key file에 복사하지 않음
- bench Server는 loopback bind를 유지하고 LAN interface에 직접 공개하지 않음

## 6. Replay config 계약

권장 example:

```toml
schema_version = 1
connectivity_config = "device-connectivity.e0b.remote.toml"
viewport_size = 10
poll_interval_ms = 20

[delivery]
outbox_db_path = "state/delivery.sqlite3"
artifact_root = "state/artifacts/ready"
upload_timeout_seconds = 60.0
retry_initial_seconds = 1.0
retry_max_seconds = 30.0

[scanner]
profile = "replay"
staging_root = "state/artifacts/staging"
ready_root = "state/artifacts/ready"
uvdoc_runtime_path = "models/uvdoc/runtime"
uvdoc_checkpoint_path = "models/uvdoc/checkpoint.pth"
uvdoc_device = "auto"
m1_model_dir = "models/paddle/page-number"
m1_model_manifest = "models/paddle/page-number-manifest.json"
replay_path = "inputs/scanner-replay.mp4"
sample_interval_ms = 500

[local_io]
controls = "console"
feedback = "jsonl"
```

`camera_*`와 `[local_io.stm_serial]`은 replay config에서 생략한다. 기존 physical config와 parser 지원은
그대로 유지한다. Physical setup에서 받은 임시 COM/camera 값을 replay runtime이 읽게 만들지 않는다.

## 7. Console acceptance flow

fresh bench state의 기본 절차:

```text
1. Laptop app start와 C0 ONLINE/catalog trace 확인
2. `confirm` 입력: new datapack 선택 및 scan start
3. replay video에서 artifact 1개 이상 생성
4. `spread_sent` 확인: valid V4 receipt 뒤에만 발생
5. `confirm` 입력: scan stop/freeze/flush/seal
6. `finalizing` 뒤 `datapack_saved` 확인
7. `reading_resumed`와 `reading_snapshot` 확인
8. `down`, `right` 또는 `next` 입력 후 Server reading command response 확인
9. Ctrl+C 종료와 outbox/server evidence 보존
```

Bench Server parser/TTS는 deterministic fixture다. 따라서 이 flow가 입증하는 것은 실제 remote
transport, persistence, orchestration과 reading payload 수신이며 OCR/TTS semantic 품질이 아니다.

## 8. 안전성과 기존 불변식

이번 패킷은 다음 순서 계약을 바꾸지 않는다.

```text
artifact ready
  -> V3-B durable queue
  -> V4/S1 receipt commit
  -> local ACK
  -> SPREAD_SENT
  -> flush through cutoff
  -> seal
  -> READY
  -> DATAPACK_SAVED
  -> reading session/snapshot
```

- Tailscale health 성공을 upload ACK로 사용하지 않음
- HTTPS response 수신만으로 parser/finalization READY를 추정하지 않음
- replay EOF를 자동 seal authority로 사용하지 않음; 사용자의 console `confirm`이 stop intent
- false ACK와 duplicate fragment 방지 계약 유지
- presenter/trace는 관측자이며 Coordinator, delivery, reading state authority가 아님
- Tailscale disconnected는 기존 retryable connectivity 경계로 처리
- 새 global retry queue, lease, tunnel watcher나 background reconciler를 추가하지 않음

## 9. 구현 단계

### Phase 0 — Scope와 fixture 동결

- E0-B.1과 physical E0-B 완료 기준 분리
- 사용할 prepared MP4 경로와 SHA-256 기록
- 현재 model bundle release/hash 확인
- 기존 E0-B/V3-B/V4 public contract 변화 0 확인

### Phase 1 — Reading JSON presenter

- secret-safe snapshot serialization
- unchanged snapshot dedup
- console/jsonl composition wiring
- presenter failure isolation과 unit test

### Phase 2 — Replay setup/profile

- dedicated replay config example
- setup에서 physical preflight/camera/COM을 요구하지 않는 replay 경로
- video/model/server prerequisite validation
- Laptop replay run wrapper

### Phase 3 — Tailscale Serve wrappers

- Tailscale binary/service/login/same-tailnet 상태 확인
- local bench health 뒤 Serve start
- local status에서 HTTPS FQDN 추출
- Serve status와 Laptop remote health 확인
- reset/stop과 same-hostname restart smoke

### Phase 4 — Remote replay acceptance

- actual Laptop prepared MP4 processing
- V3-B/V4 ACK와 Server S1 READY
- Laptop reading snapshot 및 navigation response trace
- state DB/log/report 보존

### Phase 5 — Regression과 handoff

- Device Runtime, Book Scanner, Document Parser 회귀
- Quickstart/runbook을 Tailscale Serve primary로 갱신
- Cloudflare Quick Tunnel은 fallback으로 명확히 표기
- 구현 보고서와 PROJECT_HANDOFF의 실제 검증 상태 갱신

## 10. 테스트 행렬

### 10.1 Endpoint/scripts

- Tailscale binary 없음 -> actionable failure
- Tailscale daemon offline/logout -> secret 없는 actionable failure
- empty/invalid local DNS name -> startup 거부
- local bench health 실패 -> Serve 시작 전에 중단
- Serve start -> HTTPS origin 출력
- origin에 path/query/fragment 없음
- Serve restart 뒤 FQDN 동일
- remote health의 Server instance/schema 일치
- API key/Tailscale credential stdout/report 노출 0

### 10.2 Replay setup/config

- replay profile에 existing video 요구
- unreadable/undecodable video 거부
- video SHA-256 report 기록
- replay profile이 camera open 0
- console profile이 serial open 0
- model bundle required path와 Paddle manifest hash 검증 유지
- relative paths config root 기준 resolve
- physical E0-B example/parser 회귀 0

### 10.3 Reading presenter

- initial Server reading snapshot에 cursor/cells/audio ref 출력
- unchanged poll의 duplicate JSON 0
- navigation response 뒤 changed snapshot 출력
- `None`/empty cells/audio ref 안전 처리
- API key, manifest/image bytes와 local secret path 노출 0
- stdout write failure가 domain state rollback 0
- STM FRAME presenter 테스트 회귀 0

### 10.4 Remote E2E

- Laptop C0 authenticated ONLINE
- replay artifact 1개 이상
- outbox sequence별 V4 receipt 1개
- ACK 전 `SPREAD_SENT` 0, ACK 뒤 1
- Server spread별 left/right fragment 2개와 중복 0
- flush 전 seal 0
- READY 전 `DATAPACK_SAVED` 0, READY 뒤 1
- Laptop `reading_snapshot` 수신
- console navigation command가 Server에 한 번 반영되고 response 수신
- app stop 뒤 durable ACK row와 acceptance evidence 보존

### 10.5 Regression

- Device Runtime 전체 현재 기준 `83 passed`
- Book Scanner 전체 현재 기준 `289 passed`
- Document Parser 전체 현재 기준 `573 passed, 4 skipped`
- E0-Core actual HTTP/SQLite E2E
- C0/S0/V3-B/V4 집중 회귀
- 기존 physical E0-B STM/audio/preflight 집중 회귀

테스트 수는 구현 후 추가분에 따라 증가할 수 있다. 기존 기준보다 감소하거나 skipped/error가 새로
생기면 원인을 설명하지 않고 완료 처리하지 않는다.

## 11. 완료 기준

다음을 모두 만족해야 E0-B.1을 완료로 표시한다.

1. 추가 domain 구매나 paid tunnel 없이 stable `*.ts.net` HTTPS origin을 얻는다.
2. Desktop bench Server는 계속 `127.0.0.1:8421`에만 bind한다.
3. Laptop과 Desktop이 다른 LAN에서도 Tailscale Serve origin health/auth/presence에 성공한다.
4. Serve stop/start 뒤 Laptop config를 바꾸지 않고 같은 hostname으로 다시 health에 성공한다.
5. prepared MP4가 Laptop replay Scanner에서 artifact를 한 개 이상 만든다.
6. artifact가 V3-B와 V4/S1를 거쳐 valid ACK되고 duplicate spread/fragment가 없다.
7. stop/flush/seal/finalize 뒤 Server가 READY를 반환한다.
8. Laptop JSON trace에 Server-backed `reading_snapshot`의 cursor, braille cells와 audio ref가 기록된다.
9. console navigation command 뒤 Laptop이 Server response snapshot을 다시 받는다.
10. API key와 Tailscale credential이 repository, report, trace에 포함되지 않는다.
11. 세 프로젝트 회귀와 기존 E0-B physical adapter 테스트가 통과한다.
12. 실제 camera/STM/speaker를 검증했다고 주장하지 않는다.

## 12. 예상 변경 파일

주 대상:

- `device-runtime/src/asl_device/adapters/local_feedback.py` 또는 새 reading presenter module
- `device-runtime/src/asl_device/local_composition.py`
- `device-runtime/tests/unit/test_application.py`
- `device-runtime/tests/unit/test_laptop_feedback.py` 또는 새 `test_reading_presenter.py`
- `device-runtime/device-app.e0b.replay.example.toml`
- `tools/windows/e0b-replay-setup.bat`
- `tools/windows/e0b-replay-setup.ps1`
- `tools/windows/e0b-replay-run.bat`
- `tools/windows/e0b-start-tailscale-serve.bat`
- `tools/windows/e0b-stop-tailscale-serve.bat`
- `tools/windows/e0b-check-server.bat`
- `LAPTOP_E0B_QUICKSTART.md`
- `device-runtime/docs/device-integration-e0b-laptop.md`
- `DEVICE_INTEGRATION_E0_B_1_IMPLEMENTATION_REPORT.md`
- `PROJECT_HANDOFF_20260831.md`

필요할 때만 최소 변경:

- `device-runtime/src/asl_device/app_config.py`
- `device-runtime/src/asl_device/application.py`
- `device-runtime/src/asl_device/__main__.py`
- `tools/windows/e0b-laptop-setup.ps1`
- `tools/windows/e0b-laptop-setup.bat`
- `device-runtime/tests/unit/test_app_config.py`
- `device-runtime/tests/integration/test_e0_local_composition.py`

기본 범위가 아닌 파일:

- Server S0/S1/C0/V4 schema와 route
- Scanner candidate/identity/UVDoc/Paddle 알고리즘
- STM serial adapter와 firmware
- Tailscale credential/config file

## 13. 승인 경계

승인 시 수행:

- Tailscale Serve fixed-endpoint start/check/stop wrapper
- hardwareless replay setup/config/run path
- console reading snapshot JSON evidence
- prepared MP4 기반 실제 Laptop remote E2E 실행 지원
- 필요한 unit/integration regression
- Quickstart, runbook, 구현 보고서와 handoff 갱신

별도 승인 없이는 수행하지 않음:

- SSE/WebSocket 구현
- Tailscale Funnel public exposure
- 실제 Cloudflare resource 삭제
- Tailscale account/ACL/auth key의 자동 생성 또는 credential commit
- 실제 camera/STM/speaker physical acceptance 완료 처리
- production tunnel service hardening
- Server API/schema 변경
- actual OCR/TTS model Server 전환
- commit/push/PR

## 14. 중단 조건

다음 상황에서는 범위를 조용히 넓히지 않고 보고한다.

- Laptop을 같은 tailnet에 로그인할 수 없음
- Tailscale Serve가 현재 환경에서 stable HTTPS FQDN을 제공하지 못함
- V4 multipart body가 Serve 경유 중 변형·차단됨
- 기존 C0 HTTPS validation을 약화해야만 Tailscale origin을 수용할 수 있음
- replay flow가 Server API/schema 변경 없이는 진행되지 않음
- reading snapshot 증거를 위해 STM protocol을 모방해야만 함
- API key나 Tailscale credential을 config/report에 평문 포함해야만 자동화 가능
- 새 유료 서비스나 domain 구매가 필수
- 기존 false ACK/duplicate suppression 또는 physical E0-B 회귀 발생

중단 시 endpoint 문제, replay/presenter 문제, physical hardware 대기 항목과 운영 hardening 후보를
분리해 보고한다.

## 15. 후속 패킷

E0-B.1 완료 뒤 기존 E0-B physical acceptance를 이어간다.

```text
E0-B.1 Tailscale fixed endpoint + Laptop replay/console remote acceptance
  -> E0-B physical acceptance: camera + HC-05/STM + speaker
  -> 선택적 Network Hardening: service policy, ACL, credential rotation, WAN fault evidence
  -> Raspberry Pi camera/GPIO/audio/systemd validation
```

SSE/WebSocket은 실제로 Server push latency나 polling 부하 문제가 관측될 때 별도 패킷으로 평가한다.
고정 endpoint 또는 이번 replay acceptance의 선행 조건으로 묶지 않는다.
