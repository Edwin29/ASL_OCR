# H1/H2/H3 Software Diagnostic and Pipeline-Fidelity Brief — 2026-09-08

## 1. Purpose

이 작업의 목적은 H1/H2/H3 실험 보고서에 적힌 원인 추정이나 예상 수정안을 그대로 구현하는 것이 아니다. 보고서를 재현 가능한 관찰 evidence와 조사 단서로 사용하여 다음을 독립적으로 수행한다.

1. 각 실패의 first failing boundary와 root cause를 재확인하거나 기존 가설을 반증한다.
2. 같은 실행 경로의 source를 정적·동적으로 점검하여, 아직 실제 incident로 나타나지 않았지만 구체적인 실행 조건과 실패 invariant를 제시할 수 있는 오류 위험을 찾는다.
3. product defect, test-harness artifact, environment failure, hardware/wiring/calibration 문제를 분리한다.
4. root cause가 확인된 product defect에 한해서 최소 수정안을 제시하고, 수정 전 재현과 수정 후 targeted regression을 연결한다.
5. 수정 후 정식 production composition에서 H1/H2/H3를 다시 실행할 수 있는 acceptance evidence를 정의한다.

최종 목표는 보고서의 기존 결론을 확인하는 것이 아니라, 독립적인 코드·실행 evidence로 결론을 새로 세우는 것이다.

## 2. Project and current integration handoff

ASL_OCR의 현재 prototype 목표는 다음 구성의 한정된 실제 시연 경로를 완성하는 것이다.

- Desktop: production OCR/Piper server와 C0/S0/V4/S1 API
- Laptop: `C:\ASL_OCR_INTEGRATION`의 Device Runtime
- camera: 같은 LAN의 Android IP Camera 고정 source
- input/output hardware: STM32 NUCLEO-F446RE, HC-05, PCA9685 2개, 20개 servo로 구성된 10-cell 점자 display
- audio: Laptop speaker의 실제 Piper/system cue 재생
- content scope: 선정한 교재와 고정 구도, demo pages 26/27 및 28/29

정식 사용자 경로는 다음과 같다.

```text
physical mode/button input
  -> Laptop DeviceApplication / Coordinator
  -> live camera candidate and page-change identity
  -> same-frame L/R spread artifact
  -> durable outbox
  -> V4 receipt
  -> S1 OCR/parser fragments
  -> CONFIRM LONG finalize
  -> fresh READY revision
  -> S0 reading cursor/snapshot
  -> authenticated audio_ref -> Laptop speaker
  -> same generation braille FRAME -> STM -> PCA -> physical cells
```

주요 사용자 결과는 새 datapack 생성, 두 spread 촬영, 실제 저장 완료 안내, READY 선택, page/item/math-window 이동, 음성·점자 출력, reading 종료·재진입 cursor 복구다. 모든 교재나 모든 OCR을 일반화하거나 Raspberry Pi 운영화를 완료하는 것은 현재 diagnostic pass의 목표가 아니다.

세 가지 성공 신호를 혼동하지 않는다.

- STM `ACK,<sequence>`: 물리 입력 packet 수락
- `spread_sent`: 동일 artifact가 durable V4 receipt를 받은 뒤의 전송 완료
- `datapack_saved(revision)`: finalize 후 읽을 수 있는 READY revision 게시

어느 신호도 실제 TTS 재생 완료나 물리 점자 적용 완료를 뜻하지 않는다.

Authoritative software baseline은 commit 하나만이 아니라 `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e` 위에 검증된 S-01/S-02 stabilization working-tree 변경이 적용된 source identity다. Laptop에는 이를 재현한 `C:\ASL_OCR_INTEGRATION`과 독립 C: runtime이 있다. 기존 `C:\ASL_OCR`은 reference로만 보존하고 Laptop D:는 permanently unavailable/non-authoritative다.

현재 단계의 해석은 다음과 같다.

