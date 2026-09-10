# PASS 2 — Core Algorithm & Decision Analysis

상태: COMPLETE. 입력: [PASS1 W01–W20](PASS_1_EXECUTION_RECONSTRUCTION.md), PASS0 Q2/Q3/Q4. 이 문서는 알고리즘 분석 기록이다. 최종 Technical Overview의 설명문이나 blueprint는 아직 작성하지 않는다.

코드 root 약어 DEV/SC/DP/FW는 PASS1과 같다. 아래 source는 해당 root의 상대 경로와 symbol이다. 숫자는 코드 기본값인지 run override인지 구분한다. 이 분석에서 threshold, timeout, protocol, calibration을 변경하지 않았다.

## 1. 단계 분류

| PASS1 단계 | 주 분류 | 상세 분석 / 설명 비중 |
|---|---|---|
| W01 구성 | Infrastructure / Plumbing | 실제 backend·config·owner 선택만 설명; 모든 constructor 생략 |
| W02 입력·W03 mode/catalog | Decision Logic | A01: physical event와 command, hold/release·mode 분기 |
| W04 acquisition | Supporting Processing | source decode/rotation은 A02 입력 전제; 오류는 PASS3 |
| W05 candidate | Core Algorithm + Decision Logic | A02: hard gate, stability, ranking |
| W06 identity·W11 page-change | Core Algorithm + Decision Logic | A03/A04: raw pair bank, hysteresis와 재촬영 허가 |
| W07 split/unwarp | Core Algorithm | A05: seam 경로·보수적 crop·sampling grid |
| W08 artifact·W09 outbox·W10 receipt | Decision Logic + Infrastructure | A06: durable ownership, idempotency; 파일 writer 상세는 축약 |
| W12 OCR/IR/flatten | Core Algorithm | A07/A08: model block→구조→수식 의미/접근성 |
| W13 cutoff·W14 publish | Decision Logic + Supporting Processing | A06: completeness gate, A09: utterance/audio 생성 |
| W15 restore·W16 navigation | Core Algorithm + Decision Logic | A09: cursor, table, 수식 window |
| W17 audio | Decision Logic + Infrastructure | A10: generation/epoch 권한, cancellation |
| W18 serial·W19 PCA | Decision Logic + Supporting Processing | A11: input acceptance, latest output, validated logical→actuator mapping |
| W20 lifecycle | Infrastructure + Decision Logic | A01/A10/A11에 연결; failure/termination은 PASS3 |

## 2. 핵심 분석 카드

### A01 — 입력 의미와 상태 변경 권한

- **문제 / 필요:** 느린 처리 중 들어온 physical DOWN release가 유실되면 손을 뗀 뒤에도 탐색할 수 있음. 물리 edge, 반복 command, server navigation을 구분해야 함.
- **입력 / 사용 정보:** DeviceInputEvent(control, action, event_id, monotonic time), mode, catalog/capture/reading phase, active DOWN와 release watermark.
- **아이디어 / 과정:** serial 수신은 별도 worker; application이 입력을 drain하여 Coordinator를 순차 호출. DOWN ACTIVATED는 즉시 SHORT 1개와 hold timer를 만들고 RELEASED는 timer 취소. 늦게 도착한 activation이 이미 처리한 release보다 과거여도 최초 1회 command는 보존하되 hold를 재시작하지 않음. 다른 조작은 hold를 취소. 반복 due는 한번에 최대 1개이며 놓친 tick을 몰아서 따라잡지 않음.
- **판단:** physical input을 먼저 drain한 다음 여유 시 repeat; lever ACTIVATED/RELEASED는 capture/reading. CONFIRM LONG은 scanning에서 cutoff/flush, reading에서 selection 복귀. server의 DOWN LONG을 자동 연속읽기로 해석하지 않음.
- **출력 / 다음:** 단일 순서의 capture 또는 S0 command → A02/A09. ACK는 application 실행 완료 전 나올 수 있음.
- **구현:** DEV/application.py:step/_handle_command; hold_repeat.py:apply_edge/due; coordinator.py:handle_input.
- **테스트 근거:** DEV tests/unit/test_application.py, integration/test_stm_mode_contract.py; DP tests/unit/accessibility/test_speech_controller.py:test_down_long_is_not_continuous_reading. fake/command tests는 실제 GPIO를 증명하지 않음.

### A02 — 촬영 가능한 프레임 판정과 선택

