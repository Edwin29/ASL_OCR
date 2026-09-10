# PASS 1 — End-to-End Execution Reconstruction

상태: COMPLETE. 입력: [PASS0](PASS_0_SCOPE_BASELINE.md)의 E0/E1/E2, P-Capture/P-Reading, Q1/Q2/Q4. 단계별 source 추적으로 복원한 분석 표이며 최종 설명문이 아니다. 상세 판단 수식은 PASS2에 넘긴다.

경로 약어: DEV=device-runtime/src/asl_device; SC=book-scanner/src/book_scanner; DP=document-parser/src/document_parser; FW=hardware/stm32/kitel2026final/Core/Src. 각 표의 code는 이 root에 상대적이다.

## 정상 흐름 W01–W20

| Step / Purpose | Input | Operation | Output | Decision / Next | Relevant implementation |
|---|---|---|---|---|---|
| W01 실행 구성: 실제 경계 선택 | CLI/config, models, persistent roots | Server OCR/Piper 공유 adapter·S0/S1/V4/presence 구성; Device Scanner/delivery/audio/controls 구성 | host services, model owners, workers | --preflight이면 관측 후 종료; 정상→W02 | DEV/__main__.py:main; local_composition.py:build_local_device; DP/server/combined_server.py:main |
| W02 사용자 입력을 단일 상태 변경으로 전달 | GPIO/console lines | STM debounce/edge/sequence→host ACK/dedupe; app input drain/hold scheduling | DeviceInputEvent | 모드에 따라 catalog/reading/capture 분기→W03 또는W15 | FW/main.c:ButtonPollEdge/ButtonPollConfirm/QueueControlAction; DEV/adapters/stm_serial.py; application.py:step |
| W03 새 책 또는 기존 책 선택 | C0 연결 상태, S0 catalog, input | mode별 catalog 필터; new면 datapack 생성; scan session open | datapack_id, scan_session_id, next sequence | capture→W04; READY reading→W15 | DEV/coordinator.py:_load_catalog/_open_selected_scan; DP/server/s0_services.py:create_datapack/open_scan |
| W04 Android 영상 공급 | authenticated snapshot bytes | HTTP decode/rotation/min-dimension; preview-enabled worker가 latest frame 공급 | frame ID/time/pixels | retryable transient는 재시도; permanent 종료. frame→W05 | SC/video/runtime_composition.py:LocalBookScannerEngineFactory; sources.py:HttpSnapshotCameraSource; operator_preview.py:ThreadedPreviewCameraSource |
| W05 촬영할 순간 선택 | sampled frame/이전 후보 window | preview page-pair/mask/seam proxy, 노출/선명도/가림 판정, 안정 window에서 선택 | selected source frame, candidate metrics | 부적격→W04+guidance; 선택→W06 | SC/video/candidate.py; engine.py:poll |
| W06 현재 spread의 identity 확인 | selected context, native preview footer observations, accepted banks | M1 raw pair 수집; SAME/DIFFERENT/UNKNOWN | identity decision, query bank | current opaque 경로: DIFFERENT→W07; duplicate/unknown은 재시도/대기 | SC/video/engine.py:_poll_opaque_identity; opaque_identity.py; composition.py |
| W07 양쪽 페이지 준비 | 하나의 selected full-resolution frame | seam-conservative split, L/R crop 각각 UVDoc 보정, 두 side readiness 검사 | prepared spread in staging, metadata/files | 한쪽 실패 시 uncorrected fallback 없이 retry/fatal; 성공→W08 | SC/video/spread_preparer.py:SeamUVDocSpreadPreparer.prepare; detect/spread_extraction.py; correct/uvdoc_adapter.py |
| W08 로컬 artifact 게시와 pending bank | prepared spread, identity, current job/session | artifact commit; same-frame L/R/ref/hash; pending ownership 등록 | SpreadArtifactRef + ARTIFACT_READY | cancelled/stale는 폐기; current→W09 | SC/video/engine.py:_poll_processing; artifacts.py:FilesystemArtifactStore; DEV/adapters/book_scanner_runtime.py |
| W09 전송 책임을 durable outbox로 이동 | artifact ref, scan/sequence/device | 파일 inventory 검증; SQLite enqueue; ordered claim; HTTP multipart 전송 | outbox row + request | retry/backpressure이면 row 유지; 응답→W10 | DEV/delivery.py:DurableDeliveryPort.queue/_advance_one; delivery_store.py; adapters/http_v4.py |
| W10 서버 durable 수신 | manifest/inventory/files, idempotency key | 요청 제한·identity/hash 검증, staging write/flush, final promote, S1 handoff transaction | V4 receipt, L/R fragment work rows | 같은 request 재전송은 동일 효과; conflict/reject 분기; 성공→W11과W12 | DP/server/v4_upload.py:accept_upload/_promote/_handoff; s1_services.py:accept_verified_spread |
| W11 첫 전송 완료와 새 페이지 대기 | valid receipt response | Device ack commit→scanner delivery_confirmed→accepted bank; spread_sent cue | durable ack, WAITING_FOR_PAGE_CHANGE | 새 raw identity+visual 또는 numeric corroboration→W05; 같은 page 대기. LONG→W13 | DEV/delivery.py:_handle_response; coordinator.py:_handle_delivery_update; SC/video/engine.py:delivery_confirmed/_poll_opaque_page_change |
| W12 서버에서 페이지별 해석 | received L/R image hash와 fragment claim | PaddleOCR-VL→Page IR→problem units→schema validation→flatten_page | page_ir.json + accessible_page.json, parser status | 실패는 fragment retry/terminal; receipt를 취소하는 의미 아님; W13/W14의 입력 | DP/server/s1_workers.py; s1_services.py:process_next_fragment; s1_parser.py:PaddleVlFragmentParser.parse |
| W13 사용자 촬영 종료 의사 확정 | CONFIRM LONG, captured sequence cutoff | Scanner freeze, cutoff까지 outbox flush, seal | through_sequence와 finalize request | 아직 ack 안 된 row 기다림; 성공→W14. incomplete를 READY로 표시하지 않음 | DEV/coordinator.py:_request_scan_stop/_advance_flushing; DP/server/s1_services.py:request_seal |
| W14 읽기 가능한 revision 생성 | cutoff까지 ready fragments, optional base revision | sequence/side 순서 결합, utterance 생성·Piper WAV/cache, document/audio index/manifest 검증, immutable root promote, DB publish | READY revision + datapack_saved cue | fragment 미완료→waiting; reject/validation 실패→실패; READY→W03/W15 | DP/server/s1_services.py:_finalize_readiness/_assemble_and_publish/_publish_revision; s1_assembler.py:assemble/validate; DEV/coordinator.py:_handle_finalization |
| W15 읽기 session/cursor 복구 | READY id, stable device, command id | revision 확인, preflight/cache load, persistent progress restore | reading session + NavigationState | readable revision 없으면 reject; 정상→W16 | DP/server/s0_services.py:open_reading/_load_progress; DEV/coordinator.py:_open_reading |
| W16 페이지·항목·수식 창 탐색 | navigation command, current focus/mode | document/table navigator 및 speech controller가 cursor/generation/output 갱신; command receipt와 progress 저장 | reading snapshot, speech result, braille window | 경계면 안내/유지; silent window scroll이면 새 speech 없음→W17/W18 | DP/server/session.py:DatapackSession.handle_button; accessibility/application; server/s0_services.py:send_reading_command |
| W17 해당 generation 음성 재생 | snapshot opaque audio_ref 또는 system cue | authenticated fetch/WAV validation/cache; old epoch cancel→new owner playback | started/completed/interrupted audio feedback | stale fetch/play 무효화; 오류 containment→navigation 유지 | DP/server/s0_services.py:get_audio_resource/_opaque_audio_ref; DEV/reading_audio.py; adapters/reading_audio.py |
| W18 동일 focus의 점자 프레임 전달 | snapshot cursor/generation, cells | viewport≤10 cells serialize/pad; host serialized write | FRAME,page,node,span,offset,gen,c0..c9 | catalog/clear·재접속은 presenter 정책; STM path→W19, console은 JSON만 | DEV/adapters/stm_serial.py:present 및 FRAME 생성; application.py:_present |
| W19 MCU 요청 적용 | UART byte stream FRAME | IRQ ring→line recovery→full field validation→requested state→cell bit/servo state→PCA writes | accepted frame, bus apply state/counters | 형식 오류면 전체 reject; bus 실패와 물리 위치는 별도→W20 | FW/main.c:BluetoothUartIrqHandler/PumpBluetoothInput/ParseAndApplyFrame/ShowCurrentState |
| W20 종료·재진입·재시작 | mode/LONG/Ctrl+C, persistent cursor | reading catalog 복귀 또는 resource close; 같은 device/datapack로 open | restored cursor/audio, new host boot namespace | stale command/hold/stream을 새 lifecycle로 이월하지 않아야 함 | DEV/application.py:stop; coordinator.py:_return_to_selection/stop; DP/server/s0_services.py:_load_progress |