- software regression baseline G3-A는 PASS evidence를 유지한다.
- source/environment 및 C: runtime reconstruction evidence는 보존한다.
- H1/H2/H3 물리 통합에서 새 blocking evidence가 발견됐다.
- H1/H2/H3의 단계별 실험은 서로 다른 boundary isolation이며 full end-to-end acceptance가 아니다.
- H4 full live capture + physical controls + TTS + braille acceptance는 아직 통과하지 않았다.
- hardware integration 뒤 개선하기로 한 math subscript, aligned unary minus, choice TTS 안내/간격 및 Deferred focus-granularity 문제는 별도 기존 scope다. 이번 진단에서 새 root cause와 직접 연결되지 않으면 자동으로 수정하지 않는다.

이번 작업의 목적은 H1/H2/H3에서 드러난 software risk를 신뢰할 수 있게 분류하여 다음 bounded correction을 결정하는 것이다. 프로젝트 architecture 재설계, 일반 OCR 품질 개선, 새 기능 개발 또는 repository 전반 정리는 목적이 아니다.

## 3. Authoritative inputs

- `HARDWARE_INTEGRATION_H1_STATUS_20260907.md`
- `HARDWARE_INTEGRATION_H2_STATUS_20260908.md`
- `HARDWARE_INTEGRATION_H3_STATUS_20260908.md`
- `HARDWARE_INTEGRATION_H3_READING_OUTPUT_STATUS_20260908.md`
- `HARDWARE_INTEGRATION_EXECUTION_PLAN_20260907.md`
- `PROTOTYPE_STABILIZATION_REPORT_20260906.md`
- 각 문서에 명시된 runtime logs, COM5 traces, crash dumps, manifests와 hash
- Desktop stabilization source baseline과 Laptop `C:\ASL_OCR_INTEGRATION` source identity evidence

보고서의 “leading cause”, “likely”, “proposed scope”는 사실로 전제하지 않는다. raw event/trace/dump와 source behavior가 우선한다.

## 4. Required phases

### Phase A — pipeline-fidelity audit

수정 전에 각 evidence run이 production contract의 어느 경계를 실제로 통과했고 어느 경계를 fixture, console, scripted control 또는 direct serial로 대체했는지 표로 작성한다.

각 run에 대해 다음을 기록한다.

- launcher와 Python entrypoint
- 실제 import path와 source revision
- parsed config 및 runtime override
- controls, feedback, audio와 presenter의 실제 class
- initial mode 및 시작 cursor/state
- live camera, durable outbox, V4, S1, S0 중 실제 통과한 경계
- production adapter를 사용했지만 custom composition에 주입한 경우 그 차이
- SSH, scheduled task, redirection과 interactive desktop 여부가 process/audio/serial에 미칠 수 있는 차이
- 해당 run으로 주장할 수 있는 것과 주장할 수 없는 것

### Phase B — independent root-cause diagnosis

각 confirmed symptom마다 현재 가설을 검증하는 최소 reproducer를 먼저 만든다. reproducer가 실패를 만들지 못하면 기존 가설을 유지하지 말고 `unconfirmed` 또는 `test_gap`으로 돌린다.

필수 대상은 다음과 같다.

- H1 live page-change observation liveness
- H1 transient HTTP snapshot fatal behavior
- H1 page-change timeout guidance silence
- H2/H3 production-speed STM FRAME integrity
- H3 rapid audio/navigation supersession native crash
- fatal event와 process exit status의 불일치

### Phase C — bounded adjacent-source audit

실험에서 실제 실행된 critical path와 그 lifecycle/error handling 인접 코드만 독립적으로 점검한다.

- camera source open/read/retry/stop 및 error taxonomy
- Scanner collection clock, timeout, reset과 page-change state transition
- DeviceApplication input drain, hold/release, presentation containment와 shutdown
- audio fetch/cache/play/interrupt/close의 thread ownership과 generation supersession
- STM host adapter handshake/ACK/dedupe/frame write/reconnect
- STM firmware UART receive/line buffering/parser/PCA application
- CLI fatal propagation과 exit status

