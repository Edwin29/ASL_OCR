# PASS 3 — Data Flow & Failure Analysis

상태: COMPLETE. 입력: [PASS1 W01–W20](PASS_1_EXECUTION_RECONSTRUCTION.md), [PASS2 A01–A11/J01–J17](PASS_2_ALGORITHMS_AND_DECISIONS.md). 정상 변환과 실패 경로를 분리한 분석 산출물. 최종 prose나 PASS4 목차는 아직 작성하지 않음.

DEV/SC/DP/FW code root는 PASS1 정의를 사용한다. 여기서 invariant는 다음 단계가 기대하는 조건이지 모든 실기기에서 이미 입증됐다는 표시가 아니다.

## 1. 정상 데이터 변환

| ID / 단계 | 입력 형태·의미 | 출력 형태·의미 | 추가 정보 / metadata | 제거·손실·범위 축소 | 다음 단계 invariant / 구현 |
|---|---|---|---|---|---|
| D01 W02 | GPIO 안정 상태 또는 console command | NAV→DeviceInputEvent→semantic command | control/action/seq, host boot·connection epoch·event_id/time, hold command suffix | GPIO 전압/배선/실제 압력은 host event에 없음. console은 physical·ACK 경계가 없음 | command 의미와 dedupe identity 유지; A01/A11, DEV/hold_repeat.py/adapters/stm_serial.py |
| D02 W04 | authenticated camera JPEG bytes | decoded BGR full FrameSample | unique frame ID, monotonic capture timestamp, raw/effective width-height·rotation | JPEG가 이미 담지 못한 정보 복원 불가; rotate/mirror는 좌표 변경, configured crop은 영역 제거. 원본 HTTP 응답 byte와 source_frame.jpg는 동일 byte 아님 | 유효 uint8 color/min size; strict source와 orientation 구분; SC/video/sources.py:HttpSnapshotCameraSource |
| D03 W05 | full FrameSample | CandidateObservation+selected original reference | 축소 gray/mask, page centroid/area, seam proxy, quality/retry reasons | preview 축소로 미세 정보 손실; latest-frame worker는 중간 frame을 건너뜀. 원본 selected payload reference는 별도 유지 | stability는 서로 다른 frame; full frame을 downstream 사용; SC/video/candidate.py/operator_preview.py |
| D04 W06/W11 | footer ROI pixels+recognizer 결과 | PageNumberObservation→OpaqueFooterTokenPair→query/reference bank→SAME/DIFFERENT/UNKNOWN | raw/normalized label, ROI SHA, backend/preprocess version, frame ID, match/consensus count, accepted receipt lineage | M1 raw bank는 confidence/status/normalized label을 decision gate로 쓰지 않음. 숫자는 page index나 문서 순서로 자동 승격되지 않음 | nonempty L/R raw pair, query/reference frame 분리, accepted는 receipt 이후; SC/video/opaque_identity.py/page_number_provider.py |
| D05 W07 | selected full frame+full 좌표 L/R mask | conservative crop·mask·UVDoc corrected image | crop bbox, seam path/uncertainty, input-output dimensions, runtime/model metadata | uncertainty band가 양쪽에 중복 보존 가능; crop 바깥은 제거, warp interpolation과 JPEG 재인코딩은 비가역 | L/R는 **같은 selected frame**; identity 수집에 사용한 모든 frame과 같을 필요는 없음; SC/video/spread_preparer.py:_write_bundle |
| D06 W08/W09 | staging source_frame.jpg, left/right mask.png·crop.jpg·uvdoc.jpg·diagnostics.json | immutable artifact manifest/ref→PreparedDelivery+durable outbox row | 파일 inventory/hash/size/MIME, manifest SHA, artifact/spread/source/datapack/scan IDs, sequence, attempt/status | wire에는 in-memory numpy/worker state 없음. 정상 product lifecycle에서 local ack 뒤 local bundle cleanup 가능; 조사 evidence 보존 정책과 구분 | manifest/file 일치·path confinement·single lineage; SC/video/artifacts.py, DEV/delivery.py/delivery_store.py |
| D07 W10 | multipart metadata+manifest+inventory/files | received bundle+V4 receipt+L/R page_fragment rows | server receipt_id/accepted_at, upload idempotency/digest, server page_id, storage-relative path, lease/status | receipt에는 OCR text와 READY 보장 없음 | durable promotion+S1 acceptance 후 receipt; 서버 page_id는 printed page label과 다름; DP/server/v4_upload.py/s1_services.py |
| D08 W12 | corrected page image | PaddleOCR-VL structured blocks | labels/bboxes/order/content(텍스트·LaTex·HTML 등), engine provenance | visual raster→model output에서 누락/오인식 가능. model이 반환하지 않은 글자는 후단 schema validation으로 복구 불가 | parsing_res_list 구조; empty 결과는 accessible page gate에서 거절; DP/ocr/paddleocr_vl_adapter.py |
| D09 W12 | raw VL blocks | Page IR nodes+reading_order+problem unit+parse issues | raw_text와 normalized_text, bbox/normalized_bbox, AST/unconsumed, table cells/confidence, role/member IDs | invalid bbox block skip; reading_order 재정렬; 성공한 problem scope의 multiline block은 line nodes로 대체. 원문 시각 배치 전체를 보존하는 포맷은 아님 | schema-valid Page IR; confidence=1.0은 converter 상수이며 OCR 확신도 아님; DP/serialization/vl_page_ir.py/structure/problem_units.py/server/s1_parser.py |
| D10 W12 | validated Page IR | AccessiblePage focus_items/spans/nested table·visual content | source node IDs/problem_id, kind, ast_status, raw_formula/AST, issues, standalone_accessibility | top-level structure node를 member focus로 펼침; visited로 중복 제외. geometry 중심 구조를 탐색 중심 구조로 축약 | preserved readable content를 중복 focus로 읽지 않음; table/visual children은 nested; DP/accessibility/flattening/structure_nodes.py |
| D11 W14 | ordered ready AccessiblePages+optional immutable base | revision document.json+audio_index.json+manifest.json+WAV | global_reading_order, revision/base/cutoff/scan lineage, engine/TTS manifests, audio SHA and text keys | runtime revision은 모든 raw scan/IR를 inline 포함하지 않음(별도 received/fragments lineage). text normalization과 음성 발음은 raw text와 다름 | base+new order, exact utterance coverage/text/hash, validation 후 publish; DP/server/s1_assembler.py |
| D12 W15/W16 | READY revision+device/datapack persistent cursor+command | NavigationState→ReadingSnapshot | reading_session_id, generation, stable page/focus anchors, indices, mode/table/span/offset, source/spoken text, opaque audio_ref | 한 snapshot은 한 focus/window만 표현; 전체 문서를 매번 전송하지 않음. audio_ref는 경로/WAV가 아님 | command receipt+progress transaction; session revision 고정; 같은 device/datapack restore; DP/server/s0_services.py/session.py |
| D13 W17 | authenticated opaque audio_ref 또는 system ref | fetched/validated WAV→PCM→native output | scope/cache key, SHA, MIME/bytes/duration, epoch/generation feedback | PCM에는 source node/문자 정보 없음; 음성으로 원문 수식 모양 완전 복원 불가. stale fetch/play는 출력 권한 취소 | current job/epoch만 정상 completed; emit started는 실제 청취 전일 수 있음; DEV/reading_audio.py/adapters/reading_audio.py |
| D14 W16/W18 | VALID math AST | dot 집합 logical buffer→10-cell viewport→FRAME | each cell dot1..6→bit0..5(0..63), page/node/span/offset/gen, host desired version | plain text/불확실 AST는 빈 cells; window 밖 cells는 이번 FRAME에 없음. FRAME에 datapack/session/physical measured state 없음 | host padding으로 정확히 10 cells, newline/field grammar; DP/accessibility/braille, DEV/adapters/stm_serial.py |
| D15 W19 | 완전히 검증된 FRAME의 10 cells | 두 3-bit pattern/cell→reversal/LUT→20 motor desired states→PCA pulse writes | nav requested generation, motor success cache, last_frame_apply_ok/last_applied_generation, error counters | logical dots에서 기구 위치로의 변환은 calibration/배선에 의존; 현재 물리 pin 높이 피드백은 없음 | 전체 parse validation은 atomic, 여러 PCA write는 atomic 아님; FW/main.c:ParseAndApplyFrame/ApplyBrailleFrame/Motor_SetState |

