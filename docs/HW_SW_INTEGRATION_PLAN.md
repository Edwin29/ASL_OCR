# HW/SW Integration Plan

작성일: 2026-09-05 · 계획 기준: `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e`

이 문서는 후속 실행 절차다. 이번 세션은 문서 작성까지만 수행했다. 현재 Entry Gate는 미충족이며 상세 판정·P0/P1/Deferred·수정 예산은 [Prototype Stabilization Gate](PROTOTYPE_STABILIZATION_GATE.md)를 따른다.

## 1. 순서와 공통 진단 원칙

**0 안정화·baseline → 1 원격 software/replay → 2 live camera+console → 3 STM 입력+서버 읽기 → 4 점자 actuator → 5 전체 live capture/read → 6 bounded recovery·시연 수용 → 7 필요 시 Pi 이식** 순서다. 앞 단계의 정상 경계를 고정한 채 새 장치/경계를 하나씩 추가한다.

- Desktop은 실제 PaddleOCR-VL/Piper와 영속 S0/V4/S1을 실행한다. Laptop은 Scanner, Coordinator, outbox, 입력, WAV 다운로드/재생을 실행한다.
- 카메라는 준비한 PC/UVC 한 profile을 먼저 사용한다. Android IP snapshot은 대안이며 초기 합격에 두 방식을 모두 요구하지 않는다.
- 공식 runtime은 `python -m asl_device --config <toml>`다. legacy STM bridge, bench server, `RasberryPITest`를 제품 runtime 대신 사용하지 않는다.
- **가장 먼저 실패한 boundary**에서 진단한다. 마지막 TTS 무음만 보고 OCR·카메라·시리얼을 동시에 바꾸지 않는다. 한 번에 한 조건만 바꾸고 원본 실패 run을 보존한다.
- 입력 ACK, bundle durable ACK, revision READY, WAV 검증, speaker 청취, actuator 동작은 별개다. 아래의 성공 조건을 다른 계층의 녹색으로 대체하지 않는다.
- 속도는 실제 관측으로 평가한다. DOWN 650/180ms는 Host scheduling 계약이며 느린 서버에서도 180ms마다 cursor commit을 보장하는 성능 SLA가 아니다. 물리 release→Host edge 관측 시간과 Host 관측→마지막 in-flight 완료를 따로 기록한다.
- 모든 새 문제는 Gate 문서의 분류 절차를 거친다. 실패를 발견한 자리에서 제품 코드를 즉석 수정하거나 설정 임계값을 계속 풀지 않는다.

## 2. Evidence bundle과 기준 실행

각 단계마다 고유 `run_id`로 Device JSONL/transcript, Server summary/log, 설정 요약, preflight, 필요한 serial/debug log 및 영상/수동 판정을 연결한다. 기존 tools가 제공하지 않는 타임스탬프/펌웨어 정보는 외부 serial logger 또는 수동 기록으로 보완할 수 있다. 해당 계측이 없는 시험은 계측 항목을 합격으로 표시하지 않는다.

필수 manifest 필드:

| 범주 | 기록 |
|---|---|
| 실행 | 날짜, 담당자, 단계, run ID, source commit/dirty 여부, 양 host의 interpreter 및 dependency 버전 |
| 입력 | 교재/페이지, replay SHA-256 또는 live camera selector/backend/index/실효 해상도/FPS/FourCC/회전/crop, model hash, effective identity collection budget |
| 상태 | stable device ID, process boot ID, scan ID, datapack ID, revision, through_sequence, firmware source/build/flash hash, negotiated serial version |
| lineage | source frame→spread→artifact/hash→outbox key/attempt→V4 receipt→S1 fragment side/page ID→published revision→reading session/command ID→focus/generation→FRAME/audio_ref digest |
| 판정 | 각 필수 check의 passed/failed/not_run/blocked, preflight 검사 revision 수와 오류 수, 수동 청취/점자 결과, 첫 실패 B-ID, workaround/분류 |

API key/비밀번호 원문은 기록하지 않는다. audio_ref는 필요 시 digest로 연결한다. `playback_requested`, `FRAME sent`, `assets_loaded`, health 200만으로 실제 동작을 합격 처리하지 않는다.