새 위험은 반드시 구체적인 trigger, violated invariant, 실행 경로와 최소 reproduction 아이디어를 가져야 한다. 막연한 style 문제, 일반적인 refactoring 제안, 사용되지 않는 영역의 bug hunting은 기록하지 않는다.

### Phase D — proposed corrections

각 항목을 아래 중 하나로 판정한다.

- `confirmed_product_defect`
- `probable_product_risk`
- `test_harness_artifact`
- `environment_failure`
- `hardware_or_wiring`
- `insufficient_evidence`
- `expected_behavior`

수정은 `confirmed_product_defect`에 우선 제안한다. `probable_product_risk`는 targeted test로 승격한 뒤 수정한다. hardware 또는 harness 문제를 product source 변경으로 보정하지 않는다.

## 5. Modification boundary

진단 단계에서는 product source를 수정하지 않는다. 먼저 다음을 보고한다.

- failing boundary
- 기존 evidence와 독립 reproduction
- root cause 또는 남은 competing hypotheses
- pipeline-fidelity 영향
- severity와 integration impact
- proposed minimal fix scope
- 변경될 contract/invariant와 유지할 contract
- targeted regression 계획

수정 단계가 승인되면 각 defect를 작은 독립 commit/worktree로 처리한다. 한 defect를 고치기 위해 다른 threshold, protocol 또는 acceptance를 완화하지 않는다.

다음 변경은 금지한다.

- Scanner identity sample count N=5 축소
- identity/duplicate/candidate threshold 완화
- FRAME grammar, 10-cell encoding, V3 ACK/dedupe semantics 변경
- stable device ID 변경
- 인증 비활성화 또는 새 credential 임의 생성
- camera fallback으로 strict Android source 실패 은폐
- package broad upgrade 또는 lockfile 광범위 재생성
- audio interruption 기능 제거로 crash 은폐
- hardware 결과에 맞춘 braille encoding 변경
- 근거 없는 pin swap, servo angle/LUT 변경
- 기존 `C:\ASL_OCR` 또는 production DB/artifact/evidence 변경
- Laptop `D:` 접근

## 6. Self-audit limits

자체 코드 점검은 H1~H3가 실제 실행한 경계와 한 단계 인접한 error/lifecycle 경로로 제한한다. repository 전체 품질 개선으로 확장하지 않는다.

발견 항목은 다음 조건을 모두 만족할 때만 defect/risk 목록에 올린다.

1. reachable code path가 있다.
2. concrete trigger가 있다.
3. observable wrong behavior 또는 violated invariant가 있다.
4. 기존 tests가 이를 막지 못하는 이유를 설명할 수 있다.
5. H1/H2/H3 또는 다음 H4에 미치는 영향이 있다.

그 외 항목은 `out_of_scope_observation`으로만 기록하고 수정하지 않는다.

## 7. Pipeline-fidelity review of completed experiments

### H1 live camera + console

**Fidelity:** production pipeline에 가장 가깝다.

- launcher는 `python -m asl_device --config ... --initial-mode capture`였다.
- `build_local_device()`가 production connectivity, S0, durable delivery, Scanner factory와 sounddevice audio를 구성했다.
- camera는 strict `HttpSnapshotCameraSource`; 실제 4000x3000 Android snapshot을 사용했다.
- sequence 1은 candidate부터 durable outbox, V4 HTTP 201, receipt까지 실제 경로를 통과했다.
- console만 physical STM controls 대신 사용했다. `ConsoleControlSource`는 문자열을 production `DeviceInputEvent`로 변환하며, 이후 `DeviceApplication.step()`과 Coordinator 경로는 동일하다.

