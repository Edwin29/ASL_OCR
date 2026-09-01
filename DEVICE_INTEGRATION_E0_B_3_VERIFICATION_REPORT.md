# Device Integration E0-B.3 검증 보고서

작성일: 2026-09-01
작업 패킷: `DEVICE_INTEGRATION_E0_B_3_REPLAY_BOUNDARY_VERIFICATION_WORK_PACKET.md`
상태: **observer diagnostics 구현 및 local 회귀 완료 / 동일 Laptop 영상의 E0-B.3 구조화 report 재수집 대기**

## 결론

Scanner의 candidate, opaque identity, artifact, ACK 판정은 변경하지 않았다. E0-B.3은 진행 중인
identity collector가 hard reject 또는 replay EOF로 폐기될 때 bounded terminal event를 추가하고, 기존
candidate/identity lifecycle event를 Device JSONL feedback으로 전달한다.

승인 전 실제 Laptop 실행은 다음 remote software flow를 이미 통과했다.

- 고정 source SHA-256
  `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
- `spread_sent` sequence 1, 2
- EOF `queued_count=2`, `acked_count=2`
- user confirm 뒤 `datapack_saved(revision=1)`과 `reading_resumed`
- changed reading snapshot 및 up/down/left/right navigation
- Server spread receipt 2개, left/right fragment 4개, duplicate 0

따라서 transport/lifecycle happy path는 성공했다. 다만 새 diagnostics로 314/315의 `4/5 +
content_occluded`와 318의 `1/5 + source_exhausted`를 한 실행에서 다시 수집한 실제 Laptop JSON report는
아직 없다. 이 보고서는 그 재실행 전까지 E0-B.3 자체를 최종 완료로 과장하지 않는다.

## 구현 내용

### Observer-only Scanner event

- `opaque_identity_aborted`를 hard reject와 source exhaustion 경계에서 한 번 방출
- terminal reason, valid/missing observation 수와 기존 query count만 포함
- collector를 폐기하기 직전에 관찰하며 state transition, artifact 및 identity bank에는 영향 없음
- 기존 `candidate_selected`, collection started/observed/decided event 의미는 보존

### Device JSONL feedback

- `candidate_selected`
- `identity_collection_started`
- `identity_collection_progress`
- `identity_collection_decided`
- `identity_collection_aborted`

Device adapter는 frame/spread ID, bounded count/reason/timing만 whitelist한다. invalid observation은 progress로
출력하지 않고 raw token, pair digest, image, API key와 model path는 출력하지 않는다. Coordinator에서는
diagnostic feedback만 best-effort로 내보내며 domain/queue/ACK state를 변경하지 않는다.

### Exact-source report

`tools/windows/e0b_replay_boundary_report.py`는 PowerShell transcript의 JSON object line, setup source report와
optional Server summary를 결합한다. 다음을 자동 검사한다.

- source hash/status
- sequence `[1, 2]`
- EOF queued/acked `2/2`
- `content_occluded`에서 identity `4/5` abort
- `source_exhausted`에서 identity `1/5` abort
- Server receipt/fragment/duplicate `2/4/0`

Server summary가 없으면 `provisional`, 모든 증거가 일치하면 `passed`, supplied evidence가 불일치하면
`failed`다. unrecognized input field는 report에 복사하지 않는다.

## 보수 계약 동결

다음 동작을 단위 테스트로 고정했다.

- candidate 3 + identity 4 + hard reject -> abort event 1, artifact 0
- candidate 3 + identity 1 + EOF -> abort event 1, artifact 0, source exhausted
- valid progress만 Device feedback으로 전달
- raw identity evidence 비노출
- diagnostics가 Coordinator의 state/queue/ACK를 변경하지 않음
- malformed Server evidence가 provisional success로 낮아지지 않음

stable candidate frame의 identity evidence 재사용, EOF padding, N=5/K/candidate threshold 변경, 자동
ACK/finalize는 구현하지 않았다.

## 회귀 결과

| 범위 | 결과 |
|---|---:|
| Book Scanner 전체 | 298 passed |
| Device Runtime 전체 | 98 passed, 3 skipped |
| Document Parser core | 573 passed, 4 skipped |
| Document Parser hardware bridge | 29 passed |
| Document Parser 합계 | 602 passed, 4 skipped |

Book Scanner를 기본 Windows 사용자 temp에서 처음 실행했을 때 non-ASCII 경로를 OpenCV가 열지 못해 기존
파일 I/O 테스트 6개가 실패했다. 저장소 내부 ASCII basetemp로 동일 suite를 재실행해 298개가 통과했다.
Document Parser 최초 명령도 package import path가 빠져 collection에 실패했으며, 권위 있는
`document-parser/src` PYTHONPATH로 재실행해 위 기준이 통과했다. 두 경우 모두 제품 assertion 회귀가
아니다.

## 실제 Laptop에서 남은 한 번의 확인

1. 이 revision을 Laptop에 반영한다.
2. 같은 prepared MP4/hash로 fresh datapack replay를 실행하면서 transcript를 저장한다.
3. EOF `queued=2`, `acked=2`와 user confirm 뒤 READY/read/navigation을 확인한다.
4. Server summary `2/4/0`을 준비한다.
5. boundary report를 `--server-summary`와 실행해 `status=passed`를 보존한다.

이 확인 후 E0-B remote software acceptance를 최종 종료할 수 있다. 실제 camera, HC-05/STM, 점자 셀과
speaker는 계속 별도 physical acceptance 범위다.

## 범위 준수

Server S0/S1/V4, DB schema, V3-B outbox, Scanner threshold와 production/physical profile은 변경하지 않았다.
다중 writer, quota, lease, quarantine, exhaustive crash/WAN matrix도 포함하지 않았다. commit/push/PR은
별도 승인 범위라 수행하지 않았다.
