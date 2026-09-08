# H1/H2/H3 bounded critical-path architecture assurance — 2026-09-08

**판정: 구현 일괄 승인 근거가 부족하다. H4 진입 불가. Product source modification count = 0.**

기존 단일 Coordinator, audio arbiter, STM I/O worker, Scanner pending-artifact 구조를 폐기할 근거는 없다. 다만 native audio의 stream 소유·취소·종료 관계는 내부 lifecycle 설계가 먼저 필요하다. Camera/input 및 firmware RX/PCA의 실제 시간·적용 계약은 아직 입증되지 않았다. A1/A2/B-host/C2/C3/T1/T2를 한 묶음의 단순 patch로 취급하지 않는다.

본 판정은 source inspection, 기존 독립 재현, 이번 Laptop fake-boundary 재현에 근거한다. 실제 AV stack, UART overrun, servo 위치를 새로 측정한 결과가 아니다. 기존 [진단 보고서](H1_H2_H3_SOFTWARE_DIAGNOSTIC_RESULT_20260908.md)와 raw evidence를 보존하며, 그 보고서의 수정 packet보다 **이번 architecture 선행 조건을 우선** 적용한다. 아래 두 packet 묶음은 모두 제안이며 구현하지 않았다.

- [기존 구조를 유지하는 bounded local correction packets](work-packets/H123_ARCH_LOCAL_CORRECTIONS_20260908.md)
- [추가 계측·구조 설계가 먼저 필요한 packets](work-packets/H123_ARCH_DIAGNOSTIC_DESIGN_20260908.md)

## 1. 범위, source identity, evidence

범위는 live camera/page-change, DeviceApplication input scheduling, reading audio, STM host, firmware RX/parser/PCA, CLI fatal propagation이다. Parser content 개선, server architecture, repository 전반 refactoring은 제외했다. C0는 fatal 종료 호출과 application scheduling에 직접 연결된 부분만 읽었다.

Desktop와 Laptop 각각 246개 product source의 hash를 이전 진단 종료본과 비교했다. 변경 0, Desktop/Laptop LF-normalized 차이 0이다. Laptop Python은 `C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe` 3.11.9이며 `asl_device`, `book_scanner`, `document_parser`의 실제 import가 모두 `C:\ASL_OCR_INTEGRATION` 아래다. Commit 단독 동일성을 baseline으로 대체하지 않았다. [시작 identity](evidence/critical-path-architecture-assurance-20260908/source-identity-before.json), [종료 integrity](evidence/critical-path-architecture-assurance-20260908/integrity.json).

| Evidence | 사용 범위와 한계 |
|---|---|
| [기존 Laptop independent reproduction](evidence/software-diagnostic-20260908/laptop-reproduction-results.json) | A1/A2/B-host/C2/C3/T1/T2의 실제 Python 객체 + fake adapter. Native driver/UART/servo acceptance 아님 |
| [이번 probes source](evidence/critical-path-architecture-assurance-20260908/probes.py), [결과](evidence/critical-path-architecture-assurance-20260908/laptop-probes.json) | CP-I1 blocking acquisition/cancel, CP-H1 partial-line acceptance, CP-T1 fatal cleanup. 실제 Python source, fake camera/serial/connectivity. 기존 runtime state 사용 0 |
| [기존 firmware models](evidence/software-diagnostic-20260908/firmware-model-results.json) | overflow suffix와 blocking RX 가설을 설명하는 모델. compiled C/HAL/board 실행 아님 |
| [기존 targeted tests](evidence/software-diagnostic-20260908/targeted-existing-tests.txt) | 이전 source에서 142 PASS. Source 동일성 확인 후 재사용. 이번 turn에 G3-A나 142 tests를 재실행한 것으로 주장하지 않음 |
| [dump metadata](evidence/software-diagnostic-20260908/dump-metadata.json), [raw bundle](evidence/software-diagnostic-20260908/raw-evidence.json) | 두 native AV의 module/exception metadata는 확인됨. debugger/symbol/unwind stack 미확보, exact root는 계속 insufficient_evidence |

SSH는 이번에 read-only import/hash 및 stdin Python probes만 실행했다. Package/credential 생성·변경, live upload, camera probe, audio device open, COM open, servo 구동, firmware flash는 모두 0. Laptop D: 접근 0. 새 evidence는 Desktop의 전용 docs/evidence 경로에만 기록했다. 임시 thread와 fake connection은 시험 종료 때 정리했다.

## 2. Subsystem architecture 판정 matrix

`architecture_change_required`는 이 범위의 내부 책임·lifecycle 변경이 필요하다는 뜻이다. 새 외부 layer나 전면 재설계 승인이 아니다. `insufficient_evidence`는 알려진 결함이 없다는 뜻도, 구조 변경이 확정됐다는 뜻도 아니다.

