# ASL_OCR Hardware Integration H1 Status — 2026-09-07

적용 계획: `HARDWARE_INTEGRATION_EXECUTION_PLAN_20260907.md`의 조건부 H1.

현재 판정은 **H1 FAIL (two attempts preserved)**이다. H0의 `MODE-LEVER-SOLDER-P1`을 명시적으로 BLOCKED로 유지한 채, 승인된 console-control containment로 H1을 실행했다.

## Run identity

- run root: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-20260907-223731`
- source: `C:\ASL_OCR_INTEGRATION`
- Python: integration `.venv-e0b`
- controls: production `console`
- initial mode: `capture`
- stable device ID: `laptop-device-001`
- camera: `android_ip_camera:snapshot`, `HttpSnapshotCameraSource`, no fallback
- isolated state: `<run-root>\state\camera-console`
- product source modification: 0

## Confirmed boundaries

- Synthetic catalog item `새 데이터팩 추가` was selected. Its cue digest `c6d5b528eab8` matches `s0-system-cue:catalog.new_datapack`.
- New datapack: `datapack-3f0d8ec7d8c44dc7a22ea2005ab03748`, title `새 데이터팩 2026-09-07 22:52 #25`.
- Scan session: `scan-2b05e8b5cb234da48c265b07d94b84a7`.
- Camera open feedback identifies `android_ip_camera:snapshot` and `HttpSnapshotCameraSource`.
- Initial page 26/27 candidate required physical camera elevation. Several candidate identity attempts were correctly rejected as `content_occluded`, `seam_failed`, or `footer_identity_unavailable` before acceptance.
- Accepted spread outbox sequence 1:
  - source frame `phone-snapshot-00000191`
  - spread ID `scan-2b05e8b5cb234da48c265b07d94b84a7-spread-000015`
  - artifact `spread-47577804af842a4b8490f3aea35262f5`
  - outbox status `acked`, attempt 1, HTTP 201
  - receipt `spread-receipt-e1bf0646b544e633f7670772ac105d1e`
  - upload digest `13509f057ade65633475e6beef902127654a9379c3ec6b374b1fbf9759f10121`
- Raw Server scan status after failure: `open`, spread counts `ready=1`, other counts 0, `through_sequence=null`, no published revision.
- Page 28/29 was physically presented only after the sequence-1 transmission announcement. No sequence-2 artifact was queued.

## Failure

- first failing boundary: Laptop TCP connection to Android IP Camera `192.168.1.78:4444`.
- direct strict snapshot: `ConnectTimeout` after 12 seconds.
- `Test-NetConnection`: ping failed and TCP 4444 failed while Laptop remained `192.168.1.53/24` on the intended Wi-Fi.
- runtime terminal event: `fatal_error`, reason `frame_decode_failed`.
- last scanner evidence before fatal: page-change identity attempts were incomplete/unknown; there is no second spread or upload.
- the expected `InsecureRequestWarning` is caused by the explicitly configured self-signed TLS mode and is not the failure.

Classification: **demo input / capture condition**. The endpoint became unavailable after the first spread. This is not evidence of Scanner threshold, OCR/parser, upload, or Server regression.

This attempt is not resumed across a process restart because the in-memory coordinator/scan session is gone. The draft, open Server session, ACKed receipt, SQLite and all evidence are preserved. After the Android endpoint is restored and re-probed, a new isolated H1 run/new datapack should be used so both spreads share one fresh lineage.

## Additional issues

### `ANDROID-PREFLIGHT-SOURCE-P1`

The legacy Laptop preflight rejects the `android_ip_camera` profile while its camera sub-check opens the Laptop camera at `640×480`. That result is excluded from Android-camera evidence. The exact production factory strict probe remains the source readiness evidence.

### `FATAL-EXIT-STATUS-D01`

Classification: **Deferred diagnostic/operational issue**. The runtime emitted `fatal_error: frame_decode_failed` but the CLI wrapper later printed `Device runtime exited with code 0`. The visible fatal event prevented a false H1 PASS in this run, but supervisors relying only on process exit status could misclassify it. Reclassify to P1 if the prototype launcher or service uses exit status as its health/restart contract.

## Human observation

- Initial page 26/27 required camera elevation before one spread was recognized.
- The corresponding send announcement played successfully.
- The operator turned to page 28/29 after that announcement.
- No subsequent guidance audio played because the camera transport later became unavailable and the runtime terminated.

## Recovery and second attempt

