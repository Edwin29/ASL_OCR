# Bounded prototype stabilization — 2026-09-06

판정: **S-01/S-02 교정 및 현재 환경의 검증 완료, Stabilization Exit Gate는 BLOCKED**. 통합 준비 완료가 아니며 Prototype Integration Baseline을 선언하지 않았다.

작업 계약은 [Stabilization Gate](PROTOTYPE_STABILIZATION_GATE.md), [Integration Plan](HW_SW_INTEGRATION_PLAN.md) 및 이번 사용자 지시다. 이번 세션에서는 G3만 G3-A Regression Replay / G3-B Demo Replay로 분리한다. 두 gate가 모두 PASS여야 combined G3 PASS다. G3-B의 개수/내용 정답은 최초 실행 결과로 정하지 않으며 사람의 원본 대조가 필요하다. live camera physical acceptance는 별도다.

## 변경 범위와 source identity

- 시작 HEAD: `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e`, `main`은 로컬 origin/main보다 5 commits 앞섬. fetch/push/commit하지 않았다.
- 계약 문서 두 개는 시작 시부터 untracked였고 내용을 변경하지 않았다.
- 최종 시험 source는 위 HEAD + 이번 작업 트리 변경이다. 개별 파일 hash, diff hash, 양 interpreter의 dependency 목록은 [session manifest](../device-runtime/tmp/stabilization-20260906/session-manifest.json)에 고정했다. 이는 Desktop의 두 interpreter이며 Laptop baseline 증거가 아니다.
- 코드 issue 2개, production Python 3파일 / 추가+삭제 총 18줄(주석 포함), test 4파일. 6 production files / 실행 코드 400줄 / 6 test files 상한 안이다. 신규 architecture layer, schema/receipt migration, threshold/OCR 규칙 변경 없음.
- fresh **demo** 생성: 0회. 별도 회귀 교재인 G3-A 산출물을 S-03의 선정 demo로 바꾸어 부르지 않는다.

## S-01 / P1 — 수정 완료

실패 invariant: stable device의 새 프로세스 조작은 과거 receipt와 다른 operation ID여야 한다. 동일 연결의 동일 sequence 재전송은 한 번만 적용되어야 한다.

원인: `StmSerialControlSource`가 source마다 connection epoch 0으로 시작해 첫 입력을 모두 `stm-0001-0000000002`로 만들었다. 서버 영속 receipt가 새 create/reading command를 이전 조작으로 해석할 수 있었다.

수정: STM source에 bounded ASCII 실행 namespace를 추가했다. 기본 생성은 UUID 기반, 정식 composition은 C0 boot ID를 전달한다. 정상/legacy 입력과 강제 DOWN release ID에 같은 namespace를 쓴다. stable device ID, HELLO epoch, ACK/dedupe, hold/release timing, 서버 idempotency 계약은 유지한다.

증거:

- 수정 전 [targeted-before.log](../tmp/stabilization-20260906/targeted-before.log): 서로 다른 두 source의 ID가 같아 실패.
- 실제 S0Store 재사용: 동일 create ID retry는 같은 datapack, 새 boot create는 다른 datapack. 같은 device/book reading 재진입 시 cursor 복구 후 새 DOWN으로 다음 페이지/다음 generation 진행, 그 DOWN 재전송은 동일 snapshot 반환.
- namespace 최대 80자에서 `:create`, `:scan-open`, `:reading-open`, 실제 Host `-hold-xxxxxxxx` ID가 서버 128자 계약을 통과한다. 잘못된 namespace는 거부한다.
- composition의 STM namespace = 실제 C0 boot ID 확인. 기존 ACK/dedupe/HELLO/hold 회귀 유지.

## S-02 / P1 — 수정 완료

실패 invariant: ACK 전 pending artifact를 freeze로 보존한 경우 같은 scan 복구는 같은 engine/artifact/outbox lineage를 이어야 한다. 다른 scan 또는 active engine 중복 start는 거부해야 한다.

