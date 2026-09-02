# Device Integration E0-B.4-D — Desktop Loopback Acceptance Harness 작업 패킷

상태: **승인됨 / 구현·전체 회귀·prepared Desktop 실증 완료**
기준일: 2026-09-02
성격: **단일 Windows 호스트의 격리된 E0-B replay 소프트웨어 acceptance 자동화**
선행 조건: E0-B.3.3 ACK callback diagnostic forwarding, pinned `test1.mp4` 및 검증된 model bundle
후속 조건: E0-B.4-L 실제 Laptop/Tailscale 증거 closure, Physical E0-B acceptance

## 1. 배경과 우선순위

실제 Laptop replay에서 spread 2개와 Server 2/4/0은 확인됐지만, PowerShell transcript/encoding 및 수동
종료 시점 때문에 `datapack_saved`와 `reading_snapshot`을 포함한 완결 증거를 안정적으로 한 번에 보존하지
못했다. Laptop과 Desktop을 반복 이동하는 운영 방식은 재현성과 증거 완전성을 떨어뜨린다.

따라서 다음 순서로 진행한다.

| 순서 | 작업 | 이유 |
|---:|---|---|
| 1 | **Desktop loopback acceptance harness** | 같은 revision에서 Scanner→V4/S1→reading 전체 소프트웨어 경계를 자동 검증하고 증거 수집 결함을 제거 |
| 2 | **E0-B.4-L 실제 Laptop/Tailscale evidence closure** | loopback으로 안정화한 절차를 실제 원격 호스트 경계에서 최종 확인 |
| 3 | **Physical E0-B** | camera, STM/HC-05, speaker와 실제 장치 성능 확인 |

Loopback 결과를 Laptop 또는 Physical acceptance로 승격하지 않는다.

## 2. 목표

한 명령이 다음 작업을 순서대로 수행하고 단일 evidence bundle을 생성한다.

1. 실행별 고유 work/evidence 디렉터리 생성
2. 빈 loopback TCP port 선택
3. 신규 Server SQLite/state에서 E0-B Bench Server 시작 및 health 확인
4. 별도 Device config/outbox/artifact state 생성
5. 준비된 replay source report, MP4, model bundle 계약 검증
6. Device Runtime 시작과 JSON event 기반 console command 자동 입력
7. candidate 2개, spread sequence 1/2, EOF 2/2, ACK callback diagnostic 검증
8. scan seal, revision 1 save, reading 4페이지 순회와 역방향 이동 검증
9. Server SQLite에서 receipt 2, fragment 4, duplicate 0 증거 추출
10. schema v2 replay boundary report 생성 및 최종 `passed` 판정

## 3. 격리 모델

```text
Desktop host
  prepared root (read-only input)
    inputs/scanner-replay.mp4
    models/...
    reports/e0b-replay-input.json
    secrets/device-api-key.txt

  per-run work root (secret/state; evidence 외부)
    device config + copied API key
    device outbox/artifacts
    server SQLite/datapacks

  per-run evidence root (secret 없음)
    UTF-8 console/server log
    source report copy
    server summary/raw rows
    boundary report
    run manifest
```

- Bench Server는 `127.0.0.1`에만 bind한다.
- Device connectivity는 해당 실행에서만 `http://127.0.0.1:<port>`와
  `allow_insecure_http=true`를 사용한다.
- 기존 remote Laptop config/template의 HTTPS 정책은 완화하지 않는다.
- API key 값은 log, manifest, evidence JSON에 기록하지 않는다.
- prepared root의 MP4/model/source report는 수정하지 않는다.

## 4. 자동 제어 상태기계

고정 시간 sleep으로 명령을 보내지 않고 출력 JSON event를 authority로 사용한다.

```text
speak_catalog_title(kind=new_datapack)
  -> confirm

scan_started
  -> replay/ACK 진행 대기

scan_input_exhausted(queued_count=2, acked_count=2)
  + spread_sent sequence=[1,2]
  -> confirm

datapack_saved(revision=1)
reading_resumed
reading_snapshot(page 1-L)
  -> down
reading_snapshot(page 1-R)
  -> down
reading_snapshot(page 2-L)
  -> down
reading_snapshot(page 2-R)
  -> up
reading_snapshot(page 2-L)
  -> 완료
```

catalog에 existing entry가 나타나면 `down`으로 이동하되, 신규 Server state에서 existing datapack이
보이거나 bounded 탐색 한도를 초과하면 격리 실패로 중단한다. 각 단계는 전체 timeout과 무진행 timeout을
가진다.

