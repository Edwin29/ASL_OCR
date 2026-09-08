# 1B Servo 없는 실제 audio 결합 — 2026-09-08

Run ID: `audio-console-20260908-163539`

## 범위

- Existing READY와 stable device ID `laptop-device-001`
- Console `DeviceInputEvent` → production DeviceApplication/Coordinator → S0
- Authenticated reading/system `audio_ref` → production cache/controller → SoundDevice → Laptop speaker
- 정상 이동, 빠른 supersession, replay, reading 종료·재진입, app restart cursor 복구

Live capture, V4/S1/finalize, physical controls, STM presenter, PCA/servo는 우회한다. 이 run은 H2/H3/H4 acceptance를 대신하지 않는다.

## 고정 절차

1. Reading catalog system cue 청취 및 대상 READY 선택.
2. `confirm`으로 reading을 열고 resumed cursor와 실제 읽기 음성을 확인.
3. `down`, `up`, `page_next`, `page_previous`, `right`, `left`, `confirm`을 순차적으로 시험.
4. 짧은 간격의 세 명령을 입력해 old generation 중단과 latest generation 재생을 확인.
5. `confirm long`으로 catalog 복귀 후 같은 READY를 다시 열어 cursor 복구 확인.
6. 정상 종료 후 같은 run config/stable device ID로 app을 재시작하고 cursor 복구 확인.

## Stop condition

Crash, hang, `reading_audio_failed`, stale audio 재출현, 최신 focus와 다른 음성, worker 종료 실패, session/datapack identity mismatch 또는 server fatal이 발생하면 해당 시점 evidence를 보존한다. 독립적인 남은 단계는 가능한 범위에서 계속하되 결과를 PASS로 합치지 않는다.

## 현재 상태

`PASS` within the bounded 1B scope. This result does not replace fresh H2/H3 or
H4 physical acceptance.

첫 두 interactive launch는 product 초기화 전에 run-only 오디오 장치 조회 helper가
SoundDevice `_InputOutputPair`를 scalar로 처리하거나 존재하지 않는 named member를
기대하여 종료됐다. 이는
`test_harness_artifact`이며 product audio, S0, camera, serial, actuator 경계는
실행되지 않았다. Helper가 output member를 읽도록 보정하고 같은 고정 절차를
계속한다.

## 사용자 청취 관측

- Startup catalog cue/title: 정상 청취.
- `confirm`: generation 134의 복구된 문제 본문을 텍스트 내용대로 청취;
  끊김과 중복 없음.
- `down`: generation 135의 다음 item을 청취; 끊김·중복 보고 없음.
  음성에 수식 인식 불확실 안내가 포함됐고 source에는
  `\\lim_{x\\to b}`가 존재했다. 이는 보존된 content/parser 관측이며 1B audio
  lifecycle 결과와 분리한다.
- `up`: generation 136으로 이전 item에 복귀했고 cached reading audio가 한 번
  시작·완료됨. 사용자 관측 정상.
- `page_next`: generation 137, page index 2/node 0으로 이동하여
  `www.ebsi.co.kr`을 정상 청취. fetch/start/completion 각 1회.
- Interactive console 아래에 과거 generation 136 `cache_hit` line의 일부로 보이는
  `che_hit...generation13` 조각이 나타났다는 사용자 관측이 있었다. 같은 시점의
  file sink 29개 line은 전부 valid JSON이고 tail에는 generation 137의
  snapshot/fetch/start/completion만 존재한다. Transcript에도 해당 fragment가 없어
  현재 evidence는 console rendering artifact를 지지하며 product event/log corruption은
  관측되지 않았다.
- `page_previous`: 명령 직전 마지막 durable product event는 generation 137 audio
  completion이다. Generation 138 snapshot이나 Python traceback/lifecycle record 없이
  process가 종료됐고 Scheduled Task result는 `0x8007042B`였다. Laptop은 배터리
  상태(56%, BatteryStatus 1)였고 run-only scheduled task의 기본 설정은
  `DisallowStartIfOnBatteries=true`, `StopIfGoingOnBatteries=true`였다. 재시작 task도
  같은 이유로 `Queued`가 되어 원인이 확인됐다. Classification:
  `test_harness_artifact` + `environment_failure`; 해당 `page_previous`는 product
  boundary에 도달하지 않았다. Run-owned task에만 battery start/continue를 허용하고
  절차를 재개한다.
- Restart 1은 default output이 `헤드폰(Px7 S3)`인 상태에서 catalog audio event가
  완료됐으나 사용자는 음성을 듣지 못했다. Ctrl+C 종료는 exit code 0,
  audio worker stopped, close complete, presentation failure 0이다. 다음 restart부터
  `Realtek(R) Audio` default-output preflight guard를 적용한다.
