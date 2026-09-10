# PASS 6 — Verification Against Implementation

기준일: 2026-09-10. 입력은 PASS 4 blueprint로 작성한 PASS 5 완성 문서이다. 검증 시작 전에 [PASS 5 원본 사본](PASS_5_DRAFT.md.snapshot)과 [해시·완료 기록](pass5_record.json)을 보존했다. 이 보고서를 먼저 작성한 뒤 아래 Required correction을 최종 문서에 적용한다. 분석 중의 가설을 product defect로 승격하거나 product source를 수정하는 작업이 아니다.

- 기준 HEAD: `b6005f13b0283cc6cac128a5016140613b7ee1ae`.
- 검증 대상: [Technical Overview](../ASL_OCR_TECHNICAL_OVERVIEW.md)의 9개 절, 4개 Mermaid 도식, 실행 예, source/test 대응표.
- 수정 전 문서 SHA256: `237969372354743a366b4ab89704b33b0a07d4ca1b4ab9a54d1edfcd8d0819c6`.
- 이전 단계 입력: [PASS 1](PASS_1_EXECUTION_RECONSTRUCTION.md), [PASS 2](PASS_2_ALGORITHMS_AND_DECISIONS.md), [PASS 3](PASS_3_DATA_AND_FAILURES.md), [PASS 4](PASS_4_DOCUMENTATION_BLUEPRINT.md). 이전 분석 표현과 실제 구현이 다르면 실제 구현을 우선한다.

## 1. Findings — 수정 전에 확정한 내용

### V01 — Ambiguous: raw identity의 과반 기준

