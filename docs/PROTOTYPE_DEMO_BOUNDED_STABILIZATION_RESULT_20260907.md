# Prototype Demo Bounded Stabilization Result — 2026-09-07

## Scope and authority

This report records the user-approved bounded stabilization pass performed after the 2026-09-06 G0/G3-B handoff. The pass was limited to three demonstrated invariants: horizontal answer-choice classification, problem-stem math reading order, and the explicit policy that answer choices retain TTS but do not expose braille targets. No scanner threshold, protocol semantic, datapack identity rule, state transition, or test acceptance condition was relaxed.

The Laptop integration checkout is `C:\ASL_OCR_INTEGRATION`. The preserved repository `C:\ASL_OCR` was not modified. The authoritative runtime root is `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905`; its final environment manifest SHA-256 is `30a41312c5218e357ae4bb351dbce33e15f69e6cbe2749f26f11266391590aa7` on both Desktop and Laptop.

## Approved fixes

| ID | Priority | Failure/invariant before fix | Root cause | Minimal change | Verification |
|---|---|---|---|---|---|
| BS-01 | P0 | Page 29 answer row `①62 ②66 ③70 ④74 ⑤78` became a 1×5 TABLE. Finalize attempted braille per cell and failed with five `BRAILLE_RENDER_FAILED` errors, so no READY revision was published. | PaddleOCR-VL represented a visual choice row as HTML table and the serializer treated every table-shaped block as a data table. | Reclassify only an exact one-row/five-column TEXT-cell shape with ordered `①`–`⑤` markers as one TEXT answer-choice item. Ordinary and partial tables remain TABLE. | Red test reproduced TABLE output. Final demo finalize/READY succeeds; preflight error 0. Page 29 row is one TTS focus item with no braille target. |
| BS-02 | P1 | Standalone MATH nodes inside page 27 problems 5/7 and page 28 problem 1 were outside their problem units and were read after the choices. | Problem-unit scopes were built from TEXT nodes only. | Include MATH in the existing ordered problem scope and mark it as a stem member without changing start/choice thresholds. | Red test reproduced `TEXT → continuation → choices → MATH`. Final evidence has 3/3 standalone MATH nodes grouped as stem, before choices, with TTS/audio present. |
| BS-03 | P1 | Two grouped choice rows still exposed 9 math braille targets although the demo contract requires TTS and no braille for choices. | Flattening retained choice-row inline math as standalone braille spans. | Preserve the inline math and focus-item TTS, but mark math spans from an already-classified choice member as non-standalone for braille. | Red test reproduced the target. Final 13 complete-marker choice rows have TTS/audio 13/13 and braille-target rows 0/13. |

Changed product files:

- `document-parser/src/document_parser/serialization/vl_page_ir.py`
- `document-parser/src/document_parser/structure/problem_units.py`
- `document-parser/src/document_parser/accessibility/flattening/structure_nodes.py`

Changed targeted-test files:

- `document-parser/tests/unit/test_vl_page_ir.py`
- `document-parser/tests/unit/test_problem_units.py`

## Source and environment identity

| Check | Result |
|---|---|
| Base commit | `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e` |
| Expected tracked diff set | 11/11 exact, unexpected tracked diff 0 |
| Stabilization transplant hashes | all exact |
| Package imports | device runtime, book scanner, document parser all under `C:\ASL_OCR_INTEGRATION` |
| Dependency alignment | Desktop difference 0; `pip check` PASS |
| Python | integration venv `C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe`, 3.11.9 |
| Model identity | preserved and hash-matched |
| Stable device ID | `laptop-device-001` |
| Demo input | `20260905_224928.mp4`, SHA-256 `dc16c5659ccf307f5829a5019138a8332a0f4cbc16607a55224f472850f691d8` |
| Runtime/config/env D: references | 0 |
| Desktop health | HTTP 200, database ok, schema 4, writable true |
| Laptop remote health/auth | HTTPS health PASS; authenticated S0 catalog PASS |

The integration-only pytest `py.py` compatibility shim was restored from the exact Desktop environment (`b71675b5d9845ba0814e9e88767f88dac3b3cc0d3128da028bd45edbb523e871`). This was an environment repair, not a product change.

## Regression evidence

### Targeted and subsystem regression

| Run | Result |
|---|---|
| Final targeted parser/accessibility/preflight/finalize | 182 passed, 3 subtests passed |
| Laptop final targeted sync check | 47 passed |
| Parser full regression | 624 passed, 4 skipped, 6 subtests passed |
| `git diff --check` | PASS; only line-ending conversion notices |

The four skips are the pre-existing optional real-model environment skips. Assertions and acceptance conditions were not changed.

### G3-A Regression Replay

