# Laptop baseline and demo verification — 2026-09-06

Authoritative starting handoff: [PROTOTYPE_STABILIZATION_REPORT_20260906.md](PROTOTYPE_STABILIZATION_REPORT_20260906.md). This follow-up is verification/diagnosis only. G3-A remains PASS; it was not rerun. No new bounded stabilization pass was started.

## Final gates

| Gate | Result | Reason |
|---|---|---|
| G0 | **BLOCKED** | Laptop committed HEAD and working source differ from the Desktop stabilization source. Existing Laptop changes require a separate alignment decision. |
| G3-B | **BLOCKED / not_run** | Demo MP4 identity is now fixed, but G0 is not satisfied. No Scanner/upload/finalize run was started. |
| G4 | **BLOCKED / not_run** | No fresh demo READY revision exists from this verification. No demo preflight or human content acceptance was performed. |

Prototype Integration Baseline is not declared. Previous G3-A regression preflight does not substitute for demo G4.

## Phase 1 — observed Laptop baseline

SSH target: `user@100.106.45.8`; observed host: `LAPTOP-HUM24QK4`. Existing SSH authentication and strict host-key checking succeeded outside the Desktop sandbox. The sandbox could not access the existing known host entry. No passwords, private keys, SSH configuration, or known_hosts entries were created or changed.

Baseline snapshot: `2026-09-06T09:02:25.7557302Z`. Evidence was written only to Desktop's ignored [session directory](../device-runtime/tmp/demo-verification-20260906). Remote repositories/configuration/model files were read only; Python probes used `-B` and git used `GIT_OPTIONAL_LOCKS=0`.

| Required observation | Result |
|---|---|
| Main repository | `C:\ASL_OCR`, confirmed Git top-level `C:/ASL_OCR` |
| Laptop HEAD | `84aa71b8bc55eeafd9f6729824f29f81b4caa6f0` |
| Laptop status | **24 modified tracked files, 3 untracked entries**; complete list in [baseline JSON](../device-runtime/tmp/demo-verification-20260906/laptop-baseline-raw.json) |
| Desktop reference | `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e` + the completed S-01/S-02 working-tree changes pinned by the handoff manifest |
| Source equivalence | **No**. All three stabilization production files differ even after CRLF→LF normalization; [hash comparison](../device-runtime/tmp/demo-verification-20260906/source-comparison.json) |
| Launcher interpreter | `C:\ASL_OCR\.venv-e0b\Scripts\python.exe`; executed read-only probe confirms Python **3.11.9** |
| Global Python | `C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe`; not the launcher-selected virtual environment |
| Active runtime | No Python application process was observed in initial inventory; profiles below describe saved configuration, not a running Device process |
| Config root | `D:\ASL_OCR_E0B` |
| Stable device ID | `laptop-device-001` from `device-connectivity.e0b.remote.toml` |
| Configured server origin | `https://desktop-ekp6an5.taild2128f.ts.net`; authenticated health/runtime connection was not exercised because G0 is blocked |
| Existing state | `D:\ASL_OCR_E0B\state`; outbox `state/delivery.sqlite3`; artifact/staging roots `state/artifacts/ready` and `state/artifacts/staging` |
| New demo state | Not created; existing outbox/datapacks were not cleared, migrated, or reused for a new run |

Laptop's committed HEAD is five commits before Desktop's committed HEAD in the Desktop Git history: OCR workflow, asynchronous STM ACK, braille containment/preflight, DOWN correction documentation, and release-safe DOWN hold. This does not prove that none of their content was manually copied into the dirty Laptop tree; actual source hash disagreement is the decisive equivalence failure. Copying only the three stabilization files would not establish complete baseline equivalence.

The 24 modified files include Scanner engine/identity/source/runtime composition, Device HTTP/config/coordinator/delivery/types, tests, and launchers. Untracked entries are `capture_phone_snapshot.py`, `device-runtime/device-app.android-ip-camera.example.toml`, and `tools/windows/e0b-android-ip-camera-run.bat`. Their changes were preserved.

