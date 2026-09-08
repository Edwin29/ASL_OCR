# Laptop source alignment — read-only assessment (2026-09-06)

현재 **G0 BLOCKED**. 권고는 기존 `C:\ASL_OCR`과 외부 환경/state를 보존하고, **별도 독립 clean checkout**을 integration 검증용으로 준비하는 것이다. 이 보고서는 실행 승인을 위한 assessment이며 alignment는 수행하지 않았다.

작업 계약은 `PROTOTYPE_STABILIZATION_REPORT_20260906.md`와 사용자의 이번 read-only 지시다. SSH의 기존 인증을 사용했다. Laptop Git/source/config/environment/credential을 수정하지 않았으며 pull/reset/checkout/merge/rebase/clean/commit을 실행하지 않았다. Desktop에는 비교 evidence와 이 보고서만 추가했다. 새로운 stabilization pass, replay, 제품 테스트는 실행하지 않았다.

## 1. 비교 기준과 commit 차이

| 항목 | 확인 결과 |
|---|---|
| Laptop | `LAPTOP-HUM24QK4`, `C:\ASL_OCR` |
| Laptop HEAD | `84aa71b8bc55eeafd9f6729824f29f81b4caa6f0` |
| Desktop HEAD | `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e` |
| HEAD 비교 | Laptop-only 0 / Desktop-only 5; Laptop HEAD는 Desktop HEAD의 ancestor |
| Laptop working tree | modified 24, untracked 3; snapshot 전후 status 동일 |
| 실제 stabilization source | Desktop HEAD **+ 미커밋 S-01/S-02 production/test 변경**; session manifest의 파일 hash로 식별 |

Desktop-only commit은 오래된 순서로 다음과 같다. 이 비교는 두 HEAD 사이의 비교이며 모든 Laptop branch의 조사 결과를 뜻하지 않는다.

| Commit | Subject |
|---|---|
| `b6ed3e4fb8a5e6dd7c12f93ba8a6710bfca925f2` | Improve OCR processing workflow |
| `0af0a395992b2fa76bfa72b4d620da7d2fa9eb12` | feat: decouple STM input acknowledgements from device I/O |
| `c8fc8ef47bb0ad95fc0ebe00ff3a2115f761612e` | feat: contain braille failures and preflight datapacks |
| `3ad7edf7a97df426862893e61662cc3101a79cc2` | docs: specify down hold repeat correction |
| `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e` | fix: make down hold repeat release-safe |

`ea7e6f2`만 checkout하면 S-01/S-02 stabilization source가 되지 않는다. 승인 후 source를 고정할 때 3개 production 파일, 4개 test 파일(신규 `test_stm_operation_identity.py` 포함), 계약/보고서를 명시적으로 포함해야 한다. 현재 상태를 이미 승인된 Prototype Integration Baseline commit으로 표현하지 않는다.

## 2. 변경 분류와 전체 목록

분류 A = Desktop baseline에 이미 반영된 오래된 변경, B = Laptop/환경 전용 보존 항목, C = 실험/임시 변경, D = 목적 불명으로 human decision 필요.

비교는 원본 bytes를 보존한 뒤 UTF-8 BOM/줄바꿈을 정규화해 수행했다. 아래 “동일”은 이 정규화 이후 전체 내용 동일을 뜻한다. modified **20개는 동일**, 나머지 **4개는 이후 Desktop 추가사항이 없는 구버전/부분 반영본**이다. 동일성은 내용에 대한 판단이며 누가 어느 방향으로 복사했는지의 이력까지 증명하지 않는다.

