# Device Integration E0-B.3.2 — Identity Role 및 Replay Report 계약 교정 작업 패킷

상태: **승인됨 / 구현 및 local 전체 회귀 완료 / E0-B.4 actual evidence closure 대기**
기준일: 2026-09-02
성격: **observer-only diagnostics 의미 교정 및 E0-B replay acceptance report 복구**
선행 조건: E0-B.3 diagnostics, E0-B.3.1 console idempotency namespace repair, 동일 prepared MP4의 실제 Laptop 성공 로그
후속 조건: E0-B.4 actual evidence closure, physical E0-B acceptance, production OCR/TTS acceptance

## 1. 우선순위와 패킷 분할

현재 남은 작업은 한 번에 검증 가능한 크기와 외부 환경 의존성을 기준으로 다음과 같이 분리한다.

| 우선순위 | 패킷 | 한 번에 수행 가능한 이유 | 외부 의존성 |
|---:|---|---|---|
| 1 | **E0-B.3.2 identity role/report 계약 교정** | Book Scanner event, Device feedback, report, unit regression과 문서 정정을 한 저장소에서 함께 검증 가능 | 없음 |
| 2 | **E0-B.4 actual evidence closure** | 교정된 report로 Laptop transcript, source report, Server summary를 결합해 최종 acceptance 산출물 생성 | Laptop/Desktop 보존 로그와 Server state 필요 |
| 3 | **Physical E0-B hardware acceptance** | camera mode, 실제 COM port, STM, beep/speech를 물리 장비 기준으로 재검증 | camera와 HC-05/STM 필요 |
| 4 | **Production content acceptance** | deterministic bench parser를 제외하고 실제 OCR, reading content, braille/audio 품질 평가 | 실제 production model/runtime과 품질 기준 필요 |
| 5 | **Short-dwell/calibration 정책 검토** | 실제 recall 요구가 확정된 경우에만 candidate evidence 재사용이나 threshold를 비교 | 제품 정책과 추가 라벨 영상 필요 |

1순위와 2순위를 합치지 않는다. 1순위는 저장소 안에서 결정론적으로 완료할 수 있지만, 2순위는 실제
Laptop transcript와 Desktop Server summary가 없으면 최종 `passed`를 만들 수 없다. 3~5순위 역시 물리
장비, production 품질 기준 또는 제품 정책을 요구하므로 이 패킷의 완료를 막지 않는다.

## 2. 배경과 교정 근거

고정 prepared MP4는 다음 source authority를 사용한다.

```text
SHA-256: 16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8
resolution: 3840 x 2160
fps: 59.69965076707844
frame count: 2677
duration: 44.84113333333334s
replay sample_interval_ms: 100
```

E0-B.3.1 적용 뒤 fresh datapack으로 수집한 실제 Laptop 로그는 다음을 확인했다.

```text
datapack_id = datapack-ee8c7c014211465c9fdff0dd7839b6eb

candidate video-00000092 / spread-000001
  -> candidate identity valid 5/5
  -> decision different
  -> spread_sent sequence 1

page-change identity observations without candidate spread lineage
  -> repeated same early decisions
  -> video-00000310 ... video-00000314 valid 5/5
  -> decision different
  -> candidate search resumes

candidate video-00000365 / spread-000002
  -> candidate identity valid 5/5
  -> decision different
  -> spread_sent sequence 2

scan_input_exhausted queued_count=2, acked_count=2
user confirm
  -> scan_stopping through_sequence=2
  -> finalizing
  -> datapack_saved revision=1
  -> reading_resumed
  -> four unique page IDs: spread 1 L/R, spread 2 L/R
```

이 로그는 기존 E0-B.3의 다음 원인 가설을 지지하지 않는다.

- 314/315가 `candidate identity 4/5 + content_occluded abort`였다는 가설
- 318/다음 장 시작이 `candidate identity 1/5 + source_exhausted abort`였다는 가설
- 위 두 abort가 exact-video acceptance의 필수 증거라는 report 계약

실제 로그에서 `video-00000314`는 책 페이지 314가 아니며 원본 MP4 frame 314도 아니다. replay source가
runtime에 제공한 순차 `source_frame_id`다. 또한 `candidate_selected`/`spread_id` lineage 없이 나타난
identity observation과 decision은 새 artifact 후보 검증이 아니라 accepted reference를 기준으로 한
`WAITING_FOR_PAGE_CHANGE` 감시다.

