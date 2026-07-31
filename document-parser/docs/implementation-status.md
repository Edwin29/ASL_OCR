# Implementation Status

## Current Goal

The current milestone hardened the layout foundation and TEXT-only Page IR validation.

This does not include a real Korean OCR engine yet. Instead, it reduces two early integration risks:

- Same-baseline tokens from separate columns are no longer merged into a single line by default.
- Same-column block grouping can survive interleaved left/right column lines.
- `validation_summary` is now based on a real basic invariant pass.
- Render filename page IDs are extracted only from explicit `_pNNN` or `-pNNN` markers.

## Implemented

### P0-0 Project Foundation

- Python package structure under `document-parser/`
- Source asset audit
- Canonical 160-page manifest
- ZIP duplicate/copy exclusion
- PDF 300dpi rendering tool
- Initial Page IR, Math AST, Table IR, and Parse Issue schemas
- Unit tests for asset and schema contracts

### Stage 2 Image Input And Quality Gate

- Image metadata ingestion
- SHA-256, dimensions, format, mode, aspect ratio, and long-edge extraction
- Rule-based image quality gate
- Blur candidate score using Laplacian variance
- Quality report CLI
- Verified comparison:
  - ZIP samples: `LOW_QUALITY`
  - PDF 300dpi samples: `PASS`

### Stage 3 General OCR Entry Contract

- `GeneralOcrAdapter` protocol
- `OcrToken`, `OcrPageResult`, and bbox models
- `NoopGeneralOcrAdapter` for explicit unconfigured state
- `FixtureGeneralOcrAdapter` for deterministic tests
- Raw OCR result cache
- TEXT-only Page IR builder
- TEXT node conversion from OCR tokens
- Normalized bbox conversion
- OCR cache issue propagation
- CLI to generate a TEXT-only Page IR skeleton

### Stage 4 Layout Foundation

- `LayoutBuilder`
- OCR token to line grouping
- line to block grouping
- conservative top-to-bottom reading order
- TEXT-only Page IR now emits line-level TEXT nodes
- layout provenance on TEXT nodes
- horizontal gap guard against same-baseline column merging
- same-column block candidate matching
- regression coverage for two-column same-baseline fixture

### Stage 4.5 TEXT IR Validation Hardening

- basic Page IR invariant validation
- validation summary generated from actual payload state
- invalid reading-order reference count
- duplicate node ID count
- missing coordinate count
- manifest page-count mismatch flag
- stricter render filename page ID extraction

## Generated Artifacts

- `data/manifests/asset_audit.json`
- `data/manifests/ebs_2027_math1_pages.json`
- `data/manifests/render_report.json`
- `data/pages_pdf300/*.png` for selected initial pages
- `data/debug/image_quality_report.json`
- `data/debug/text_only_page_ir.json`
- `data/debug/ocr_cache/`

## Partially Implemented

### Page IR

The schema and TEXT-only skeleton exist, but the full Page IR merger is not implemented.

Available:

- document manifest
- page geometry
- quality report
- parse issues
- TEXT nodes from OCR tokens
- reading order as line order
- basic invariant validation summary

Not available yet:

- layout-derived block hierarchy in the final schema
- math nodes
- table nodes
- unsupported visual nodes
- cross-engine reconciliation
- duplicate suppression based on spatial overlap

### OCR

Available:

- adapter contract
- fixture adapter
- no-op adapter
- raw cache
- explicit OCR-missing issue

Not available yet:

- real Korean OCR engine adapter
- OCR engine comparison report
- OCR confidence calibration
- token-to-line grouping from real OCR results

## Not Implemented Yet

### Stage 4 Layout And Reading Order

- container detection
- robust one-column/two-column page ordering for real OCR outputs
- box-shaped problem ordering
- full JSON Schema validation and graph validation beyond the current flat invariant checks
- debug overlay for OCR/layout boxes

### Stage 5 Math Detection And AST

- math candidate detection
- inline math span split
- formula OCR adapter
- LaTeX parser
- Presentation AST builder
- AST validator
- math crop provenance

### Stage 6 Table Structure

- table candidate detection
- ruled-grid detection
- row/column/cell reconstruction
- merged cell detection
- table-contained OCR assignment
- table-contained math linkage

### Stage 7 Unsupported Visuals

- graph/diagram candidate detection
- embedded OCR text linking
- unsupported visual region preservation

### Stage 8 Reconciliation

- general OCR, math OCR, table parsing result merge
- duplicate content suppression
- orphan token detection
- final Page IR validation summary beyond skeleton-level invariants

### Stage 9 Evaluation

- hand-authored golden annotations
- OCR CER/WER metrics
- reading-order pair accuracy
- math AST comparison
- table structure comparison
- transformed image tests
- full-book batch regression

## Verification

Current test command:

```powershell
$env:PYTHONPATH='D:\Projects\OCR\document-parser\src'
& "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s D:\Projects\OCR\document-parser\tests -p 'test_*.py'
```

Current result:

```text
Ran 21 tests
OK
```