최소 정상 실행은 **서로 다른 펼침면 2개(4페이지)**, 기존 READY에 append 1 spread, 읽기 항목/쪽/수식 span/표 셀/10-cell window, 같은 stable device ID 재진입이다. 물리 표 페이지가 준비되지 않으면 표 navigation은 preflight된 fixture로 단계 3~4에서 확인하고 live OCR 표 정확도는 완료 범위에서 분리해 적는다.

고정 replay 기대는 input hash `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`, 2 receipt/4 fragments/0 duplicates다. 다른 영상에 같은 개수를 강제하지 않는다. live 입력은 촬영한 펼침면 목록과 최종 page side/order를 직접 대조한다.

## 3. 단계 0 — bounded stabilization과 실행 준비

**사전조건:** Gate 문서의 S-01/S-02/S-03만 후속 수정/준비 대상으로 고정한다. 이번 감사의 제품 코드 무변경 원칙과 후속 구현 세션을 구분한다.

**절차 및 evidence:**

1. S-01/S-02를 예산 안에서 교정하고 실제 STM adapter/S0Store 및 Scanner adapter/outbox 경계를 포함하는 회귀를 실행한다. Gate 문서의 기존 404개는 참고 기준이며 발견한 두 결함용 회귀를 대신하지 않는다.
2. 사용될 코드·모델·TOML·state root를 고정한다. host별 profile을 명시하고 `viewport_size=10`, STM `cell_count=10`을 확인한다. `device_id`를 테스트를 통과시키려고 매번 바꾸지 않는다.
3. 현재 코드/실제 OCR/Piper로 fresh demo 세트를 한 번 생성해 preflight 및 핵심 내용 확인을 수행한다. archive `datapack-660f28f931054859b1bccd1c8d48df5e`는 현재 audio mapping 오류 3개가 있으므로 합격 데이터로 재사용하지 않는다.
4. 운영/시연 데이터를 보존한 별도 시험 state를 사용한다. rollback 기준은 서버를 정지한 상태의 DB+datapacks+jobs 묶음, Device outbox DB+아직 ACK 전인 artifact 묶음 및 설정/hash다. 서로 다른 시점의 DB와 파일을 조합하지 않는다.
5. G0~G4의 evidence를 묶는다. STM build는 가능한 장비에서 authoritative 소스를 빌드해 log/hash를 보존하고 단계 3 진입 전 G5를 닫는다.

**성공:** Stabilization Exit Gate 통과. 코드 budget 2건 및 데이터 세트 1개 외의 수정이 섞이지 않음.

**실패 진단 순서:** import/cwd/interpreter → 실패 assertion의 실제 B-ID → concrete adapter/서버 영속 상태 → 선정 데이터 preflight → 실제 모델/runtime. namespace collection error를 제품 결함으로 수정하지 않는다.

**Stop/rollback:** unresolved P0/P1 또는 budget 초과 시 affected 단계 진입 보류. 이전 evidence/baseline 보존. dataset 직접 편집, receipt 삭제, silent partial publish로 gate를 통과시키지 않는다.

## 4. 단계 1 — 원격 server/device와 replay 기준선

대상: B00, B02, B04~B09, B11. 카메라/STM의 물리 변수를 추가하기 전에 두 컴퓨터의 실제 네트워크·경로·모델 경계를 확인한다.

**사전조건:** G0~G4 및 fixed MP4/model 준비. Desktop/Laptop 동일 source revision. Desktop production 서버와 Laptop console/replay profile. 실제 API key가 일치하고 outbox/state는 준비된 쓰기 가능한 저장소다.

**절차:**

