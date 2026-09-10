# PASS 4 — Documentation Blueprint

상태: COMPLETE. 최종 설명문을 작성하기 위한 설계 산출물이다. **PASS5 최종 Technical Overview 및 PASS6 Verification Report는 작성하지 않는다.** 아래의 항목은 절의 목적·필수 사실·근거·도식 요구사항이며 완성 문서의 prose가 아니다.

## 입력과 설명 전략

| 입력 산출물 | 이번 단계가 사용하는 내용 |
|---|---|
| [PASS0](PASS_0_SCOPE_BASELINE.md) | Project Scope, E0/E1/E2, 현재 Windows 경로·Pi 목표 분리, legacy/alternative 경계 |
| [PASS1](PASS_1_EXECUTION_RECONSTRUCTION.md) | W01–W20의 실제 순서·병렬 경계·mode 분기 |
| [PASS2](PASS_2_ALGORITHMS_AND_DECISIONS.md) | A01–A11 핵심 알고리즘 및 J01–J17 판단; page mask/table/correction 내부 보충 근거 포함 |
| [PASS3](PASS_3_DATA_AND_FAILURES.md) | D01–D15 변환, I01–I03 identity/completion/owner, F01–F28 실패, X01–X05 사례와 evidence 한계 |

- 대상: 개발 경험이 있을 수 있으나 ASL_OCR 소스를 처음 접하는 독자.
- 조직 원리: 사용자 문제 → 물리/네트워크 경계 → 정상 workflow → 결과를 좌우하는 판단 → 데이터 형태 → 실패 → 구현 위치.
- 본문에서 concept를 먼저 설명하고 해당 절 끝에 1–3개의 핵심 source anchor만 연결. 전체 module 목록은 9절에 배치.
- 용어 최초 정의: spread=한 frame에 담긴 좌우 두 페이지; artifact=전송할 파일 묶음; fragment=서버가 page별로 처리하는 단위; revision=게시된 읽기 내용의 불변 버전; focus=한 번의 탐색 대상; generation=읽기 출력 권한을 구분하는 state 값.
- 최종 문서 예시 경로(미생성): `docs/ASL_OCR_TECHNICAL_OVERVIEW.md`.
- 구현의 지원 범위와 실험의 수용 범위를 나누는 표기: `현재 구현`, `특정 run 검증`, `미검증/계획`. 모든 알고리즘 설명에 과거 PASS라는 꼬리표를 붙이지 않음.

## 최종 문서 목차와 절별 계약

### 1. 프로젝트가 해결하는 문제

- **Purpose:** 프로젝트의 사용자 가치와 bounded prototype 범위를 먼저 고정.
- **Reader should understand:** 인쇄 교재의 혼합 텍스트/수식을 촬영하여 버튼으로 탐색하고 음성·10-cell 점자로 읽는 것이 목표. OCR 문자열 추출만으로 목표가 완성되지 않는 이유.
- **Required facts:** 두 spread26/27·28/29가 대표 demo; hands-free에 가까운 촬영 안내와 physical controls 목표; 혼합 수식 구조/페이지 경계/좁은 점자창/비동기 처리의 어려움; 최종 출력까지 completion을 분리해야 함.
- **Required diagrams:** 없음. 입력/출력 두 줄 요약 또는 작은 표로 충분.
- **Evidence:** PASS0 Project Scope; PASS1 W02–W20; PASS3 I02.
- **Do not include:** 파일 목록, OCR 전체 역사, 모든 교재 지원 주장, 미검증 설계 의도, 장애 연대기, Pi 이식 완료 주장.

### 2. 시스템 전체 구조

