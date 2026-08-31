# Scanner Video V3-A 구현 보고서

상태: **로컬 구현·결정론적 회귀 완료 / 실제 identity threshold·실영상 page-change 검증 미완료**
기준일: 2026-08-31

## 구현 결과

V2가 같은 source frame에서 atomic commit한 좌우 `seam-conservative + UVDoc bilinear` artifact를
spread 단위로 식별하고, 하나의 artifact만 전송 lifecycle을 소유하도록 V3-A를 구현했다.

- `video/identity.py`: manifest와 파일 hash 검증, DCT perceptual hash, 명암 projection, ORB
  보조 특징, 좌우 순서 보존 비교, bounded in-memory ledger
- `video/page_change.py`: ACK 이후 preview-only 변화 감시와 연속 안정 표본 hysteresis/latch
- `video/engine.py`: identity 생성, pending/accepted 중복 억제, ambiguous 보수 처리,
  delivery lifecycle, `WAITING_FOR_PAGE_CHANGE` 상태 실행
- `video/config.py`: `validated=false`인 identity/page-change 정책과 cache 상한
- `video/events.py`, `video/protocols.py`, `video/types.py`: 구조화 event와 결합 경계

핵심 불변식은 다음과 같다.

- 좌우 identity는 반드시 같은 committed V2 spread에서 생성한다.
- pending은 한 개뿐이며 `READY_FOR_SERVER_PREFLIGHT`, `UPLOADING`, `REMOTE_RETRY` 동안 새 후보를
  평가하거나 UVDoc artifact를 생성하지 않는다.
- delivery ACK만 pending을 accepted로 바꾸며, 다른 artifact의 늦은 ACK와 반복 ACK는 무시한다.
- reject 또는 ACK 전 cancel은 pending을 해제하지만 이미 accepted인 기록은 되돌리지 않는다.
- accepted duplicate는 새 `ARTIFACT_READY` 전송 요청을 만들지 않는다.
- ambiguous 비교는 duplicate 또는 new spread로 조용히 강제하지 않고 local retry로 돌린다.
- ACK 이후 대기 상태는 full-resolution V2 preparer/UVDoc을 호출하지 않는다.

## Identity 및 page-change 정책

identity algorithm version은 `page-identity-v3a-1`이다. corrected page를 고정 크기로 정규화한 뒤
서로 성격이 다른 DCT hash, 투영 특징, ORB 대응을 함께 비교한다. 파일 hash가 좌우 모두 같을 때만
exact duplicate이며, visual duplicate는 좌우 페이지 모두의 특징 합의를 요구한다. 한쪽만 같거나
증거가 엇갈리면 `AMBIGUOUS`다.

page-change 초기 정책은 750ms 간격의 preview 표본과 연속 3개 안정 변화다. motion, 손 가림,
페이지 미검출 등 retry reason이 있는 프레임은 안정 변화 증거에 포함하지 않는다. 변경이 확정되면
기존 candidate window를 비우고 `PAGE_CHANGED`를 한 번만 발행한다. 이 수치는 실제 사용성 및 Pi
검증 전의 provisional 값이다.

## 실제 p30 identity 평가

사용자가 동일 p30 촬영이라고 확인한 세 이미지의 V2 corrected spread를 positive로 사용했다.
세 pair의 결과는 다음과 같다.

| 비교 | 판정 | 좌/우 pHash 거리 | 좌/우 ORB match |
|---|---|---:|---:|
| 111919 ↔ 112000 | `VISUAL_DUPLICATE` | 18 / 14 | 0.299 / 0.206 |
| 111919 ↔ 112042 | `AMBIGUOUS` | 18 / 14 | 0.148 / 0.109 |
| 112000 ↔ 112042 | `AMBIGUOUS` | 24 / 14 | 0.169 / 0.094 |

따라서 현재 정책은 false duplicate를 만들지 않도록 두 pair를 보류했지만, 실제 same-page
duplicate recall을 충분히 확보했다고 볼 수 없다. MP4에서 만든 p30/p309 spread와 p316/p317
spread 비교는 `NEW_SPREAD`였으나, 이 비교에는 사용자가 확인한 identity ground truth label이
없으므로 different-page 정확도에 산입하지 않았다.

재현 산출물은
`experiment_outputs/scanner_video_v3a_identity_20260831/summary.json`에 있으며 상태는
`PROVISIONAL_THRESHOLD_NOT_VALIDATED`다.

```powershell
python tools/run_scanner_video_v3a_identity_evaluation.py `
  --same-ready-dir D:\Projects\OCR\tmp\v3a-p030-identity-artifacts\ready `
  --output experiment_outputs\scanner_video_v3a_identity_20260831\summary.json
```

`--diagnostic-ready-dir <ready-dir>`는 서로 다른 spread의 진단용 artifact가 준비된 경우에만
추가한다. label이 확인되지 않은 diagnostic pair는 정확도에 포함되지 않는다.

## 검증 결과

- Book Scanner 전체 unit test: **223 passed**, exit code 0
- Python `compileall`: 통과
- `git diff --check`: 통과
- pytest cache 경로 접근 권한 경고 1개: 테스트 결과에는 영향 없음
- identity 단위: exact, 합성 밝기/이동/JPEG 변화, 좌우 swap, 한쪽 일치 ambiguous,
  version mismatch, decode failure, bounded ledger 검증
- lifecycle 단위: pending 중 평가/준비 차단, stale/repeated confirm, reject, cancel/confirm 소유권,
  accepted duplicate 전송 억제 검증
- page-change 단위: 동일 페이지 대기, 연속 K 변화 후 1회 release, motion/obstruction 제외,
  단일 spike 제외 검증

PC에서 5개 artifact fingerprint에 걸린 총 시간은 858.665ms였고 개별 측정은
332.558/162.455/136.986/106.644/119.942ms였다. Python `tracemalloc` peak는 80,559,341 bytes다.
이는 process RSS나 Raspberry Pi 4 성능 근거가 아니다.

## 완료하지 않은 항목

- 실제 labeled different-page 집합을 이용한 false duplicate/threshold 고정
- 실제 MP4 page-turn 구간을 이용한 750ms, K=3 검증
- Raspberry Pi 4 latency, RSS, Picamera2/GPIO 검증
- durable SQLite ledger/outbox와 재부팅 후 중복 방지
- 실제 HTTP upload, lost-response 재시도, 서버 idempotency 및 parser 접수
- 실제 비프음/TTS 완료 피드백
- Integration V0 coordinator와의 concrete upload adapter

따라서 V3-A는 동일 process/session의 로컬 중복 억제와 page-change 상태기계 구현으로 한정해
완료했다. crash-safe 전송 또는 실영상 임곗값 검증까지 완료한 것으로 해석하지 않는다.
