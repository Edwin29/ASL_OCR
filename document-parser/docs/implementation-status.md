# Implementation Status

## Current Goal

The current milestone incorporated overlay review feedback into region-separation diagnostics, changed the p003 introduction page policy from attempted region splitting to explicit unsupported-page exclusion, added a PaddleOCR comparison path for the 8-page sample set, and promoted PaddleOCR to the project baseline OCR engine.

The latest overlay review found that vertical text order is mostly stable, but visual/table/sidebar text can be merged with body text, p102 needs explicit left/right separation, and p003 is publisher guide content rather than supported math-learning content. The diagnostics and postprocess now handle these cases:

- mixed body/visual/table region candidates
- table-like or answer-list candidates
- two-column split candidates
- intro/guide page exclusion candidates
- p004 table/body separation candidates
- p102 two-column and answer-list separation candidates
- p003 represented by a full-page `UNSUPPORTED_VISUAL` node
- p003 OCR nodes preserved only as embedded evidence outside primary `reading_order`
- intro/guide exclusion policy shared by diagnostics and Page IR postprocess
- overfit guards verify the policy is not tied to `p003` and does not exclude ordinary sparse math pages
- unsupported-page exclusions are approval-gated: candidates can be reported before being applied
- p102-style full-page two-column layouts can be reordered left-column first, then right-column
- PaddleOCR can run through the shared OCR adapter path with Windows-safe CPU settings
- PaddleOCR has been batch-tested on the 8 rendered sample pages and compared against the EasyOCR baseline
- PaddleOCR is now exposed as the baseline OCR adapter and baseline CLI path
- PP-Structure/layout analysis remains the next structure-aware PaddleOCR integration target
- PaddleOCR layout detection can now add experimental table/image/figure/chart region candidates to Page IR
- generic PaddleOCR layout labels are now mapped into EBS math-textbook domain candidates
- structure candidates are now linked to overlapping OCR TEXT nodes without removing those TEXT nodes from primary reading order
- reviewed table/graph structure candidates can now be promoted into primary reading order while preserving contained OCR text as embedded evidence
- p102 problem-box candidates can now be promoted through an explicit preview profile without changing the safe default profile
- p102 problem-box captions are now linked to their corresponding promoted problem boxes as preview metadata
- Stage 5 has started with conservative math-candidate metadata on primary TEXT nodes
- math-candidate crops can now be exported as formula-OCR-ready work units
- structure regions can now act as layout barriers to expose cross-region OCR merge risks
- layout-barrier crossing warnings can now be exported as split/re-OCR crop work units
- split/re-OCR crop work units can now be recognized with the baseline PaddleOCR adapter into a review manifest
- split OCR results can now be linked back to original crossing TEXT nodes as reconciliation preview metadata
- approved split OCR reconciliation previews can now be converted into draft primary TEXT segment replacements
- stale layout-barrier crossing warnings are now cleaned after split OCR replacement drafts are applied
- split OCR replacement drafts now have before/after review reports and visually distinct overlay rendering
- split OCR replacement draft order is now audited after overlay review and two-column order is reapplied after segment creation

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
- `EasyOcrGeneralAdapter` for temporary development OCR
- Raw OCR result cache
- OCR cache keys include adapter configuration signatures when provided
- TEXT-only Page IR builder
- TEXT node conversion from OCR tokens
- Normalized bbox conversion
- OCR cache issue propagation
- CLI to generate a TEXT-only Page IR skeleton
- CLI to generate TEXT-only Page IR with EasyOCR

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

### Stage 4.6 Page IR Validation Gate

- reusable `document_parser.validation` package
- standalone Page IR validation CLI
- bbox and normalized bbox range checks
- confidence range checks
- reading-order coverage checks
- parse issue shape checks
- quality status checks
- validation summary artifact generation

### Stage 4.7 Debug Overlay Artifacts

- reusable `document_parser.debug` package
- Page IR node bbox overlay rendering
- content-type color coding for TEXT, MATH, TABLE, UNSUPPORTED_VISUAL, and UNKNOWN
- page header labels with node count, issue count, and quality status
- standalone overlay rendering CLI
- overlay summary artifact generation

### Stage 4.8 EasyOCR Development OCR

