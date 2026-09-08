# H1 해결 및 미검증 physical controls 시험 목표·완료 조건

작성일: 2026-09-08  
상태: **계획 수립 / 실행 전 / H1 미해결 / H4 BLOCKED**

이번 지시는 코드 수정 금지다. 본 문서만 작성하며 product, firmware, harness, test code, config를 수정하거나 배포·flash·실험을 실행하지 않는다. 아래 조건은 후속 실행의 판정 기준이다. 원인 조사 완료와 문제 해결 완료를 구분한다.

## 1. 근거와 출발 상태

| 근거 | 현재 주장 가능한 사실 | 남은 공백 |
|---|---|---|
| [Fresh H1 기록](H1_CAMERA_FRESH_RUN_20260908.md) | 첫 spread 26/27의 durable receipt 확보. 후속 page-change에서 SAME/UNKNOWN timeout 반복 | 두 번째 spread 28/29, 두 번째 receipt, finalize/fresh READY 미완료 |
| [독립 H1/UP 검토](H123_UP_AND_H1_HIGH_COST_REVIEW_20260908.md) | 실제 engine replay에서 exact 28/29가 2.05초 간격이어도 8초마다 N4가 폐기돼 무진전. valid5/no-majority UNKNOWN은 정상 가능 | 원 run의 raw pair/reference bank가 없어 모든 SAME·UNKNOWN을 timeout 하나로 설명할 수 없음 |
| [후속 수정 결과](H1_UP_FOLLOWUP_IMPLEMENTATION_RESULT_20260908.md) | stale visual latch와 late preparation cleanup targeted PASS | H1 liveness 수정은 미선정. 이 결과만으로 Laptop 배포·fresh H1 PASS를 주장할 수 없음 |
| [Firmware/physical 상태](H2_H3_FIRMWARE_SERIAL_PHYSICAL_STATUS_20260908.md) | USART1 RX normal/stress 및 aligned firmware evidence 보유. 과거 UP 성공, 현재 UP 3회 무패킷 | UP 원인은 미확정. CONFIRM→PAGE PREVIOUS 오인입력, MODE solder, physical CLEAR 미해결 |

보고된 전체 Scanner suite는 349 PASS/3 FAIL이다. P030 math-span golden 3 FAIL은 별도 content 항목으로 추적한다. 본 계획에서는 baseline 비교 없이 변경과 무관함을 새로 확정하거나 전체 suite PASS로 표기하지 않는다. 기존 waiver가 실제 실패와 일치하는지도 확인한다.

## 2. 목표와 우선순위

아래 P는 **작업 순서**이며 기존 defect severity의 상향이 아니다. H1과 controls는 독립 분기로 진행할 수 있다.

| 순서 / 목표 | 완료 조건 | 미충족 시 처리 |
|---|---|---|
| P0 / G0 증거의 실행 identity 확정 | Laptop interpreter와 세 package `__file__`, source/config hash, 실제 launcher/override, firmware image, boot/session, 최초 state를 run manifest에 연결 | identity가 다른 과거 PASS를 승계하지 않고 해당 acceptance 대기 |
| P1-A / H1 원인·해결 후보 결정 | timeout N4 폐기, valid5 UNKNOWN, SAME 각각의 원인과 evidence 공백을 분리. 해결 후보가 유지할 invariant·변경 상한·regression·rollback 명시 | 계측 없이는 구분 불가하면 diagnostic/design packet으로 종료. 무근거 수정 금지 |
| P1-B / UP 재검증 | 유효한 관측 구간에서 SHORT 3/3, 각 `UP STEP → NAV,U,S → ACK` 연결. 이후 production action 검증 | 첫 누락 경계를 지정하고 측정으로 전환. 무응답 반복만으로 배선/코드 결론 금지 |
| P2 / 기타 controls 검증 | 버튼별 packet 및 production 동작 표를 채움. 수리 의존 항목은 BLOCKED로 명시 | 독립 버튼 시험은 계속. CONFIRM/MODE 수리 전 강제 우회 금지 |
| P3 / H1 해결 수용 | 아래 fresh H1 조건을 전부 충족하고 별도 bounded page-change 반복으로 재현성 확인 | 실패 checkpoint 기록, dependent step SKIP. H1 PASS 금지 |
| P4 / H2·H3·H4 재진입 | 최종 identity regression 및 각 gate 충족 | 물리 CLEAR/정렬/controls blocker가 남으면 full H2/H3/H4 보류 |

현재 코드 금지 범위에서 달성할 수 있는 것은 G0, 원인/설계 판단 및 변경 없이 가능한 시험의 증거 확보다. 해결에 코드·harness 변경이 필요하면 별도 승인용 packet을 제출하며 이번 지시로 구현하지 않는다.

## 3. 공통 실행·증거 gate

