# Current Milestone

## Goal

Implement the first project foundation milestone:

- Audit the source PDF and ZIP assets.
- Generate a canonical 160-page manifest.
- Exclude ZIP copy files from canonical processing.
- Provide PDF-to-PNG rendering tooling for 300dpi OCR baseline images.
- Add initial Page IR, Math AST, Table IR, and Parse Issue schema drafts.
- Verify the implementation without installing additional dependencies.

## Done Criteria

- `data/manifests/asset_audit.json` exists.
- `data/manifests/ebs_2027_math1_pages.json` contains 160 canonical pages.
- ZIP copy files are reported but excluded.
- Selected PDF pages can be rendered to `data/pages_pdf300/`.
- Unit tests pass with bundled Python and `unittest`.

## Completed Follow-up

The next milestone added image ingestion and a rule-based quality gate.

- ZIP samples are reported as `LOW_QUALITY`.
- PDF 300dpi rendered samples are reported as `PASS`.
- Quality reports are written to `data/debug/image_quality_report.json`.

## Completed OCR Contract Follow-up

The next milestone added the General OCR adapter contract and a TEXT-only Page IR skeleton.

- `GeneralOcrAdapter` is defined.
- Raw OCR cache writing is implemented.
- `NoopGeneralOcrAdapter` emits `OCR_ENGINE_NOT_CONFIGURED`.
- `data/debug/text_only_page_ir.json` can be generated from rendered page images.

## Completed Layout Foundation Follow-up

The next milestone added token-to-line and line-to-block grouping.

- OCR tokens on the same baseline become one `LayoutLine`.
- TEXT-only Page IR emits line-level TEXT nodes.
- Reading order is currently conservative top-to-bottom order.

## Completed Layout And Validation Hardening Follow-up

The next milestone hardened the largest risks found in the self-review.

- Same-baseline tokens separated by a large horizontal gap are kept as separate lines.
- Line-to-block grouping can attach later lines to an existing same-column block instead of only comparing with the immediately previous line.
- TEXT-only Page IR now runs a basic invariant validation pass before writing `validation_summary`.
- Page ID extraction now requires an explicit `_pNNN` or `-pNNN` marker and otherwise falls back to the input sequence index.
