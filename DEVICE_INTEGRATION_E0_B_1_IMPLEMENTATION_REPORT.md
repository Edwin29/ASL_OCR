# Device Integration E0-B.1 구현 보고서

작성일: 2026-09-01
작업 패킷: `docs/work-packets/DEVICE_INTEGRATION_E0_B_1_TAILSCALE_REPLAY_ACCEPTANCE_WORK_PACKET.md`
상태: **software implementation, Desktop Tailscale Serve와 실제 Laptop remote replay/upload/reading 성공 /
E0-B.3 구조화 boundary report 재수집 대기 / physical acceptance 대기**

## 결과

E0-B.1의 코드 경계는 구현됐다. 기존 REST, C0 heartbeat, V4 multipart, finalize polling과 reading
command API는 변경하지 않았다. Laptop은 camera와 STM 없이 준비된 MP4, console controls와 JSONL
feedback으로 하드웨어 직전의 전체 remote flow를 실행할 수 있다. Desktop은 loopback bench Server를
Tailscale Serve의 stable private `*.ts.net` HTTPS origin으로 연결하는 start/check/stop wrapper를 갖는다.

Desktop tailnet의 Serve 활성화와 fixed private HTTPS smoke는 완료됐다. 실제 Laptop 첫 실행에서 footer
collection budget과 누락된 EOF bridge blocker를 확인한 뒤 E0-B.2를 반영해 동일 영상을 재실행했다.
재실행은 `spread_sent` 2개, EOF queued/acked 2/2, user confirm 뒤 READY, reading snapshot과 navigation까지
통과했다. Server에도 spread 2개, fragment 4개, duplicate 0이 확인됐다. E0-B.3은 이 성공 결과와 정상
거부 candidate의 terminal reason을 구조화하는 observer diagnostics를 추가했으며, 새 diagnostics를 포함한
동일 Laptop report의 재수집만 남았다. 실제 camera/HC-05/STM/speaker physical E0-B는 계속 대기다.

## 구현 내용

### Reading snapshot evidence

- console + JSONL 기본 composition에 `JsonLineReadingPresenter` 연결
- Server-backed `reading_session_id`, `datapack_id`, `cursor`, `braille_cells`, `audio_ref` 출력
- 동일 snapshot polling 중복 억제, reading 전 `None` 생략
- write/flush 실패를 진단 실패로 격리하여 ACK/domain state rollback 방지
- STM presenter와 Windows audio 경로는 변경하지 않음

### Replay profile와 setup

- `device-app.e0b.replay.example.toml`: replay Scanner + console + JSONL 전용 authority
- 기존 Laptop setup에 explicit `-ReplayVideo` mode 추가
- replay mode에서 COM/camera prompt, config mutation과 physical preflight 제거
- model bundle 구조 및 Paddle manifest hash 검증 유지
- 입력 MP4를 fixed config-root path로 복사하고 첫 frame decode 검증
- secret-safe `e0b-replay-input.json`에 파일명, 크기, SHA-256과 첫 frame 해상도 기록
- double-click 가능한 replay setup/run batch 추가

### Tailscale Serve

- local bench `/api/v1/health` 성공 전에 Serve를 바꾸지 않음
- Tailscale binary/daemon/online/MagicDNS 상태를 local status에서 동적 확인
- `tailscale serve --bg --yes 8421` 뒤 Serve status 확인
- 실제 사용자 FQDN을 repository에 hard-code하지 않고 `ORIGIN=https://<fqdn>` 출력
- HTTPS health의 `server_instance_id`를 local loopback health와 비교
- reset wrapper 제공; Funnel/public exposure는 추가하지 않음
- Cloudflare Quick Tunnel wrapper는 one-run fallback으로 보존

## 검증 결과

### 집중 검증

- reading presenter + application/config unit: `13 passed`
- PowerShell setup/start/stop script parser: `3 passed`
- replay MP4 decode/hash helper: passed (`64x48` codec fixture)
- noninteractive replay setup smoke: passed
  - replay config가 camera/STM authority를 포함하지 않음
  - model bundle manifest/hash 검증과 copy 성공
  - MP4 decode/hash JSON report 생성 성공
- Desktop bench Server loopback health: `status=ok`, instance ID 존재

### 전체 회귀

| 프로젝트 | 결과 |
|---|---:|
| Device Runtime | 83 passed, 3 skipped |
| Book Scanner | 289 passed |
| Document Parser | 602 passed, 4 skipped |

첫 전체 회귀에서 공용 `tmp` 아래 explicit basetemp 생성이 Windows permission error를 냈다. 제품/테스트
assertion 실패가 아니며, 기존 지침대로 package-local ASCII temp를 사용해 Device/Scanner가 통과했다.
Document Parser는 cache plugin을 끄고 기본 temp 경로로 재실행해 602/602가 통과했다.

### Tailscale Desktop smoke 상태

- Desktop Tailscale binary/version/service/login/online/MagicDNS 상태 확인: 통과
- local bench Server health: 통과
- tailnet 관리 화면 최초 Serve 활성화: 완료
- `tailscale serve --bg --yes 8421`: 통과
- private HTTPS health와 local health의 같은 `server_instance_id`: 통과
- Serve reset 뒤 status `{}`: 통과
- Serve 재적용 뒤 MagicDNS hostname 동일: 통과
- 재시작 private HTTPS health `status=ok`: 통과

관리 활성화 URL과 실제 private FQDN에는 node/tailnet 식별자가 들어가므로 report/repository에 기록하지
않았다. API key와 Tailscale credential도 기록하지 않았다. 현재 Serve와 bench Server는 Laptop 시험을
위해 실행 상태로 유지했다.

## 남은 acceptance

1. E0-B.3 revision을 Laptop에 반영
2. 동일 prepared MP4로 identity `4/5 + content_occluded`, `1/5 + source_exhausted` report 수집
3. Server receipt/fragment/duplicate `2/4/0`과 결합해 report `passed` 확인
4. 이후 physical E0-B에서 camera + HC-05/STM + speaker 검증

Remote transport/lifecycle happy path는 통과했지만 E0-B.3 구조화 report와 physical E0-B는 완료로 표시하지
않는다.

## 범위 준수

SSE/WebSocket, Funnel, Server schema 변경, 다중 writer, lease, quarantine, 일반화 quota/GC, service
auto-start와 exhaustive crash/WAN matrix는 구현하지 않았다. false ACK와 duplicate fragment를 막는 기존
V3-B/V4 계약은 그대로 유지했다.
