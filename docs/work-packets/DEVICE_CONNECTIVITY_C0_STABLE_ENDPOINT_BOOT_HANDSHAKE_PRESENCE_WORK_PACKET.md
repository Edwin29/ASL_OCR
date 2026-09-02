# Device Connectivity C0 — Stable Endpoint · Startup Handshake · Presence 작업 패킷

상태: **승인됨 · 구현 및 로컬 검증 완료**  
작성일: 2026-08-31  
선행 조건: Integration V0 Coordinator, Server S0 persistent control plane, Server S1 incremental publish  
후속 조건: Server V4 durable bundle upload, Scanner V3-B sender/durable outbox, LAPTOP Integration E0,
Raspberry Pi Port P0  
개발 호스트 결정: `DEVICE_CONNECTIVITY_DEVELOPMENT_HOST_DECISION_20260831.md`

## 1. 목표와 우선 결정

C0는 장치 애플리케이션이 시작될 때 설정된 서버를 찾고, 서버가 정상이며 인증 가능한지 확인한 뒤,
장치의 최근 접속 상태를 서버에서 조회할 수 있게 하는 공통 연결 계층을 구현한다.

개발 단계에서는 **LAPTOP PC의 Device Runtime process 시작**을 Raspberry Pi 부팅의 대체 경계로
사용한다. C0 core와 HTTP 계약을 LAPTOP에서 먼저 검증하고, 이후 같은 설정·상태·wire 계약을 Pi의
systemd와 network-online 환경에 연결한다.

권위 있는 연결 판정은 공용 인터넷 접속 여부가 아니라 다음 단계의 성공이다.

```text
validated local config
  -> configured server hostname resolution/connection
  -> GET /api/v1/health
  -> authenticated presence start/heartbeat
  -> ONLINE
```

핵심 결정은 다음과 같다.

1. server URL은 자동 발견하거나 임시 tunnel 출력에서 추측하지 않고 명시적 설정으로 주입한다.
2. `device_id`는 MAC/IP/hostname에서 파생하지 않는 provisioned stable ID다.
3. public `/health` 성공만으로 장치 연결 완료로 보지 않고 authenticated presence까지 성공해야 한다.
4. HTTP는 지속 연결이 아니므로 server-side online 상태는 최근 heartbeat의 server 수신 시각에서
   계산한다.
5. device clock은 상태 판정의 권위가 아니며 server clock과 device monotonic clock을 사용한다.
6. C0 retry는 서버 연결 복구만 소유한다. 특정 Scanner artifact의 보존·재전송·ACK는 V3-B outbox가
   소유한다.
7. heartbeat 성공은 upload ACK 또는 datapack 완료를 뜻하지 않는다.
8. 실제 fixed DNS/tunnel/VPN을 개설하거나 배포하는 일은 C0 core 범위가 아니다. C0는 이미 제공된
   안정 endpoint를 사용하는 계약을 구현한다.

## 2. 현재 구현과 공백

### 2.1 이미 존재하는 기반

- `S0HttpClient(base_url, api_key, timeout_seconds)`는 명시적 HTTP(S) URL을 받는다.
- `GET /api/v1/health`는 DB migration/version과 writable probe를 수행한다.
- S0 `devices` 테이블에는 `first_seen_at`, `last_seen_at`가 있다.
- catalog/create/open 같은 device 업무 요청은 `last_seen_at`를 갱신한다.
- HTTP timeout, OS/DNS 계열 오류와 retryable server 응답은 `RecoverablePortError`로 분류된다.
- Coordinator에는 server retry feedback와 recoverable 상태 전이가 있다.

### 2.2 아직 없는 것

- device config file/env loader와 secret-safe validation
- process startup에서 시작되는 connection supervisor
- health response의 service/API compatibility identity
- authenticated presence start/heartbeat/disconnect API
- heartbeat session, boot/process identity와 sequence replay 처리
- server-side `online/stale/offline` projection 및 조회 API
- deterministic exponential backoff/jitter와 연결 상태 event
- 연결이 끊긴 동안 Coordinator/Scanner가 따라야 할 명시적 gate
- LAPTOP 실제 HTTP server stop/start 재연결 검증
- Windows 자동 시작 및 Raspberry Pi systemd integration

현재 `devices.last_seen_at`는 마지막 업무 요청의 흔적일 뿐이다. 이를 현재 접속 상태로 표시하지 않는다.

