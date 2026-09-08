# Architecture assurance — diagnostic/design work packets

상태: **계측·설계 제안, 구현/flash/live pipeline 실행0**. [Architecture 판정](../H123_CRITICAL_PATH_ARCHITECTURE_ASSURANCE_20260908.md)과 [local packets](H123_ARCH_LOCAL_CORRECTIONS_20260908.md)를 함께 사용한다. 이 문서는 새 architecture layer의 구현 승인이 아니다.

비용은 필요한 검증 campaign의 범위 추정이며 실행 완료나 소요시간 보장이 아니다. 실측시간/장비 가용성 없이는 인일 또는 수 분 내 완료를 약속하지 않는다. Product file cap은 설계가 채택됐을 때의 상한이며, 계측 승인은 correction·flash 승인을 자동 포함하지 않는다.

## D-A. Native audio owner / cancellation / teardown

**판정:** architecture_change_required — existing audio controller/port 내부 lifecycle 경계. 새 전역 audio layer가 필요하다는 결론은 아니다. A1의 concurrent native use는 확인했고, 실제 두 AV root는 insufficient_evidence다.

**답해야 할 설계 질문**

1. 각 stream의 create/start/write/abort/drain/close를 누가 언제 수행하며 input interrupt가 어떤 epoch/stream에 적용되는가?
2. Blocking write 또는 drain이 끝나지 않을 때 cancellation responsiveness와 단일 native ownership을 어떻게 동시에 만족하는가? Mutex 대기는 해결 완료 신호가 아니다.
3. Worker가 종료됐다는 handshake 전에 close가 성공으로 반환하지 않는가? Join timeout/close failure를 어떻게 terminal diagnostic으로 보존하는가?
4. Old fetch late result, `present(None)`, system cue priority, A2 replacement activation을 같은 계약으로 다룰 수 있는가?

**계측 및 선택지**

- 먼저 stream lifecycle call에 epoch/stream ID/thread ID/enter/exit 시각을 붙인 isolated diagnostic wrapper로 overlap와 blocking 구간을 측정한다. Credential/audio text를 log하지 않는다. Fake blocked write/drain/fetch/close에서 deterministic scheduler로 재현한다.
- Installed sounddevice/PortAudio/host API/device를 고정하고 native-only local WAV 시험, HTTPS-only fetch 시험, 두 경계 결합을 분리한다. 최초 native 오류/잔존 worker/잘못된 generation 완료에서 정지한다.
- 선택지1: 기존 blocking worker가 native lifecycle을 독점하고 interrupt는 target cancellation만 전달. 채택하려면 chunk/write/drain의 실제 interruption bound가 사용자 경로를 만족함을 보여야 한다.
- 선택지2: 동일 player adapter 안의 callback/nonblocking 방식과 단일 owner control handshake. Callback RT 제약, buffer ownership, underrun/close 규칙을 먼저 명세한다. 별도 process/backend 교체는 이번 상한 초과로 새 design review가 필요하다.
- Root AV를 확정하려면 원본 C: dump를 read-only native debugger로 분석하고 symbol 상태와 stack 한계를 기록한다. 현재 module metadata만으로 ucrtbase/libcrypto/PortAudio 중 하나를 원인으로 단정하지 않는다. 분석 도구가 없으면 그 부분은 insufficient_evidence로 유지한다.

**변경 budget / migration / compatibility**

| 항목 | 상한·제약 |
|---|---|
| 지금 diagnostic | Product source0; isolated harness/evidence만. Real sound device 시험은 먼저 endpoint/context/횟수/stop/evidence 계획 보고 |
| 이후 구조 correction 후보 | Product2파일: `reading_audio.py`, `adapters/reading_audio.py`. Tests3파일 이하. 새 process/service/layer0, dependency/lockfile0 |
| 예산 초과 | Public port signature, application scheduler, server ref/auth, backend package 변경이 필요하면 설계 중단 후 새 cap 제안 |
| 호환성 | `play(resource,cancelled)/stop/close` 외부 계약과 generation/ref/cache/system cue 의미 유지. 내부 stop target/activation handshake는 변경 가능하나 interruption 제거 금지 |
| Migration | Persisted state/schema0. Native stream은 runtime ephemeral. Old/new controller를 동시에 같은 speaker owner로 실행하지 않음 |
| Rollback | Process를 정상 정리한 뒤 승인된 두 파일 diff만 baseline으로 복원. Old native lifecycle 위험도 복귀한다. DB/state/cache 증거 삭제0 |

