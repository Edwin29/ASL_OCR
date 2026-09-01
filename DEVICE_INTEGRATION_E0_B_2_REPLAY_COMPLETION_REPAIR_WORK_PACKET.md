# Device Integration E0-B.2 — Replay Completion Repair 작업 패킷

상태: **승인됨 / software implementation 및 회귀 완료 / 실제 Laptop 재검증 대기**
기준일: 2026-09-01
성격: **E0-B.1 실제 Laptop acceptance blocker 교정 패킷**
선행 조건: Device Integration E0-B.1 software implementation, Desktop Tailscale Serve 검증,
Laptop replay setup 및 remote scan-session 생성
후속 조건: E0-B.1 remote replay acceptance 완료 후 Device Integration E0-B physical acceptance

## 1. 배경

실제 Laptop에서 원본 `20260830_133526.mp4`와 동일한 SHA-256
`16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8` 영상을 사용해
E0-B.1 replay를 실행했다. 다음 경계는 정상 동작했다.

- Tailscale Serve private HTTPS health
- API key 인증과 device presence/heartbeat
- catalog 조회
- 새 datapack 생성 `201`
- scan session 생성 `201`
- UVDoc/Paddle model bundle load
- replay MP4 decode와 Scanner sampling

그러나 artifact와 V4 upload에는 도달하지 못했다. 로그에는 candidate guidance가 이어지다가 한 번
`footer_identity_unavailable`이 발생했고 `valid_observations=1`만 기록됐다. 당시 마지막 candidate
guidance와 footer timeout 사이의 실측 간격은 약 2.9초였다.

현재 M1 opaque footer identity 기본값은 다음과 같다.

```text
reference_bank_size = 5
query_sample_count = 5
max_collection_ms = 1500
```

Laptop CPU에서 첫 Paddle recognition 한 번이 collection wall-clock budget 1.5초보다 오래 걸리므로,
후보가 선택돼도 N=5를 모으기 전에 다음 poll에서 timeout된다. 이 결과는 page candidate가 전혀 없다는
뜻이 아니라 **선택된 candidate가 footer identity 단계에서 실행환경 시간 예산 때문에 폐기됐다**는
뜻이다.

또한 replay source 소진 시 Book Scanner는 `SOURCE_EXHAUSTED`를 발생시키지만 Device Runtime adapter가
이를 변환하지 않는다. Scanner engine은 IDLE이 되지만 Coordinator는 SCANNING 상태로 남아 presence
heartbeat만 계속하므로 사용자는 처리가 계속되는 것으로 오인한다.

이번 패킷은 위 두 실제 blocker만 교정한다.

## 2. 목표

E0-B.1의 기존 remote software acceptance 흐름을 다음과 같이 완료 가능하게 만든다.

```text
prepared MP4 replay
  -> existing candidate stable selection
  -> Laptop CPU에 맞는 bounded N=5 footer collection
  -> artifact ready
  -> existing V3-B durable queue
  -> existing V4/S1 valid receipt
  -> spread_sent
  -> explicit replay source exhausted feedback
  -> user confirm
  -> flush/seal/finalize READY
  -> Laptop reading_snapshot
```

핵심 목표:

1. replay profile에서만 opaque footer collection wall-clock budget을 명시적으로 설정할 수 있다.
2. N=5, `k_same=1`, `k_different=0`과 candidate hard gate는 변경하지 않는다.
3. replay EOF를 Device Runtime과 사용자에게 한 번, 명확하게 전달한다.
4. EOF를 자동 ACK, 자동 seal 또는 acceptance 성공으로 사용하지 않는다.
5. 실제 Laptop에서 artifact, V4 ACK, READY와 reading snapshot까지 다시 검증한다.

## 3. 관측된 실패와 판정

### 3.1 통과한 경계

Desktop Server access log에서 다음 요청이 확인됐다.

- `GET /api/v1/health` -> `200`
- presence session 생성 -> `201`
- datapack catalog 조회 -> `200`
- 새 datapack 생성 -> `201`
- scan session 생성 -> `201`
- 이후 bounded interval의 presence heartbeat -> `200`

따라서 Tailscale, HTTPS, API key, C0/S0와 Server process는 이번 실패의 원인이 아니다.

### 3.2 막힌 경계

Laptop feedback 순서는 다음과 같다.

```text
scan_started
  -> page_not_found/content_occluded/page_moving guidance
  -> candidate stable selection 진입
  -> footer_identity_unavailable(valid_observations=1)
  -> local retry
  -> 후속 candidate guidance
  -> source 소진 뒤 명시적 terminal feedback 없음
```

