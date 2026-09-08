# H1/H2/H3 Software Stabilization Proposal — 2026-09-08

## Decision

고비용 모델을 사용한 새 bounded stabilization pass는 타당하다. 다만 H1/H2/H3의 모든 FAIL을 하나의 수정 묶음으로 처리하지 않는다. 현재 evidence는 세 개의 독립된 software failure boundary를 가리킨다.

1. Windows audio stream의 rapid supersession/interrupt 수명주기
2. STM32 USART1의 production-speed line 수신 무결성
3. Android live snapshot의 page-change 수집 시간, transient recovery, timeout guidance

각 workstream은 별도 재현, 최소 수정, targeted regression, 실제 장치 재검증을 가져야 한다. `gpt-6-astra`의 `ultra` reasoning은 1번의 native crash 분석과 2번의 firmware concurrency 설계에 우선 배정하고, 3번은 `high` 이상으로 충분하다. 단순 guidance event와 CLI exit code 수정만을 위해 ultra 비용을 쓰는 효율은 낮다.

현재 제품 source는 수정하지 않았으며, 이 문서는 수정 승인이나 구현 결과가 아니다.

## Evidence-based classification

| Issue | Stage | 현재 분류 | Software pass 포함 | 근거 |
|---|---|---|---|---|
| `RAPID-READING-SUPERSESSION-NATIVE-CRASH-P1` | H3 | confirmed P1 | 포함, 최우선 | 서로 다른 두 실행에서 `0xc0000005`; `ucrtbase.dll` 및 `libcrypto-3.dll`; active playback interrupt 직후 Python 전체 종료 |
| `STM-FRAME-TRANSPORT-INTEGRITY-P1` | H2/H3 | confirmed P1 | 포함, 최우선 | production burst와 3 ms/byte에서 문자/field 유실, 20 ms/byte에서 exact parse; parser/PCA/actuator downstream은 도달 |
| `LIVE-PAGE-CHANGE-LIVENESS-P1` | H1 | confirmed P1 | 포함, 먼저 config-vs-code 진단 | N=5는 유지됐지만 8초 안에 blocking acquisition/recognition으로 충분한 관측을 모으지 못함 |
| `HTTP-SNAPSHOT-TRANSIENT-FATAL-P1` | H1 | confirmed P1 | 포함 | terminal `frame_decode_failed` 직후 strict read 성공 및 10/10 burst 성공; transient transport failure가 전체 scan을 종료 |
| `POST-FIRST-SPREAD-GUIDANCE-SILENCE-P1` | H1 | confirmed P1, 조건부 waiver | 포함, 작은 후속 수정 | page-change timeout은 diagnostic decision만 내고 guidance event를 생성하지 않음 |
| `ANDROID-PREFLIGHT-SOURCE-P1` | H1 | tooling P1 | 포함 가능, 낮은 우선순위 | preflight가 configured Android source 대신 Laptop webcam 640x480을 검사 |
| `FATAL-EXIT-STATUS-D01` | H1 | Deferred | 작은 후속 수정 후보 | fatal event 이후 CLI가 0을 반환하여 supervisor가 성공으로 오판 가능 |
| `ACTUATOR-CLEAR-RESIDUAL-P1` | H3 | confirmed physical-output P1 | 조건부 제외 | exact zero FRAME이 2/2 파싱되고 모터도 움직였으나 동일 돌출 잔류; 기계적 zero/horn/cam 또는 per-channel calibration 가능성이 큼 |
| `STM-REQUIRED-CONTROL-INPUT-P1` | H3 | confirmed integration P1 | 제외 | PAGE NEXT 무신호, CONFIRM 위치에서 PAGE PREVIOUS, MODE lever 납땜 파손. 먼저 continuity/pin trace 필요 |
| `MODE-LEVER-SOLDER-P1` | H1/H3 | hardware P1 | 제외 | 물리 접점 파손 |
| Android phone battery/network loss | H1 | environment | 제외 | 장치 방전과 endpoint 단절 자체는 product defect가 아님 |