- [공통 manifest](DEMO_RUN_COMMON_MANIFEST_20260908.md)를 양식으로 쓰되 당시 상태를 현재 사실로 복사하지 않는다. Laptop은 C:만 사용하고 기존 source/state/evidence를 보존한다. 새 run directory를 사용한다.
- Source는 commit뿐 아니라 working-tree hash로 구별한다. Desktop 최신 engine 수정과 Laptop 실행 identity의 일치를 확인하기 전에는 수정 후 live 재시험이라고 부르지 않는다.
- UTC/monotonic, operator 조작 시각, camera frame/attempt/reference epoch, boot/protocol/sequence, command, cursor/generation을 연결한다. 관측되지 않은 값은 추정으로 채우지 않는다.
- 비밀번호/API credential은 기록하지 않는다. Android strict source, 해당 profile의 TLS 정책, native 입력 해상도와 runtime wrapper를 유지한다. 640/1920 진단을 production 4000 입력과 동등하게 취급하지 않는다.
- N=5, Ksame=1, Kdifferent=0, identity/duplicate threshold와 production 8000ms를 유지한다. FRAME/V3, baud, UART 구조, pin/PCA mapping, servo LUT/각도도 변경하지 않는다.
- 사람의 관측은 번호가 붙은 일괄 안내와 영상/시각 표시로 수집한다. 다음 관측은 사용자의 준비 응답 후 시작한다. 빠른 시간 내 필기나 50ms 화면 판독을 요구하지 않는다.

### Controls harness 유효성 보완 조건

`docs/evidence/h23-1c-20260908/capture_physical_controls.ps1`의 기존 교정은 parser 및 invalid-cap preflight까지만 검증됐다. Source 재검토상 후속 HELLO3에서 observation-ready/sequence 집합이 완전히 새 epoch로 초기화되지 않으며, ready는 host ACK write 뒤 열린다. 목표 개수 도달 즉시 종료하므로 release 이후 관측도 자동 보장되지 않는다.

코드 변경 없이 시험할 때는 **한 trial에 하나의 안정된 handshake epoch**를 사용한다. 실제 STM 측 ACK 수신까지 확인하고 시작하며, 중간 reconnect/reset이면 그 trial을 INVALID로 남긴 뒤 새 directory에서 재개한다. Retry는 `(boot epoch, sequence)`로 구별하고 새 누름 횟수로 세지 않는다. Packet cap은 boot·repeat·retry와 종료 후 관측을 담아야 하며, cap 종료를 PASS로 해석하지 않는다. 기존 설정으로 충분한 release 후 tail을 확보할 수 없다면 해당 시험은 실행 전 BLOCKED다.

Direct serial harness의 `FRAME=0`은 boot 때 PCA 초기화/clear가 없다는 뜻이 아니다. Servo 보류 중에는 hardware team이 확인한 전원 분리 등 안전 조건 없이 board reset/boot를 실행하지 않는다. 실행 전 실제 packet, 예상 동작, stop condition, evidence root를 따로 안내한다.

## 4. H1 진단 및 해결 완료 조건

### H1-D: 원인·설계 판단 완료

1. 보존된 native timing replay, slow exact pair, SAME, N5 conflicting pairs, missing/hard reject, deadline 전후를 분리한다. 과거 결함 재현 script의 assertion은 수정 전 identity용이므로 현재 source에서 실패했다고 곧바로 regression으로 판정하지 않는다.
2. 새 live 진단이 필요하면 accepted bank identity와 attempt별 normalized raw pair/status, sample 시작·종료·deadline, visual epoch를 확보한다. 기존 관측 기능으로 확보 불가능하면 누락 필드와 최소 계측 packet부터 제시한다. 이번 단계에서 계측 코드를 작성하지 않는다.
3. acquisition 대기, candidate gating, footer localization/inference, collector reset, application poll/input 대기의 시간을 분리한다. 사용자 cancel 도착→dispatch→scanner stop의 실제 지연도 기록한다.
4. First-valid clock만의 변경은 2.05초×4간격=8.2초 문제를 닫지 못한다. Recognizer 조기 종료 후보는 output/exception/diagnostic 동등성과 native timing 증거 없이 해결책으로 선정하지 않는다.
5. 후보는 이전 spread의 evidence 혼입 방지, finite timeout/cancel, SAME 이후 visual epoch 폐기, duplicate 방지, close 뒤 late result 미게시를 모두 보존해야 한다. Worker/collector 구조 변경이 필요하면 파일 상한·migration·호환성·rollback·H1–H4 재검증 비용을 먼저 제시한다.

이 다섯 항목이 채워져야 **진단·설계 완료**다. 이것은 H1 해결 PASS가 아니다.

### H1-A: Fresh H1 실제 해결 수용

