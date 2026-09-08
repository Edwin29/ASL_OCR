# ASL_OCR Hardware Integration Execution Plan

작성일: 2026-09-07  
상태: **승인된 조건부 HW 통합 진입 계획 / 아직 물리 시험은 not_run**  
선행 evidence: `PROTOTYPE_DEMO_BOUNDED_STABILIZATION_RESULT_20260907.md`, `PROTOTYPE_STABILIZATION_REPORT_20260906.md`, `SOURCE_ALIGNMENT_RESULT_20260906.md`  
적용 계약: `PROTOTYPE_STABILIZATION_GATE.md`, `HW_SW_INTEGRATION_PLAN.md`

## 1. 결정과 범위

현재 software/replay baseline과 G0/G3-A 결과는 보존한다. 아래 알려진 content/presentation 문제는 severity를 낮추지 않고 P1로 유지하되, **물리 camera·audio transport·STM input·FRAME·actuator 통합 착수를 거부하는 조건에서는 임시 제외**한다.

이 결정은 `Hardware Integration Entry: CONDITIONAL GO`다. G3-B/G4의 human content acceptance를 PASS로 바꾸거나 Prototype 최종 수용을 선언하는 결정이 아니다. HW 통합 뒤 별도 bounded pass에서 P1을 수정하고 fresh G3-B/G4와 실제 음성·점자를 다시 확인해야 한다.

이번 계획의 실제 제품 경로는 다음과 같다.

```text
live camera
  -> Scanner candidate/page-change
  -> spread L/R artifact
  -> durable outbox
  -> V4 receipt / S1 fragment
  -> finalize / READY revision
  -> S0 reading command/snapshot
  -> audio_ref -> Laptop speaker
  -> FRAME -> STM -> PCA9685 -> 10-cell actuator
```

입력은 세 단계로 확대한다.

1. live camera + console control
2. console control + STM/PCA/actuator output
3. live camera + STM physical buttons + speaker + STM/PCA/actuator 전체 경로

## 2. 알려진 issue와 integration waiver

### 2.1 P1 — HW bench에 한정한 임시 waiver

| ID | 확정 증거와 영향 | HW 통합 중 취급 | waiver 종료 조건 |
|---|---|---|---|
| `MATH-LIMIT-SUBSCRIPT-P1` | `\lim_`에서 `_`가 `Unknown` argument가 되어 뒤 token이 미소비된다. 5개 span/4개 item에서 INVALID, 불확실 TTS와 빈 점자 발생 | 아래 명시 item의 예상된 불확실 음성/clear frame만 비차단. actuator 합격 표본으로 사용 금지 | lower-condition과 피극한식을 보존하도록 parser/TTS/braille 수정, targeted regression, G3-A, fresh G3-B/G4 |
| `MATH-ALIGNED-UNARY-MINUS-P1` | aligned/array cell의 `&-x`에서 `&` 제거 후 unary parser를 우회하여 `-`가 Unknown이 된다. 페이지 28·29의 2개 item, 선두 음수 3곳 | 해당 item의 PARTIAL 음성/빈 점자는 비차단. 알려진 정상 수식으로 actuator 시험 | aligned cell 선두 음수가 `UnaryMinus`가 되고 음성/점자가 보존되는 회귀 및 fresh G3-B/G4 |
| `CHOICE-TTS-PRESENTATION-P1` | 선택지 TTS 앞에 고정 안내가 없고 안내 후 휴지 및 보기 사이 명시 간격이 없다. 현재 한 utterance의 자연 운율에 의존 | WAV fetch/playback 성공은 검증하되 안내 문구와 간격 품질은 HW bench 거부 조건에서 제외 | `객관식 정답` 안내, 안내 후 pause, 보기 사이 현재 체감의 약 2배 간격을 정의·합성하고 human listening 수용 |

`MATH-LIMIT-SUBSCRIPT-P1`의 고정 영향 범위:

- page 26 `pg-c4b5938b7318-00000001-L-vl010-L02` span 0/1
- page 27 `pg-c4b5938b7318-00000001-R-vl009-L02` span 1
- page 28 `pg-c4b5938b7318-00000002-L-vl006-L01` span 0
- page 29 `pg-c4b5938b7318-00000002-R-vl008-L01` span 3

`MATH-ALIGNED-UNARY-MINUS-P1`의 고정 영향 범위:

