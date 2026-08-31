# Device Connectivity C0 구현 보고서

상태: **구현 및 로컬 검증 완료**  
기준일: 2026-08-31  
승인 패킷: `DEVICE_CONNECTIVITY_C0_STABLE_ENDPOINT_BOOT_HANDSHAKE_PRESENCE_WORK_PACKET.md`

## 결론

개발 단계의 LAPTOP Device Runtime이 고정 설정을 읽고 서버 호환성 확인, 인증된 presence 등록,
heartbeat, 연결 상실과 재접속을 수행하는 C0 경계를 구현했다. 서버는 SQLite schema v3에 세션을
보존하고 server clock 기준 `online/stale/offline` 상태와 복수 활성 세션 진단을 제공한다.
Coordinator는 C0가 `ONLINE`이 되기 전 catalog를 열지 않으며, 스캔 중 연결 상실 시 Scanner를
중지하고 복구 가능한 상태로 전이한다.

이는 Scanner artifact 송신이 완료됐다는 의미가 아니다. V4 업로드 프로토콜과 durable outbox,
업로드 ACK, 캐시/재전송 및 페이지 중복 억제는 의도적으로 후속 패킷에 남겼다.

## 구현 범위

- secret-safe TOML/env config, stable device identity, HTTPS 기본 및 로컬 HTTP 명시적 opt-in
- public health의 service/API/schema/process identity 확인
- 인증된 presence start/heartbeat/disconnect와 request replay/collision 처리
- persistent SQLite v2 -> v3 migration, server-clock presence projection
- poll-driven connectivity supervisor, exponential backoff와 jitter, fatal/retryable 오류 분리
- Coordinator startup/recovery gate와 연결 상태 feedback/event
- 실제 LAPTOP loopback HTTP stop/restart 및 동일 SQLite/session 복구 시험

주요 구현 파일:

- `device-runtime/src/asl_device/connectivity_config.py`
- `device-runtime/src/asl_device/connectivity.py`
- `device-runtime/src/asl_device/adapters/http_connectivity.py`
- `device-runtime/src/asl_device/connectivity_composition.py`
- `device-runtime/src/asl_device/coordinator.py`
- `document-parser/src/document_parser/server/c0_presence.py`
- `document-parser/src/document_parser/server/s0_http.py`
- `document-parser/src/document_parser/server/s0_migrations.py`

## 검증 결과

2026-08-31 로컬 환경에서 다음을 확인했다.

| 범위 | 결과 | 비고 |
|---|---:|---|
| Device Runtime 전체 | 47 passed | C0 unit, HTTP adapter, Coordinator, 실제 loopback 통합 포함 |
| Document Parser 전체 | 552 passed, 4 skipped | 1 existing warning, 3 subtests passed |
| C0 server focused | 6 passed | v2 -> v3 보존 migration 포함 |
| S0/S1/C0/combined focused | 38 passed | 1 existing warning |
| Book Scanner 전체 | 288 passed | 프로젝트 내부 ASCII `basetemp` 사용 |

Book Scanner의 최초 기본 temp 경로 실행은 한글 Windows 사용자 경로가 깨져 OpenCV 파일 생성이
실패했고, 이는 제품 assertion 실패가 아니었다. 프로젝트 내부 ASCII 임시 경로로 재실행한 전체
288개 테스트가 통과했다.

실제 HTTP 통합 시험은 임의 loopback port에 서버를 열고 presence를 `online`으로 확인한 뒤 서버를
중단했다. 다음 heartbeat에서 loss/retry를 확인하고 같은 port와 SQLite DB로 서버를 재기동하여
동일 `presence_session_id`가 `SERVER_RECOVERED`로 복구되고 활성 세션 수가 1임을 확인했다.

## 완료로 처리하지 않은 사항

- 외부 고정 DNS/IP, TLS 인증서, VPN/tunnel 구성 및 실제 LAN/인터넷 왕복
- Windows 자동 시작과 Raspberry Pi 4 `systemd`/`network-online` 이식
- Wi-Fi 재연결, DNS 장애, captive portal, 장시간 heartbeat 부하 시험
- 장치별 자격 증명 또는 mTLS로의 강화(현재는 기존 shared API key 계약)
- Server V4 bundle upload, Scanner sender/durable outbox, ACK와 캐시 정리
- 카메라·STM·TTS 하드웨어와 결합한 end-to-end 운전

따라서 다음 우선순위는 C0를 다시 확장하는 것이 아니라, C0의 `ONLINE` gate 아래에서 동작할
Server V4 업로드 계약을 먼저 고정하고 그 다음 Scanner 송신/durable outbox를 구현하는 것이다.