Server에는 spread bundle/fragments upload 요청과 receipt가 없었다. 따라서 V3-B/V4 실패가 아니라
V3-B queue 이전의 Scanner artifact 생성 실패다.

### 3.3 무관한 경고

다음 메시지는 이번 실패 원인이 아니다.

- Windows `정보: 제공된 패턴에 해당되는 파일을 찾지 못했습니다.`
- Paddle의 `No ccache found` warning
- Google logging 초기화 전 stderr warning
- oneDNN 정보 메시지

이번 패킷에서 이 경고를 제거하기 위한 dependency/toolchain 정리는 하지 않는다.

## 4. 포함 범위

### 4.1 Replay-only footer collection budget

E0-B replay app config의 `[scanner]`에 다음 명시적 값을 추가한다.

```toml
[scanner]
profile = "replay"
opaque_identity_max_collection_ms = 30000
```

계약:

- 값이 없으면 기존 Book Scanner 기본값 `1500ms`를 유지한다.
- override는 `profile = "replay"`에서만 허용한다.
- physical `pc_camera`와 `image_sequence`에 조용히 적용하지 않는다.
- `query_sample_count=5`, `reference_bank_size=5`, `k_same=1`, `k_different=0`은 그대로다.
- candidate의 `stable_sample_count=3`, motion, occlusion, clipping threshold는 그대로다.
- 값은 positive integer이며 구현에서 정한 단순 상한을 넘으면 config load를 거부한다.
- E0-B.1 example은 실측 2.9초 recognition과 N=5에 여유를 둔 `30000ms`를 사용한다.
- timeout 증가는 recognition 결과를 성공으로 간주하지 않는다. 유효한 5개 관측이 실제로 모여야
  `DIFFERENT` 또는 기존 reference와의 `SAME` 판정이 가능하다.

이 설정은 Laptop acceptance 실행시간을 위한 host/runtime 값이다. M1 identity 알고리즘의 새로운
production calibration이나 held-out 일반화 완료를 의미하지 않는다.

### 4.2 Source exhausted 전달 계약

Book Scanner의 기존 `VideoEventType.SOURCE_EXHAUSTED`를 Device Runtime에서 버리지 않고 명시적으로
전달한다.

최소 변경:

- Device Runtime `ScannerEventType`에 source exhausted 표현 추가
- `BookScannerRuntimeAdapter`에서 같은 scan session lineage로 정확히 한 번 mapping
- Coordinator가 `SCAN_INPUT_EXHAUSTED` 또는 동등한 semantic feedback을 한 번 발생
- JSONL feedback에 현재 queued/ACKed spread 수를 포함하되 secret/path/image bytes는 제외
- replay run 안내에 다음 사용자 행동을 명시

```text
artifact/`spread_sent`가 1개 이상이면 `confirm`으로 stop/flush/seal
artifact가 0개면 acceptance 실패이며 자동 seal하지 말고 종료/진단
```

EOF는 정상 source lifecycle event이며 그 자체로 Scanner fatal error가 아니다. 다만 acceptance
wrapper/report는 EOF 시 artifact 또는 ACK가 0이면 성공으로 판정하면 안 된다.

### 4.3 Replay 실행 관측성

JSONL에서 최소한 다음 순서를 판별할 수 있어야 한다.

```text
scan_started
footer identity collection/결정 또는 artifact ready
spread_sent(sequence)
scan_input_exhausted(queued_count, acked_count)
scan_stopping
finalizing
datapack_saved
reading_snapshot
```

기존 상세 candidate event 전체를 stdout에 추가해 로그를 폭증시키지 않는다. 현재 semantic guidance와
새 EOF feedback만으로 acceptance 진행 여부를 판단한다.

### 4.4 실제 Laptop 재검증

동일한 다음 authority로 재검증한다.

- 같은 prepared MP4 SHA-256
- 같은 model bundle manifest/hash
- 같은 Desktop Tailscale Serve origin
- 같은 API key file 계약
- 같은 `laptop-device-001` 또는 명시적으로 기록한 device ID
- fresh datapack/scan session

실행 결과는 secret-safe report 또는 구현 보고서에 다음을 기록한다.

- source SHA-256
- footer collection configured budget
- artifact 수와 sequence
- V4 receipt 존재 여부와 identity 일치
- source exhausted 관측 횟수
- READY revision
- reading snapshot 수신 여부
- 실패 시 마지막 성공 경계와 reason code

## 5. 제외 범위

이번 패킷에는 다음을 포함하지 않는다.