- **Purpose:** 독자가 '무엇이 어디서 처리되는가'를 이해하도록 책임과 resource owner를 제시.
- **Reader should understand:** Android는 image source, Laptop은 Device/Scanner/local footer recognition·unwarp·outbox·audio/serial host, Desktop은 C0/S0/V4/S1·본문 OCR·Piper·persistent storage, STM/PCA는 physical boundary. Pi4는 Laptop 역할의 목표 배포.
- **Required facts:** local M1와 server VL의 역할 차이; endpoint별 책임; shared model/synthesizer serialization; audio bytes는 server 생성·host 재생; 같은 host serial object가 controls/presenter; thread 최신값·durable queue·worker lease의 구분.
- **Required diagrams:** G01 architecture. 옆 표에 component/owner/persistent state/외부 dependency만 배치.
- **Evidence:** PASS0 E0/E1/E2·Dependencies; PASS1 W01/W04/W12/W17–W19; PASS3 I03/D11–D15; source index M01–M06/M13–M17.
- **Do not include:** constructor dependency graph 전체, hardware GPIO/LUT 수치 목록, 모든 optional backend. Pi planned node를 production 실선과 섞지 않음. Desktop model을 Pi로 이전하는 것으로 그리지 않음.

### 3. End-to-End Workflow

- **Purpose:** 대표 사용 경로를 entry부터 종료/복구까지 한 번에 따라가게 함.
- **Reader should understand:** 새 datapack→한 spread acquisition/identity/preparation→receipt→다음 spread→LONG cutoff/flush/seal→READY→선택/탐색→audio/FRAME→재진입/재시작 복구의 순서.
- **Required facts:** W01–W20을 8–10개 개념 단계로 묶음; receipt 이후 page parser는 다음 촬영과 병렬; CONFIRM LONG은 OCR 시작 버튼이 아님; reading은 기존 READY에서 바로 시작 가능; app vs server vs firmware lifecycle; V4 receipt·READY·physical completion을 다른 노드로 표시.
- **Required diagrams:** G02 workflow/sequence. 본문 표는 단계/입력/결과/다음 분기만 요약, 함수 호출 stack 생략.
- **Evidence:** PASS1 전체와 비동기 경계; PASS2 A06/A09; PASS3 정상 데이터 연결/I02.
- **Do not include:** H2 기존 READY 시작을 capture 통과로 묘사, serial ACK를 STEP 완료로 묘사, 각 polling 함수 반복, 앱 전체를 하나의 선형 blocking pipeline으로 표현.

### 4. 핵심 처리 단계

- **Purpose:** workflow에서 결과를 실제로 바꾸는 알고리즘을 '어떤 문제 때문에 필요하며 어떻게 결정하는가' 중심으로 해설.
- **Reader should understand:** 촬영 품질·identity·기하 보정·문서 구조·신뢰 정책·게시·navigation/output이 서로 다른 판단임.
- **Required facts:** 아래 4.1–4.8 순서. 각 설명은 문제/입력→핵심 아이디어→기준→출력/다음으로 통일. 알고리즘 수식은 seam DP/boolean page-change/AST projection에 도움될 때만 짧게 사용.
- **Required diagrams:** G03 acquisition decision 필수; G05 수식 projection 선택; G02/G04 반복 복사 금지.
- **Evidence:** PASS2 A01–A11, PASS3 D/F 해당 연결.
- **Do not include:** 실제 숫자를 나열하는 config 사전, neural network layer 추측, generic wrapper 설명, 전체 함수 pseudocode.

#### 4.1 입력과 촬영할 순간 선택

- **Purpose:** '잘 보이는 것'과 기계가 촬영해도 되는 상태를 분리.
- **Reader should understand:** orientation/preview 비율, page mask, obstruction, stability, best-frame selection의 단계 차이.
- **Required facts:** source profile rotation/crop; full frame 보존/preview 축소; 밝은 contour의 대비·edge·height·area 가중합; provisional border/chroma obstruction; stability AND; 최종 frame는 margin 우선 lexicographic ranking. mask 후보 ranking과 frame ranking을 혼동하지 않음.
- **Required diagrams:** G03 앞부분 또는 mask→stable window→selected frame 작은 흐름. 새 별도 대형 도식 불필요.
- **Evidence:** A02 및 내부 보충; J01/J02; D02/D03; F02–F06; M03/M04.
- **Do not include:** '손을 반드시 인식해야만 페이지 넘김', '미리보기 회전만 고치면 입력도 고쳐짐', 모든 경계접촉 hard reject, 보편 피부/배경 성능 주장.

#### 4.2 같은 spread와 새 spread 구별