## 3. 책임 경계

### 3.1 C0가 소유

- stable endpoint와 device identity 설정 읽기·검증
- startup probe, server health/schema compatibility 확인
- authenticated presence session 시작과 heartbeat
- connection state, retry schedule와 connection event
- server clock 기반 presence 상태 계산
- server-side device presence 조회
- duplicate presence session 진단
- graceful process shutdown의 best-effort disconnect
- Coordinator가 사용할 narrow connectivity status/event port
- 로그와 API 응답에서 secret 제거

### 3.2 C0가 소유하지 않음

- Wi-Fi SSID/password 설정, captive portal, OS network configuration
- DNS record, static public IP, VPN, named tunnel 또는 TLS certificate 발급
- Scanner artifact upload body와 S1 handoff
- artifact durable outbox, upload retry count와 receipt lifecycle
- camera/frame/crop/UVDoc/identity
- catalog/scan/finalize/reading domain 동작
- STM/GPIO/lever, beep/TTS renderer 구현
- Windows Task Scheduler/서비스 등록
- Raspberry Pi systemd unit, camera/GPIO/audio adapter
- 관리자 계정·역할 분리, mTLS, device별 credential rotation
- production deployment와 외부 인터넷 security hardening

## 4. 개발·운영 호스트 경계

### 4.1 LAPTOP 개발 단계

LAPTOP에서 다음 process composition을 사용한다.

```text
LAPTOP Device App
  DeviceConnectivitySupervisor
  DeviceFlowCoordinator
  Book Scanner
  future V3-B outbox/sender
  STM/camera/feedback adapters
```

C0 supervisor는 Device App process가 시작될 때 즉시 시작한다. Windows 자체 자동 시작 등록은 후속
Integration E0 범위이지만, 자동 시작 여부와 무관하게 process 진입 후의 순서는 동일하다.

### 4.2 Raspberry Pi 이식 단계

Pi에서는 config와 HTTP/presence/state 계약을 바꾸지 않는다. 다음만 target adapter로 교체·검증한다.

- `/proc/sys/kernel/random/boot_id` 등 Linux boot identity source
- systemd `network-online.target` 이후 process 시작
- persistent config/secret/outbox directory
- camera/GPIO/serial/audio와 shutdown signal

C0 LAPTOP 통과를 Pi 부팅·성능·전원 차단 완료로 표시하지 않는다.

## 5. 설정 계약

권장 config는 versioned TOML 또는 동등한 typed config다. precedence는 명시적으로 고정한다.

```text
explicit test/program arguments
  > approved environment override
  > config file
  > safe defaults
```

최소 설정:

```toml
schema_version = 1
device_id = "asl-device-prototype-01"
server_base_url = "https://ocr.example.invalid"
api_key_file = "secrets/server-api-key.txt"
connect_timeout_seconds = 5.0
request_timeout_seconds = 10.0
heartbeat_interval_seconds = 15.0
stale_after_seconds = 45.0
offline_after_seconds = 120.0
retry_initial_seconds = 1.0
retry_max_seconds = 30.0
retry_jitter_fraction = 0.20
allow_insecure_http = false
```

규칙:

- `server_base_url`은 path/query/fragment가 없는 absolute HTTP(S) origin
- production 기본은 HTTPS이며 HTTP는 loopback/LAN 개발 profile에서 명시적으로만 허용
- URL에 credential/token을 넣지 않음
- API key 내용은 config/log/event/exception `repr`에 포함하지 않음
- `api_key_file`은 root-confined file 또는 OS secret adapter로 읽음
- `device_id`는 기존 S0 ID 규칙을 만족하고 재설치/재부팅 뒤에도 보존
- heartbeat `< stale < offline`, timeout/backoff 값은 양수이고 상한을 둠
- redirect로 다른 origin에 credential을 자동 전달하지 않음
- endpoint 후보를 무작위 순회하거나 quick tunnel 주소를 runtime에 자동 채택하지 않음

초기 구현은 단일 endpoint를 사용한다. primary/secondary failover는 server replication semantics가
정해지기 전 추가하지 않는다.

## 6. Device connection state machine

최소 상태:

```text
STOPPED
STARTING
PROBING
AUTHENTICATING
ONLINE
RETRY_WAIT
FATAL
SHUTTING_DOWN
```

전이:

```text
process start
  STOPPED -> STARTING -> PROBING

health ok + compatible
  PROBING -> AUTHENTICATING

presence accepted
  AUTHENTICATING -> ONLINE

retryable probe/heartbeat failure
  PROBING|AUTHENTICATING|ONLINE -> RETRY_WAIT
  -> scheduled retry -> PROBING

invalid config / unauthorized / incompatible API / TLS identity failure
  STARTING|PROBING|AUTHENTICATING -> FATAL

shutdown
  any nonterminal -> SHUTTING_DOWN -> STOPPED
```

규칙:

- `ONLINE` 진입은 같은 presence session의 authenticated server response 뒤에만 발생
- 성공한 heartbeat는 retry attempt를 0으로 reset
- 한 번의 timeout으로 FATAL 또는 artifact failure를 만들지 않음
- 401/403, incompatible service/schema, invalid certificate/hostname은 무한 retry로 감추지 않음
- 408/429/5xx, DNS/connection reset/timeout은 retryable
- retry는 `min(max, initial * 2^attempt)`에 injected jitter를 적용
- scheduling은 monotonic clock을 사용하고 시스템 wall-clock 변경에 영향받지 않음
- supervisor thread/task가 OCR·TTS·Scanner processing을 실행하지 않음

## 7. Health와 compatibility 계약

기존 endpoint를 additive하게 확장한다.

```http
GET /api/v1/health
```

예시:

```json
{
  "status": "ok",
  "service": "asl-ocr-server",
  "api_versions": ["v1"],
  "schema_version": 3,
  "database": "ok",
  "writable": true,
  "server_instance_id": "opaque-process-id"
}
```

- health는 public 유지하되 secret, filesystem path, hostname, DB path를 노출하지 않음
- `status=ok`, 예상 service, 필요한 API version, 최소 schema를 모두 확인
- `server_instance_id`는 process 재시작 관측용이며 device identity나 idempotency key로 사용하지 않음
- DB degraded는 ONLINE으로 전환하지 않음
- health GET은 `devices.last_seen_at`를 갱신하지 않음

## 8. Presence HTTP 계약

모든 presence endpoint는 `X-API-Key` 인증을 요구한다. 현재 prototype의 shared API key를 보존하되,
device별 credential/role 분리는 후속 security 패킷으로 남긴다.

```text
POST   /api/v1/devices/{device_id}/presence-sessions
PUT    /api/v1/devices/{device_id}/presence-sessions/{presence_session_id}
DELETE /api/v1/devices/{device_id}/presence-sessions/{presence_session_id}
GET    /api/v1/devices/{device_id}/presence
GET    /api/v1/devices
```

### 8.1 Presence start

```json
{
  "presence_session_id": "presence-...",
  "boot_id": "opaque-boot-or-process-id",
  "heartbeat_sequence": 0,
  "client_version": "0.1.0",
  "platform": "windows-laptop",
  "capabilities": ["scanner", "coordinator"]
}
```

- `presence_session_id`는 process start마다 새 opaque ID
- LAPTOP에서 portable boot ID를 얻지 못하면 process-run ID를 `boot_id`로 사용하고 provenance 명시
- 같은 session/start body replay는 멱등
- 같은 session ID에 다른 boot/device/body를 사용하면 409
- server가 받은 시각이 `started_at/last_seen_at`의 권위

### 8.2 Heartbeat

```json
{
  "boot_id": "opaque-boot-or-process-id",
  "heartbeat_sequence": 17,
  "connection_state": "online"
}
```

- sequence는 session 안에서 단조 증가
- 동일 sequence/same digest replay는 동일 응답
- 낮은 sequence는 stale replay로 성공 응답하되 `last_seen_at`를 앞으로 갱신하지 않음
- 동일 sequence/different digest는 409
- 더 높은 sequence만 `last_seen_at` 갱신
- client timestamp는 선택 diagnostics이며 online 판정에는 사용하지 않음
- 응답은 server time, accepted sequence와 다음 권장 heartbeat interval 포함

### 8.3 Disconnect

graceful shutdown은 DELETE를 best effort로 보낸다. 응답을 받지 못해도 종료를 막지 않으며, server는
heartbeat expiry를 최종 권위로 사용한다. disconnect 뒤 같은 session heartbeat는 409 terminal이다.

### 8.4 Server-side 조회

prototype 운영 조회는 다음을 반환한다.

