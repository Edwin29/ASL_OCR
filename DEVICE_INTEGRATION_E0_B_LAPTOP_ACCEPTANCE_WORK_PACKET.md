# Device Integration E0-B — Laptop Acceptance 작업 패킷

상태: **승인됨 / software implementation 완료 / physical acceptance 대기**
기준일: 2026-09-01
선행 조건: Device Integration E0-Core, Scanner V3-B, Server V4, C0/S0/S1

## 1. 목표

E0-Core에서 검증한 Device composition을 실제 Windows Laptop의 camera, STM serial과 speaker에
연결하고, Laptop과 같은 LAN에 있지 않은 현재 개발용 desktop Server까지 인터넷 HTTPS tunnel로
연결했을 때 기존 순서 계약이 유지되는지 판정한다. 이 패킷은 새 upload protocol이나 운영 hardening을
설계하는 패킷이 아니다.

```text
STM NAV/HELLO
  -> DeviceInputEvent / current braille FRAME
  -> Coordinator
  -> live camera Scanner V2 artifact
  -> V3-B durable outbox
  -> Internet HTTPS tunnel
  -> desktop 127.0.0.1 bench Server V4 ACK
  -> SPREAD_SENT beep
  -> stop / flush / seal / READY
  -> DATAPACK_SAVED beep + speech
```

## 2. 포함 범위

- `pc_camera`의 명시적 index, width, height, FPS 적용과 실제 capture mode 검증
- 기존 STM firmware의 `HELLO`, `NAV,<direction>,<action>` line protocol
- 한 serial connection에서 STM 입력과 `FRAME` 응답을 직렬화
- 10-cell viewport/cell count 일치와 6-dot cell 범위 검증
- bounded poll, firmware debounce를 보완하는 최소 host debounce, bounded reconnect backoff
- semantic feedback의 비동기 Windows beep/SAPI speech rendering
- ACK 이후 `SPREAD_SENT`, READY 이후 `DATAPACK_SAVED`라는 기존 순서 보존
- model/server/camera/serial/audio를 확인하는 secret-safe `--preflight` JSON report
- 실제 C0/S0/V4 HTTP, SQLite, S1 worker를 사용하는 desktop deterministic bench server
- desktop loopback origin을 공개 HTTPS origin으로 연결하는 Cloudflare Tunnel 절차
- 인터넷에 연결된 Laptop에서 동일 revision과 model assets를 준비하는 절차
- 실제 Laptop에서 수행할 acceptance runbook과 관측 latency 기록

## 3. 제외 범위

- Server S0/S1/C0/V4 schema나 public API 변경
- V3-B multi-writer, lease, quota/GC, quarantine와 exhaustive crash matrix
- production Access policy/mTLS, credential rotation, tunnel service auto-start와 WAN fault matrix
- 다중 tunnel/region, 장시간 availability와 exhaustive disconnect/recovery 검증
- Windows service/auto-start와 Raspberry Pi systemd/GPIO 이식
- 새로운 STM firmware 기능 또는 Bluetooth pairing 자동화
- remote audio byte endpoint/cache
- Scanner threshold/model 재학습과 M1 held-out 일반화
- 전체 active scan process restart checkpoint

## 4. STM 계약

현재 firmware 호환 입력은 다음과 같다.

```text
HELLO
NAV,U,S
NAV,D,L
NAV,L,S
NAV,R,L
```

adapter는 기존 문서의 확장 token `N/P/C/V`도 domain control로 변환하지만, 실제 firmware가 보내지
않은 token을 Acceptance 성공 근거로 삼지 않는다. `HELLO`와 모든 valid `NAV` 뒤에는 같은 serial
writer가 현재 `ReadingSnapshot`의 FRAME을 보낸다. reading 전에는 blank frame을 보내 handshake만
완료한다. malformed line은 추측해 변환하지 않는다.

```text
FRAME,page,node,math_span,braille_offset,generation,c0,...,c9
```

- `viewport_size == cell_count == 10`
- cell은 current firmware가 수용하는 `[0, 63]`
- serial read는 application poll마다 최대 16줄
- host duplicate debounce 기본 30ms
- reconnect 기본 500ms에서 5s까지 bounded exponential backoff
- reconnect/HELLO 뒤 current 또는 blank frame 재전송

## 5. Camera 계약

Laptop config는 `camera_index`, `camera_width`, `camera_height`를 명시하고 필요 시 FPS를 명시한다.
OpenCV가 요청 mode를 적용하지 못하면 시작을 실패시켜 잘못된 저해상도 capture를 Acceptance로
오인하지 않는다. camera source는 기존 latest-frame drain과 `release()` lifecycle을 유지한다.