**Exit evidence / 재검증 비용**

Single-owner 또는 검증된 serialized native contract, close exactly once, use-after-close/overlap0, generation-targeted cancel, no false completion, terminal join failure가 입증되어야 설계를 구현 packet으로 전환한다. Fake cancellation은 actual driver 안정성의 대체물이 아니다.

Targeted audio/application→device subsystem→G3-A→fresh H2 native speaker+normal FRAME→fresh H3 physical V3 rapid navigation/release/re-entry→H4 combined. H1 system cue regression도 포함. 최소 native-only/HTTP-only/combined3개 isolation campaign 및 fresh H2/H3, 최종 H4가 필요하다. Crash 재발 시 packet 완료로 처리하지 않고 root 재분리한다.

## D-C. Live acquisition과 input scheduling의 시간·취소 계약

**판정:** camera 및 DeviceApplication scheduling은 insufficient_evidence. C2/C3 국소 결함이 있다고 acquisition thread 추가가 자동 정답이 되지 않는다. 현재 poll synchronous 구조가 실제 제한된 시연에 충분한지 먼저 측정한다.

**계측 목적과 isolated 실행 조건**

- Invariant: physical/console event 도착, STM ACK, application dequeue, command dispatch, camera fetch/decode/analyze/identity 완료, cancel 요청/lock획득/resource release를 각각 측정하여 accepted input이 어디에서 대기하는지 분리한다.
- `cancel_latency_ms` 기존 값에 빠진 queue/lock 대기를 따로 기록한다. 20ms poll sleep과 snapshot timeout을 end-to-end latency로 대체하지 않는다.
- Collection start/sample start/sample end/recognizer end/valid/missing/hard-reset/decision과 accepted reference ID를 같은 monotonic clock으로 기록한다. N=5와8초를 고정하고 pages26/27→28/29 고정 구도로 관찰한다.
- Live read-only 시험이 필요하면 먼저 위 invariant, source endpoint(profile credential은 출력 금지), 표본 상한과 시간 상한, stop condition을 보고한다. Evidence 위치는 `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics\arch-camera-<fresh-id>`; production SQLite/artifact는 열지 않으며 upload/finalize0. Source는 strict Android, orientation/settings/auth/TLS 변경0.
- 취소/HTTP taxonomy는 먼저 fake boundary로 재현한다. 실제 인증 오류를 만들려고 credential을 바꾸지 않는다. 첫 unreleased resource, unexpected source, timeout budget 초과, secret 노출 가능 상태에서 정지한다.

**설계 decision gates**

1. 8초 의미를 sampling-start admission window로 할지 결과 collection deadline으로 할지 문서 계약과 실제 source에 대조한다. 현재 late fifth observation이 accepted되는 동작을 숨기지 않는다. 이 단계에서 수치·assertion을 완화하지 않는다.
2. 실측으로 source/recognizer latency, valid observation 부족, hard reset 중 first failing boundary를 구분한다. Source profile throughput mismatch만 있으면 environment_failure이며 곧바로 product scheduler 개편 사유가 아니다.
3. C2 taxonomy+기존 poll-driven retry만으로 bounded response/recovery가 가능하면 local L-C2로 진행한다. 단일 read 내부 retry를 늘려 입력 대기를 악화시키지 않는다.
4. 취소·입력 응답 계약을 만족할 수 없을 때만 acquisition/identity를 engine 내부의 단일 owner worker로 분리하는 후보를 설계한다. Mailbox는 bounded latest result1/in-flight1 후보, immutable same-frame sample 및 request/session epoch로 late result discard. Thread를 추가하는 것만으로 requests/recognizer의 실행 취소가 보장되는 것은 아니다.
5. 모든 S0/delivery/C0를 async로 바꾸거나 전역 task scheduler를 도입해야 한다면 이번 bounded scope 초과다. 먼저 실제 어느 호출이 계약을 위반하는지 제시하고 별도 예산을 받는다.