```json
{
  "device_id": "asl-device-prototype-01",
  "status": "online",
  "first_seen_at": "server timestamp",
  "last_seen_at": "server timestamp",
  "active_session_count": 1,
  "split_brain_suspected": false,
  "sessions": []
}
```

`GET /api/v1/devices`는 deterministic order로 목록을 반환한다. session 상세에 API key, IP 전체,
filesystem path 또는 임의 client metadata를 그대로 반사하지 않는다.

## 9. Server presence schema — migration v3

S0/S1 SQLite database를 additive migration으로 확장하며 기존 DB를 삭제·재생성하지 않는다.

### 9.1 `device_presence_sessions`

```text
device_id FK
presence_session_id
boot_id
request_sha256
client_version
platform
capabilities_json
status: active | disconnected
last_heartbeat_sequence >= 0
last_heartbeat_sha256
started_at
last_seen_at
disconnected_at NULL
PRIMARY KEY(device_id, presence_session_id)
```

필요 index:

```text
(status, last_seen_at)
(device_id, status, last_seen_at)
```

온라인 상태는 DB에 주기적으로 rewrite하지 않고 조회 시 server now와 threshold로 계산한다.

```text
online:  now - latest active last_seen <= stale_after
stale:   stale_after < age <= offline_after
offline: active session 없음 또는 age > offline_after
```

graceful disconnect session은 즉시 offline 후보에서 제외한다. 같은 device에 online/stale active session이
둘 이상이면 요청을 임의 차단하지 않고 `split_brain_suspected=true`로 노출한다. 실제 catalog/scan
동시성은 기존 S0 invariant가 계속 막는다.

기존 업무 요청의 `_touch_device()`는 audit용 `devices.last_seen_at`를 계속 갱신할 수 있지만 presence
status는 `device_presence_sessions`의 authenticated heartbeat에서만 계산한다.

## 10. Coordinator와 Scanner 연계

C0는 `ConnectivityPort` 또는 동등한 narrow interface를 Device Runtime에 추가한다.

```python
current_status() -> ConnectivitySnapshot
poll(now) -> tuple[ConnectivityEvent, ...]
start() -> None
stop() -> None
```

최소 event:

- `CONNECTING`
- `SERVER_ONLINE`
- `SERVER_CONNECTION_LOST`
- `SERVER_RETRY_SCHEDULED`
- `SERVER_AUTH_FAILED`
- `SERVER_INCOMPATIBLE`
- `SERVER_RECOVERED`

Integration 규칙:

- 최초 ONLINE 전에는 catalog selection 및 새 scan을 시작하지 않음
- ONLINE에서 기존 Coordinator 흐름을 시작
- 연결 상실을 scan success, parser reject 또는 artifact ACK로 변환하지 않음
- V3-B durable outbox가 없을 때 연결이 상실되면 새 artifact commit/delivery 진입을 pause/freeze
- 이미 메모리에 있는 artifact를 버리거나 새 sequence로 재촬영하지 않음
- V3-B 이후에는 outbox capacity 정책이 capture 지속 여부를 결정
- feedback renderer는 `연결 중`, `서버 연결 실패`, `재연결됨` 같은 semantic code를 받되 C0 core는
  실제 한국어 TTS 파일을 소유하지 않음

## 11. Resource와 scheduling 정책

- 기본 heartbeat interval 15초, stale 45초, offline 120초는 prototype 시작값이며 config로 분리
- heartbeat request는 작은 JSON이며 OCR/TTS thread와 별도 실행
- 동시에 heartbeat 하나만 in-flight
- 이전 heartbeat가 끝나지 않았으면 queue를 누적하지 않고 timeout/retry state로 합침
- connection supervisor thread 수 기본 1
- client response body와 server request body에 작은 상한 적용
- server listing은 prototype에서 bounded limit을 두고 pagination은 후속 가능
- device business request piggyback은 audit `last_seen` 개선에 사용할 수 있으나 heartbeat를 대체하지 않음

## 12. 보안·개인정보 경계

- API key, Authorization value, config secret과 raw exception request header 로그 금지
- HTTPS certificate와 hostname 검증 기본 활성
- cross-origin redirect에 credential 전달 금지
- device가 보낸 IP/hostname/client timestamp를 신뢰 identity로 사용하지 않음
- `device_id`, boot/session ID는 path로 사용하지 않고 기존 ID validation 적용
- JSON body 64 KiB 이하, capability 수/문자열 길이 제한
- unknown JSON field 정책을 고정하고 중첩 임의 metadata 저장 금지
- server query는 prototype shared key로 보호하되 외부 배포 보안 완료로 주장하지 않음