- **문제 / 필요:** 양쪽 책장이 화면에 있어도 가림·움직임·잘림·노출 때문에 downstream 처리가 달라짐. 먼저 부적격을 제외하고 안정한 순간을 고름.
- **입력 / 정보:** full BGR FrameSample, 축소 preview/masks, 최근 bounded window, CandidatePolicy.
- **아이디어:** 양쪽 ROI의 contrast/spatial mask 및 seam proxy, 노출/가림 지표를 계산. 물리 frame의 page mask/원본 reference는 유지하면서 저해상도 preview로 반복 판단.
- **과정:** page pair 부재·가림·설정된 hard gate 등을 retry_reasons로 분류 → 최근 표본의 frame identity·적격성 확인 → 인접 mask IoU, centroid/area/seam 이동, 광량 정규화·정렬 후 motion/connected motion 비교 → 모두 안정할 때 best 선택.
- **판단:** stability는 여러 조건의 AND. 순위는 **lexicographic max**: physical margin → mask confidence → 낮은 white/black clipping 합 → 낮은 illumination range → Tenengrad → Laplacian → 최신 시간. 가중합도, 선명도 단독 선택도 아님. outer frame contact/content clipping은 config에 따라 경고 또는 hard gate이며 늘 reject하는 것이 아님.
- **출력 / 다음:** selected full frame와 quality diagnostics → A03. 불안정하면 재관측+guidance. 같은 frame ID 반복은 새 안정 표본으로 간주하지 않음.
- **구현:** SC/video/candidate.py:OpenCVCandidateAnalyzer/StableWindowAssessor/select_best/_compare; config.py:CandidatePolicy; engine.py:poll.
- **테스트 근거:** SC tests/unit/video/test_candidate.py의 exposure normalization, duplicate_frame_id, hard_gate_before_sharpness, margin_before_sharpness, bounded_window 사례. 합성 영상 test로 실물 framing 일반화를 주장할 수 없음.

### A03 — 같은 spread인지 판단하는 M1 raw pair bank