진입 조건은 실행할 source/config identity가 명확하고, 필요한 수정이 있다면 별도 승인·적용 및 targeted/subsystem 검증이 완료된 상태다.

| Checkpoint | PASS에 필요한 증거 |
|---|---|
| Capture 시작 | Production `python -m asl_device`, console controls 우회 명시, strict Android camera, 새 datapack, 실제 catalog/system cue 청취 |
| Spread 1 | 26/27 same-frame L/R artifact, sequence 1의 durable V4 receipt/outbox ACK 및 그 이후의 `spread_sent`; 실제 안내 청취 |
| Page change | 28/29로 바꾼 operator 시각부터 frame/identity를 연결. 실제 28/29에 근거한 PAGE_CHANGED; 손/동일 페이지/오인식만으로 false capture 없음 |
| Spread 2 | 28/29 same-frame L/R, 독립 sequence 2 receipt, 두 spread 총 네 page fragment의 연결. 불필요한 duplicate receipt 없음 |
| Finalize | 두 durable receipt 후 CONFIRM LONG. S1 처리 완료와 fresh READY revision의 연결; `datapack_saved(revision)`를 receipt와 구분 |
| Reading | 해당 fresh revision을 S0에서 선택하고 26→27→28→29에 해당하는 네 page의 artifact/page identity와 focus 확인. authenticated audio 실제 청취 |
| Exit/state | 정상 종료와 supervisor 상태가 일치하고 재진입 시 승인된 stable device ID의 cursor/state 복구. Fatal은 성공 종료로 위장되지 않음 |

시연용 **제안 목표**는 손을 치우고 28/29를 고정한 operator marker부터 PAGE_CHANGED까지 30초 이내다. 이것은 새 운영 목표이며 production 8초 설정 변경이나 기존 acceptance의 대체가 아니다. Candidate reject가 발생한 시간도 숨기지 않고 함께 보고한다. 첫 시도 관측은 최대 60초로 제한하고, 30초 초과는 지연 목표 FAIL, 60초 무진전은 해당 checkpoint FAIL로 기록한다. 이후 상태를 보존하며 후속 독립 시험으로 진행한다.

Fresh H1 전체 1회 PASS와 같은 identity에서의 page-change targeted 반복 1회 PASS를 재현성 목표로 둔다. 실패 시 원인 구분에 도움이 되는 변경된 관측 조건이 있을 때만 bounded 재시도 최대 1회를 수행한다. 부분 datapack finalize가 별도 진단에 필요하면 목적을 먼저 제안하며 두-spread H1 PASS로 세지 않는다.

## 5. 버튼별 목표와 시험 표

Source 계약: `hardware/stm32/kitel2026final/Core/Src/main.c`의 button handlers/main poll, `device-runtime/src/asl_device/application.py`의 input drain/hold-repeat. 모든 버튼을 DOWN과 같은 A/R 방식으로 기대하지 않는다.

제안 조작은 SHORT 200–300ms를 2초 간격으로 3회, HOLD는 1.2–1.5초다. 실제 시간은 영상으로 확인한다. Release 후 최소 2초의 tail을 확보해 새 반복과 같은 sequence 재전송을 구별한다. 이 수치는 사용자 시험 조작이며 debounce/repeat 값을 변경하지 않는다.

| 입력 / pin | 현재 증거 상태 | Serial 수준 완료 조건 | Production 수준 완료 조건 |
|---|---|---|---|
| UP / PA0 | 과거 성공, 현재 3회 무패킷 | SHORT 3/3 `UP STEP`, `NAV,U,S`, 대응 ACK. HOLD에서는 firmware SHORT 반복, release 뒤 새 반복 중단 | 이전 item이 실제 존재하는 S0 위치에서 이전 item 이동. 시작 경계 안내도 별도 확인 |
| DOWN / PA1 | 과거 V3 성공; 현 identity 대조군 | SHORT/HOLD마다 V3 `D,A`와 `D,R` 쌍, 각각 ACK. V2 `D,S`로 대체 불가 | Host hold-repeat 진행, release 후 반복 중단. 최종 focus/audio generation 일치 |
| LEFT / PA4 | 입력 evidence 있음, catalog action만으로 부족 | `L,S` 3/3 및 hold-repeat/release 종료 | 실제 이전 math window가 있는 위치에서 offset/window 변경. 경계에서는 유지+정상 안내 |
| RIGHT / PB0 | 입력 evidence 있음, catalog action만으로 부족 | `R,S` 3/3 및 hold-repeat/release 종료 | 10-cell 초과로 다음 window가 존재하는 수식에서 offset/window 변경. offset 0 유지가 항상 오류는 아님 |
| PAGE NEXT / PB1 | 과거 `N,S` 후 NOACK 존재; 완전 무패킷으로 일반화 불가 | `N,S` 3/3과 STM의 ACK 수신; 재전송/재연결 여부 분리 | 다음 page가 있는 위치에서 page_id/page_index 이동, 끝 경계 안내 |
| PAGE PREVIOUS / PC0 | 과거 packet 성공; CONFIRM 오인입력의 대조군 | `P,S` 3/3과 ACK; 인접 버튼에서 잘못 발생하지 않음 | 이전 page가 있는 위치에서 이동, 첫 page 경계 안내 |
| CONFIRM / PC1 | 실제 누름이 PAGE PREVIOUS로 관측됨 | 수리/label·회로 확인 후 SHORT 3/3 `C,S`, LONG 3/3 `C,L`, 모두 release 때 한 번. `P,S` 오발생 0 | SHORT catalog 선택/현재 상태의 계약 동작, LONG은 준비된 capture datapack finalize. 미완성 상태에 반복 finalize하지 않음 |
| MODE / PC2 | solder blocker | 수리 후 왕복 3회, capture `V,A`/reading `V,R` 및 ACK, bounce 중복 없음 | 양방향 mode 전환, pending hold 취소, capture/reading lifecycle과 재진입 cursor 보존 |