- EasyOCR result normalization into `OcrToken`
- EasyOCR bbox union from polygon points
- EasyOCR confidence propagation
- low-confidence page-level issue emission
- skipped-result issue emission
- EasyOCR raw result cache payloads
- EBS p008 EasyOCR Page IR generation
- EBS p008 EasyOCR validation and overlay artifacts

### Stage 4.9 OCR Quality Diagnostics

- reusable `document_parser.evaluation` package
- OCR quality report CLI
- low-confidence node summary
- suspicious line shape summary
- bbox overlap warning summary
- large reading-order gap warning summary
- EBS p008 OCR diagnostic artifact generation

### Stage 4.10 Sample OCR Review Set

- EasyOCR TEXT-only Page IR generation for the 8 rendered sample pages
- sample-set validation summary generation
- sample-set overlay generation
- sample-set OCR quality report generation
- compact sample review-priority report
- page ranking by low confidence, reading-order warnings, overlap warnings, and suspicious node shapes

### Stage 4.11 Region Separation Diagnostics

- mixed-region candidate warnings for wide noisy OCR lines
- table-like candidate warnings for numeric/list-like answer rows
- two-column split candidate warnings for midpoint-crossing OCR lines
- region-separation warning counts in OCR quality reports
- region-separation warning counts in sample review reports
- p004/p102 overlay feedback reflected in diagnostics

### Stage 4.12 Intro Guide Page Exclusion Diagnostics

- intro/structure page detection from header text
- dense guide/example-page OCR detection
- p003 flagged as an unsupported intro/guide page candidate
- sample review report includes intro-guide exclusion warnings

### Stage 4.13 Intro Guide Page Exclusion Postprocess

- reusable intro/guide page exclusion postprocess
- one full-page `UNSUPPORTED_VISUAL` node created for p003
- all p003 OCR TEXT nodes preserved with `parent_visual_node_id`
- all p003 OCR TEXT nodes excluded from primary `reading_order`
- Page IR validator allows embedded OCR nodes outside primary reading order when linked by a visual node
- standalone unsupported-page postprocess CLI

### Stage 4.14 Support Policy Overfit Guard

- shared `document_parser.page_policy` module for support/exclusion decisions
- OCR diagnostics and Page IR postprocess now use the same intro/guide exclusion decision
- exclusion decision records evidence counts for auditability
- regression coverage proves the policy is not page-ID specific
- regression coverage prevents sparse math pages with incidental `Structure` text from being excluded
- 8-page EasyOCR sample check excludes only p003 and keeps p004, p008, p012, p019, p020, p054, and p102 supported

### Stage 4.15 Support Exclusion Approval Gate

- support review report builder for unsupported-page exclusion candidates
- standalone support review report CLI
- exclusion approval config with approved exclusion types
- visual-region postprocess only applies approved exclusion types
- regression coverage for pending and approved exclusion candidate states
- current sample support review reports one approved p003 intro/guide candidate and zero pending candidates

### Stage 4.16 Two-Column Reading Order Postprocess

- shared two-column reading-order candidate policy
- full-page left/right vertical-band evidence guard
- p004 is not treated as a two-column reading-order page after the vertical-band guard
- p102 reading order is reordered by header, left column, right column, footer
- primary nodes receive `layout.reading_order_group`
- standalone reading-order postprocess CLI
- debug overlay labels now prefer `reading_order_index`

### Stage 4.17 PaddleOCR Safe Adapter Smoke

- `PaddleOcrGeneralAdapter` added behind the `GeneralOcrAdapter` contract
- PaddleOCR v3/v5 dict results normalized into `OcrToken`
- Windows-safe defaults: CPU, MKLDNN disabled, 2 CPU threads, max detector side length 1600
- project-local Paddle cache/home environment setup
- PaddleOCR TEXT-only Page IR CLI
- p008 PaddleOCR Page IR smoke generated successfully
- p008 PaddleOCR validation, overlay, and OCR quality artifacts generated

### Stage 4.18 OCR Engine Sample Comparison

- PaddleOCR TEXT-only Page IR generated for the 8 rendered sample pages
- PaddleOCR sample validation summary, overlay set, and OCR quality report generated
- reusable OCR comparison report builder added
- standalone EasyOCR/PaddleOCR comparison CLI added
- comparison report shows PaddleOCR lowering the sample diagnostic score from 169 to 53
- page verdicts: 7 `CANDIDATE_PREFERRED`, 1 `TIE_OR_REVIEW`
- p102 remains the main review page for layout/structure tuning after the OCR baseline switch

