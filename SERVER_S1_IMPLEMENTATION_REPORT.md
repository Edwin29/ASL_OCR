# Server S1 구현 보고서

상태: **구현 및 로컬 회귀 검증 완료**  
기준일: 2026-08-31  
승인 패킷: `SERVER_S1_INCREMENTAL_FRAGMENT_APPEND_PUBLISH_WORK_PACKET.md`

## 1. 구현 결과

Server S1의 transport-neutral core를 구현했다.

- SQLite schema v2: spread, left/right fragment, finalize journal 및 scan publish 상태
- Scanner V2 bundle의 manifest/file/hash/image/경로/양면 readiness 검증
- 동일 sequence·동일 digest receipt 재사용과 sequence/artifact 충돌 차단
- lease와 제한 재시도를 갖는 재시작 가능한 페이지 fragment worker
- UVDoc side image만 받는 Document Parser adapter와 deterministic page ID
- base datapack 보존, `sequence -> left -> right` 순서 append, 신규 TTS 조립
- 전체 datapack loader/navigation 검증 후 immutable revision 승격
- filesystem 승격과 SQLite current revision 전환 사이 crash recovery journal
- 기존 READY append 실패 시 기존 revision 보존, 신규 DRAFT 실패 시 DRAFT 복원
- cutoff 0의 기존 데이터팩 no-op 및 빈 신규 DRAFT 명시 실패
- S0 seal/status API에 finalize enqueue, spread 상태, published revision 투영
- legacy `/jobs`와 S1이 Paddle/TTS 인스턴스를 동시에 사용하지 않도록 직렬화 wrapper 적용

S1 ACK의 의미는 parser 완료가 아니라 **서버 소유 bundle 검증 + spread/fragment DB commit 완료**로
고정했다. 외부 artifact body를 받는 HTTP endpoint는 승인 범위대로 만들지 않았다.

## 2. 검증 결과

2026-08-31 로컬 Windows 환경에서 다음을 실행했다.

```text
S1 집중 테스트
15 passed

Document Parser 전체 테스트
546 passed, 4 skipped, 3 subtests passed

Device Runtime 전체 테스트
34 passed
```

집중 테스트는 durable/idempotent acceptance, bundle 변조/미등록 파일 거부, parser composition,
sequence 충돌, transient retry와 restart, cutoff gate, 신규 publish, 기존 append, 기존 anchor/페이지
보존, TTS 실패 rollback, promotion 이후 crash recovery, 대기 run의 head-of-line 차단 방지, S1 HTTP
status 및 device READY mapping을 포함한다. 또한 crash 뒤 승격된 revision의 WAV가 변조되면
SHA-256/WAV metadata 재검증에서 DB publish 전에 거부되는 경우를 검증했다.

전체 회귀의 4개 skip은 기존 환경 조건부 테스트다. 기존 `latex_ast.py`의 invalid escape
`SyntaxWarning` 1건은 남아 있으며 S1 변경에서 발생한 경고가 아니다.

## 3. 완료로 처리하지 않은 사항

다음은 이번 결과로 검증하거나 구현했다고 보지 않는다.

- Scanner device에서 실제 bytes를 전송하는 production HTTP upload protocol
- LAPTOP durable outbox, 재전송 backoff, 캐시 quota/eviction 및 이후 Pi storage 이식
- 실제 PaddleOCR-VL GPU 및 Piper 음성 모델을 사용한 S1 end-to-end 실행
- 실제 수능특강 영상/프레임에서의 처리량, 지연, GPU/메모리 계측
- LAPTOP 카메라, STM 버튼, TTS 피드백을 포함한 개발 장치 통합
- Raspberry Pi 4 systemd·camera/GPIO/audio·자원·전원 차단 target 검증
- LAN 장애, TLS, 서버 재부팅을 포함한 실제 네트워크 fault test
- partial finalize, 특정 sequence 교체/재촬영, orphan revision 정리 관리자 기능
- 배포, commit, push, PR

개발 단계에서는 LAPTOP PC가 Raspberry Pi의 Scanner/Coordinator/HTTP client/outbox 호스트 역할을
대체한다. 현재 S1 검증은 server-local fixture 경계까지이므로 LAPTOP 실제 송신·연결 E2E를 포함하지
않는다. LAPTOP에서 C0/V4를 먼저 검증한 뒤 Pi의 systemd·camera/GPIO/audio·자원·전원 차단을 별도
검증한다.

따라서 현재 Scanner가 네트워크로 S1에 직접 송신할 수 있는 상태는 아니다. 다음 경계는 Server V4의
업로드 writer가 byte stream을 검증된 server-owned bundle로 원자 저장하고, 그 후 S1
`accept_verified_spread()`를 호출하는 것이다.

## 4. 보존된 기존 구조

- S0 catalog/scan/reading API와 SQLite revision pointer
- legacy `/jobs`, `/sessions`, `/datapacks` 시험 경로
- 기존 datapack revision directory 및 기존 page/focus/audio identity
- Coordinator의 `FINALIZING -> READY` polling 계약
- 현재 작업 트리의 기존 사용자 변경과 실험 산출물

이번 구현 과정에서 commit 또는 push는 수행하지 않았다.
