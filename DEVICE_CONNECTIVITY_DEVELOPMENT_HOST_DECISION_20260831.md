# Device Connectivity 개발 호스트 대체 결정

상태: **아키텍처 결정 기록 완료 · 구현 후속**  
기록일: 2026-08-31  
영향 범위: Book Scanner, Device Runtime, Server V4, Device Connectivity C0, 최종 Raspberry Pi 이식

구현 패킷: `DEVICE_CONNECTIVITY_C0_STABLE_ENDPOINT_BOOT_HANDSHAKE_PRESENCE_WORK_PACKET.md`

## 1. 결정

개발 단계에서는 **LAPTOP PC가 최종 Raspberry Pi 4의 애플리케이션 호스트 역할을 대체**한다.
LAPTOP PC에서 먼저 다음 책임을 통합·검증한다.

- 카메라 입력과 Book Scanner frame/crop/UVDoc/identity 실행
- `DeviceFlowCoordinator` 실행
- 서버 endpoint 설정, 부팅에 대응하는 연결 bootstrap과 재연결
- Scanner artifact의 durable outbox, HTTP 송신과 ACK 처리
- STM 버튼·레버 입력 adapter와 beep/TTS feedback adapter 연결
- 서버 catalog/scan/finalize/reading API 사용

서버는 장치 호스트와 별도 책임이다. 개발 편의를 위해 같은 PC의 loopback으로 실행할 수는 있지만,
연결 계약 검증은 별도 서버 주소를 사용하는 경우와 동일하게 수행한다. 최종 구성에서는 LAPTOP PC
대신 Raspberry Pi가 같은 Device Runtime·Scanner·HTTP 계약을 실행한다.

## 2. 변하지 않는 계약

- stable `device_id`, idempotency key, scan/artifact identity와 서버 schema
- 고정된 server base URL을 설정에서 주입하는 방식
- server-owned bundle ACK, S1 fragment/finalize와 immutable revision 계약
- 동일 artifact를 보존하는 outbox/retry 원칙
- Coordinator 상태와 Scanner/Document Parser 책임 분리

LAPTOP과 Raspberry Pi에 서로 다른 domain flow 또는 별도 전송 protocol을 만들지 않는다.

## 3. 개발 환경에서 먼저 검증할 것

1. 설정 파일 또는 환경변수의 고정 server URL과 provisioned `device_id`
2. 네트워크 interface → DNS → `/api/v1/health` → authenticated presence 순서의 bootstrap
3. timeout, exponential backoff/jitter, 연결 단절과 자동 재접속
4. server-side `first_seen/last_seen`, boot ID와 `online/stale/offline` projection
5. process/PC 재시작 뒤 durable outbox와 동일 artifact 재전송
6. 실제 HTTP upload, S1 ACK/finalize polling과 완료 feedback
7. STM serial 및 개발용 카메라를 포함한 LAPTOP E2E

공용 인터넷 연결 자체가 아니라 **설정된 서버에 도달 가능한지**를 최종 연결 기준으로 사용한다.

## 4. Raspberry Pi 이식 때 별도로 검증할 것

- Raspberry Pi OS/Linux camera adapter와 장치 권한
- systemd 자동 시작·종료, boot ordering과 network-online 의존성
- writable persistent storage 위치, 용량, fsync와 전원 차단 내구성
- CPU/RSS/온도/처리 지연과 모델 적합성
- GPIO/USB/serial/audio 장치명과 재연결
- 실제 전원 차단·부팅·네트워크 변경 E2E

따라서 LAPTOP E2E 성공은 기능 계약의 선행 검증이지만 Raspberry Pi 성능·부팅·하드웨어 검증 완료를
뜻하지 않는다.

## 5. 기존 완료 패킷에 대한 영향

Integration V0, Server S0, Server S1과 Scanner V3-A.5의 완료 기준은 변경하지 않는다. 이 패킷들은
각각 pure coordinator, control plane, incremental publish, scanner identity 범위를 완료했으며 실제
장치 통합을 완료로 주장하지 않았다.

수정이 필요한 부분은 후속 범위의 표현이다.

- `Pi durable outbox` → 개발 단계 `LAPTOP durable outbox`, 이후 동일 저장 계약의 Pi 이식
- `Device Integration` → `LAPTOP Device Integration`과 `Raspberry Pi Port/Target Validation` 분리
- 실제 network 미검증 → LAPTOP 기반 C0/V4 network fault 검증을 먼저 수행
- Pi 전용 항목은 systemd, camera/GPIO/audio adapter, 자원 및 전원 차단 검증으로 한정

현재 구현에는 아직 boot connectivity/presence/heartbeat가 없으므로 이를 완료로 소급 기록하지 않는다.