현재 Book Scanner는 동일 opaque collector/event family를 두 용도로 사용한다.

```text
role = candidate_verification
  stable candidate
    -> 최근 accepted identity와 비교
    -> SAME: duplicate suppression
    -> DIFFERENT 5/5: artifact processing 허용

role = page_change
  accepted/uploaded spread 뒤 대기
    -> SAME: 아직 같은 펼침면, 계속 대기
    -> DIFFERENT 5/5: 페이지 변경 확인, candidate search 재개
```

두 역할의 로그 이름이 같고 role 필드가 없기 때문에, E0-B.3 report와 문서가 page-change observation을
candidate lifecycle 증거로 오인했다. 이 패킷은 그 관측 계약을 교정한다. Scanner 선택 결과와 opaque
identity 판정 정책 자체는 변경하지 않는다.

## 3. 목표

1. 모든 opaque identity lifecycle diagnostic에 `identity_role`을 명시한다.
2. candidate verification과 page-change monitoring을 report에서 별도 timeline으로 집계한다.
3. 실제 성공 로그에 존재하지 않는 4/5 및 1/5 abort 필수 조건을 제거한다.
4. exact prepared MP4의 runtime acceptance를 실제 관찰값에 맞게 고정한다.
5. 기존 E0-B.3 문서의 검증되지 않은 페이지별 인과 주장을 철회하고 증거 수준을 명시한다.
6. diagnostics 변경이 Scanner state, artifact, queue, ACK 또는 capture threshold를 바꾸지 않음을 회귀로
   고정한다.

## 4. 포함 범위

### 4.1 Explicit identity role

Book Scanner semantic event의 bounded details에 다음 enum 값을 사용한다.

```text
identity_role = candidate_verification | page_change
```

적용 대상:

- `opaque_identity_collection_started`
- `opaque_identity_observed`
- `opaque_identity_decided`
- `opaque_identity_aborted`

규칙:

- `VERIFYING_IDENTITY`에서 생성된 lifecycle은 `candidate_verification`이다.
- `WAITING_FOR_PAGE_CHANGE`에서 생성된 lifecycle은 `page_change`다.
- role은 engine state에서 명시적으로 정하고 `spread_id` 유무만으로 추론하지 않는다.
- candidate lifecycle에는 candidate `spread_id` lineage를 유지한다.
- page-change lifecycle에는 가능한 경우 accepted reference의 bounded ID 또는 sequence lineage를 제공한다.
  기존 public protocol/schema 확장이 필요하면 role만 필수로 하고 reference lineage는 report limitation으로
  남길 수 있다.
- raw footer token, token digest, image/ROI bytes, API key와 absolute model path를 Device JSONL에 추가하지
  않는다.
- diagnostic sink 실패가 Scanner state transition을 바꾸지 않는다.

Device Runtime은 role을 삭제하거나 재추론하지 않고 bounded feedback에 그대로 전달한다.

예시:

```json
{"code":"identity_collection_progress","details":{"identity_role":"candidate_verification","spread_id":"...","valid_observations":5,"query_sample_count":5}}
{"code":"identity_collection_decided","details":{"identity_role":"page_change","decision":"same","valid_observations":1,"query_sample_count":5}}
```

### 4.2 Report schema 및 성공 계약 교정

`replay_boundary_report`는 identity event를 다음 두 collection으로 분리한다.

```text
candidate_attempts[]
page_change_checks[]
```

candidate attempt는 최소한 다음 lineage를 가진다.

- candidate source frame ID
- spread ID
- required observation count
- maximum valid observation count
- terminal decision 또는 abort
- 해당 spread의 `spread_sent` sequence 연결 가능 여부

page-change check는 최소한 다음을 가진다.

- role
- source frame range 또는 terminal source frame ID
- maximum valid observation count
- terminal decision/timeout
- candidate artifact attempt로 계수되지 않았다는 명시

schema version은 기존 consumer와의 혼동을 피하도록 증가시킨다. 구 schema 입력을 조용히 새 의미로
해석하지 않는다. 필요한 경우 legacy log에는 `identity_role_missing` limitation을 반환하되, 실제 role을
추측해 exact acceptance를 통과시키지 않는다.