- **문제 / 필요:** 반복 camera frame을 중복 촬영하지 않되, OCR 한 번의 오인식을 새 spread로 확정하지 않아야 함.
- **입력 / 정보:** native preview footer ROI, hash-pinned local Paddle `en_PP-OCRv5_mobile_rec`, L/R raw text 쌍, frame ID, 최근 receipt-confirmed reference banks.
- **과정:** mask/side 기준 하단 ROI → 바깥쪽부터 정렬된 glyph 후보 region 최대 4개 → 원본/CLAHE crop 각각 recognition → 숫자 길이 filtering 및 variant count/score로 region 내부 선택 → 첫 유효 outer region. 모델 다운로드를 전제로 하지 않고 composition에서 assets 검증.
- **중요 경계:** provider는 normalized page label에 confidence/variant gate를 적용하지만 `token_pair_from_page_observation`은 **양쪽 nonempty raw_text**를 사용한다. provider의 OBSERVED/CONFLICT 또는 normalized label을 raw bank의 수락 조건으로 재사용하지 않는다. confidence 0.62를 M1 SAME/DIFFERENT threshold라고 설명하면 틀림. backend 내부 숫자 filtering과 raw bank의 exact equality는 별개.
- **핵심 판단:** query raw `(L,R)` 전체가 reference bank의 pair 중 하나와 exact match하면 count 증가. 현재 default N=5, Ksame=1: 한 쌍 일치만으로 SAME early exit. DIFFERENT는 유효 N개 이상, 모든 reference match count≤Kdifferent(기본0), query dominant pair가 과반(N//2+1)이어야 함. 첫 spread도 reference만 없을 뿐 query N/과반은 필요. 한쪽만 같아서는 SAME이 아님.
- **시간 / 누락:** missing은 유효 표본을 늘리지 않음. 서로 다른 frame을 요구하고 query/reference frame 중복은 오류. max collection 도달은 UNKNOWN이지 DIFFERENT가 아님. collector count가 N에 도달했다고 언제나 완료하는 것은 아님.
- **출력 / 다음:** SAME→duplicate 대기; DIFFERENT→A05 preparation; UNKNOWN→다시 관측/해당 window 재시작. pending bank는 artifact 준비만으로 accepted가 되지 않고 receipt 이후 승격.
- **구현:** SC/video/composition.py:compose_m1_page_number_provider; page_number_provider.py:_observe_roi; page_number_recognizer.py:PaddleRoiDigitRecognizer; opaque_identity.py:token_pair_from_page_observation/OpaqueQueryCollector/OpaqueIdentityLedger; engine.py:_poll_opaque_identity.
- **테스트 근거:** SC tests/unit/video/test_opaque_identity.py: missing_does_not_consume, first_pair_match, n_valid_all_mismatches_with_query_majority, timeout/frame_overlap, ack_only_transition. raw bank의 단위검증은 현재 교재 OCR 정확도나 Laptop 처리속도 검증이 아님.

### A04 — receipt 이후 page-change 재무장

- **문제 / 필요:** OCR 문자열이 흔들렸다는 이유만으로 같은 spread를 다시 보내거나, 시각 변화가 약한 다음 spread를 영구 보류하면 안 됨.
- **입력 / 정보:** accepted spread reference, preview L/R fingerprint(pHash, ink projections, ORB), A03 raw decision, visual latch.
- **아이디어 / 과정:** L/R 각각 Hamming·projection MAE·feature match로 same/different/ambiguous 구분. 양쪽 변화가 충분하고 새 후보끼리는 유사한 preview가 K회 안정하면 hysteresis changed를 latch. 가림/부적격 관측은 stability를 끊음. motion_seen은 관측 정보이며 이 코드에서 손 검출 자체가 필수 통과 조건은 아님.
- **최종 판단:** raw DIFFERENT **AND** (latched visual change **OR** coherent numeric difference). numeric corroboration은 query dominant pair와 reference dominant pair 각각 ASCII 숫자 1..9999이며 한 쌍 내부 차이의 절대값이 1이고 두 쌍이 다른지 검사. 정확히 +2 순서, 특정 짝홀 배치, 다음 번호 강제 규칙은 아님. raw SAME이면 예전 visual latch를 지우고 현 preview로 rearm; 이전 변화의 잔여 latch를 다음 판단에 빌려쓰지 않음.
- **출력 / 다음:** gate 해제→SEARCHING으로 돌아가 A02/A03을 거쳐 새 artifact. gate 해제 그 자체가 촬영이나 receipt 아님. DIFFERENT여도 corroboration 미충족이면 계속 대기 가능.
- **구현:** SC/video/page_change.py:HysteresisPageChangeGate; identity.py:compare_visual_spreads/_compare_visual; opaque_identity.py:_coherent_numeric_difference; engine.py:_poll_opaque_page_change.
- **테스트 근거:** SC tests/unit/video/test_page_change.py 및 test_opaque_identity.py의 numeric reference/query, unrelated mismatches; engine 경로 테스트는 PASS3 failure 표와 연결. 과거 H1 지연은 이런 gate·관측속도·orientation과 분리해 기록해야 하며 단일 원인 확정 근거 아님.

### A05 — 같은 순간의 L/R 보존과 곡면 보정

- **문제 / 필요:** 서로 다른 시점의 두 페이지를 결합하거나 책등 인접 내용을 임의 절단하면 spread lineage가 깨짐. 곡면 이미지는 OCR 입력으로 정돈해야 함.
- **입력 / 정보:** A02가 고른 하나의 full-resolution H×W×3 uint8 BGR, 좌우 mask, seam policy, UVDoc checkpoint.
- **아이디어 / 과정:** overlap ROI를 full 좌표로 복원 → 허용 central band에서 Gaussian luminance+center prior cost → 행별 제한 이동과 penalty를 둔 dynamic programming으로 최소 누적 cost seam → confidence/범위 gate → ownership과 uncertainty band를 적용한 보수적 L/R crop. uncertain seam band는 양쪽 conservative crop에 보존될 수 있으므로 완전 비중첩이라고 설명하지 않음.
- **보정:** crop을 RGB float로 변환; 축소 model input에서 UVDoc sampling grid 추론; grid를 원 crop 크기로 확대하고 source pixel을 sample. grid finite/shape, 출력 validity 검사. model은 재사용하며 L/R 모두 성공해야 artifact 준비 성공.
- **판단:** no page/no seam/low seam confidence/잘못된 출력은 retry 또는 명시된 fatal. 기본 active seam은 LuminanceValley, mask-aware cost/fixed-centerline 클래스가 있다는 이유로 active라고 설명하지 않음. UVDoc 실패 후 원본 crop을 성공 결과로 대신 내보내지 않음. 최종 크기/aspect gate는 내용 OCR 정확성 판정이 아님.
- **출력 / 다음:** 원본·crop·corrected 이미지/해시·좌표·알고리즘 metadata를 갖는 두-page preparation → A06.
- **구현:** SC/detect/spread_extraction.py:SeamConservativeSpreadExtractor; detect/spine_seam.py:_DynamicSeamDetector/LuminanceValleySeamDetector/apply_seam_ownership; correct/uvdoc_adapter.py:unwarp_with_mode; video/spread_preparer.py:prepare/_page_readiness.
- **테스트 근거:** SC tests/unit/test_spine_seam.py, test_uvdoc_adapter.py, tests/unit/video의 spread preparation tests. 정량 seam confidence에는 metric_calibration=False가 기록되며 보편 정확도 확률이 아님.

### A06 — 전달·처리·게시를 분리하는 durable 결정

- **문제 / 필요:** 전송 재시도, process 종료, OCR 지연 중에도 같은 spread를 중복으로 책에 넣거나 불완전한 책을 READY로 보여주면 안 됨.
- **입력 / 정보:** artifact inventory와 SHA256, device/datapack/scan/sequence, outbox SQLite, V4 idempotency, fragment state, cutoff, base revision.
- **과정:** local durable enqueue → ordered upload claim → 서버 staging/hash/fsync/promote → S1 transaction handoff → valid receipt → local ack commit. OCR은 receipt 이후 독립 worker. CONFIRM LONG은 cutoff 고정/freeze→cutoff까지 ack flush→seal. 새 페이지는 sequence와 L/R 순서로, append면 기존 revision 페이지 뒤에 결합.
- **판단:** 요청 identity 재사용 시 payload 동일성 필요; content mismatch는 conflict. receipt는 parser 성공을 요구하지 않음. READY는 cutoff에 필요한 fragment 전체 ready 및 조립물 schema/order/audio inventory/hash validation을 요구. 새 draft cutoff0와 기존 revision append cutoff0의 결과는 다름(오류 대 no-op).
- **출력 / 다음:** receipt→A04; validated immutable revision→A09. assembly/TTS 실패는 이미 READY인 이전 revision을 대체하지 않음. 세부 failure/재시도는 PASS3.
- **구현:** DEV/delivery.py/delivery_store.py; DP/server/v4_upload.py; s1_services.py:_finalize_readiness/_assemble_and_publish/_publish_revision; s1_assembler.py:assemble/validate.
- **테스트 근거:** DP tests/unit/test_server_v4_upload.py, test_server_s1_ingest.py, test_server_s1_finalize.py의 L/R order, append preservation, cutoff0, TTS failure, crash-after-promotion, audio-tamper. fake parser/TTS 테스트는 실제 모델 결과 품질을 보장하지 않음.

### A07 — OCR block을 읽을 구조로 변환

- **문제 / 필요:** mixed Korean/math, 표, 그림, 문제 보기의 raw 문자열만으로 일관된 reading focus를 만들 수 없음.
- **입력 / 정보:** corrected page 이미지 → PaddleOCR-VL raw `parsing_res_list`, block_label/content/bbox/order. 로컬 footer recognizer와 다른 모델/책임.
- **과정:** server adapter가 구조화 모델 호출(use_ocr_for_image_block=True 기본) → 유효 bbox block만 IR화 → unindexed header, block_order가 있는 본문, 나머지 unordered, unindexed footer 순 → TEXT는 raw 보존+deterministic OCR correction+inline math spans; FORMULA는 LaTex AST; TABLE은 HTML grid/cells; visual은 unsupported로 표시하고 제공된 embedded text만 보존.
- **판단:** 명백한 1행5열/순서①–⑤/각 cell plain text인 표만 answer-choice TEXT로 재분류. 그 외 표는 table 유지. 표 structure_confidence<0.8이면 issue 기록. 변환 base confidence=1.0은 코드 대입값이지 모델 OCR 정확도 측정값이 아님. invalid bbox는 block skip; source가 애초 누락한 문자 복원 보장 없음.
- **문제 묶음:** code/exam-source regex를 시작점으로 scope 설정 → 성공한 scope만 multiline split → stem/condition/bogi/choices role 분류. 연속 choice-marker run을 모으며, choice 또는 short-answer 종료 근거+stem 없으면 묶지 않음. member node를 보존하며 primary reading_order를 PROBLEM_UNIT으로 바꿈.
- **출력 / 다음:** validated Page IR → A08 flatten. unsupported visual은 그래프 의미를 추론해 주는 기능 아님.
- **구현:** DP/ocr/paddleocr_vl_adapter.py:parse_page; serialization/vl_page_ir.py:build_page_ir_from_vl_result/node_from_block/single_row_choice_text; structure/problem_units.py:detect_problem_units_in_page/classify_problem_scope; server/s1_parser.py:parse.
- **테스트 근거:** DP tests/unit/test_problem_units.py, test_server_s1_ingest.py 및 VL serialization tests. 현행 TABLE 구현과 모듈 상단의 오래된 table 미지원 설명은 다르므로 실행 branch를 근거로 사용.

### A08 — 수식 구조와 접근성 projection

- **문제 / 필요:** 수식을 일반 문자열처럼 읽으면 분수·첨자·관계의 구조가 사라짐. 잘못 파싱한 내용을 확실한 점자로 보여주면 안 됨.
- **입력 / 정보:** display/inline LaTex, raw formula, node issues, parser가 지원하는 token/grammar; 표와 problem member 구조.
- **아이디어 / 과정:** tokenizer→관계/덧셈/곱셈/분수/단항/첨자/원자 순 recursive parser → presentation AST(수식 계산/풀이 아님). 모르는 token/command는 Unknown+raw 보존; unconsumed/error를 수집. flattener는 reading_order를 따라 visited set으로 member를 중복 읽지 않게 하고 PROBLEM_UNIT을 역할 순 focus로 펼침. TABLE/visual의 내용은 nested로 유지.
- **판단:** error 또는 unconsumed 있으면 INVALID; 그렇지 않고 Unknown issue면 PARTIAL; 나머지 VALID. VALID가 수학적/원문 인식 정답을 의미하지 않음. 음성 INVALID→불확실 안내만, PARTIAL→안내+지원 구조 읽기. 점자 VALID만 번역, PARTIAL/INVALID→빈 cells. VALID여도 미구현 symbol의 NotImplementedError는 가능하고 presenter가 degraded clear로 containment.
- **변환:** AST→한국어 naturalization/pronunciation→utterance와 별도로 AST→규칙 기반 dot 집합. inline lexical suffix와 answer choices의 standalone accessibility 억제로 spoken inline math와 독립 점자 span 목록이 항상 같지는 않음. 일반 text 전체를 한글 점자로 번역하는 경로로 설명 금지.
- **출력 / 다음:** AccessibleDocument page/focus/spans/ast_status, spoken strings와 logical cell buffers → A09.
- **구현:** DP/math/latex_ast.py:parse_latex_to_ast/validate_ast; accessibility/flattening/structure_nodes.py:classify_ast_status/flatten_page; accessibility/speech/math_rules.py; accessibility/naturalization; accessibility/braille/math_translator.py/cell_encoding.py.
- **테스트 근거:** DP tests/unit/test_latex_ast.py, tests/unit/accessibility/test_speech_rules.py, test_math_notation_coverage_fixture.py, test_speech_controller.py:test_braille_renderer_exception_clears_only_display_and_keeps_speech. fixture coverage는 모든 수학 표기 지원 주장이 아님.

### A09 — focus 탐색, 수식 window, utterance 선택

- **문제 / 필요:** 긴 문서·수식을 버튼과 10-cell 창으로 읽되, 문서 이동과 창 이동의 의미를 보존해야 함.
- **입력 / 정보:** immutable AccessibleDocument, state(page/node/mode/table row-column/span/offset/generation), command, viewport_size.
- **과정 / 분기:** UP/DOWN SHORT는 focus 이동, 페이지 경계를 넘으면 인접 페이지로 이어짐. PAGE_NEXT/PREV는 해당 페이지 첫 항목으로 jump하며 TABLE mode 해제. TABLE의 RIGHT SHORT는 진입, 내부 SHORT 방향키는 cell 이동, UP LONG은 탈출. DOCUMENT LEFT/RIGHT SHORT는 현 수식 span의 whole-window 이동, 끝에서 같은 focus의 인접 span으로 이동; 인접 text block으로 넘어가지 않음. TABLE LEFT/RIGHT LONG은 cell 내 수식 window.
- **판단:** page/focus 변경은 offset/span reset; 경계여도 generation을 갱신할 수 있음. CONFIRM SHORT는 동일 focus를 새 generation으로 재생. 순수 window 이동은 silent, 다른 inline span으로 넘어가면 그 수식만 발화. no span/짧은 span/처음·끝에서는 offset0이 정상 가능. audio 완료 callback은 focus 이동 권한이 없음.
- **결과 생성:** 미리 열거한 utterance key와 text를 Piper WAV/index에 연결; append cache는 같은 key+같은 text만 재사용. runtime S0는 해당 utterance resource를 opaque audio_ref로 노출하고 state/command receipt를 저장. snapshot의 audio는 그 generation에 speech가 생성됐을 때만 있음.
- **점자 창:** dot1..6→bit0..5 integer, 길이가 긴 buffer에서 viewport_size 단위 slice. 일반 text는 clear. host에서 10개로 truncate/pad하여 wire 형식 생성.
- **scope 제약:** 위 plain-text clear는 DOCUMENT focus 정책. TABLE cell은 열 번호→행 번호→값 buffer를 만들며 text는 지원된 문자 translator를 사용할 수 있다. math cell은 현재 Number/Operator/Identifier leaf AST만 허용하며 구조적 수식은 NotImplementedError→degraded clear 가능. TABLE LONG scroll 기능이 있다는 이유로 임의의 긴 구조적 수식 번역까지 지원한다고 쓰지 않음(`accessibility/braille/table_formatter.py`).
- **설정 경계:** 10-cell은 이 hardware 시연의 계약. 독립 BraillePresenter default20, DeviceApplicationConfig default viewport40이며 stm_serial 구성은 viewport_size==cell_count를 요구한다(cell_count 기본10). S0 open_reading이 실제 viewport_size를 전달받아 presenter에 주입하므로 모든 entrypoint의 기본값이10인 것은 아님.
- **출력 / 다음:** 같은 state authority의 spoken_text/audio_ref/braille cells → A10/A11; persisted progress→다음 open_reading.
- **구현:** DP/accessibility/application/speech_controller.py/document_navigator.py/table_navigator.py; accessibility/braille/viewport.py; server/session.py; server/s0_services.py:open_reading/send_reading_command; server/s1_assembler.py.
- **테스트 근거:** DP tests/unit/accessibility/test_speech_controller.py의 page jump/table exit, replay generation, silent within-span, boundary/no-math, no callback authority. physical LONG/SHORT 검증은 별도.

### A10 — 음성의 generation/epoch와 native resource owner

- **문제 / 필요:** 새 focus 이후 도착한 fetch/old playback을 들려주거나 서로 다른 thread가 native stream을 동시에 닫는 일을 막아야 함.
- **입력 / 정보:** session/device scope, audio_ref, generation, priority/group, controller epoch, validated WAV/cache.
- **과정:** session/ref별 byte+entry bounded LRU → pending job priority 선택(single worker) → authenticated fetch 또는 cache → current epoch 확인 → 단일 play owner가 RawOutputStream 생성/start/완료대기/abort/close. callback은 PCM 복사와 stop/abort 신호만 담당. 다른 thread의 stop은 Event signal만 설정.
- **판단:** same active/pending dedupe_key는 합침; new reading 및 interrupt/group/priority 정책이 epoch를 올려 이전 pending/active 권한 취소. 교체 job이 runnable해지기 전에 old stop target을 확정. cancelled completion을 정상 completion으로 내보내지 않음. priority queue를 모든 안내의 무한 FIFO라고 설명하지 않음.
- **종료:** playback deadline=duration+10s; controller close는 cancel 후 worker join 30.5s, 살아 있으면 실패로 보고. join 뒤 player.close/cache clear. timeout은 OS/native thread를 강제 종료한다는 뜻 아님.
- **출력 / 다음:** software started/completed/interrupted/failed feedback. started는 stream.start 이전 emit이므로 실제 청취 증명이 아님. completed는 play 반환/현재 epoch를 확인한 software 결과이며 사용자의 실제 청취와 구분.
- **구현:** DEV/reading_audio.py:present/_submit/_run/_execute/close; adapters/reading_audio.py:SoundDeviceWavPlayer.play/stop/close.
- **테스트 근거:** DEV tests/unit/test_h123_audio_lifecycle.py의 native thread ownership, callback failure, replacement fence, join timeout; test_reading_audio.py. 실기기 PortAudio/헤드폰 증거를 단위 test로 대체 금지.

### A11 — ordered transport와 논리 점자→actuator 요청

- **문제 / 필요:** NAV와 FRAME이 동시에 오갈 때 ACK 유실·중복 command·잘린 FRAME의 일부 적용을 막아야 함.
- **입력 / 정보:** HELLO3/NAV sequence, desired snapshot version, host events queue; firmware byte ring/line buffer, 10 six-bit cells, LUT/PCA success cache.
- **과정:** host single I/O owner가 bounded read_until(size=256)와 partial-record framer 사용 → V3 handshake ACK → NAV validity/dedupe/debounce, full queue에는 BUSY(urgent DOWN release는 별도 통로) → app에 전달. output은 latest desired FRAME version을 같은 owner가 write. firmware는 IRQ ring 수신/overflow recovery → newline record → 전체 field count/range 검증 후 requested state commit → cell 두 3-bit pattern→bottom reversal→state LUT→motor/channel pulse→PCA writes.
- **판단:** NAV 재시도는 같은 seq, host duplicate 재ACK·재실행 없음; reconnect epoch를 새로 부여하고 active DOWN을 강제 release. FRAME은 event FIFO가 아닌 최신 상태 projection이라 중간 generation은 합쳐질 수 있음. firmware parser는 generation 필드 범위는 검사하지만 이전 generation보다 큰지를 거부하는 비교는 없음. 모든 actuator가 물리 적용된다는 보장은 host ordering만으로 나오지 않음.
- **적용:** 먼저 frame 전체를 validate하므로 invalid 뒷필드가 앞 cell만 적용시키지 않음. 그러나 PCA 여러 write는 원자적이지 않음. 성공한 motor만 cache 갱신; failed motor는 다음 frame 적용에서 다시 필요 상태가 됨. software의 lower/upper 또는 top/bottom 이름은 실제 설치 방향 검증 증거가 아님.
- **출력 / 다음:** host ACK=input packet acceptance; FRAME write=전달 요청; last_frame_apply_ok/last_applied_generation=bus 적용 판단; physical cell 관측 별도. native protocol FRAME에 physical acknowledgement 확장을 가정하지 않음.
- **구현:** DEV/adapters/stm_serial.py:_io_loop/_SerialLineFramer/_format_frame; FW/main.c:BluetoothUartIrqHandler/PumpBluetoothInput/ParseAndApplyFrame/ApplyBrailleFrame/Motor_SetState.
- **테스트 근거:** DEV tests/unit/test_stm_serial.py의 V3 dedupe/rehandshake/full queue/reconnect/latest-wins; firmware/serial 진단은 harness boundary와 별도. UART 통과가 기구 정렬 성공을 뜻하지 않음.

## 3. 주요 판단 inventory

| ID / 종류 | 통제하는 행동 | 현재 source 근거 / 주의 |
|---|---|---|
| J01 threshold/filter | 부적격 frame 제거, 연속 안정 표본 확보 | A02 CandidatePolicy; hard/diagnostic 설정 분리 |
| J02 ranking | 안정 후보 중 어느 full frame을 처리할지 | A02 select_best의 tuple 우선순위, 합산점수 아님 |
| J03 ranking/filter | footer에서 어느 숫자 영역을 택할지 | A03 outer position 우선, region 내부 variant count/score |
| J04 early exit | SAME을 빠르게 확정 | A03 Ksame=1, raw L/R pair exact membership |
| J05 threshold/confidence | DIFFERENT 오판 억제 | A03 N=5, Kdifferent=0, dominant pair 과반. 숫자 OCR confidence와 별개 |
| J06 timeout/retry | identity observation window를 종료하고 UNKNOWN 재수집 | SC config.py 저수준 기본 max_collection_ms=1500; runtime_composition.py:_effective_scanner_config override 가능. 과거 H1의 8초는 run 정책 값이며 모든 entrypoint의 코드 기본값이 아님. N/timeout 도달과 실제 processing interval은 별도 |
| J07 branching/hysteresis | page-change 이후 다시 capture 허가 | A04 DIFFERENT AND (visual OR numeric), SAME이면 latch rearm |
| J08 confidence/filter | seam이 crop 경계로 적합한지 | A05 accumulated cost/path confidence/allowed band; 교정된 정확도 확률 아님 |
| J09 fallback/early exit | 보정실패 이미지 업로드 방지 | A05 both sides success, UVDoc model missing/load fatal, invalid output retry |
| J10 filter/branch | VL 구조를 text/math/table/visual로 보존 | A07 labels/bbox, exact five-choice reclassification, problem scope regex |
| J11 confidence handling | 불확실 수식의 음성·점자 차별 처리 | A08 VALID/PARTIAL/INVALID; raw confidence 숫자와 혼동 금지 |
| J12 threshold/branch | viewport 이동 또는 span 전환·경계안내 | A09 total_cell_count/offset/has_next/has_previous; 10-cell은 현 hardware contract |
| J13 retry/early exit | at-least-once request의 중복 효과 억제 | A06 request hash/idempotency/command receipt; conflict는 성공 fallback 아님 |
| J14 branching | seal 이후 READY 허가 | A06 cutoff completeness + artifact/audio validation + publish |
| J15 ranking/cancellation | 어느 음성을 지금 들려줄지 | A10 priority/group/dedupe/epoch, playback callback은 navigation authority 없음 |
| J16 backpressure/retry | input queue 포화·serial reconnect | A11 BUSY/동일seq retry/epoch; latest FRAME coalescing |
| J17 permanent/fatal | 정상 실패와 앱 종료의 차이 | PASS3에서 camera/delivery/parser/audio/CLI를 분리해 상세화 |

## 4. PASS3에 전달할 확인 사항

### A02 / A07 내부 변환의 추가 근거

| 연결 | 문제 / 입력 | 처리·판단 | 출력·다음 / 한계 / 구현 |
|---|---|---|---|
| A02 page mask | 배경 속 책장 영역 선택 / side ROI pixels+allowed mask | 밝은 영역 threshold→morphological closing→external contours. 면적·높이·내부 밝기·외부 ring 대비로 filtering; contrast(0.40), edge support(0.30), height coverage(0.20), area plausibility(0.10) 가중합으로 contour 선택·min score gate | mask/confidence→candidate 안정성. **mask 내부 contour 선택은 가중합, 최종 frame 선택은 lexicographic**. black-background contrast 전제를 모든 배경으로 일반화 금지. SC/detect/contrast_spatial.py:ContrastSpatialPageSegmenter.segment |
| A02 obstruction | 화면 밖에서 들어와 책장을 가리는 성분 식별 / BGR+page masks | YCrCb·HSV 색 범위→open/close→connected component; image border contact·최소 면적·page-near overlap filtering; area/proximity 우선순위 | obstruction result→CONTENT_OCCLUDED. 일반 hand landmark/skin tone 전반 검증 주장이 아님. SC/video/obstruction.py:EdgeChromaIntrusionObstructionDetector.detect |
| A07 table grid | HTML table를 방향키 cell 좌표로 전환 / tr·td·th·rowspan·colspan | 이전 span이 점유한 좌표를 건너뛰고 cell 배치; row/column/span 저장; table bbox를 균등 분할해 cell bbox 추정; 행별 colspan 합의 직사각형 일관성으로 confidence 0.9/0.5(빈표0) | nested content nodes→table navigator; bbox_is_estimated=True, confidence는 source OCR probability 아님. DP/serialization/table_html.py:build_table_ir/structure_confidence |
| A07 correction | 알려진 OCR 변형의 한정 정규화 / raw text | 순서 있는 regex rule을 적용하고 source/replacement/count/rule_id 기록 | normalized text+issues→inline spans; raw text 유지, 일반 언어모델 자동 교정/빠진 글자 복원 아님. DP/postprocessing/ocr_dictionary.py:correct_ocr_text/correction_issues |

이 세부 근거는 PASS4 설명 단위를 확정하기 전 분석 카드에 보충한 것으로, 새 기능/알고리즘 제안이 아니다.

- 데이터 provenance: source_frame와 identity 관측 frame은 다를 수 있으나 L/R artifact는 한 selected frame에서 나와야 함.
- 신뢰 정보: raw footer pair, normalized page label, AST status, fixed confidence=1.0은 각각 다른 의미.
- 손실 경계: 후보 preview 축소, seam uncertain 중복, warp interpolation, VL omitted block/invalid bbox, AST unsupported, logical math-only braille, 10-cell slice.
- completion 분리: accepted input → local durable artifact/outbox → server receipt → READY → software audio completion/PCA success → physical observation.
- lifecycle: pull retry는 일정시간 sleep/block과 다름; controller join deadline과 실제 native termination을 분리.

Gate: W01–W20의 분류, A01–A11 분석, J01–J17 판단 inventory 완료. 다음 PASS3는 이 파일과 PASS1을 입력으로 사용한다. 아직 최종 문서 prose 작성/실행 test/하드웨어 재검증은 수행하지 않음.