- **Purpose:** duplicate 억제와 page-change liveness 사이의 판단 구조 설명.
- **Reader should understand:** local footer ROI raw pair 관측·bank와 visual hysteresis가 다름; DIFFERENT와 촬영 허가는 다름.
- **Required facts:** M1 exact L/R pair·frame-disjoint·accepted receipt bank; N/K/과반의 행동; missing/timeout UNKNOWN; numeric coherent pair는 연속 pair 확인이며 순차+2 강제가 아님; DIFFERENT AND (visual OR numeric); SAME rearm; low-level1500ms와 run override8초를 구분.
- **Required diagrams:** G03 중심 decision diamond. SAME/UNKNOWN/DIFFERENT 뒤의 continuation을 모두 표시.
- **Evidence:** A03/A04; J03–J07; D04/I01; F07/F08; X02; M05.
- **Do not include:** confidence0.62가 raw bank 수락 기준이라는 설명, 성공을 위해 N/timeout 완화 제안, printed footer number=server page_index, late-success의 trigger 단정.

#### 4.3 좌우 추출과 곡면 보정

- **Purpose:** same-frame lineage와 OCR 입력 정돈을 설명.
- **Reader should understand:** seam DP로 보수적 L/R crop을 얻고 UVDoc sampling으로 보정한다는 원리; 두 side 모두 필요.
- **Required facts:** central band luminance+center prior, 제한 row transition/누적 최소비용, uncertainty band 중복 보존, crop geometry, model grid→원 crop sampling, both-side readiness; no uncorrected success fallback.
- **Required diagrams:** G04 image 변환 부분에 연결. seam의 입력/출력 좌표계 작은 보조도 선택.
- **Evidence:** A05; J08/J09; D05/D06; F09/F10; M06.
- **Do not include:** UVDoc 학습 architecture 추측, source JPEG byte-lossless 주장, 두 crop 무조건 비중첩, content accuracy를 size/aspect gate가 보장한다는 설명.

#### 4.4 OCR에서 문서의 읽기 구조 만들기

- **Purpose:** 단순 OCR 텍스트에서 focus 순서가 생기는 과정을 설명.
- **Reader should understand:** VL block labels/order를 활용해 TEXT/MATH/TABLE/UNSUPPORTED_VISUAL을 구성하고 문제의 역할을 묶은 뒤 펼침.
- **Required facts:** PaddleOCR-VL direct block path; deterministic raw/normalized correction; bbox/order; exact choice-row exception; HTML span occupancy와 estimated cell bbox; problem scope regex/marker aggregation; visited member flattening; embedded text만 보존하는 visual policy.
- **Required diagrams:** G04 blocks→IR→AccessiblePage 부분. TABLE/PROBLEM_UNIT은 한 예의 tree→focus 표로 보완 가능.
- **Evidence:** A07/A08 및 내부 보충; J10; D08–D10; F15/F19; M09/M10.
- **Do not include:** legacy token-based LayoutBuilder를 active S1에 삽입, table 미지원이라는 오래된 주석, 그림 의미 완전 분석, converter confidence1.0=정확한 OCR.

#### 4.5 수식의 의미와 음성·점자 신뢰 정책

- **Purpose:** raw LaTex가 서로 다른 접근성 출력으로 바뀌는 핵심 설명.
- **Reader should understand:** parser는 표현 구조를 만들며 문제를 풀지 않음; PARTIAL/INVALID에서 음성과 점자의 행동이 다름.
- **Required facts:** token→recursive presentation AST; precedence/grouping/fraction/scripts/Unknown; VALID/PARTIAL/INVALID 조건; spoken naturalization/pronunciation; 규칙기반 logical dots; 미지원 symbol exception의 degraded clear; inline lexical/choices standalone accessibility 제한.
- **Required diagrams:** G05 선택(짧은 수식 1개 AST→speech/dots 분기), 그리고 status→speech/braille 3행 표는 필수.
- **Evidence:** A08; J11; D09/D10/D13/D14; F19/F24; X05; M10/M11.
- **Do not include:** 일반 한국어 본문 전체가 점자로 출력된다고 설명, VALID=원문 정답, 전체 LaTex 지원, 모든 점자 규정의 원문 복제.

#### 4.6 전송 완료와 읽기 가능한 revision 게시

