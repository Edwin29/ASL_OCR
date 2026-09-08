# ASL_OCR H3-R Reading Output Verification Plan — 2026-09-08

## Status and purpose

**Status: required before H4; not_run**

H3-R is a required output subtest of H3. It does not replace the failed physical-button checks and cannot promote H3 to PASS by itself. Its purpose is to isolate the READY reading output path before live camera, physical capture controls and append/restart behavior are combined in H4.

The required lineage is:

```text
READY revision
  -> S0 reading command
  -> operation/cursor/generation
  -> reading snapshot
  -> audio_ref -> Laptop speaker
  -> 10-cell FRAME -> HC-05 -> STM -> PCA9685 -> actuator
```

## Why H2 evidence is insufficient

H2 proved that a deliberately paced diagnostic FRAME can cross the STM parser, PCA mapping and actuator boundary. It did not prove that a real READY item produces matching TTS and braille from the same reading generation over the production FRAME transport. H3-R therefore verifies the real content output while keeping the camera variable out.

## Constraints

- source: `C:\ASL_OCR_INTEGRATION`
- runtime root: `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905`
- device ID: `laptop-device-001`
- use an isolated H3-R state/log/evidence directory on C:
- product source modification: prohibited
- existing `C:\ASL_OCR`, production state and evidence: preserve
- Laptop D: access: prohibited
- acceptance thresholds and protocol semantics: unchanged
- audio navigation: one item at a time; wait for playback completion before the next command

The last constraint avoids deliberately reproducing `RAPID-AUDIO-SUPERSESSION-NATIVE-CRASH-P1` during this output test.

## Fixed content policy

Primary positive braille sample:

- page 26: `pg-c4b5938b7318-00000001-L-vl012-L01`
- reason: previously selected normal non-empty long-math sample outside the known waiver list

Policy samples:

- ordinary TEXT: expected audio; braille behavior must match the current reading contract
- answer choice: expected audio; braille must be clear/no-display
- non-choice normal MATH: expected audio and non-empty braille

Known P1 samples may be observed but cannot be used as positive actuator acceptance:

- `MATH-LIMIT-SUBSCRIPT-P1`
- `MATH-ALIGNED-UNARY-MINUS-P1`

## Execution steps

1. Record source/config/state/server/COM identity and confirm D: dependency 0.
2. Start the existing runtime-only console-input plus STM-presenter composition if it preserves production S0 commands, snapshots, audio resources and FRAME serialization.
3. Select the preflighted READY demo revision.
4. Move one item at a time and wait for audio completion.
5. At a normal text item, correlate operation, cursor, generation, audio reference and FRAME.
6. At the fixed normal-math sample, confirm:
   - correct item identity;
   - audible TTS corresponding to the displayed source;
   - exactly 10 cell values, each 0..63;
   - non-empty physical braille pattern;
   - physical pattern corresponds to the logged cells.
7. Use LEFT/RIGHT on the long formula and confirm window/offset and physical pattern change without stale overwrite.
8. Move to a choice item and confirm the actuator clears and stays clear while choice audio plays.
9. Move back to normal math and confirm a fresh non-empty generation replaces the clear frame.
10. Stop the runtime, preserve logs and hashes, and record human observations.

## PASS criteria

- real READY item identity is known;
- command -> snapshot -> audio_ref/FRAME lineage uses the same current generation;
- TTS fetch/playback completes without wrong-item or stale playback;
- FRAME has exactly 10 values in 0..63;
- fixed normal-math sample produces non-empty physical braille matching the logged cells;
- LEFT/RIGHT changes the intended window and final physical state matches the latest generation;
- answer choice produces the required no-braille clear with no residual raised dots;
- no malformed production FRAME, uncontrolled actuator movement, audio corruption or process crash occurs.

## Failure and classification

H3-R remains FAIL if any required output is absent, stale, malformed or inconsistent. Existing issues retain their current classifications:

- `STM-FRAME-TRANSPORT-INTEGRITY-P1`
- `RAPID-AUDIO-SUPERSESSION-NATIVE-CRASH-P1`
- `STM-REQUIRED-CONTROL-INPUT-P1`

A new symptom must first be localized to S0 selection/snapshot, audio fetch/playback, FRAME serialization/transport, STM parser/PCA, physical actuator, or content quality. No product fix is made during this run.

## Human observation required

- spoken content corresponds to the selected item;
- normal-math braille pattern is physically non-empty;
- logged cell/dot mapping matches the physical top/bottom actuator state;
- choice item is physically clear;
- LEFT/RIGHT final pattern corresponds to the intended formula window;
- no audible corruption and no uncontrolled mechanical behavior.

## Gate relationship

- H3-R PASS supplies the missing real-content output evidence.
- H3 remains FAIL until physical CONFIRM/PAGE/MODE, production FRAME integrity and audio crash are resolved and rerun.
- H4 remains BLOCKED until the required H3 input and output contracts are both satisfied.
