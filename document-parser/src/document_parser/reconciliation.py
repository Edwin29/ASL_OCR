"""Cross-validate low-confidence PaddleOCR-VL nodes against the legacy engines.

Stage 8 was originally scoped around merging redundant output from several
engines that each processed the same pixels (기획서 §15, "결과 통합과 중복 제거").
That scenario mostly does not occur any more: PaddleOCR-VL assigns each region
to exactly one block (verified: zero bbox overlap across every block on
p004/p014/p019/p050), so there is nothing to deduplicate in the classic sense.

What VL *does* have is a handful of concrete, independently-verified failure
modes (silent choice omission, AST-unparseable formula fragments) that are
flagged as issues but never checked against anything else. This module is
where that check happens: for the minority of nodes carrying one of those
issues, crop the same source pixels and ask a *different* engine (the legacy
`PaddleFormulaOcrAdapter` / `PaddleOcrGeneralAdapter` this project already
validated at length) for a second opinion, and record both readings side by
side. This is deliberately narrow -- it does not re-run the legacy pipeline on
every node, only the ones VL's own output already told us to doubt.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image

from document_parser.ingest import ImageIngestor
from document_parser.math.formula_ocr import FormulaOcrAdapter, validate_formula_output
from document_parser.ocr.base import GeneralOcrAdapter
from document_parser.serialization.vl_page_ir import CHOICE_MARKER_PATTERN

AST_ISSUE_PREFIX = "AST_"
CHOICE_OMISSION_CODE = "VL_POSSIBLE_CHOICE_OMISSION"
DEFAULT_PADDING = 8


def cross_validate_document(
    payload: dict[str, object],
    images_dir: Path,
    formula_adapter: FormulaOcrAdapter,
    ocr_adapter: GeneralOcrAdapter,
    padding: int = DEFAULT_PADDING,
) -> dict[str, object]:
    result = deepcopy(payload)
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result
    for page in pages:
        if isinstance(page, dict):
            cross_validate_page(page, images_dir, formula_adapter, ocr_adapter, padding)
    return result


def cross_validate_page(
    page: dict[str, Any],
    images_dir: Path,
    formula_adapter: FormulaOcrAdapter,
    ocr_adapter: GeneralOcrAdapter,
    padding: int = DEFAULT_PADDING,
) -> dict[str, object]:
    page_id = str(page.get("page_id", ""))
    image_path = find_page_image(images_dir, page_id)
    if image_path is None:
        return page
    with Image.open(image_path) as image:
        width, height = image.size
        for node in page.get("nodes", []):
            if not isinstance(node, dict):
                continue
            if node.get("content_type") == "MATH" and has_ast_issue(node):
                cross_validate_math_node(node, image, width, height, formula_adapter, padding)
            elif node.get("content_type") == "TEXT" and has_issue_code(node, CHOICE_OMISSION_CODE):
                cross_validate_choice_node(node, image, width, height, page_id, ocr_adapter, padding)
    return page


def has_ast_issue(node: dict[str, Any]) -> bool:
    return any(
        isinstance(issue, dict)
        and isinstance(issue.get("code"), str)
        and issue["code"].startswith(AST_ISSUE_PREFIX)
        and issue.get("severity") in {"warning", "error"}
        for issue in node.get("issues", [])
    )


def has_issue_code(node: dict[str, Any], code: str) -> bool:
    return any(isinstance(issue, dict) and issue.get("code") == code for issue in node.get("issues", []))


def cross_validate_math_node(
    node: dict[str, Any],
    image: Image.Image,
    image_width: int,
    image_height: int,
    formula_adapter: FormulaOcrAdapter,
    padding: int,
) -> None:
    crop_box = padded_crop_box(node.get("bbox"), image_width, image_height, padding)
    if crop_box is None:
        return
    crop_path = crop_to_temp_file(image, crop_box, prefix=str(node.get("node_id", "math")))
    try:
        result = formula_adapter.recognize(crop_path)
    finally:
        crop_path.unlink(missing_ok=True)

    guard_issues = validate_formula_output(result.raw_latex)
    is_trusted = not any(issue["severity"] == "error" for issue in guard_issues)
    candidates = node.setdefault("alternative_candidates", [])
    candidates.append({
        "engine_id": formula_adapter.engine_id,
        "raw_formula": result.raw_latex,
        "trusted": is_trusted,
        "issues": guard_issues,
    })
    node.setdefault("issues", []).append({
        "code": "CROSS_VALIDATION_RECORDED",
        "severity": "info",
        "message": (
            f"Cross-validated against {formula_adapter.engine_id} due to AST parsing issues; "
            f"see alternative_candidates (trusted={is_trusted})."
        ),
    })


def cross_validate_choice_node(
    node: dict[str, Any],
    image: Image.Image,
    image_width: int,
    image_height: int,
    page_id: str,
    ocr_adapter: GeneralOcrAdapter,
    padding: int,
) -> None:
    crop_box = padded_crop_box(node.get("bbox"), image_width, image_height, padding)
    if crop_box is None:
        return
    crop_path = crop_to_temp_file(image, crop_box, prefix=str(node.get("node_id", "choices")))
    try:
        ingestor = ImageIngestor()
        legacy_image = ingestor.load(crop_path, page_id=f"{page_id}-crossval")
        ocr_result = ocr_adapter.recognize(legacy_image)
    finally:
        crop_path.unlink(missing_ok=True)

    legacy_text = " ".join(token.text for token in ocr_result.tokens)
    legacy_marker_count = len(set(CHOICE_MARKER_PATTERN.findall(legacy_text)))
    vl_marker_count = len(set(CHOICE_MARKER_PATTERN.findall(str(node.get("normalized_text", "")))))

    if legacy_marker_count > vl_marker_count:
        node.setdefault("issues", []).append({
            "code": "CROSS_VALIDATION_CONFIRMS_OMISSION",
            "severity": "error",
            "message": (
                f"{ocr_adapter.engine_id} found {legacy_marker_count} choice marker(s) in this region vs. "
                f"{vl_marker_count} in PaddleOCR-VL's text; a choice was very likely dropped."
            ),
            "legacy_engine_id": ocr_adapter.engine_id,
            "legacy_text": legacy_text,
        })
    else:
        node.setdefault("issues", []).append({
            "code": "CROSS_VALIDATION_INCONCLUSIVE",
            "severity": "info",
            "message": (
                f"{ocr_adapter.engine_id} also found only {legacy_marker_count} choice marker(s) in this region; "
                "the omission warning could not be confirmed or ruled out from OCR alone."
            ),
            "legacy_engine_id": ocr_adapter.engine_id,
            "legacy_text": legacy_text,
        })


def padded_crop_box(
    box: object,
    image_width: int,
    image_height: int,
    padding: int,
) -> tuple[int, int, int, int] | None:
    if not isinstance(box, dict):
        return None
    x, y, width, height = box.get("x"), box.get("y"), box.get("width"), box.get("height")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y, width, height)):
        return None
    left = max(0, int(x) - padding)
    top = max(0, int(y) - padding)
    right = min(image_width, int(x + width) + padding)
    bottom = min(image_height, int(y + height) + padding)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def crop_to_temp_file(image: Image.Image, crop_box: tuple[int, int, int, int], prefix: str) -> Path:
    import tempfile

    fd, path_str = tempfile.mkstemp(prefix=f"crossval_{safe_filename(prefix)}_", suffix=".png")
    import os

    os.close(fd)
    crop_path = Path(path_str)
    image.crop(crop_box).save(crop_path)
    return crop_path


def safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def find_page_image(images_dir: Path, page_id: str) -> Path | None:
    candidates = sorted(images_dir.glob(f"*_{page_id}.png"))
    if not candidates:
        candidates = sorted(images_dir.glob(f"*{page_id}*.png"))
    return candidates[0].resolve() if candidates else None
