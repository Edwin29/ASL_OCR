# Fresh H1 after source alignment

Run: `h1-fresh-aligned-20260908-2350`. Current status: two durable receipts and fresh READY revision VERIFIED; application remains at capture catalog. Scene orientation and prolonged second-page admission issues remain recorded below. Full H4/content/physical acceptance is not claimed.

User approved proceeding from continuous Scanner diagnosis to aligned fresh H1. Compared237 tracked Python source files across the three Desktop/Laptop packages after CRLF normalization: only engine.py differed. No Python process was running before deployment. Preserved original Laptop engine at diagnostics/h1-investigation-20260908/engine-before-alignment-20260908.py, then copied the already approved Desktop engine. Old hash f223f744fe2fd6a6818ea7bed4ed4f522e27f90590fc2c477fcb40fdbe8e427f; new hash6ee44d42cae3456544e58c183c193f970b1467ef26a616feeb9ad6e563dfc380. No new product correction, threshold/config policy change or firmware flash.

Laptop targeted engine tests26 passed. First isolated test copy failed collection because relative imports lost their package context; preserved that output and repeated with original video test package structure plus the two current tests. This was a test harness artifact.

Created new isolated config/state/log/evidence root under C:/ASL_OCR_INTEGRATION_RUNTIME/demo-20260905/hardware-integration. Copied existing authorized configuration/credentials locally, replacing only old run-root references; no credential values exported. Stable device identity and production state are retained. Full source index and run manifest are under docs/evidence/h1-fresh-aligned-20260908.

Preflight report passed all five checks: profile, scanner models, server health200, Android4000x3000 snapshot, authenticated Piper WAV transport. No audio playback requested for preflight. SSH/PowerShell exit1 did not match passed report; wrapper/native-stderr exit behavior remains an observation, not confirmed product failure.

Interactive manual scheduled task ASL_H1_Aligned_20260908_2350 has no time/recurring trigger. Runs production `python -u -m asl_device --config ... --initial-mode capture` in Windows session3. `-u` and stdout Tee-Object improve console evidence; stderr goes to native-stderr.txt. PowerShell ErrorActionPreference=Continue around native invocation avoids launcher termination merely from native stderr. GUI preview and native audio retain interactive context. This differs from previous H1 transcript-only logging, so console stdin behavior must be observed on first command.

UTC14:44:05 launcher start, Python PIDs18672/23916 in session3. Logs show capture catalog opened at index0 on an EXISTING datapack, with system playback completions. Human hearing not yet confirmed. User must select the synthetic `새 데이터팩 추가` / kind=new_datapack before confirm; existing draft must not be used for fresh H1.

Expected sequence:26/27 fresh capture → durable receipt1 and human spread-sent cue → user turns28/29 → receipt2 → console confirm long → fresh READY revision. No STM/servo packets. Finalize is gated on two actual durable receipts. Independent failures remain recorded; dependent steps are skipped only with reasons. H4 remains BLOCKED.

User reported 준비완료. Read-back still shows only initial index0/kind=existing and initial audio events, with no catalog movement event. New-datapack selection is not yet verified; do not issue confirm. Next bounded check is one console down+Enter and observation of both visible selection/voice and logged event, to distinguish user readiness from input or logging harness failure.

## Portrait source during capture

User subsequently entered capture and reported portrait preview plus repeated position guidance despite unchanged angle. Runtime remains active; recent candidate selections enter identity verification but repeatedly time out with valid_observations=0. This is not evidence of a stopped app.

Read-only single snapshot probe UTC14:51:34.730~14:51:36.407 returned shape[4000,3000,3], i.e. width3000/height4000, versus earlier width4000/height3000. Viewed preview confirms sideways text and vertically stacked spread halves. Thus this is actual input orientation change, not merely window stretching. All configured generic/landscape/portrait rotations remain0. Cause of endpoint orientation change (phone/app orientation state or otherwise) is unconfirmed. Do not attribute to engine update without evidence.

Probe ran concurrently with production acquisition; exclude its time window from cadence assessment. No credentials/policies changed, no upload from probe. Full diagnostic snapshot remains Laptop evidence/orientation-probe-01; Desktop orientation-preview.jpg preserves a proportional thumbnail. Restore the previous source orientation before judging framing/identity. Do not rotate only the preview or alter thresholds to hide the issue. Existing run/state retained, no automatic restart or finalize.

## First durable receipt, second page-change held