### Stage 4.19 PaddleOCR Baseline Promotion

- `create_baseline_ocr_adapter()` now returns the PaddleOCR PP-OCRv5 adapter
- baseline detection model: `PP-OCRv5_server_det`
- baseline recognition model: `korean_PP-OCRv5_mobile_rec`
- `tools/baseline_ocr_text_ir.py` provides a stable baseline OCR CLI alias
- `pyproject.toml` now treats PaddleOCR/PaddlePaddle as the primary OCR optional dependency and EasyOCR as `legacy-ocr`
- PaddleOCR support review report confirms one approved p003 intro/guide exclusion and zero pending candidates
- PaddleOCR baseline Page IR sample generated with p003 unsupported-page handling and p102 two-column reading-order handling
- two-column reading-order postprocess is now idempotent for repeated application

### Stage 4.20 PaddleOCR Layout Region Candidate Path

- PaddleOCR `LayoutDetection` / `PP-DocLayout_plus-L` was verified locally with project-local model cache
- PP-StructureV3 availability was checked; the installed environment requires additional `paddlex[ocr]` dependencies for the full pipeline
- reusable experimental structure adapter added under `document_parser.structure`
- `tools/paddleocr_structure_regions.py` adds filtered layout candidates to an existing Page IR
- default structure labels are limited to table/image/figure/chart/graph candidates to avoid text-layout clutter
- p004 structure smoke adds one `TABLE` candidate and two graph/image `UNSUPPORTED_VISUAL` candidates
- p102 structure smoke adds large box-layout candidates for the two-column problem page
- generated structure-candidate Page IR outputs remain schema-valid

### Stage 4.21 EBS Math Structure Domain Mapping

- domain mapping policy added for PaddleOCR layout labels
- compact `table` regions map to `TABLE_CANDIDATE`
- large `table`-like regions map to `PROBLEM_BOX_CANDIDATE` instead of being prematurely treated as real tables
- `image`/`figure`/`chart`/`graph` regions map to `GRAPH_OR_DIAGRAM_CANDIDATE`
- `figure_title`/`table_title` regions map to `VISUAL_OR_PROBLEM_CAPTION_CANDIDATE`
- raw structure summaries now include PaddleOCR raw labels, domain labels, target content types, and mapping reasons
- p004 now reports 1 `TABLE_CANDIDATE` and 2 `GRAPH_OR_DIAGRAM_CANDIDATE` regions
- p102 now reports 6 `PROBLEM_BOX_CANDIDATE` and 6 `VISUAL_OR_PROBLEM_CAPTION_CANDIDATE` regions

### Stage 4.22 Structure Candidate Text Linking

- spatial linking postprocess added for structure candidates and OCR TEXT nodes
- structure nodes now record `contained_text_nodes`
- structure node layout metadata records contained text counts and overlap evidence
- TEXT node layout metadata records `parent_structure_node_ids`, `primary_parent_structure_node_id`, and overlap evidence
- linking is conservative and does not remove TEXT nodes from primary `reading_order`
- p004 links 14 TEXT nodes to table/graph structure candidates
- p102 links 62 TEXT nodes to problem-box/caption structure candidates
- structure-linked Page IR outputs remain schema-valid

### Stage 4.23 Structure Candidate Promotion

- conservative structure promotion postprocess added
- default promotable labels are `TABLE_CANDIDATE` and `GRAPH_OR_DIAGRAM_CANDIDATE`
- promoted structure nodes replace their contained OCR TEXT nodes in primary `reading_order`
- contained OCR TEXT nodes are preserved through `embedded_text_nodes`
- contained TEXT nodes are marked as non-primary reading-order candidates
- validator now accepts embedded OCR text refs from TABLE, MATH, UNSUPPORTED_VISUAL, and UNKNOWN structure nodes
- p004 promotes 1 table candidate and 2 graph/diagram candidates
- p004 preserves 14 contained OCR TEXT nodes as embedded evidence
- p102 promotes 0 candidates by default; problem-box candidates remain review/layout candidates

### Stage 4.24 Problem-Box Preview Promotion