- **Purpose:** durable boundary가 왜 여러 단계인지 설명.
- **Reader should understand:** outbox/receipt/parser/seal/READY의 책임 분리가 데이터 유실·중복·불완전 게시를 막는 방법.
- **Required facts:** sequence/idempotency/hash, durable acceptance, receipt 후 parser 독립 진행, freeze/cutoff/flush, 모두 ready인 fragment 및 optional base 합치기, utterance WAV/index/hash validation, immutable publish/recovery.
- **Required diagrams:** G02의 parallel swimlane과 I02 completion 표 참조. database table별 diagram은 불필요.
- **Evidence:** A06/A09; J13/J14; D06/D07/D11; F11–F18; M07/M08/M12.
- **Do not include:** network exactly-once 보장, receipt와 READY 동일 취급, empty draft를 성공 처리, append 실패가 기존 READY도 제거한다고 설명.

#### 4.7 페이지·항목·표·수식 창 탐색과 cursor 복구

- **Purpose:** 작은 버튼 집합으로 어떤 단위를 움직이는지 설명.
- **Reader should understand:** node/page/table/span/window가 별도 좌표이며 focus/generation/audio 관계와 stable anchor restore가 있음.
- **Required facts:** A09 command matrix, table enter/exit/page jump, whole-window step, plain-text clear, boundary message, same-focus replay 새 generation, pure-window silent, audio completion의 무권한, server persistent device/datapack anchors; corrupt cursor는 처음으로 silent reset하지 않음.
- **Required facts 보완:** plain-text clear는 DOCUMENT scope; TABLE buffer는 열/행/지원된 값이며 현재 math는 leaf AST로 제한. TABLE LONG scroll을 arbitrary structured-math 지원으로 설명하지 않음. S0 negotiated viewport와 standalone defaults(20/40), hardware10을 분리.
- **Required diagrams:** command→단위→state reset/발화 표. G02 recovery 경로에 참조; 전체 state machine 추가는 필요할 때만.
- **Evidence:** A01/A09; J12; D01/D12/D14; I01; F20/F21; X03/X04; M02/M13/M14.
- **Do not include:** offset0 항상 오류, 같은 음성이면 page 이동 실패, generation은 이동한 거리, process별 새 stable device_id.

#### 4.8 같은 상태의 실제 출력 전달

- **Purpose:** snapshot이 스피커와 셀에 도달하는 마지막 경계와 권한 설명.
- **Reader should understand:** audio와 FRAME은 같은 snapshot의 독립 projection; native owner/epoch와 ordered serial/RX 검증이 stale 출력과 손상을 억제하지만 physical 완료는 별도.
- **Required facts:** authenticated ref→WAV/cache→single owner PCM lifecycle; signal-only stop/current epoch; latest desired FRAME coalescing; V3 input ACK/dedupe/release; firmware IRQ ring/resync/full validation; bit3+3/reversal/LUT/PCA success cache; bus success≠physical pin position.
- **Required diagrams:** G01 끝부분과 completion 표 연결. worker/thread lifecycle 도식은 한 줄 타임라인 정도로 제한.
- **Evidence:** A10/A11; J15/J16; D13–D15/I02/I03; F22–F28; M15–M17.
- **Do not include:** FRAME가 순서대로 모두 물리 적용, FRAME ACK protocol 신설, firmware generation monotonic rejection 가정, 사진만으로 mapping/LUT 원인 확정, native cleanup timeout=강제중단.

### 5. 주요 데이터와 데이터 변환

- **Purpose:** workflow에서 무엇이 보존·축약·추가되는지 독자가 추적하도록 함.
- **Reader should understand:** pixels→artifact→fragment IR→accessible revision→cursor snapshot→WAV/dots→actuator의 형태 차이와 각 identity.
- **Required facts:** PASS3 D01–D15를 7–9행으로 묶은 변환 표; input/output·metadata·loss·next invariant. source-frame vs observation-frame, artifact vs receipt, printed label vs page ID, revision vs session vs generation, estimated table bbox, JPEG/warp/model/viewport의 서로 다른 손실.
- **Required diagrams:** G04 data transformation. I01 ID표 중 critical 6개 정도를 옆에 배치.
- **Evidence:** PASS3 D01–D15/I01; A03/A05/A07–A11.
- **Do not include:** 모든 JSON schema/enum, credentials/local absolute state paths, byte inventory 전체. 일반 field dump로 개념 설명을 대체하지 않음.