### 4.3 Exact-video acceptance checks

새 runtime 필수 조건은 다음과 같다.

```text
source SHA-256/status = exact expected/passed
candidate_selected count = 2
candidate spread IDs = two distinct non-empty values
candidate terminal decisions = [different 5/5, different 5/5]
spread_sent sequences = [1, 2]
scan_input_exhausted = queued_count 2, acked_count 2
datapack_saved = revision 1
reading_resumed = same fresh datapack
unique reading page IDs = 4, ordered as spread 1 L/R and spread 2 L/R lineage
```

Server summary가 제공되면 다음도 필수다.

```text
spread_receipts = 2
fragments = 4
duplicates = 0
```

Server summary가 없으면 source/runtime checks가 모두 통과해도 `provisional`이다. malformed 또는 명시적으로
불일치하는 Server summary가 제공되면 `failed`다.

다음은 더 이상 필수 성공 조건이 아니다.

- `identity_collection_aborted(content_occluded, 4/5)` 존재
- `identity_collection_aborted(source_exhausted, 1/5)` 존재
- 314/315 또는 318이라는 책 페이지 의미를 runtime `source_frame_id`에서 추론
- candidate attempt가 정확히 4개라는 가정

page-change SAME 조기 결정은 `k_same=1` 계약에 따른 정상 관찰이다. DIFFERENT는 필요한 valid mismatch
수를 채울 때까지 진행될 수 있다. page-change decision은 artifact count나 candidate recall로 집계하지
않는다.

### 4.4 문서 정정

다음을 현재 실제 증거에 맞게 갱신한다.

- E0-B Laptop 문서
- Laptop Quickstart
- E0-B.3 verification report
- project handoff의 E0-B 상태
- 기존 E0-B.3 작업 패킷에는 역사적 승인 내용은 보존하되, 상단에 **E0-B.3.2에 의해 원인 가설과
  report 조건이 대체됨**을 명시한다.

문서는 다음 세 층의 증거를 분리한다.

1. offline candidate audit와 사람이 확인한 영상 구간
2. runtime candidate/page-change identity lifecycle
3. Server receipt/fragment/duplicate persistence

한 층의 ID나 관찰을 다른 층의 페이지 번호 또는 인과 증거로 승격하지 않는다.

## 5. 명시적 제외 범위

- candidate stable count, sample window, sample interval 또는 identity N/K 변경
- stable-window frame을 candidate identity evidence로 재사용
- EOF frame 반복, padding 또는 synthetic observation
- motion/occlusion/geometry/seam/clipping threshold 완화
- 314/315 또는 318을 추가 capture하도록 Scanner 동작 변경
- Book Scanner artifact, V3-B outbox, V4/S1 또는 Server DB schema 변경
- 새 Laptop replay 실행과 실제 Server summary 수집
- 실제 OCR/parser, 실제 TTS, 점자 변환 품질 변경
- physical camera mode, COM port, STM/HC-05, speaker 구성 변경
- 운영 service, network, retry/quota/lease hardening

## 6. 유지해야 할 불변식

```text
candidate stable
  -> role=candidate_verification identity
  -> SAME: duplicate suppression/page-change wait
  -> DIFFERENT: immutable artifact processing
  -> durable queue
  -> valid Server ACK
  -> spread_sent
  -> role=page_change identity
  -> DIFFERENT: candidate search resumes
```

- candidate verification과 page-change monitoring의 decision 의미를 바꾸지 않는다.
- valid observation count가 정책 기준 미만이면 candidate DIFFERENT/artifact를 만들지 않는다.
- page-change DIFFERENT는 artifact가 아니라 search 재개 authority다.
- ACK 전에 `spread_sent`를 출력하지 않는다.
- EOF는 자동 finalize authority가 아니며 user `confirm`만 stop/seal intent다.
- report는 누락된 evidence를 추측으로 채우지 않는다.
- observer diagnostics는 Scanner 결과와 timing authority가 아니다.

## 7. 구현 단계

### Phase 0 — 실제 증거 동결