- `tools/promote_structure_candidates.py` now supports promotion profiles
- `safe` profile promotes only table/graph candidates
- `problem-box-preview` profile promotes `PROBLEM_BOX_CANDIDATE` regions explicitly
- problem-box preview uses geometry order instead of first-contained-text insertion
- p102 preview promotes 6 problem-box candidates
- p102 preview preserves 58 problem-box-contained OCR TEXT nodes as embedded evidence
- p102 preview reading order is left column top-to-bottom, then right column top-to-bottom for promoted problem boxes
- preview profile metadata is recorded in `engine_manifest.structure_promotion`

### Stage 4.25 Problem-Box Caption Linking

- promoted problem-box regions can link nearby caption/title structure candidates
- caption matching uses geometric evidence rather than page-specific IDs: vertical gap above the box, horizontal overlap, and center distance
- problem-box nodes record `layout.caption_structure_node_ids` and `layout.caption_structure_node_refs`
- caption nodes record `layout.parent_problem_box_structure_node_id`
- caption candidates remain in primary `reading_order` for now; this is a conservative preview metadata link, not final problem reconstruction
- p102 preview links 6 caption candidates to 6 promoted problem boxes
- p102 preview Page IR remains schema-valid after caption linking

### Stage 5.1 Math Candidate Detection Entry

- initial math-candidate detector added under `document_parser.math`
- `tools/detect_math_candidates.py` annotates Page IR TEXT nodes and writes a candidate summary report
- original TEXT nodes are preserved; this stage does not create committed `MATH` nodes yet
- candidate metadata is stored at `layout.math_candidate`
- scoring uses relation operators, function notation, fraction-like expressions, powers/subscripts, root/sigma symbols, and symbolic density
- simple multiple-choice answer-list rows are excluded from candidate scoring
- only primary reading-order TEXT nodes are scanned, so embedded evidence from unsupported pages or promoted structures is not reintroduced
- PaddleOCR baseline sample output reports 119 math candidates and remains schema-valid

### Stage 5.2 Math Candidate Crop Export

- `document_parser.math.crops` exports image crops for TEXT nodes marked with `layout.math_candidate`
- `tools/export_math_candidate_crops.py` writes crop PNG files and a crop manifest
- crop manifest entries preserve the source page ID, node ID, original bbox, padded crop bbox, score, reasons, text, and crop path
- crop boxes are padded and clamped to source image bounds
- crop export follows primary reading order and ignores non-primary embedded evidence
- PaddleOCR baseline sample output exports 119 math-candidate crops with zero missing crop files
- this remains formula OCR preparation only; committed `MATH` nodes and AST are still pending

### Stage 4.26 Layout Barrier Annotation

- `document_parser.structure.barriers` annotates table, graph/diagram, and problem-box structure candidates as layout barriers
- primary TEXT nodes contained by a barrier receive `layout.primary_layout_barrier_node_id`
- barrier nodes record assigned TEXT refs without changing primary reading order
- TEXT nodes overlapping multiple barriers receive `layout.layout_barrier_crossing_candidate`
- crossing candidates are reported through `LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE`
- `tools/apply_layout_barriers.py` writes barrier-annotated Page IR and a summary report
- p004 reports 3 barriers, 14 assigned TEXT nodes, and 0 crossing warnings
- p102 reports 6 problem-box barriers, 58 assigned TEXT nodes, and 16 crossing warnings, confirming that left/right split and row splitting still need later reconciliation

### Stage 4.27 Layout Barrier Split Work-Unit Export

- `document_parser.structure.barrier_splits` exports crop work units for TEXT nodes that cross multiple layout barriers
- `tools/export_layout_barrier_split_crops.py` writes split crop PNG files and a manifest
- each work unit is based on `TEXT bbox ∩ barrier bbox`, with configurable padding clamped to the source image bounds
- work-unit manifests preserve source TEXT node ID, barrier node ID, source bbox, barrier bbox, intersection bbox, crop bbox, source text, and crop path
- this stage does not split recognized strings automatically; it prepares localized re-OCR or review input
- p102 exports 32 split work-unit crops from 16 crossing TEXT nodes with zero missing files

### Stage 4.28 Layout Barrier Split Re-OCR