- Restart 2에서 `page_previous`는 page index 1/generation 134를 유지한 채 같은
  audio만 재생했다. 앞 page index 0은 존재하며 source contract상 page 0/node 0과
  새 generation으로 이동해야 한다. Run harness가 재시작마다 같은
  `audio-console-20260908-163539` namespace와 counter를 재사용해, 이전 run의
  command ID를 다른 payload에 재사용했다. S0의 durable receipt contract는 이를
  `IDEMPOTENCY_KEY_REUSED`로 거부한다. Classification: `test_harness_artifact`.
  Production console composition처럼 process별 고유 namespace로 수정 후 재시험한다.
- Restart 3 uses unique control namespace
  `audio-console-0237df72b6d34bc69be441e78125f07b` and Realtek output.
  Stable cursor resumed at generation 137, page index 2/node 0. This confirms
  generation 137 was durable despite the earlier Task Scheduler termination;
  Restart 2's generation 134 result was the command-ID collision artifact.
- `right`/`left` at the resumed `www.ebsi.co.kr` focus produced generations
  138/139 with `braille_cells=[]` and offset 0. Later formula-boundary prompts
  also occurred at focuses with zero cells or only 9 cells, below the 10-cell
  viewport. Keeping offset 0 while announcing no previous/next displayable
  formula is `expected_behavior`, not an offset defect. A positive-scroll focus
  with more than 10 cells remains to be exercised.
- With unique IDs, `page_previous` moved page 2 to page 1/node 0 at generation
  140 and `page_next` returned to page 2/node 0 at generation 141. Replay
  advanced to generation 142 and completed once.
- Rapid navigation reached generations 143--146. Generations 144 and 145 were
  observably interrupted; generation 146 was then interrupted by the planned
  catalog exit before it could complete. Catalog re-entry resumed the exact
  generation 146 focus and its 40.832-second audio completed. A later bounded
  sequence also interrupted generation 164 and completed latest generation 165,
  with no stale generation reappearance.
- Positive viewport exercise reached the known long formula focus and produced
  generation 168/169/170 offsets 10/20/10 with `spoken_text=null`; user observed
  normal behavior.
- Restart 3 Ctrl+C reached the run-only lifecycle writer after product stop, but
  the writer called `dataclasses.asdict()` on the mapping-valued cursor and raised
  `TypeError`. Classification: `test_harness_artifact`. Cursor serialization is
  changed to `dict(...)`; one minimal restart/open/close is required to capture
  exit code and audio worker close evidence.
- Restart 4 resumed the durable generation 171 cursor at page index 1/node 9,
  offset 0, played the matching reading audio to completion on the Realtek
  speaker, and stopped with application exit code 0. Presentation failures were
  zero, the audio worker was not alive after stop, and `audio_close_complete=true`.

## 최종 판정

- Production-preserved boundary: DeviceApplication/Coordinator, S0 reading,
  authenticated `audio_ref`, cache/controller, SoundDevice, Realtek speaker.
- Bypassed boundary: camera/V4/S1/finalize, physical controls, STM/PCA/servo.
- Normal item/page/replay and positive braille-window cursor 10→20→10: PASS.
- Rapid supersession, latest completion, catalog exit/re-entry: PASS.
- Stable device cursor across restart and graceful close: PASS.
- User-observed content, no unintended duplicate/stale audio: PASS.
- Product source modification count: 0.

Run-only issues were the SoundDevice default-pair probe, scheduled-task battery
defaults, reused console command namespace, and lifecycle cursor serialization.
All are classified as `test_harness_artifact`; the battery stop additionally
records `environment_failure`. The transient headphone default was an output
environment mismatch caught by the Realtek preflight. None is promoted to a
product defect.

Raw evidence:

- `audio-console-events-final.jsonl`, SHA-256
  `021863ca536f1ce8d26fbf2059327ff713c597bdbbf4e7e19cfe58f7a340e8e2`
- `interactive-lifecycle-final.json`, SHA-256
  `4252035c35aa7b7b862508739fc6d9b09cc0746619dd5817dd60bfebdf36ed67`
- `source-identity-before.json`, SHA-256
  `76749f9ebc25aa0fffd4353633dfd44bcdeaa7e0223f479f1b8fcccfa99a0ffa`

## 관측 기록

- Catalog 진입: system cue와 index 0 제목 audio가 실제 speaker에서 완료됐다.
- `confirm`: 대상 `datapack-63c0ac30cc8a482f8fa9d0795e044a03`
  revision 1을 열었다.
- Stable cursor는 page index 1, node 9, braille offset 10, generation 134로
  정확히 복구됐다.
- Generation 134 reading audio가 재생 완료됐고, 사용자 관측은 “텍스트 그대로
  문제 내용 들림, 끊김·중복 없음”이다.