A secondary checkout exists at `D:\ASL_OCR_STM_TEST`. Git refused HEAD/status inspection because the filesystem does not record ownership (`dubious ownership`). Its three source hashes also differ from the Desktop reference. No global or local `safe.directory` exception was added. Empty fields in the raw JSON mean **unavailable**, not clean status. This auxiliary checkout was not selected as the runtime baseline.

### Dependencies and models

[Environment/input JSON](../device-runtime/tmp/demo-verification-20260906/laptop-environment-input.json) contains the full installed distribution inventory, resolved interpreter, launcher evidence, and model file hashes. [Comparison JSON](../device-runtime/tmp/demo-verification-20260906/environment-comparison.json) compares against Desktop's recorded Device/test environment.

| Dependency | Laptop | Desktop Device/test |
|---|---|---|
| Python | 3.11.9 | 3.11.8 |
| numpy | 2.3.5 | 2.3.5 |
| opencv-contrib-python | 4.10.0.84 | 4.10.0.84 |
| paddlepaddle | 3.3.1 | 3.3.1 |
| paddleocr / paddlex | 3.7.0 / 3.7.2 | 3.7.0 / 3.7.2 |
| torch | 2.13.0 | 2.13.0 |
| pillow / pyserial | 12.3.0 / 3.5 | 12.3.0 / 3.5 |
| sounddevice | 0.5.6 | Not listed in the recorded Desktop Device/test distribution inventory |

The Python patch-version difference is recorded, not treated as a proven software failure. No package was installed, upgraded, removed, or reconfigured. Desktop production-server dependencies are a separate environment already recorded in the authoritative handoff; the table does not substitute the Device/test interpreter for the server interpreter.

All **10 inspected files** in the Laptop UVDoc/page-number bundle match their Desktop equivalents byte-for-byte, including model/runtime/config/manifest files:

- UVDoc runtime: `D:\ASL_OCR_E0B\models\uvdoc\runtime`; checkpoint SHA-256 `7e90861b8a516eb4bc51f84bd889cb77275743d2d1d3ca8091951ec9f2b7da23`.
- Page-number model: `D:\ASL_OCR_E0B\models\paddle\page-number`; `inference.pdiparams` SHA-256 `3ec8a97ed6cefe8568d3e2ee90bb193299b566a7661aa4fd52d224b96b59f66b`.
- Page-number manifest SHA-256 `994a5ceaa26fe35aa0e36b0c113be1a0eb05e342ef14fa38c12ccbf072bb21d0`.

### Saved profiles

| Config under `D:\ASL_OCR_E0B` | Observed configuration |
|---|---|
| `device-app.e0b.toml` | **pc_camera**, viewport 10, console, camera index 0, sample interval 500 ms, identity collection 8,000 ms |
| `device-app.e0b.webcam.toml` | pc_camera, viewport 10, same configured camera/sample/collection values |
| `device-app.android-ip-camera.toml` | android_ip_camera, **viewport 40**, sample interval 750 ms, identity collection 30,000 ms |
| `device-connectivity.e0b.remote.toml` | stable device ID and remote origin above |

The current `e0b-replay-run.bat` calls `e0b-laptop-run.bat`, whose default config is `device-app.e0b.toml`. That file currently selects **pc_camera**, not this MP4. No valid demo replay profile was established by the inspection. The Android profile's viewport 40 is outside this session's 10-cell contract; it was not selected or modified. Config hashes and whitelisted settings are preserved in baseline JSON; secret values were not collected.

## Phase 2 — fixed Demo Replay input identity

The requested directory exists and contains exactly **one file / one video / one MP4**. There is no input ambiguity.

| Field | Observed value |
|---|---|
| Absolute path | `C:\Users\user\Desktop\OCR_TEST\20260905_224928.mp4` |
| Filename | `20260905_224928.mp4` |
| Extension | `.mp4` |
| File size | **216,858,835 bytes** |
| SHA-256, calculated on Laptop | `dc16c5659ccf307f5829a5019138a8332a0f4cbc16607a55224f472850f691d8` |
| Resolution | **3840×2160** |
| FPS | **29.991943209916357** |
| Frame count | **1,798** |
| Duration | **59.94943333333333 seconds** (`frame count / reported FPS`) |
| Decoder open | OpenCV `VideoCapture.isOpened() = true` |

