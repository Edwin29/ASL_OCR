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

## Completed Page IR Validation Gate Follow-up

The next milestone moved Page IR validation into a reusable module and added a standalone CLI gate.

- `document_parser.validation` now owns Page IR invariant checks.
- The validator checks required fields, core types, bbox ranges, normalized bbox ranges, confidence ranges, quality status, issue shape, reading-order references, duplicate IDs, missing reading-order nodes, and page-count mismatch.
- `tools/validate_page_ir.py` validates any generated Page IR JSON and returns a non-zero exit code when the payload is invalid.
- `data/debug/page_ir_validation_summary.json` records the latest validation result for the EBS rendered sample baseline.

## Completed Debug Overlay Follow-up

The next milestone added visual inspection artifacts for Page IR and layout outputs.

- `document_parser.debug` renders Page IR node boxes on source page images.
- `tools/render_page_ir_overlays.py` renders overlays for generated Page IR files.
- The overlay summary records page/image/output mappings, node counts, issue counts, and quality status.
- `data/debug/overlays/` contains overlay PNG files for the current EBS rendered sample baseline.

## Completed EasyOCR Development Adapter Follow-up

The next milestone connected the temporary development OCR engine.

- `EasyOcrGeneralAdapter` implements `GeneralOcrAdapter` using EasyOCR.
- `tools/easyocr_text_ir.py` generates TEXT-only Page IR with real EasyOCR tokens.
- EasyOCR model/cache paths are kept under `data/debug/model_home` for local development.
- OCR cache keys now include adapter configuration signatures to avoid option collisions.
- `data/debug/easyocr_text_page_ir_p008.json` records a real EasyOCR Page IR sample for EBS page p008.
- EasyOCR Page IR validation and overlay artifacts are generated for p008.

## Completed OCR Quality Report Follow-up

The next milestone added a practical diagnostic report for real OCR Page IR output.

- `document_parser.evaluation` now owns OCR/Page IR diagnostic report generation.
- `tools/ocr_quality_report.py` writes page-level OCR quality and reading-order warning summaries.
- The report flags low-confidence nodes, suspiciously wide/tall nodes, overlapping boxes, and large reading-order jumps.
- `data/debug/ocr_quality_report_p008.json` records the EasyOCR p008 diagnostic result.

## Completed Sample OCR Review Follow-up

The next milestone expanded EasyOCR diagnostics from one page to the full initial sample set.

- EasyOCR TEXT-only Page IR is generated for the 8 rendered sample pages.
- Validation, overlay, and OCR quality reports are generated for the same sample set.
- `document_parser.evaluation.sample_review` combines those artifacts into a compact review-priority report.
- `data/debug/sample_ocr_review_report.json` ranks pages by low-confidence nodes, reading-order warnings, overlap warnings, and suspicious node shapes.

## Completed Region Separation Diagnostics Follow-up

The next milestone incorporated overlay review feedback into the diagnostics layer.

- Wide noisy lines are flagged as mixed body/visual/table region candidates.
- Numeric/list-like lines are flagged as table-like or answer-list candidates.
- Pages with midpoint-crossing lines and left/right column evidence are flagged as two-column split candidates.
- p004 now surfaces table/body separation candidates.
- p102 now surfaces two-column and answer-list separation candidates.

## Completed Intro Guide Page Exclusion Diagnostics Follow-up

The next milestone changed p003 introduction-page handling from region splitting to unsupported-page exclusion diagnostics.

- Intro/structure pages are detected from header text such as `Structure`.
- Dense guide/example-page OCR is treated as a signal that the page is publisher guide content.
- p003 now surfaces `INTRO_GUIDE_PAGE_EXCLUSION_CANDIDATE` in the sample OCR review report.

## Completed Intro Guide Page Exclusion Postprocess Follow-up

The next milestone moved the p003 introduction-page policy from diagnostics into a conservative Page IR postprocess.