- 제공된 full Laptop log의 핵심 lineage를 regression fixture로 최소화한다.
- secret, raw token, absolute external path와 불필요한 반복 guidance는 fixture에서 제거한다.
- 두 candidate attempt, page-change SAME/DIFFERENT, 두 spread, EOF, save, reading 4페이지를 보존한다.

### Phase 1 — Book Scanner role semantics

- engine의 두 opaque collector call path에 explicit role을 전달한다.
- started/observed/decided/aborted event detail에 role을 포함한다.
- event serialization round-trip과 bounded scalar 검증을 추가한다.
- role 추가 전후 artifact/state 결과가 동일함을 회귀로 확인한다.

### Phase 2 — Device mapping

- `BookScannerRuntimeAdapter`가 role을 bounded feedback으로 전달한다.
- role missing/unknown을 candidate 또는 page-change로 임의 추론하지 않는다.
- raw token/digest가 Device feedback에 노출되지 않음을 유지한다.

### Phase 3 — Report v2

- candidate attempts와 page-change checks를 분리 집계한다.
- 실제 성공 계약으로 checks를 교체한다.
- save/read evidence와 unique page count를 추가한다.
- Server summary absent/malformed/mismatch 상태를 각각 provisional/failed로 검증한다.
- legacy/missing-role 로그는 명시적 limitation 또는 failure로 처리한다.

### Phase 4 — 문서 및 전체 회귀

- 잘못된 314/315 4/5, 318 1/5 필수 주장을 정정한다.
- exact prepared MP4의 정상 기대값을 두 candidate/two spread로 기록한다.
- Book Scanner와 Device Runtime 전체 테스트를 실행한다.
- Document Parser는 코드 비변경이면 관련 Server/report contract smoke test만 수행하고, public diff가 있으면
  전체 회귀로 확대한다.

## 8. 테스트 행렬

### 8.1 Role semantics

- candidate collector started/observed/decided -> `candidate_verification`
- candidate hard reject/EOF abort -> `candidate_verification`
- page-change observed/decided/timeout -> `page_change`
- page-change SAME 1/5 -> 대기 유지, artifact 0
- page-change DIFFERENT 5/5 -> search 재개, artifact 0
- role diagnostics on/off 또는 sink failure -> artifact/state 결과 동일

### 8.2 Device feedback boundary

- role, bounded frame/spread/count/decision만 노출
- pair digest, raw token, ROI/image, API key와 model path 노출 0
- candidate event의 spread lineage 보존
- page-change event를 candidate attempt로 승격하지 않음
- unknown/missing role을 조용히 오분류하지 않음

### 8.3 Report v2

- 실제 최소 fixture: candidate 2, 각각 DIFFERENT 5/5, spread `[1,2]`, EOF 2/2, save/read 4 -> runtime passed
- 동일 fixture + Server 2/4/0 -> final passed
- Server summary 없음 -> provisional
- malformed/mismatch Server summary -> failed
- candidate terminal이 SAME, UNKNOWN, 4/5 또는 lineage missing -> failed
- page-change SAME/DIFFERENT 수 변화 -> candidate count에 영향 없음
- 4/5 hard-reject와 1/5 EOF abort가 없어도 성공 가능
- source SHA mismatch -> failed
- duplicate spread sequence 또는 reading page 부족 -> failed
- unrecognized/raw fields가 report에 복사되지 않음

### 8.4 기존 동작 회귀

- pinned video 기대 전송 수 2 유지
- candidate/identity threshold diff 0
- artifact/queue/ACK ordering diff 0
- console process namespace repair 유지
- EOF 뒤 user confirm finalize 계약 유지

## 9. 완료 기준

1. identity diagnostic마다 역할이 명시되고 두 collector path가 구분된다.
2. candidate와 page-change identity가 report에서 별도 collection으로 나타난다.
3. 실제 Laptop 성공 로그의 두 candidate가 각각 5/5 DIFFERENT로 집계된다.
4. page-change `video-00000310`~`314` DIFFERENT는 candidate/artifact attempt로 집계되지 않는다.
5. `spread_sent [1,2]`, EOF 2/2, save revision 1, reading 4페이지가 runtime acceptance에 포함된다.
6. 4/5 content-occluded 및 1/5 source-exhausted abort 필수 check가 제거된다.
7. Server summary absent는 provisional, exact 2/4/0은 passed, 불일치는 failed다.
8. Scanner decision/threshold/artifact 수와 delivery ordering은 변경되지 않는다.
9. raw identity evidence와 secret이 Device log/report에 노출되지 않는다.
10. 관련 unit/integration 및 Book Scanner/Device Runtime 전체 회귀가 통과한다.
11. E0-B.3 문서의 반증된 원인 가설에 명시적인 대체/정정 표기가 있다.
12. 실제 Laptop 재실행이나 physical/OCR 품질 승인을 이 패킷 완료로 오인하지 않는다.