User restored direction and heard first transmission success, then reported second held. Read-only SQLite observation UTC14:56:26 confirms exactly one row: sequence1, device laptop-device-001, artifact spread-bab169a3d77c491a19e7c4fcfc727fb5, source frame00000264, status acked, attempt1, HTTP201, receipt spread-receipt-a07e94c3d8f11e68490ee540a05d79c8. Sequence2 is absent, so do not classify as second upload/network failure or finalize.

Recent production feedback repeatedly completes page_change N5 DIFFERENT/timed_out=false at ~1.2–1.4sec observation intervals but stays in page_change. This differs from original N4/8sec timeout. Actual engine's DIFFERENT path also requires latched visual change OR coherent_numeric_difference. Neither flag is exposed in these Device feedback rows, so failure of that combined gate is a source-supported hypothesis, not independently observed root cause. Existing slow-cadence risk is not the first failing boundary in this excerpt.

Preserved device-stdout-second-held.jsonl; inspect_delivery.py is new read-only tooling. Next bounded operator step is one baseline26/27 re-presentation followed by visible turn to28/29 with support/camera unchanged. Stop this added retry after30sec of stable query if no receipt; retain run and classify pending failure rather than repeat indefinitely. Do not change source/threshold or submit incomplete finalize.

## Second receipt arrived without further operator action

User reported a second transmission cue before performing the proposed baseline re-presentation. Therefore that extra retry was NOT performed and must not be credited with recovery. UTC14:57:39 read-only outbox check confirms sequence2 artifact spread-322c165d099ba73ec5d46b69956cd5d4/source frame00000373, status acked, attempt1, HTTP201, receipt spread-receipt-ddc6d7f3bf68527728b5a06388c7bae4. Exactly two rows are present and both acked.

Production sequence: page-change DIFFERENT184660.500 → candidate selected184663.812 → candidate-verification N5 DIFFERENT184670.843 → spread_sent(sequence2)184676.078 → corresponding system audio started184676.078/completed184681.265. This is an actual second durable receipt and associated cue, not merely replay of the first cue. First-to-second spread_sent interval142.282sec is not page-turn latency because exact physical turn time is unknown. After second receipt the current page is repeatedly SAME.

A preceding collection at184653.687 reports unknown/timed_out=true/valid6. Thus do not generalize the earlier N5 DIFFERENT excerpt into a claim that the whole waiting period had no timeout. The specific condition that eventually opened the page-change gate remains unobserved in compact Device feedback. Preserve prolonged liveness/guidance risk despite eventual success.

Both local manifest paths referenced by acked rows were absent on attempted read-back. No cleanup was performed by this investigation. Actual uploaded page content/manifest validation must use retained server artifacts; receipt existence alone does not establish correct page content. New evidence: delivery-second-check.json and device-stdout-second-sent.jsonl.

Cancel the proposed manual baseline repeat. Two durable receipt prerequisites for normal finalize are now met; next operator instruction is a single console `confirm long`, followed by fresh READY revision verification. Until verified, datapack_saved/READY/H4 remain unaccepted.

## Finalize and fresh READY verified (KST midnight boundary)

User heard the generating-datapack cue after confirm long. Logs show scan_stopping through_sequence2 at184814.812, finalizing184814.984, generating cue completed184818.203, and datapack_saved184842.593. Datapack is datapack-b7d5a769ad5347738d491f1b39e5e909, revision1. Finalizing-to-saved interval27.609sec. Capture catalog returned with title 새 데이터팩 2026-09-08 23:47 #28. Saved-cue playback and subsequent catalog playback events were retained; human observation currently explicitly confirms the generating cue, not the saved cue.

Independent read-only Desktop production DB verification at UTC2026-09-08T15:00:04 (KST2026-09-09T00:00:04) confirms datapack.status=ready/current_revision1 and revision.status=ready/published_at2026-09-08T14:59:17.771635Z. All four S1 fragments(sequence1/2 × left/right) are ready, attempt1, error_code=null. Manifest hash eceaf5820908926393fa4cb7fed1759f6e56e8df80bc5b398b8eda68573ad5a8. Evidence server-ready-verification.json and device-stdout-finalized.jsonl; query code verify_ready.py is read-only.

Bounded result: two V4 receipts → four parser-ready fragments → explicit finalize → fresh READY publication is verified. This does not validate every recognized text/math item or actual physical controls/braille. Initial portrait input and long second-page wait prevent describing the entire run as problem-free or universally live. Next separate reading check can select this new READY and verify S0/audio/cursor; no new reading command or application shutdown was issued during this verification.

User subsequently confirmed hearing the saved-completion cue ("들렸어"). Human observation of that cue is now confirmed separately from native playback completion and server READY publication. Fresh H1's bounded two-receipt/finalize/READY/saved-cue outcome is complete with the recorded orientation and liveness issues retained. No additional control command, reading test, shutdown or hardware action was performed for this acknowledgment.