- **Finding:** §4.2와 §6의 ‘query 내부 과반’은 현재까지 누적한 모든 관측의 과반으로 읽힐 수 있다.
- **Evidence:** [opaque_identity.py:151](../../book-scanner/src/book_scanner/video/opaque_identity.py#L151)에서 `required_novel_consensus = query_sample_count // 2 + 1`을 사용한다. count는 N 이상이어야 하지만 N을 최대 관측 수로 제한하지 않는다. [raw identity tests](../../book-scanner/tests/unit/video/test_opaque_identity.py)는 exact-pair consensus와 early SAME을 검사한다.
- **Impact:** N을 넘긴 window의 로그나 충돌 관측을 잘못 해석할 수 있다. 이전 PASS 2/3의 축약된 ‘과반’ 표현도 이 구체적 의미로 읽어야 한다.
- **Required correction:** 설정 N 기준의 고정 consensus 수임을 명시한다. 기본 N=5에서는 같은 raw pair 최소3개와 총 유효 관측 최소5개가 각각 필요하다. reference match 조건은 그대로 유지한다.

### V02 — Oversimplified: identity timeout과 rearm의 의미

- **Finding:** §4.2는 timeout이 전체 capture deadline이 아님을 설명하지만, 진행 중 recognition을 강제로 중단하는 deadline인지와 SAME의 rearm 기준은 분명하지 않다.
- **Evidence:** [collector observe/decision](../../book-scanner/src/book_scanner/video/opaque_identity.py#L134)는 observe에서 now 없이 decision을 호출하고, `_unknown`에서만 전달된 now를 이용해 timeout을 표시한다. [engine page-change 경로](../../book-scanner/src/book_scanner/video/engine.py#L651)는 poll에서 clock을 확인하고 SAME 시 `_page_change_baseline_preview`로 rearm한다.
- **Impact:** production 8초를 processing preemption 또는 전체 촬영 시간 상한으로 해석하거나, 오래된 source_frame_id를 곧바로 새 frame 누락으로 단정할 수 있다.
- **Required correction:** polling 기반 UNKNOWN/window reset과 실행 중 작업 취소를 구별하고, SAME의 기준은 accepted spread의 보존된 baseline임을 명시한다. N·timeout·threshold는 변경하지 않는다.

### V03 — Oversimplified: sequence diagram의 parser 병렬 구간

- **Finding:** §3의 spread loop 안 `par ... end`는 매 spread마다 parser 완료를 기다린 뒤 다음 loop로 들어가는 join처럼 읽힐 수 있다.
- **Evidence:** [V4 수신](../../document-parser/src/document_parser/server/v4_upload.py), [S1 fragment worker](../../document-parser/src/document_parser/server/s1_services.py#L169), [Device delivery](../../device-runtime/src/asl_device/delivery.py). receipt는 fragment 처리 완료를 기다리는 응답이 아니며 다음 촬영과 parser 처리의 overlap이 가능하다.
- **Impact:** 다음 촬영과 OCR의 실제 독립 실행 및 seal 이후 대기 경계를 잘못 이해할 수 있다.
- **Required correction:** 수신 시 fragment 등록과 비동기 처리 가능성을 표시하고, spread마다 parser join을 그리지 않는다. cutoff 내 fragment 전체 대기는 finalize 단계에 표시한다. READY 화살표는 seal 응답의 동기 반환이 아니라 후속 status 확인을 축약한 것임도 명시한다.

### V04 — Missing: reading session 재사용과 transaction 경계

- **Finding:** §4.7은 stable progress 복구를 설명하지만 command receipt와 cursor의 동시 저장 및 OPEN session 재사용을 빠뜨렸다.
- **Evidence:** [open_reading](../../document-parser/src/document_parser/server/s0_services.py#L348)는 같은 device/datapack/revision/viewport의 OPEN session을 재사용한다. [send_reading_command](../../document-parser/src/document_parser/server/s0_services.py#L460)는 transaction-local DatapackSession에서 계산하고 progress와 receipt를 같은 transaction에 저장한다. [Coordinator catalog 복귀](../../device-runtime/src/asl_device/coordinator.py#L601)는 local reading snapshot을 비운다. [S0 테스트](../../document-parser/tests/unit/test_server_s0.py#L139)는 재시작 뒤 command replay 중복 이동 방지와 session/cursor 복구를 확인한다.
- **Impact:** ‘읽기 종료’를 서버 session 삭제로 오해하거나 응답 유실 뒤 재시도 시 중복 이동을 막는 이유를 놓칠 수 있다.
- **Required correction:** command ID의 replay/conflict, commit 이후 응답, 같은 OPEN session 재사용, local catalog 복귀의 의미를 설명한다.

### V05 — Missing: 단말 input scheduling의 동기 구간

- **Finding:** worker 소유권과 DOWN hold 설명은 있으나, DeviceApplication이 모든 input을 즉시 처리하는 구조는 아니라는 한계가 드러나지 않는다.
- **Evidence:** [application.step](../../device-runtime/src/asl_device/application.py#L70)는 input을 모아 명령을 순차 처리한 뒤 coordinator poll/presentation을 수행한다. [reading command 경로](../../device-runtime/src/asl_device/coordinator.py#L580)는 reading port 반환을 동기적으로 기다린다. missed hold tick을 몰아서 실행하지 않는 정책은 지연 자체를 없애지 않는다.
- **Impact:** serial/audio worker가 있으므로 느린 server request 중에도 application-level 명령 전이가 즉각적이라고 오해할 수 있다.
- **Required correction:** 단일 command scheduling과 동기 API의 지연 가능성을 짧게 설명한다. UI 입력 의미나 architecture 변경을 제안하는 문서로 확장하지 않는다.

### V06 — Missing: 수식 예제의 실제 중간값

- **Finding:** §7 수식 예는 추상적인 ‘분수→AST→두 출력’에 머물러 입력·중간값·결과를 직접 비교하기 어렵다.
- **Evidence:** [격리 probe](evidence/math_example.py), [실행 결과](evidence/math-example.json). 현재 source에 `\frac{1}{2}`를 넣으면 Fraction(Number1, Number2), speech rule output `2분의 1`, logical cell 정수 `[60,3,12,60,1]`을 얻는다. viewport10/offset0에서 has_next=false다.
- **Impact:** 변환과 계산, logical cell과 physical pin의 차이를 독자가 구체적으로 확인하기 어렵다.
- **Required correction:** 실제 probe 결과를 표로 넣고 순수 함수 예제임을 표시한다. OCR/Piper/native playback/STM 실험으로 주장하지 않는다. 10-cell zero padding은 host 전달 표현이며 이 probe가 host transport를 실행한 결과는 아님을 명시한다.

### V07 — Ambiguous: 완료 evidence 표의 cue와 durable 상태 병기

- **Finding:** §8.2의 `V4 receipt / spread_sent`, `datapack_saved / READY`는 앞 문단의 구분에도 불구하고 음성 관측만으로 durable 상태를 독립 검증한 것처럼 읽힐 수 있다.
- **Evidence:** [delivery receipt 검증](../../device-runtime/src/asl_device/delivery.py), [Coordinator feedback](../../device-runtime/src/asl_device/coordinator.py), [historical H1 evidence](../H1_FRESH_ALIGNED_RUN_20260908.md). 음성 요청/청취와 outbox ack·서버 revision 확인은 서로 다른 관측이다.
- **Impact:** 프로젝트가 강조한 accepted/durable/ready/audible/physical completion 분리가 흐려진다.
- **Required correction:** 유효 receipt+local ack, 서버 READY, 각 cue 요청/청취를 표의 다른 행으로 분리한다. cue는 코드상 선행 조건에 따른 안내라는 설명을 유지한다.

### V08 — Oversimplified: decision diagram의 artifact 준비 이후 성공 화살표

- **Finding:** §4.2 도식은 identity 중심이며 prepare→receipt 사이의 local retry/fatal을 생략했으나, 그 생략 범위가 표시되지 않았다.
- **Evidence:** [spread_preparer](../../book-scanner/src/book_scanner/video/spread_preparer.py), [PASS 3 F07–F13](PASS_3_DATA_AND_FAILURES.md), 문서 §4.3/§8.1의 readiness와 delivery 실패 설명.
- **Impact:** candidate DIFFERENT만 얻으면 보정·전송까지 반드시 성공한다고 읽힐 수 있다.
- **Required correction:** prepare→receipt는 성공 경로 축약이며 보정·전송 실패는 §4.3/§8.1을 따른다고 도식 바로 뒤에 명시한다. 모든 오류 분기를 identity 도식에 추가해 읽기 어렵게 만들지는 않는다.

## 2. 대조 범위와 판정

| 문서 범위 | 대조한 핵심 사실 | 결과 / 보완 |
|---|---|---|
| §1 문제·목표 | 현재 prototype, 두 spread, 독립 completion | PASS 0 scope 및 fresh H1 경계와 일치 |
| §2 구조 / G01 | 실제 composition, local footer와 server 본문, owner, Pi 계획 | 현재 Windows 경로와 목표 Pi를 분리; 신규 배포 수용 주장 없음 |
| §3 workflow / G02 | enqueue→receipt ack→Scanner accepted, seal/cutoff→READY | V03 적용 필요 |
| §4.1 | contour 가중합, frame lexicographic ranking, chroma 가림 | candidate/contrast 구현과 구별된 설명 유지 |
| §4.2 / G03 | exact pair, fixed-N consensus, visual/numeric gate, clock | V01/V02/V08 적용 필요 |
| §4.3–4.5 | seam/UVDoc, VL→IR→focus, AST trust·표 제한 | PASS 2/3와 현재 구현 대조; VALID를 OCR 정확도로 표현하지 않음 |
| §4.6 | receipt와 parser/assembly 구분, append 실패 시 이전 READY 보존 | S1 finalize tests로 fake parser/synthesizer 경로 확인 |
| §4.7 | navigation/window/mode, durable cursor·command replay | V04/V05 적용 필요 |
| §4.8 | audio owner/cancel/current completion, latest FRAME, RX/parser/PCA | source 및 fake adapter 테스트 대조. firmware는 source 검토만; flash/실측 없음 |
| §5 / G04 | frame→IR→revision→snapshot, IDs, lossy transformation | source/frame/cursor와 wire generation의 의미를 분리 |
| §6–7 | threshold/fallback/retry, historical vs synthetic examples | V01/V06 적용 필요 |
| §8 | recoverable/fatal, CLI exit, independent completion, harness 한계 | V07 적용 필요. 무처리 exception/native crash를 exit2 보장에 포함하지 않음 |
| §9 | entrypoint와 M01–M17 source/test 대응, legacy 경계 | module별 전수 해설을 피하고 개념 뒤에 연결 |

Incorrect/Unsupported/Outdated 범주도 점검했다. 위 표는 확인 범위를 말하며 repository 전수 무결성, OCR 원문 정확성 또는 외부 규정 준수 검증을 뜻하지 않는다. 별도의 신규 product defect 판정은 하지 않는다. 이전 source 주석의 SET_FRAME 명칭 등은 현재 FRAME grammar의 근거로 사용하지 않았다.

## 3. 독립 실행 기록

실행 interpreter: Desktop `D:\Projects\OCR\.venv-e0b\Scripts\python.exe`. `PYTHONPATH`는 세 package의 현재 src를 지정했다. package별 별도 process로 pytest를 실행해 동일한 `tests` package name 간섭을 피했다. `-B`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`를 사용했다.

| 실행 | 선택한 테스트 | 결과 | 원시 로그 |
|---|---|---|---|
| Scanner | candidate, opaque_identity, page_change, h123_camera_recovery | 46 passed | [scanner-pytest.txt](evidence/scanner-pytest.txt) |
| Parser | latex_ast, vl_page_ir, problem_units, flattening, speech_rules, server_s1_finalize, server_s0 | 145 passed + 3 subtests passed | [parser-pytest.txt](evidence/parser-pytest.txt) |
| Device 첫 실행 | h123_audio_lifecycle, stm_serial, h123_boundaries | 60 passed / 1 fixture error | [device-pytest.txt](evidence/device-pytest.txt) |
| Device 격리 재실행 | 같은 3개 파일; 새 C: 임시 basetemp | 61 passed | [device-pytest-isolated.txt](evidence/device-pytest-isolated.txt) |
| 수식 순수 변환 | 위 math_example.py | 예제 JSON 생성 성공 | [math-example.json](evidence/math-example.json) |

최종 선정 suite는 **252 passed + 3 subtests passed**다. Device 첫 실행의 error는 Desktop의 기존 pytest 임시 root에 대한 PermissionError였으며 product assertion 실패가 아니다. 기존 임시 폴더의 권한·내용은 수정하지 않았고 첫 로그도 보존했다. 재실행에서 임의의 새 `C:\Users\...\AppData\Local\Temp\asl-doc-pass6-*` 위치를 지정했다. 이는 Laptop D: 접근과 관계없는 Desktop 실행이다.

위 테스트는 fake camera/serial/native stream, pure transformation, 임시 저장소와 fake parser/synthesizer 기반이다. 실제 OCR model inference, Piper 음성 합성, speaker 청취, UART/PCA/servo, SSH/Laptop/Pi, production 업로드는 수행하지 않았다. 이는 문서의 source contract 검증이며 G3-A/fresh H1–H3/H4를 새로 통과한 증거가 아니다.

## 4. 후속 교정과 최종 무결성 확인

초기 보고서를 [사본](PASS_6_INITIAL_REPORT.md.snapshot)으로 보존한 뒤 V01–V08을 최종 문서에 적용했다. 초기 보고서 SHA256은 `a38ec41c7d39a8e7c61c0e5b3fa8676fa404d7e8220a27f3ac5c3c30d959c166`이다. 최종 문서 SHA256은 `8e8fc96bb4dd0da6887a32aedf77b705b4aa884af226ac3f455572d03f93cfba`이다.

| Finding | 반영 위치 | 교정 결과 |
|---|---|---|
| V01 | §4.2 / §6 | N 기준 고정 consensus와 총 관측 수 조건 분리 |
| V02 | §4.2 | clock을 통한 UNKNOWN/window reset, accepted baseline rearm, recognition 강제취소와 구분 |
| V03 | §3 G02 및 다음 문단 | spread별 parser join 제거; 독립 worker, seal 후 status 확인 표시 |
| V04 | §4.7 | transaction-local 계산→progress+receipt commit→응답, replay/conflict와 OPEN session 재사용 설명 |
| V05 | §4.7 | 순차 input scheduling과 동기 API 지연 한계 설명 |
| V06 | §7 | LaTeX→AST→발화 문자열→dot sets→정수 cells→viewport의 실제 순수 함수 결과 추가 |
| V07 | §8.2 | receipt+ack / READY / 각 안내 요청·청취를 독립 행으로 분리 |
| V08 | §4.2 G03 다음 문단 | prepare 이후 성공 경로 축약 표시, readiness/delivery 실패 설명으로 연결 |

G01은 배포 경계·API/출력 연결, G02는 실행 순서와 비동기 처리, G03은 identity 조건과 반복, G04는 데이터 변환의 방향을 다시 대조했다. Mermaid의 선언·블록·edge label과 code fence는 정적으로 검토했다. 별도 Mermaid renderer는 실행하지 않았으므로 특정 viewer의 실제 레이아웃·SVG 렌더링 성공을 검증했다고 주장하지 않는다.

최종 링크·section·source hash 결과는 [documentation-validation.json](evidence/documentation-validation.json), 검증 코드는 [validate_documentation.py](evidence/validate_documentation.py), 실행/산출물 hash 목록은 [pass56_record.json](pass56_record.json)에 보존한다. PASS0–4 기록을 덮어쓰지 않고 후속 기록을 분리했다.

## 5. 사용자 품질 질문에 대한 최종 대응

| 질문 | 최종 문서의 답 |
|---|---|
| 어떤 문제를 해결하는가? | §1 인쇄 교재를 탐색 가능한 음성·점자로 변환하는 문제와 한정된 prototype |
| 입력부터 출력까지 어떤 단계를 거치는가? | §2 구조, §3 9단계/sequence, §7 실제 H1 사례 |
| 결과를 결정하는 알고리즘은 무엇인가? | §4 quality·ranking, identity·page-change, seam/UVDoc, VL/IR/AST·접근성 변환 |
| 중요한 판단은 어디에서 발생하는가? | §4.2 decision diagram, §4.5 AST trust, §6 판단 표 |
| 데이터가 어떻게 바뀌는가? | §5 변환 도식·metadata/손실·ID, §7 구체적 수식 값 |
| 무엇이 실패하고 어떻게 처리하는가? | §8 오류 taxonomy·retry/fatal·CLI·실험 한계, §4의 local failure 설명 |
| 각 개념의 구현은 어디인가? | 각 개념 뒤 source 링크와 §9 M01–M17 source/test map |

문서화 PASS5/6은 완료다. product source/firmware 수정은 **0개**이며 247개 baseline 파일을 유지한다. fake 테스트 결과를 실기기 수용으로 확대하지 않는다. camera liveness, hardware GPIO/정렬·clear, Pi deployment 등 기존 미완료 검증은 남아 있으며 H4 또는 integration-ready를 선언하지 않는다.