**Substituted boundary:** GPIO/debounce, HC-05 packet, sequence ACK/dedupe와 physical lever는 통과하지 않았다. 따라서 H1은 Scanner/upload/audio 진단에는 유효하지만 버튼/serial 수용 evidence가 아니다.

**Incomplete boundary:** 두 번째 spread 이전에 실패했으므로 two-spread finalize/READY 전체 pipeline은 실행되지 않았다.

**Orchestration effect:** SSH는 scheduled task를 만들고 evidence를 수집하는 데 사용됐다. 실제 H1 process는 interactive user session의 production module entrypoint로 실행됐다. SSH 자체가 Scanner/Coordinator path를 대체한 증거는 없다.

### H2 console + STM presenter

**Fidelity:** 의도적인 mid-pipeline isolation이다.

- 기존 READY datapack에서 reading을 시작해 camera, outbox, V4, parser, finalize를 건너뛰었다.
- S0 reading, production sounddevice audio, `StmSerialControlSource.present()`와 COM9/HC-05/STM/PCA 경로는 실제였다.
- custom harness가 config의 `stm_serial` controls를 `ConsoleControlSource`로 override했다.

console event는 production `DeviceInputEvent` 이후의 application/Coordinator 책임을 보존한다. 하지만 physical STM input, firmware debounce, V3 edge, ACK와 dedupe는 대체했다. H2의 정상 production-speed FRAME 손상은 실제 presenter/serial path evidence지만, paced diagnostic은 host application을 우회해 STM parser/PCA/actuator만 국소화한 evidence다.

추가 fidelity caveat: config에는 controls가 `stm_serial`로 남아 있어 advertised connectivity capability는 STM control 포함으로 계산됐지만 실제 application controls는 console이었다. 이 차이는 reading command semantics를 바꾸지는 않으나 manifest에서 명시해야 하며 formal production acceptance로 사용하면 안 된다.

### H3 physical STM run

**Fidelity:** input/output 하드웨어 관점에서 가장 높은 H3 evidence다.

- launcher는 production `python -m asl_device --config ...`였다.
- config와 default composition 모두 `stm_serial` controls/presenter, sounddevice TTS를 사용했다.
- 실제 V3 handshake, DOWN activated/released cadence, ACK/reconnect와 physical buttons를 관측했다.

이 run은 existing READY/catalog에서 reading을 검증한 것이므로 live capture부터 시작한 full pipeline은 아니다. 버튼 배선 불일치로 CONFIRM/PAGE NEXT/MODE의 필수 경로는 완료되지 않았다.

### H3-R console and braille-only diagnostics

**Fidelity:** targeted downstream diagnostics이며 production full run이 아니다.

- existing READY에서 시작했다.
- custom composition이 console controls와 STM presenter를 주입했다.
- braille-only config는 의도적으로 TTS를 비활성화했다.
- generation 110/111 paced scripts는 Device/S0/host presenter를 우회하고 byte stream을 STM에 직접 보냈다.

따라서 paced 결과는 parser/PCA/motor 및 physical clear 경계를 판단하는 데만 유효하다. production FRAME reliability, TTS coexistence 또는 end-to-end generation ownership의 PASS 증거가 아니다.

### Physical DOWN-to-braille follow-up

custom harness는 direct `DeviceInputEvent`로 CONFIRM/PAGE_PREVIOUS/DOWN bootstrap을 수행한 뒤 physical STM input으로 전환했다. bootstrap 동안 intermediate FRAME을 STM에 보내지 않았고, audio도 비활성화했다. 시작 cursor 가정이 실제 persisted cursor와 달라 목표 node도 달라졌지만, readiness marker 이후 실제 before/after snapshot은 보존됐다.

측정한 물리 입력은 `NAV,D,S,2`였다. 이는 V2 asynchronous SHORT 형식이며 V3 DOWN `ACTIVATED/RELEASED` 계약이 아니다. 따라서 다음만 증명한다.