**PASS.** Final post-change run used the fixed regression SHA-256 `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`.

- scan: `scan-cc40cb53a67847a9aa77dd800ca44b3c`
- datapack: `datapack-b9264bc5fbd049ffa9cbbb99f3472326`, revision 1
- spread receipts 2 / fragments 4 / duplicates 0
- page count 4; accessible and non-empty braille present on all pages
- audio resources verified 136; transport failures 0
- serving preflight: catalog 1 / checked revision 1 / error 0 / warning 21
- manual listening was not run and is not claimed

## G3-B final replay evidence

The final replay used isolated state `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\state\g3b-final`.

| Boundary | Evidence/result |
|---|---|
| video | fixed demo SHA-256 matched |
| candidate/page-change | transmitted candidates were frame 243 and frame 359; occluded candidates were rejected |
| spread | `spread_sent=[1,2]`; no repeated sequence |
| L/R artifact | sequence 1 L/R and sequence 2 L/R, same spread lineage per pair |
| durable outbox | 2 rows; both `acked`; attempt count 1; HTTP 201 |
| V4 receipt | 2 accepted receipts |
| S1 fragment | 4 ready fragments; duplicates 0 |
| finalize | completed |
| READY | datapack `datapack-63c0ac30cc8a482f8fa9d0795e044a03`, revision 1 |
| reading | first page `pg-c4b5938b7318-00000001-L`; all 87 items reachable |
| serving preflight | page 4 / focus 87 / expected utterance 176 / audio files 133 / error 0 / warning 9 |

The user confirmed the physical mapping: sequence 1 is pages 26/27 and sequence 2 is pages 28/29.

## Item classification

| Physical page | Visible problems | Detected problem units | Classification status |
|---|---:|---:|---|
| 26 | 1–4 | 3 | Problems 1–3 grouped. Problem 4 remains separate because its printed item code `[26009-0036]` was not recovered. |
| 27 | 5–8 | 4 | All four grouped. Standalone formulas in problems 5 and 7 are stem members in source order. |
| 28 | 1–4 | 2 | Problems 1–2 grouped. Problem 3 is a complete short-answer block but not grouped because its trailing `(단, …)` text follows `구하시오`. Problem 4 is not grouped and its choices are incomplete in OCR. |
| 29 | 5–7 | 1 | Problem 5 grouped. Problems 6–7 remain separate because printed item codes `[26009-0046]`, `[26009-0047]` were not recovered. Their content remains in page reading order. |

Choice representation:

- A recovered physical `①`–`⑤` row is one focus item, not five focus items.
- Within a detected problem unit, five logical options remain available in `layout.choice_options`; those option records do not become separate navigation items.
- 13 complete-marker choice rows were recovered: 10 grouped with a problem and 3 ungrouped. All 13 have TTS/audio and zero braille targets.
- The user-confirmed page 29 problem 7 row `①62 ②66 ③70 ④74 ⑤78` is one ungrouped TEXT focus item, has TTS/audio, and has no braille target.
- Page 28 problem 4 is the exception: the captured page image appears to show `① 1/2, ② 1, ③ 3/2, ④ 2, ⑤ 5/2`, while OCR retained only `1/2`, `③ 3/2`, and `⑤ 5/2`. It therefore cannot be treated as a complete choice row by the verified rule. A person must confirm the printed content before acceptance.

Passage/math separation:

- Three standalone formula nodes are now grouped as problem stem and occur before their corresponding choices: page 27 problem 5, page 27 problem 7, and page 28 problem 1.
- Other inline formulas remain inside their surrounding TEXT focus items and are spoken with the text.
- Nine non-empty-target failures remain as `BRAILLE_TARGET_EMPTY` warnings: page 26 (2), page 27 (1), page 28 (4), page 29 (2). Two page-28 warnings are the ungrouped `③ 3/2` and `⑤ 5/2` choice fragments; the other seven are non-choice limit/piecewise-function formulas. Preflight remains error 0, but content acceptance needs a human decision about required math braille coverage.

## G4 final serving verification

Automated serving path: **PASS**.

- exact page order: 26 → 27 → 28 → 29
- 87/87 focus items reached
- 87/87 items have spoken text
- 87/87 items have audio references
- 87 authenticated WAV fetches validated; fetch failures 0
- 81 unique audio hashes; 27,078,388 bytes fetched
- serving preflight checked revision count 1; error count 0

The WAV files were fetched and structurally validated. A person has not yet confirmed the heard Korean content against the printed pages, so human content acceptance is not promoted to PASS.

## Newly found issues and classification

