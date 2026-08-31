# ASL OCR 통합 구조 재점검 기록

상태: **기록 완료 — Integration V0 작업의 근거**
작성일: 2026-08-30
검토 기준:

- GitHub `ASL_OCR` commit `b6244884b86913b41159e6cdd97ab493dc37862f`
- 현재 Book Scanner 작업 checkout `e90156f2f5b7e88f3ac940717ee39a5af7fdceb7`
- 현재 `book-scanner` Video V0~V2 및 V3-A 제안
- `document-parser` datapack ingest/combined server/session store/STM bridge

## 1. 결론

현재 구현에는 세 개의 서로 다른 수명주기가 존재한다.

1. **촬영 수명주기**: frame 표본 수집, 후보 선택, crop/UVDoc, 전달 가능 artifact 생성
2. **데이터팩 수명주기**: 기존/신규 데이터팩 선택, spread 접수, parser 실행, append, seal/finalize
3. **읽기 수명주기**: 데이터팩 선택, 장치별 위치 복구, 버튼 navigation, 점자·오디오 응답

어느 한 모듈도 이 세 수명주기를 모두 소유해서는 안 된다. `book-scanner`와
`document-parser` 위에 장치 애플리케이션 상태를 소유하는 별도 `DeviceFlowCoordinator`가
필요하다.

따라서 Scanner V3-A 구현에 바로 들어가기 전에, cross-component 계약과 coordinator 순수
상태기계를 Integration V0으로 먼저 고정한다.

### 1.1 개발 호스트 결정 (2026-08-31 추가)

개발 단계에서는 LAPTOP PC가 Raspberry Pi의 애플리케이션 호스트 역할을 대체한다. Scanner,
Coordinator, HTTP client와 후속 durable outbox를 LAPTOP에서 먼저 통합하고, 동일 계약을 유지한 채
Raspberry Pi로 이식한다. LAPTOP 통합과 Pi target 검증은 별도 완료 단계다. 상세 결정은
`DEVICE_CONNECTIVITY_DEVELOPMENT_HOST_DECISION_20260831.md`를 따른다.

## 2. b624488에서 확인한 사실

commit `b624488`의 직접 변경은 `server/cli.py`에 CONFIRM SHORT/LONG 명령을 추가하고 실제
오디오 재생 검증에서 발견한 공백을 메운 것이다.

해당 commit 계열의 `device_flow.py`는 다음 경계를 이미 전제로 한다.

- 데이터팩 선택 화면은 `SpeechController`나 bare CLI가 아니라 client-side 상위 flow 책임
- `CONFIRM SHORT`는 선택 화면에서 항목 선택, 읽기 화면에서 현재 항목 replay
- `CONFIRM LONG`은 읽기 화면에서 선택 화면으로 복귀
- `DatapackSession`은 이미 선택된 `book_id`만 받으며, 미선택 상태를 소유하지 않음
- STM bridge는 serial/HTTP 변환기이며 데이터팩·navigation state를 직접 소유하지 않음

이는 사용자가 제안한 “현재 상태에 따라 Book Scanner와 HTTP API를 조율하는 상위 객체”와
일치한다. 다만 b624488 계열의 flow에는 Scanner 상태, `[새 데이터팩 추가]`, append scan,
scan seal/finalize가 아직 없다.

## 3. 브랜치 통합 상태

현재 Book Scanner checkout과 b624488은 어느 한쪽이 다른 쪽의 ancestor가 아니다.

```text
current Book Scanner checkout: e90156f
b624488 integration branch:    b624488
merge base:                    1efc4cd
```

b624488 계열에는 `device_flow.py`, selection/reading 통합 및 CONFIRM 동작이 추가되었고, 현재
checkout에는 더 발전된 sampled-frame, seam-conservative, UVDoc atomic artifact 구현이 있다.

그러므로 한쪽 구현을 다른 쪽의 최신 통합본으로 간주해 덮어쓰지 않는다. Integration V0에서
공통 계약을 먼저 정하고 이후 필요한 commit을 선택적으로 통합해야 한다.

## 4. 책임 경계

### 4.1 DeviceFlowCoordinator

소유:

- 장치 전체 화면/모드 상태
- STM 버튼·레버 event의 상태별 routing
- 데이터팩 catalog 탐색과 `[새 데이터팩 추가]`
- 기존 데이터팩 append 또는 신규 draft 생성 선택
- Book Scanner 시작·중단
- spread delivery, flush, scan seal/finalize 순서
- reading session 시작과 서버 저장 위치 복구
- 전송·최종화·재접속에 대한 사용자 feedback 시점

