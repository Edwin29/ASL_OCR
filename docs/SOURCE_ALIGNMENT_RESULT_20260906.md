# Laptop integration checkout and G0 environment result — 2026-09-06

최종 판정: **source alignment PASS, Python/dependency isolation PASS, G0 전체 BLOCKED, G3-B 미실행/준비 BLOCKED**.

`C:\ASL_OCR_INTEGRATION`에는 Desktop에서 검증된 stabilization source를 재현했다. `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905`에는 별도 venv, model copy, replay profile, 빈 state root를 준비했다. 남은 blocker는 기존 connectivity/secret이 있는 Laptop `D:` volume의 content I/O 불능과 Desktop server health HTTP 502다. 이 두 경계를 우회하기 위해 secret을 복사하거나 새로 만들지 않았다.

## Source identity — PASS

- Base commit: `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e`.
- 독립 Git checkout이다. 기존 `C:\ASL_OCR`과 `.git` metadata/alternates/worktree를 공유하지 않는다.
- Authoritative source는 base commit + bounded stabilization의 S-01/S-02 working-tree 변경이다.
- Desktop session manifest에 고정된 production 3개, test 4개, 계약 문서 2개만 이식했다. 전체 Desktop working tree나 runtime data를 복사하지 않았다.
- 예상 tracked diff 6개, 예상 untracked 3개다. 예상 밖 tracked diff는 0개다.
- 이식한 9개 파일은 Desktop manifest와 raw SHA-256 및 normalized hash가 모두 일치한다.
- Python `/src/` 237개에는 content mismatch가 없다. 환경 구성 전후 새 checkout 1,626개 파일의 raw hash 변화는 0개다.

Git LFS payload 264개는 materialize하지 않았다. 모두 과거 `book-scanner/experiment_outputs`의 PNG/JPG 261개와 `document-parser/data/debug/model_home`의 `.pdiparams` 3개다. 각 pointer OID는 Desktop payload SHA-256과 일치한다. G3-B runtime은 이 파일들을 참조하지 않고 별도 model/input identity를 사용하므로 필요한 LFS payload는 0개로 판정했다. 이를 전체 repository payload 동일성으로 확대하지 않는다.

## Python/dependency environment — PASS

| 항목 | 결과 |
|---|---|
| Interpreter | `C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe` |
| Python | 3.11.9; Desktop test interpreter는 3.11.8이므로 patch version 차이를 기록 |
| Interpreter SHA-256 | `21bb438c0d4a6f1f164b9a646f6ee000340185e5871180aec06db8d3f07c0082` |
| Desktop dependency differences | 0 |
| `pip check` | exit 0, `No broken requirements found.` |
| Import contamination | 기존 `C:\ASL_OCR` source path 0 |

실제 import path:

| Package | `__file__` |
|---|---|
| device runtime | `C:\ASL_OCR_INTEGRATION\device-runtime\src\asl_device\__init__.py` |
| book scanner | `C:\ASL_OCR_INTEGRATION\book-scanner\src\book_scanner\__init__.py` |
| document parser | `C:\ASL_OCR_INTEGRATION\document-parser\src\document_parser\__init__.py` |

처음 venv 생성 시 기본 `pip 24.0`/`setuptools 65.5.0` metadata가 복사한 `pip 26.2.1`/`setuptools 84.0.0`과 중복되어 `pip check`가 실패했다. 이는 product failure가 아니라 environment construction failure였다.

허용된 전용 venv 정리 범위에서 다음과 같이 수정했다.

- 새 venv 내부의 `pip-24.0.dist-info`, `setuptools-65.5.0.dist-info`, 기존 cv2 tree만 제거했다.
- Desktop 검증 venv의 Pygments 2.21.0, iniconfig 2.3.0, pluggy 1.6.0, pytest 9.1.1, opencv-python 5.0.0.93 payload를 exact archive로 이식했다.
- archive SHA-256: `b03f9ff287f60953711f3586dc8ad5af0946d7acc167ca9ad20111c930c8c881`.
- package index를 사용하거나 dependency를 upgrade하지 않았다.
- 실제 cv2는 Desktop과 같은 5.0.0이며 새 venv에서 import된다. numpy 2.3.5, Pillow 12.3.0, pyserial 3.5 smoke도 통과했다.

Laptop runtime 전용 추가 package는 sounddevice 0.5.6, cffi 2.1.1, pycparser 3.0, py-spy 0.4.2다. 기존 Laptop 환경의 audio/runtime 필요 항목으로 보존하고 manifest에 명시했다. Desktop과 공통인 모든 distribution의 이름/version 차이는 0개다.

## Demo replay runtime preparation

