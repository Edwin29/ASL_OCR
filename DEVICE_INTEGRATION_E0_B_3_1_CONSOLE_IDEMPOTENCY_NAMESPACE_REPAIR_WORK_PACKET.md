# Device Integration E0-B.3.1 — Console Idempotency Namespace Repair 작업 패킷

상태: **승인됨 / 즉시 구현**
기준일: 2026-09-01
성격: **E0-B.3 실제 Laptop 재검증을 막는 작은 local-control identity 교정**

## 1. 관측과 원인

E0-B.3 실제 Laptop 재실행에서 사용자가 `새 데이터팩 추가`를 선택했지만 Server가 이전 실행의
`datapack-3a17d02954854113a882b4fe216e6e07`을 다시 반환했다.

Console control event ID가 모든 프로세스에서 다음처럼 다시 시작하는 것이 원인이다.

```text
console-00000001
console-00000002
console-00000003
```

Coordinator는 confirm event ID에 `:create`, `:scan-open`을 붙여 S0 Idempotency-Key로 사용한다. 이전
실행과 같은 수의 navigation 뒤 confirm하면 새 사용자 intent인데도 같은 key가 만들어지고, Server는
정상적인 idempotent replay로 과거 datapack/scan-session receipt를 반환한다.

## 2. 목표

1. 서로 다른 application process의 console event ID가 충돌하지 않게 한다.
2. 한 process 안에서는 기존 순서와 event identity를 안정적으로 유지한다.
3. S0 Server의 idempotency receipt, schema와 replay 규칙은 변경하지 않는다.
4. E0-B.3 재실행에서 `새 데이터팩 추가`가 이전 READY datapack이 아닌 새 datapack을 만들게 한다.

## 3. 구현 범위

- `ConsoleControlSource`에 process별 safe-ASCII event namespace 추가
- 기본 namespace는 process마다 새 UUID 기반 값
- local composition에서는 이미 존재하는 C0 `boot_id`를 console namespace로 공유
- event ID 형식은 bounded Server ID 범위 안에서 다음처럼 생성

```text
console-process-<uuid>-00000001
```

- deterministic unit test를 위한 explicit namespace injection 허용
- 서로 다른 source instance의 첫 event가 서로 다름을 회귀로 고정
- unsafe/과도한 namespace 거부
- Quickstart와 E0-B.3 보고서에 이전 실행과 datapack ID가 달라야 함을 명시

## 4. 제외 범위

- S0/V4 idempotency contract 또는 DB receipt 변경
- Server의 과거 receipt 삭제/만료/GC
- Device ID 변경
- Scanner candidate/identity/ACK/finalize 의미 변경
- STM serial event identity 변경
- 현재 진행 중인 충돌 실행을 성공 evidence로 승격
- 운영 hardening 또는 crash matrix 확대

## 5. 불변식

- 같은 logical event object를 중복 처리할 때 event ID는 변하지 않는다.
- 새 process의 새 user intent는 이전 process의 operation key를 재사용하지 않는다.
- event ID와 `:create`/`:scan-open` suffix는 S0 safe ASCII 128자 제한 안에 있다.
- API key, model path 또는 사용자 경로는 event ID에 포함하지 않는다.
- Server가 동일 key에 동일 response를 돌려주는 기존 보수성은 그대로 유지한다.

## 6. 테스트와 완료 기준

- explicit namespace에서 counter가 1, 2로 단조 증가
- 서로 다른 default `ConsoleControlSource`의 첫 event ID가 다름
- unsafe namespace 입력 거부
- Device Runtime 전체 회귀가 기존 `98 passed, 3 skipped` 이상
- Book Scanner와 Document Parser에는 code diff 0
- Laptop 재실행에서 `새 데이터팩 추가` confirm의 datapack ID가 이전
  `datapack-3a17d02954854113a882b4fe216e6e07`과 다름

마지막 Laptop 확인은 코드 반영 후 사용자가 수행한다. commit/push는 별도 요청 전에는 수행하지 않는다.