1. [Conditional runbook](LAPTOP_CONDITIONAL_E0B_RUNBOOK.md)의 Desktop production server/Tailscale 절차로 시작한다. `tools/windows/e0b-start-production-server.bat`의 기본 포트는 8421이다. 다른 설정은 manifest에 기록한다.
2. Desktop loopback health → Laptop에서 같은 private HTTPS origin의 health → 인증 catalog/system cue → C0 handshake/presence 순서로 확인한다. host identity는 C0/서버 로그로 대조한다. endpoint만 같고 다른 서버 인스턴스를 보고 있지 않은지 확인한다.
3. `e0b-replay-setup.bat`/`e0b-replay-run.bat` 및 [E0-B.3 verification](../DEVICE_INTEGRATION_E0_B_3_VERIFICATION_REPORT.md)의 role-aware report 절차를 사용한다. 최신 모드 계약상 저장 후 capture catalog로 돌아간 뒤 reading 모드에서 다시 선택한다.
4. candidate verification 두 건의 N=5/different → artifact/outbox → `spread_sent` 1,2 → EOF queued/acked 2/2를 관측한다. EOF는 자동 저장이 아니다. CONFIRM LONG 뒤 cutoff=2, flush, seal, READY를 확인한다.
5. 같은 revision의 4페이지를 읽고 audio 다운로드/auth/session 격리 및 10-cell snapshot을 확인한다. 서버 receipt 재시도 횟수는 1 초과일 수 있으며 최종 duplicate 0과 lineage로 판단한다.
6. 새 Device 앱 실행에서 같은 버튼 순서로 새 작업을 시작해 S-01 해결을 확인한다. reading 재진입에서는 stable device ID를 유지해 커서 복구를 확인한다.

**필수 evidence/성공:** actual Laptop/Server logs + report `passed`, receipts/fragments/duplicates=2/4/0, 모든 through N의 durable ACK, fresh READY revision, page order/identity, 같은 generation의 audio/braille. G3/G4를 이미 동일한 두-host full-model 실행으로 확보했다면 그 evidence를 재사용할 수 있다. Desktop loopback만으로 remote 통과를 대신하지 않는다.

**실패 진단:** origin/health → auth/C0 → operation IDs → candidate 역할·유효 관측 수 → artifact hash/outbox status → V4 receipt → fragment status → seal/finalize → reading/audio. `candidate_verification`과 `page_change`를 합산해 N=5를 채우지 않는다.

**Stop/rollback:** wrong server/book/page identity, false ACK/READY, duplicate spread, 기존 revision 변조가 관측되면 stop. 전송 불명확 상태는 artifact를 다시 촬영하기 전에 outbox/receipt를 조회한다. 서버를 reset하여 중복 증거를 없애지 않는다.

## 5. 단계 2 — live camera + console + 실제 Piper

대상: B03~B09. STM과 actuator는 아직 추가하지 않는다.

**사전조건:** 단계 1 통과, 선정 교재/받침/조명/거리 고정, 사용할 카메라 profile 한 개 및 model bundle 준비. GUI preview를 쓰면 지원되는 OpenCV GUI 환경이어야 한다.

구도는 기존 합의대로 검은 배경 위 펼친 책 양면을 위에서 촬영한다. 마커 부착이나 다른 촬영 구도 일반화를 이번 통합 조건으로 추가하지 않는다.

**절차:**

1. `tools/windows/e0b-laptop-setup.bat -ConfigRoot <준비루트> -TestProfile webcam -OpaqueIdentityMaxCollectionMs 8000`으로 physical profile을 준비하고 `e0b-laptop-preflight.bat <준비루트> webcam`을 실행한다. 실제 TOML의 effective 값을 manifest에 남긴다.
2. `e0b-laptop-run.bat <준비루트> webcam`으로 새 datapack을 선택한다. preview source/backend와 실제 렌즈의 일치를 확인한다. 기본 Windows MSMF와 DShow의 index를 서로 같은 장치라고 추정하지 않는다.
3. 펼침면을 고정해 `candidate_selected`, valid observation 5, `different`, `spread_sent`를 관측한 뒤 페이지를 넘긴다. 한 번 손을 가려 local reject/안내 후 손을 치우고 정상 후보로 복귀하는 것을 확인한다.
4. 2개 spread가 ACK된 뒤 `confirm long` → `finalizing` → `datapack_saved` → capture catalog를 확인한다. 새 draft에서 `spread_sent=0`이면 종료를 성공 시험으로 세지 않는다.
5. `lever released` 또는 `e0b-laptop-read.bat <준비루트> webcam`으로 READY를 선택한다. `reading_snapshot`의 `source_text/spoken_text/braille_cells`와 현재 페이지 원문을 대조하고 실제 Piper 음성을 듣는다.