### 6. 판단 로직

- **Purpose:** 독자가 시스템의 선택·대기·포기 원리를 비교할 수 있는 짧은 reference.
- **Reader should understand:** threshold/ranking/fallback/retry가 어떤 행동을 통제하는지; 서로 다른 confidence의 의미.
- **Required facts:** J01–J17를 ①quality/rank ②identity/time ③structure/trust ④durability/retry ⑤generation/backpressure 묶음으로 편집. N/K, time window, lexicographic vs weighted contour score, ASTstatus, capped delay vs bounded attempts, retryable metadata vs actual retry 구분. configuration provenance 필수.
- **Required diagrams:** G03 재참조; compact decision table 1개. 모든 상수로 flowchart를 만들지 않음.
- **Evidence:** PASS2 J01–J17와 A02/A03 내부 보충; PASS3 F02–F04/F12/F16/F22.
- **Do not include:** threshold 조정법/추천치, timing PASS를 얻기 위한 값 변경, 휴리스틱을 통계적으로 calibrated probability로 해석, duplicate 기준완화.

### 7. 대표적인 실행 예시

- **Purpose:** 개념을 실제 식별 가능한 데이터 계보에 연결.
- **Reader should understand:** 무엇이 성공 증거였고 무엇이 남았는지를 한 사례로 추적.
- **Required facts:** X01 fresh2spread→2receipt→4fragment→cutoff2→revision1을 주 예시. X03/X04로 동일 website audio의 다른 page ID와 restart full cursor 비교. 수식 예시는 test fixture 기반이라는 표기로 분리(X05); fresh H1은 math-window positive offset 증거가 아님.
- **Required diagrams:** G02를 반복하지 않고 sequence/side/page_id/status/revision의 짧은 trace 표. 수식 실제 변환은 G05를 선택했을 때만 재참조.
- **Evidence:** PASS3 X01–X05; docs/H1_FRESH_ALIGNED_RUN_20260908.md의 raw evidence index. 날짜/당시 source와 현재 분석 baseline을 구분.
- **Do not include:** 수백 줄 raw log, 임의로 만든 receipt·AST를 실측처럼 제시, exact physical turn timestamp가 없는 first→second cue interval을 page-change latency로 표기, H4 통과 선언.

### 8. 실패하는 경우와 한계

- **Purpose:** 정상 경로가 성립하지 않는 조건과 실제 회복 owner를 설명.
- **Reader should understand:** 기다려야 하는 경우/새 input 필요/작업 거절/앱 fatal/관측 부족을 구분. supported fallback이 무엇이며 없는 fallback이 무엇인지 이해.
- **Required facts:** F01–F28을 camera·delivery·parser/publish·reading/output·shutdown 5묶음으로 축약. 원인/감지/retry/fallback/포기 표. partial AST와 visual text preservation, preview-only degrade는 명시적 fallback; webcam substitution/invalid artifact acceptance/automatic DB reset은 없음. H1 orientation/liveness·harness encoding/exit·hardware residual·Pi performance 미검증 유지.
- **Required diagrams:** completion ladder 표 필수(I02 축약). G03 UNKNOWN loop만으로 모든 failure를 표현하지 않음; 장문의 retry flowchart는 생략.
- **Evidence:** PASS3 F01–F28/I02/I03, Q6/Q7, X02; source/test vs past-run/hardware boundary 구분.
- **Do not include:** 이미 수정한 incident를 현재 재현된 defect로 단정, 손실 log로 OCR 내용 손상 단정, generic 보안 경고 목록, native dump 미확인 root 확정, 새 architecture layer 제안.

### 9. 코드 구조와의 대응

- **Purpose:** 개념을 이해한 독자가 다음에 열 소스와 테스트를 찾을 수 있게 함.
- **Reader should understand:** 어느 책임이 어느 entrypoint/module에 있고 어떤 test가 해당 contract를 다루는지.
- **Required facts:** 아래 M01–M17의 concept→source→test index; 대표 launch(E0/E1/E2), optional/legacy caveat; baseline hash manifest 링크. 한 concept당 핵심 source만 먼저, 나머지는 분석 산출물 링크로 확장.
- **Required diagrams:** 불필요. concept mapping table 사용.
- **Evidence:** PASS0 entrypoints/legacy, PASS1 symbols, PASS2 card source/test, PASS3 failure source; [baseline.json](baseline.json).
- **Do not include:** 폴더 tree가 본문 구조를 지배, 전 함수/클래스 해설, dependency lock 재기술, diagnostic script를 product runtime으로 설명.