| # | Laptop modified file | 분류 / Desktop 대비 |
|---|---|---|
| 1 | `book-scanner/src/book_scanner/video/__init__.py` | A / 동일 |
| 2 | `book-scanner/src/book_scanner/video/camera_host.py` | A / 동일 |
| 3 | `book-scanner/src/book_scanner/video/engine.py` | A / 동일 |
| 4 | `book-scanner/src/book_scanner/video/opaque_identity.py` | A / 동일 |
| 5 | `book-scanner/src/book_scanner/video/operator_preview.py` | A / 동일 |
| 6 | `book-scanner/src/book_scanner/video/runtime_composition.py` | A / 동일 |
| 7 | `book-scanner/src/book_scanner/video/sources.py` | A / 동일 |
| 8 | `book-scanner/tests/unit/video/test_engine_v3a5.py` | A / 동일 |
| 9 | `book-scanner/tests/unit/video/test_opaque_identity.py` | A / 동일 |
| 10 | `book-scanner/tests/unit/video/test_sources.py` | A / preview test 반영, 이후 crop/HTTP snapshot tests 없음 |
| 11 | `device-runtime/src/asl_device/adapters/http_connectivity.py` | A / 동일 |
| 12 | `device-runtime/src/asl_device/adapters/http_s0.py` | A / 동일 |
| 13 | `device-runtime/src/asl_device/adapters/local_feedback.py` | A / 동일 |
| 14 | `device-runtime/src/asl_device/app_config.py` | A / HoldRepeatConfig 도입 전 |
| 15 | `device-runtime/src/asl_device/coordinator.py` | A / LONG 5-step burst 제거 전 |
| 16 | `device-runtime/src/asl_device/delivery.py` | A / 동일 |
| 17 | `device-runtime/src/asl_device/local_composition.py` | A / hold controller 및 S-01 namespace wiring 전 |
| 18 | `device-runtime/src/asl_device/protocols.py` | A / 동일 |
| 19 | `device-runtime/src/asl_device/types.py` | A / 동일 |
| 20 | `device-runtime/tests/unit/test_http_connectivity.py` | A / 동일 |
| 21 | `device-runtime/tests/unit/test_http_s0.py` | A / 동일 |
| 22 | `device-runtime/tests/unit/test_laptop_feedback.py` | A / 동일 |
| 23 | `tools/windows/e0b-laptop-read.bat` | A / 동일 |
| 24 | `tools/windows/e0b-laptop-run.bat` | A / 동일 |

| # | Laptop untracked file | 분류 / Desktop 대비 / 보존 판단 |
|---|---|---|
| 1 | `tools/windows/e0b-android-ip-camera-run.bat` | A / 전체 동일, Desktop에서 이미 tracked |
| 2 | `device-runtime/device-app.android-ip-camera.example.toml` | A / 구버전 example; Desktop의 orientation 설명 2줄과 rotation=0 설정 2줄만 없음. Laptop 고유 실제 profile과 구분 |
| 3 | `capture_phone_snapshot.py` | C / Desktop에 없는 24줄 휴대폰 snapshot 진단 스크립트. Laptop 경로/endpoint 포함; 원본 별도 보존, production 재적용 대상 아님 |

합계 **A 26개, C 1개**. 조사한 27개 source 변경 중 고유한 Laptop production 기능이나 목적 불명 잔여 변경은 발견하지 않았다. B는 아래 외부 실제 설정/환경/state에서 확인된다. D를 억지로 부여하지 않으며, 진단 스크립트의 향후 유지/폐기 결정은 사람에게 남긴다.

`capture_phone_snapshot.py`는 기존 secret 파일 경로를 읽어 휴대폰 HTTPS snapshot을 가져오고 JPEG 저장/크기를 확인하는 도구다. 인증서 검증을 끄는 호출과 고정 endpoint가 있다. 실행하거나 secret 내용을 읽지 않았다. 이 독립 진단 도구의 정리는 **Deferred**이며 현재 integration gate를 막는 제품 결함으로 분류할 증거는 없다.

### 동일하지 않은 modified 4개