**성공:** 실제 입력 2 spread의 L/R가 같은 source lineage로 남고 page 수/순서가 일치, fresh published revision preflight error 0, 선정 핵심 본문/수식을 이해 가능한 음성으로 읽음. Scanner preview가 정상이어도 upload가 없으면 불합격이다.

**실패 진단:** 장치 선택/실효 해상도/회전 → 초점·노출·잘림/가림 → candidate 사유 → N=5 수집 시간과 processing_ms → seam/crop/UVDoc artifact → V4/S1. 원문이 틀리면 source image→corrected image→Page IR→focus item→spoken text를 순서대로 비교한다. Android 무선 영상 품질이 의심되면 같은 조건의 USB UVC 비교 **한 번**을 수행해 입력 압축/전송 영향과 parser 문제를 분리한다.

**Stop/rollback:** 다른 카메라를 조용히 열었거나 L/R/페이지 혼입, false `spread_sent`, fresh 핵심 페이지의 지속 실패이면 해당 단계 중단/재분류. 단계 1 replay로 돌아가 서버 경계가 유지되는지 확인한다. N=5 축소나 무한 timeout 연장으로 합격시키지 않는다.

## 6. 단계 3 — STM build/flash·물리 입력과 reading

대상: B01/B02/B08/B11. 카메라 scan 대신 이미 preflight된 READY 데이터팩으로 입력 경계를 격리한다.

**사전조건:** G5 충족. [firmware README](../hardware/stm32/kitel2026final/README.md)와 `Core/Src/main.c`를 authoritative로 사용한다. CubeIDE build log, ELF/bin hash와 flashed artifact 대응, GPIO active-low/pull-up 및 header map을 기록한다. archive ELF를 최신 빌드로 간주하지 않는다.

현재 firmware는 startup에 PCA 0x40/0x41 presence/init를 요구한다. 따라서 입력 단계라도 firmware가 요구하는 보드를 연결해야 하며, actuator 전원 격리는 하드웨어 담당자가 가능한 구성을 정한다. PCA 없는 입력 시험을 위해 제품 코드를 임의로 우회하지 않는다.

**절차:**

1. `-TestProfile hardware -ComPort <실제 COM>` 설정과 hardware preflight로 포트/환경을 확인한다. preflight의 COM open 성공은 protocol v3 합격이 아니다.
2. 실제 serial/debug log에서 `HELLO,3 → ACK,HELLO,3`를 확인한다. runbook의 오래된 "v2 기본" 설명을 적용하지 않는다. fallback v2/legacy는 migration 호환이며 DOWN release 수용에는 불합격이다.
3. 레버의 부팅 당시 위치와 `NAV,V,A/R`를 확인한다. capture/reading 두 catalog 필터, reading 중 capture 레버 전환, CONFIRM SHORT replay 및 LONG selection 복귀를 시험한다. scan 중 레버로 즉시 모드를 바꾸는 기능을 요구하지 않는다.
4. UP/DOWN/LEFT/RIGHT/PAGE_NEXT/PAGE_PREVIOUS를 짧게 누르고 packet/ACK/server command/snapshot을 대조한다. DOWN 짧게 5회는 문서 끝 clamp가 아닌 구간에서 5회 이동해야 한다.
5. DOWN 2초 hold: v3 STM발 DOWN SHORT 반복은 0, press/release edge 각각 한 번, Host 즉시 1회+650ms 이후 repeat, catch-up 없음. release 관측 후 새 repeat dispatch 0, 이미 in-flight였던 요청 최대 1, 완료 뒤 추가 이동 0을 확인한다.
6. 외부 지연 주입 또는 시험 harness로 server 응답을 500ms 이상 늦춘 뒤 같은 release 시험을 한다. 제품 코드에 sleep을 넣지 않는다. direct COM 분리와 HC-05 radio 단절은 구분해 기록한다. OS가 단절을 언제 알려주는지도 관측한다.
7. 앱/STM 재시작 후 같은 조작 순서를 반복해 stale operation receipt가 재사용되지 않고 stable device cursor는 유지되는지 확인한다.