- The operator confirmed that the phone battery had discharged, then charged and reconnected it.
- A strict production-source probe after recovery succeeded at `4000x3000` through `HttpSnapshotCameraSource` with no fallback.
- Recovered-frame pixel SHA-256: `3fbcb9942c2af7024d0e075c1727958a00c4fa1fe7250114958372eedfe66e46`.
- Recovered JPEG SHA-256: `6bc4a009540cbca3ea51c69fab70da7e892dcc4eddf64902aa6b1d824ec06799`.
- The failed run, its open scan, ACKed receipt, and isolated state remain preserved.
- Fresh run root: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-20260907-231944`.
- Fresh state is isolated, config parses through the production client, and the server catalog contained 25 existing entries before the run. The synthetic new-datapack entry is index 25.
- The fresh runtime is running from `C:\ASL_OCR_INTEGRATION\.venv-e0b`; product source modification remains 0.

### `POST-FIRST-SPREAD-AUDIO-SILENCE-P1-CANDIDATE`

The operator reports that guidance audio disappearing after the first transmitted page has been observed at least three times historically. The first H1 attempt cannot isolate this symptom because the phone endpoint failed after sequence 1 and the runtime terminated with `frame_decode_failed`. The second attempt therefore monitors camera transport, scanner feedback emission, audio fetch/playback events, and durable ACK independently across the page change. Classification remains **P1 candidate / reproduction pending** until the symptom occurs while the camera source remains healthy, or the second attempt demonstrates normal post-first-spread guidance.

## Second attempt result

- The operator heard the synthetic new-datapack cue at catalog index 25 and confirmed a new scan.
- New datapack: `datapack-b2deeaeb6434464189ee1c5539bf58fe`.
- Scan session: `scan-9725fbc4b3d04095a1810a3d16ef6b35`.
- Page 26/27 produced sequence 1, artifact `spread-cd479bf7b7c9a62b8e2c967750e052d2`, HTTP 201, receipt `spread-receipt-678834b6e1bd5b4a69f548ab666b37cb`, and local durable status `acked`.
- The operator heard the first spread-sent cue and then presented page 28/29.
- A strict source probe captured the presented 28/29 spread at `4000x3000`; visual inspection shows both pages, seam, corners, and footer areas in frame.
- While the source was reachable, page-change identity repeatedly timed out as `unknown`. Observed valid counts per bounded collection included `3`, `1`, `1`, then `0`, with `query_sample_count=5`. Effective observation intervals included about `1.922 s`, `2.5 s`, and `5.094 s`; recognition processing included about `0.56-0.96 s` in the captured tail.
- No sequence 2 artifact was created. Server status remained `open`, `ready=1`, all other spread counts 0, and no revision.
- The terminal event was `fatal_error: frame_decode_failed`; the wrapper again reported process exit code 0.
- Immediately after termination, a strict source read succeeded. A following ten-read burst passed 10/10 at `4000x3000`, with individual reads about `1.187-1.438 s`. This proves that the terminal acquisition failure was transient rather than a continuing phone outage.

### `LIVE-PAGE-CHANGE-LIVENESS-P1`

Classification: **P1, confirmed, integration blocking**. The live snapshot/OCR cadence did not collect the required five valid page-change observations inside the configured 8,000 ms collection window. The invariant requiring five observations remains unchanged; no threshold or acceptance condition was lowered. The first failing boundary in the second attempt is `page_change identity -> different`, before candidate selection for sequence 2.

Minimal proposed scope: make the live-camera collection time budget compatible with measured blocking acquisition/recognition latency while retaining N=5 and all K/identity gates, or change timeout accounting so the configured budget is not consumed by synchronous acquisition/recognition work. This requires a bounded stabilization decision because hardware integration currently forbids product source changes and threshold relaxation.

### `POST-FIRST-SPREAD-GUIDANCE-SILENCE-P1`

Classification: **P1, confirmed symptom; conditionally excludable from the integration rejection condition only as an audio-guidance item**. The audio transport did not fail. The runtime produced repeated `identity_collection_decided(role=page_change, decision=unknown, timed_out=true)` diagnostics, but the page-change timeout path emits no `scanner_guidance` event. The audio controller only maps `scanner_guidance` and defined process events to system cues, so there was no audio request to fetch or play. This item does not explain the missing second artifact; it makes the liveness failure silent to the operator.

Minimal proposed scope: emit a bounded, rate-limited page-change timeout guidance event through the existing guidance/audio path. It must not synthesize acceptance or treat unknown identity as a page change.

### `HTTP-SNAPSHOT-TRANSIENT-FATAL-P1`

Classification: **P1, confirmed, integration blocking**. A transient HTTP snapshot/decode exception terminates the scanner as `frame_decode_failed`. The source was healthy immediately afterwards and passed 10/10 reads, so restarting the phone is not a durable correction. The source remains strict; no webcam fallback occurred.

Minimal proposed scope: preserve strict source identity but apply a bounded retry/recoverable-acquisition policy to transient `SnapshotTransportError`/decode failures, with explicit loss/recovery feedback and a finite fatal ceiling. It must not hide sustained camera loss or substitute another source.

## Current H1 disposition

H1 remains **FAIL**. Repeating the identical run is not justified: the first-spread path is proven twice, while the second attempt isolated two product/runtime liveness blockers before sequence 2. H2/H3/H4 must not treat this partial live-camera run as a two-spread H1 PASS. Product source modification remains 0.