- `document_parser.structure.barrier_split_ocr` recognizes split crop work units through `GeneralOcrAdapter`
- `tools/ocr_layout_barrier_split_crops.py` runs the baseline PaddleOCR adapter on split crop PNG files
- split OCR manifests preserve source TEXT node ID, barrier node ID, structure label, crop path, source text, recognized text, OCR tokens, issues, and geometry provenance
- the stage intentionally does not mutate Page IR or replace crossing TEXT nodes yet
- p102 split re-OCR recognizes all 32 work units and emits 225 crop-level OCR tokens

### Stage 4.29 Split OCR Reconciliation Preview

- `document_parser.structure.barrier_reconciliation` groups split OCR work units by source TEXT node
- `tools/apply_split_ocr_reconciliation.py` attaches split OCR preview metadata to crossing TEXT nodes
- preview metadata records segment text, confidence summaries, crop provenance, barrier IDs, and review status
- the preview does not remove original TEXT nodes, change primary reading order, or commit replacement text
- p102 receives reconciliation previews for 16 crossing TEXT nodes and 32 split OCR segments
- p102 statuses are 15 `REVIEW_REPLACE_CANDIDATE` and 1 `REVIEW_REQUIRED_LOW_CONFIDENCE`
- the reconciliation-preview Page IR remains schema-valid

### Stage 4.30 Split OCR Replacement Draft

- `document_parser.structure.barrier_replacement` converts approved reconciliation previews into draft TEXT segment nodes
- `tools/apply_split_ocr_replacement_draft.py` writes a replacement-draft Page IR and summary report
- original crossing TEXT nodes are preserved as non-primary evidence through `split_ocr_replaced_by_node_ids`
- the Page IR validator accepts linked split-OCR evidence TEXT nodes outside primary reading order
- low-confidence or otherwise unaccepted reconciliation candidates remain unchanged in primary reading order
- p102 converts 15 safe crossing TEXT candidates into 30 draft TEXT segment nodes
- p102 skips 1 `REVIEW_REQUIRED_LOW_CONFIDENCE` candidate
- the replacement-draft Page IR remains schema-valid

### Stage 4.31 Split OCR Replacement Issue Cleanup

- replacement draft application removes stale `LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE` warnings for source TEXT nodes that were replaced by split OCR draft segments
- unresolved or unaccepted candidates keep their crossing warnings
- replacement draft summaries record resolved and unresolved crossing issue counts
- p102 resolves 15 stale crossing warnings and leaves 1 unresolved warning for `p102-n031`
- the cleaned replacement-draft Page IR remains schema-valid

### Stage 4.32 Split OCR Replacement Review Artifacts

- `document_parser.structure.replacement_review` builds before/after review reports from replacement-draft Page IR
- `tools/split_ocr_replacement_review.py` writes structured review JSON for accepted replacements and unresolved candidates
- debug overlays now render split OCR draft TEXT segments with a distinct color and replaced source TEXT nodes as evidence boxes
- p102 review report records 15 replacement sources, 30 replacement segments, and 1 unresolved low-confidence candidate
- p102 replacement-draft overlay is generated for visual review

### Stage 4.33 Split OCR Replacement Order Audit

- overlay review showed two different issues: misleading evidence-node numbering in visual overlays and real primary reading-order drift for right-column split segments
- evidence boxes no longer display fallback order numbers because they are not primary reading-order nodes
- replacement draft application reapplies two-column reading-order postprocess after split segment creation
- p102 split segments now receive `reading_order_group` metadata and right-column segments move into the right-column flow
- same-region duplicate or irregular OCR remains a review target and is not treated as solved by this order fix

## Generated Artifacts