- `test_sources.py`: Laptop 417줄, Desktop 595줄. Laptop HEAD 대비 추가된 19줄 parameterized preview test는 Desktop에도 있다. Desktop 대비 없는 부분은 HTTP snapshot import 및 crop/HTTP snapshot tests다. Laptop 고유 assertion이나 기능을 보존해야 하는 상황은 아니다. 의도적으로 테스트를 삭제했다는 이력 판단은 하지 않는다.
- `app_config.py`: Laptop 596줄, Desktop 626줄. `HoldRepeatConfig`의 650/180 기본값·검증, config field, local_io allowlist/parsing/wiring이 없다.
- `coordinator.py`: Laptop은 `_BURST_STEPS=5`와 catalog UP/DOWN LONG 5-step 경로를 유지한다. Desktop은 burst를 제거하고 해당 action을 SHORT로 제한한다. 이 구동작을 Laptop-specific 변경으로 재적용하면 release-safe 계약을 되돌릴 위험이 있다.
- `local_composition.py`: Laptop 238줄, Desktop 244줄. `HoldRepeatController` import/주입과 `event_namespace=connectivity.boot_id`가 없다.

마지막 3개 파일은 Desktop의 `b6ed3e4`, `0af0a39`, `c8fc8ef`, `3ad7edf` 시점 파일과 정규화 후 정확히 일치한다. `test_sources.py`와 Android example은 조사한 commit의 전체 파일과 정확히 일치하지 않는 부분 반영본이다.

## 3. S-01 / S-02 production 차이

| File | Laptop 상태 | Desktop stabilization 차이 / 의미 |
|---|---|---|
| `device-runtime/src/asl_device/adapters/stm_serial.py` | dirty 목록에 없으며 Laptop HEAD 구버전과 동일; 252줄 | Desktop 515줄. S-01 event namespace 외에도 비동기 I/O worker/queue, immediate HELLO, ACK/sequence dedupe, DOWN activated/released 지원 등 intervening commit 변화가 있다. 단순 namespace 패치만 복사하는 것으로 baseline alignment를 대체할 수 없음 |
| `device-runtime/src/asl_device/local_composition.py` | modified 구버전 | C0 boot ID를 STM namespace에 전달하지 않음. hold controller wiring도 없음 |
| `device-runtime/src/asl_device/adapters/book_scanner_runtime.py` | dirty 목록에 없으며 Laptop HEAD와 동일 | S-02의 5줄 early return 없음: 기존 engine이 frozen이고 같은 scan_session이면 unfreeze 후 engine/lineage를 유지하는 동작이 Laptop에 없음 |

따라서 dirty 파일만 맞춰도 G0는 닫히지 않는다. **전체 source revision + stabilization patch/test identity**를 맞춰야 한다. 이번 assessment에서는 event identity, state transition, scanner threshold 등 계약을 변경하지 않았다.

## 4. Code synchronization과 분리할 보존 항목

| 항목 | 확인값 / 보존 원칙 |
|---|---|
| 실제 config root | `D:\ASL_OCR_E0B`; 원본 TOML과 backups 보존(B) |
| 기본/webcam profile | `device-app.e0b.toml`, `device-app.e0b.webcam.toml`: pc_camera, viewport 10, camera index 0, sample 500ms, identity budget 8000, console controls, UVDoc auto |
| Android 실제 profile | `device-app.android-ip-camera.toml`: viewport 40, sample 750ms, identity budget 30000. 레거시 capture 환경으로 보존. 새 replay에 이 값을 자동 승계하지 않음 |
| config backups | `device-app.e0b.webcam.before-camera1-20260904.toml` 및 verified/backup 변형 등. source cleanup 대상 아님 |
| Stable device ID | `laptop-device-001`; 임의 재생성하지 않음 |
| Server origin | `https://desktop-ekp6an5.taild2128f.ts.net`; Laptop 연결 설정으로 분리 |
| 기존 test state | `D:\ASL_OCR_E0B\state\delivery.sqlite3` (81,920 bytes), artifacts/ready의 3 spread 디렉터리와 L/R/source/manifest. DB와 artifact 집합을 함께 보존. pending/acked 상태는 이번에 판정하지 않음 |
| 부가 state evidence | `state\fetch_phone_snapshot.py`, `state\page-change-current.jpg`도 존재. 내용/보존 목적은 추가 조사하지 않았으므로 그대로 보존하고 삭제 판단 유보 |
| Secrets | 기존 `D:\ASL_OCR_E0B\secrets` 및 기존 SSH 인증. 내용 읽기/복사/변경 없이 보존 |
| Python/venv | `C:\ASL_OCR\.venv-e0b\Scripts\python.exe`, Python 3.11.9; Desktop test Python 3.11.8. 기존 venv 보존, Desktop venv 무조건 복사 금지 |
| Editable imports | `.pth`가 `C:\ASL_OCR\device-runtime\src`, `book-scanner\src`, `document-parser\src`를 직접 가리킴. 새 checkout에서 기존 interpreter만 재사용하면 구 source import 위험 |
| Dependency identity | 이전 environment evidence에 전체 version 기록; Laptop sounddevice 0.5.6 등. source alignment와 dependency 설치/변경을 분리 |
| Model identity | `D:\ASL_OCR_E0B\models`의 UVDoc/runtime/checkpoint 및 page-number 관련 확인한 10파일 hash는 Desktop과 일치. 모델 전체에 대한 포괄적 동일성 주장은 아님. 재다운로드 불필요 |
| Demo MP4 | `C:\Users\user\Desktop\OCR_TEST\20260905_224928.mp4`, 216,858,835 bytes; SHA-256 `dc16c5659ccf307f5829a5019138a8332a0f4cbc16607a55224f472850f691d8`. 별도 입력으로 보존 |

