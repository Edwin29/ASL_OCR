# Device Integration E0-B.2 구현 보고서

작성일: 2026-09-01
작업 패킷: `DEVICE_INTEGRATION_E0_B_2_REPLAY_COMPLETION_REPAIR_WORK_PACKET.md`
상태: **software implementation 및 회귀 완료 / 실제 Laptop replay 재검증 대기**

## 결과

E0-B.1 실제 Laptop replay에서 확인된 두 blocker를 승인 범위 안에서 교정했다.

1. Laptop CPU에서 첫 Paddle footer recognition 약 2.9초가 기존 opaque collection 기본
   `1500ms`를 초과해 N=5 중 1개만 모으고 timeout되던 문제
2. Book Scanner가 replay EOF를 발생시켜도 Device Runtime adapter가 버려 사용자가 계속 처리 중으로
   오인하던 문제

Server, V4, V3-B, candidate/obstruction 알고리즘은 변경하지 않았다. production/physical profile의
기존 `1500ms`, N=5, K threshold와 false ACK/duplicate fragment 불변식도 유지했다.

## 구현 내용

### Replay-only footer collection budget

- Device `[scanner]` config에 optional `opaque_identity_max_collection_ms` 추가
- `profile="replay"`에서만 허용하고 `1..60000ms`로 제한
- 미지정 시 Book Scanner 기본 `1500ms` 유지
- E0-B replay example은 `30000ms` 명시
- local composition에서 Book Scanner runtime까지 값 전달
- runtime은 기존 `VideoScannerConfig` 중 `opaque_footer_identity.max_collection_ms`만 교체
- candidate, identity, page change와 N=5/K 값은 기존 config 그대로 보존

### Replay source exhausted bridge

- Device `ScannerEventType.SOURCE_EXHAUSTED` 추가
- Book Scanner adapter가 session lineage와 event ID를 보존해 mapping
- Coordinator `SCAN_INPUT_EXHAUSTED` event/feedback 추가
- feedback detail은 `queued_count`, `acked_count`만 기록
- event ID dedup으로 같은 EOF event의 feedback 중복 방지
- Coordinator는 SCANNING을 유지하고 delivery polling을 계속함
- EOF에서 freeze, flush, seal, ACK 또는 READY를 자동 실행하지 않음

### 실행 안내

- replay batch 시작 메시지에 EOF 이후 행동 추가
- Quickstart/runbook에 기존 config root 재생성 또는 timeout 값 확인 절차 추가
- `queued_count=0`이면 빈 datapack을 seal하지 않고 실패로 보존
- queued artifact가 ACK 전이면 `spread_sent`를 기다린 뒤 `confirm`
- ccache/oneDNN/Windows pattern warning이 단독 실패 원인이 아님을 기록

## 실제 실패 증거

E0-B.2 구현 전 실제 Laptop 실행에서 다음이 확인됐다.

- prepared MP4 SHA-256:
  `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
- model load: 통과
- Tailscale private HTTPS health/auth/presence: 통과
- datapack 및 scan session 생성: 통과
- Scanner candidate guidance와 한 번의 footer identity 진입: 확인
- footer 결과: `footer_identity_unavailable`, `valid_observations=1`
- artifact/V3-B queue/V4 upload: 0
- Server access log: scan session 이후 presence heartbeat만 존재
- source 종료 뒤 명시적 EOF feedback: 없음

이 증거는 E0-B.2 변경 동기를 고정하지만 변경 후 Laptop acceptance 성공 증거는 아니다. 최신 코드를
Laptop에 반영하고 동일 source로 다시 실행해야 한다.

## 검증 결과

### 집중 테스트

- Device config/adapter/Coordinator 집중: `41 passed`
- Book Scanner effective runtime config 집중: `7 passed`
- 합계: `48 passed`

검증한 핵심 조건:

- replay override 30000 적용
- 생략 시 1500 유지
- bool/0/음수/문자열/60000 초과 거부
- physical profile override 거부
- N=5/K/candidate config 변화 0
- source exhausted mapping과 detail 보존
- one-shot Coordinator feedback
- EOF에서 freeze/flush/seal 0
- artifact ACK 뒤에도 사용자 confirm 전 seal 0
- confirm 뒤 기존 cutoff seal 호출

### 전체 회귀

| 프로젝트 | 결과 |
|---|---:|
| Device Runtime | 96 passed |
| Book Scanner | 296 passed |
| Document Parser core | 573 passed, 4 skipped |
| Document Parser hardware bridge | 29 passed |
| Document Parser 합계 | 602 passed, 4 skipped |

첫 전체 회귀는 공용 `tmp` basetemp의 Windows permission error로 fixture setup이 실패했다. 제품 assertion
실패가 아니며 기존 지침대로 Device/Scanner는 package-local ASCII basetemp, Document Parser는 cache
plugin을 끈 기본 temp로 재실행해 위 결과가 통과했다.

## 남은 실제 Laptop acceptance

1. 최신 repository revision을 Laptop에 반영
2. 기존 `D:\ASL_OCR_E0B` config는 자동 갱신되지 않으므로 replay setup 재실행 또는
   `opaque_identity_max_collection_ms=30000` 확인
3. 같은 MP4/hash와 model bundle로 fresh datapack run
4. `spread_sent` 최소 1개 확인
5. `scan_input_exhausted` 1회와 queued/acked count 확인
6. `confirm` 뒤 flush/seal/finalize READY
7. `reading_snapshot`과 navigation response 확인
8. Server receipt/fragment 중복 0 확인

이 결과 전에는 E0-B.1 remote replay acceptance를 완료로 표시하지 않는다. 실제 camera, HC-05/STM,
speaker physical E0-B도 계속 대기다.

## 범위 준수

다음을 구현하지 않았다.

- candidate stable/motion/occlusion/clipping threshold 완화
- N=5 또는 K threshold 변경
- alternate/synthetic positive fixture 생성
- Server/V4/V3-B protocol/schema 변경
- EOF 자동 seal 또는 빈 datapack 성공 처리
- accepted identity bank persistence
- multi-writer/lease/quota/quarantine/GC hardening
- network service/ACL/credential 운영화
- actual physical hardware 완료 처리

따라서 이번 변경은 production Scanner 판정을 느슨하게 한 것이 아니라 replay host에서 기존 판정을
끝낼 수 있는 bounded 시간과 명시적 EOF 관측을 추가한 최소 교정이다.
