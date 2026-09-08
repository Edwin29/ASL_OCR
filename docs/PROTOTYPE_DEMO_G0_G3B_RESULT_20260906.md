# Laptop C: runtime G0 / G3-B result — 2026-09-06

This report supersedes the pre-alignment gate status in
`PROTOTYPE_DEMO_VERIFICATION_20260906.md` for the C: integration checkout and the
2026-09-05 demo replay. The governing contracts remain
`PROTOTYPE_STABILIZATION_GATE.md`, `HW_SW_INTEGRATION_PLAN.md`, and
`PROTOTYPE_STABILIZATION_REPORT_20260906.md`. G3-A remains PASS and was not rerun.
This was an environment/runtime recovery and verification pass. No product source
code was changed.

## Gate result

| Item | Result | Evidence / reason |
|---|---|---|
| Laptop D: runtime dependency | **0** | C: app/connectivity configs, launcher, resolved runtime paths, and relevant environment variables contain no D: reference. Laptop D: was not accessed in this phase. |
| C: runtime reconstruction | **PASS** | `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905`; full config parse, model/input identity, writable isolated state, imports, dependencies, and network checks passed. |
| Connectivity config | **PASS** | Production parser accepted the C: config; stable device ID and existing production HTTPS origin match the contract. |
| Secret availability | **PASS** | The existing authorized Desktop production-server credential was copied to the C: runtime secret reference. Content/hash was not logged. Authenticated read-only S0 catalog succeeded. |
| Desktop server health | **PASS** | Initial first boundary was no listener on 127.0.0.1:8421. The unchanged production launcher was restarted non-destructively; loopback health returned HTTP 200, DB `ok`, schema 4, writable true. |
| Laptop remote health/auth | **PASS** | Tailscale HTTPS health returned HTTP 200. Authenticated S0 catalog returned successfully. |
| **G0** | **PASS** | Every recorded G0 pass condition is true before and after G3-B. |
| **G3-B Demo Replay** | **FAIL** | Scanner/upload/parser fragments passed, but finalize preflight rejected the staging revision with `BRAILLE_RENDER_FAILED`; no READY revision or reading snapshot exists. |
| **G4 Demo Serving** | **BLOCKED / not_run** | G3-B produced no READY revision. The failed staging root was diagnosed separately and had error 5, warning 9; it is not a publishable G4 target. |

Prototype Integration Baseline is not declared because G3-B and G4 are not PASS.

## G0 evidence

The final C: verification report is
`device-runtime/tmp/source-alignment-20260906/g3b-laptop-evidence/g0-verification.json`.
The same report is retained on Laptop at
`C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\reports\g0-verification.json`.

- Git HEAD remains `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e`.
- All nine authoritative stabilization transplant hashes still match.
- `asl_device`, `book_scanner`, and `document_parser` resolve under
  `C:\ASL_OCR_INTEGRATION`.
- Integration Python remains 3.11.9; `pip check` passes; the aligned dependency
  inventory was not upgraded.
- Production `DeviceAppConfig.from_toml` parsing succeeds.
- Stable identity remains `laptop-device-001`.
- Server origin remains `https://desktop-ekp6an5.taild2128f.ts.net`.
- All verified model hashes match the Desktop bundle.
- Demo SHA-256 remains
  `dc16c5659ccf307f5829a5019138a8332a0f4cbc16607a55224f472850f691d8`;
  OpenCV opens 3840×2160, 29.991943 FPS, 1,798 frames, 59.949433 seconds.
- The C: isolated state write/read/delete probe passes.
- Resolved path, config/launcher text, and relevant environment D: reference
  counts are all zero.
- Remote HTTPS health and an authenticated read-only S0 catalog both pass.

The Desktop 502 was an operational server-down condition, not a D: loss or a
newly demonstrated product defect. The unchanged production server was started
with its existing launcher/config/state. No DB reset, state deletion, protocol
change, authentication change, or dependency change was performed.