물리 DOWN 한 번에 대해 `NAV,D,S,2 -> ACK,2 -> page 1/node 9/generation 129 -> exact ten-cell FRAME -> visible movement`가 통과했다. 따라서 버튼부터 reading 및 actuator까지의 기본 경로 전체를 재설계할 근거는 없다.

## Workstream A — audio supersession native crash

### Violated invariant

새 navigation 입력은 이전 음성을 취소할 수 있어야 하지만 process를 종료하거나 다음 generation의 audio/FRAME을 손상하면 안 된다. stream의 `write`, `abort`, `stop`, `close`는 한 번씩 정해진 소유 순서로 실행되어야 한다.

### Current code hypothesis

`SoundDeviceWavPlayer.play()`의 worker가 `stream.write()` 후 finally에서 `stop/close`를 수행하는 동안, 다른 입력 thread의 `stop()`이 같은 stream에 `abort()`를 호출할 수 있다. Python lock은 `_stream` 포인터 교환만 보호하며 native stream lifecycle 전체를 직렬화하지 않는다. 두 crash의 fault module이 다르므로 PortAudio 한 함수로 단정할 수는 없지만, cross-thread native object teardown race가 가장 강한 가설이다.

### Required diagnosis

1. 두 crash dump의 thread stack을 WinDbg/cdb와 가능한 symbol로 확인한다.
2. 실제 `sounddevice` backend에서 짧은 WAV와 긴 WAV를 빠르게 교체하는 bounded reproducer를 만든다.
3. fetch, playback write, interrupt, controller close를 각각 분리해 어느 조합이 crash를 만드는지 확인한다.
4. fake stream에 lifecycle event/barrier를 넣어 `abort`와 `stop/close`가 겹치는 현재 동작을 결정적으로 재현한다.

### Expected minimal fix

native stream lifecycle의 소유자를 playback worker 하나로 제한하는 방향이 우선이다. interrupt thread는 generation/epoch cancellation과 wakeup만 전달하고, 실제 abort/stop/close는 같은 owner context에서 순서대로 수행한다. 즉시 중단이 callback stream을 요구한다면 callback도 동일한 command/state machine 아래 둔다. `close()`는 worker 종료와 native stream 해제를 확인한 뒤 cache/resource를 닫아야 한다.

전역 audio architecture 교체, backend 임의 변경, interrupt 기능 제거는 예상 범위를 넘는다.

### Acceptance

- deterministic lifecycle unit test
- 실제 Windows sounddevice의 bounded rapid supersession 반복에서 crash/noise 0
- 마지막 generation audio만 완료되고 이전 generation completion event 0
- DOWN/UP/CONFIRM interruption 및 application shutdown 회귀
- H3 실제 speaker + physical DOWN 재시험

## Workstream B — STM FRAME transport integrity

### Violated invariant

9600 baud production write로 전달된 newline-delimited ACK/FRAME은 byte 유실 없이 한 줄로 재조립되어야 한다. FRAME grammar, ten-cell payload, V3 ACK/dedupe semantics는 유지돼야 한다.

### Evidence interpretation

정상 burst와 3 ms/byte는 `FRAME`을 `FAME`, `FRA` 등으로 손상시켰고 20 ms/byte는 exact parse됐다. 같은 exact frame이 파싱된 뒤 PCA와 모터가 작동했다. 따라서 host formatter나 braille renderer보다 STM polling receive가 first failing boundary다.

현재 firmware는 main loop에서 `HAL_UART_Receive(..., 1 byte, 1 ms)`로 최대 64 byte를 polling한다. 같은 loop에는 debug UART, I2C write와 servo batch delay가 있다. 이 구조는 수신 중 main loop가 지연될 때 USART overrun/byte loss가 발생할 수 있다.

### Required diagnosis

1. host가 ACK와 최대 길이 FRAME을 back-to-back으로 보내는 production-rate fixture를 만든다.
2. actuator 변경 0개/일부/20개 조건에서 유실률을 분리한다.
3. UART ORE/FE/NE 상태와 line buffer overflow/recovery counter를 COM5에 기록한다.
4. HC-05를 우회한 direct UART와 HC-05 경로를 각각 한 번 비교해 radio와 MCU receive를 분리한다.

