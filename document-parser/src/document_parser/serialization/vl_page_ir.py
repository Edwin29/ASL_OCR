"""Build Page IR directly from PaddleOCR-VL's structured block output.

This bypasses the token-boundary pipeline (LayoutBuilder -> math candidates ->
math spans -> structure regions -> promotion) entirely, because PaddleOCR-VL
already returns text/formula/table/image separated into blocks with reading
order. That pipeline exists specifically to reconstruct structure a flat OCR
token stream does not have; PaddleOCR-VL does not have that problem, so
reapplying it here would throw away information instead of recovering it.

What this module does NOT do (kept deliberately conservative for this first
integration pass):
- Parse table HTML into row/col/cell TABLE IR structure (the HTML is preserved
  as-is in `raw_html`; row/col reconstruction is a follow-up).
- Auto-correct the two known failure modes documented in
  `document_parser.ocr.paddleocr_vl_adapter` (silent omission, problem-number
  prefix merging). Both are flagged as explicit issues instead, per this
  project's rule that ambiguous content is never silently dropped or "fixed".
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from document_parser.math.latex_ast import parse_latex_to_ast
from document_parser.serialization.table_html import build_table_ir

CHOICE_MARKER_PATTERN = re.compile(r"[①②③④⑤]")
EXPECTED_CHOICE_COUNT = 5

# A block is a plausible multiple-choice line if markers are present at all but
# short of the standard 5, which is the exact shape of the silent-omission
# failure verified on this project's own data (a value or choice dropped with no
# other signal).
#
# The problem-number prefix merge does NOT glue digit-to-letter with zero space
# (verified real case: "1" + "4 이하의..." -> "14 이하의...", note the space is
# still there between "14" and "이하의"). The signature is a bare leading
# integer followed by whitespace at the very start of the block, before any
# other content -- legitimate stems in this corpus consistently open with a noun
# phrase ("함수", "두 실수", "실수 a"...), never a cold bare number.
PROBLEM_NUMBER_PREFIX_PATTERN = re.compile(r"^\d+\s")

INLINE_MATH_PATTERN = re.compile(r"\${1,2}(.+?)\${1,2}", re.DOTALL)

# Block labels that are page furniture rather than primary content, but should
# still be preserved for TTS per the project's "no silent drops" principle --
# they just sort to the top/bottom since PaddleOCR-VL gives them no reading-order
# index.
HEADER_LABELS = {"header", "header_image"}
FOOTER_LABELS = {"footer", "number"}
VISUAL_LABELS = {"image", "chart", "figure"}
FORMULA_LABELS = {"display_formula", "formula", "equation"}
TABLE_LABELS = {"table"}


def build_document_ir_from_vl(
    image_paths: list[Path],
    adapter: Any,
    book_id: str,
) -> dict[str, object]:
    """Build a full document Page IR using PaddleOCR-VL as the baseline engine.

    This is the project's default page-parsing path (promoted over the token
    pipeline in `document_parser.serialization.text_ir`): PaddleOCR-VL resolves
    text/formula/table/image separation and reading order directly, which the
    token pipeline exists only to approximate from a flat OCR token stream.
    """
    from document_parser.structure.problem_units import detect_problem_units_in_document
    from document_parser.validation import validate_document_ir

    pages = []
    for image_path in sorted(image_paths):
        page_id = page_id_from_path(image_path)
        vl_result = adapter.parse_page(image_path)
        pages.append(build_page_ir_from_vl_result(vl_result, page_id=page_id))

    payload: dict[str, object] = {
        "document_manifest": {"book_id": book_id, "page_count": len(pages)},
        "engine_manifest": {
            "general_ocr": {"engine_id": adapter.engine_id, "engine_version": adapter.engine_version},
            "pipeline": {"mode": "paddleocr_vl_baseline"},
        },
        "pages": pages,
        "validation_summary": {},
    }
    # Group each problem's stem/condition/보기/선택지 lines into one PROBLEM_UNIT
    # node so downstream TTS/braille consumers get problem structure directly,
    # instead of a flat sequence of same-looking TEXT blocks.
    payload = detect_problem_units_in_document(payload)
    payload["validation_summary"] = validate_document_ir(payload)
    return payload


def page_id_from_path(path: Path, fallback_index: int = 1) -> str:
    match = re.search(r"(?:^|[_-])p(\d{1,4})(?:$|[_-])", path.stem)
    if match:
        return f"p{int(match.group(1)):03d}"
    return f"p{fallback_index:03d}"


def build_page_ir_from_vl_result(
    vl_result: dict[str, Any],
    page_id: str,
    source_engine: str = "paddleocr-vl",
) -> dict[str, object]:
    blocks = vl_result.get("parsing_res_list") or []
    page_width = number_value(vl_result.get("width")) or 1.0
    page_height = number_value(vl_result.get("height")) or 1.0

    ordered_blocks = [b for b in blocks if isinstance(b, dict) and b.get("block_order") is not None]
    ordered_blocks.sort(key=lambda b: b["block_order"])
    header_blocks = sorted(
        (b for b in blocks if isinstance(b, dict) and b.get("block_order") is None and b.get("block_label") in HEADER_LABELS),
        key=lambda b: bbox_from_corners(b.get("block_bbox"))["y"] if bbox_from_corners(b.get("block_bbox")) else 0.0,
    )
    footer_blocks = sorted(
        (b for b in blocks if isinstance(b, dict) and b.get("block_order") is None and b.get("block_label") in FOOTER_LABELS),
        key=lambda b: bbox_from_corners(b.get("block_bbox"))["y"] if bbox_from_corners(b.get("block_bbox")) else 0.0,
    )
    other_unordered = [
        b for b in blocks
        if isinstance(b, dict)
        and b.get("block_order") is None
        and b.get("block_label") not in HEADER_LABELS
        and b.get("block_label") not in FOOTER_LABELS
    ]

    all_blocks = header_blocks + ordered_blocks + other_unordered + footer_blocks

    nodes: list[dict[str, object]] = []
    reading_order: list[str] = []
    next_index = 1
    for block in all_blocks:
        node = node_from_block(block, page_id, next_index, page_width, page_height, source_engine)
        if node is None:
            continue
        nodes.append(node)
        reading_order.append(node["node_id"])
        next_index += 1

    return {
        "page_id": page_id,
        "page_geometry": {"width": int(page_width), "height": int(page_height)},
        "nodes": nodes,
        "reading_order": reading_order,
        "parse_issues": [],
        "quality_report": {"status": "PASS_WITH_CORRECTION", "issues": []},
    }


def node_from_block(
    block: dict[str, Any],
    page_id: str,
    index: int,
    page_width: float,
    page_height: float,
    source_engine: str,
) -> dict[str, object] | None:
    label = block.get("block_label")
    content = str(block.get("block_content", ""))
    corners = block.get("block_bbox")
    box = bbox_from_corners(corners)
    if box is None:
        return None
    node_id = f"{page_id}-vl{index:03d}"

    base = {
        "node_id": node_id,
        "bbox": box,
        "normalized_bbox": normalize_bbox(box, page_width, page_height),
        "reading_order_index": index - 1,
        "confidence": 1.0,
        "source_engine": source_engine,
        "issues": [],
        "layout": {"vl_block_label": label, "vl_block_id": block.get("block_id")},
    }

    if label in TABLE_LABELS:
        def build_cell_content_nodes(cell_text: str, node_id_prefix: str, cell_bbox: dict[str, float]) -> list[dict[str, object]]:
            return content_nodes_from_cell_text(cell_text, node_id_prefix, cell_bbox, page_width, page_height, source_engine)

        table_ir = build_table_ir(content, table_bbox=box, node_id_prefix=node_id, content_node_builder=build_cell_content_nodes)
        table_issues = list(base["issues"])
        if table_ir["structure_confidence"] < 0.8:
            table_issues.append({
                "code": "VL_TABLE_STRUCTURE_LOW_CONFIDENCE",
                "severity": "warning",
                "message": "Parsed table rows do not form a clean rectangular grid; row/column assignment may be off.",
            })
        return {
            **base,
            "content_type": "TABLE",
            "raw_html": content,
            "row_count": table_ir["row_count"],
            "column_count": table_ir["column_count"],
            "cells": table_ir["cells"],
            "structure_confidence": table_ir["structure_confidence"],
            "issues": table_issues,
        }

    if label in FORMULA_LABELS:
        raw_formula = strip_math_delimiters(content)
        parsed = parse_latex_to_ast(raw_formula)
        return {
            **base,
            "content_type": "MATH",
            "raw_formula": raw_formula,
            "formula_format": "LATEX",
            "presentation_ast": parsed.ast,
            "unconsumed_tokens": parsed.unconsumed_tokens,
            "issues": list(base["issues"]) + parsed.issues,
        }

    if label in VISUAL_LABELS:
        embedded_content_nodes = (
            content_nodes_from_cell_text(content, f"{node_id}-embedded", box, page_width, page_height, source_engine)
            if content.strip()
            else []
        )
        return {
            **base,
            "content_type": "UNSUPPORTED_VISUAL",
            "visual_type_candidate": "GRAPH_OR_DIAGRAM",
            # Only claim text preservation when there is actually text to preserve.
            # PaddleOCR-VL's image-block OCR (`use_ocr_for_image_block`) is what
            # makes this non-empty at all; verified on p004, off by default in the
            # underlying library it returns "" for every graph, which is a real
            # silent-loss risk this project explicitly rules out (기획서 §15.3).
            "handling": "ANNOUNCE_AND_PRESERVE_TEXT" if embedded_content_nodes else "ANNOUNCE_ONLY_NO_TEXT_CAPTURED",
            "embedded_content_nodes": embedded_content_nodes,
        }

    # Everything else (text, paragraph_title, header, footer, number) is TEXT.
    text_node = {
        **base,
        "content_type": "TEXT",
        "raw_text": content,
        "normalized_text": content,
        "spans": spans_from_inline_math(content),
    }
    text_node["issues"] = list(base["issues"]) + completeness_issues(content, label)
    return text_node


def spans_from_inline_math(content: str) -> list[dict[str, object]]:
    spans: list[dict[str, object]] = []
    last_end = 0
    for match in INLINE_MATH_PATTERN.finditer(content):
        if match.start() > last_end:
            spans.append({"span_type": "TEXT", "text": content[last_end:match.start()]})
        formula_text = match.group(1).strip()
        parsed = parse_latex_to_ast(formula_text)
        spans.append({
            "span_type": "UNKNOWN",
            "text": formula_text,
            "math_span_candidate": True,
            "presentation_ast": parsed.ast,
            "unconsumed_tokens": parsed.unconsumed_tokens,
            "ast_issues": parsed.issues,
        })
        last_end = match.end()
    if last_end < len(content):
        spans.append({"span_type": "TEXT", "text": content[last_end:]})
    if not spans:
        spans.append({"span_type": "TEXT", "text": content})
    return spans


def content_nodes_from_cell_text(
    cell_text: str,
    node_id_prefix: str,
    cell_bbox: dict[str, float],
    page_width: float,
    page_height: float,
    source_engine: str,
) -> list[dict[str, object]]:
    """Split a table cell's text into TEXT/MATH content nodes for `cells[].content_nodes`.

    Reuses the same inline-math splitting used for body text (`$...$` delimited
    math is common in table cells, verified on p004's real table), so a cell
    like "$ \\sqrt[n]{a} $" becomes a MATH node with a parsed `presentation_ast`
    instead of an opaque string. No finer-grained coordinates exist inside a
    table cell, so every content node in a cell shares that cell's bbox.
    """
    nodes: list[dict[str, object]] = []
    last_end = 0
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"{node_id_prefix}-{counter:02d}"

    for match in INLINE_MATH_PATTERN.finditer(cell_text):
        plain = cell_text[last_end:match.start()].strip()
        if plain:
            nodes.append(_cell_text_node(next_id(), plain, cell_bbox, page_width, page_height, source_engine))
        formula_text = match.group(1).strip()
        nodes.append(_cell_math_node(next_id(), formula_text, cell_bbox, page_width, page_height, source_engine))
        last_end = match.end()
    remaining = cell_text[last_end:].strip()
    if remaining:
        nodes.append(_cell_text_node(next_id(), remaining, cell_bbox, page_width, page_height, source_engine))
    return nodes


def _cell_text_node(
    node_id: str, text: str, bbox: dict[str, float], page_width: float, page_height: float, source_engine: str
) -> dict[str, object]:
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": bbox,
        "normalized_bbox": normalize_bbox(bbox, page_width, page_height),
        "confidence": 1.0,
        "source_engine": source_engine,
        "issues": [],
        "raw_text": text,
        "normalized_text": text,
        "spans": [{"span_type": "TEXT", "text": text}],
    }


def _cell_math_node(
    node_id: str, formula_text: str, bbox: dict[str, float], page_width: float, page_height: float, source_engine: str
) -> dict[str, object]:
    parsed = parse_latex_to_ast(formula_text)
    return {
        "node_id": node_id,
        "content_type": "MATH",
        "bbox": bbox,
        "normalized_bbox": normalize_bbox(bbox, page_width, page_height),
        "confidence": 1.0,
        "source_engine": source_engine,
        "issues": parsed.issues,
        "raw_formula": formula_text,
        "formula_format": "LATEX",
        "presentation_ast": parsed.ast,
        "unconsumed_tokens": parsed.unconsumed_tokens,
    }


def completeness_issues(content: str, label: str | None) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    marker_count = len(set(CHOICE_MARKER_PATTERN.findall(content)))
    # A block with exactly one marker is almost always a single numbered property
    # or worked-example item spread across its own block (verified on p004: the
    # "거듭제곱근의 성질" list has one marker per block across 6 blocks), not a
    # partial choice row. Genuine choice rows in this corpus always print several
    # markers bunched on one line, so a real omission still leaves at least 2.
    if 1 < marker_count < EXPECTED_CHOICE_COUNT:
        issues.append({
            "code": "VL_POSSIBLE_CHOICE_OMISSION",
            "severity": "warning",
            "message": (
                f"Found {marker_count} of {EXPECTED_CHOICE_COUNT} expected circled-number choice markers. "
                "PaddleOCR-VL has a verified failure mode of silently dropping a value or choice with no "
                "other signal; this block should be reviewed against the source image before trusting it."
            ),
        })
    if label == "text" and PROBLEM_NUMBER_PREFIX_PATTERN.match(content.lstrip("\n")):
        issues.append({
            "code": "VL_POSSIBLE_PROBLEM_NUMBER_PREFIX",
            "severity": "warning",
            "message": (
                "Block starts with a bare digit directly touching the next character. PaddleOCR-VL "
                "inconsistently merges the left-margin problem-number glyph into the stem text instead of "
                "keeping it as a separate block (verified: \"1\" + \"4 이하의...\" -> \"14 이하의...\"). "
                "This may be a real leading digit or a merged problem number; not auto-corrected."
            ),
        })
    return issues


def strip_math_delimiters(content: str) -> str:
    stripped = content.strip()
    for delimiter in ("$$", "$"):
        if stripped.startswith(delimiter) and stripped.endswith(delimiter) and len(stripped) >= 2 * len(delimiter):
            return stripped[len(delimiter):-len(delimiter)].strip()
    return stripped


def bbox_from_corners(corners: object) -> dict[str, float] | None:
    if not isinstance(corners, (list, tuple)) or len(corners) != 4:
        return None
    values = [number_value(v) for v in corners]
    if any(v is None for v in values):
        return None
    x0, y0, x1, y1 = values
    return {"x": round(x0, 3), "y": round(y0, 3), "width": round(x1 - x0, 3), "height": round(y1 - y0, 3)}


def normalize_bbox(box: dict[str, float], page_width: float, page_height: float) -> dict[str, float]:
    if page_width <= 0 or page_height <= 0:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    return {
        "x": round(box["x"] / page_width, 6),
        "y": round(box["y"] / page_height, 6),
        "width": round(box["width"] / page_width, 6),
        "height": round(box["height"] / page_height, 6),
    }


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