## 13. 구현 단계

### Phase 0 — 계약 고정

- 개발 LAPTOP/Pi host substitution 경계 문서 연결
- config, connection states/events, health compatibility, presence wire schema 고정
- C0/V4/V3-B retry 책임 분리

### Phase 1 — Device config·pure supervisor

- typed config loader와 secret redaction
- injected clock/RNG/transport를 사용하는 deterministic state machine
- backoff/jitter, fatal/retryable 분류
- Coordinator narrow connectivity port/event

### Phase 2 — Server migration·presence service

- SQLite v3 additive migration
- presence start/heartbeat/disconnect repository/service
- server-clock status projection과 split-brain diagnostics
- restart/replay/concurrency tests

### Phase 3 — HTTP/API adapter

- health compatibility 확장
- authenticated presence routes와 server device list/status
- Device Runtime HTTP presence adapter
- redirect/timeout/body/auth/error 처리

### Phase 4 — LAPTOP composition

- config file/env에서 stable endpoint와 device ID 주입
- Device App process startup에서 supervisor 시작
- ONLINE 뒤 Coordinator 활성화
- process 종료 시 best-effort disconnect
- secret-free structured logging

### Phase 5 — Fault·회귀·보고

- real local/LAN Flask server stop/start 재연결
- wrong URL/DNS, refused port, timeout, 401, incompatible API, degraded DB
- process/server restart와 heartbeat replay
- Server S0/S1, Document Parser, Device Runtime, Book Scanner 회귀
- 구현 보고서와 미검증 Pi/V4/outbox 항목 명시

## 14. 테스트 행렬

### 14.1 Config

- valid HTTPS origin과 explicit development HTTP
- URL credential/path/query/fragment, empty device ID, invalid threshold 거부
- missing/unreadable secret file fail-fast
- secret가 repr/log/error/event에 나타나지 않음
- precedence와 relative secret path confinement

### 14.2 Pure state machine

- startup → probe → auth → online
- retryable failure의 deterministic exponential backoff/jitter와 max cap
- success 뒤 attempt reset
- auth/schema/TLS identity fatal 분류
- heartbeat loss → retry → recovered event 한 번
- shutdown 중 새 retry/heartbeat 0
- wall-clock 변경에도 schedule 불변

### 14.3 Migration·repository

- v2 → v3 migration, 반복 no-op, future schema fail-fast
- start replay mutation 0, same ID/different body 409
- heartbeat same sequence replay, stale lower sequence, different digest conflict
- server restart 뒤 presence history 보존
- disconnect idempotency와 post-disconnect heartbeat 거부
- multiple sessions의 deterministic split-brain projection

### 14.4 HTTP

- public health에 service/API/schema identity
- presence endpoints API key 필수
- malformed/oversized body, path ID, capability limit
- 401/403/404/408/409/429/5xx client mapping
- no cross-origin credential redirect
- GET device list/status가 server time으로 online/stale/offline 계산
- health GET이 device presence를 만들거나 갱신하지 않음

### 14.5 LAPTOP integration

- LAPTOP process start 뒤 configured server ONLINE
- server UI/API에서 해당 device와 latest heartbeat 확인
- server stop → connection-lost/retry, server restart → recovered
- client process restart가 새 presence session을 만들고 이전 session은 expiry/disconnect 처리
- 잘못된 key는 retry loop가 아니라 FATAL/auth feedback
- 연결 상실을 artifact ACK/scan 완료로 오인하지 않음
- log에 API key 0

### 14.6 회귀

- S0 catalog/scan/reading과 S1 status/finalize 회귀
- legacy `/jobs`, `/sessions`, `/datapacks` 보존
- Device Coordinator 기존 state/event 회귀
- Book Scanner frame/identity/V2 artifact 회귀
- C0 테스트에서 V4 upload/outbox 호출 0

## 15. 완료 기준