**성공 evidence:** v3 handshake, sequence ACK/dedupe, server operation IDs, press/release 시각과 Host 관측 시각, generation 변화, 끝 clamp, 재시작 결과. ACK는 서버 왕복과 독립적으로 진행해야 한다. 설정상 ACK timeout 500ms/retry limit와 실제 지연을 대조한다.

**실패 진단:** build/flash/hash → 전원/pin/pull-up/debounce → HC-05 baud/COM → HELLO 버전 → NAV sequence/ACK/retry → Host edge/hold → Coordinator 모드 → S0 command receipt/generation. 버튼이 무반응이면 먼저 어떤 경계까지 기록이 있는지 찾는다.

**Stop/rollback:** release 후 지속 이동, 동일 조작 중복 적용, stale cursor 반환, 반복 disconnect/queue overflow로 제어 불능이면 stop. old v2로 내렸다면 기본 버튼 통신 진단까지만 수행하고 최신 hold 수용 완료를 표시하지 않는다. 실제 flash 변경은 하드웨어 담당자가 검증된 이미지/hash로 복귀한다.

## 7. 단계 4 — FRAME에서 실제 10-cell 점자까지

대상: B10 및 B09와의 공존.

**사전조건:** 단계 3 입력 수용, hardware 담당자의 전원/배선 확인. STM firmware의 PCA1 0x40 CH0~9=top, PCA2 0x41 CH0~9=bottom 및 bottom 방향 매핑을 기준으로 실제 연결을 검토한다. server viewport와 STM cell_count는 모두 10이다.

**절차:**

1. 현재 firmware의 정상 startup/FRAME 경로로 clear frame, 알려진 수식의 셀 패턴을 적용한다. 필요한 개별 dot 검증은 통제된 serial fixture/hardware test 절차로 수행하고 reading 세션의 실제 출력 검증과 구분한다.
2. `FRAME,page,node,span,offset,generation,c0..c9`가 완전한 10셀/0..63인지 확인하고 UART 수신값, `ParseAndApplyFrame`, 실제 점자 돌출을 대조한다. 전송 성공만으로 actuator 적용 성공이라 하지 않는다.
3. 긴 수식의 LEFT/RIGHT 창 이동, span 전환, 표 셀 이동, 일반 텍스트/selection 진입의 clear를 확인한다. within-span/window 이동의 무음은 정상이다.
4. 빠른 DOWN 이동 후 마지막 focus의 generation/cells가 남는지 확인한다. 실제 물리 점자가 따라오지 않으면 serial log/PCA 전원/I2C/모터 상태를 먼저 확인한다.
5. 같은 focus의 실제 Piper 음성을 함께 확인한다. 채널 오류 containment로 음성만 살아 있는 경우 전체 접근성 출력 합격으로 처리하지 않는다.

**성공:** known frame의 좌우/상하/dot 순서가 실제 물리 출력과 일치, 10셀 window 스크롤 끝까지 확인, stale FRAME이 최종 상태를 덮지 않음, 의도한 clear 뒤 잔류 점자 없음, 같은 focus 음성 일치.

**실패 진단:** server braille render diagnostics → snapshot/frame generation → Host 전송 → STM 수신/parser → PCA 주소/채널/I2C 결과 → 모터 상태/배선/기구. current_cells/nav_state 값이 바뀌었다는 사실만으로 모든 Motor_SetState 성공을 추정하지 않는다.

**Stop/rollback:** 제어되지 않는 움직임, 기계적 걸림/비정상 전원 징후, clear 실패 또는 반복적인 frame 혼입이면 hardware 담당 절차로 구동 전원을 차단하고 로그 보존. software input만 검증한 단계 3으로 돌아간다. 물리 결과를 맞추려고 점역 규칙을 임의 변경하지 않는다.

## 8. 단계 5 — 전체 live capture → publish → 읽기·append

대상: B00~B11의 정상 사용자 흐름.

**사전조건:** 단계 2~4 통과, 동일 baseline/firmware/profile 유지. fresh 시연 dataset을 만들 격리 state 및 기존 READY append 기준본 준비.

**절차:**

