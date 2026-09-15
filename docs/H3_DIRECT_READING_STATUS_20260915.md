# H3 production physical reading continuation

> 후속 갱신: 연결 timeout 재시도, 초기 FRAME1회 재전송, 셀 역순 mapping 보정 적용 및 양끝 물리 검증을 마쳤다. 아래 기존 실패 증거를 삭제하지 않으며 최신 상태는 [최소 수정 결과](MINIMAL_CORRECTIONS_RESULT_20260915.md)를 따른다. 전원/접촉 추가 조사는 재발 시까지 보류.

## User observations

The user reports that moving MODE to the opposite position and back restored operation. Physical CONFIRM, UP/DOWN/LEFT/RIGHT, audio and braille output were observed working. The same reversed cell order remains. These are human observations from the direct production run using h3-direct-20260914/config/device-app.stm-reading.toml; a correlated NAV/ACK/FRAME trace was not captured in this turn. Do not declare V3 acceptance or a root cause for the initial lack of mode transition from this observation alone.

## Environment recovery

On 2026-09-15 Desktop port8421 had no listener. Started the existing production server launcher with isolated logs under docs/evidence/h3-direct-20260915/server-logs. Existing database, credentials and product source were not changed. Laptop process query returned no Python processes, so direct application restart is needed.

## Remaining bounded user procedure

Restart the same production entrypoint, switch MODE to reading, select the same READY and confirm. Check page next/previous, DOWN hold approximately2seconds then release (navigation must stop), CONFIRM short replay, CONFIRM long catalog return with CLEAR, and same-READY re-entry with cursor restoration. Wait for audio between independent checks. Capture console transcript for this run; transcript alone does not prove wire ACK/FRAME application. No camera acquisition/upload should be requested during this reading exercise.

Keep reversed cells, initial FRAME prefix loss, and unresolved reconnect/serial evidence gaps separate from normal physical-button observations. No product patch, firmware flash, threshold change or automatic motor diagnostic is performed in this turn.

## Flash identity check after absent braille output

User reports braille display not operating. Read-only HOTPLUG SWD readback on ST-LINK 066EFF505071655067246025 succeeded without reset/halt/write commands. The verified candidate ELF SHA256 remains 4e415e19ffcdbcc845d2b8f27d6e719812dcbc4ed6e26082c2478e4334d4220e. Both loadable flash segments (0x08000000/26520 bytes and 0x08006798/256 bytes) matched the board byte-for-byte. Readback SHA256: 71b7bde1bee964fa82d0d6055556c75354111c5705b507bba7ad167b8ae00201.

Evidence: docs/evidence/h3-direct-20260915/flash-check/result.json and programmer-stdout.log; raw readback remains in Laptop C runtime h3-flash-check-20260915. This excludes a different/stale flashed image within the compared firmware load segments, not an execution, transport, PCA power, or physical application fault. No reflash is warranted from this observation alone. Runtime Python processes existed during the check; COM9 was not opened by the diagnostic.

Next distinction: a text-only focus can legitimately yield empty braille; a previously verified formula focus should yield nonzero cells. Compare that snapshot with actual STM FRAME/parser output before diagnosing actuator failure. Existing first-FRAME/reconnect issues remain candidates, not established causes of this incident.

## Direct display-only probe

After the user exited the reading app, process check returned no Python processes. Sent exactly three direct frames: node/generation501 all0,502 all63,503 all0, separated by at least5seconds. COM11 debug confirmed receipt of all three complete FRAME payloads. No reset/flash, no tool error, both ports closed. User physical movement observation is pending. Raw result/events are in docs/evidence/h3-direct-20260915/display-probe-{result.json,events.jsonl}.

This test uses direct pyserial plus ACK handling and a readiness gate. It bypasses DeviceApplication/S0/production STM presenter and therefore cannot clear the production output/reconnect failure even if physical output succeeds. Existing-session duplicate ACK and received NAV may establish the probe gate; this is not fresh V3 startup acceptance.

User observed no physical movement at all in the first direct probe. Thus complete FRAME receipt did not establish physical application. User then checked some contacts and restarted the hardware, suspecting power; the power/contact cause is not yet confirmed by measurement.

At the user's request, repeated the same three-frame 5-second sequence in a new isolated runtime `display-probe-20260915-retry1`, preserving the first evidence. No Python process was present before the probe. All three complete FRAMEs were again observed at STM RX, tool error=null, ports closed. No agent reset/flash or product modification. Retry physical observation remains pending. Evidence: `display-probe-retry1-result.json` and `display-probe-retry1-events.jsonl`.

User confirmed the retry operated normally. Direct display actuation is therefore observed working after contact inspection/restart. This supports a recoverable hardware/power/runtime condition but does not isolate which changed condition caused recovery; no voltage or contact measurement was supplied.

Before H3 resumption, a second HOTPLUG read-only flash comparison at 2026-09-15T08:03:36 UTC again matched both firmware segments (26776 bytes total) against the same verified ELF. Readback hash is unchanged. Evidence: flash-check/resume-result.json and resume-programmer-stdout.log. No reset/halt/flash write, no calibration or cell mapping change. Desktop health returned200. H3 can resume its remaining physical reading checks; known cell reversal/startup/reconnect issues remain open.

## H3 remaining steps: user observation complete

The user confirmed all six instructed steps normal: physical MODE/READY entry, next/previous page, DOWN approximately2second hold/release with no further movement, short CONFIRM replay, long CONFIRM catalog/CLEAR, and same-datapack re-entry with position/audio/braille recovery. This completes the requested normal physical-reading observation sequence. Cell reversal remains known, not waived by this report.

Follow-up SSH process inspection returned no Python processes. Application termination is observed, but this direct run did not capture a fresh CLI exit code, worker-close record, or correlated NAV/ACK/snapshot/FRAME trace. Do not transfer H2's instrumented close result to H3. No additional button exercise is requested merely to repeat these normal observations.

Disposition: H3 normal workflow user-observed success; full instrumented acceptance remains incomplete. Required follow-up and bounded correction packets are in H3_FOLLOWUP_CORRECTION_PRIORITIES_20260915.md. Product source modifications in this closeout:0; existing adaptation changes in the working tree preserved.