- LAPTOP Device App process 시작 시 별도 사용자 URL 입력 없이 configured endpoint로 연결 시도
- health와 authenticated presence가 모두 성공해야 ONLINE
- server에서 device의 first/last seen과 online/stale/offline 상태 조회 가능
- heartbeat/retry가 restart-safe server rows와 deterministic client state를 유지
- 연결 상실·복구가 structured event와 feedback 근거로 노출
- auth/schema/security 오류를 무한 network retry로 감추지 않음
- C0가 artifact upload/outbox ACK를 소유하지 않음
- 기존 S0/S1/Coordinator/Scanner 계약과 회귀 보존
- LAPTOP 실제 HTTP stop/start test 통과
- Pi systemd/자원/하드웨어 및 V4/outbox 미구현을 완료로 표시하지 않음

## 16. 명시적 후속 범위

### Server V4

- streamed bundle upload, server-owned temp storage, hash/limit validation
- atomic promotion과 S1 `accept_verified_spread()` handoff
- idempotent durable receipt와 upload error contract

### Scanner V3-B

- LAPTOP SQLite/filesystem durable outbox
- artifact lifecycle, upload retry, ACK 후 cleanup, quota/eviction
- process/OS restart 뒤 동일 sequence/artifact 복구

### LAPTOP Integration E0

- Windows 자동 시작 방식 결정
- 실제 STM serial, camera와 feedback renderer
- C0 + V4 + outbox + Coordinator full E2E/fault test

### Raspberry Pi Port P0

- systemd/network-online, Linux boot ID, persistent storage
- camera/GPIO/serial/audio adapter와 resource/thermal measurement
- 전원 차단·부팅·네트워크 변경 E2E

## 17. 승인 시 변경 범위

승인 시 다음을 구현한다.

- `device-runtime` connectivity config/domain/supervisor/HTTP adapter 및 tests
- Server S0 SQLite migration v3, presence service/API/status projection 및 tests
- existing health response의 additive compatibility fields
- Coordinator startup/connection event의 최소 additive 연계
- LAPTOP local/LAN fault integration harness
- C0 API/config 문서와 구현 보고서

다음은 승인 범위에 포함하지 않는다.

- Server V4 upload endpoint와 S1 artifact handoff
- Scanner V3-B durable outbox/sender
- 실제 fixed DNS/tunnel/VPN/TLS infrastructure 개설
- Windows 자동 시작 등록과 Raspberry Pi systemd/하드웨어 이식
- production credential system/mTLS
- 배포, commit, push, PR

## 18. 중단 조건

다음이 확인되면 silent workaround 없이 구현을 중단하고 보고한다.

- authenticated presence 없이 public health만으로 ONLINE 처리해야 함
- stable endpoint 대신 runtime이 임시 URL을 scrape/추측해야 함
- C0가 Scanner artifact를 메모리에서 삭제하거나 ACK로 표시해야 함
- heartbeat를 보내기 위해 OCR/Scanner/TTS main loop를 blocking해야 함
- server online 판정에 device wall clock을 신뢰해야 함
- API key를 URL, log 또는 persisted diagnostics에 평문 노출해야 함
- SQLite migration이 기존 S0/S1 data를 삭제·재생성해야 함
- LAPTOP과 Pi에 서로 다른 HTTP/domain protocol이 필요함
- V4 upload/outbox를 동시에 구현하지 않으면 C0 연결 계약을 검증할 수 없음
- 실제 fixed external server가 없다는 이유로 local/LAN C0 core를 완료로 가장해야 함

중단 시 config/pure supervisor/server presence/HTTP/LAPTOP integration 중 실제 검증된 단계까지만
완료로 기록하고, 나머지를 같은 성공 상태로 묶지 않는다.

## 19. 구현 결과 (2026-08-31)

승인 범위의 config, supervisor, presence persistence/API, HTTP adapter, Coordinator gate와 LAPTOP
loopback stop/restart harness를 구현했다. SQLite는 기존 v2 데이터를 보존하며 v3으로 전진하고,
실제 HTTP 재접속은 동일 DB와 presence session을 사용해 복구됨을 확인했다.

검증 결과는 Device Runtime 47 passed, Document Parser 552 passed/4 skipped, Book Scanner 288
passed다. 세부 명령 범위와 미검증 조건은 `DEVICE_CONNECTIVITY_C0_IMPLEMENTATION_REPORT.md`에
기록했다.

패킷에서 제외한 V4 upload/outbox, 외부 fixed endpoint/TLS, Windows 자동 시작, Raspberry Pi
systemd/network/hardware 이식은 구현하지 않았으며 완료로 처리하지 않는다.