**변경 budget / migration / rollback**

| 항목 | 상한·제약 |
|---|---|
| 현재 계측 | Product0, wrapper/fake/isolated logs만. 기존 runtime source/config/evidence 보존 |
| Local correction | L-C2 product3 / L-C3 product1 상한. 같은 파일 중복 변경은 source identity별 원자적 검증 |
| 구조 후보 cap | Product4파일 이하: `video/sources.py`, `video/engine.py`, `video/runtime_composition.py`, `adapters/book_scanner_runtime.py`; 새 helper가 필요하면 이4개 budget 안에서 교환. Application/Coordinator 전역 rewrite0 |
| Migration | Datapack/outbox/receipt/identity bank schema0. Open/freeze/cancel/close caller 계약 유지. In-flight frame/future는 session epoch에 묶고 old worker 정리 후 source 재open |
| 호환성 | N/K/threshold/8초, same-frame L/R, ACK 후 accepted bank, duplicate/discard, strict source/auth/TLS 그대로. 무한 queue/retry/capture 재사용 금지 |
| Rollback | 새 worker가 완전히 정리된 뒤 source diff만 역적용. Pending durable artifact는 기존 ownership 규칙으로 보존. DB/reset/clean0. Old camera responsiveness 위험 복귀 명시 |

**Targeted / 재검증 비용**

Slow fetch/slow recognizer/slow drip-like fake, timeout near Nth result, missing/hard-reject, freeze/cancel during read/retry/preparation, late result after new session, source.close/reopen, worker failure, artifact discard race를 검증한다. Deadline assertion은 승인된 의미를 엄격히 검사하고 production 수치는 고정한다.

Book-scanner + device adapter/application subsystem→G3-A→fresh H1 전체 두 spread 및 transient/cancel→fresh H3 capture 중 physical control scheduling→H4 full. H2 existing READY는 camera 변경의 liveness acceptance가 아니며 audio/input 회귀를 확인하는 비용으로만 포함한다. 최소 live timing1개, fake fault/cancel campaign1개, fresh H1/H3 및 H4가 필요하다. 실제 timing 결과 전 구조 correction 승인 불가.

## D-F. Firmware receive service와 parser/PCA completion

**판정:** insufficient_evidence. Normal-speed FRAME corruption이 있다는 사실과 USART polling이 근본 원인이라는 결론을 구분한다. UART DMA/IRQ, servo LUT/angle/channel/pin 변경은 모두 보류한다.

**1단계 — 실행 identity와 receive 계측 설계**

- Laptop C:의 authoritative source/host config/baud와 실제 flash binary/hash/map을 대응시킨다. 현재 ELF 미확보를 PASS로 대체하지 않는다. Firmware 재flash를 identity 확인 수단으로 임의 사용하지 않는다.
- Host write bytes/time, HC-05 입력/STM UART 수신 bytes/time, RX ORE/FE/NE와 line overflow, maximum no-service interval, debug/I2C/servo batch enter/exit를 분리한다. Debug 출력 자체가 timing을 바꾸므로 hot-path blocking printf 추가는 금지하고 bounded counter/trace sampling을 설계한다.
- 동일 normal-rate packet trace를 parser-only, PCA-stub, 실제 PCA, direct UART 대 HC-05로 단계 분리한다. Paced 성공만으로 normal transport PASS를 선언하지 않는다. Direct UART를 위해 pin 변경이 필요하면 실제 배선 확인과 별도 계획 없이는 진행하지 않는다.

**2단계 — parser/PCA의 국소 확인**

- Exact current parser/RX function을 compiled host fixture 또는 HAL stub으로 실행한다. 현재 Python 모델을 compiled C 결과처럼 보고하지 않는다. Toolchain이 없으면 설치·업그레이드 대신 부족한 evidence를 보고하고 approved environment를 정한다.
- Late cell64, empty/extra token, oversized integer, prefix noise, RX overflow+valid-looking suffix를 넣고 reject 시 nav/current_cells/PCA calls 변화0인지 검증한다. 확인되면 validate-all-before-commit와 discard-until-newline은 같은 `main.c` 내 local correction으로 분리 가능하다. FRAME grammar 변경이 아니다.
- HAL failure를 특정 motor write에 주입해 parser accepted, I2C applied, cached success, physical observation을 분리한다. Request print를 applied signal로 취급하지 않는다. Channel/LUT/각도는 고정한다.