- global `stable_sample_count`를 3에서 2로 낮추기
- motion/occlusion/page mask/clipping threshold 완화
- opaque identity N=5를 줄이거나 `k_same`, `k_different` 변경
- footer token이 없는데도 artifact를 준비하는 bypass
- replay EOF 기반 자동 seal, 자동 READY 또는 자동 acceptance 성공
- alternate image sequence나 합성 positive clip 자동 생성
- Scanner V3-A identity 알고리즘 재설계 또는 held-out calibration
- M1 accepted identity bank restart persistence
- V3-B multi-writer, lease, quota, GC와 outbox 운영 hardening
- Server V4/S1 API, DB schema, ACK 또는 fragment idempotency 변경
- Tailscale ACL, service, auth-key rotation과 network hardening
- 실제 camera, HC-05/STM, 점자 셀과 speaker physical 검증
- ccache 설치나 Paddle/oneDNN warning 정리
- exhaustive CPU/latency matrix

명시적 replay timeout 하나로 실패가 해소되지 않으면 위 gate를 조용히 완화하지 않는다. source의
positive-window/fixture 적합성 문제로 분리해 보고하고 별도 승인을 받는다.

## 6. 불변식

이번 변경 뒤에도 다음 순서와 안전성은 유지해야 한다.

```text
valid candidate + valid N=5 footer decision
  -> immutable artifact
  -> durable queue commit
  -> V4 upload
  -> receipt identity validation
  -> local ACK
  -> SPREAD_SENT
```

- health, heartbeat, EOF 또는 stdout 메시지를 upload ACK로 사용하지 않는다.
- ACK 전에 `SPREAD_SENT`를 출력하지 않는다.
- 같은 sequence/artifact/idempotency key의 재시도 계약을 바꾸지 않는다.
- duplicate fragment와 duplicate spread 방지 계약을 바꾸지 않는다.
- EOF 전후 pending artifact/delivery settlement를 폐기하지 않는다.
- user `confirm`만 scan stop/flush/seal intent다.
- timeout 증가가 false footer match 또는 missing observation 수락으로 이어지지 않는다.
- physical profile의 기존 latency/timeout authority는 변경하지 않는다.

## 7. 상태 전이 계약

### 7.1 Artifact가 있는 EOF

```text
SCANNING
  -> ARTIFACT_READY
  -> QUEUED/SENDING/ACKED
  -> SPREAD_SENT
  -> SOURCE_EXHAUSTED
  -> SCAN_INPUT_EXHAUSTED feedback
  -> SCANNING 상태에서 사용자 stop intent 대기
  -> confirm
  -> FLUSHING_UPLOADS
  -> FINALIZING_DATAPACK
  -> READING
```

EOF가 먼저 관측되고 delivery가 아직 pending이면 Coordinator는 기존 delivery poll을 계속하며 사용자
confirm 이후에도 cutoff까지 flush한다.

### 7.2 Artifact가 없는 EOF

```text
SCANNING
  -> SOURCE_EXHAUSTED
  -> SCAN_INPUT_EXHAUSTED(queued=0, acked=0)
  -> acceptance 실패로 명시
```

이 경우 빈 datapack을 성공 acceptance로 seal하지 않는다. 자동 재생 반복도 하지 않는다. 사용자는
프로세스를 종료하고 마지막 Scanner reason을 근거로 진단한다.

### 7.3 Event 중복

- Book Scanner가 같은 EOF event를 재노출하더라도 Device event ID dedup 또는 adapter lifecycle로
  사용자 feedback은 한 번만 나타난다.
- EOF 뒤 poll은 추가 frame read나 반복 guidance를 만들지 않는다.
- EOF는 existing fatal/recoverable server recovery 상태를 덮어쓰지 않는다.

## 8. 구현 단계

### Phase 0 — 실제 실패 증거 동결

- Laptop 로그에서 `valid_observations=1`과 약 2.9초 first recognition 경계 기록
- Server access log에서 scan session 이후 upload 요청 0 확인
- source MP4 SHA-256과 model manifest 유지
- 현재 global Scanner/V3-B/V4 계약 diff 0 확인

### Phase 1 — Replay-only config plumbing

- `ScannerHostConfig`에 optional replay-only collection budget 추가
- TOML known-key, type/range와 profile validation
- local composition을 통해 Book Scanner runtime config로 전달
- `LocalBookScannerEngineFactory`가 기존 `VideoScannerConfig`의 opaque timeout만 교체
- E0-B replay example/setup-generated config에 `30000ms` 기록
- physical example/config의 effective default가 계속 `1500ms`인지 테스트