- page 28 `pg-c4b5938b7318-00000002-L-vl005`
- page 29 `pg-c4b5938b7318-00000002-R-vl009-L02`

위 목록 밖에서 같은 실패가 새로 나타나거나, 알려진 문제가 crash/finalize 실패/false READY/identity 혼입/stale FRAME으로 확대되면 waiver를 적용하지 않고 해당 단계에서 중단한다.

### 2.2 Deferred — integration 거부 조건 제외

| ID | 현재 상태 | 재분류 조건 |
|---|---|---|
| `TTS-DUPLICATE-ITEM-SPAN-D01` | 동일 spoken text의 item key와 `#0` span key가 10쌍 존재한다. 별도 Piper 합성으로 WAV hash/길이는 다르지만 serving loader는 spoken text로 하나를 선택한다. 자동 이중 재생 증거 없음 | 단순 focus 이동에서 실제 이중 재생, audio lookup 충돌 또는 실질적인 resource failure 재현 시 P1 |
| `PROBLEM-FOCUS-GRANULARITY-D02` | 검출된 10개 problem unit 모두 문제 코드·stem·MATH·choices를 4~6 focus item으로 유지한다. 같은 `problem_id`와 순서는 보존된다 | 한 문제 한 번의 연속 낭독/문제 단위 navigation이 prototype 필수 UX로 확정되면 P1 |

### 2.3 waiver가 면제하지 않는 조건

다음은 기존 stop/reject 조건을 그대로 유지한다.

- wrong camera, wrong page/side/order 또는 다른 책 혼입
- false `spread_sent`, receipt 불일치, duplicate spread
- ACK되지 않은 artifact 유실, cutoff 위반, false saved/READY
- READY revision 또는 기존 production revision 변조
- audio 누락/잘못된 item audio/stale generation/재생 실패
- waiver 밖의 필수 수식에서 빈 점자 또는 의미 불일치
- malformed/누락 FRAME, cell 범위 위반, stale FRAME 최종 덮어쓰기
- STM command 중복 적용, release 뒤 무한 이동, stale cursor
- actuator의 제어되지 않는 움직임, 걸림, 과열, 비정상 전원, clear 실패

## 3. 고정 baseline과 runtime 분리

Laptop source:

- checkout: `C:\ASL_OCR_INTEGRATION`
- Python: `C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe`
- stable device ID: `laptop-device-001`
- authoritative runtime: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905`
- 기존 `C:\ASL_OCR`은 보존하고 사용하지 않는다.
- Laptop `D:`는 permanently unavailable이며 접근하지 않는다.

각 물리 run은 다음 하위 root를 사용한다.

```text
C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\<run-id>\
  config\
  state\camera-console\
  state\console-actuator\
  state\stm-reading\
  state\full-e2e\
  logs\
  reports\
  captures\
  manifests\
