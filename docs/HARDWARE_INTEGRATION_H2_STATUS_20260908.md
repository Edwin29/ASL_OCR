# ASL_OCR H2 Console + STM Integration Status — 2026-09-08

## Verdict

**H2: FAIL (integration blocking)**

Console navigation and reading audio reached a READY datapack, but the production COM9/HC-05 to STM32 `FRAME` path did not preserve complete frames. The actuator-only paced diagnostic reached `ApplyBrailleFrame`, and the user observed the motors drawing the transmitted pattern.

Product source modification during H2: **0**.

## Runtime identity

- Laptop source: `C:\ASL_OCR_INTEGRATION`
- H2 runtime: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h2-20260907-234639`
- READY datapack: `datapack-63c0ac30cc8a482f8fa9d0795e044a03`, revision 1
- STM debug: COM5 at 115200 baud
- HC-05 host link: COM9 at 9600 baud
- Firmware protocol: V3 edge/control protocol

## Confirmed behavior

1. Console `confirm` entered reading and resumed the stable device cursor at page 29 footer (`generation=87`). Reading audio completed.
2. Console `prev` moved to page 28, first node `pg-c4b5938b7318-00000002-L-vl001`, source `www.ebsi.co.kr` (`generation=88`). The user heard the audio.
3. Both selected items had `braille_cells=[]`; motor movement was therefore not expected from their content alone.
4. The frames sent for both cursor states were rejected or damaged before actuator application:
   - `FAME,3,16,0,0,87,...` (`R` lost)
   - `FRAME,2,0,0,88,...` (one cursor field lost; `FRAME FORMAT ERROR`)
5. A controlled all-zero frame sent as a normal burst was received as `FRA,2,0,0,0,88,...`.
6. A 3 ms/byte controlled frame was received as `FRAME,20,,0,8,...`.
7. The same complete frame at 20 ms/byte was received and parsed exactly:
   - `PAGE=2`, `NODE=0`, `SPAN=0`, `OFFSET=0`, `GEN=88`
   - `CELLS=0,0,0,0,0,0,0,0,0,0`
8. A 20 ms/byte nonzero frame was received and parsed exactly, reaching the actuator application boundary:
   - `GEN=89`
   - `CELLS=1,2,4,8,16,32,63,21,42,0`
   - physical motor result: **PASS** — user observed the motors move in a distinct pattern
9. A second paced frame set all cells to zero (`GEN=90`) and was parsed successfully, returning the actuators to the reference state.

## First failing boundary

`host COM9 write -> HC-05 -> STM USART1 polling receive -> FRAME line assembly`

The host reading snapshot and TTS were correct before this boundary. STM rejected the damaged lines before `ParseAndApplyFrame`/`ApplyBrailleFrame`. The paced nonzero test proves the downstream parser, PCA, servo mapping, and motor actuation path works.

## Classification

### P1 — `STM-FRAME-TRANSPORT-INTEGRITY-P1`

- Reproduction: production H2 frames and controlled burst/3 ms frames repeatedly lose characters or fields.
- Difference from earlier evidence: H0 proved HELLO/ACK and PCA initialization, but did not prove a full asynchronous `FRAME`; G3-A is software replay and does not traverse HC-05/STM UART.
- Impact: blocks reliable braille presentation and therefore blocks H2/H4.
- Minimal fix scope for a future approved stabilization decision: make STM USART1 receive buffering robust for complete asynchronous frames, preferably interrupt/DMA ring buffering with existing line/parser semantics retained. A host pacing workaround may be used only as diagnostic evidence until its latency and protocol behavior are explicitly accepted.
- Existing frame grammar, navigation semantics, cell encoding, servo mapping, baud identity, and acceptance conditions must remain unchanged.

### Existing P1 — `MODE-LEVER-SOLDER-P1`

The broken PC2 lever contact emits a fixed mode edge after boot. It was ACKed during controlled trials so it did not contaminate the final 20 ms tests. H4 remains blocked pending repair or the previously approved bounded substitute-input acceptance.

## Evidence hashes

- `logs\h2-events.jsonl`: `CEE1FBFC22E3742F00F31CC2E5630AE5CA5AEDE42DCE831E1E77F4DB38D66929`
- `logs\stm-com5-trace.log`: `A7125C1C51679178FCE2916E453AA20CB6E146CD6BCF96D7101955E1FD20FC87`
- `logs\stm-frame-transport-diagnostic.json`: `E155E424E33A4F67A5967EBC92179CFAADC267537D60FD925EB3C146718AC328`
- `logs\stm-frame-transport-diagnostic-20ms.json`: `E287FFC3230ECAF55090470215BE0DD6AA842E80AC7AD56BF7EECE5FD3CD946A`
- `logs\stm-actuator-paced-diagnostic.json`: `9255E9DCFF02659E0FBE8B5C2A3464C11645350612B3FDDFBC21298DD3BA8318`
- `logs\stm-actuator-clear-paced-diagnostic.json`: `C86CD9F6EBDD060412916A9323A3492F3802BE2EFF8A0DFC27EAA9703C4DCDB3`

## Stop decision

Further console navigation with the unchanged production transport would add no new evidence and could not satisfy H2. H2 remains FAIL until transport integrity is corrected and the navigation-to-braille path is rerun. The actuator-only subtest is PASS.