정상 데이터 연결: D01의 command → D02–D07 반복 수집 → D08–D10 fragment 처리 → D01의 LONG cutoff → D11 게시 → D12 탐색 → D13 음성 / D14–D15 점자. D07 receipt와 D08–D10 parser 작업은 서로 다른 완료 시점이다.

## 2. ID·시간·완료의 의미

### I01 — 서로 대체하지 못하는 identity

| identity | owner / 용도 | 혼동하면 안 되는 것 |
|---|---|---|
| device_id | 지속적인 사용자 장치 progress key | process boot ID나 COM 번호 아님; Pi 계획에서 변경 여부를 자동 결정하지 않음 |
| event/command ID, hardware sequence | input dedupe·idempotency; host boot/connection epoch로 범위 구분 | navigation generation과 다름 |
| scan_session_id+sequence | 한 scan의 spread 순서·seal cutoff | printed page 26/27 등의 번호 아님 |
| source_frame_id / artifact_id / spread_id | acquisition·immutable artifact lineage | footer query 관측 frame ID와 selected frame ID가 무조건 같다는 뜻 아님 |
| receipt_id | server durable acceptance | parser-ready 또는 fresh revision이 아님 |
| datapack_id+revision+page/focus anchors | 읽을 내용 및 progress 복구 | 파일명만으로 같은 revision을 주장하지 않음 |
| generation | reading state 변경·replay 권한 | firmware가 수신 generation 단조증가를 자체 강제한다고 가정하지 않음 |
| audio epoch / desired FRAME version | host job cancellation / latest projection | server generation을 대체하는 globally persistent counter 아님 |

