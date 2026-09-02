# Server S0 구현 보고서

작성일: 2026-08-31  
범위: 승인된 `docs/work-packets/SERVER_S0_PERSISTENT_CONTROL_PLANE_WORK_PACKET.md`의 S0, Server S1/V4 제외

## 결론

Server S0의 영속 control plane을 구현했다. 서버 재시작 후에도 catalog, active scan,
seal cutoff, reading cursor, command receipt가 SQLite에 남는다. 신규 scan의 seal은
`SEALING/FINALIZING`까지만 기록하며, fragment/parser/append가 없는 상태를 READY로 표시하지 않는다.

## 구현 내용

- SQLite forward migration과 connection-per-operation transaction
- datapack catalog 및 기존 검증 datapack의 revision 1 bootstrap
- draft 생성, scan open/recovery, datapack별 active scan 1개 제약
- 동일 cutoff seal intent 멱등 처리와 다른 cutoff 충돌
- `page_id`/`focus_item_id` 안정 앵커를 포함한 reading progress
- command receipt와 progress를 한 transaction에서 commit하는 exactly-once navigation
- `(datapack_id, revision, manifest_sha256)` loader cache 및 명시 invalidation API
- `/api/v1` catalog/scan/reading API, API key, 64 KiB 제한, 구조화 오류
- combined server opt-in wiring 및 CLI `--state-db`
- Coordinator create/open operation ID 계약과 표준 라이브러리 HTTP client adapters
- legacy `/jobs`, `/sessions`, `/datapacks` 경로 보존

## 확인된 동작

- migration 반복 적용과 프로세스 재생성 후 catalog bootstrap no-op
- create 재시도 시 draft 1개와 동일 응답
- 같은 장치의 active scan 복구, 다른 장치의 동시 scan 409
- 같은 seal cutoff 재시도 mutation 0, 다른 cutoff 409
- reading command 응답 유실 가정 재시도 후 page 이동 1회
- 재시작 후 같은 reading session ID와 durable cursor 복원
- 응답 audio reference에 absolute filesystem path 미노출
- 손상된 legacy 디렉터리를 READY로 import하지 않음
- Coordinator가 선택 event ID를 create/scan-open operation lineage로 전달

## 검증 결과

```text
Document Parser unit: 531 passed, 4 skipped, 3 subtests passed
Device runtime:       33 passed
S0 core + HTTP:       13 passed (위 전체 수치에 포함)
Legacy/S0 server set: 30 passed (위 전체 수치에 포함)
py_compile:           touched Python modules passed
git diff --check:     whitespace errors 0
```

실제 Raspberry Pi/STM, 실제 네트워크 장애 주입, multi-process 부하, 장시간 DB 용량 시험은 수행하지
않았다. 따라서 해당 항목은 완료로 간주하지 않는다.

개발 단계의 실제 HTTP/device 검증은 LAPTOP PC가 Raspberry Pi 역할을 대체하여 먼저 수행한다.
현재 S0 완료는 HTTP adapter의 단위 계약까지이며 LAPTOP 부팅 연결·presence·실네트워크 E2E를
포함하지 않는다. Pi 검증은 LAPTOP 통합 후 target-specific 단계로 분리한다.

## 남은 경계

- Server S1: fragment row, parser 실행, append assembly, atomic revision publish, SEALED/READY
  (S0 보고서 작성 당시 후속이었으며 현재 별도 S1 패킷으로 완료)
- Device Connectivity C0: LAPTOP boot-equivalent 연결, 고정 endpoint, presence/heartbeat, 재연결
- Scanner V3-B / Server V4: artifact upload body, LAPTOP durable outbox, retry/cache/ACK
- audio byte streaming과 device cache
- catalog rename/delete/admin UI와 운영 backup/restore
- LAPTOP 실제 통신 지연·process/OS 재시작 E2E
- Raspberry Pi systemd·전원 차단·자원·하드웨어 E2E

특히 현재 S0 API에 Scanner 이미지 artifact를 보내는 경로는 없다. Coordinator의 `DeliveryPort`는
후속 V4가 구현될 때까지 기존 fake/시험 adapter 경계로 남는다.