### Expected minimal fix

USART1 RX를 interrupt 또는 DMA circular ring buffer로 받아 main loop의 parser가 완성된 newline frame만 소비하도록 한다. ISR/DMA callback은 byte enqueue와 overflow 표지만 담당하고, parsing/PCA 동작은 main context에 남긴다. overflow 시 현재 줄을 폐기하고 다음 newline에서 재동기화하며 explicit diagnostic을 남긴다.

host의 20 ms/byte pacing은 약 1초 이상 frame latency를 만들 수 있어 진단 workaround로만 유지한다. baud, grammar, ACK, sequence, ten-cell encoding은 바꾸지 않는다.

### Acceptance

- production rate에서 ACK + 최대 FRAME 연속 전송 exact parse 100%
- changed 20-motor actuation 동안 뒤따르는 최신 FRAME 유실 0
- malformed/oversize line 뒤 다음 정상 line 복구
- V3 ACK/dedupe/reconnect/DOWN release 회귀
- 기존 paced fixture와 실제 physical DOWN-to-braille 재시험

## Workstream C — H1 live camera liveness and recovery

### C1. Page-change collection budget

먼저 code defect인지 integration profile defect인지 분리한다. N=5, identity decision, duplicate suppression은 바꾸지 않고 현재 engine 그대로 `opaque_identity_max_collection_ms=30000`인 진단 profile을 한 번 실행한다. repository의 desktop acceptance에도 30초 설정 전례가 있다.

- 30초에서 5개 valid observation과 `different`가 안정적으로 성립하면 8초 integration profile의 latency budget 결함으로 분류한다. 이 경우 최소 수정은 profile과 문서의 evidence-based budget 정렬이다.
- 30초에서도 collection이 반복 reset되거나 completed observation을 부당하게 잃으면 engine scheduling/time-accounting 결함이다.

engine 수정이 필요할 때는 blocking capture/analyze 시간을 숨기거나 무한 대기시키지 않는다. 관측 횟수 N=5와 전체 hard ceiling을 동시에 유지하면서, sample-in-progress와 다음 sample wait를 구분하고 completed observation을 보존하는 최소 상태 전이가 적합하다. 가능하면 capture/analyze pipeline을 전면 비동기화하기 전에 clock-controlled test로 작은 변경이 충분한지 확인한다.

### C2. Transient HTTP snapshot recovery

현재 `HttpSnapshotCameraSource.read()`는 decode failure만 3회 재시도하고 `SnapshotTransportError`는 즉시 상위 engine fatal로 전파한다. 한 번 timeout 후 성공, 잘린 JPEG 후 성공, 지속 timeout, 401/403을 구분하는 fake fetcher test가 먼저 필요하다.

최소 수정은 strict source identity를 유지하면서 connect/read timeout 및 retryable 5xx에 제한된 횟수와 bounded backoff를 적용하는 것이다. 인증 실패, 잘못된 endpoint, 지속 실패는 기존처럼 fatal이어야 한다. loss/recovery feedback과 attempt count를 evidence로 남기고 webcam fallback은 추가하지 않는다.

### C3. Silent page-change timeout

candidate verification timeout은 guidance를 내지만 page-change timeout branch는 collector만 다시 시작한다. 동일 branch에 기존 feedback path를 통한 rate-limited guidance를 추가하는 것이 예상 최소 수정이다. guidance는 `unknown`을 `different`로 승격하거나 candidate를 선택해서는 안 된다.

### C4. Preflight and exit status

- Android profile preflight는 production source factory와 같은 config를 사용해 실제 `HttpSnapshotCameraSource`, resolution, endpoint identity를 검사해야 한다.
- CLI는 normal operator stop과 coordinator fatal stop을 구분하여 fatal이면 nonzero를 반환해야 한다. `fatal_error`를 log로만 보고 exit 0을 유지하는 현재 wrapper는 supervisor contract에 부적합하다.

이 두 항목은 core H1 liveness 수정 뒤 같은 pass에 묶을 수 있으나, 독립 targeted tests를 유지한다.