- p003 becomes one full-page `UNSUPPORTED_VISUAL` node.
- All p003 OCR TEXT nodes are preserved and linked through `embedded_text_nodes`.
- All p003 OCR TEXT nodes are removed from primary `reading_order`.
- The Page IR validator now accepts linked embedded OCR nodes outside primary reading order.
- `tools/apply_visual_regions.py` applies this unsupported-page postprocess to an existing Page IR JSON without rerunning OCR.

## Completed Support Policy Overfit Guard Follow-up

The next milestone checked whether the intro/guide exclusion work was overfit to p003 and moved the decision into a shared policy module.

- Source code no longer keys the exclusion decision on `p003`.
- Diagnostics and Page IR postprocess share the same intro/guide exclusion decision.
- Exclusion decisions record evidence counts for review.
- Regression tests cover a non-p003 intro guide page.
- Regression tests keep sparse math pages with incidental `Structure` text supported.
- The current 8-page EasyOCR sample check excludes only p003.

## Completed Support Exclusion Approval Gate Follow-up

The next milestone added an approval gate so unsupported-page candidates can be reported before they are excluded from primary parsing.

- `tools/support_review_report.py` writes unsupported-page candidate reports.
- `data/config/support_exclusion_approvals.json` records approved exclusion types.
- `tools/apply_visual_regions.py` applies only approved exclusion types.
- Without approval, an unsupported-page candidate remains report-only.
- With the current approval config, the 8-page sample reports one approved p003 intro/guide candidate and zero pending candidates.

## Completed Two-Column Reading Order Follow-up

The next milestone improved supported-page reading order for full-page two-column layouts.

- Two-column reading-order detection now requires left and right columns across all body vertical bands.
- p102 receives header, left-column, right-column, footer reading order.
- p004 is no longer over-applied as a two-column reading-order page.
- Primary nodes receive `layout.reading_order_group` metadata.
- `tools/apply_reading_order.py` applies this postprocess to an existing Page IR JSON.
- Debug overlay labels now prefer `reading_order_index`, making reordered pages easier to inspect.

## Completed PaddleOCR Safe Adapter Smoke Follow-up

The next milestone added PaddleOCR behind the existing OCR adapter contract without replacing EasyOCR yet.

- `PaddleOcrGeneralAdapter` normalizes PaddleOCR v3/v5 dict results into `OcrToken`.
- Safe Windows CPU defaults are used: MKLDNN disabled, 2 CPU threads, detector max side length 1600.
- Paddle cache/home paths are redirected under `data/debug/model_home`.
- `tools/paddleocr_text_ir.py` generates TEXT-only Page IR with PaddleOCR.
- p008 PaddleOCR Page IR, validation, overlay, and OCR quality artifacts were generated successfully.
- p008 smoke comparison: EasyOCR and PaddleOCR both emitted 30 Page IR nodes; PaddleOCR had 0 low-confidence nodes in the current quality report.

## Completed OCR Engine Sample Comparison Follow-up

The next milestone expanded PaddleOCR from a single-page smoke test to the 8-page rendered sample set.

- `tools/compare_ocr_quality.py` compares two OCR Page IR payloads using the shared OCR quality diagnostics.
- PaddleOCR sample Page IR, validation summary, quality report, and overlay set were generated.
- `data/debug/easyocr_vs_paddleocr_quality_comparison_samples.json` compares EasyOCR and PaddleOCR across the sample set.
- PaddleOCR reduced low-confidence nodes from 121 to 1 and total diagnostic score from 169 to 53.
- The comparison recommends advancing PaddleOCR to overlay review, not switching the default OCR engine automatically.
- p102 is the remaining review-heavy sample because PaddleOCR increases reading-order and region-separation diagnostics there.

## Completed PaddleOCR Baseline Promotion Follow-up

The next milestone accepted PaddleOCR as the project baseline OCR engine while keeping structure-aware PP-Structure work separate.

