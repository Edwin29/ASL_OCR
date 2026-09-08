# ASL_OCR H3 STM Button + Speaker + Actuator Status — 2026-09-08

## Verdict

**H3: FAIL (all independently reachable checks executed)**

H3 cannot pass because required physical controls are unavailable or miswired, the production FRAME transport is unreliable, and rapid audio supersession caused a native process crash. Independently testable button, ACK, repeat, reconnect, speaker, parser/PCA and actuator boundaries were exercised.

- Product source modification: **0**
- Existing `C:\ASL_OCR` modification: **0**
- Laptop `D:` access during H3: **0**

## Runtime

- root: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h3-20260908-001800`
- config: `config\device-app.stm-reading.toml`
- production entrypoint: `python -m asl_device --config <config>`
- controls/presenter: `stm_serial` / `stm_serial`
- device ID: `laptop-device-001`
- COM5 debug: 115200; COM9/HC-05: 9600; protocol V3
- D: runtime dependency: 0

The first runtime TOML had a PowerShell UTF-8 BOM and failed `tomllib` parsing. It was rewritten without a BOM; production `DeviceAppConfig.from_toml` then passed and imports resolved to `C:\ASL_OCR_INTEGRATION`. This was an environment preparation failure.

An H2 diagnostic process initially competed for COM9. It was terminated and the H2 scheduled task was removed before clean H3 evidence was collected. This was an environment isolation failure.

## Physical input matrix

| Control | Result | Evidence |
|---|---|---|
| UP / PA0 | PASS | One `NAV,U,S` and ACK per short press; one catalog move and matching completed title audio |
| DOWN / PA1 short | PASS | Press/release ACKed; catalog index and TTS changed once |
| DOWN / PA1 reading-to-braille | PASS within negotiated V2 async path | One physical short press emitted `NAV,D,S,2`, received `ACK,2`, advanced page 1/node 8 -> node 9/generation 129, delivered an exact ten-cell FRAME, and visibly moved the cells once. This is not V3 edge/hold acceptance. |
| DOWN hold | PASS for edge/cadence; FAIL for audio stability | One press/release. In a measured 1.234 s hold, host actions occurred immediately, then at +672 ms, +188 ms and +187 ms; release stopped movement |
| LEFT / PA4 | PASS at input/ACK | `NAV,L,S` and ACK; catalog has no LEFT action |
| RIGHT / PB0 | PASS at input/ACK | `NAV,R,S` and ACK; catalog has no RIGHT action |
| PAGE NEXT / PB1 | FAIL | Grouped/isolated operator-linked trials produced no GPIO/debug/NAV. A separate raw trace later in the same preserved run contains one `PAGE NEXT STEP` and `NAV,N,S,19`, followed by repeated retry and `NO ACK`; its physical-label timing is not preserved, so it neither proves intended NEXT wiring nor supports a blanket never-reached-GPIO claim. |
| PAGE PREVIOUS / PC0 | PASS at input/ACK/repeat | Short and long trials emitted `PAGE PREVIOUS STEP`; hold repeated and stopped on release |
| CONFIRM / PC1 short | FAIL | Intended confirm trials produced PAGE PREVIOUS; no CONFIRM event |
| CONFIRM / PC1 long | FAIL | Long trials again produced PAGE PREVIOUS repeats; no confirm edge/long classification |
| MODE / PC2 | BLOCKED | Broken lever solder leaves a fixed signal; physical mode switching is unavailable |

The current installed control wiring/labeling does not match the required PC0/PC1/PB1 contract. PAGE PREVIOUS is present, but CONFIRM is not reachable through the control identified as confirm.

## DOWN hold evidence

The instrumented hold occurred at monotonic 103796.531–103797.765:

- `NAV,D,A,44` at press and immediate ACK;
- catalog index 0 -> 1 immediately;
- further host repeats at approximately 672 ms, 188 ms and 187 ms;
- `NAV,D,R,45` at release and ACK;
- no catalog movement after release;
- no STM-generated local SHORT repeats.

This passes edge protocol and host cadence. It establishes cadence rather than an exact two-second count.

## Reconnect and restart

After the audio crash the application was restarted without changing source or state. The STM initially retained its prior connected state:

1. `NAV,U,S,46` was ACKed but its returned FRAME was malformed.
2. `NAV,D,A,47` received `NACK,47,UNSUPPORTED` and retries.
3. STM declared `NO ACK -> BLUETOOTH DISCONNECTED` and initiated `HELLO V3`.
4. `BT: HOST CONNECTED (V3 EDGES)` was established.
5. Fixed PC2 sent `NAV,V,R,1`; retry received ACK and the app entered reading catalog mode.
6. DOWN sequences 2/3 moved index 0 -> 1; UP sequence 4 returned it to 0. Both audios completed and no stale movement followed.

**Reconnect protocol and post-reconnect short input: PASS.** Reading-document cursor and boot/process namespace could not be verified because physical CONFIRM cannot enter a document. The catalog index restarted at 0 and is not reading-cursor evidence.

## P1 — `STM-FRAME-TRANSPORT-INTEGRITY-P1`

- first failing boundary: host COM9/HC-05 bytes -> STM polling USART1 line assembly;
- paced transmission at 20 ms/byte parsed and drove the actuator;
- production-speed FRAME/ACK traffic is intermittently truncated or concatenated, including `FRAME` -> `FAME`/`F...` and `ACK` -> `AK`;
- impact: blocks reliable speaker/FRAME/actuator generation lineage and H2/H3/H4 PASS.

## P1 — `RAPID-AUDIO-SUPERSESSION-NATIVE-CRASH-P1`

Rapid catalog title replacement caused audible torn/noisy output and terminated Python.

- last event: final replacement playback started at monotonic 103797.765;
- Windows Application Error: 2026-09-08 01:28:38;
- Python: 3.11.9;
- exception: access violation `0xc0000005`;
- fault module: `ucrtbase.dll`;
- loaded playback stack: sounddevice 0.5.6, PortAudio V19.7.0, `AUDIOSES.DLL`;
- dump: `C:\Users\user\AppData\Local\CrashDumps\python.exe.27012.dmp` (43,851,515 bytes);
- WER report ID: `015e9e01-0d78-4714-ad4e-029754334dab`.

The player can call `stream.abort()` from the input thread while the audio worker writes and later stops/closes the same native stream. Timing and loaded modules support a native stream lifecycle race as the leading diagnosis. This remains an inference until a native dump stack or targeted reproducer identifies the exact call.

- reproduction: one instrumented hardware run; earlier rapid navigation cancelled audio without crashing;
- impact: corrupted audio and total device application termination, blocking H3/H4;
- proposed minimal scope: serialize native stream write/abort/stop/close, add a rapid-supersession regression, then rerun speaker/reconnect checks;
- fix during this run: none.

## P1 — `STM-REQUIRED-CONTROL-INPUT-P1`

- first failing boundary: required physical buttons -> configured STM GPIO detection/mapping;
- operator-linked PAGE NEXT trials produced no GPIO/NAV; a separate unlabelled trace interval reached `PAGE NEXT STEP`/`NAV,N,S,19` but failed at ACK, so trial identity must be preserved before assigning one universal boundary;
- the control used as CONFIRM produces PAGE PREVIOUS; no PC1 confirm evidence exists;
- fixed PC2 prevents physical mode switching;
- impact: prevents document entry, page commands, CONFIRM replay/exit/finalize, and H4.

The likely correction belongs to wiring/button continuity and installed GPIO mapping. Firmware pin semantics must not change until actual wiring is traced.

## Human observations and remaining inaccessible checks

- Catalog title audio normally completed for isolated short UP/DOWN before and after reconnect.
- The operator heard torn/noisy audio immediately before the native crash.
- A controlled nonzero paced FRAME produced a visible actuator pattern; paced zero cleared it.
- No uncontrolled motion, jam, overheating or power anomaly was reported.
- Normal-math audio/braille, LEFT/RIGHT math windows, choice clear, and document commands remain unreachable because CONFIRM cannot select a document and production FRAME integrity is failed.

## Stage decision

The follow-up H3-R output test added `ACTUATOR-CLEAR-RESIDUAL-P1`: an exact all-zero FRAME was parsed twice and moved the motors, but the same substantial residual raised pattern remained. The deterministic result localizes the failure after STM/PCA command acceptance, with servo neutral angle, horn/cam indexing or channel calibration as the leading hardware/firmware cause.

H3 remains **FAIL**. All independently reachable H3 controls and output boundaries were tested. H4 is **BLOCKED** because it requires physical mode switching, CONFIRM LONG, PAGE NEXT, reliable FRAME delivery, complete physical clear and a stable runtime process. No known content waiver applies to these four H3 P1 failures.

The later physical DOWN follow-up closes the previously untested button-to-reading-to-actuator lineage. It does not change the H3 verdict: transport reliability, complete clear, required controls and runtime stability remain failed.