| Subsystem | 판정 | Source / reachable trigger / invariant / test gap | 다음 행동 |
|---|---|---|---|
| Live camera acquisition + page-change | **insufficient_evidence** | [sources.py:456](../book-scanner/src/book_scanner/video/sources.py#L456), [engine.py:347](../book-scanner/src/book_scanner/video/engine.py#L347), `engine.py:645,832,1205`; slow fetch/recognizer와 transient HTTP. 현재 N=5/8초에서 수집 진전과 timely cancellation을 함께 보장하는 근거 없음. C2/C3는 국소 contract 결함으로 확인. 기존 fake-clock 시험은 HTTP/recognizer의 실제 elapsed time·cancel 경쟁을 결합하지 않음 | C2 taxonomy/C3 guidance는 국소 후보. D-C에서 시간 의미·실측을 먼저 확정. 8초/N/K 변경 금지 |
| DeviceApplication input scheduling | **insufficient_evidence** | [application.py:90](../device-runtime/src/asl_device/application.py#L90), `:155,163`; `coordinator.py:141`. CP-I1: synchronous camera read 중 새 input과 cancel 모두 진행 불가. 기존 release-during-slow-S0 test는 입력 batch가 반환된 뒤의 repeat 억제만 검사. Live acquisition/recognition/delivery를 포함한 application turn 상한은 미측정 | Single writer는 유지. D-C에서 end-to-end input latency/queue age를 측정한 뒤 blocking port의 국소 수정 또는 acquisition owner 분리 판단 |
| Reading audio lifecycle | **architecture_change_required** | [reading_audio.py:198](../device-runtime/src/asl_device/reading_audio.py#L198), `:228,326`; [adapters/reading_audio.py:150](../device-runtime/src/asl_device/adapters/reading_audio.py#L150). A1: input-thread abort와 worker write/stop/close 동시 실행. A2: 새 epoch publish 후 무대상 stop. old cancellation이 new stream을 건드리지 않고 owner 종료가 확인돼야 한다는 invariant 위반. Fake native happy path는 overlap/blocked drain/late close를 검증하지 않음 | 기존 controller/port는 유지하되 D-A로 stream owner·cancellation target·join 결과를 먼저 설계. A2는 논리상 local이나 A1과 같은 stop 계약에 의존 |
| STM host transport | **architecture_sound_with_local_defect** | [stm_serial.py:129](../device-runtime/src/asl_device/adapters/stm_serial.py#L129), `:198,256,438`; B-host: release/activation이 서로 다른 16-event batch로 분리. CP-H1: newline 전 timeout partial `NAV,D,A,7` 수락. accepted edge order와 complete-record ACK invariant 위반. Tests는 주로 whole-line fake와 단일 batch | L-B에서 같은 I/O worker 안의 ordered drain/line accumulation 수정. UART/FRAME/V3 변경 필요 없음 |
| Firmware RX / parser / PCA application | **insufficient_evidence** | [main.c:483](../hardware/stm32/kitel2026final/Core/Src/main.c#L483), `:717,875,911,974,1175`; 정상 host FRAME가 debug/I2C/batch delay 중 도착. RX 서비스 상한·overflow 복구·reject atomicity·PCA 성공 구분 미충족/미검증. 현재 host fake는 HAL scheduling과 bus 실패를 모델링하지 않음 | D-F로 UART capture/ORE·FE·NE/compiled parser/bus 결과 확인. Parser의 validate-before-commit은 local 가능성이 높지만 RX 구조 선택과 physical 적용은 보류 |
| CLI fatal propagation + 좁은 preflight tooling | **architecture_sound_with_local_defect** | [__main__.py:49](../device-runtime/src/asl_device/__main__.py#L49), [coordinator.py:174](../device-runtime/src/asl_device/coordinator.py#L174), `:709`; [laptop_acceptance.py:105](../device-runtime/src/asl_device/laptop_acceptance.py#L105), `:172`. T2 fatal→STOPPED→return0, CP-T1 connectivity.stop 생략, T1 IP profile→webcam probe. 정상 exit와 fatal outcome, selected-source identity가 혼동됨. Existing normal stop/preflight tests는 해당 조합 없음 | L-T에서 기존 owner에 terminal outcome과 cleanup latch, 정확한 factory routing. 새 supervisor layer 불필요 |

위 링크의 `#L` 번호는 source 찾기용이며, 현재 hash와 함께 해석한다. 세부 위치와 동작은 아래 계약 설명이 기준이다. 실제 파일 탐색 시 해당 줄 번호를 사용한다.

## 3. Live camera acquisition / page-change 계약

**책임과 owner.** `HttpSnapshotCameraSource`가 profile-local requests Session/Response와 frame decode/orientation을 소유한다. `SampledFrameEngine`은 camera lifecycle, bounded candidate window, identity collector/accepted bank, pending artifact, processing future를 소유한다. `BookScannerRuntimeAdapter`가 scan session별 engine을 생성·freeze·close한다. Application thread가 `scanner.poll → engine.poll → camera.read/analyze/identity recognition`을 동기 호출한다. 별도 single-worker executor는 선택된 spread의 heavy preparation에 사용되며 acquisition worker가 아니다 (`engine.py:118,124,347,485`).

**정상 전이.** IDLE→ARMING→SEARCHING/SETTLING→VERIFYING_IDENTITY→PROCESSING_CANDIDATE→READY_FOR_SERVER_PREFLIGHT→UPLOADING(재시도 시 REMOTE_RETRY)→durable receipt 후 DELIVERY_CONFIRMED/accepted identity→WAITING_FOR_PAGE_CHANGE→충분한 새 identity와 visual 또는 coherent numeric corroboration→SEARCHING. 마지막 판정은 같은 프레임의 L/R artifact를 선택하는 조건과 다르며, capture 완료/READY를 뜻하지 않는다. Freeze는 새 capture를 멈추고 pending delivery를 보존해야 한다. S-02의 queued/retrying/rejected/confirmed artifact identity 구분을 그대로 유지한다.

**Queue/backpressure.** Candidate window와 단일 processing future/pending artifact로 영상 처리가 제한된다. HTTP는 pull 방식이며 outstanding snapshot은 호출당 1개다. FIFO를 늘리는 방식은 부적절하다. Collector는 unique frame identity N=5를 수집한다. hard rejection은 collector를 reset하며, 반복 timeout도 unknown을 기록하고 다시 시작한다. 이 동작은 queue 용량 문제와 slow-source throughput 문제를 분리해서 봐야 한다.

**Ordering.** Same-frame L/R, unique observation, accepted reference는 durable receipt 이후만 등록, stale/cancelled preparation은 publish 금지. Receipt 없는 candidate를 accepted bank에 넣거나 page-change 추정을 durable completion으로 안내할 수 없다. 재시도 중 마지막 성공 frame을 새 frame ID로 재사용하면 N=5 의미가 깨진다.

**Timeout/cancel.** IP profile의 snapshot timeout과 identity collection 8초는 별개다. HTTP timeout 인자는 전체 acquisition+decode+recognition wall deadline을 확인하는 코드가 아니다. 3회 decode retry는 한 `read()` 내부에서 동기 수행한다. Identity timeout은 acquisition 전 `now`로 검사하고 관찰 결과에는 completion-time deadline을 전달하지 않는다 (`opaque_identity.py:134,151,213`). 기존 재현에서 관찰당1.9초이면 9.58초에 N=5 통과, 2.5초이면 네 개씩 모이고 reset되어 20회 뒤에도 대기했다. 이는 8초 값을 바꿀 근거가 아니라 **8초가 무엇을 제한하는지와 생산 source 시간이 적합한지 먼저 확정할 근거**다.

CP-I1은 실제 engine lock 안의 `read()`를 barrier로 정지시켰다. queued CONFIRM LONG은 미처리이고 다른 thread에서 호출한 cancel도 lock에서 대기했다. 해제 후 처리·정리됨을 확인했다. 50ms 관찰값은 구조적 의존성 증명이며 live latency 측정이나 새로운 SLA가 아니다. `cancel_latency_ms`는 cancel 진입 후 측정하므로 **button 도착→cancel lock 획득 전 대기**를 포함하지 않는다.

**Errors.** C2에서 timeout/401/503가 동일 SnapshotTransportError→generic engine exception→FRAME_DECODE_FAILED→SESSION_ERROR→ScannerEvent.FATAL→Coordinator fatal이 된다. Adapter 자체 poll/mapping 실패는 별도 FatalPortError 경로다. 인증/TLS/설정 오류는 permanent로 별도 노출하고, 재시도 가능한 일시 transport 오류를 bounded 상태 전이로 다뤄야 한다. 현재 코드에는 이 분류가 없다. 원인을 숨기는 webcam fallback은 runtime factory에 없으며 추가하지 않는다. C3는 WAITING_FOR_PAGE_CHANGE의 unknown/reset 시 guidance event가 없어 downstream 오디오가 안내할 수 없는 producer 결함이다. Guidance를 새로 emit해도 실제 playback 완료는 별도다.

**종료/reconnect.** Engine cancel은 active job identity를 무효화하고 camera.stop, future.cancel 또는 후속 discard로 간다. close는 executor `shutdown(wait=False)`이므로 실행 중 preparation의 실제 종료 완료와 같지 않다. Adapter close 뒤 완료될 future의 artifact 정리도 D-C에서 시험해야 한다. Source stop은 Session을 닫지만 bound fetcher를 유지한다. Production adapter는 새 session마다 새 engine을 만드는 경로이므로 이 관찰만으로 실제 Session leak/reopen failure를 확정하지 않는다. Retry 설계가 source 재사용을 도입한다면 이 owner 문제를 먼저 처리해야 한다.

**Completion/fidelity.** HTTP200/decoded frame=acquired; candidate selection=local accepted candidate; outbox persistence/V4 receipt=durable; parser+finalize READY=readable revision; physical observation은 이 subsystem 밖이다. H1은 production module과 live source를 사용했으나 console controls였다. H2/H3R은 existing READY로 camera 전체를 생략했고 H3도 live capture부터 시작하지 않았다. 이들로 camera+physical input cancellation을 입증할 수 없다.

## 4. DeviceApplication input scheduling 계약

**책임과 owner.** Application만 semantic input dispatch, hold-repeat, Coordinator poll, committed snapshot presentation을 순서대로 수행한다. Coordinator가 catalog/mode/scan/reading state와 S0 operation identity를 소유한다. Console worker와 STM worker는 DeviceInputEvent를 만들 뿐 Coordinator를 off-thread 변경하지 않는다.

**전이/ordering.** start→step 반복→stop. 각 step은 submitted queue+controls.poll drain→physical edge/command 처리→physical input이 없을 때만 due repeat 최대1개→coordinator.poll→braille/audio presentation이다. DOWN A는 즉시 한 command와 hold를 시작하고 R은 hold를 해제한다. READING 명령은 synchronous S0 호출 전에 audio interrupt를 요청한다. Committed snapshot의 동일 focus/generation을 두 presenter가 받으며 각 Python Exception은 서로 독립적으로 containment된다 (`application.py:175`). 동시 physical actuator/audio 완료를 보장하는 barrier는 아니다.

**Queues/backpressure.** `submit_input`은 unbounded SimpleQueue 전체 drain이다. Console도 문자열 SimpleQueue 전체 drain이며 timestamp는 physical edge가 아니라 poll 시점이다. Production STM 경로는 normal128/release별도/한 poll16이다. Production에서 무한 scripted input을 넣는 harness와 실제 GPIO 입력량을 같은 증거로 취급하지 않는다. 다만 accepted 큐의 age와 각 batch의 synchronous S0 비용은 합산될 수 있다. `poll_interval=20ms`는 sleep 값이며 최대 input response time이 아니다.

**Timeout/cancel/errors.** Application 자체 turn deadline이나 command preemption은 없다. HTTP/recognizer 반환 전에는 mode/CONFIRM, audio interrupt도 dispatch되지 않는다. 기존 slow-S0 release test는 해당 호출이 끝난 다음 step에서 release를 먼저 읽어 repeat를 멈추는 계약을 검사한다. B-host로 release보다 늦게 A가 반환되면 이 보장이 깨진다. Scanner FatalPortError는 handled fatal로 전파되고 RecoverablePortError는 recoverable state가 된다. STM worker의 unexpected exception은 `controls.poll`에서 RuntimeError로 나오며 presentation containment와 다르게 app run을 탈출한다. 이를 숨기는 blanket catch는 제안하지 않는다.

**종료/reconnect.** Hold cancel→Coordinator stop→Scanner close→host closeables; 동일 controls/presenter는 id로 한 번 닫는다. Outer finally는 scanner failure에도 host close를 시도하지만 host close loop 내부의 한 close exception은 이후 resource 정리를 건너뛴다. Production에서 그 exception이 발생한 incident 증거는 없으므로 probable lifecycle risk로만 두고 T2/audio shutdown fault injection에 포함한다. Application은 stop 뒤 restart 불가, 재시작은 새 composition이다. C0 reconnect는 poll-driven, STM reconnect는 worker-driven으로 서로 다른 owner다.

**Completion/fidelity.** ACK는 dispatch 전 accepted signal이다. `handle_input` 완료는 semantic command 처리이며 durable S0 상태의 의미는 S0 response 계약에 따른다. `_present` 반환은 output 요청일 뿐 speaker/servo 완료가 아니다. H1/H2 console은 이후 semantics를 보존하지만 hold edge generation/ACK/firmware debounce를 우회한다. H3 physical V3와 H3R physical V2 SHORT는 별도 evidence다. D-C의 계측 없이는 이 scheduling이 정식 live demo 입력 응답을 충분히 보장한다고 판정할 수 없다. 새로운 전역 scheduler 필요성도 아직 확정하지 않는다.

## 5. Reading audio lifecycle 계약

**책임과 owner.** `ReadingAudioController`는 session/generation/epoch, system cue priority, active job과 pending list를 소유한다. Worker 한 개가 authenticated resource fetch/cache/play를 수행한다. Resource cache는 lock-protected LRU이다. `SoundDeviceWavPlayer`는 stream을 만들지만 native operation owner가 단일하지 않다: worker가 create/start/write/stop/close, input thread가 `stop→abort`, application shutdown thread가 controller.close 및 player.close를 수행한다.

**정상 전이.** IDLE→PENDING→FETCH/CACHE_HIT→PLAYING→COMPLETED; supersede→epoch invalidation→cancelled; recoverable resource/playback error→FAILED; close→closed/no new job→worker termination→native resource release이어야 한다. 현재 마지막 두 단계의 순서는 충분히 확인되지 않는다.

**Queue/backpressure.** Pending은 명시적 capacity가 없는 list다. 그러나 현재 producer에서 reading은 전부 supersede, catalog/screen/guidance/process는 group replacement, 나머지는 고정 cue와 dedupe이므로 list라는 이유만으로 무한 backlog defect를 선언하지 않는다. 한 active job과 우선순위 선택을 유지한다. Cache/HTTP byte 상한은 보존하고 capacity 확대나 cue 제거로 문제를 숨기지 않는다.

**Ordering.** Old epoch 취소가 new stream에 적용되지 않아야 한다. 한 native stream의 start/write/abort/stop/close는 valid lifetime 안에서 합의된 owner가 수행해야 한다. Latest generation만 completion을 emit해야 한다. A2의 publish/notify 뒤 broad `stop()`은 cached/instant replacement가 시작된 뒤 새 stream을 abort할 수 있다. `_is_current` epoch 검사는 그 job 자체가 current일 때 발생하는 이 오류를 막지 못한다. A1의 pointer lock은 native 호출 중첩을 막지 못한다.

**Timeout/cancel.** HTTP는 chunk 사이 cancellation을 확인하지만 blocking opener/read 내부는 즉시 취소하지 못한다. Player는 chunk마다 cancelled를 보지만 native write/drain 동안의 cancellation을 별도 thread abort에 의존한다. `close()`의 30.5초 join 뒤 `is_alive` 확인 없이 playback.close/cache.clear를 수행한다. Join timeout은 owner 종료 완료 신호가 아니다. Native write 전체에 mutex를 걸면 input stop이 write 끝까지 막힐 수 있어 기존 'thread-safe, immediate interruption' 주석과 사용자 interruption 요구를 입증하지 못한다.

**Errors.** Authenticated HTTP adapter는 malformed ref/type/digest/4xx를 permanent, transport/5xx와 일부408/429를 retryable로 분류한다. Retryable 표시는 자동 재시도 성공 보장이 아니며 worker는 FAILED feedback 후 다음 job을 기다린다. Same snapshot key dedupe가 있으므로 즉시 반복 present만으로 refetch하지 않는 점을 regression에 명시해야 한다. Python failure containment와 native access violation은 다르다. 두 crash의 exact root는 계속 insufficient_evidence이며 A1 수정으로 해결된다고 단정하지 않는다.

**Shutdown/re-entry.** interrupt는 epoch/pending/key를 무효화하지만 active worker 종료를 기다리는 handshake가 없다. `present(None)` 자체는 session/cache/key만 비우고 interrupt하지 않는다. 정상 reading exit의 application interrupt/system cue와 함께 검증해야 하며 port를 분리 호출하는 harness와 혼동하지 않는다. 새 controller는 새 worker/cache로 시작하고 stable cursor 복구는 S0 책임이다. Closed old worker가 late callback/resource에 접근하지 않아야 한다.

**Completion/fidelity.** Fetch 성공은 bytes/digest/WAV 검증, playback_started는 play 호출 직전 event, playback_completed는 current epoch의 play 반환 뒤 event다. 정상 adapter의 stop/drain 반환은 software playback 종료 근거이며 사용자가 실제 speaker에서 들은 사실은 별도 관찰로 기록한다. H1/H2/H3는 production audio, H3R 일부는 disabled다. SSH/scheduled task의 Python entrypoint 동일성만으로 interactive desktop/audio device context가 같다고 할 수 없다. 다음 native test는 host API/device/session을 기록해야 한다.

**구조 판정 이유.** A2의 queue publication은 기존 arbiter 내 local correction이 가능하다. A1은 단순 lock 위치를 바꾸기 전에 `stop`이 어느 job/stream을 취소하고 누가 native lifecycle을 끝내는지 결정해야 한다. 외부 port API를 유지하더라도 이 내부 owner/handshake 변경은 architecture change로 취급한다. D-A 승인 전 callback 전환, 새 audio process, dependency upgrade, interruption 제거는 하지 않는다.

## 6. STM host transport 계약

**Owner/전이.** I/O worker가 serial open/read/write/close를 독점한다. DISCONNECTED→bounded backoff→OPEN→HELLO1/2/3→CONNECTED→I/O failure→forced DOWN release/close/backoff. Boot namespace와 connection epoch가 reboot sequence 재사용을 분리한다. Application `present`는 lock 아래 latest desired frame/version 한 칸만 갱신한다.

**Queues/backpressure.** Normal input128, release SimpleQueue, poll 최대16, dedupe sequence window256. Full이면 새 non-release sequence에는 NACK BUSY; duplicate에는 ACK; release는 normal queue 포화와 독립적으로 수락한다. Last-wins FRAME coalescing은 stale intermediate visual output을 줄이지만 물리 적용 ACK를 기다리는 backpressure는 아니다. Serial write short count는 error로 reconnect한다.

**Ordering.** 한 worker가 ACK/FRAME bytes를 순서대로 쓰므로 host 내부 writer interleave를 막는다. OS write의 성공은 STM 전체 line 수신을 증명하지 않는다. B-host는 release-first drain 후 현재 batch만 sort하여 이전 A를 뒤 batch로 남긴다. Release priority를 제거해 backlog 뒤에 묻거나 A/R 의미를 SHORT로 바꾸는 수정은 허용하지 않는다. Accepted semantic order와 긴급 hold cancellation을 모두 보장하는 local merger/fence가 필요하다.

CP-H1에서는 intended `NAV,D,A,78\n`을 fake `readline`이 `NAV,D,A,7`/`8\n`으로 반환하자 ACK7과 sequence7 A가 생성됐다. Installed Windows serial.read는 timeout 시 short read를 허용한다. 현재 worker는 `.strip()` 후 newline 여부를 검사하지 않는다. 원문 bytes를 바꾸지 않아도 잘못된 sequence를 수락할 수 있다는 confirmed local defect다. H1/H2/H3 원시 trace에서 이 분할이 실제 발생했다는 주장은 하지 않는다. Firmware로 보내는 FRAME corruption root와도 방향이 다르다.

**Timeout/cancel/error.** Config read/write timeout20ms와 reconnect backoff가 있다. `readline` 호출 단위와 protocol record boundary는 다르다. OSError/UnicodeError는 connection reset; unexpected worker error는 poll/present 시 surfaced. Stop event+wake+bounded join으로 종료하며 join 뒤 alive 결과를 보고하지 않는다. Driver가 timeout 계약을 지키는 정상 경로와 stalled close는 구분하여 시험한다.

**Reconnect/completion/fidelity.** Rehandshake 시 down hold release, epoch/dedupe reset, 최신 FRAME 재전송. ACK sequence=host queue admission/dedupe acceptance이며 crash-safe durable input journal은 아니다. FRAME write=OS accepted bytes, parser acceptance/PCA bus write/physical dots는 별도다. H2 paced byte 시험은 host worker를 우회했고 H3R의 intermediate-frame suppression도 production last-wins workload와 다르다. H3 production의 V3 A/R 및 H3R `NAV,D,S,2` V2 SHORT를 서로 대체하지 않는다.

## 7. Firmware RX / parser / PCA application 계약

**Owner/정상 전이.** `main.c` main loop가 UART1 RX, host line parse, control queue/retry, GPIO debounce/edge, PCA I2C writes와 debug UART를 모두 수행한다. HELLO3→ACK handshake(실패 시2/legacy)→고정 lever state 전송→두 pump 사이 GPIO/control service. Complete FRAME→parse→requested nav/cells→PCA update→debug state. IRQ/DMA RX owner는 현재 이 경로에 없다. `stm32f4xx_it.c`의 USART1 IRQ servicing을 확인하지 못한 것이 아니라 이 구현에 handler가 없다.

**Queues/backpressure.** RX line256 bytes, pump64 byte budget, HAL receive1byte/1ms. Control FIFO16와 in-flight1, V3 DOWN release용1slot 예약, ACK500ms/retry3. Queue full은 debug 후 false 반환이고 main-loop button call은 반환을 재전송 큐로 보존하지 않는다. Host FRAME에는 firmware admission/applied ACK나 flow control이 없다. Main loop는 incoming FRAME를 처리하면서 다음 FRAME 수신 서비스를 중단할 수 있다.

**Ordering/atomicity.** Newline 전체 검증 전 어떤 nav/cell도 commit하면 안 된다. 현재 parser는 숫자15개 읽은 뒤 nav_state를 먼저 변경하고, cell range를 순회 검사하면서 current_cells를 차례로 변경한다. 뒤 cell이64 이상이면 reject하면서 일부 requested state는 이미 달라진다 (`main.c:748–764`). 또한 strtok는 빈 필드를 보존하지 않고 strtoul conversion의 범위 검사가 제한된다. RX overflow는 discard-until-newline 대신 length=0만 하여 suffix를 새 FRAME로 해석할 수 있다. 이런 source risk는 malformed input에서 fail-closed 계약 문제이며 정상 FRAME grammar를 바꿀 이유가 아니다.

**Timing/cancellation.** Debug print, control TX, I2C timeout100ms, servo4개 변경마다100ms delay가 같은 loop에 있다. 20개 모두 변경하면 batch delay만500ms다. Pump64 budget은 서비스 시간 상한이 아니다. 긴 적용 중 도착한 최신 FRAME/ACK/GPIO release는 처리 지연될 수 있다. 적용 도중 latest generation으로 전환하는 cancellation 상태기계는 없다. 이 사실만으로 HC-05 손상 vs UART ORE vs 전원/noise를 구분할 수는 없다. 필요한 계측 없이 DMA가 답이라고 결론내리지 않는다.

**Errors/lifecycle.** UART receive error는 disconnect/reset control transport; line format error는 debug; ACK 소실은 동일 seq retry 후 disconnect. PCA error는 `Motor_SetState` HAL_OK일 때만 cached motor state를 갱신하지만 전체 ApplyBrailleFrame은 void, ParseAndApplyFrame은 bus 실패에도 success1을 반환한다. 요청을 다시 적용할 기회와 failed channel 상태가 외부로 명확히 전달되지 않는다. Rehandshake는 control sequence와 RX line을 reset하며 새 lever state를 보낸다. Host close가 physical clear나 torque-off를 보장하는 protocol은 아니다. 임의 새 clear packet/servo LUT 변경을 제안하지 않는다.

**Completion/fidelity.** `BT RX`=debug 시점에 line을 얻음; parser success=문법 경로 수락; current_cells=요청 값; current_motor_state=HAL_OK였던 command cache; PCA bus 성공=register write 성공; servo 이동·점자 상태=물리 관찰. 어떤 debug print도 마지막 단계를 대체하지 않는다. H2/H3R paced 성공은 수신 경로 timing 민감성을 좁혀 줄 뿐 UART 구조나 PCA 적용 완전성을 증명하지 않는다. Firmware flash identity와 실제 binary/map, USART counters, direct UART 대 HC-05 bytes, I2C/pulse/physical mapping이 남아 있어 subsystem은 insufficient_evidence다.

## 8. CLI fatal propagation / tooling 계약

**Owner/전이.** CLI가 config/initial mode/composition과 process exit를 소유하고 Coordinator가 domain fatal을 발생시킨다. 정상 run→STOPPED→cleanup→exit0와 fatal→terminal outcome→cleanup→nonzero가 구분되어야 한다. 현재 T2는 event로만 fatal을 보내고 STOPPED로 전이하여 CLI가0을 반환한다. New terminal owner를 추가할 필요 없이 Coordinator에 outcome을 유지하고 CLI가 읽도록 할 수 있다.

**Queue/ordering.** 별도 terminal queue가 없다. Fatal outcome을 latch한 뒤 cleanup과 exit까지 보존해야 한다. Feedback 출력 예외나 cleanup 예외가 원래 fatal 이유를 덮지 않아야 한다. 로그에 fatal이 있어도 launcher/supervisor의 exit0이면 성공 신호가 잘못된다.

**Timeout/error/shutdown.** CP-T1에서 실제 `_fatal → app.stop` 실행은 scanner와 controls는 닫고 connectivity.stop은 생략했다. `Coordinator.stop`의 STOPPED early-return 때문이다. Connectivity supervisor는 thread가 아니라 poll-driven이며, 누락되는 것은 best-effort presence disconnect와 local STOPPED lifecycle이다. 이 결과를 heartbeat thread leak나 DB corruption으로 과장하지 않는다. Normal stop은 idempotent여야 하고 fatal state와 cleanup-done 상태를 동일 bool/state로 대체하지 않아야 한다. Fatal 뒤 자동 retry/reconnect를 추가하지 않는다.

**Tooling/fidelity.** T1의 preflight는 android_ip_camera를 허용 profile로 인정하지 않거나 camera probe에서 OpenCV index0를 연다. Production runtime factory는 IP source를 선택한다. 기존 factory/config 해석을 재사용해 source identity를 맞추는 local correction이며 strict source/auth/TLS 정책 변경은 필요 없다. CLI production module 사용과 custom H2/H3R composition, SSH/scheduled-task launcher context를 계속 구분한다. `-NoExit` shell/tee/scheduled task 완료는 child exit와 별도로 기록하고 기존 evidence script는 덮어쓰지 않는다.

**Completion.** Fatal event accepted by sink, 로그 flush, child exit code, task 종료 상태는 각기 다르다. 어느 것도 durable V4/READY/speaker/physical completion을 대신하지 못한다.

## 9. 결함별 local/structural 재판정 및 새로운 evidence

| ID | 기존/이번 증거에 따른 분류·severity | Architecture 결론 / 위반 invariant / regression gap |
|---|---|---|
| A1 | confirmed_product_defect, 기존 P1 유지; exact native AV 원인은 insufficient_evidence | Stream owner와 close/cancel handshake 설계가 먼저 필요. 단순 pointer lock patch로 닫지 않음. Overlap10/10 fake-native 증거는 실제 driver 원인 확정과 별개 |
| A2 | confirmed_product_defect, 기존 P1 | Arbiter publication ordering의 local correction. 단 A1 stop target 계약에 종속. 새 job의 cached/instant start와 old stop 사이 adversarial scheduling이 기존 tests에 없음 |
| B-host | confirmed_product_defect, 기존 P1 | 기존 worker+queue 계약 복구. Cross-batch edge ordering과 release safety를 함께 검사. 새 scheduler/protocol 불필요 |
| C2 | confirmed_product_defect, 기존 P1 | Error taxonomy와 bounded transient recovery는 기존 engine/adapter 내 local 후보. 동기 retry loop 추가로 input stall을 늘리는 해법은 금지. Cancellation/clock 관련 구조 필요성은 D-C 결과에 종속 |
| C3 | confirmed_product_defect, 기존 P1 | Producer guidance emission의 local correction. Existing guidance arbiter/rate limit 활용, timeout을 success로 바꾸지 않음 |
| T1 | confirmed_product_defect, 기존 P1 | Preflight composition routing local. Runtime webcam fallback defect로 확대하지 않음 |
| T2 | confirmed_product_defect, 기존 D01 | Existing Coordinator terminal outcome + idempotent cleanup + CLI mapping local. Exit code 한 줄만 바꾸는 scope로는 CP-T1을 놓침 |
| CP-H1 신규 | confirmed_product_defect; P1 수정 후보, 기존 incident severity 상향 없음 | Partial line에서 잘못된 sequence7 accepted/ACK 재현. Complete-line buffer/overflow recovery는 host worker 내부 local. Whole-line fake test gap |
| CP-T1 신규 인접 | confirmed_product_defect; T2/D01 lifecycle 확장, severity 상향 없음 | Fatal STOPPED가 cleanup을 생략. 실제 method+spy 재현. Normal-stop-only test gap |
| CP-I1 신규 확인 | probable_product_risk; live incident root는 insufficient_evidence, P1 위험 범위 유지 | 동기 read가 input/cancel을 막는 구조는 재현. 이 구조가 사용자 경로에 허용되는 실제 지연인지 미측정. Poll sleep을 latency SLA로 오해하면 안 됨 |
| Firmware overflow/partial commit/PCA result | probable_product_risk, 기존 P1 adjacent; board 원인 insufficient_evidence | Source와 제한된 모델 증거. RX overflow suffix/atomic rejection/failed bus command에 대한 compiled HAL test gap. D-F에서 확인 후 local 또는 structural로 분기 |
| Audio close join / host close fanout / late preparation | probable_product_risk, 신규 severity 상향 없음 | Concrete trigger는 blocking I/O가 join을 넘김, close exception, 실행 중 future 후완료. Owner 종료·late resource discard 확인 tests가 부족. 관련 lifecycle packet에서만 검증 |

기존 liveness/profile mismatch, native DLL/host API, Bluetooth/UART corruption의 competing hypotheses는 유지한다. 물리 clear residual, required control input, mode lever solder는 **hardware_or_wiring** 또는 해당 측정 부족으로 남긴다. H3R bootstrap cursor 가정/FRAME suppression/TTS off는 **test_harness_artifact** 또는 명시적 boundary bypass이며 product defect와 분리한다. Empty braille snapshot은 해당 empty focus에서 **expected_behavior**다. Content P1 waiver/Deferred와 무관한 정리는 **out_of_scope_observation**으로도 신규 작업화하지 않았다.

## 10. 검증·진입 순서와 결론

1. 현재 source/evidence identity를 보존한 채 D-A owner 설계, D-C timing/cancel 계측 정의, D-F receive/apply 계측 설계를 먼저 검토한다. L-T/L-B/L-C3은 다른 subsystem 구조 결정 없이 독립 review 가능하다.
2. 승인된 local packet마다 현재 defect 재현을 failure assertion으로 전환해 targeted regression을 수행한다. 다음으로 해당 subsystem tests. Source를 바꾸지 않은 이번 pass의 probe PASS는 결함 재현 성공이다.
3. A1의 새 lifecycle은 fake adversarial interleavings→실제 interactive Laptop native-only→HTTPS-only→결합 순으로 검증한다. D-F는 compiled parser/HAL fixture→별도 보고된 bounded hardware capture→normal production rate로 검증한다.
4. Local/subsystem 완료 후 기존 G3-A software regression을 새 source identity로 재실행한다. 기존 G3-A PASS를 소급 무효화하거나 새 hardware PASS로 취급하지 않는다.
5. Fresh H1: live Android로 두 spread/durable receipt/CONFIRM LONG/fresh READY와 guidance, source/transient/cancel evidence. Fresh H2: existing READY S0/audio/normal-rate STM/PCA, generations와 실제 적용 분리. Fresh H3: production entrypoint/physical V3 A-R/hold-release/reconnect/audio/physical dots. Console·paced·suppressed intermediates는 보조 isolation만 인정한다.
6. Hardware/wiring/calibration blocker와 각 위 항목이 닫힌 뒤 H4: physical controls→live pages26/27,28/29→fresh READY→same focus/generation audio+physical braille→exit/re-entry/restart stable cursor. 정상·실패 모두 evidence를 보존한다.

**현재 H4 = BLOCKED. Integration ready 선언 불가.** Architecture_change_required(audio)와 insufficient_evidence(camera/input/firmware)가 남았다. 새 architecture layer, threshold/8초/protocol/UART/LUT/pin/auth/TLS 변경은 모두 0. Product source modification count **0**.