## 실행 순서에서 중요한 비동기 경계

- W10 durable receipt는 W12 OCR 완료 전 나올 수 있다. W12는 수신 후 background worker에서 진행하며 W13 seal이 OCR 시작 명령은 아니다.
- W11은 다음 spread를 수집하는 동안 W12가 진행될 수 있다. W14는 cutoff의 모든 fragment 준비를 기다린다.
- W17/W18은 같은 snapshot의 독립 projection. 한 presenter 실패가 다른 출력을 막지 않도록 application이 각각 containment.
- W19 ACK는 physical application 응답이 아님. ACK,<seq>는 STM발 NAV 입력 수락용. FRAME write, PCA bus success, physically observed cell은 별도.
- E0 console mode에서 serial presenter를 자동 사용하지 않음. current production composition은 stm_serial 선택 시 동일 객체를 controls/presenter로 사용; console+jsonl은 JSON snapshot. H2 custom composition override와 구분.

## 의미 있는 실패 경로 (PASS3에서 상세화)

| ID | 최초 경계 | 관측되는 진행 | 다음 owner |
|---|---|---|---|
| F-PATH1 | camera/candidate/identity 부적격 | transport recovery 또는 guidance/local retry; artifact 없음 | Scanner |
| F-PATH2 | outbox/network/server busy | local durable row 유지, exponential retry; spread_sent 없음 | delivery/V4 |
| F-PATH3 | fragment terminal reject | receipt는 존재할 수 있으나 fresh READY 못 만듦 | S1 finalize |
| F-PATH4 | audio/braille presenter 실패 | navigation snapshot은 이미 commit; 각 채널 실패 보고 | application/presenter |
| F-PATH5 | malformed UART/overflow | 완전 record 전 ACK 금지; FRAME full validation; resync | Host/firmware |

## PASS0 open questions 처리

- Q1: W09–W14로 durable receipt / parser / seal / READY 순서 분리 완료.
- Q2: production S1은 PaddleVlFragmentParser→build_page_ir_from_vl_result→detect_problem_units→flatten_page. 과거 document_parser.pipeline 전체를 무조건 거치는 것으로 설명하면 오류.
- Q4: W15–W19에서 cursor→generation→audio/FRAME 흐름 식별. 함수 내부 algorithm은 PASS2 입력.
- Q3/Q5: 미해결이 아니라 다음 Pass의 분석 범위. Q6/Q7은 실험 증거와 한계로 유지.

Gate: W01–W20에 Purpose/Input/Operation/Output/Branch/Next/Implementation 확보. PASS2는 이 Step ID를 분류 단위로 사용한다.