원인: freeze는 pending engine을 보존하지만 start는 engine 존재만으로 FatalPortError를 던졌다. Coordinator의 `retry_queue` 및 `resume_scanning` 경로가 이 불일치를 실제로 밟았다.

수정: frozen이고 scan reference가 동일한 engine에 한해 `_frozen=False`로 재개한다. create/start/cancel을 다시 호출하거나 identity history를 초기화하지 않는다. 닫힌 engine은 기존 신규 생성 경로를 사용한다. Coordinator/서버/Scanner 알고리즘 변경 없음.

증거:

- 수정 전 adapter `start → freeze → start(same scan)` FatalPortError 재현.
- 수정 전 실제 adapter + durable SQLite outbox + local HTTP S0/V4/S1 + fake camera/engine 조합에서 connection-loss 및 queue-failure 두 case 모두 `coordinator._retry_recovery → scanner.start`에서 실패(2 failed / 원래 case 1 passed).
- 수정 후 세 case 모두 same artifact/key/sequence 유지, ACK 전 파일 보존 및 false `spread_sent`/saved 없음, receipt 1 / L/R fragments 2, response-loss retry 후 ACK 1회, seal → READY → reading, ACK 후 cleanup 확인.
- pending 없는 freeze 후 새 engine 생성, frozen pending의 terminal ACK 후 close, 잘못된 scan/datapack 재개 거부, active restart 거부도 통과.
- 이 증거는 concrete software 경계 시험이다. 실제 C0 네트워크 단절/HC-05/카메라 수용을 대신하지 않는다.

## S-03 / P1 — BLOCKED

실제 시연 영상의 Laptop 경로 `C:\Users\user\Desktop\OCR_TEST`는 현재 Desktop에 없다. Laptop 접근 방법과 human observation을 요청했다. 디렉터리 자체에 접근하지 못했으므로 파일 수를 0이라고 단정하거나 임의의 MP4를 고르지 않았다. absolute path/filename/size/hash/resolution/FPS/frame count/duration 고정 및 선정 spread/side/order/핵심 내용 대조가 미완료다. 새 demo datapack은 만들지 않았다. 기존 archived revision은 변경하지 않았다.

## 회귀 결과

모든 subsystem은 `.venv-e0b/Scripts/python.exe` Python 3.11.8, 세 src를 명시한 PYTHONPATH, 패키지별 cwd/별도 pytest process, bytecode/cache off, ASCII 임시 경로에서 실행했다. assertion/acceptance 조건을 낮추지 않았다.

| 범위 | 결과 | Evidence |
|---|---:|---|
| 최종 변경 경계 + Device integration | 106 passed | [log](../device-runtime/tmp/stabilization-20260906/targeted-short-path.log), [JUnit](../device-runtime/tmp/stabilization-20260906/targeted-short-path.xml) |
| Device 전체 tests | 274 passed | [log](../device-runtime/tmp/stabilization-20260906/device-full.log), [JUnit](../device-runtime/tmp/stabilization-20260906/device-full.xml) |
| Scanner 전체 tests | 337 passed | [log](../device-runtime/tmp/stabilization-20260906/scanner-full.log), [JUnit](../device-runtime/tmp/stabilization-20260906/scanner-full.xml) |
| Parser 전체 tests | 619 passed, 4 skipped, 6 subtests passed | [log](../device-runtime/tmp/stabilization-20260906/parser-full.log), [JUnit](../device-runtime/tmp/stabilization-20260906/parser-full.xml) |

전체 합계: **1,230 passed / 4 skipped** (+ Parser subtests 6). 집중 회귀 수를 이 합계에 더하지 않는다. 4 skips는 Piper model/espeak 환경 변수 미지정에 따른 real Piper tests이며 PASS로 승격하지 않는다. `git diff --check` 통과.

환경/시험 구성 실패는 별도 처리했다:

- 첫 evidence 경로 지정 실수로 pytest 미실행. 경로 교정 후 root tmp 쓰기 권한 거부를 받아 escalation 후 최초 red evidence를 기록했다.
- 통합 시험 한 번에서 `UPLOAD_STORAGE_TEMPORARY` / HTTP 503 / upload journal `abandoned`를 확인했다. 실제 저장소 OSError 경계이며 기대 receipt가 없었다. 원본 [log](../device-runtime/tmp/stabilization-20260906/targeted.log)와 `device-runtime/tmp/stab-targeted-final` state를 보존했다. 짧은 ASCII basetemp에서 동일 assertions로 106 passed. 세부 OS 원인은 확정하지 않았다. 환경 요인으로 분류하며 제품 정상 전송 실패 증거를 삭제하지 않았다.
- 신규 S-01 fixture가 규정한 `pNNN` filename을 사용하지 않아 모든 page ID가 p001이 되었고 audio ID가 덮였다. fixture를 고유 `book-p001..003.png`로 교정했다. STM viewport=10/cell_count=10 fixture도 맞췄다. 제품 assertion을 바꾸지 않았다.

## G3-A input identity 및 replay

| 항목 | 값 |
|---|---|
| 원본 filename | `20260830_133526.mp4` |
| 기존 설정에서 찾은 local path | `D:\ASL_OCR_E0B\inputs\scanner-replay.mp4` |
| 실제 local filename / 크기 | `scanner-replay.mp4` / 242,882,956 bytes |
| 실행 전 계산 SHA-256 | `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8` |
| resolution / FPS | 3840×2160 / 59.69965076707844 |
| frame count / duration | 2,677 / 44.84113333333334 seconds |

G3-A **PASS**. 기존 `tools/windows/e0b_production_full_model_desktop_acceptance.py`를 실제 production PaddleOCR-VL/Piper와 실행했다. Device는 정식 local composition이다. 기존 thresholds/role-aware 판정 그대로이며 Desktop loopback이다. Laptop 원격 시험으로 확대 해석하지 않는다.

- 실행: 2026-09-06 07:53:38–07:57:39 UTC (KST 16:53:38–16:57:39). [run manifest](../device-runtime/tmp/g3a-e01/e0b-loopback-run-manifest.json), [격리 state/config](../device-runtime/tmp/g3a-w01).
- stable run device ID: `desktop-loopback-0cb03e130098`; scan: `scan-65e11033ff7a4c35a2526ae21352092c`.
- datapack: `datapack-f3eee3d21a8a40a4b0433fd82dc29ce5`, fresh READY revision 1. Immutable manifest SHA-256 `7d3dc081ffa150c134f62b58e7bb1bdc61bb857e81e8e9fedd7edc08b07f9417`.
- [role-aware boundary report](../device-runtime/tmp/g3a-e01/e0b-replay-boundary.json): `status=passed`, candidate verification 두 건 각각 N=5/different, `spread_sent=[1,2]`, EOF queued=2/acked=2. Page-change의 same 조기 판정과 candidate 검증을 혼합하지 않았다.
- [server evidence](../device-runtime/tmp/g3a-e01/e0b-server-evidence.json): receipt 2 / fragments 4 / duplicates 0; 각 upload attempt=1. spread source frame `video-00000092`, `video-00000365`에 각각 L/R가 연결된다.
- cutoff=2 후 sealed/published revision=1. Reading page IDs는 `pg-20f2fbf6dff5-00000001-L`, `...00000001-R`, `...00000002-L`, `...00000002-R` 순서이며 reverse navigation도 통과.
- [full-model report](../device-runtime/tmp/g3a-e01/e0b-production-full-model-report.json): `automated_status=passed`, `acceptance_failures=[]`, 151 audio resources verified. **원 보고서 `status=manual_pending`, `manual_listening_status=not_run`, heard=0은 그대로 유지**한다. `--no-playback`에서 기록된 playback lifecycle counters는 실제 speaker 청취 증거가 아니다.
- [model manifest](../device-runtime/tmp/g3a-e01/e0b-production-model-manifest.json): PaddleOCR-VL 56 files / tree SHA-256 `40411d09e06e9631687c1527a4c9555f84f633538e68635030c458ef456ebd66`; Piper model SHA-256 `624fd774e26895f24bebae1bd9a3379e3394baeade4b584924f83e414096e2c9`. `D:/ASL_OCR_E0B/models/paddleocr-vl`은 `D:/model_home_vl` junction으로 같은 model root임을 확인했다.