### Acceptance

- N=5 유지, duplicate 0, sequence 1/2 및 ACK 1/2
- 한 번의 transient transport/decode failure 후 scan lineage 유지 및 recovery
- 지속 failure는 finite ceiling 뒤 fatal/nonzero exit
- page-change timeout 중 audible rate-limited guidance, false acceptance 0
- strict Android source preflight가 webcam을 열지 않음
- fresh H1에서 26/27 후 28/29 전송 및 finalize/READY

## Items that must wait for hardware evidence

### Actuator clear residual

software/firmware pass 전에 20개 motor의 top/bottom별 residual pattern, zero-state pulse, horn/cam orientation과 mechanical stop을 기록해야 한다. 모든 채널에 같은 offset이면 global state-0 angle 후보이고, 특정 채널만 남으면 per-channel calibration 또는 기구 설치 후보이며, 같은 bit position만 남으면 cam/LUT 방향 후보다. 이 측정 없이 LUT나 `SERVO_MIN_US`를 바꾸는 것은 위험하다.

### Required controls

PAGE NEXT/CONFIRM/MODE는 continuity와 실제 GPIO level을 먼저 측정해야 한다. 회로가 문서와 다를 때만 authoritative wiring map에 맞춘 firmware pin 변경을 검토한다. 현재 관찰만으로 PC0/PC1 의미를 software에서 맞바꾸면 잘못 연결된 hardware를 계약으로 고정할 수 있다.

## Recommended execution order

1. **A: audio crash** — process 전체 종료를 먼저 제거한다.
2. **B: STM receive** — 실제 braille 결과를 신뢰할 수 있게 한다.
3. **C1 config-only discrimination** — 8초/30초 비교로 H1 변경 범위를 결정한다.
4. **C2/C3**, 필요할 때만 C1 engine 수정.
5. **C4 tooling/exit semantics**.
6. 각 workstream의 targeted regression.
7. device-runtime, book-scanner, firmware 관련 subsystem regression.
8. G3-A regression replay.
9. fresh H1, H2, H3 순서의 실제 장치 시험.
10. hardware residual 및 wiring correction 뒤 H4.

한 workstream의 실패를 다른 workstream의 threshold, baud, protocol 또는 acceptance 완화로 우회하지 않는다.

## Proposed high-cost model work packets

### Packet A — native audio lifecycle

Input: 두 dump, H3 event logs, `reading_audio.py`, `adapters/reading_audio.py`, audio tests.  
Deliverable: confirmed race or falsified hypothesis, deterministic reproducer, minimal patch, targeted tests, Windows physical playback evidence.  
Stop: dump/reproducer가 다른 boundary를 가리키면 architecture 변경 전에 보고.

### Packet B — STM RX integrity

Input: H2 COM5 traces, host serial adapter, firmware `main.c`, V3 contract.  
Deliverable: measured loss mechanism, interrupt/DMA ring-buffer patch or smaller proven correction, build artifact/hash, burst and actuator-latency evidence.  
Stop: direct UART는 통과하고 HC-05에서만 실패하면 firmware redesign 전에 radio/power boundary로 재분류.

### Packet C — live camera

Input: 두 H1 run logs, strict-source probes, Android profile, source/engine tests.  
Deliverable: 8초/30초 discrimination, bounded transient recovery, timeout guidance, exact H1 rerun evidence.  
Stop: 30초에서도 실제 footer identity가 visual input 때문에 성립하지 않으면 threshold 변경 없이 capture condition으로 재분류.

## Expected final gate effect

A가 통과하면 H3의 process-stability blocker 하나가 제거된다. B가 통과하면 H2의 핵심 FAIL과 H3의 intermittent physical presentation ambiguity가 제거된다. C가 통과하면 H1의 두 번째 spread 및 operator guidance 경로를 재검증할 수 있다.

그 후에도 actuator clear residual과 required physical controls가 남아 있으면 H3/H4를 PASS로 선언할 수 없다. software pass 성공은 hardware calibration과 wiring acceptance를 대체하지 않는다.