### I02 — completion ladder

| 단계 | 증거가 말하는 것 | 말하지 못하는 것 |
|---|---|---|
| STM발 NAV에 대한 host ACK,seq | input packet 수락/중복 ACK 정책 | Coordinator command 완료·cell 움직임 |
| local artifact/outbox durable | 전송할 파일/요청 책임 보존 | 서버가 받음 |
| V4 receipt + local acked | 동일 artifact 서버 durable acceptance | OCR 완료·READY |
| S1 fragment READY | 그 page의 parse/flatten 결과 저장 | cutoff 전체 완성·TTS 생성 |
| immutable revision READY | 읽기 artifact/audio inventory validation와 publication | OCR 내용이 원문과 모두 동일함·스피커 청취·physical braille |
| reading_audio_playback_completed | current job의 play 반환 성공 | 사람의 청취·모든 환경의 장치 음량/출력 route 검증 |
| FRAME write | host가 serial write를 완료 | MCU parser/PCA/servo 완료 |
| PCA apply success cache | 해당 motor 상태 요청의 HAL 성공; frame success면 그 write 집합 성공 | 실제 링크/돌기 위치와 tactile correctness |
| physically observed | 사용자가 해당 시점·셀 상태를 확인 | 다른 generation/frame까지 자동 소급 검증 |

### I03 — ownership와 backpressure