### Replay 이후 serving preflight

현재 production interpreter에서 repository의 `document_parser.datapack.preflight` CLI를 `--viewport-size 10`으로 실행했다. [preflight JSON](../device-runtime/tmp/g3a-e01/serving-preflight.json): catalog 1 / checked revision 1 / **error 0 / warning 21**, 4 pages / 69 focus items / 168 expected utterances / 142 checked audio files / 95 braille targets. 빈 catalog의 녹색이 아니다. Desktop 인증 document/system WAV fetch 및 unauthorized/cross-session/cross-device 거부도 [audio transport report](../device-runtime/tmp/g3a-e01/e0b-production-audio-transport.json)에서 통과했다.

21 warnings는 모두 `BRAILLE_TARGET_EMPTY`다. [항목별 원문/AST](../device-runtime/tmp/g3a-e01/braille-warning-items.json)와 [분류 목록](../device-runtime/tmp/g3a-e01/braille-warning-review.json)을 보존했다. INVALID/PARTIAL MATH 및 TEXT 안의 span이 포함되어 **전부 정상 일반 텍스트 clear라고 간주하지 않는다**. 회귀 교재의 지원 범위/점역 문제는 D-05로 유지하며, 실제 선정 demo의 필수 수식에서 재현되면 P1 재분류 대상이다. 이 preflight PASS가 OCR 의미/점역 내용/청취 수용 또는 S-03 demo dataset 준비를 대신하지 않는다.

G3-B는 입력 identity, 의도한 spread 순서/left-right 대응, candidate/page-change 구간, human content observation을 확보하지 못해 **BLOCKED**다. acceptance 1~9 전부 not_run이며 임의 expectation을 생성하지 않았다. combined G3는 FAIL(BLOCKED)이다.

## Deferred / 추가 분류

기존 D-01~D-09를 그대로 유지한다: reject는 원본 보존 후 새 datapack으로 재촬영; parser reject의 silent partial publish 금지; finalize 중 C0 loss는 서버 상태 조회 후 operator 절차; v3 DOWN만 필수 hold; 일반 OCR/카메라/점역 확대, 광범위 정리 및 Pi는 후속 범위다. 과거 Scanner golden 실패 3개는 이번 Scanner 337 tests에서 재현되지 않았다.

| ID | Boundary/근거 | 분류·workaround·재분류 trigger / 수정 상한 |
|---|---|---|
| D-10 | 별도 legacy `build_document_ir_from_vl` fixture의 비규격 filename은 fallback p001 중복을 만들 수 있음. 신규 synthetic fixture에서 audio index가 마지막 페이지만 남음 | Deferred. 정식 Scanner/S1의 explicit page identity 경로가 막힌 증거 없음. offline 입력은 고유 pNNN 이름 사용. 실제 선정 경로의 identity 중복이면 P0/P1 재분류. 이번 수정 0파일 |
| D-11 | production server log: installed Paddle CUDNN 9.9 vs runtime 9.5 경고 | Deferred 환경 의존성 경고. 이번 실제 full-model regression replay는 통과. 이후 inference critical-path failure가 발생하면 환경/제품 원인부터 분리. dependency 재설치/정리 0회 |

## Integration Entry Gate