## Diagram specifications — PASS5용, 아직 렌더/최종 도식 작성 안 함

| ID / 우선도 | 종류·배치 | 필수 요소 / invariants | 제외·검증 주의 |
|---|---|---|---|
| G01 필수 | Mermaid flowchart / §2 architecture | Android, Laptop Device+Scanner+outbox+audio/serial, Desktop C0/S0/V4/S1+VL/Piper+DB/storage, HC05→STM→PCA→cells. 실선 current path, 별도 점선 Pi4 target. 제어/이미지/WAV/FRAME edge label | 피드백 없는 물리 센서 화살표 금지; Laptop footer와 Desktop body OCR 분리 |
| G02 필수 | Mermaid sequenceDiagram 또는 swimlane / §3 | user, Device, Scanner, V4/S1, S0, output. loop2spreads; receipt 이후 parser 병렬; LONG freeze/flush/seal→validate/publish→READY; reading/reentry 흐름 | receipt와 parser-ready 메시지 합치지 않음. packet ACK를 upload receipt로 그리지 않음 |
| G03 필수 | Mermaid flowchart / §4.2 | candidate eligible/stable → raw query; SAME/UNKNOWN/DIFFERENT; receipt 이후 page-change에서는 DIFFERENT AND (visual OR numeric); SAME reset/rearm; timeout UNKNOWN loop | 모든 DIFFERENT가 capture로 직결되지 않게 구분; query missing을 DIFFERENT로 연결 금지; 8초를 universal constant로 표기 금지 |
| G04 필수 | Mermaid flowchart / §5 | full frame→preview decision와 source preparation 분기→same-frame L/R→durable bundle→VL blocks→IR→AccessiblePages→revision/audio→snapshot→WAV/10cells→PCA. lossy/estimated/metadata boundary label | 모든 원본 파일이 읽기 snapshot에 실리는 것처럼 그리지 않음. 각 node JSON schema 전체 삽입 금지 |
| G05 선택 | Mermaid small AST/projection / §4.5 | repository fixture의 짧은 분수/첨자 하나, presentation tree→한국어 발화와 dots. 아래 별도 status 표로 PARTIAL/INVALID 대비 | 입력/기대 문자열·cells를 fixture/source와 확인 후만 사용. 실물 이 예제를 관측했다고 쓰지 않음 |

도식 표기 규칙: 사람이 읽는 concept label 우선; source path는 도식 밖. NORMAL / RETRY / ERROR 화살표 명시; solid/dashed 의미 legend 제공. 하나의 도식에 모든 polling·exception을 넣지 않는다.

## Concept → implementation index (9절용)

링크는 이 분석 디렉터리에서 repository source로 연결된다. 이 표는 함수 목록이 아니라 설명 개념의 진입점이다.