| owner | queue/state 정책 | cancellation / reconnect의 실제 범위 |
|---|---|---|
| camera source / optional preview worker | latest frame 1개, engine이 새 generation만 수령 | source generation으로 stop 후 늦은 성공결과 억제; HTTP 진행 중 I/O 즉시 kill 보장 없음 |
| Scanner engine / preparation executor | bounded candidate window, single recognition in flight, preparation Future, one pending artifact/bank | cancel은 active job 무효화, 진행 Future 결과 폐기. close는 executor shutdown(wait=False), model call 강제중단 보장 아님 |
| DeviceApplication/Coordinator | 순차 state mutation, physical/release 먼저, hold tick 누적 catch-up 없음 | 긴 synchronous network/recognition 호출은 scheduling latency에 영향; serial worker ACK와 main command 처리는 독립 |
| durable delivery | SQLite next_nonterminal 순서, monotonic next-attempt backoff | reconnect 후 전송 재개 가능; retry 횟수 상한을 이 경로가 제공하지 않음. backoff cap은 최대 전체 대기시간이 아님 |
| S1 workers/store | fragment lease·attempt, finalize waiting/assembling/validating/promoted | expired claim 재처리; promoted journal recovery 검증 후 publish. 아무 실패나 무한재시도 아님 |
| audio controller/native player | priority/group replacement, one playback worker, byte/entry LRU | epoch fence 후 cooperative stop; join timeout은 오류. native thread 강제종료 아님 |
| host serial | bounded normal event queue+urgent release, one latest desired frame | backoff reconnect, HELLO새 epoch, active DOWN forced release; intermediate frames 합쳐짐 |
| STM UART/main/PCA | IRQ bounded ring, main bounded pump, one inflight NAV+FIFO, state별 PCA write skip | byte error/overflow newline까지 폐기+resync; no physical closed-loop feedback |

## 3. 실패 흐름

정상적인 failure result(UNKNOWN, RETRY_LOCAL, rejected row, finalization ERROR 등)와 exception(FatalPortError, transport error, native error)을 분리한다. `retryable=true` 표시는 재시도 가능 분류이지 그 caller가 자동으로 같은 작업을 다시 수행한다는 보장이 아니다.