1. 모드 레버 capture → 새 datapack 선택 → 실제 2 spread 촬영. 각 `spread_sent` 이후에만 넘긴다. source/spread/artifact/outbox/receipt/fragment lineage를 보존한다.
2. CONFIRM LONG으로 freeze/flush through N/seal을 수행한다. ACK 대기 상태에서 종료해도 마지막 artifact가 빠지지 않는지는 단계 6에서 별도로 확인한다.
3. `datapack_saved` 뒤 capture catalog를 확인한다. reading 모드로 명시 전환해 READY를 선택한다. 실제 음성/점자/항목·쪽·창·표 navigation과 CONFIRM replay/exit를 수행한다.
4. 서버의 current revision에 preflight를 실행한다. 예: `tools/windows/e0b-preflight-datapacks.bat <시험 state root> <evidence report path>`. READY 목록/검사 수/error/warning을 기록한다.
5. capture 모드에서 기존 READY를 선택해 한 spread를 append하고 저장한다. revision 증가, 기존 page/item ID 및 기존 페이지 순서 보존, 새 L/R가 뒤에 붙는지 확인한다.
6. 같은 stable device ID로 읽기 재진입 및 앱 재시작 후 cursor 복구를 확인한다. 이전 reading session이 고정한 revision과 새로 연 current revision을 구분한다.

S1은 `_revisions` 아래 immutable revision을 게시한다. document/audio 파일 위치는 `datapack_revisions.root_relative_path`와 manifest hash를 조회해 결정한다. 옛 runbook의 `datapacks/<id>/document.json`이 항상 current라고 가정하지 않는다.

**성공:** 2 spread/4 pages fresh READY와 append 후 올바른 revision/page order, preflight error 0, 주요 시연 내용과 실제 출력 일치, 저장/완료 안내의 시점 일치, 재진입/재시작 후 올바른 상태. 두 번의 정상 시연 반복 중 데이터팩/조작 identity가 충돌하지 않아야 한다.

**실패 진단:** B-ID lineage를 따라 마지막 성공과 첫 실패를 찾는다. V4 ACK가 있어도 fragment가 queued/rejected/error인지 확인하며 OCR 완료로 간주하지 않는다. OCR가 맞고 spoken text가 틀리면 speech 규칙, spoken text가 맞고 WAV lookup이 없으면 serving preflight/S-03, WAV가 맞고 소리가 없으면 장치 출력으로 좁힌다.

**Stop/rollback:** wrong page/side, 중복 fragment, 성공 안내 후 READY 없음, append가 기존 revision을 손상하면 즉시 stop/P0 검토. 새 revision 실패는 기존 READY를 계속 읽을 수 있어야 한다. 복구 시 파일만 덮어쓰지 말고 정지한 서버의 일관된 DB/파일 checkpoint 단위로 복원한다.

## 9. 단계 6 — bounded failure/recovery와 prototype acceptance

무작위 fuzzing/장시간 soak 대신 아래 선정한 시험을 각 1회 실행한다. 정상 시연은 단계 5와 합해 2회로 제한한다. 실패 시 동일 원인 재현/진단은 하되 새 수정을 자동 시작하지 않는다.

