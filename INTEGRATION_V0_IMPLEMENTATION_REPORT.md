# Integration V0 구현 보고서

상태: **구현 및 단위 회귀 검증 완료**
작성일: 2026-08-30
근거 패킷: `docs/work-packets/INTEGRATION_V0_DEVICE_FLOW_COORDINATOR_WORK_PACKET.md`

## 1. 구현 결과

`device-runtime`을 새 top-level package로 추가하고, Book Scanner와 Document Parser 위에서
장치 전체 흐름을 조율할 순수 Python 계약과 상태기계를 구현했다.

구현 파일은 다음 책임으로 분리했다.

- `types.py`: ID, catalog, scan, artifact, delivery, finalize, reading의 immutable value
- `protocols.py`: Catalog, scan session, Scanner, delivery, reading, feedback, clock port
- `catalog.py`: server catalog filtering과 단일 `[새 데이터팩 추가]` projection
- `events.py`: semantic coordinator/feedback event
- `coordinator.py`: 입력 routing과 selection → scanning → finalize → reading 상태 전이

Coordinator는 실제 HTTP, SQLite, camera, UVDoc, OCR, TTS, serial 구현을 import하지 않는다.
외부 시스템은 모두 protocol 뒤에 있으며 V0 테스트에서는 deterministic fake로 대체했다.

## 2. 고정한 핵심 계약

- 기존 datapack은 append scan을 열고, 새 항목은 DRAFT를 만든 뒤 scan을 연다.
- Scanner artifact에는 Coordinator가 scan session 안에서 단조 증가 sequence를 부여한다.
- 전달 큐 일시 장애 시 이미 선별된 artifact와 동일 sequence를 보관하여 재시도한다.
- parser reject 뒤 재캡처는 실패한 logical sequence를 대체하여 순서의 hole을 남기지 않는다.
- scanning CONFIRM은 Scanner를 먼저 freeze하고 cutoff 이하 delivery가 끝난 뒤 seal한다.
- server가 READY를 반환하기 전에는 저장 완료 feedback이나 reading session을 열지 않는다.
- reading은 장치의 임의 기본값이 아니라 server가 반환한 cursor에서 시작한다.
- CONFIRM SHORT/LONG은 현재 상태에 따라 scan stop, reading replay, selection 복귀로 분기한다.
- input/scanner event 중복과 이전 session의 delivery/finalize callback은 상태를 다시 바꾸지 않는다.
- feedback 출력 실패는 성공한 domain 전이를 되돌리지 않는다.

## 3. 검증 결과

### Integration V0 자체 검증

- 단위 테스트: **26 passed**
- source/test bytecode compile: 통과
- source/docs trailing-whitespace scan: 통과
- core forbidden import 검색: HTTP/serial/OpenCV/OCR/GPU/TTS 구현 import 없음

검증에는 catalog, append/new scan, event deduplication, stale lineage 차단, monotonic sequence,
queue 장애 재시도, ACK/reject, freeze/flush/seal, finalize READY, reading cursor, 버튼 routing,
feedback failure를 포함했다.

### Book Scanner 회귀

- `book-scanner/tests/unit`: **204 passed**
- OpenCV가 설치된 기존 `document-parser/.venv`와 repository-local pytest dependency를 사용했다.

### Document Parser 회귀

2026-08-31에 `document-parser/tests/unit` 전체를 별도로 재실행하여 정상 종료를 확인했다.

- 결과: **492 passed, 29 skipped, 3 subtests passed**
- 종료 코드: **0**
- 실행 시간: **5.95초**
- Python: `document-parser/.venv`의 Python 3.11.8
- 누락된 순수 Python 필수 의존성 `pypdf`만 workspace-local 임시 dependency 경로로 제공

29개 skip은 실패가 아니다. Flask 선택 의존성이 없는 환경의 remote-ingest/HTTP 테스트와
실제 Piper 한국어 모델·espeak data 환경변수가 필요한 통합 테스트가 테스트 자체의 조건에
따라 명시적으로 skip되었다. 따라서 작업 패킷의 기존 Document Parser **단위 테스트 회귀
없음** 기준은 충족한 것으로 판정한다. 실제 Flask/Piper 통합 검증은 아래 미실행 항목으로
계속 분리한다.

## 4. 실행하지 않은 검증

- 실제 HTTP client/server와 idempotency
- 실제 SQLite catalog/outbox/progress persistence
- 실제 camera 및 Book Scanner V3-A artifact 연결
- 실제 UVDoc, Document Parser OCR·점역 처리
- 실제 STM 버튼/lever 입력
- 실제 beep/TTS feedback
- Flask 선택 의존성을 사용한 실제 remote-ingest/HTTP adapter
- 실제 Piper 한국어 모델과 espeak data를 사용한 음성 통합
- Raspberry Pi 4의 지연, 메모리, 재시작 복구

후속 실제 adapter 통합은 먼저 LAPTOP PC가 Raspberry Pi 역할을 대체하여 수행한다. 이 보고서의
V0 결과는 pure coordinator 검증이므로 LAPTOP E2E까지 실행했다는 의미는 아니며, Pi target 검증은
그 이후 별도 단계로 남는다.

위 항목은 Integration V0 완료 결과에 포함하지 않는다.

## 5. 후속 경계

다음 구현은 V0 protocol을 adapter로 연결하는 순서가 적절하다.

1. Scanner V3-A의 page identity/change gate를 `ScannerRuntime` artifact event에 연결
2. server catalog/scan session/delivery/finalize/reading API 계약과 adapter 구현
3. LAPTOP persistent storage를 사용하는 durable outbox, upload idempotency와 재시작 복구 구현
4. LAPTOP에서 STM input adapter와 semantic feedback renderer 통합
5. 동일 계약을 Raspberry Pi로 이식하고 target-specific 부팅·자원·하드웨어 검증

V3-A를 구현할 때 Scanner가 datapack, HTTP ACK, reading cursor를 소유하게 만들지 않는다.