## 10. 예상 변경 파일

주 대상:

- `book-scanner/src/book_scanner/video/engine.py`
- `book-scanner/src/book_scanner/video/events.py` 또는 role value를 둘 최소 domain 위치
- `book-scanner/tests/unit/video/test_engine_v3a5.py`
- `book-scanner/tests/unit/video/test_events.py`
- `device-runtime/src/asl_device/adapters/book_scanner_runtime.py`
- `device-runtime/src/asl_device/replay_boundary_report.py`
- `device-runtime/tests/unit/test_book_scanner_runtime.py`
- `device-runtime/tests/unit/test_replay_boundary_report.py`
- `device-runtime/docs/device-integration-e0b-laptop.md`
- `LAPTOP_E0B_QUICKSTART.md`
- `DEVICE_INTEGRATION_E0_B_3_REPLAY_BOUNDARY_VERIFICATION_WORK_PACKET.md`
- `DEVICE_INTEGRATION_E0_B_3_VERIFICATION_REPORT.md`
- `PROJECT_HANDOFF_20260831.md`

필요할 때만 변경:

- `device-runtime/src/asl_device/events.py`
- `tools/windows/e0b_replay_boundary_report.py`
- `tools/windows/e0b-replay-run.bat`

기본 범위 밖:

- Scanner config/threshold 파일
- replay camera/source adapter
- Device delivery/outbox schema
- Document Parser V4/S1/DB schema
- STM serial adapter와 firmware
- Tailscale Serve 설정

## 11. 승인 경계

승인 시 수행:

- observer-only identity role 추가
- Device bounded feedback mapping
- report v2와 실제 로그 기반 regression fixture
- 반증된 E0-B.3 문서/보고서 정정
- 관련 전체 회귀와 구현 보고서 작성

별도 승인 없이는 수행하지 않음:

- Laptop/Desktop에서 새 replay 또는 Server evidence 수집
- Scanner recall/threshold/policy 변경
- physical camera/STM/audio 작업
- actual OCR/TTS/braille 품질 작업
- commit, push 또는 PR

## 12. 중단 조건

다음이면 범위를 조용히 넓히지 않고 보고한다.

- role을 추가하려면 identity/token public wire schema나 persisted DB migration이 필요함
- observer detail 추가가 Scanner timing/state/artifact 결과를 바꿈
- 실제 최소 fixture에서 후보가 2개가 아니거나 두 candidate의 terminal 5/5 DIFFERENT를 재현할 수 없음
- save/read evidence가 JSONL만으로 datapack lineage를 안전하게 연결할 수 없음
- page-change collector와 candidate collector를 engine state로 명확히 구분할 수 없음
- Server 2/4/0을 report에 넣기 위해 Server protocol 변경이 필요함
- raw token/image/secret 기록 없이는 report를 만들 수 없음

중단 시 실제 확인된 범위까지만 report하고 Scanner 정책 변경, Server schema 변경 또는 새 Laptop 실행을
자동으로 선택하지 않는다.

## 13. 후속 순서

```text
E0-B.3.2 identity role/report contract correction
  -> E0-B.4 actual Laptop + Server evidence closure
  -> physical E0-B camera + HC-05/STM + speaker acceptance
  -> production OCR/TTS/braille content acceptance
  -> 필요성이 입증된 경우에만 short-dwell/calibration policy
```

이 패킷의 목적은 더 많은 페이지를 전송시키는 것이 아니다. 이미 성공한 두 후보와 전송 후 페이지 변경
감시를 로그와 report에서 정확히 분리하여, 성공 실행이 잘못된 필수 abort 조건 때문에 실패로 판정되는
진단 계약 결함을 제거하는 것이다.