### Phase 2 — EOF event bridge

- Device scanner event type 추가
- Book Scanner adapter mapping과 lineage 검증
- Coordinator semantic event/feedback 및 one-shot 처리
- artifact 0/1+, pending/ACKed count를 secret-safe details로 전달
- EOF에서 auto seal하지 않는 테스트

### Phase 3 — Wrapper와 문서

- replay run 시작 메시지에 EOF 이후 행동 추가
- Quickstart의 성공 trace와 실패 trace 구분
- `footer_identity_unavailable` 반복 시 timeout/gate 진단 안내
- ccache/oneDNN warning이 비차단임을 troubleshooting에 기록

### Phase 4 — 실제 Laptop remote acceptance

- setup-generated config에 새 budget 적용 확인
- 동일 MP4로 fresh run
- `spread_sent` 최소 1개 확인
- EOF 한 번 확인 후 `confirm`
- V4 receipt, S1 READY와 reading snapshot 확인
- navigation command response 확인

### Phase 5 — 회귀와 보고

- Device Runtime/Book Scanner/Document Parser 회귀
- E0-B.2 구현 보고서 작성
- E0-B.1 보고서와 PROJECT_HANDOFF의 실제 Laptop 상태 갱신
- 실제로 통과한 범위만 완료 처리

## 9. 테스트 행렬

### 9.1 Config

- replay override 생략 -> effective `1500ms`
- replay override `30000` -> effective opaque policy에 정확히 반영
- bool, 0, 음수, 문자열 -> load 거부
- 단순 상한 초과 -> load 거부
- `pc_camera`에서 override 지정 -> load 거부
- unknown scanner key 거부 유지
- physical E0-B example effective policy 변화 0
- N=5/k threshold/candidate threshold 변화 0

### 9.2 Footer collection

- 1.5초를 넘는 recognition latency fixture에서도 configured replay budget 안에서 5개 valid observation 수집
- missing observation은 trial로 세지 않음
- 5개 미만 timeout은 계속 `UNKNOWN`/local retry
- first same match의 기존 duplicate suppression 유지
- 5개 all-mismatch 뒤에만 first spread `DIFFERENT`
- timeout 뒤 artifact/ACK 오발생 0

### 9.3 EOF bridge

- Book Scanner `SOURCE_EXHAUSTED` -> Device source exhausted event 1개
- 다른 scan-session lineage -> 거부
- EOF가 guidance/fatal로 잘못 mapping되지 않음
- EOF 뒤 frame read와 반복 feedback 0
- EOF가 auto seal/finalize/ACK를 발생시키지 않음
- artifact 0 EOF가 acceptance 성공으로 기록되지 않음
- artifact ACK 뒤 EOF와 confirm은 기존 flush/seal 순서를 유지

### 9.4 Remote E2E

- Laptop remote health/auth/presence 정상
- exact source SHA-256 일치
- artifact 최소 1개
- ACK 전 `spread_sent` 0, valid V4 receipt 뒤 1
- Server left/right fragment 중복 0
- source exhausted feedback 정확히 1
- confirm 뒤 flush/seal/finalize READY
- `datapack_saved` 뒤 `reading_snapshot`
- console navigation response 수신
- API key/model bytes/image bytes 로그 노출 0

### 9.5 Regression 기준

구현 전 최신 기준선:

| 범위 | 기준 |
|---|---:|
| Book Scanner 전체 | 289 passed |
| Device Runtime + actual E0-Core integration | 83 passed, 3 skipped |
| Document Parser 전체 | 602 passed, 4 skipped |
| S0/S1/C0/V4/combined 집중 | 51 passed |

추가 테스트로 총수는 늘 수 있다. 기존 테스트 감소, 새 error 또는 설명되지 않은 skip이 있으면 완료로
처리하지 않는다.

## 10. 완료 기준

다음을 모두 만족해야 E0-B.2를 완료로 표시한다.

1. replay-only collection budget이 config에서 명시되고 physical profile 기본값을 바꾸지 않는다.
2. N=5와 candidate/duplicate/ACK 불변식이 유지된다.
3. 동일 prepared MP4에서 Laptop Scanner artifact가 최소 1개 생성된다.
4. artifact가 V3-B/V4/S1를 거쳐 valid receipt로 ACK된다.
5. ACK 전 `spread_sent`가 없고 ACK 뒤 정확한 sequence로 나타난다.
6. source exhausted가 Laptop JSONL에 정확히 한 번 나타난다.
7. EOF가 자동 seal 또는 빈 datapack 성공을 만들지 않는다.
8. 사용자 `confirm` 뒤 flush/seal/finalize가 READY에 도달한다.
9. Laptop이 Server-backed reading snapshot과 navigation response를 받는다.
10. Server에 duplicate spread/fragment가 없다.
11. 세 프로젝트 회귀가 최신 기준 이상으로 통과한다.
12. camera/STM/speaker physical acceptance를 완료했다고 주장하지 않는다.

