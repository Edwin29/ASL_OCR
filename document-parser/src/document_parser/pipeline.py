"""Canonical, correctly-ordered math recognition pipeline.

This module exists because running the stages out of order silently produces bad
results: math-candidate detection must run *after* graph/table structure regions
are detected and promoted, otherwise text embedded in graphs (axis labels, tick
marks) leaks into the math-candidate scan and formula OCR hallucinates on it. This
was verified end-to-end on p004: running candidate detection directly on raw OCR
output let 8 graph-axis-label nodes through, 3 of which produced "trusted" but
semantically wrong LaTeX. Running the same stages in the order below removed all 8
at the source.

Stage order (do not reorder):
    1. General OCR (with per-token bbox preserved for span splitting later)
    2. Structure region detection (table/graph/image/formula layout candidates).
       Formula regions are kept out of primary reading order (they are detection
       candidates, not committed content) and stashed as a spatial lookup for
       stage 6b instead.
    3. Structure candidate promotion (removes graph/table text from primary reading
       order, replacing it with embedded evidence)
    4. Math candidate detection (only scans primary reading-order TEXT nodes, so
       promoted graph/table text is already excluded)
    5. Math span detection (splits mixed Korean/math lines using token bboxes).
       Works only when the general OCR detector produced more than one token for a
       line; verified to fail this way for a large, page-dependent fraction of
       math-candidate lines (0%-92% observed across a 15-page sample).
    6. Formula-region fallback (document_parser.math.formula_regions): for
       math-candidate lines stage 5 could not split (OCR merged the whole line into
       one token), look for `DISPLAY_FORMULA_CANDIDATE` layout regions spatially
       inside the line. Unlike token-boundary splitting, this does not depend on
       there being OCR-visible whitespace between the Korean and math parts, so it
       recovers lines stage 5 cannot touch at all. Verified on p004: lines that
       produced 100% garbage when fed whole to formula OCR produced mostly clean,
       separately-recognized formulas once cropped to their individual regions.
    7. Math candidate crop export (span-level crops when available, whole-line
       fallback otherwise, for anything stage 6 did not already cover)
    8. Formula OCR recognition on both stage 6 and stage 7 crops, with hard guards
       against known failure modes (Hangul/CJK contamination, degenerate repetition)
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol

from document_parser.math import (
    FORMULA_REGION_LABEL,
    create_baseline_formula_ocr_adapter,
    detect_math_candidates_in_document,
    detect_math_spans_in_document,
    export_formula_region_crops,
    export_math_candidate_crops,
    math_candidate_report,
    math_span_report,
    recognize_math_candidate_crops,
)
from document_parser.math.formula_ocr import FormulaOcrAdapter
from document_parser.ocr.base import GeneralOcrAdapter
from document_parser.ocr.baseline import DEFAULT_MODEL_HOME, create_baseline_ocr_adapter
from document_parser.ocr.cache import OcrResultCache
from document_parser.serialization.text_ir import TextOnlyPageIrBuilder
from document_parser.structure import (
    PROMOTABLE_STRUCTURE_LABELS,
    PaddleStructureRegionAdapter,
    apply_structure_regions_to_document,
    promote_structure_candidates_to_primary_order_for_document,
)
from document_parser.structure.domain_mapping import map_region_to_ebs_math_domain
from document_parser.structure.paddle_structure_adapter import structure_region_node
from document_parser.validation import validate_document_ir


class StructureRegionReader(Protocol):
    def detect_regions(self, image_path: Path) -> list[object]:
        """Return structure region candidates for a page image."""


def run_math_recognition_pipeline(
    images_dir: Path,
    output_dir: Path,
    page_ids: set[str] | None = None,
    model_home: Path = DEFAULT_MODEL_HOME,
    cpu_threads: int = 2,
    enable_mkldnn: bool = False,
    layout_threshold: float = 0.35,
    crop_padding: int = 8,
    ocr_adapter: GeneralOcrAdapter | None = None,
    structure_adapter: StructureRegionReader | None = None,
    formula_adapter: FormulaOcrAdapter | None = None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    image_paths = [
        path
        for path in sorted(images_dir.glob("*.png"))
        if page_ids is None or any(f"_{page_id}" in path.stem for page_id in page_ids)
    ]
    if not image_paths:
        raise ValueError(f"No page images found in {images_dir} matching page_ids={page_ids}.")

    steps: list[dict[str, object]] = []

    # 1. General OCR
    ocr_adapter = ocr_adapter or create_baseline_ocr_adapter(
        model_home=model_home,
        cpu_threads=cpu_threads,
        enable_mkldnn=enable_mkldnn,
    )
    page_ir = TextOnlyPageIrBuilder(
        adapter=ocr_adapter,
        cache=OcrResultCache(output_dir / "ocr_cache"),
    ).build_document(image_paths)
    steps.append(write_step(output_dir, "01_ocr.json", page_ir, "general_ocr"))

    # 2. Structure region detection. Detect once per page, then split the raw
    # regions: everything except formula candidates goes through the existing
    # primary-reading-order pipeline unchanged; formula candidates are attached as
    # a spatial lookup only (stage 6b), never added to reading order, since they
    # are not committed content on their own.
    structure_adapter = structure_adapter or PaddleStructureRegionAdapter(
        model_home=model_home,
        layout_threshold=layout_threshold,
        cpu_threads=cpu_threads,
        enable_mkldnn=enable_mkldnn,
    )
    main_regions_by_page_id: dict[str, list[object]] = {}
    formula_regions_by_page_id: dict[str, list[object]] = {}
    for page in page_ir["pages"]:
        page_id = page["page_id"]
        image_path = image_path_for(images_dir, page_id)
        if image_path is None:
            continue
        geometry = page.get("page_geometry", {})
        page_width, page_height = geometry.get("width", 1.0), geometry.get("height", 1.0)
        main_regions: list[object] = []
        formula_regions: list[object] = []
        for region in structure_adapter.detect_regions(image_path):
            domain = map_region_to_ebs_math_domain(region, page_width, page_height)
            (formula_regions if domain.domain_label == FORMULA_REGION_LABEL else main_regions).append(region)
        main_regions_by_page_id[page_id] = main_regions
        formula_regions_by_page_id[page_id] = formula_regions

    page_ir = apply_structure_regions_to_document(page_ir, main_regions_by_page_id)
    page_ir = attach_formula_region_nodes(page_ir, formula_regions_by_page_id)
    steps.append(write_step(output_dir, "02_structure_regions.json", page_ir, "structure_region_detection"))

    # 3. Promotion (removes graph/table text from primary reading order at the source)
    page_ir = promote_structure_candidates_to_primary_order_for_document(
        page_ir, promotable_labels=PROMOTABLE_STRUCTURE_LABELS
    )
    steps.append(write_step(output_dir, "03_promoted.json", page_ir, "structure_promotion"))

    # 4. Math candidate detection (graph/table text already excluded by step 3)
    page_ir = detect_math_candidates_in_document(page_ir)
    candidate_report = math_candidate_report(page_ir)
    steps.append(write_step(output_dir, "04_math_candidates.json", page_ir, "math_candidate_detection"))

    # 5. Math span detection (token-boundary based; misses fully-merged lines)
    page_ir = detect_math_spans_in_document(page_ir)
    span_report = math_span_report(page_ir)
    steps.append(write_step(output_dir, "05_math_spans.json", page_ir, "math_span_detection"))

    page_ir["validation_summary"] = validate_document_ir(page_ir)
    schema_valid = page_ir["validation_summary"]["schema_valid"]

    # 6. Formula-region fallback crops for lines stage 5 could not split
    formula_region_manifest = export_formula_region_crops(
        page_ir,
        images_dir=images_dir,
        output_dir=output_dir / "formula_region_crops",
        padding=crop_padding // 2 or 2,
    )
    (output_dir / "06_formula_region_crops.json").write_text(
        json.dumps(formula_region_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 7. Standard crop export (span-level where available, whole-line fallback
    # otherwise) for everything else
    crop_manifest = export_math_candidate_crops(
        page_ir,
        images_dir=images_dir,
        output_dir=output_dir / "crops",
        padding=crop_padding,
    )
    (output_dir / "07_crop_manifest.json").write_text(
        json.dumps(crop_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 8. Formula OCR recognition on both crop sets (same guards apply to both)
    formula_adapter = formula_adapter or create_baseline_formula_ocr_adapter(
        model_home=model_home,
        cpu_threads=cpu_threads,
        enable_mkldnn=enable_mkldnn,
    )
    formula_region_results = recognize_math_candidate_crops(
        formula_region_manifest, adapter=formula_adapter, path_base=output_dir
    )
    (output_dir / "08a_formula_region_ocr.json").write_text(
        json.dumps(formula_region_results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    formula_results = recognize_math_candidate_crops(crop_manifest, adapter=formula_adapter, path_base=output_dir)
    (output_dir / "08b_formula_ocr.json").write_text(
        json.dumps(formula_results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "page_count": len(page_ir["pages"]),
        "schema_valid": schema_valid,
        "math_candidate_count": candidate_report["total_candidate_count"],
        "math_span_split_node_count": span_report["total_split_node_count"],
        "math_span_candidate_count": span_report["total_math_span_count"],
        "formula_region_crop_count": formula_region_manifest["crop_count"],
        "formula_region_trusted_count": formula_region_results["trusted_crop_count"],
        "formula_region_untrusted_count": formula_region_results["untrusted_crop_count"],
        "crop_count": crop_manifest["crop_count"],
        "formula_ocr_trusted_count": formula_results["trusted_crop_count"],
        "formula_ocr_untrusted_count": formula_results["untrusted_crop_count"],
        "total_trusted_count": formula_region_results["trusted_crop_count"] + formula_results["trusted_crop_count"],
        "total_untrusted_count": formula_region_results["untrusted_crop_count"] + formula_results["untrusted_crop_count"],
        "steps": [step["name"] for step in steps],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def attach_formula_region_nodes(
    payload: dict[str, object],
    formula_regions_by_page_id: dict[str, list[object]],
) -> dict[str, object]:
    """Stash DISPLAY_FORMULA_CANDIDATE regions for spatial lookup only.

    These are detection candidates, not committed content: they are never added to
    `nodes`/`reading_order` (a MATH-typed node sitting outside reading order with no
    embedded-evidence link would fail Page IR validation, and it must not be read
    aloud or otherwise consumed directly anyway). They live under the page's
    `formula_region_candidates` side-channel instead, which the schema validator
    does not inspect.
    """
    result = deepcopy(payload)
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("page_id", ""))
        regions = formula_regions_by_page_id.get(page_id, [])
        if not regions:
            continue
        geometry = page.get("page_geometry") if isinstance(page.get("page_geometry"), dict) else {}
        page_width = float(geometry.get("width") or 1.0)
        page_height = float(geometry.get("height") or 1.0)
        candidates = page.get("formula_region_candidates")
        if not isinstance(candidates, list):
            candidates = []
            page["formula_region_candidates"] = candidates
        existing_ids = {item.get("node_id") for item in candidates if isinstance(item, dict)}
        next_index = 1
        for region in regions:
            node_id = f"{page_id}-formula-region-{next_index:03d}"
            while node_id in existing_ids:
                next_index += 1
                node_id = f"{page_id}-formula-region-{next_index:03d}"
            existing_ids.add(node_id)
            next_index += 1
            node = structure_region_node(
                node_id=node_id,
                region=region,
                page_width=page_width,
                page_height=page_height,
                reading_order_index=-1,
            )
            node.pop("reading_order_index", None)
            candidates.append(node)
    return result


def write_step(output_dir: Path, filename: str, payload: dict[str, object], name: str) -> dict[str, object]:
    (output_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"name": name, "path": str(output_dir / filename)}


def image_path_for(images_dir: Path, page_id: str) -> Path | None:
    matches = sorted(images_dir.glob(f"*_{page_id}.png"))
    return matches[0] if matches else None
