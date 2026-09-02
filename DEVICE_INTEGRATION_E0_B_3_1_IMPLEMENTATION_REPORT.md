# Device Integration E0-B.3.1 구현 보고서

작성일: 2026-09-01
작업 패킷: `docs/work-packets/DEVICE_INTEGRATION_E0_B_3_1_CONSOLE_IDEMPOTENCY_NAMESPACE_REPAIR_WORK_PACKET.md`
상태: **구현 및 local 회귀 완료 / 실제 Laptop fresh datapack 재확인 대기**

## 결과

서로 다른 console application process가 같은 입력 순서를 사용할 때 S0 create/open operation key가
충돌하던 문제를 교정했다. `ConsoleControlSource` event ID는 이제 C0 process `boot_id`를 namespace로
사용한다.

```text
before: console-00000003:create
after:  console-process-<uuid>-00000003:create
```

새 process는 새 namespace를 얻고, 한 process 안에서는 기존 counter 순서를 유지한다. Server S0/V4
idempotency, receipt, DB schema와 Scanner 판정은 변경하지 않았다.

## 검증

- explicit namespace에서 counter 1, 2 확인
- 별도 source instance의 첫 event ID 불일치 확인
- Server `:scan-open` suffix 포함 128자 이하 확인
- empty/space/non-ASCII/과도한/leading-hyphen namespace 거부
- Device Runtime 전체: `105 passed, 3 skipped`
- Book Scanner 및 Document Parser source diff: 0

## 남은 실제 확인

Laptop이 수정 revision을 반영한 뒤 `새 데이터팩 추가`의 `confirm_selection.datapack_id`가 이전
`datapack-3a17d02954854113a882b4fe216e6e07`과 달라야 한다. 충돌이 관측된 진행 중 실행은 diagnostics
부분 관찰로만 보존하며 final E0-B.3 acceptance에는 사용하지 않는다.