| ID / 발생 조건 | 감지 / failure 형태 | Retry owner·조건 | Fallback / 포기·전파 | 근거 |
|---|---|---|---|---|
| F01 C0 server unavailable | RetryableConnectivityError, retry_wait/lost | connectivity capped exponential+jitter, poll due | auth/protocol fatal은 retry 성공으로 숨기지 않고 Coordinator STOPPED | DEV/connectivity.py:_connect/_send_heartbeat/_schedule_retry; coordinator.py:_poll_connectivity |
| F02 snapshot timeout/connection·408/429/500/502/503/504 | SnapshotTransportError(retryable=True) | source read 1회당 transport 1회; 실패1/2회 뒤 0.25×count sec pull backoff; 성공 시 counter reset | 연속3회 또는 permanent면 terminal→Scanner SESSION_ERROR→Device fatal. webcam fallback 없음 | SC/video/sources.py:read/_fetch_decoded_frame; engine.py:_fail_snapshot; DEV/adapters/book_scanner_runtime.py |
| F03 camera auth/SSL/그 외 permanent HTTP | status/SSLError, unreadable credential file | auth/SSL 오류 자동 반복 대상 아님 | profile별 TLS option만 적용, 인증해제/전역 verify off 없음. SESSION_ERROR/초기화 fatal | 위 source:_auth/_tls_verify. 비밀번호 내용은 본 분석에서 열지 않음 |
| F04 oversized/nonimage/too-small snapshot | FrameDecodeError | read 내부 decode failure 최대3회 | 모두 실패→fatal; image 성공처럼 빈 frame 제공하지 않음. transport retry와 같은 loop라고 설명하지 않음 | SC/video/sources.py:read/_fetch_decoded_frame |
| F05 preview render 실패 / worker stop 지연 | warning; preview_active=False / 2sec join 후 warning | render 실패 후 그 preview를 끔; acquisition source는 동일 | 화면 표시 중단은 camera 교체 아님. warning만으로 worker 종료 성공 주장 불가 | SC/video/operator_preview.py:pump_preview/stop |
| F06 page missing/moving/occluded/quality 부족 | retry_reasons, SETTLING/guidance | 계속 샘플링; guidance 안정시간/반복 간격 정책 적용 | 사용자 framing 조정이 필요할 수 있음; bright/선명한 육안 관측만으로 algorithm eligible은 아님 | A02; SC/video/guidance.py, engine.py:poll |
| F07 footer missing/contradictory/시간 만료 | no raw pair 또는 UNKNOWN/timed_out | missing은 N 미충족, window 재시작/로컬 retry | 가짜 DIFFERENT나 arbitrary page number fallback 없음. 일부 provider 예외는 engine에서 None 관측으로 축약됨 | A03; SC/video/engine.py:_observe_opaque_pair/_poll_opaque_identity/_poll_opaque_page_change |
| F08 raw DIFFERENT지만 page-change 미허가 | A04 conjunctive gate 불충족 | 새 관측 cycle; eventual visual/numeric corroboration 필요 | 전체 획득의 유한 완료시간 보장 없음. H1 compact logs에 gate 세부가 없으면 두 후보 원인 중 어느 것인지 확정 불가 | A04; docs/H1_FRESH_ALIGNED_RUN_20260908.md의 second-held/late-success evidence |
| F09 seam/crop/UVDoc 실패 | PreparationDecision RETRY_LOCAL 또는 FATAL | detection/invalid output은 local retry; model unavailable/load 실패는 fatal | uncorrected page로 성공 처리 없음. L/R 한쪽만 업로드 금지 | SC/video/spread_preparer.py:prepare/_map_unwarp_failure |
| F10 cancel 중 preparation 완료·artifact collision | job ID/state 비교, prepared discard / commit fatal reason | stale job 재사용 없음; cancelled Future는 publish 불가 | close 이후 future completion cleanup callback. collision overwrite 금지. cancellation은 실행 중 모델의 강제 interrupt 아님 | SC/video/engine.py:cancel/close/_cleanup_preparation_after_close/_poll_processing; artifacts.py |
| F11 local artifact hash/lineage 오류 | verify_prepared failure, LOCAL_ARTIFACT_INVALID→rejected | 손상된 artifact 반복 전송 안 함 | flush BLOCKED; lineage mismatch는 fatal. local ack 뒤 cleanup 실패는 cleanup_error이며 durable ack를 되돌리지 않음 | DEV/delivery.py:_advance_one/_cleanup_acked; coordinator.py:_advance_flushing |
| F12 upload transport/temporary HTTP | outbox RETRYING, response.retryable/5xx/408/429 | delivery exponential delay cap, Retry-After 있으면 더 긴 delay; 전체 attempts 상한 없음 | FIFO head pending이면 후속/flush 지연; ack cue 없음 | DEV/delivery.py:_handle_response/_retry |
| F13 V4 auth/receipt identity/malformed response | 401/403 또는 FatalPortError | outbox는 retry 상태 보존하되 exception fatal 전파 | 잘못된 receipt를 ack로 기록하지 않음; operator/environment 정정 필요. 자동 인증 fallback 없음 | DEV/delivery.py:_handle_response; adapters/http_v4.py |
| F14 server invalid upload/conflict/storage interruption | S0Error code/retryable, OSError, interrupted receiving journal | temporary receiving abandon; promoted bundle는 recover handoff; 동일 idempotency replay | permanent는 rejected; untracked final quarantine. 동일key 다른payload는 conflict. 이 작업에서는 cleanup/recovery를 실행하지 않음 | DP/server/v4_upload.py:accept_upload/recover |
| F15 fragment hash/schema/empty page/assigned page mismatch | ParserRejectError→REJECTED | terminal semantic rejection은 자동 parser retry 없음 | receipt 자체를 성공 OCR로 재해석 금지; seal은 해당 fragment 때문에 실패 | DP/server/s1_parser.py:parse; s1_services.py:process_next_fragment |
| F16 parser exception/worker lease 만료 | PARSER_RUNTIME_FAILED 또는 expired processing lease | QUEUED로 복귀, parser_max_attempts까지; 초과 ERROR | 무한 모델 retry 없음. lease ownership 잃으면 결과 commit 거절 | DP/server/s1_services.py:_claim_fragment/_finish_fragment |
| F17 seal incomplete/fragment failure/cutoff 위반 | readiness wait/error | incomplete는 waiting; 필요한 fragment만 기다림 | failed fragment/SPREAD_AFTER_CUTOFF/EMPTY_DRAFT는 finalize fail. 빈 기존 append는 no-op일 수 있음 | DP/server/s1_services.py:_finalize_readiness |
| F18 assembly/TTS/index/hash/publish 실패 | finalization ERROR; validation exception code | promoted journal는 재검증 후 publish recovery; terminal fail은 자동 성공 승격 없음 | 기존 READY revision 유지. system/reading WAV가 없는 revision을 READY로 대체하지 않음 | DP/server/s1_assembler.py:validate; s1_services.py:process_next_finalization/_fail_finalize |
| F19 OCR omission/미지원 math·visual | 알려진 completeness issues, AST status, visual handling | 일반 OCR 자동정답 복구/재인식 fallback 없음 | A08의 불확실 음성/empty braille/embedded text만 보존. 발견되지 않은 silent omission은 남을 수 있음 | DP/serialization/vl_page_ir.py; accessibility/flattening/structure_nodes.py/speech/math_rules.py |
| F20 corrupt/stale persistent cursor | version/JSON/anchor/index/mode/type 검증, S0ConflictError | 없는 progress만 최초 page/node0. 기존 progress 부정합을 임의 초기화하지 않음 | 다른 revision에서도 stable page/focus anchors로 재탐색; anchor 부재는 error. client는 HTTP409를 RecoverablePortError로 전달하며 UI 회복과 저장 정정은 별개 | DP/server/s0_services.py:_load_progress/_cursor_to_state; DEV/adapters/http_s0.py:_call |
| F21 S0 command timeout/404/409/5xx·response shape 오류 | RecoverablePortError / FatalPortError | Coordinator가 현재/선택 회복 및 later poll/input으로 처리; 자동 무조건 동일 command 반복 아님 | command receipt는 동일 command ID/hash에 동일 효과/응답. malformed/auth 등 fatal은 STOPPED | DEV/adapters/http_s0.py:_call; coordinator.py:_handle_reading_input; DP/server/s0_services.py:send_reading_command/_receipt |
| F22 audio fetch/format/hash failure | AudioResourceError(retryable flag), current job FAILED feedback | controller는 실패 job 자동 재시도 loop 없음. 사용자의 새 command/replay로 새 job 가능 | authenticated origin/ref endpoint로만 fetch; redirect 금지; arbitrary URL/OS TTS fallback 가정 금지 | DEV/adapters/reading_audio.py:_NoRedirect/_fetch_url/_validate_wav; reading_audio.py:_run |
| F23 audio supersession/native failure/underrun | epoch cancellation, callback abort/errors, duration+10sec deadline | 취소는 정상 제어; native failure는 FAILED, stale 결과 feedback 억제 | stream owner finally abort/close. controller close join 실패는 observable cleanup error. '재생 started'만으로 청취 PASS 금지 | A10; DEV/reading_audio.py/adapters/reading_audio.py |
| F24 braille translator/presenter exception | BRAILLE_RENDER_FAILED/degraded clear 또는 app channel warning counter | 다음 유효 snapshot으로 다시 시도 가능 | server renderer failure는 clear projection, app presenter failure는 다른 audio channel과 분리; 이전 physical frame이 실제 사라졌다고 보장하지 않음 | DP/accessibility/application/speech_controller.py:_contain_braille_failure; DEV/application.py:_present_contained |
| F25 serial port loss/partial record/queue full | OSError/read bounds/framer, BUSY/worker error | host reconnect capped backoff; seq 재ACK/dedupe, rehandshake release; line continuation | V2/legacy 호환은 별도 경로, V2 SHORT를 V3 A/R acceptance로 승격 금지 | DEV/adapters/stm_serial.py:_io_loop/_SerialLineFramer |
| F26 MCU UART error/overflow/invalid FRAME | IRQ error counters, ring resync, parser return0 | newline resync 뒤 다음 record 수용 | invalid partial state 적용 안 함. frame-level applied ACK protocol은 없음 | FW/main.c:BluetoothRxHandleByte/PumpBluetoothInput/ParseAndApplyFrame |
| F27 PCA 실패/잘못된 물리 정렬 | HAL return/cache/counter / 사용자 셀 관측 | 실패 motor cache는 갱신 안 함; 다음 apply에서 재시도 가능, 별도 자동 closed-loop 없음 | 이미 성공한 다른 motor write rollback 없음. HAL_OK여도 돌기 residual 가능; LUT/pin 임의교정 금지 | FW/main.c:ApplyBrailleFrame/Motor_SetState |
| F28 fatal/cleanup/launcher 종료 | Coordinator fatal_reason/STOPPED, cleanup_failures, Python exception/OS exit | cleanup 개별 보호로 다른 resource도 닫기 시도 | 정상 main 반환 경로에서 fatal/cleanup failure→exit2, 정상0; unhandled exception/native crash는 별도 OS 결과. wrapper null exitcode를 exit0으로 읽지 않음 | DEV/application.py:run/stop/exit_code; __main__.py:main; H1 fresh launcher evidence |