- `create_baseline_ocr_adapter()` now returns the PaddleOCR PP-OCRv5 adapter.
- Baseline models are `PP-OCRv5_server_det` for text detection and `korean_PP-OCRv5_mobile_rec` for Korean text recognition.
- `tools/baseline_ocr_text_ir.py` provides a stable baseline OCR entry point.
- `pyproject.toml` now lists PaddleOCR/PaddlePaddle under the primary `ocr` optional dependency and EasyOCR under `legacy-ocr`.
- PaddleOCR baseline sample artifacts were generated under `data/debug/paddleocr_baseline_*`.
- p003 is excluded as an approved intro/guide unsupported page in the PaddleOCR baseline Page IR.
- p102 remains the priority sample for layout and structure tuning.

## Completed PaddleOCR Layout Region Candidate Follow-up

The next milestone added the first structure-aware PaddleOCR path.

- Local PaddleOCR exposes `PPStructureV3`, `LayoutDetection`, and table-related pipeline classes.
- Full `PPStructureV3` currently requires extra `paddlex[ocr]` dependencies in this environment.
- `LayoutDetection` with `PP-DocLayout_plus-L`, CPU, and MKLDNN disabled runs successfully.
- `tools/paddleocr_structure_regions.py` adds experimental structure candidates to an existing Page IR.
- p004 now receives one table candidate and two image/graph candidates.
- p102 receives large layout-region candidates for the two-column problem layout.
- Structure candidate outputs remain schema-valid and overlays are generated under `data/debug/paddleocr_structure_overlays`.

## Completed EBS Math Structure Domain Mapping Follow-up

The next milestone added a textbook-domain interpretation layer over PaddleOCR layout labels.

- Compact PaddleOCR `table` regions are mapped to `TABLE_CANDIDATE`.
- Large `table`-like regions are mapped to `PROBLEM_BOX_CANDIDATE` to avoid prematurely treating boxed problems as tables.
- `image`/`figure`/`chart`/`graph` regions are mapped to `GRAPH_OR_DIAGRAM_CANDIDATE`.
- `figure_title`/`table_title` regions are mapped to `VISUAL_OR_PROBLEM_CAPTION_CANDIDATE`.
- p004 now reports 1 `TABLE_CANDIDATE` and 2 `GRAPH_OR_DIAGRAM_CANDIDATE` regions.
- p102 now reports 6 `PROBLEM_BOX_CANDIDATE` and 6 `VISUAL_OR_PROBLEM_CAPTION_CANDIDATE` regions.
- Raw structure summaries include both the original PaddleOCR label and the mapped EBS-domain label.

## Completed Structure Candidate Text Linking Follow-up

The next milestone connected structure candidates to the OCR TEXT nodes they spatially contain.

- Structure candidate nodes now record `contained_text_nodes`.
- Structure node layout metadata records contained text counts and overlap evidence.
- TEXT node layout metadata records `parent_structure_node_ids` and `primary_parent_structure_node_id`.
- Primary reading order is unchanged; this remains a conservative linking stage.
- p004 links 14 TEXT nodes to table/graph structure candidates.
- p102 links 62 TEXT nodes to problem-box/caption structure candidates.
- Structure-linked Page IR outputs remain schema-valid.

## Completed Structure Candidate Promotion Follow-up

The next milestone promoted only reviewed-safe structure candidates into primary reading order.

- `TABLE_CANDIDATE` and `GRAPH_OR_DIAGRAM_CANDIDATE` are promotable by default.
- Promoted structure nodes replace their contained OCR TEXT nodes in primary `reading_order`.
- Contained OCR TEXT nodes are preserved as `embedded_text_nodes` and marked non-primary.
- p004 promotes 1 table candidate and 2 graph/diagram candidates.
- p004 preserves 14 contained OCR TEXT nodes as embedded evidence.
- p102 promotes 0 candidates by default; problem-box candidates remain candidates for later layout logic.
- Promoted Page IR outputs remain schema-valid.

## Completed Problem-Box Preview Promotion Follow-up

The next milestone added an explicit preview profile for problem-box candidates.