- `data/manifests/asset_audit.json`
- `data/manifests/ebs_2027_math1_pages.json`
- `data/manifests/render_report.json`
- `data/pages_pdf300/*.png` for selected initial pages
- `data/debug/image_quality_report.json`
- `data/debug/text_only_page_ir.json`
- `data/debug/page_ir_validation_summary.json`
- `data/debug/overlay_summary.json`
- `data/debug/overlays/*.png`
- `data/debug/easyocr_text_page_ir_p008.json`
- `data/debug/easyocr_page_ir_validation_summary_p008.json`
- `data/debug/easyocr_overlay_summary_p008.json`
- `data/debug/easyocr_overlays/*.png`
- `data/debug/ocr_quality_report_p008.json`
- `data/debug/easyocr_text_page_ir_samples.json`
- `data/debug/easyocr_page_ir_validation_summary_samples.json`
- `data/debug/easyocr_overlay_summary_samples.json`
- `data/debug/easyocr_sample_overlays/*.png`
- `data/debug/ocr_quality_report_samples.json`
- `data/debug/sample_ocr_review_report.json`
- `data/debug/easyocr_visual_page_ir_samples.json`
- `data/debug/easyocr_visual_overlay_summary.json`
- `data/debug/easyocr_visual_overlays/*.png`
- `data/config/support_exclusion_approvals.json`
- `data/debug/support_review_report_samples.json`
- `data/debug/easyocr_reading_order_page_ir_samples.json`
- `data/debug/easyocr_reading_order_overlay_summary.json`
- `data/debug/easyocr_reading_order_overlays/*.png`
- `data/debug/paddleocr_text_page_ir_p008.json`
- `data/debug/paddleocr_page_ir_validation_summary_p008.json`
- `data/debug/paddleocr_overlay_summary_p008.json`
- `data/debug/paddleocr_overlays/*.png`
- `data/debug/paddleocr_quality_report_p008.json`
- `data/debug/paddleocr_text_page_ir_samples.json`
- `data/debug/paddleocr_page_ir_validation_summary_samples.json`
- `data/debug/paddleocr_quality_report_samples.json`
- `data/debug/paddleocr_overlay_summary_samples.json`
- `data/debug/paddleocr_sample_overlays/*.png`
- `data/debug/easyocr_vs_paddleocr_quality_comparison_samples.json`
- `data/debug/paddleocr_support_review_report_samples.json`
- `data/debug/paddleocr_visual_page_ir_samples.json`
- `data/debug/paddleocr_visual_overlay_summary.json`
- `data/debug/paddleocr_visual_overlays/*.png`
- `data/debug/paddleocr_baseline_page_ir_samples.json`
- `data/debug/paddleocr_baseline_validation_summary_samples.json`
- `data/debug/paddleocr_baseline_quality_report_samples.json`
- `data/debug/paddleocr_baseline_overlay_summary.json`
- `data/debug/paddleocr_baseline_overlays/*.png`
- `data/debug/paddleocr_structure_regions_p004.json`
- `data/debug/paddleocr_structure_page_ir_p004.json`
- `data/debug/paddleocr_structure_overlay_summary_p004.json`
- `data/debug/paddleocr_structure_regions_p102.json`
- `data/debug/paddleocr_structure_page_ir_p102.json`
- `data/debug/paddleocr_structure_overlay_summary_p102.json`
- `data/debug/paddleocr_structure_overlays/*.png`
- `data/debug/paddleocr_promoted_structure_page_ir_p004.json`
- `data/debug/paddleocr_promoted_structure_page_ir_p102.json`
- `data/debug/paddleocr_promoted_structure_overlay_summary_p004.json`
- `data/debug/paddleocr_promoted_structure_overlay_summary_p102.json`
- `data/debug/paddleocr_promoted_structure_overlays/*.png`
- `data/debug/paddleocr_problem_box_preview_page_ir_p102.json`
- `data/debug/paddleocr_problem_box_preview_overlay_summary_p102.json`
- `data/debug/paddleocr_problem_box_preview_overlays/*.png`
- `data/debug/paddleocr_math_candidate_page_ir_samples.json`
- `data/debug/paddleocr_math_candidate_summary_samples.json`
- `data/debug/paddleocr_baseline_math_candidate_page_ir_samples.json`
- `data/debug/paddleocr_baseline_math_candidate_summary_samples.json`
- `data/debug/paddleocr_baseline_math_candidate_crop_manifest_samples.json`
- `data/debug/paddleocr_baseline_math_candidate_crops/*.png`
- `data/debug/paddleocr_barrier_page_ir_p004.json`
- `data/debug/paddleocr_barrier_summary_p004.json`
- `data/debug/paddleocr_barrier_overlay_summary_p004.json`
- `data/debug/paddleocr_barrier_page_ir_p102.json`
- `data/debug/paddleocr_barrier_summary_p102.json`
- `data/debug/paddleocr_barrier_overlay_summary_p102.json`
- `data/debug/paddleocr_barrier_overlays/*.png`
- `data/debug/paddleocr_barrier_split_manifest_p102.json`
- `data/debug/paddleocr_barrier_split_crops/*.png`
- `data/debug/paddleocr_barrier_split_ocr_manifest_p102.json`
- `data/debug/paddleocr_split_ocr_reconciliation_page_ir_p102.json`
- `data/debug/paddleocr_split_ocr_reconciliation_summary_p102.json`
- `data/debug/paddleocr_split_ocr_replacement_draft_page_ir_p102.json`
- `data/debug/paddleocr_split_ocr_replacement_draft_summary_p102.json`
- `data/debug/paddleocr_split_ocr_replacement_review_p102.json`
- `data/debug/paddleocr_split_ocr_replacement_draft_overlay_summary_p102.json`
- `data/debug/paddleocr_split_ocr_replacement_draft_overlays/*.png`
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
- reusable invariant validation summary

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
- EasyOCR adapter for development
- PaddleOCR adapter as the project baseline OCR path with safe Windows CPU defaults
- raw cache
- explicit OCR-missing issue
- real OCR tokens for p008 sample through EasyOCR
- real OCR tokens for p008 sample through PaddleOCR safe settings
- real PaddleOCR tokens for the 8-page sample set
- OCR quality diagnostics for p008
- OCR quality diagnostics for the 8-page initial sample set
- EasyOCR/PaddleOCR comparison diagnostics for the 8-page initial sample set
- PaddleOCR baseline Page IR artifacts for the 8-page initial sample set
- PaddleOCR layout region candidate artifacts for p004 and p102
- EBS math domain-mapped structure labels for p004 and p102
- spatial links between structure candidates and OCR TEXT nodes for p004 and p102
- conservative primary-order promotion for p004 table/graph structure candidates
- explicit p102 problem-box preview promotion profile
- p102 problem-box caption linking preview metadata
- region-separation diagnostics for p004, p102, and other mixed-layout samples
- intro/guide page exclusion diagnostics for p003
- p003 intro/guide page postprocess into one linked full-page `UNSUPPORTED_VISUAL` node
- shared support policy and overfit guard tests for intro/guide exclusions
- support exclusion candidate reporting and approval-gated application
- p102 two-column reading-order postprocess with p004 over-application guard
- primary TEXT-node math candidate detection and summary reporting
- math-candidate crop export for formula OCR preparation
- layout barrier annotation and cross-barrier merge warnings for p004/p102
- split/re-OCR work-unit export for p102 cross-barrier TEXT nodes
- split crop re-OCR manifest generation for p102 cross-barrier TEXT nodes
- split OCR reconciliation preview metadata for p102 cross-barrier TEXT nodes
- split OCR replacement-draft TEXT segment generation for accepted p102 cross-barrier candidates
- stale crossing-warning cleanup for accepted p102 split OCR replacement drafts
- before/after review reporting and overlay visualization for p102 split OCR replacement drafts