현재 `e0b-replay-run.bat`는 기본 launcher를 전달 호출하며 실제 기본 profile은 pc_camera다. 이름만 보고 demo MP4 replay라고 판정하지 않는다. 승인 후 별도 demo config/state root를 구성하고 원본 config를 유지해야 한다. 기존 state를 새 source의 시험 실행 대상으로 자동 사용하지 않는다. 동일 device ID를 쓰는 기존/신규 runtime을 동시에 실행하지 않도록 이후 실행 절차에서 확인해야 한다.

## 5. 손실 위험

- untracked 3파일은 일반 `git diff` patch에 포함되지 않는다. 특히 `capture_phone_snapshot.py`는 Desktop 대체본이 없다.
- modified 24파일의 원본 bytes/작업 이력은 backup 없이 덮어쓰면 사라진다. 내용이 이미 반영된 A 분류라도 지금 삭제할 근거로 사용하지 않는다.
- branch 생성만으로 미커밋/미추적 파일이 보존되지 않는다. `.gitignore`에 가려진 venv/config/model/state 역시 Git patch나 commit만으로 보존되지 않는다.
- SQLite 단일 파일만 복사하는 live backup은 journal/WAL 및 artifact와 일관성이 어긋날 수 있다. 향후 backup 필요 시 실행 상태를 확인하고 DB/artifact를 일관된 집합으로 보존해야 한다. 현재 snapshot은 전체 Laptop backup이 아니다.
- Desktop HEAD만 배포하면 미커밋 stabilization production 수정과 신규 regression test가 누락된다.
- 오래된 Laptop patch 전체를 새 baseline 위에 다시 적용하면 hold/STM 계약을 되돌릴 수 있다.

## 6. 전략 비교와 권고

| 전략 | 장점 | 현재 상태에서의 위험 / 판단 |
|---|---|---|
| 기존 위치에서 patch/branch/full backup 후 source 정렬 | 기존 launcher/venv 경로를 유지하기 쉬움 | 원본 작업공간에 직접 영향. patch/branch만으로 untracked/ignored/state 보존 불충분. 되돌리기 부담이 큼 |
| stabilization 위에 Laptop-specific 변경 선별 재적용 | 필요한 고유 기능만 유지 가능 | 현재 26개는 이미 반영된 내용이고 고유 1개는 진단 도구라 production 재적용 필요가 입증되지 않음. 잘못 선별하면 구계약 복원 위험 |
| **별도 독립 clean checkout** | 기존 source/작업상태 보존, 비교와 실행 경계 명확, 기존 경로로 돌아가기 쉬움 | 추가 공간과 별도 import/config/state 검증 필요. 기존 venv 경로를 그대로 신뢰할 수 없음. **현재 권고** |