| 시험 | 주입/사전조건 | 성공 조건 및 evidence | 실패 시 진단·stop |
|---|---|---|---|
| F1 local obstruction | 정상 카메라에서 손 가림 후 제거 | 가림 중 false upload 없음, 명시 guidance, 제거 후 정상 후보/전송 | source→candidate/identity. 핵심 페이지 지속 실패면 단계 2 보류 |
| F2 ACK 응답 유실 | durable receipt 이후 응답 한 번 유실; 외부 proxy/harness 사용 | 같은 key/hash 재시도, receipt 1개/fragment L/R 2개/duplicate 0, local ACK 후 cleanup | outbox→V4→S1 순서. receipt 불명확하면 recapture/삭제 금지 |
| F3 pending 상태 C0 단절 | artifact가 queued/retrying이고 Scanner가 pending인 시점에 연결 단절 | freeze 보존→연결 회복→CONFIRM→같은 scan/artifact 재개, start 충돌 없음, 정상 ACK/seal. S-02 concrete regression과 실제 네트워크 각각 구분 | held engine/pending artifact/outbox→recovery start. 프로세스 종료 또는 lineage 분실이면 stop/P1 |
| F4 scan stop 중 pending | 마지막 artifact ACK 전에 CONFIRM LONG | cutoff 고정, through N 모두 ACK 전 seal/저장 안내 없음, 이후 READY에 마지막 L/R 포함 | freeze/pending callback→flush→seal→publish. 페이지 유실이면 stop/P0 검토 |
| F5 결정적 reject / finalize 실패 | 격리 fixture로 잘못된 bundle 또는 parser/TTS 실패 | reject/error 명시, false READY 없음, 기존 READY/원본 보존. D-01의 same-sequence recapture는 성공 요구에서 제외하고 새 datapack으로 재시작 | V4 reject와 S1 post-ACK reject를 구분. 파일/DB 손상 또는 silent partial publish면 stop |
| F6 DOWN release·slow response·radio loss | 단계 3의 v3/500ms 지연 및 실제 COM/radio 단절 | Host release 관측 뒤 dispatch 0, 최대 1 in-flight, 최종 focus 유지. physical→Host 지연 별도 기록 | UART edge/ACK→OS 단절 감지→Host hold. radio silent-loss의 무한 repeat를 허용된 성공으로 세지 않음 |
| F7 reading restart / output interruption | 같은 device/book, 빠른 이동, CONFIRM exit, 앱 재시작 | cursor 복구, 새 command 적용, 과거 audio/FRAME의 최종 덮어쓰기 없음 | boot/operation namespace→S0 progress→snapshot→audio/serial. S-01 재발 시 stop |

F2/F5의 서버 failure semantics는 기존 real local HTTP/실제 store regression으로 이미 고정한 부분을 재사용할 수 있다. 실제 장치 연결이 결과에 영향을 주는 F3/F4/F6/F7은 장치 run evidence를 남긴다. 각 failure를 full OCR로 다시 합성할 필요는 없다.

**최종 성공:** Gate 문서의 prototype 완료 조건 충족, 필수 물리 check not_run 0, P0 미해결 0, P1 미해결 0 또는 핵심 경로에서 제거된 명시적 범위 결정, Deferred workaround 수행 가능, 두 정상 run의 lineage와 manual audio/braille 판정 보존. 실패를 containment했다는 사실만으로 핵심 출력 실패를 면제하지 않는다.

## 10. 단계 7 — Raspberry Pi target validation (후속)

**사전조건:** Laptop prototype acceptance와 계약 baseline 고정. Pi가 실제 최종 시연 대상이면 이 단계까지 최종 완료 범위에 넣는다. 개발 host 결정과 [E0-Core 문서](../device-runtime/docs/device-integration-e0-core.md)의 Laptop/Pi 구분을 유지한다.

**절차:** Desktop 서버와 데이터팩은 고정하고 Device host만 Pi로 바꾼다. camera/UVDoc/M1 import·성능, writable persistent outbox 및 재부팅 보존, serial 권한/HC-05, 실제 10-cell FRAME, ALSA/PipeWire/sounddevice 출력, network presence, boot/start/stop을 순서대로 검증한다. 같은 G2~G4 의미 및 단계 3~6 사용자 계약을 적용한다.

**evidence/성공:** Pi OS/Python/model hash, 실제 제품 workload의 latency/RSS/CPU/온도/전원 및 underrun/disconnect 관측, 재시작 후 outbox/cursor 보존, 실제 음성/점자 확인. 처음부터 임의 production 부하 SLA나 장기 soak를 추가하지 않는다. workload가 사용자 경로를 유지하는지 측정한다.

**실패 진단:** dependency/asset → camera/serial/audio 권한 → 저장소/네트워크 → 실제 inference/output resource 간섭. Windows 전용 launcher/platform 표기만 보고 architecture redesign을 시작하지 않는다.

**Stop/rollback:** Pi에서 핵심 경로를 만족하지 못하면 Laptop 통합 결과는 유지하고 Pi 단계만 보류한다. 시연 대상이 Pi로 고정돼 있다면 전체 완료는 대기다. Pi 시험 실패를 숨기기 위해 `RasberryPITest`의 부하 결과를 제품 성공으로 대체하지 않는다.