## 4. failure result / exception / 관측 부재 분류

| 표현 | 의미 | 문서에 필요한 주의 |
|---|---|---|
| UNKNOWN·SAME, no next formula | 정상 decision result | 기대 경계 안내일 수 있으며 exception과 구분 |
| RETRY_LOCAL·outbox RETRYING·finalize waiting | 작업이 아직 완료되지 않음 | retry cap/time bound와 pass 여부를 별도 표시 |
| fragment REJECTED/ERROR·finalize ERROR | 해당 작업의 terminal business state | 서버 process 전체 crash 의미 아님 |
| RecoverablePortError | caller의 현재 동작이 복구 가능한 API 실패로 중단 | 데이터 손상 자동 수리/모든 command retry 의미 아님 |
| FatalPortError·Scanner FATAL·connectivity FATAL | Device 진행을 중단하는 실패 | feedback 재생 성공을 fatal propagation의 전제조건으로 두지 않음 |
| contained audio/braille exception | 한 출력 channel 실패 기록 | navigation 가능해도 해당 output은 PASS 아님 |
| native crash·중단된 wrapper·invalid JSON log | Python이 정상 상태를 기록하지 못할 수 있음 | source exception 정책으로 원인 확정 불가; raw dump/bytes/exit 관측 필요 |
| 실제 청취/핀 관측 없음 | 해당 physical boundary evidence 부족 | software success나 향후 Pi 설정 계획으로 대체 금지 |