- `tools/promote_structure_candidates.py` now supports `--profile safe` and `--profile problem-box-preview`.
- `safe` remains the default and promotes only table/graph candidates.
- `problem-box-preview` promotes `PROBLEM_BOX_CANDIDATE` regions explicitly.
- p102 preview promotes 6 problem boxes.
- p102 preview preserves 58 contained OCR TEXT nodes as embedded evidence.
- Problem-box preview uses geometry order: left column top-to-bottom, then right column top-to-bottom.
- Preview metadata is recorded under `engine_manifest.structure_promotion`.

## Completed Problem-Box Caption Linking Follow-up

The next milestone linked caption/title candidates to their corresponding promoted problem boxes.

- Caption candidates are not removed from primary reading order at this stage.
- Problem boxes now record linked caption candidate IDs and geometric evidence.
- Caption candidates record their parent problem-box structure node.
- The matching rule uses nearby same-column geometry: vertical gap above the box and horizontal overlap.
- p102 preview links 6 caption candidates to 6 promoted problem boxes.
- The p102 preview Page IR remains schema-valid.

## Completed Math Candidate Detection Entry Follow-up

The next milestone opened Stage 5 with conservative math-candidate metadata.

- TEXT nodes can now be marked with `layout.math_candidate` for later formula OCR and AST parsing.
- The detector keeps original TEXT nodes intact and does not create committed `MATH` nodes yet.
- Candidate scoring uses relation operators, function notation, fractions, powers/subscripts, and symbolic density.
- Simple answer-list rows are excluded from math-candidate scoring.
- Only primary reading-order TEXT nodes are scanned, so embedded evidence from unsupported pages is not reintroduced.
- PaddleOCR baseline samples produce 119 math candidates and remain schema-valid.

## Completed Math Candidate Crop Export Follow-up

The next milestone converted math-candidate metadata into formula-OCR-ready crop work units.

- `tools/export_math_candidate_crops.py` exports one PNG crop per primary TEXT math candidate.
- Crop bounding boxes preserve the original node bbox and add configurable padding.
- Crop boxes are clamped to the source page image bounds.
- The crop manifest records page ID, node ID, original bbox, crop bbox, score, reasons, text, and crop path.
- PaddleOCR baseline samples export 119 math-candidate crops with no missing crop files.
- This stage prepares formula OCR input; it still does not create committed `MATH` nodes or Presentation AST.

## Completed Layout Barrier Annotation Follow-up

The next milestone turned reviewed structure regions into explicit layout barriers.

- `document_parser.structure.barriers` marks table, graph/diagram, and problem-box candidates as layout barriers.
- Primary TEXT nodes receive `layout.primary_layout_barrier_node_id` when they are spatially contained by a barrier.
- Barriers record assigned TEXT node refs without changing primary reading order.
- TEXT nodes that overlap multiple barriers are reported as `LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE`.
- p004 barrier annotation marks 3 barriers, assigns 14 TEXT nodes, and reports 0 crossing warnings.
- p102 barrier annotation marks 6 problem-box barriers, assigns 58 TEXT nodes, and reports 16 crossing warnings for later split/reconciliation work.

## Completed Layout Barrier Split Work-Unit Export Follow-up

The next milestone converted crossing warnings into concrete split/re-OCR work units.

- `document_parser.structure.barrier_splits` exports crop work units for TEXT nodes crossing multiple layout barriers.
- Each work unit uses the intersection between the crossing TEXT bbox and one barrier bbox.
- Split crops preserve the source TEXT node ID, barrier node ID, source bbox, barrier bbox, intersection bbox, crop bbox, and source text.
- No TEXT string is split automatically at this stage.
- p102 exports 32 split work-unit crops from 16 crossing TEXT nodes.
- The p102 split manifest has 0 missing crop files.

## Completed Layout Barrier Split Re-OCR Follow-up

The next milestone ran the baseline PaddleOCR engine on split/re-OCR work units.