**3단계 — 구조 변경을 선택할 조건**

- UART wire는 온전하지만 RX service gap/overrun에서 first byte loss가 발생함이 확인되면 servicing 구조 변경을 설계한다. Ring buffer/IRQ, DMA, cooperative deferred application 중 무엇을 선택할지 증거·buffer bound·ownership/error recovery에 따라 결정한다. 지금 선택하지 않는다.
- RX가 온전하고 parser만 손상되면 parser local packet. PCA bus는 성공하지만 물리 clear가 실패하면 hardware_or_wiring/calibration 측정 packet으로 분리. Error를 지우거나 host inter-byte delay로 정상 동작을 재정의하지 않는다.
- Deferred PCA application을 선택한다면 requested/pending/applied state와 current frame generation, partial failure, newest frame 도착 중 적용 처리 규칙을 설계한다. 기존 FRAME에 applied ACK를 몰래 추가하거나 V3 ACK 의미를 바꾸지 않는다.

**변경 budget / migration / compatibility / rollback**

| 항목 | 상한·제약 |
|---|---|
| 현재 read-only / compiled fixture | Product source0, actual firmware flash0 |
| 별도 승인 계측 build | Product3파일 이하: `main.c`, 필요한 경우 `stm32f4xx_it.c`, `main.h`. Flash 목적/packet/stop/evidence를 먼저 보고하고 원래 binary identity 확보 |
| 이후 구조 correction 후보 | Product4파일 이하, Core Src/Inc와 필요할 경우 기존 HAL MSP/config 중 선택. `.ioc`, linker, build-system/HAL regeneration까지 필요하면 상한 초과로 새 design review. 동시 UART+LUT/pin 변경 금지 |
| Migration | RX buffer capacity·overflow policy·ISR/main ownership·boot clear를 명시. RTOS/new protocol/new architecture layer0. Old binary와 host FRAME/V3 호환 유지 |
| Rollback | 검증된 이전 firmware binary로만 복원 계획. 기존 binary/hash를 확보하지 못하면 flash/rollback 가능하다고 주장하지 않음. Host source/config/DB 변경0, evidence 보존 |

**실제 hardware 실행 전 보고할 내용**

정확한 목적과 예상 packet bytes/순서/간격/최대 횟수, 대상 cells, 현재 binary/host identity, operator stop 방법, 첫 malformed line/overrun/누락 ACK/예상 외 이동/PCA 실패/전원 이상 시 정지 조건, `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics\arch-stm-<fresh-id>` evidence 위치를 먼저 제출한다. 이는 아직 실행 지시가 아니며 실제 servo/flash/live upload는 본 pass에서0이다.

**재검증 비용**

Compiled malformed/overflow/PCA-fault fixture→host normal-rate transport fixture→receive-only board capture→PCA/physical application→host+firmware combined. 새 firmware면 V3 handshake/ACK/dedupe/A-R/retry/reconnect, legacy compatibility까지 재검증한다. G3-A→fresh H2 physical output→fresh H3 physical controls+audio→H4 full. H1의 durable path는 유지되지만 physical capture controls는 H3/H4에서 다시 확인한다. 최소 receive-only/PCA/combined3개 board campaign 및 fresh H2/H3/H4; firmware identity/rollback 확보가 선행 비용이다.

## 구조 변경 승인 자료의 필수 형태

각 D packet은 (a) 원인 또는 남은 competing hypotheses, (b) owner/state/queue/order/cancel/error/shutdown 명세, (c) 정확한 변경 파일 목록과 상한, (d) migration·protocol 호환성, (e) 실현 가능한 rollback, (f) before/after targeted assertions와 H1–H4 비용을 제출한 뒤 구현 단계로 전환한다. 상한을 넘는 설계는 즉시 새 layer를 구현하지 않고 별도 검토 대상으로 보고한다.

현재 audio 구조 설계 미완료, camera/input timing 미확보, UART/PCA/physical evidence 미완료이므로 local corrections가 제안됐다는 이유로 integration ready를 선언할 수 없다.