## New READY reading continuation — planned/in progress

User approved proceeding. Current app remains in capture catalog on title #28. Checked production ConsoleControlSource grammar and Coordinator: `lever released` selects reading mode; `confirm long` while reading returns to catalog. First operator bundle: select reading mode, verify target title, open, item down, page_next, page_previous, exit via confirm long, reopen same title. Wait for each audio completion; compare the last focus before exit with reopened focus. Target datapack remains datapack-b7d5a769ad5347738d491f1b39e5e909/revision1. Pending results must not be inferred from command instructions. Process restart/stable cursor recovery is a separate later bundle after saving the actual cursor. No STM/servo action or source change.

### Reading/re-entry observed

User reports all seven steps normal. Snapshot sequence confirms target datapack: generation0 page0/node0(www.ebsi.co.kr) → generation1 page0/node1(1) → generation2 page1/node0 → generation3 page0/node0. Page0/page1 both begin with the same website text, so page movement is verified by distinct page_id, not voice text alone. Catalog exit followed by reading_resumed at monotonic185162.765 restores full generation3/page0/node0/focus vl001 cursor, followed by matching audio completion185166.187. Read-only server reading_progress for laptop-device-001 agrees with revision1/generation3. Evidence device-stdout-reading-reentry.jsonl and cursor-after-reentry.json.

All snapshots in this bundle have empty braille_cells and offset0; math-window scrolling is not tested here. Next restart bundle intentionally moves to page1/node1 before normal Ctrl+C, making recovery distinguishable from resetting to the first item. Resume and clean-exit outcome remain pending.

### Restart checkpoint

User completed the move/stop bundle. Generation4 page1/node0 → generation5 page1/node1/focus pg-a11ebe27eb63-00000001-R-vl002 and generation5 playback completion185304.031 were observed. Independent server reading_progress agrees; saved cursor-before-restart.json. No Python process remained. First launcher lifecycle records exited at UTC15:07:06.938 but exit_code=null, so clean exit0 and native worker-close acceptance are not established by this run. Ctrl+C interrupted the PowerShell/native pipeline before the assignment could be observed; exact exit behavior remains a tooling investigation item.

Restart uses the same production module/config/device identity and state, with explicit --initial-mode reading. Separate restart1 stdout/stderr/transcript/lifecycle filenames preserve first-run evidence. A new manually launched interactive task ASL_H1_Aligned_Restart1_20260909 has no recurring trigger. Opening the target READY and comparing the full generation5 cursor remains pending user input. Do not count a catalog launch alone as cursor recovery.

### Restart recovery verified; console encoding issue

User confirms same audio as before shutdown, while console text is corrupted. reading_resumed185456.578 matches the complete saved generation5/page1/node1/focus vl002 cursor and audio_ref b449b693e19598dcf4cb389ed8ac3c14; matching playback completed185459.484. A subsequent generation6 snapshot stays on the same focus/audio and completes185473.828. Recovery PASS applies to generation5 restore, not an inferred command behind the later generation6 event. Evidence restart1-stdout-observed.jsonl and cursor-before-restart.json.

Read-only encoding investigation finds the server revision document's target TEXT span intact as `정답과 물이 12쪽` (OCR correctness against the printed page is not assessed here). Downloaded Tee-Object stdout is UTF-16 LE BOM, with corrupted source_text/spoken_text; two snapshot rows(lines12/16) are invalid JSON due to corrupted string boundaries. ASCII cursor fields and reading_resumed feedback remain readable; the complete resumed cursor is separately valid JSON. Thus stored console output cannot be treated as lossless content evidence.

Launcher sets PYTHONUTF8=1 but does not explicitly set native-output decoding Console.OutputEncoding. UTF-8 decoded using CP949 produces similar mojibake, but the Python decoder experiment did NOT exactly reproduce the captured bytes after replacement normalization. Classification: confirmed test_harness_artifact in console/log fidelity; precise decoder/codepage attribution remains probable, requiring a small same-PowerShell diagnostic. No evidence here of corrupted server text or audio; user hearing is normal. No production source or active process change made. New check_console_encoding.py and console-encoding-check.json preserve this distinction. A bounded launcher encoding correction plus Korean JSON round-trip check is the next tooling candidate; do not rewrite original logs.

Reading entry/navigation/re-entry and actual restart cursor/audio recovery are now verified for this READY. Clean exit code/native-close observation, math-window positive offset on this new content, and physical H4 remain unverified. Restarted app remains open.