- negotiated V2에서 physical short DOWN 수신
- production DeviceApplication/Coordinator의 한 item 이동
- 동일 generation/cells의 FRAME 송신 및 physical movement

다음을 증명하지 않는다.

- V3 press/release/hold semantics
- TTS와 FRAME의 동시 안정성
- intermediate rapid FRAME ordering
- full live capture-to-reading pipeline

V3 edge/cadence는 별도의 H3 production run evidence에 의존해야 한다.

## 8. Overall fidelity decision

완료된 시험은 stage isolation 원칙에는 대체로 부합한다. console 입력은 application boundary 이후의 command semantics만 시험할 때 적절했고, direct paced frame은 STM downstream을 국소화하는 데 적절했다. 그러나 H1/H2/H3/H3-R 중 어느 하나도 live camera부터 physical controls, TTS와 actuator까지 동시에 가동한 final production pipeline acceptance는 아니다. 그 역할은 H4에 남아 있다.

따라서 기존 evidence는 root-cause investigation의 강한 입력으로 사용할 수 있지만 다음 제한을 적용해야 한다.

- H1 결과를 physical input 결함 증거로 사용하지 않는다.
- H2/H3-R 결과를 upstream capture/publish 회귀 증거로 사용하지 않는다.
- paced serial 결과를 production transport PASS로 사용하지 않는다.
- physical DOWN follow-up을 V3 acceptance로 사용하지 않는다.
- isolated C: state와 existing READY 시작을 fresh end-to-end success로 사용하지 않는다.

## 9. Required final deliverable from the diagnostic model

1. pipeline-fidelity matrix와 evidence validity
2. issue별 independent reproduction 결과
3. raw evidence와 source inspection으로 확인한 root cause
4. 기존 가설과 일치/불일치 여부
5. 새로 찾은 confirmed risk와 test gap
6. 수정 대상과 비수정 대상
7. 최소 patch 범위 및 예상 contract 변화
8. targeted/subsystem/G3-A/H1-H3 재검증 결과
9. production-composition 재실행에서 남은 차이
10. H4 진입 가능 여부

FAIL 또는 insufficient evidence가 남으면 integration ready를 선언하지 않는다.

## 10. Compact instruction for the diagnostic model

> ASL_OCR의 현재 prototype은 Desktop production OCR/Piper server, Laptop Device Runtime, 고정 Android IP Camera, STM32/HC-05/PCA/10-cell actuator와 Laptop speaker를 연결해 선정한 pages 26–29를 capture, durable upload, parse, finalize, READY publish, S0 reading, TTS와 physical braille까지 전달하는 것이다. STM input ACK, durable `spread_sent`, READY `datapack_saved`, audio completion과 physical cell application은 서로 다른 boundary다. H1/H2/H3 status reports and their raw evidence are observations and investigation leads, not authoritative root-cause conclusions or implementation instructions. Begin with a read-only pipeline-fidelity audit, independently reproduce each symptom, and inspect the exercised source plus adjacent lifecycle/error paths for concrete reachable defects. Classify every finding as confirmed product defect, probable risk, harness artifact, environment failure, hardware/wiring, insufficient evidence, or expected behavior. Do not modify product source until the failing boundary, reproduction, competing hypotheses, integration impact and minimal fix scope are reported. After approval, change only confirmed product defects, preserve all scanner identity thresholds and N=5, serial/frame/V3 semantics, stable identity, authentication and data lineage, and run targeted regressions before subsystem, G3-A and fresh production-composition H1/H2/H3 verification. Do not use console, scripted bootstrap, paced serial or existing READY evidence beyond the specific boundary each fixture actually exercised, and do not declare H4 readiness while any required physical control, transport, audio stability or complete actuator-clear condition remains failed. Do not expand this task into general OCR improvement, Pi deployment, new features, architecture redesign or repository-wide cleanup.