This is G3-B input, distinct from regression SHA-256 `16c57970...4e6f8`. Metadata/open success does not establish full-frame decoding, spread count, page identity, or OCR quality. The video was not replaced, renamed, or uploaded to the server.

## Phases 3 and 4 — held at G0

No candidate/page-change, selected spread, L/R artifact, durable outbox upload, V4 receipt, S1 parse, finalize, READY revision, or reading session was generated for this input. Therefore expected spread/page counts remain **unset**, not 2/4 and not 0. No new result was adopted as golden.

G4's checked-revision count/error count/audio mappings/braille warnings/page order are **not_run** for the demo. An empty catalog was not used to claim PASS. Previous regression preflight and warning records remain separate.

**human observation required**:

1. Intended demo spreads, their chronological order, actual printed pages, and left/right correspondence.
2. Stable candidate intervals and physical page-change/occlusion intervals in the video.
3. Selected core demo pages and original textbook reference for comparison.
4. After an authorized replay: OCR completeness and obvious misreads, spoken content, essential formulas/tables/braille, and whether the selected content can support the actual demonstration.

No human observations have been supplied or invented. All content acceptance remains pending.

## Findings and classification before any modification

| ID / classification | Boundary and reproduction/evidence | G3-A relationship and proposed minimal scope |
|---|---|---|
| V-01 / **P1 readiness blocker**, baseline/deployment mismatch, not a newly reproduced software defect | B00 and S-01/S-02 boundaries: read `git HEAD/status` in `C:\ASL_OCR`; compare the three normalized file hashes with the authoritative Desktop manifest. Different HEAD, dirty tree, three differing source files. No data corruption observed. | G3-A PASS applies to Desktop's stabilized source, not this Laptop tree. Proposed action only after explicit alignment authorization: preserve the Laptop's 24 modifications and 3 untracked entries, establish an isolated Desktop-equivalent source snapshot, then verify full source identity. Do not reset/pull over the existing tree or assume three-file copying is sufficient. No new product fix proposed. |
| V-02 / **P1 replay setup blocker**, profile mismatch | B03 input selection: replay launcher resolves to a saved `pc_camera` config without the fixed demo MP4 path. This was diagnosed statically; the camera was not opened. | G3-A used a pinned replay profile. After G0 alignment, prepare a separate demo replay TOML with the fixed MP4, viewport 10, unchanged Scanner contracts, stable device ID, and isolated state. Do not overwrite the current camera profile or tune thresholds. No product code change proposed. |
| V-03 / **Deferred**, alternate Android profile | B00/B10: unselected Android config uses viewport 40. | Keep it outside this replay. If selected for the demo, its configuration must meet the existing 10-cell contract before entry. No automatic change. |
| V-04 / **Deferred environment/access issue**, auxiliary checkout | `D:\ASL_OCR_STM_TEST` Git ownership refusal; raw source hashes are still different. | Primary `C:\ASL_OCR` was inspectable. Do not treat failed status inspection as clean. If this checkout is later selected, resolve its ownership/trust explicitly first. No global Git configuration change. |

No new product assertion failure was reproduced. A new software stabilization pass and code modification are neither requested nor started. Existing G3-A and full-regression evidence remain valid for the unchanged Desktop source.

## Modification record and restart condition

- **Product code modification: none.** Desktop production/test/contract file hashes still match the authoritative session manifest.
- **Laptop repository/environment/config/state modification: none requested or performed.** No pull/reset/checkout, dependency change, credential change, camera run, upload, or finalize.
- Only Desktop evidence files and this documentation were written. A local audit-command quoting failure was corrected; it did not run a remote replay or modify remote state.
- Next decision is source alignment while preserving Laptop changes. Until that is explicitly authorized and G0 reverified, G3-B/G4 remain BLOCKED. After alignment, use the fixed demo hash above and obtain human observation before any content PASS.