## 11. 예상 변경 파일

주 대상:

- `device-runtime/src/asl_device/app_config.py`
- `device-runtime/src/asl_device/types.py`
- `device-runtime/src/asl_device/events.py`
- `device-runtime/src/asl_device/adapters/book_scanner_runtime.py`
- `device-runtime/src/asl_device/coordinator.py`
- `device-runtime/src/asl_device/local_composition.py`
- `book-scanner/src/book_scanner/video/runtime_composition.py`
- `device-runtime/device-app.e0b.replay.example.toml`
- `device-runtime/tests/unit/test_app_config.py`
- `device-runtime/tests/unit/test_book_scanner_runtime.py`
- `device-runtime/tests/unit/test_coordinator.py`
- `book-scanner/tests/unit/video/test_runtime_composition.py`
- `tools/windows/e0b-laptop-setup.ps1`
- `tools/windows/e0b-replay-run.bat`
- `LAPTOP_E0B_QUICKSTART.md`
- `device-runtime/docs/device-integration-e0b-laptop.md`
- `DEVICE_INTEGRATION_E0_B_2_IMPLEMENTATION_REPORT.md`
- `PROJECT_HANDOFF_20260831.md`

필요할 때만 최소 변경:

- `device-runtime/src/asl_device/application.py`
- `device-runtime/tests/unit/test_application.py`
- `device-runtime/tests/integration/test_e0_local_composition.py`
- `DEVICE_INTEGRATION_E0_B_1_IMPLEMENTATION_REPORT.md`

기본 범위가 아닌 파일:

- `document-parser/src/document_parser/server/v4_*`
- Server DB migration/schema
- V3-B delivery/outbox schema
- Scanner candidate/obstruction/page-number algorithm
- STM serial adapter와 firmware
- Tailscale Serve 설정

## 12. 승인 경계

승인 시 수행:

- replay-only footer collection budget config/plumbing
- source exhausted Device event와 one-shot feedback
- 관련 unit/integration 테스트
- replay example/setup/run/Quickstart 갱신
- 실제 Laptop 재실행을 위한 명령과 결과 판정 지원
- 실제 remote 결과 수신 후 구현 보고서/handoff 갱신

별도 승인 없이는 수행하지 않음:

- candidate/identity threshold 완화
- alternate replay fixture 생성
- Server/V4/V3-B protocol 변경
- production physical timeout 변경
- actual camera/STM/speaker 완료 처리
- 운영 hardening, service 설치 또는 network 정책 변경
- commit/push/PR

## 13. 중단 조건

다음이면 범위를 조용히 넓히지 않고 보고한다.

- `30000ms` budget에서도 valid observation이 5개 모이지 않음
- 후속 frame이 candidate hard gate에 걸려 opaque collection 자체가 취소됨
- 동일 source에서 stable candidate가 더 이상 재현되지 않음
- timeout override가 physical profile 전역 변경 없이는 적용 불가능함
- EOF 전달을 위해 auto seal/Server API 변경이 필요함
- V4 receipt identity 또는 duplicate suppression 회귀 발생
- API key, model/image bytes를 report에 넣어야만 진단 가능함
- 실제 Laptop run에서 새로운 hardware/network blocker가 나타남

이 경우 다음 문제를 분리한다.

```text
E0-B.2 runtime budget/EOF repair
  != Scanner positive fixture 적합성
  != M1 identity calibration
  != physical Laptop acceptance
  != network/operations hardening
```

## 14. 후속 순서

```text
E0-B.2 replay completion repair
  -> E0-B.1 actual Laptop remote software acceptance 완료
  -> E0-B physical acceptance(camera + HC-05/STM + speaker)
  -> 필요 시 Scanner fixture/calibration 별도 패킷
  -> Network/Raspberry Pi 운영 hardening
```

E0-B.2는 production Scanner 판정을 느슨하게 만드는 패킷이 아니다. 실제 Laptop CPU에서 기존 N=5
판정을 완료할 수 있는 bounded 시간과 replay 종료를 관측 가능한 상태로 만드는 최소 교정이다.