소유하지 않음:

- OpenCV, seam, UVDoc, OCR, 점역
- 데이터팩 파일/DB 직접 저장
- navigation 알고리즘
- serial/HTTP 세부 구현

### 4.2 Book Scanner

소유:

- frame sampling 및 후보 안정성
- obstruction/layout/local quality 판정
- 동일 source frame의 좌우 seam-conservative crop
- UVDoc correction과 atomic artifact
- page/spread identity, single in-flight, page-change gate
- 물리 조정을 위한 semantic guidance reason

소유하지 않음:

- 데이터팩 선택·생성·append·finalize
- reading cursor
- HTTP endpoint와 DB schema
- 서버 ACK를 임의로 성공 처리하는 정책

Book Scanner가 TTS 문구의 원인을 결정할 수는 있지만, 실제 재생 timing과 전송/최종화 문구는
Coordinator가 소유한다.

### 4.3 Server

소유:

- 데이터팩 catalog, draft/ready/error 상태와 revision
- scan session과 page/spread 순서
- idempotent snapshot/spread 접수
- Document Parser OCR·점역·TTS 작업
- 기존 데이터팩 append와 신규 데이터팩 생성
- seal 이후 atomic revision publish
- 장치별 persistent reading progress
- navigation command idempotency
- 원격 장치가 가져갈 수 있는 audio resource

소유하지 않음:

- 카메라 frame의 물리적 배치 안내
- 다음 frame 후보 선택
- page-turn 영상 판정

## 5. 현재 서버 구현의 공백

### 5.1 Whole-batch ingest와 append의 차이

현재 `/jobs`는 여러 이미지를 한 번에 받아 `build_datapack()`을 호출하는 내부 테스트 경로다.

- 임의 job ID이며 request idempotency가 없음
- job registry가 in-memory
- 개별 spread append, sequence, seal 개념이 없음
- `build_datapack()`은 `manifest.json`과 `document.json`을 다시 씀
- 기존 데이터팩을 읽고 있는 session에 새 revision을 안전하게 publish하지 않음

따라서 제품 Scanner upload API로 그대로 사용하지 않는다.

### 5.2 Session과 읽기 위치

현재 `SessionStore`는 loaded datapack과 active session을 process memory에 보관한다.

- 서버 재시작 시 reading progress 소실
- `session_id` 기본값 공유 시 장치 충돌 가능
- disk datapack이 바뀌어도 cached datapack invalidation 없음
- command network retry 시 같은 이동을 두 번 적용할 수 있음

장치에 로컬 저장장치가 없다는 문제를 해결하려면 server DB에
`device_id + datapack_id -> navigation cursor`를 저장해야 한다. 파일 저장이 없는 장치라도
재식별 가능한 stable device ID는 필요하며 STM UID 또는 provisioned ID를 사용해야 한다.

### 5.3 Audio 전달

현재 wire response의 `audio_ref`와 catalog의 title audio는 server-local absolute path다. 서버와
Raspberry Pi가 다른 장치면 해당 경로를 열 수 없다. HTTP audio URL/stream 또는 동등한 remote
resource 계약이 별도로 필요하다.

## 6. 권장 데이터 흐름

```text
BOOT/CONNECTING
  -> DATAPACK_SELECT
  -> SCAN_SESSION_OPEN
  -> SCANNING
  -> FLUSHING_UPLOADS
  -> DATAPACK_FINALIZING
  -> READING
  -> DATAPACK_SELECT
```

### 6.1 데이터팩 선택

- 서버가 저장된 데이터팩 catalog와 상태를 반환
- Coordinator가 목록 끝에 `[새 데이터팩 추가]` pseudo-item을 삽입
- 기존 항목 선택: 해당 데이터팩을 target으로 append scan session 생성
- 새 항목 선택: server가 기본 제목의 empty draft를 만들고 scan session 생성
- 입력 장치에 문자를 넣는 UI가 없으므로 기본 제목은 날짜/순번으로 만들고 추후 관리 기능에서
  변경하는 방식을 우선 사용

### 6.2 Spread 처리

- Scanner는 같은 source frame의 corrected left/right를 하나의 `SpreadArtifact`로 제공
- Coordinator/delivery port가 같은 batch로 server에 접수
- server는 client sequence와 side를 보존
- 비동기 parser 작업 완료 순서가 달라도 최종 page order는 client sequence, left/right로 결정
- network retry는 같은 idempotency key와 request digest를 사용