```

production state, 기존 replay state, SQLite, outbox, artifacts와 evidence는 삭제/reset하지 않는다. API secret 원문을 로그·manifest에 쓰지 않는다. 기존 secret reference와 Desktop server origin을 재사용한다.

실행 시작 시 다음 identity를 manifest에 고정한다.

- Desktop/Laptop source manifest hash와 tracked diff set
- Python/interpreter/dependency identity와 실제 import path
- UVDoc/M1/Paddle model path/hash
- Desktop server instance ID, origin, loopback 및 Laptop remote health/auth
- camera name/stable selector/backend/index/effective width/height/FPS/FourCC/rotation/crop
- audio output device/backend
- STM project source hash, CubeIDE build log, ELF/BIN hash와 flashed artifact 대응
- COM port, baudrate, protocol version, STM boot identity
- GPIO/button/header map, active-low/pull-up 확인
- PCA addresses `0x40/0x41`, channel map, cell count 10, actuator power arrangement

## 4. H0 — 장비·설정 preflight와 안전 경계

### 사전 준비

1. Desktop production server의 loopback health와 Laptop private HTTPS health/auth를 확인한다.
2. Laptop의 camera를 열기 전에 장치 목록을 기록하고 하나의 selector/backend/index를 명시한다. 장치가 사라졌을 때 다른 카메라로 fallback하지 않는다.
3. 실제 camera mode가 요청한 mode와 같은지 probe에서 확인하고 한 장의 preview로 펼침면 전체, 중심 seam, 초점, 노출, 반사를 사람이 확인한다.
4. `viewport_size=10`, STM `cell_count=10`, `controls`, state root, model path를 production parser로 전체 parse한다.
5. STM authoritative source를 CubeIDE로 build하고 build log와 artifact hash를 남긴다. 과거 handoff ELF를 현재 source build로 간주하지 않는다.
6. 전원을 끈 상태에서 GPIO/header, HC-05, PCA `0x40/0x41`, top/bottom channel, actuator 기계 간섭을 확인한다. actuator 전원 인가와 비상 차단 절차는 하드웨어 담당자가 확정한다.
7. COM open만으로 합격 처리하지 않고 `HELLO,3 -> ACK,HELLO,3`를 실제 UART log로 확인한다.

### PASS

- preflight 각 check가 독립적으로 passed
- source/config/model/camera/firmware/COM/PCA identity가 모두 기록됨
- secret 노출 0, Laptop `D:` dependency 0
- 물리 전원·배선 점검 완료

### STOP

- source/import/config identity mismatch
- camera ambiguity 또는 requested mode 불일치
- firmware hash 불명확, v3 handshake 실패
- PCA startup failure, 배선/전원/기계 안전 미확인

## 5. H1 — live camera + console capture/read

목적은 MP4를 실제 camera로 교체하되 STM과 actuator를 아직 추가하지 않고 B03~B09를 검증하는 것이다.

### 설정

- scanner: 실제 `pc_camera`, `android_uvc` 또는 승인된 explicit camera profile 하나
- controls: `console`
- feedback: secret-safe JSONL
- reading audio: Laptop `sounddevice`
- state: `<run-id>\state\camera-console`
- config: `<run-id>\config\device-app.camera-console.toml`

console command는 `up/down/left/right/next/prev/confirm`, `confirm long`, `lever activated|released`의 현재 contract만 사용한다.

### 절차

1. 카메라에 검은 배경·고정 받침·조명을 사용해 실제 펼침면을 배치한다.
2. capture catalog에서 새 datapack을 선택한다.
3. 첫 spread를 고정하고 `candidate_selected`, valid observation 5, `spread_sent=1`, durable ACK를 확인한 뒤에만 페이지를 넘긴다.
4. 두 번째 spread에 대해 같은 절차를 수행한다. 시험 중 한 번만 손 가림을 넣어 false upload가 없고 제거 후 정상 후보로 복귀하는지 확인한다.
5. `confirm long`으로 freeze/cutoff/flush/seal/finalize를 수행한다.
6. READY 게시 뒤 reading으로 전환하여 네 페이지의 side/order, audio fetch/playback, braille snapshot을 확인한다.
7. fresh revision preflight를 실행하고 checked revision > 0, error 0을 확인한다.

### PASS

- 실제 의도한 2 spread/4 pages가 순서대로 검출됨
- L/R source lineage, artifact/outbox/receipt/fragment 대응 일치
- duplicate 0, cutoff 이후 새 spread 0
- false saved 0, fresh READY 1
- remote audio fetch와 실제 speaker playback 성공
- waiver 대상 외 selected item의 source/spoken/braille가 일치

### human observation

- 실제 펼침면과 L/R/page order
- crop/seam/dewarp 품질
- waiver 밖의 대표 본문·수식 OCR 의미
- 실제 speaker 음성의 항목 대응

## 6. H2 — console control로 actuator 시험

목적은 물리 버튼을 추가하기 전에 console command에서 S0 reading, FRAME, STM, PCA와 actuator까지의 출력 경계를 격리하는 것이다. 입력은 console이고 출력은 실제 STM/PCA/10-cell이다.

### 현재 composition 제약

production TOML의 `local_io.controls`는 `console` 또는 `stm_serial` 중 하나다. `console`을 선택하면 기본 presenter는 JSONL이고 STM FRAME presenter가 생성되지 않는다. 따라서 이 단계에는 다음 조건의 **runtime-only 진단 harness**가 필요하다.

- 기존 `ConsoleControlSource`, `StmSerialControlSource`, production S0/Coordinator/reading adapter를 그대로 조합
- console event만 domain input으로 전달
- STM serial은 `HELLO`/ACK와 FRAME writer를 계속 pump
- 이 단계에서 들어오는 물리 STM NAV는 적용하지 않거나 명시적으로 기록 후 무시
- harness 파일/hash/command를 evidence에 기록
- product source, protocol, firmware를 수정하지 않음

이 harness는 H2 진단에만 사용한다. H3/H4의 production `controls=stm_serial` 결과를 대체하지 않는다.

### 표본

- 기존 preflight PASS READY revision을 사용한다.
- 정상 non-empty 긴 수식 기준: page 26 `pg-c4b5938b7318-00000001-L-vl012-L01`
- 일반 TEXT/selection에서 clear frame 확인
- answer choice의 no-braille clear는 정책 확인용이며 actuator 구동 성공 표본으로 세지 않는다.
- P1 waiver item은 actuator 합격 표본에서 제외한다.

### 절차

1. HELLO v3 뒤 blank/current FRAME을 확인한다.
2. console `down`으로 정상 수식 focus까지 이동하고 snapshot의 10 cells와 UART FRAME을 대조한다.
3. 실제 top/bottom actuator 돌출을 cell/dot mapping 표와 대조한다.
4. `left/right`로 긴 수식의 window offset과 span 이동을 끝까지 수행한다.
5. 일반 TEXT와 선택지로 이동해 clear 뒤 잔류 돌출이 없는지 확인한다.
6. 빠른 `down` 입력 후 최종 generation의 FRAME만 남는지 확인한다.
7. 동일 focus의 audio_ref와 실제 speaker 음성이 대응하는지 확인한다.

### PASS

- console event -> S0 command -> snapshot -> FRAME -> STM -> PCA -> actuator lineage 일치
- FRAME은 정확히 10 cells, 각 0..63
- known frame의 cell/dot/top/bottom 방향이 물리 돌출과 일치
- window/offset 이동, clear, latest-generation 적용이 정확함
- stale/잔류 actuator 0

### STOP

- 제어되지 않는 움직임, 걸림, 과열, 전원 이상
- UART FRAME과 물리 돌출 불일치
- clear 실패 또는 stale FRAME 반복
- harness가 product contract와 다른 command/FRAME을 생성함

## 7. H3 — STM 버튼 입력 + speaker + actuator

목적은 preflight된 READY revision을 사용해 camera 변수를 제외하고 물리 버튼 입력과 실제 출력을 닫는 것이다.

### 설정

- controls: `stm_serial`
- presenter: 동일 STM serial
- scanner는 시작되더라도 capture를 수행하지 않고 READY reading 경로를 사용
- state: `<run-id>\state\stm-reading`
- config: `<run-id>\config\device-app.stm-reading.toml`

### 절차

1. `HELLO,3 -> ACK,HELLO,3`와 current/blank FRAME을 확인한다.
2. 레버 실제 위치가 capture/reading mode와 일치하는지 확인한다.
3. UP/DOWN/LEFT/RIGHT/PAGE_NEXT/PAGE_PREVIOUS/CONFIRM SHORT/LONG을 한 번씩 수행한다.
4. 각 NAV sequence, immediate ACK, operation ID, cursor, generation, audio_ref, FRAME을 연결한다.
5. DOWN 2초 hold에서 STM repeat SHORT 0, press/release edge 각 1, Host 즉시 1회와 650ms 이후 180ms repeat를 확인한다.
6. release 후 새 repeat 0, 이미 in-flight 요청 최대 1, 완료 후 추가 이동 0을 확인한다.
7. 앱 재시작과 STM 재연결 후 stable device cursor가 유지되고 boot namespace는 새 값인지 확인한다.
8. 정상 수식의 실제 음성·점자와 선택지의 no-braille clear를 확인한다.

### PASS

- 한 짧은 press가 한 command로 적용되고 duplicate sequence는 재적용되지 않음
- ACK와 server round trip이 구분됨
- button -> snapshot -> speaker/FRAME -> actuator가 같은 generation
- DOWN release 뒤 지속 이동 0
- reconnect 뒤 stale command/frame/audio가 최종 상태를 덮지 않음

## 8. H4 — live camera + STM 버튼 + 전체 output E2E

H1~H3가 통과한 동일 source/model/server/firmware/camera/배선으로 전체 사용자 흐름을 한 번 수행한다.

### 절차

1. STM 레버를 capture 위치로 두고 새 isolated datapack을 선택한다.
2. live camera로 2 spread를 촬영한다. 각 `spread_sent`와 durable ACK 후에만 페이지를 넘긴다.
3. STM CONFIRM LONG으로 cutoff/freeze/flush/seal/finalize한다.
4. READY와 saved 안내 뒤 레버를 reading으로 전환하고 새 revision을 선택한다.
5. STM 버튼으로 네 페이지를 이동하며 실제 speaker와 actuator를 함께 관찰한다.
6. 정상 non-empty 수식에서 LEFT/RIGHT window, page 이동, CONFIRM replay와 exit를 수행한다.
7. current revision preflight를 실행하고 lineage와 실제 page/order를 대조한다.
8. capture mode에서 기존 READY에 한 spread를 append한다. revision 증가, 기존 ID/order 보존, 새 L/R append를 확인한다.
9. 앱 재시작 후 같은 stable device ID로 cursor를 복구하고 새 revision과 기존 open reading revision을 구분한다.

### 전체 PASS

- camera -> READY lineage와 STM button -> audio/FRAME/actuator lineage가 하나의 run ID로 연결됨
- 2 spreads/4 pages, duplicate 0, 올바른 L/R/order
- 저장 안내는 READY 뒤에만 발생
- preflight checked revision > 0, error 0
- 실제 speaker 재생, 10-cell actuator, clear와 navigation이 같은 focus/generation
- append revision/ID/order와 restart cursor가 정확함
- waiver에 명시된 content 차이 외 새로운 P0/P1 없음

H4 통과는 세 P1 content waiver를 해소하지 않는다. 해당 P1을 수정하고 fresh revision을 다시 검증하기 전에는 최종 prototype demo acceptance를 선언하지 않는다.

## 9. H5 — bounded recovery

HW 통합 정상 run 뒤 다음을 각 한 번만 수행한다.

| 시험 | 방법 | 성공 조건 |
|---|---|---|
| camera obstruction | 손 가림 후 제거 | 가림 중 false upload 0, 제거 후 정상 candidate |
| pending upload 후 connectivity loss | 격리 test network에서 단절/복구 | 같은 artifact/key 재시도, duplicate receipt/spread 0 |
| stop during pending | 마지막 ACK 전 CONFIRM LONG | through cutoff 모두 ACK 전 seal/saved 0, 완료 READY에 마지막 L/R 포함 |
| slow server + DOWN release | 외부 proxy/harness로 500ms 이상 지연 | release 뒤 새 dispatch 0, in-flight 최대 1 |
| HC-05 disconnect/reconnect | radio와 direct COM 단절을 분리 | bounded reconnect, 새 HELLO, stale NAV/FRAME 미적용 |
| app restart | 동일 device/book | cursor 복구, boot namespace 갱신, stale audio/FRAME 미적용 |

기존 software evidence로 닫힌 ACK-loss/finalize containment는 물리 장치가 결과에 영향을 주는 범위만 재확인한다. 무작위 fuzzing이나 장시간 soak를 추가하지 않는다.

## 10. evidence와 보고 형식

각 단계는 시작 전 manifest, event JSONL, Desktop server log excerpt, Laptop log, UART trace, 사진/영상 human observation을 같은 run ID로 연결한다.

최종 HW 보고서는 다음을 포함한다.

- H0/H1/H2/H3/H4/H5: PASS/FAIL/BLOCKED/not_run
- camera absolute identity와 effective mode
- firmware source/build/flash hash
- COM/protocol/HELLO/ACK/NAV identity
- PCA/channel/cell/dot mapping과 전원 조건
- source frame -> artifact -> receipt -> revision lineage
- button -> operation -> cursor/generation -> audio_ref/FRAME lineage
- 실제 speaker/actuator human observation
- exact first failing boundary와 environment/product 구분
- P0/P1/Deferred 및 waiver 해당 여부
- product source modification count
- 기존 `C:\ASL_OCR`, production state, Laptop `D:` 접근/변경 여부

## 11. 실행 후 판정

다음과 같이 판정을 분리한다.

| 판정 | 조건 |
|---|---|
| `Hardware Integration Entry` | 현재 **CONDITIONAL GO** |
| `HW transport/physical integration` | H0~H4 필수 항목과 선택한 H5가 실제 evidence로 PASS |
| `Known-content waiver` | 정확히 명시된 세 P1에만 적용 |
| `Prototype final acceptance` | 세 P1 수정, fresh G3-B/G4, 실제 TTS·점자 human acceptance 뒤에만 PASS |

하드웨어 통합 중 새 문제가 발견되면 즉시 수정하지 않는다. first failing boundary, 재현, 기존 G3-A/G3-B와 차이, P0/P1/Deferred, 물리 안전 영향을 기록하고 해당 단계의 stop/rollback 규칙을 적용한다.