ACK는 packet 수락 evidence다. 실제 action 완료는 S0 snapshot/state에서, audio는 playback event와 사람 청취에서 확인한다. 이 controls 시험에서는 physical braille 정확성 PASS를 주장하지 않는다.

### UP 실패 시 분기

1. 같은 handshake epoch에서 DOWN 대조군 1회 → UP SHORT 3회 → DOWN 대조군 1회로 시작한다.
2. DOWN까지 없으면 준비/연결/관측 환경부터 INVALID 여부를 판단한다. UP 배선 원인으로 승격하지 않는다.
3. DOWN은 통과하고 UP debug가 없으면 PA0 idle/pressed/released level, 유효 LOW 지속시간, IDR/MODER/PUPDR와 main-loop 생존 여부를 측정 대상으로 정한다. 접근할 수 없으면 `insufficient_evidence`로 남긴다. SWD halt 측정은 timing acceptance와 분리한다.
4. `UP STEP`은 있으나 NAV가 없으면 firmware enqueue/transport, NAV는 있으나 ACK가 없으면 host/serial, ACK는 있으나 action이 없으면 production routing/state를 조사한다.
5. Shorts가 통과하면 HOLD 1회와 release tail, 이어 production 이전 item 동작으로 진행한다. 원인 미확정 상태에서 pin swap, 과거 firmware flash 또는 debounce 변경으로 PASS를 만들지 않는다.

## 6. 실행 순서·실패 처리·전체 종료

1. G0 및 harness gate를 먼저 확인한다.
2. H1 원인·설계와 UP 시험을 독립 진행한다. 이어 LEFT/RIGHT/PAGE NEXT/PAGE PREVIOUS 및 DOWN 대조를 묶어 안내한다.
3. CONFIRM/MODE는 hardware team 수리·확인 뒤 재개한다. 단일-dot orientation, servo 0..7 calibration, PCA role 수정, physical CLEAR 반복은 기존 보류를 유지한다.
4. 필요한 변경은 승인 packet으로 분리한다. 승인·반영 뒤 targeted → affected subsystem → 최종 identity G3-A → fresh H1 순으로 검증한다. 변경 없는 T-close/Host bound/audio-only/RX stress는 새 trigger 없이 반복하지 않는다.
5. Controls의 production routing/audio는 servo를 분리한 조건에서 독립 검증 가능하지만 full H3라 부르지 않는다. 정렬·physical CLEAR 수용 뒤 fresh H2 → 모든 controls 포함 fresh H3 → H4로 진행한다.

각 trial은 `PASS / FAIL / INVALID / BLOCKED / SKIP` 중 하나와 근거를 갖는다. 원인 분류는 기존 `confirmed_product_defect`, `probable_product_risk`, `test_harness_artifact`, `environment_failure`, `hardware_or_wiring`, `insufficient_evidence`, `expected_behavior` 체계를 유지한다. 버튼 한 개의 FAIL은 나머지 독립 시험을 중단하는 이유가 아니다. Serial 환경 상실·예기치 않은 움직임 등은 영향받는 분기만 중단하고 기록한다.

**이번 계획의 실행 완료**는 모든 목표에 근거 있는 결과 또는 blocker·다음 action·재개 조건이 채워진 상태다. **H1 해결 완료**는 H1-A 전부 PASS, **controls 수용 완료**는 8개 입력의 serial 및 production 조건 전부 PASS다. 세 완료는 서로 대체하지 않는다. 최종 H4는 실제 live capture부터 physical cells까지 한 run에서 검증해야 하며 현재 계속 BLOCKED다.

이번 작업 변경: **문서 1개 / product source 0 / firmware 0 / harness·test code 0 / 실행한 시험 0**.