## G3-B input and execution

The fixed input was
`C:\Users\user\Desktop\OCR_TEST\20260905_224928.mp4`, with the identity above.
The replay used the C: profile with viewport 10, sample interval 100 ms, identity
collection budget 30,000 ms, the verified UVDoc/page-number models, isolated C:
outbox/artifacts, production HTTPS origin, and stable device ID.

An initial harness attempt stopped before scan creation because the production
catalog already contained entries and index 0 was not the synthetic New Datapack
item. It did not open a scan or process the video. The harness was corrected to
move downward through the bounded catalog and confirm only when
`kind=new_datapack`. This was a verification-harness correction, not a product
change.

The actual run created:

- datapack `datapack-d7d6bbaeac7247e2ba0afe4b86d9321e`
- scan `scan-0ee0904af20c4726bd39b7d70010c532`
- sequence 1 from accepted spread
  `scan-0ee0904af20c4726bd39b7d70010c532-spread-000004`, frame 243
- sequence 2 from accepted spread
  `scan-0ee0904af20c4726bd39b7d70010c532-spread-000005`, frame 359

Scanner evidence:

- Several early candidates did not complete acceptance and produced no upload.
- Spread 000004 reached candidate verification N=5 / `different`, then
  `spread_sent sequence=1`, followed by page-change monitoring for the same
  accepted spread lineage.
- Page change was observed at frame 358. Spread 000005 then reached candidate
  verification / `different` and `spread_sent sequence=2`.
- EOF was `queued_count=2`, `acked_count=2`.
- `CONFIRM LONG` was issued once after nonzero EOF.

Durable outbox evidence is in
`device-runtime/tmp/source-alignment-20260906/g3b-outbox-evidence.json`:

- exactly two rows, sequences 1 and 2
- both `acked`, one attempt each, HTTP 201
- receipt IDs match the server S1 receipts
- no local error or cleanup error
- stable device ID on both rows

Server evidence is in
`device-runtime/tmp/source-alignment-20260906/g3b-server-evidence.json`:

- V4/S1 spread receipts: 2
- left/right fragments: 4
- duplicate receipts: 0
- upload attempts: 2, both accepted once
- fragment order/side identity:
  `00000001-L`, `00000001-R`, `00000002-L`, `00000002-R`
- all four fragments were parsed by PaddleOCR-VL 3.7.0 and reached `ready`

These observed counts are execution evidence, not a G3-A expectation imposed on
the demo input. Human observation is still required to establish that two spreads
were intended and that their physical pages and sides are correct.

## First failing boundary

The first product failure is B07, finalize assembly preflight:

- scan status: `error`
- through sequence: 2
- fragment counts: ready 2 spreads / 4 pages, no parser-error fragment
- finalize run:
  `finalize-ec1af97e5355d1c92e3c74317cdf137a`
- error: `REVISION_PREFLIGHT_FAILED`
- detail: `serving preflight failed: BRAILLE_RENDER_FAILED`
- published revision: none

The staging preflight report is
`device-runtime/tmp/source-alignment-20260906/g3b-staging-preflight.json`:

- page count 4
- focus items 87
- braille targets 89
- nonempty braille targets 75
- expected utterances 190
- checked audio files 145
- errors 5 (`BRAILLE_RENDER_FAILED`)
- warnings 9 (`BRAILLE_TARGET_EMPTY`)

All five errors are cells in one five-column table on the fourth generated page,
`pg-ec1af97e5355-00000002-R-vl010`. PaddleOCR-VL Page IR contains:

```text
��62  ��66  ��70  ��74  ��78
```

The raw Page IR table evidence is
`device-runtime/tmp/source-alignment-20260906/g3b-raw-table.json`; it contains the
same replacement characters in `raw_html`, `raw_text`, and `normalized_text`.
`table_cell_braille` treats non-digit TEXT as Hangul text. Each cell therefore
raises `ValueError: Not a digit string`, recorded in
`device-runtime/tmp/source-alignment-20260906/g3b-braille-failure.json`.