| ID | Classification | Evidence | Disposition |
|---|---|---|---|
| DEMO-P1-01 | P1 — demo content quality, human confirmation pending | Page 28 problem 4 OCR contains only three apparent option values/markers; the captured image appears to contain five. All pages 26–29 were declared core. | Not fixed. A robust recovery would require OCR/crop/choice-fragment work beyond the exact table and existing problem-role invariants; no threshold was loosened for one video. |
| DEMO-P1-02 | P1 pending human requirement | Seven non-choice core math expressions yield empty braille warnings. | Not fixed. Existing INVALID/PARTIAL/unsupported-math withholding contract was preserved. Human must state whether these formulas require braille in the demo. |
| DEMO-P1-03 | P1 pending human comparison | Captured images appear to contain `[26009-0033]` and `[26009-0041]`, while OCR emits `[28009-0033]` and `[28009-0041]`; apparent printed codes for page 26 problem 4 and page 29 problems 6–7 are absent from OCR. | Not fixed. Dataset-specific numeric correction and weaker problem-start heuristics were rejected without broader evidence. |
| ITEM-D01 | Deferred | 10/15 visible problems are grouped; five remain as sequential accessible items. The grouping gap alone did not prevent page order, TTS, READY, or reading. | Preserve evidence. Reclassify if prototype interaction requires problem-level navigation rather than sequential item reading. |
| ENV-D01 | Deferred environment incident | One earlier Laptop replay process exited with Windows native code `0xC0000005` during rapid catalog/audio navigation. Paced reruns completed repeatedly. | No product change. Evidence preserved; reproducible product boundary was not established. |

## Gate result

| Gate | Result | Reason |
|---|---|---|
| G0 | **PASS** | Final source hashes/diff set, imports, dependencies, C: runtime, model/video identity, health and auth all pass; D: dependency 0. |
| G3-A Regression Replay | **PASS** | Fixed hash, 2/4/0, READY revision, four-page reading and preflight error 0. |
| G3-B Demo Replay | **BLOCKED** | Automated pipeline is PASS, but page 28 problem 4 has demonstrated OCR content loss and human OCR/TTS/math-content acceptance is pending. |
| G4 Demo Serving | **BLOCKED** | Automated serving and remote audio fetch are PASS; human listening/content comparison and required non-choice math braille scope are pending. |

Because G3-B and G4 still contain human/content blockers, this revision is **not** declared Prototype Integration Baseline. General bug hunting and refactoring remain stopped.

## Post-report hardware integration decision — 2026-09-07

The user approved a **conditional hardware-integration entry waiver** for the known `\\lim_` lower-condition parser failure, aligned/array leading-unary-minus parser failure, and answer-choice TTS announcement/pause deficiency. Their P1 severity is unchanged. They do not reject the isolated camera, speaker transport, STM input, FRAME, or actuator bench stages when the exact affected item IDs are contained and known-valid non-empty braille items are used for physical acceptance. They still prevent final demo content acceptance until a later bounded fix pass and fresh G3-B/G4 human verification.

The duplicate item/`#0` WAV pairs and multi-focus-item problem granularity remain Deferred and do not reject hardware integration. Detailed scope, test order, evidence, waiver boundaries, and stop conditions are recorded in [Hardware Integration Execution Plan](HARDWARE_INTEGRATION_EXECUTION_PLAN_20260907.md).

## Evidence index

- `device-runtime/tmp/source-alignment-20260906/integration-environment-manifest.json`
- `device-runtime/tmp/source-alignment-20260906/g0-verification-final.json`
- `device-runtime/tmp/g3a-choicebraille-e01/e0b-production-full-model-report.json`
- `device-runtime/tmp/g3a-choicebraille-e01/serving-preflight.json`
- `device-runtime/tmp/source-alignment-20260906/g3b-final-runner-report.json`
- `device-runtime/tmp/source-alignment-20260906/g3b-final-evidence.json`
- `device-runtime/tmp/source-alignment-20260906/g3b-item-classification-final.json`
- `device-runtime/tmp/source-alignment-20260906/g3b-math-order-final-summary.json`
- `device-runtime/tmp/source-alignment-20260906/g3b-choice-policy-final-summary.json`
- `device-runtime/tmp/source-alignment-20260906/g3b-braille-warning-review-final.json`
- `device-runtime/tmp/source-alignment-20260906/g4-remote-reading-final.json`
- `device-runtime/tmp/source-alignment-20260906/g3b-human-review/sequence-1-left.jpg`
- `device-runtime/tmp/source-alignment-20260906/g3b-human-review/sequence-1-right.jpg`
- `device-runtime/tmp/source-alignment-20260906/g3b-human-review/sequence-2-left.jpg`
- `device-runtime/tmp/source-alignment-20260906/g3b-human-review/sequence-2-right.jpg`