별도 `git worktree`도 가능하지만 원본 `.git`의 linked-worktree metadata/refs를 공유한다. 기존 repository 보존 의도가 강한 이번 상태에서는 **독립 checkout**을 우선 추천한다. 후보 `C:\ASL_OCR_INTEGRATION`은 read-only 확인 시 존재하지 않았다. 디렉터리는 생성하지 않았고 공간/설치 가능 여부는 실행 전에 추가 확인해야 한다.

승인 이후 제안하는 순서는 다음과 같다. 아직 어느 단계도 실행하지 않았다.

1. 현 Laptop snapshot과 보존 목록을 기준으로 원본을 유지한다. 별도 backup이 필요하면 source/untracked/ignored/environment/state를 구분해 완전성을 확인한다.
2. Desktop의 HEAD + 승인된 stabilization 변경 + 신규 test/계약 문서를 review 가능한 고정 source로 만든다(별도 승인된 commit 또는 hash manifest를 가진 source bundle). `ea7e6f2`만 baseline으로 사용하지 않는다.
3. 별도 독립 checkout에 그 source를 배치하고 commit/patch 및 관련 파일 hash를 Desktop manifest와 대조한다. 기존 Laptop patch 26개를 재적용하지 않는다. 진단 스크립트는 기존 위치에서 보존한다.
4. 기존 venv는 유지하고 새 실행 환경의 세 패키지 import 경로가 새 checkout인지 검증한다. 필요한 환경 구성은 기존 venv를 변형하는 대신 별도로 수행한다. models/secrets는 기존 identity를 보존한다.
5. 기존 config/state를 덮어쓰지 않는 전용 demo replay profile/state root를 준비한다. stable device ID와 연결 대상, source/model/input identity를 기록하고 G0를 재판정한다.
6. G0를 통과한 뒤 G3-B 및 해당 READY revision의 G4를 수행한다. 사람의 실제 원본/OCR/음성/수식/표/점자 대조가 없으면 content acceptance는 계속 BLOCKED다.

## 7. Evidence 및 현재 gate

Evidence root: `device-runtime/tmp/demo-verification-20260906/` (Desktop 로컬 ignored evidence).

- `alignment-snapshot.json`: Laptop HEAD/status 전후, 24 modified/3 untracked와 S-01/S-02 관련 추가 2파일의 원본 bytes 및 HEAD bytes/hash.
- `alignment-comparison.json`: 파일별 정규화 hash, 동일성, 줄 수.
- `alignment-diffs/`: Laptop HEAD→working 및 Desktop→Laptop diff.
- `historical-matches.json`: 구 commit 파일과의 내용 대조.
- `alignment-preservation.json`: editable `.pth` 경로, state 파일 목록, 후보 checkout 경로 존재 여부.
- `laptop-baseline-raw.json`, `laptop-environment-input.json`, `environment-comparison.json`: 앞선 baseline/config/dependency/model/input 확인.
- `../stabilization-20260906/session-manifest.json`: authoritative Desktop stabilization 파일 identity.

| Gate | 현재 판정 |
|---|---|
| G0 | **BLOCKED** — source/실행 환경 alignment 미실행 |
| G3-A | 이전 **PASS** 유지; 이번 재실행 없음 |
| G3-B | **BLOCKED** — G0 선행 조건 미충족; 이번 replay 없음 |
| G4 demo | **BLOCKED** — 새 demo READY revision/preflight 없음 |

새로운 제품 결함을 재현하거나 P0/P1 code work를 추가하지 않았다. 확인된 source mismatch와 editable import 경로는 G0를 막는 baseline/environment 문제다. 임시 진단 도구 정리는 Deferred다. state 부가 파일의 목적 판단과 demo content acceptance는 human decision/observation 대상으로 남긴다. **Code modification 없음. Alignment 미실행. Integration 준비 완료 선언 없음.**