## 5. 대표 사례용 데이터 계보와 한계

Blueprint에 넘길 **예시 근거**이며 최종 narrative는 아님.

| 사례 | 입력 → 중간 → 결과 | 근거 / 제한 |
|---|---|---|
| X01 fresh 두 spread | 교재26/27·28/29 → seq1/2 각각 receipt → L/R 네 fragment ready → cutoff2 → datapack-b7d5a769ad5347738d491f1b39e5e909 revision1 READY | docs/H1_FRESH_ALIGNED_RUN_20260908.md 및 그 raw evidence index. 기존 run의 결과로만 사용; 이번 pass에서 live 실행 안 함 |
| X02 모양은 선명한데 두 번째 대기 | orientation 문제 정정 → raw N5 DIFFERENT 반복·page-change 대기 → 나중에 operator 추가조작 없이 receipt2 | D03/D04와 A04를 분리해서 설명. gate가 열린 실제 flag는 compact log에 없어 원인 미확정. 완전한 liveness PASS 아님 |
| X03 같은 음성이지만 page 이동 | 서로 다른 page_id의 첫 TEXT가 모두 www.ebsi.co.kr → 각각 다른 snapshot generation/page anchor | 같은 audio string만으로 page 이동 실패라고 단정 불가; 위 fresh run reading continuation |
| X04 restart restore | page1/node1 generation5 progress → process restart → 새 reading session에서 full cursor generation5 복구+audio completion | stable device/progress의 제한된 증거. 해당 bundle은 empty braille/offset0이므로 수식 window나 physical braille 검증이 아님 |
| X05 수식 confidence 차이 | LaTex AST PARTIAL → uncertainty speech + empty braille | A08 실제 code·test로 정의된 branch 예시, X01의 모든 수식이 이 상태였다고 주장하지 않음 |