Runtime root: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905`.

| 항목 | 결과 |
|---|---|
| App config | `device-app.demo-replay.toml`, SHA-256 `ac9341e812f7be927142f38656767f9aae3d5aa0c2c601112678dbfc5b2f61d2` |
| Launcher | `run-demo-replay.cmd`, SHA-256 `e7944f25aa12ea8ce194aa80afec8174c726813abf0ceb85ef4ef6a604787052` |
| Scanner profile | replay |
| Viewport | 10 |
| Sample cadence | 100 ms, 기존 replay contract 유지 |
| Identity budget | 30,000 ms, 기존 replay contract 유지 |
| Controls / feedback | console / jsonl |
| Reading audio | enabled, sounddevice |
| State | `state/delivery.sqlite3`, `state/artifacts/staging`, `state/artifacts/ready`; 준비 시 파일 0, 기존 state와 분리 |
| Models | runtime root에 Desktop verified bundle 복제; 확인한 10개 hash 모두 기존 Desktop/Laptop identity와 일치 |
| Demo MP4 | `C:\Users\user\Desktop\OCR_TEST\20260905_224928.mp4`; SHA-256 `dc16c5659ccf307f5829a5019138a8332a0f4cbc16607a55224f472850f691d8` |
| Video decode identity | open 성공, 3840×2160, 29.991943 fps, 1,798 frames, 59.949433 seconds |

Model archive는 Desktop의 `D:\ASL_OCR_E0B\models` 13파일을 그대로 담은 40,200,747-byte bundle이며 ZIP SHA-256은 `cc3a2a9d9f5098070caa25f88aac365642cd07a33a7b506e4bd900968a262466`이다. Source repository에 넣지 않았다.

App config는 기존 stable device ID와 API secret을 바꾸지 않기 위해 `D:\ASL_OCR_E0B\device-connectivity.e0b.remote.toml`을 명시적으로 참조한다. Secret 값은 읽거나 manifest에 기록하지 않았다. Stable device ID `laptop-device-001`은 이전 hash evidence로 고정되어 있으며 이번 작업에서 변경하지 않았다.

## 현재 blockers

### ENV-03 — Laptop D: content I/O unavailable

`fsutil fsinfo drives`에는 `C:\ D:\ G:\`가 보이지만, `D:\ASL_OCR_E0B`의 directory/file 접근과 `manage-bde -status D:`가 반환되지 않는다. 10초 child timeout도 kernel I/O 대기에서 종료되지 않아 수동으로 process tree를 정리했다. 일부 pending-I/O Python process는 `taskkill /F /T` 후에도 process table에 남았다. Laptop reboot, volume unlock/repair 또는 물리 storage 확인은 이번 허용 범위를 넘어 실행하지 않았다.

이 때문에 다음을 현재 시점에 재검증할 수 없다.

- connectivity TOML의 current hash와 full config parse
- API secret file availability
- stable device ID의 현시점 재-read
- 기존 D: production config/state의 현시점 접근성

Desktop에서 복제한 models와 새 C: state 덕분에 OCR runtime asset/state는 D:에 의존하지 않는다. 그러나 connectivity/secret을 우회 복사하지 않았으므로 G3-B 실행은 차단된다. 첫 D: 기반 runtime root 생성 시도도 I/O에 걸렸으며 존재/부분 생성 여부를 재접근해 확인하지 않았다. 기존 `D:\ASL_OCR_E0B`에 삭제/reset 명령은 실행하지 않았다.

### ENV-04 — Desktop server health HTTP 502

Laptop의 새 venv에서 `https://desktop-ekp6an5.taild2128f.ts.net/api/v1/health`를 GET한 결과 157 ms 후 HTTP 502였다. Tailscale HTTPS endpoint에는 도달했지만 ASL OCR upstream health가 성공하지 않았다. Server 시작/재구성은 이번 허용 범위에 포함되지 않아 수행하지 않았다.

## 기존 repository/data 보존

- 기존 `C:\ASL_OCR`의 기록한 1,614파일 raw hash 변화 0, Git status 동일(24 modified / 3 untracked).
- `capture_phone_snapshot.py`를 포함한 기존 untracked 파일을 보존했다.
- 기존 SQLite/artifacts/evidence를 삭제·reset·연결하지 않았다.
- secret, SSH/Tailscale 설정, stable device ID를 변경하지 않았다.
- product source, scanner threshold, protocol semantics, datapack identity, state transition, test assertion을 변경하지 않았다.
- G3-B, G4, product regression은 실행하지 않았다.

## G0 및 G3-B 준비 판정

| 항목 | 판정 |
|---|---|
| Source baseline | PASS |
| Expected stabilization diff/hash | PASS |
| Import isolation | PASS |
| Dependency alignment / pip check | PASS |
| Required G3-B LFS payload | PASS; 필요 항목 0, pointer OID 검증 완료 |
| Demo model/input identity | PASS |
| Isolated replay profile/state | PASS, 단 full config load 전 |
| Stable connectivity/secret availability | BLOCKED — ENV-03 |
| Server health | BLOCKED — ENV-04 |
| **G0 전체** | **BLOCKED** |
| **G3-B 실행 준비** | **BLOCKED** |
| G3-B execution | 미실행 |

G0를 닫으려면 D: content I/O가 정상화된 뒤 connectivity config/hash, `laptop-device-001`, secret file existence를 재검증하고 app config를 실제 `DeviceAppConfig.from_toml`로 load해야 한다. 이어 server `/api/v1/health`가 정상 응답해야 한다. 이 두 조건이 충족되기 전에는 G3-B를 실행하지 않는다.

## Evidence

Desktop evidence root: `device-runtime/tmp/source-alignment-20260906/`.

- `source-manifest.json`, `source-result.json`, `lfs-audit.json`: base/source/diff/LFS identity.
- `original-before.json`: 기존 Laptop source/status 보존 기준.
- `environment-copy.json`, `environment-repair.json`, `desktop-missing-deps.zip`: venv 구성과 exact dependency payload.
- `verification-result.json`, `dependency-diagnosis.py.stdout`: imports, distribution entries, pip check 전후.
- `runtime-prepare-result.json`, `desktop-models.zip`: C: runtime/model preparation identity.
- `integration-environment-manifest.json`: 최종 source/environment/runtime/config/model/input/network 결과. Secret 값 없음.

Laptop manifest: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\integration-environment-manifest.json`.

Code modification: **없음**. Environment/runtime preparation만 수행했다.