| Gate | 판정 | 근거/남은 조건 |
|---|---|---|
| G0 | FAIL (BLOCKED) | Desktop HEAD+diff/interpreters/input/isolated state 고정. Laptop 동일 baseline, 실제 demo content/profile identity 미확인 |
| G1 | FAIL (BLOCKED) | S-01/S-02 닫힘. S-03 demo dataset/내용 확인 미완료 |
| G2 | PASS | 집중 106, 전체 1,230 passed; 환경/fixture 실패와 4 optional model skips를 분리 |
| G3-A Regression Replay | PASS | hash 일치, N=5, 2/4/0, cutoff 2, READY revision 1, 4-page reading; boundary passed |
| G3-B Demo Replay | BLOCKED | Laptop input 접근 및 human observation 미확보 |
| G3 combined | FAIL (BLOCKED) | A와 B 모두 PASS 조건 미충족 |
| G4 | FAIL (BLOCKED) | regression fresh catalog 1 revision/error 0 및 인증 WAV 검증 통과. 실제 선정 demo dataset/핵심 내용 및 사람의 대조는 없음 |
| G5 | FAIL (BLOCKED; STM 단계 진입 전 조건) | authoritative source hash만 기록. compiler/CubeIDE build log, firmware/flash 대응, 실제 wiring/v3 관측 준비 미확인 |

일반 bug hunting/refactoring 및 Deferred 수정은 시작하지 않는다. 남은 검증은 이 pass의 gate 범위로 제한한다. G0~G4 미충족 상태에서 안정화 완료나 Prototype Integration Baseline을 선언하지 않는다. G5/후속 물리 수용도 완료로 표시하지 않는다.

재개에 필요한 외부 정보: Laptop의 해당 디렉터리를 조사할 접속/공유 경로, 실제 demo spread/page 순서와 핵심 페이지를 확인할 human observation, Laptop source/dependency/profile 확인, STM 담당자의 build/flash/wiring 자료다. 입력을 확보해도 기존 regression output을 demo golden으로 사용하지 않는다. 원본/archived revision, 실패 시험 state 및 신규 replay state는 모두 보존했다. 실행 산출물은 session 전용 ignored `device-runtime/tmp` 아래이며 tracked 코드 변경에 포함하지 않는다.

## 후속 verification handoff — Laptop SSH 확인

위 stabilization 결과 및 G3-A PASS는 유지한다. 이후 verification-only 세션의 [상세 보고서](PROTOTYPE_DEMO_VERIFICATION_20260906.md)에 Laptop 현재 상태와 demo input identity를 기록했다. 새로운 제품 코드 변경은 없다.

- **G0 BLOCKED:** `C:\ASL_OCR`의 HEAD는 `84aa71b8bc55eeafd9f6729824f29f81b4caa6f0`, 수정 24개/untracked 3개이며 stabilization production 3파일이 줄바꿈 정규화 후에도 Desktop과 다르다. pull/reset/checkout하지 않았다.
- **Demo input identity 확보:** `C:\Users\user\Desktop\OCR_TEST\20260905_224928.mp4`, 한 파일, SHA-256 `dc16c5659ccf307f5829a5019138a8332a0f4cbc16607a55224f472850f691d8`, 3840×2160 / 약 29.992 FPS / 1,798 frames / 약 59.949초.
- **G3-B/G4 BLOCKED:** 입력 접근 공백은 해소됐지만 source 불일치 때문에 replay는 시작하지 않았다. 저장된 기본 replay launcher 대상 TOML도 현재 `pc_camera` profile이다. 사람의 원본/spread/핵심 내용 대조는 여전히 필요하다.
- 현재 재개 조건은 **Laptop 변경 보존을 전제로 명시적으로 승인된 source alignment → G0 재확인 → 격리 demo replay/profile/state 준비 → G3-B/G4 및 human observation**이다. 추가 stabilization pass나 일반 bug hunting은 시작하지 않는다.