남은 외부 검증 범위: Raspberry Pi4 배포/성능·AUX output·Linux Bluetooth serial은 계획으로만 표시. firmware의 논리 FRAME contract와 실제 GPIO/기구 mapping은 하드웨어팀 정정 뒤 재검증 필요. 이 pass는 native dump 분석/새 incident root-cause 확정 작업을 수행하지 않음.

## 6. 테스트 근거와 분석의 범위

- source/test 대조: SC tests/unit/video/test_h123_camera_recovery.py, test_sources.py, test_engine.py, test_engine_v3a5.py; DEV tests/unit/test_delivery_v3b.py, test_h123_boundaries.py, test_h123_audio_lifecycle.py, test_reading_audio_adapters.py, test_stm_serial.py; DP tests/unit/test_server_v4_upload.py, test_server_s1_ingest.py, test_server_s1_finalize.py, test_server_s0.py, accessibility/test_speech_controller.py.
- 테스트 파일은 경로/의도/대표 assertion의 근거이며 이번 단계에서 실행한 PASS 결과가 아님. 실물 camera/Paddle/Piper/COM/servo test를 새로 실행하지 않음.
- 분석 보완: PASS1의 단순 'audio completion' 표현은 I02/F23 수준으로 좁혀 읽는다. source completion과 사람의 청취, profile timeout과 전체 deadline은 별개.
- D09 table metadata 보완: cell 좌표는 HTML rowspan/colspan을 반영하지만 pixel bbox는 table bbox의 균등 분할 추정이며 bbox_is_estimated=True. structure_confidence는 row-grid 일관성의 휴리스틱이다(PASS2 A07 추가 근거).
- D14 출력 범위 보완: DOCUMENT의 일반 text는 clear. TABLE 내부는 열/행 번호와 지원된 text/leaf math 값을 encoding하는 별도 buffer가 있고, 구조적 math cell은 현재 NotImplementedError 가능(PASS2 A09; DP/accessibility/braille/table_formatter.py). 따라서 '모든 text는 점자 없음'이나 '표 내부 모든 수식 지원'으로 일반화하지 않음. 이 시연 viewport10과 독립 library/config 기본값도 구분한다.

Gate: D01–D15 정상 데이터 변환, I01–I03 identity/completion/owner, F01–F28 실패 경로, X01–X05 사례 근거 완료. PASS4의 입력은 PASS0 범위, PASS1 workflow, PASS2 algorithms/decisions, 본 PASS3 데이터·실패·한계이다.