| ID / 개념 | 핵심 source | 테스트 진입점 |
|---|---|---|
| M01 실행 구성 | [Device main](../../device-runtime/src/asl_device/__main__.py), [composition](../../device-runtime/src/asl_device/local_composition.py), [server main](../../document-parser/src/document_parser/server/combined_server.py) | [app](../../device-runtime/tests/unit/test_application.py) |
| M02 입력·mode·hold | [application](../../device-runtime/src/asl_device/application.py), [Coordinator](../../device-runtime/src/asl_device/coordinator.py), [hold](../../device-runtime/src/asl_device/hold_repeat.py) | [STM mode](../../device-runtime/tests/integration/test_stm_mode_contract.py) |
| M03 source·preview | [sources](../../book-scanner/src/book_scanner/video/sources.py), [preview](../../book-scanner/src/book_scanner/video/operator_preview.py), [runtime config](../../book-scanner/src/book_scanner/video/runtime_composition.py) | [camera recovery](../../book-scanner/tests/unit/video/test_h123_camera_recovery.py) |
| M04 frame quality | [candidate](../../book-scanner/src/book_scanner/video/candidate.py), [contrast mask](../../book-scanner/src/book_scanner/detect/contrast_spatial.py), [obstruction](../../book-scanner/src/book_scanner/video/obstruction.py) | [candidate tests](../../book-scanner/tests/unit/video/test_candidate.py) |
| M05 identity·page-change | [engine](../../book-scanner/src/book_scanner/video/engine.py), [raw bank](../../book-scanner/src/book_scanner/video/opaque_identity.py), [hysteresis](../../book-scanner/src/book_scanner/video/page_change.py), [recognizer](../../book-scanner/src/book_scanner/video/page_number_recognizer.py) | [raw identity](../../book-scanner/tests/unit/video/test_opaque_identity.py), [page-change](../../book-scanner/tests/unit/video/test_page_change.py) |
| M06 split·unwarp·artifact | [seam](../../book-scanner/src/book_scanner/detect/spine_seam.py), [extraction](../../book-scanner/src/book_scanner/detect/spread_extraction.py), [UVDoc](../../book-scanner/src/book_scanner/correct/uvdoc_adapter.py), [preparer](../../book-scanner/src/book_scanner/video/spread_preparer.py) | [preparation](../../book-scanner/tests/unit/video/test_spread_preparer.py) |
| M07 local durability | [delivery](../../device-runtime/src/asl_device/delivery.py), [store](../../device-runtime/src/asl_device/delivery_store.py) | [delivery tests](../../device-runtime/tests/unit/test_delivery_v3b.py) |
| M08 durable server ingest | [V4](../../document-parser/src/document_parser/server/v4_upload.py), [S1](../../document-parser/src/document_parser/server/s1_services.py) | [V4 tests](../../document-parser/tests/unit/test_server_v4_upload.py), [ingest](../../document-parser/tests/unit/test_server_s1_ingest.py) |
| M09 model→IR | [VL adapter](../../document-parser/src/document_parser/ocr/paddleocr_vl_adapter.py), [Page IR](../../document-parser/src/document_parser/serialization/vl_page_ir.py), [table](../../document-parser/src/document_parser/serialization/table_html.py), [correction](../../document-parser/src/document_parser/postprocessing/ocr_dictionary.py) | [VL tests](../../document-parser/tests/unit/test_vl_page_ir.py), [table tests](../../document-parser/tests/unit/test_table_html.py) |
| M10 structure→focus | [problem units](../../document-parser/src/document_parser/structure/problem_units.py), [flatten](../../document-parser/src/document_parser/accessibility/flattening/structure_nodes.py) | [problem tests](../../document-parser/tests/unit/test_problem_units.py), [flatten tests](../../document-parser/tests/unit/accessibility/test_flattening.py) |
| M11 math meaning/output | [AST](../../document-parser/src/document_parser/math/latex_ast.py), [speech](../../document-parser/src/document_parser/accessibility/speech/math_rules.py), [math braille](../../document-parser/src/document_parser/accessibility/braille/math_translator.py), [encoding](../../document-parser/src/document_parser/accessibility/braille/cell_encoding.py) | [AST tests](../../document-parser/tests/unit/test_latex_ast.py), [speech tests](../../document-parser/tests/unit/accessibility/test_speech_rules.py) |
| M12 READY assembler | [assembler](../../document-parser/src/document_parser/server/s1_assembler.py), [services](../../document-parser/src/document_parser/server/s1_services.py) | [finalize tests](../../document-parser/tests/unit/test_server_s1_finalize.py) |
| M13 reading/cursor | [S0 services](../../document-parser/src/document_parser/server/s0_services.py), [session](../../document-parser/src/document_parser/server/session.py) | [S0 tests](../../document-parser/tests/unit/test_server_s0.py) |
| M14 navigation/window | [speech controller](../../document-parser/src/document_parser/accessibility/application/speech_controller.py), [document navigator](../../document-parser/src/document_parser/accessibility/application/document_navigator.py), [viewport](../../document-parser/src/document_parser/accessibility/braille/viewport.py), [table buffer](../../document-parser/src/document_parser/accessibility/braille/table_formatter.py) | [controller tests](../../document-parser/tests/unit/accessibility/test_speech_controller.py) |
| M15 audio lifecycle | [controller](../../device-runtime/src/asl_device/reading_audio.py), [fetch/native player](../../device-runtime/src/asl_device/adapters/reading_audio.py) | [lifecycle tests](../../device-runtime/tests/unit/test_h123_audio_lifecycle.py), [resource tests](../../device-runtime/tests/unit/test_reading_audio_adapters.py) |
| M16 serial contract | [host serial](../../device-runtime/src/asl_device/adapters/stm_serial.py) | [serial tests](../../device-runtime/tests/unit/test_stm_serial.py) |
| M17 firmware/RX/PCA | [main.c](../../hardware/stm32/kitel2026final/Core/Src/main.c), [IRQ](../../hardware/stm32/kitel2026final/Core/Src/stm32f4xx_it.c) | physical evidence는 H2/H3/후속 run manifest 별도. host fake serial tests로 대체 금지 |

