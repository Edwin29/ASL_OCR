# Device Integration E0-B.4-D 구현 보고서

작성일: 2026-09-02
작업 패킷: `docs/work-packets/DEVICE_INTEGRATION_E0_B_4_D_DESKTOP_LOOPBACK_ACCEPTANCE_HARNESS_WORK_PACKET.md`
상태: **구현·local 전체 회귀·prepared Desktop loopback 실증 완료**

## 결과

단일 Windows Desktop에서 E0-B Bench Server와 replay Device Runtime을 실행별로 격리하고, JSON event를
기준으로 전체 software acceptance를 자동 수행하는 하네스를 추가했다.

```bat
tools\windows\e0b-desktop-loopback-acceptance.bat D:\ASL_OCR_E0B
```

Harness는 new datapack 선택, spread `[1,2]`, explicit ACK page-change start, EOF 2/2, seal, revision 1 save,
reading 4페이지 순회와 마지막 역방향 이동을 자동 제어한다. 결과는 UTF-8 no-BOM log, Server raw/2/4/0
evidence, schema v2 boundary report와 `environment=desktop_loopback` manifest로 보존한다.

## 구현 내용

- 실행별 고유 loopback port와 Server SQLite/state
- Device config/outbox/artifact와 Server state 분리
- prepared MP4/model/source report를 수정하지 않는 절대경로 config
- pinned replay의 검증 cadence `sample_interval_ms=100`
- remote Laptop template의 HTTPS 정책을 변경하지 않는 loopback 전용 connectivity
- event-driven command state machine; 고정 sleep 기반 입력 없음
- `spread_sent` 직후 동일 spread의 explicit page-change start 강제
- EOF가 `[1,2]` 및 2/2가 아니면 seal 금지
- save/read 전 snapshot 거부, 1-L→1-R→2-L→2-R→2-L 순서 검증
- Server SQLite의 spread/fragment/upload raw row와 2/4/0 summary 추출
- ready/accepted/status와 upload `attempt_count=1` 추가 검증
- work/evidence 경로 중첩 거부로 API key evidence 유입 차단
- child output UTF-8 강제 및 console evidence UTF-8 no-BOM 기록
- timeout/실패/interrupt child process 정리와 partial evidence 보존
- `.venv-e0b`가 없는 Desktop에서는 repository `document-parser\.venv`를 안전하게 재사용

전체 Device 회귀에서 E0-B.3.3 이전에 작성된 response-loss 통합 테스트 double이 ACK callback event의
필수 `session_id`/`event_id`를 누락한 사실도 발견했다. 제품 lineage 검증을 완화하지 않고 test double을
실제 Scanner event 계약에 맞게 수정했다.

## 검증

| 범위 | 결과 |
|---|---:|
| E0-B.4-D controller/config/SQLite/UTF-8 unit | 8 passed |
| Device Runtime 전체 | 120 passed |
| Book Scanner 전체, ASCII temp | 299 passed |
| Document Parser 전체 | 602 passed, 4 skipped |
| Bench Server 집중 | 2 passed |

Book Scanner의 최초 전체 실행은 Windows 한글 사용자명이 깨진 pytest temp 경로에서 OpenCV image write가
실패해 293 passed, 6 failed였다. 동일 revision을 ASCII temp에서 재실행해 299 passed를 확인했다. 제품
assertion 실패가 아니다.

## 실제 Desktop 실행

Google Drive `Ocr_scan`의 개발 원본 `20260830_133526.mp4`와 검증된 model bundle로
`D:\ASL_OCR_E0B`를 구성한 뒤 하네스를 실제 호출했다.

```bat
tools\windows\e0b-desktop-loopback-acceptance.bat D:\ASL_OCR_E0B
```

최초 harness/template의 replay source cadence가 `500ms`여서 실제 Laptop 성공 구성의 `100ms`와 달랐고,
고정 영상의 성공 candidate frame 92/365를 건너뛰어 EOF 0/0이 재현됐다. Scanner threshold/N/K는 바꾸지
않고 replay 전용 source cadence를 검증값 100ms로 정정했다. Git metadata capture도 UTF-8로 고정해 한글
Windows user path에서 CP949 reader traceback이 발생하지 않게 했다.

최종 실행은 `scan-70c5387a20d64fc4b3c45dd950d376c1`에서 통과했다.

- spread sequence `[1,2]`
- ACK callback page-change start 2개, accepted spread ID 일치
- Server `{spread_receipts:2, fragments:4, duplicates:0}`
- datapack revision 1 save
- reading snapshot page index `[0,1,2,3,2]`
- manifest/boundary `status=passed`
- evidence: `tmp/e0b-loopback-runs/e0b-loopback-20260902T060639Z-f6a05794/evidence`

## 증거 등급

E0-B.4-D 성공은 Scanner→V3-B→loopback V4/S1→READY→reading 소프트웨어 통합을 입증한다. 다음은
입증하지 않는다.

- 실제 Laptop host와 그 성능/설치 상태
- Laptop↔Tailscale↔Desktop network boundary
- camera, STM/HC-05, speaker
- production OCR/TTS/braille content 품질

실제 원격 증거는 E0-B.4-L, 물리 장치 증거는 Physical E0-B에서 별도로 닫는다.