### 6.3 확인 버튼과 scan seal

스캔 중 CONFIRM은 새 capture 생성을 즉시 중단하되, 이미 선택·저장된 마지막 artifact를
잃어서는 안 된다.

1. Scanner를 freeze하고 마지막 local sequence `N` 고정
2. `N` 이하 artifact의 durable server ACK를 기다림
3. `seal(through_sequence=N)` 요청
4. server는 `N` 이후 upload 거부
5. `N` 이하 접수 작업이 terminal 상태가 될 때까지 `FINALIZING`
6. 모든 page fragment가 유효할 때 새 datapack revision atomic publish
7. publish 이후 저장 완료 feedback 및 reading session 시작

ACK 전 process/전원 손실을 복구하려면 device host의 durable outbox가 필요하다. 개발 단계에서는
LAPTOP persistent storage로 먼저 구현하고, 이후 Pi의 writable storage로 같은 계약을 이식한다.
안전한 persistent storage가 없다면 ACK 이전에는 사용자가 페이지를 넘기도록 안내하지 않는 정책이
최소 안전장치다.

### 6.4 Datapack append

기존 datapack 디렉터리에 processing 결과를 바로 덮어쓰지 않는다.

- 각 accepted spread를 immutable page fragment로 저장
- 기존 current revision + 새 fragment로 staging revision 구성
- 기존 page/item ID를 보존하고 새 page를 뒤에 append
- manifest/document/audio index 검증
- staging revision을 원자적으로 current revision으로 publish
- 실패 시 기존 current revision 유지

parser 실패 페이지를 조용히 생략해 READY datapack으로 만들지 않는다. scan session을
`FINALIZE_BLOCKED` 또는 명시적 partial 상태로 남기고 사용자 선택을 요구한다.

## 7. Feedback와 fallback

### Scanner local retry

- 책 이동, 손 가림, page moving, local crop/UVDoc 실패
- upload 없음
- 새 후보를 찾도록 물리 안내

### Network/remote retry

- 이미 생성된 같은 artifact를 보존
- 새 frame을 촬영하지 않고 같은 idempotency key로 retry
- 서버 ACK 전에는 전송 완료 feedback 없음

### Parser reject

- accepted page/identity로 기록하지 않음
- artifact와 구조화된 reject reason 보존
- 재촬영 안내 또는 명시적 fallback 후보 실행
- UVDoc 실패를 silent unwarped success로 대체하지 않음

### Finalize failure

- 기존 datapack revision 유지
- draft/scan session과 error diagnostics 보존
- 읽기 화면으로 자동 진입하지 않음

## 8. 우선순위 결정

1. **Integration V0**: coordinator 순수 상태기계, domain contract, ports, deterministic fake
2. **Scanner V3-A 수정·구현**: identity, single in-flight, page-change, coordinator ACK 입력
3. **Server S0**: persistent catalog, scan domain, reading progress, command idempotency
4. **Server S1**: incremental page fragment, append, seal, atomic datapack revision
5. **Device Connectivity C0**: LAPTOP 고정 endpoint, handshake, presence/heartbeat, 재연결
6. **Scanner V3-B + Server V4**: LAPTOP durable outbox와 실제 spread HTTP ingest
7. **LAPTOP Device Integration**: STM/카메라/HTTP/audio adapter와 실제 E2E
8. **Raspberry Pi Port/Target Validation**: 동일 계약 이식, systemd·자원·하드웨어·전원 검증

Integration V0 이전에는 Book Scanner engine, STM bridge 또는 HTTP server 중 하나에 상위 흐름을
임의로 밀어 넣지 않는다.

## 9. 미결·후속 검증

- LAPTOP outbox directory·quota·fsync·OS restart 정책
- Raspberry Pi에 같은 outbox 계약을 둘 writable persistent storage가 실제로 있는지
- 한 datapack에 동시에 여러 scan session을 허용할지: 초기 권고는 하나만 허용하고 409
- parser failure에서 partial finalize를 사용자에게 허용할지
- 기존 데이터팩 선택 시 항상 append scan을 거칠지: 현재 요구사항 기준으로는 거친 뒤 reading
- 새 데이터팩 자동 제목 형식
- 완료 feedback 기준: spread durable ingest ACK와 datapack finalization 완료를 서로 다른 음으로
  구분
- LAPTOP에서 audio download/cache와 frame processing의 resource 간섭을 먼저 계측
- Pi에서 같은 workload의 CPU/RSS/온도/지연 간섭

위 항목은 실제 검증 전 완료로 표시하지 않는다.
