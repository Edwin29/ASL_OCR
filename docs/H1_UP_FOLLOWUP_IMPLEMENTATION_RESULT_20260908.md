# H1/UP follow-up local correction 결과 — 2026-09-08

상태: **UP diagnostic harness correction PASS / two local engine lifecycle corrections PASS / H1 liveness correction 미선정**

근거와 architecture 판정은 [H1 및 physical UP 독립 고비용 검토](H123_UP_AND_H1_HIGH_COST_REVIEW_20260908.md)에 있다.

## 적용한 변경

### 1. UP diagnostic harness

`docs/evidence/h23-1c-20260908/capture_physical_controls.ps1`은 이제 다음을 구분한다.

- `ports-open`: serial port가 열린 시점
- `ready`: 지정한 HELLO3 ordinal과 그 boot의 initial mode NAV가 ACK된 뒤 observation epoch가 열린 시점
- 전체 NAV packet 수와 observation epoch 뒤 required control/action의 unique V3 sequence 수
- handshake-mode packet과 required control을 모두 담지 못하는 total cap의 preflight rejection

PowerShell parser는 PASS했고 `2 HELLO + 3 UP` 요구에 total cap 4를 주면 serial open 전에 exit 1로 거부했다. 기존 zero-UP run을 성공으로 바꾸지는 않으며 다음 physical recheck의 수용 가능성만 회복한다.

### 2. Opaque SAME의 visual evidence epoch

`book-scanner/src/book_scanner/video/engine.py`의 opaque SAME branch가 이전 `_opaque_visual_page_changed`를 폐기하고 accepted baseline으로 visual gate를 다시 arm한다.

회복한 invariant는 SAME으로 확인된 frame 이전의 visual-change evidence가 후속 OCR 오인식과 결합해 `PAGE_CHANGED`를 만들지 않는다는 것이다. N/K/identity/duplicate threshold, 8초 값, event grammar, receipt ordering은 바꾸지 않았다.

### 3. Close 뒤 late preparation cleanup

Engine-owned preparation future에 completion callback을 등록했다. Engine close 뒤 같은 current future가 늦게 끝난 경우에만, lock 안에서 prepared staging 또는 failed job staging을 폐기하고 processing ownership을 비운다.

회복한 invariant는 uncommitted preparation 결과가 close 뒤 추가 poll 없이 정확히 한 번 폐기된다는 것이다. Future가 close 전에 끝난 경로, cancel된 future, committed artifact, 다른 future identity는 기존 owner path를 유지한다.

## Targeted verification

| 범위 | 결과 |
|---|---|
| Actual-engine H1 baseline replay before local corrections | exit 0, 모든 assertion PASS; slow exact N4 timeout 반복 및 stale-latch false PAGE_CHANGED 재현 |
| `test_engine.py` + `test_engine_v3a5.py` | 26 PASS |
| 전체 `book-scanner/tests/unit/video` | 209 PASS |
| `device-runtime/tests/unit/test_book_scanner_runtime.py` | 10 PASS |
| 전체 book-scanner | 349 PASS, 3 FAIL |

전체 suite의 3 FAIL은 `test_p030_reference.py`의 human-golden math span count 기대 30/29 대비 실제 15/14다. Camera engine 변경과 무관하고 기존 content P1 범위이므로 이번 packet에서 수정하지 않았다.

## 남은 경계

- H1 liveness: exact `28|29`가 2.05초마다 지속돼도 8초 경계마다 N4를 폐기하는 현행 mechanism은 남아 있다. First-valid clock만으로도 N5가 8.2초라 충분하지 않아 correction을 아직 선택하지 않았다.
- Synchronous footer OCR: cancel/input latency의 실제 상한과 worker ownership을 추가 측정해야 한다.
- Recognizer unused inference: output/diagnostic/exception equivalence와 실제 native timing을 먼저 측정한다.
- Physical UP: corrected harness를 배포한 다음에도 무응답이면 PA0 raw/IDR·MODER·PUPDR, LOW duration, poll heartbeat와 continuity를 측정한다.
- Physical CLEAR, CONFIRM, MODE: hardware team 정렬/수리 전 보류 상태를 유지한다.

H1 sequence 2/fresh READY와 physical acceptance가 없으므로 H4는 계속 BLOCKED다.

## Source identity

- `engine.py` SHA-256: `6ee44d42cae3456544e58c183c193f970b1467ef26a616feeb9ad6e563dfc380`
- `test_engine.py` SHA-256: `9c2be028a665185f94629a3685d0b575a4359d15c064754c179791a2c573fbd0`
- `test_engine_v3a5.py` SHA-256: `b1b43581368a85b24dc220a237857f1921a26bb575a6d48cc9f6ae6e9e6d6e74`

이번 follow-up packet의 product source modification count는 **1 file** (`engine.py`)이다. 전체 진행의 unique product source count는 기존 15 files 안에서 유지된다.