- `document_parser.structure.barrier_split_ocr` recognizes split crop work units through the shared `GeneralOcrAdapter` contract.
- `tools/ocr_layout_barrier_split_crops.py` writes a split OCR manifest without mutating the source Page IR.
- Split OCR manifest entries preserve source TEXT node ID, barrier node ID, crop path, source text, recognized text, OCR tokens, and geometry provenance.
- p102 split crop OCR recognizes all 32 work units and emits 225 crop-level OCR tokens.
- This confirms the localized re-OCR path is runnable, but automatic replacement of original crossing TEXT nodes remains a later reconciliation step.

## Completed Split OCR Reconciliation Preview Follow-up

The next milestone linked split OCR results back to the original crossing TEXT nodes as review metadata.

- `document_parser.structure.barrier_reconciliation` groups split OCR work units by source TEXT node.
- `tools/apply_split_ocr_reconciliation.py` attaches preview metadata to crossing TEXT nodes without changing primary reading order.
- Preview metadata records split segments, recognized text, confidence summary, crop provenance, and replacement-review status.
- p102 receives reconciliation previews for 16 crossing TEXT nodes and 32 split OCR segments.
- 15 p102 candidates are marked `REVIEW_REPLACE_CANDIDATE`; 1 candidate remains `REVIEW_REQUIRED_LOW_CONFIDENCE`.
- The reconciliation-preview Page IR remains schema-valid.

## Completed Split OCR Replacement Draft Follow-up

The next milestone converted approved reconciliation previews into draft primary TEXT segments.

- `document_parser.structure.barrier_replacement` creates draft TEXT segment nodes from `REVIEW_REPLACE_CANDIDATE` previews.
- `tools/apply_split_ocr_replacement_draft.py` writes a draft Page IR and summary report.
- Original crossing TEXT nodes are preserved as non-primary evidence through `split_ocr_replaced_by_node_ids`.
- The validator now accepts linked split-OCR evidence TEXT nodes outside primary reading order.
- p102 converts 15 safe crossing TEXT candidates into 30 draft TEXT segment nodes.
- The one low-confidence p102 candidate remains unchanged in primary reading order.
- The replacement-draft Page IR remains schema-valid.

## Completed Split OCR Replacement Issue Cleanup Follow-up

The next milestone cleaned stale layout-barrier crossing warnings after draft replacement.

- Replacement draft application now removes `LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE` issues for source TEXT nodes that were replaced by split OCR draft segments.
- Unaccepted candidates keep their crossing warnings so unresolved risks remain visible.
- The replacement summary records resolved and unresolved crossing warning counts.
- p102 resolves 15 stale crossing warnings and leaves 1 unresolved warning for the low-confidence candidate `p102-n031`.
- The cleaned replacement-draft Page IR remains schema-valid.

## Completed Split OCR Replacement Review Artifacts Follow-up

The next milestone made replacement drafts easier to review visually and as structured before/after data.

- `document_parser.structure.replacement_review` builds a before/after review report from a replacement-draft Page IR.
- `tools/split_ocr_replacement_review.py` writes review JSON for accepted replacements and unresolved candidates.
- Debug overlays now color split OCR draft TEXT segments distinctly and show replaced source TEXT nodes as evidence boxes.
- p102 review report records 15 replacement sources, 30 replacement segments, and 1 unresolved low-confidence candidate.
- p102 replacement-draft overlay is generated under `data/debug/paddleocr_split_ocr_replacement_draft_overlays/`.

## Completed Split OCR Replacement Order Audit Follow-up

The next milestone addressed overlay review feedback about mixed visual numbering and draft segment order.

- The issue was partly visual: replaced source TEXT nodes are evidence, not primary reading-order nodes, so overlay labels no longer show misleading evidence order numbers.
- The issue was also partly internal: replacement draft segments were initially inserted next to the original crossing node, which could place right-column segments inside left-column reading flow.
- Replacement draft application now reapplies two-column reading-order postprocess after segment creation.
- p102 draft segments now receive left/right `reading_order_group` metadata and right-column segments move into the right-column flow.
- Same-region duplicate or irregular recognition remains a real review concern rather than a display-only issue.