## 6. Feedback 계약

feedback rendering은 Coordinator thread 밖의 bounded worker에서 실행한다. JSON trace를 함께 남길 수
있으며 API key, image bytes, manifest path를 speech로 전달하지 않는다.

- `SPREAD_SENT`: V4 receipt identity가 local ACK로 확정된 뒤 한 번의 high beep
- `FINALIZING`: flush와 seal 이후 진행 beep/speech
- `DATAPACK_SAVED`: READY 뒤 ascending beep와 완료 speech
- server loss/recovery와 parser reject: 구분 가능한 pattern/문구
- catalog speech는 `title` detail만 사용

audio 실패는 domain state를 되돌리지 않는다.

## 7. Preflight와 실행

```powershell
# Desktop terminal 1
python -m document_parser.server.e0b_bench_server --state-root state/e0b-bench --api-key-file secrets/device-api-key.txt

# Desktop terminal 2: one-run fallback; named tunnel is preferred for a stable endpoint
cloudflared tunnel --url http://localhost:8421

# Laptop
python -m asl_device --config device-app.e0b.toml --preflight --report reports/e0b-preflight.json
python -m asl_device --config device-app.e0b.toml
```

Bench server는 desktop `127.0.0.1:8421`에만 bind하며 실제 C0/S0/V4 route, SQLite upload journal,
S1 worker, revision publish와 reading API를 사용한다. OCR/TTS content 변환만 deterministic fixture로
대체한다. `cloudflared`는 이 loopback origin으로 outbound tunnel을 만들며 Laptop은 공개 `https://`
origin만 사용한다. 고정 hostname의 named tunnel을 권장하고 Quick Tunnel은 URL을 config에 수동 반영한
단일 실행에만 허용한다. Preflight는 remote HTTPS/non-loopback profile, Scanner model load, remote server
`/api/v1/health`, camera, serial과 audio를 독립 check로 기록한다. API key 값은 report에 기록하지 않는다.

## 8. 테스트 행렬

- E0-B nested config parse와 unknown/mismatch reject
- viewport/cell count mismatch reject
- HELLO -> blank FRAME
- NAV -> exact DeviceInputEvent -> current FRAME
- host debounce 중에도 firmware가 요구한 FRAME 응답 유지
- disconnect -> bounded reconnect -> HELLO response
- 6-dot 범위 밖 cell reject
- presenter가 coordinator input/poll 뒤 실행되고 shared serial을 한 번만 close
- ACK beep와 READY beep/speech 구분
- catalog title 외 detail을 speech로 노출하지 않음
- preflight의 independent failure capture와 secret-safe report
- bench server의 direct non-loopback bind 거부와 실제 health/auth/SQLite 구성
- remote E0-B profile의 HTTPS/non-loopback 강제
- requested camera mode apply/verify/release
- E0-Core actual HTTP/SQLite response-loss E2E 회귀
- Book Scanner와 Document Parser 전체 회귀

## 9. Physical Acceptance 완료 기준

실제 Laptop에서 다음 증거가 있어야 E0-B를 완료로 바꾼다.

1. preflight 6개 check 모두 `passed`
2. 실제 STM `HELLO` 뒤 blank/current FRAME 수신
3. 실제 버튼 입력이 domain control과 일치하고 한 press가 한 command로 처리
4. configured camera mode의 live frame과 Scanner artifact 1개 이상 생성
5. Laptop과 다른 network의 desktop Server에 대해 HTTPS C0 ONLINE과 V3-B -> V4 receipt 성공
6. ACK 전 sent beep 0, valid ACK 뒤 sent beep 1
7. flush 전 seal 0, READY 전 saved speech 0, READY 뒤 saved speech 1
8. reading FRAME이 10-cell STM에 표시되고 후속 NAV에 갱신
9. app stop 뒤 camera, COM port와 audio worker release
10. preflight report, 실행 로그, 관측 capture/upload/ACK/READY latency 보존

현재 저장소의 자동 테스트는 software boundary를 검증한다. 물리 장치와 실제 external tunnel 실측이
없으므로 위 완료 기준을 아직 충족했다고 주장하지 않는다. 같은 LAN은 요구하지 않지만 Laptop과
desktop 양쪽의 외부 인터넷 연결 및 remote HTTPS health 성공은 E0-B 완료 조건이다.