## 5. 성공 조건

기존 replay boundary report의 모든 runtime/server check가 통과해야 한다.

- pinned source SHA-256 및 source status
- pinned replay source cadence `sample_interval_ms=100`
- explicit supported `identity_role`
- fresh `new_datapack` lineage
- candidate verification 정확히 2회, 각각 5/5 `different`
- `spread_sent` sequence `[1, 2]`
- EOF `{queued_count:2, acked_count:2}`
- 동일 datapack revision 1 save
- reading page position `1-L, 1-R, 2-L, 2-R`
- Server `{spread_receipts:2, fragments:4, duplicates:0}`

Harness는 추가로 다음을 요구한다.

- 각 `spread_sent` 뒤 동일 accepted spread ID의 explicit
  `identity_collection_started(identity_role=page_change)`가 정확히 한 번 존재
- 2-R에서 `up` 후 2-L snapshot으로 되돌아옴
- child process output이 UTF-8 JSONL로 보존됨
- 실행 manifest가 `environment=desktop_loopback`과 실제 git revision을 기록

## 6. 산출물

```text
e0b-loopback-<UTC timestamp>-<suffix>/
  e0b-replay-console.log
  e0b-server.log
  e0b-replay-input.json
  e0b-server-summary.json
  e0b-server-evidence.json
  e0b-replay-boundary.json
  e0b-loopback-run-manifest.json
```

Manifest와 boundary report에는 로컬 API key, Tailscale hostname/token, raw image/OCR token을 넣지 않는다.
실패해도 가능한 산출물과 work root를 남겨 재현 원인을 조사할 수 있게 한다.

## 7. 포함 범위

- stdlib 기반 orchestration/상태기계/SQLite evidence extractor
- Windows batch entry point
- loopback 전용 Device TOML 생성
- UTF-8 no-BOM log writer
- child process start/health/interrupt/timeout 정리
- controller/config/evidence 단위 테스트
- Laptop quickstart와 E0-B runbook에 증거 등급 및 실행법 추가
- 구현 보고서와 project handoff 상태 갱신

## 8. 제외 범위

- 기존 Laptop setup의 non-loopback HTTPS 검증 완화
- Tailscale Serve, Quick Tunnel 또는 WAN failure matrix
- 실제 camera, COM/STM, Bluetooth, Windows audio
- production OCR/TTS/braille 품질
- Scanner threshold/N/K/candidate 정책 변경
- Server REST/SQLite schema 변경
- Docker/Hyper-V/Windows Sandbox 이미지 제공

## 9. 실패 및 안전 경계

- prepared root가 불완전하거나 source hash가 다르면 child process 시작 전 실패
- 기존 Server port/state를 재사용하지 않고 실행별 신규 state 사용
- Server health가 같은 child instance에서 오지 않으면 실패
- EOF가 2/2가 아니거나 spread 순서가 다르면 seal command를 보내지 않음
- `datapack_saved` 전에 reading navigation을 보내지 않음
- timeout/실패 시 child process를 정리하되 evidence/work 디렉터리는 삭제하지 않음
- `Ctrl+C` 또는 harness interrupt 시 두 child를 정리하고 partial manifest를 기록

## 10. 검증 계획

1. controller event→command 전이와 오류 조건 단위 테스트
2. TOML 생성 시 loopback/격리 경로/secret 비노출 테스트
3. fixture SQLite의 2/4/0 추출 및 duplicate 검출 테스트
4. UTF-8 JSONL 저장/재읽기 테스트
5. Device Runtime 전체 suite
6. Document Parser Bench Server suite
7. prepared root가 현재 호스트에 있으면 실제 loopback acceptance 실행

실제 모델/MP4가 없는 CI 또는 개발 Desktop에서는 1~6을 구현 완료 조건으로 삼고, 7은 외부 입력이
준비된 호스트의 실행 증거로 남긴다.

## 11. 완료 정의

- 단위 및 관련 전체 회귀가 통과한다.
- 한 명령으로 partial 또는 complete evidence bundle이 항상 생성된다.
- prepared root가 있는 Desktop에서 최종 report `status=passed`를 재현할 수 있다.
- 결과가 Desktop loopback임을 문서·manifest에서 명확히 표시한다.
- 실제 Laptop/Tailscale 및 Physical E0-B가 별도 미완료 경계로 남는다.