Not available yet:

- OCR confidence calibration
- full sampled-page OCR regression batch with expected/golden annotations
- raw-token orphan detection against final merged Page IR
- committed problem-level layout regions beyond the preview profile
- final policy for whether linked problem captions should be removed from primary reading order or folded into problem nodes
- finalizing split OCR draft segments as production replacements across all supported pages
- automatic repair of `LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE` nodes
- review UI or approval workflow for accepting/rejecting split OCR replacement drafts
- full two-column reading-order reconstruction for arbitrary textbook layouts
- formal unsupported-page profile list beyond the current intro/structure-page heuristic
- user-facing approval workflow beyond the JSON approval config
- PP-Structure/layout/table pipeline integration for structure-aware PaddleOCR output
- final promotion rules that convert reviewed structure candidates into committed table, graph, and problem-box regions
- formula OCR execution
- committed MATH nodes, inline math span splitting, LaTeX parsing, and Presentation AST validation
- crop-level formula OCR result cache and formula OCR failure issue mapping

## Not Implemented Yet

### Stage 4 Layout And Reading Order

- container detection
- robust one-column/two-column page ordering for real OCR outputs
- box-shaped problem ordering
- full JSON Schema validation and graph validation beyond the current invariant checks
- debug overlay review with real OCR/layout boxes

### Stage 5 Math Detection And AST

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
Ran 94 tests
OK
```