## Evidence limitations와 작성 금지 주장

| 항목 | 최종 문서가 사용할 수 있는 범위 | 남겨야 하는 한계 |
|---|---|---|
| 현재 baseline | Desktop tracked source hash+actual entrypoint 추적 | live Laptop/Pi import를 이번에 재확인하지 않음 |
| fresh H1 | 두 receipt/four fragments/READY 및 제한된 reading/restart 관측 | orientation/장기대기와 로그 인코딩/exit 공백 유지; H4 아님 |
| H2/H3/H3-R | 해당 harness가 실제 통과한 subsystem만 | console/script/direct serial/disabled TTS/FRAME suppression 차이. NAV,D,S,2는 V2 SHORT이고 V3 A/R가 아님 |
| 알고리즘 tests | fixture/fake boundary의 기대 contract 설명 | 이번 pass에서 테스트 실행하지 않음. 새로운 regression PASS claim 없음 |
| physical cells/buttons | firmware 현재 mapping 의미와 과거 관측을 분리 | 하드웨어팀 정렬/GPIO 복구 중; 현재 physical integration acceptance 없음 |
| Pi4 | Device host 역할 이식 계획(AUX 유선 이어폰, Bluetooth HC05) | 설치/성능/serial/audio 동작 미검증; 마감용 문서에서 완료형으로 쓰지 않음 |

## Quality-question coverage — 최종 문서 작성 시 사용할 체크맵

| 사용자 품질 질문 | 답을 제공할 절 | 필수 근거 |
|---|---|---|
| 1 어떤 문제를 해결하는가 | §1/2 | PASS0 Scope, I02 |
| 2 입력부터 출력까지 어떤 단계인가 | §3/5/7 | W01–W20, D01–D15, X01 |
| 3 결과를 결정하는 알고리즘은 무엇인가 | §4.1–4.8 | A01–A11, internal mask/table detail |
| 4 중요한 판단/분기는 어디인가 | §4/6 | J01–J17, G03 |
| 5 데이터는 어떤 형태로 바뀌는가 | §5/7 | D01–D15, I01, G04 |
| 6 무엇이 실패하고 어떻게 처리되는가 | §8 및 각4.x의 실패 경계 | F01–F28, I02/I03 |
| 7 개념은 코드 어디에 있는가 | §9 및 각 절 말미 source anchor | M01–M17, baseline.json |

## PASS4 완료 조건과 다음 경계

- 9개 conceptual section 및 4.1–4.8마다 Purpose / Reader understanding / Facts / Diagrams / Previous-pass evidence / Exclusions 정의 완료.
- source 디렉터리 순서가 설명 순서를 결정하지 않음; model/OCR/geometry/state/reliability를 주요 설명 단위로 선택.
- 필수 Mermaid 4개와 선택 도식1개의 내용·금지 연결 정의; 최종 도식/prose는 아직 생성하지 않음.
- 미확정 원인·미검증 하드웨어/Pi 항목을 blueprint 내부에 명시. 외부 측정 없이 사실로 채울 빈칸 없음.
- 후속 PASS5는 이 blueprint를 입력으로 최종 문서를 작성하고, PASS6는 **그 문서가 존재한 뒤** sentence/diagram 검증보고서를 먼저 작성해야 함. 이번 요청 범위는 여기서 종료.