## 11. 공통 stop/rollback 절차

1. 사용자 입력/scan을 정지하고 추가 upload/seal 명령을 보내기 전에 현재 scan/receipt/finalize 상태를 확인한다. 기구 위험이 있으면 하드웨어 담당 절차가 우선이다.
2. 마지막 정상 B-ID와 첫 실패 B-ID, 시간, operation key/digest, pending artifact, server scan/current revision을 기록한다. 실패 evidence를 저장한 뒤 재시도를 결정한다.
3. 재시도는 상태에 따라 구분한다. 전송 불확실이면 같은 artifact/key; 결정적 reject면 새 datapack; 이미 sealing/READY이면 상태 확인 후 읽기/완료 관측. 무조건 재촬영하거나 신규 seal을 만들지 않는다.
4. source rollback은 대응 firmware/config와 함께 한다. 데이터 rollback이 필요하면 server/device를 정지한 상태에서 **일관된 checkpoint 묶음**을 사용한다. 이미 ACK된 서버 데이터와 ACK 전 Device 파일의 소유권을 확인한다.
5. `e0b-reset-experimental-datapacks.bat`는 일상적인 retry가 아니다. 증거 보존 후 별도 명시적 전체 실험 초기화가 필요한 경우에만 기존 runbook 절차를 따른다. 이 계획은 자동 reset/삭제를 지시하지 않는다.
6. 문제를 P0/P1/Deferred로 기록하고 해당 단계 재개 조건을 정한다. 성공한 무관 단계는 새 증거가 없는 한 처음부터 반복하지 않는다.

## 12. Repository 재대조 결과

| critical boundary | 대응 단계 | 근거 코드/기존 tests |
|---|---|---|
| B00 설정/C0/remote origin | 0, 1, 7 | `local_composition.py`, `connectivity.py`, `test_c0_local_http.py` |
| B01 STM GPIO/ACK/hold | 3, F6 | `stm_serial.py`, `hold_repeat.py`, `application.py`, firmware `main.c`, `test_stm_mode_contract.py` |
| B02 mode/catalog/idempotency | 1, 3, 5, F7 | `coordinator.py`, `catalog.py`, S0 `_receipt`, S-01 |
| B03 camera/candidate/identity | 1, 2, F1 | `video/sources.py`, `runtime_composition.py`, `engine.py`, `opaque_identity.py`, video unit tests |
| B04 same-frame artifact/freeze | 1, 2, F3/F4 | `video/artifacts.py`, `spread_preparer.py`, `book_scanner_runtime.py`, S-02 |
| B05 outbox/V4 receipt | 1, F2/F3 | `delivery.py`, `delivery_store.py`, `http_v4.py`, `v4_upload.py`, `test_v3b_v4_local_http.py` |
| B06 Page IR/accessible fragments | 1, 2, F5 | `s1_parser.py`, `s1_services.py`, `vl_page_ir.py`, flattening, `test_server_s1_ingest.py` |
| B07 seal/append/TTS/publish | 0, 5, F4/F5 | `s1_services.py`, `s1_assembler.py`, `test_server_s1_finalize.py`, serving preflight |
| B08 persisted navigation | 1, 3, 5, F7 | `s0_services.py`, `session.py`, `speech_controller.py`, `test_server_s0.py`, `test_server_wire.py` |
| B09 document/system audio | 1, 2, 4~6 | `reading_audio.py`, `adapters/reading_audio.py`, `system_audio.py`, audio unit tests |
| B10 braille projection/physical actuation | 4~6 | `braille_presenter.py`, `stm_serial.py`, `main.c` ParseAndApplyFrame/ApplyBrailleFrame/Motor_SetState |
| B11 failure/stop/restart | F2~F7, 7, §11 | Coordinator recovery, concrete Scanner adapter, durable outbox, C0, S0 progress, STM re-handshake |

계획 작성 후 위 경로를 repository와 다시 대조했다. software regression/replay/datapack preflight/physical acceptance를 분리했으며, legacy 경로와 오래된 성공 보고서가 최신 production/hardware 증거를 대신하지 않도록 했다. 이후 변경은 해당 B-ID와 gate의 증거 유효성부터 다시 판단한다.