The human-review dewarped pages are:

- `device-runtime/tmp/source-alignment-20260906/g3b-human-review/sequence-1-left.jpg`
- `device-runtime/tmp/source-alignment-20260906/g3b-human-review/sequence-1-right.jpg`
- `device-runtime/tmp/source-alignment-20260906/g3b-human-review/sequence-2-left.jpg`
- `device-runtime/tmp/source-alignment-20260906/g3b-human-review/sequence-2-right.jpg`

The images appear to show consecutive printed pages 26, 27, 28, and 29, and the
problematic visual row appears to be circled answer choices 1–5 with values 62,
66, 70, 74, and 78. These observations are not promoted to content acceptance
without user confirmation.

## Classification and proposed scope

### G3B-01 — P0

Trigger: the fixed demo's fourth page includes the answer-choice row above.

Boundary: PaddleOCR-VL table output contains replacement characters; table cell
braille rendering raises ValueError; strict serving preflight rejects the entire
fresh revision. No READY revision or reading path is available.

Impact: current selected demo cannot complete Scanner → publish → reading. This is
a current critical-journey stop with preserved error state and no data corruption.
It meets the gate's P0 rule. G3-A remains PASS, so this is a demo-content-triggered
OCR/parser/braille compatibility failure rather than evidence of a general
Scanner/upload regression.

Proposed bounded work, requiring a new explicit stabilization approval:

1. Reproduce from the immutable fourth-page image/Page IR with a targeted test.
2. Determine whether U+FFFD originates in PaddleOCR-VL output or repository table
   serialization before changing behavior.
3. If repository serialization corrupts a preserved circled digit, fix only that
   encoding/normalization boundary and retain the exact semantic label.
4. If the model itself returns U+FFFD, do not infer or silently discard the symbol.
   Define and test a narrow, evidence-backed answer-choice representation before
   extending table braille translation for mixed choice-label/numeric cells.
5. Keep unsupported table content strict; do not demote `BRAILLE_RENDER_FAILED`,
   lower preflight acceptance, remove the table, edit the generated document, or
   reuse another WAV/braille target.
6. Rerun the exact cell test, staging preflight, the fixed demo replay, fresh READY
   serving preflight, and selected-page human comparison. Reconfirm G3-A if the
   change touches shared parser/braille behavior.

The exact implementation path is intentionally not selected until the origin of
U+FFFD and the visual answer-choice semantics are confirmed. If the repair needs a
new parser layer or broad OCR cleanup, it exceeds the current bounded change budget
and must be re-scoped.

No additional Deferred issue was created. The nine `BRAILLE_TARGET_EMPTY` warnings
belong to the failed, unpublished staging revision and require human content review
after the P0 is resolved; they do not independently change the current gate result.

## Human pending

1. Confirm whether the video intentionally contains exactly two spreads, ordered
   as printed pages 26/27 and then 28/29, with those left/right sides.
2. Confirm whether the page 29 answer row is exactly
   `① 62, ② 66, ③ 70, ④ 74, ⑤ 78`.
3. Identify which of pages 26–29 are the core demonstration pages and whether the
   page 29 answer row must be spoken and rendered in braille.
4. OCR meaning, formulas/tables, generated speech, and physical braille remain
   `human_pending`; audio playback and braille actuation were not reached.

## Modification record

- Product source code modification: **0**.
- Existing `C:\ASL_OCR` modification: **0**.
- Laptop D: access/repair/recovery operation in this phase: **0**.
- Production DB/artifact deletion or reset: **0**.
- Secret/device ID/auth/threshold/assertion change: **0**.
- Runtime-only C: config, credential reference, evidence scripts, logs, isolated
  state, and the operational server restart are recorded in the evidence above.
