"""Formula-region-based math span recovery.

`document_parser.math.spans` splits a line into text/math spans using OCR *token*
boundaries. That fails whenever the general OCR detector merges an entire mixed
Korean/math line into a single token (verified on real EBS pages: this happens for
roughly a fifth to over half of math-candidate lines, depending on the page).

The PaddleOCR/PaddleX layout model exposes a completely different detection
mechanism for exactly this case: `LayoutDetection`/`PPStructureV3` can be asked for
"formula"/"equation" *regions* (`--include-formula` on
`paddle_structure_adapter.py`), which are found by recognizing what a formula looks
like as a visual pattern, not by finding text-instance gaps. This does not depend on
there being any OCR-visible whitespace between the Korean and math parts of a line,
so it succeeds on lines the token-boundary approach cannot touch at all. Verified on
p004: lines that produced 100% garbage when fed whole to formula OCR produced mostly
clean, separately-recognized formulas (e.g. "x=\\sqrt[n]{a}", "a\\geq0") once cropped
to their individual formula regions.

This module is the fallback stage for exactly the lines
`document_parser.math.spans` could not split: it finds `DISPLAY_FORMULA_CANDIDATE`
structure regions that fall inside an un-split math-candidate TEXT node's bbox, and
exports one crop per region for formula OCR (reusing
`document_parser.math.formula_ocr.recognize_math_candidate_crops`, since the
manifest shape is compatible).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

FORMULA_REGION_LABEL = "DISPLAY_FORMULA_CANDIDATE"
DEFAULT_CONTAINMENT_THRESHOLD = 0.6


def find_formula_regions_in_page(page: dict[str, Any]) -> list[dict[str, Any]]:
    # Formula regions live in the `formula_region_candidates` side-channel, not in
    # `nodes` (see document_parser.pipeline.attach_formula_region_nodes for why: a
    # MATH-typed node sitting outside reading_order with no embedded-evidence link
    # would fail Page IR schema validation). Also accept them from `nodes` for
    # callers that pre-date the side-channel or pass already-linked structure nodes.
    candidates = page.get("formula_region_candidates")
    if isinstance(candidates, list) and candidates:
        return [
            node
            for node in candidates
            if isinstance(node, dict)
            and isinstance(node.get("layout"), dict)
            and node["layout"].get("structure_label") == FORMULA_REGION_LABEL
        ]
    return [
        node
        for node in page.get("nodes", [])
        if isinstance(node, dict)
        and isinstance(node.get("layout"), dict)
        and node["layout"].get("structure_label") == FORMULA_REGION_LABEL
    ]


def is_unsplit_math_candidate(node: dict[str, Any]) -> bool:
    layout = node.get("layout")
    if not isinstance(layout, dict):
        return False
    candidate = layout.get("math_candidate")
    is_candidate = isinstance(candidate, dict) and candidate.get("is_candidate") is True
    return is_candidate and "math_span_count" not in layout


def matching_formula_regions(
    text_box: dict[str, float],
    formula_regions: list[dict[str, Any]],
    containment_threshold: float,
) -> list[dict[str, Any]]:
    matches = []
    for region in formula_regions:
        region_box = bbox(region)
        region_id = region.get("node_id")
        if region_box is None or not isinstance(region_id, str):
            continue
        ratio = intersection_ratio(region_box, text_box)
        if ratio >= containment_threshold:
            matches.append({"region_node_id": region_id, "region_bbox": region_box, "containment_ratio": round(ratio, 6)})
    matches.sort(key=lambda match: match["region_bbox"]["x"])
    return matches


def export_formula_region_crops(
    payload: dict[str, object],
    images_dir: Path,
    output_dir: Path,
    padding: int = 4,
    containment_threshold: float = DEFAULT_CONTAINMENT_THRESHOLD,
    page_ids: set[str] | None = None,
) -> dict[str, object]:
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Page IR payload must contain a pages list.")
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_pages = []
    total_crops = 0
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("page_id")
        if not isinstance(page_id, str) or (page_ids is not None and page_id not in page_ids):
            continue
        image_path = find_page_image(images_dir, page_id)
        crops = export_page_formula_region_crops(page, image_path, output_dir, padding, containment_threshold)
        manifest_pages.append({"page_id": page_id, "crop_count": len(crops), "crops": crops})
        total_crops += len(crops)

    return {
        "mode": "formula_region_fallback_crops",
        "containment_threshold": containment_threshold,
        "page_count": len(manifest_pages),
        "crop_count": total_crops,
        "pages": manifest_pages,
    }


def export_page_formula_region_crops(
    page: dict[str, Any],
    image_path: Path,
    output_dir: Path,
    padding: int,
    containment_threshold: float,
) -> list[dict[str, object]]:
    page_id = str(page.get("page_id", image_path.stem))
    formula_regions = find_formula_regions_in_page(page)
    if not formula_regions:
        return []

    reading_order = {node_id for node_id in page.get("reading_order", []) if isinstance(node_id, str)}
    candidate_nodes = [
        node
        for node in page.get("nodes", [])
        if isinstance(node, dict)
        and node.get("content_type") == "TEXT"
        and isinstance(node.get("node_id"), str)
        and (not reading_order or node["node_id"] in reading_order)
        and is_unsplit_math_candidate(node)
    ]
    if not candidate_nodes:
        return []

    crops: list[dict[str, object]] = []
    with Image.open(image_path) as image:
        image_width, image_height = image.size
        for node in candidate_nodes:
            node_id = str(node["node_id"])
            text_box = bbox(node)
            if text_box is None:
                continue
            matches = matching_formula_regions(text_box, formula_regions, containment_threshold)
            for index, match in enumerate(matches, start=1):
                crop_box = padded_crop_box(match["region_bbox"], image_width, image_height, padding)
                if crop_box is None:
                    continue
                crop_path = output_dir / page_id / f"{safe_filename(node_id)}__formula_region_{index:02d}.png"
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                image.crop(crop_box).save(crop_path)
                crops.append({
                    "node_id": node_id,
                    "region_node_id": match["region_node_id"],
                    "region_index": index,
                    "crop_path": str(crop_path),
                    "bbox": match["region_bbox"],
                    "containment_ratio": match["containment_ratio"],
                    "crop_bbox": {
                        "x": crop_box[0],
                        "y": crop_box[1],
                        "width": crop_box[2] - crop_box[0],
                        "height": crop_box[3] - crop_box[1],
                    },
                    "image_size": {"width": image_width, "height": image_height},
                    "text": node.get("normalized_text", ""),
                })
    return crops


def bbox(node: dict[str, Any]) -> dict[str, float] | None:
    raw = node.get("bbox")
    if not isinstance(raw, dict):
        return None
    values = {key: number_value(raw.get(key)) for key in ("x", "y", "width", "height")}
    if any(value is None for value in values.values()):
        return None
    return {key: float(value) for key, value in values.items() if value is not None}


def intersection_ratio(inner: dict[str, float], outer: dict[str, float]) -> float:
    width = max(0.0, min(inner["x"] + inner["width"], outer["x"] + outer["width"]) - max(inner["x"], outer["x"]))
    height = max(0.0, min(inner["y"] + inner["height"], outer["y"] + outer["height"]) - max(inner["y"], outer["y"]))
    intersection_area = width * height
    denominator = max(inner["width"] * inner["height"], 1.0)
    return intersection_area / denominator


def padded_crop_box(
    box: dict[str, float],
    image_width: int,
    image_height: int,
    padding: int,
) -> tuple[int, int, int, int] | None:
    left = max(0, int(box["x"]) - padding)
    top = max(0, int(box["y"]) - padding)
    right = min(image_width, int(box["x"] + box["width"]) + padding)
    bottom = min(image_height, int(box["y"] + box["height"]) + padding)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def find_page_image(images_dir: Path, page_id: str) -> Path:
    candidates = sorted(images_dir.glob(f"*_{page_id}.png"))
    if not candidates:
        candidates = sorted(images_dir.glob(f"*{page_id}*.png"))
    if not candidates:
        raise FileNotFoundError(f"No PNG image found for page_id={page_id} in {images_dir}")
    return candidates[0].resolve()


def safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
