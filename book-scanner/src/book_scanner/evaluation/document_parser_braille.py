"""Downstream Page IR and braille evaluation for corrected page images.

The production accessibility presenter intentionally emits braille only for
math spans and table cells.  Plain OCR text is therefore tracked as preserved
content, but is never counted as a failed braille translation.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


def _cells_payload(cells: list[frozenset[int]]) -> dict[str, object]:
    from document_parser.accessibility.braille.viewport import cell_to_int

    packed = [cell_to_int(cell) for cell in cells]
    return {
        "cells": packed,
        "unicode": "".join(chr(0x2800 + value) for value in packed),
        "cell_count": len(packed),
    }


def _translation_record(
    source_id: str,
    source_kind: str,
    translate,
    ast_status: object = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "source_id": source_id,
        "source_kind": source_kind,
        "ast_status": ast_status,
    }
    try:
        record.update(_cells_payload(translate()))
        record["status"] = "TRANSLATED" if record["cell_count"] else "WITHHELD"
        record["error"] = None
    except Exception as exc:  # Translator intentionally raises on unverified notation.
        record.update({
            "status": "ERROR",
            "cells": [],
            "unicode": "",
            "cell_count": 0,
            "error": f"{type(exc).__name__}: {exc}",
        })
    return record


def evaluate_page_ir_braille(page_ir: dict[str, object]) -> dict[str, object]:
    """Run the same flattener/translators used by the production session.

    This stops before TTS synthesis and hardware transmission.  It records all
    braille opportunities, including deliberately withheld PARTIAL/INVALID ASTs
    and unsupported-notation exceptions, rather than hiding them.
    """
    from document_parser.accessibility.braille import braille_scrollable_spans
    from document_parser.accessibility.braille.math_translator import math_focus_item_to_braille
    from document_parser.accessibility.braille.table_formatter import table_cell_braille
    from document_parser.accessibility.flattening import flatten_document

    document = flatten_document(page_ir)
    node_types: Counter[str] = Counter()
    parse_issue_codes: Counter[str] = Counter()
    preserved_fragments: list[str] = []
    for page in page_ir.get("pages", []):
        if not isinstance(page, dict):
            continue
        for issue in page.get("parse_issues", []):
            if isinstance(issue, dict):
                parse_issue_codes[str(issue.get("code") or "UNSPECIFIED")] += 1
        for node in page.get("nodes", []):
            if not isinstance(node, dict):
                continue
            node_types[str(node.get("content_type") or "UNKNOWN")] += 1
            if node.get("content_type") == "TABLE":
                for cell in node.get("cells", []):
                    if not isinstance(cell, dict):
                        continue
                    for content_node in cell.get("content_nodes", []):
                        if isinstance(content_node, dict):
                            preserved_fragments.append(str(
                                content_node.get("normalized_text")
                                or content_node.get("raw_text")
                                or content_node.get("raw_formula")
                                or ""
                            ))
            else:
                preserved_fragments.append(str(
                    node.get("normalized_text") or node.get("raw_text") or node.get("raw_formula") or ""
                ))

    translations: list[dict[str, object]] = []
    focus_count = 0
    for page in document.get("pages", []):
        if not isinstance(page, dict):
            continue
        for item in page.get("focus_items", []):
            if not isinstance(item, dict):
                continue
            focus_count += 1
            source_id = str(item.get("id") or "focus")
            for span_index, span in enumerate(braille_scrollable_spans(item)):
                translations.append(_translation_record(
                    f"{source_id}#{span_index}",
                    "MATH_SPAN",
                    lambda span=span: math_focus_item_to_braille(span),
                    span.get("ast_status"),
                ))
            if item.get("kind") == "TABLE":
                for cell in item.get("cells", []):
                    if not isinstance(cell, dict):
                        continue
                    translations.append(_translation_record(
                        str(cell.get("id") or f"{source_id}:cell"),
                        "TABLE_CELL",
                        lambda cell=cell: table_cell_braille(cell),
                    ))

    statuses = Counter(str(record["status"]) for record in translations)
    translated = statuses["TRANSLATED"]
    opportunities = len(translations)
    validation = page_ir.get("validation_summary")
    schema_valid = bool(validation.get("schema_valid")) if isinstance(validation, dict) else False
    return {
        "schema_valid": schema_valid,
        "validation_summary": validation if isinstance(validation, dict) else {},
        "page_count": len(document.get("pages", [])),
        "focus_item_count": focus_count,
        "node_type_counts": dict(sorted(node_types.items())),
        "preserved_text_character_count": sum(
            not char.isspace() for fragment in preserved_fragments for char in fragment
        ),
        "normalized_content_text": re.sub(r"\s+", "", "\n".join(preserved_fragments)).casefold(),
        "parse_issue_codes": dict(sorted(parse_issue_codes.items())),
        "parse_issue_count": sum(parse_issue_codes.values()),
        "braille_opportunity_count": opportunities,
        "braille_translated_count": translated,
        "braille_withheld_count": statuses["WITHHELD"],
        "braille_error_count": statuses["ERROR"],
        "braille_translation_rate": translated / opportunities if opportunities else None,
        "translations": translations,
    }


def compare_braille_evaluations(
    candidate: dict[str, object],
    reference: dict[str, object],
    *,
    same_content: bool = False,
) -> dict[str, object]:
    """Compare pipeline health; only compare cell sequences for the same text."""
    candidate_opportunities = int(candidate.get("braille_opportunity_count", 0))
    reference_opportunities = int(reference.get("braille_opportunity_count", 0))
    candidate_rate = candidate.get("braille_translation_rate")
    reference_rate = reference.get("braille_translation_rate")

    if not candidate.get("schema_valid"):
        verdict = "FAIL_INVALID_PAGE_IR"
    elif int(candidate.get("braille_error_count", 0)) > 0:
        verdict = "FAIL_TRANSLATION_ERROR"
    elif candidate_opportunities == 0:
        verdict = "NOT_APPLICABLE_NO_BRAILLE_CONTENT"
    elif candidate_rate is None or reference_rate is None:
        verdict = "INCONCLUSIVE"
    elif float(candidate_rate) + 0.05 < float(reference_rate):
        verdict = "BELOW_REFERENCE_PIPELINE_HEALTH"
    else:
        verdict = "SIMILAR_PIPELINE_HEALTH"

    result: dict[str, object] = {
        "verdict": verdict,
        "same_content": same_content,
        "cell_similarity": None,
        "candidate_braille_opportunity_count": candidate_opportunities,
        "reference_braille_opportunity_count": reference_opportunities,
        "translation_rate_delta": (
            float(candidate_rate) - float(reference_rate)
            if candidate_rate is not None and reference_rate is not None
            else None
        ),
        "note": (
            "Different source content: schema/translation coverage is comparable, exact braille cells are not."
            if not same_content
            else "Same source content: exact translated cell sequence was compared."
        ),
    }
    if same_content:
        candidate_cells = _flatten_packed_cells(candidate)
        reference_cells = _flatten_packed_cells(reference)
        result["cell_similarity"] = SequenceMatcher(None, candidate_cells, reference_cells).ratio()
    return result


def page_ir_sha256(page_ir: dict[str, object]) -> str:
    canonical = json.dumps(page_ir, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_and_evaluate_page_ir(path: Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    result = evaluate_page_ir_braille(payload)
    result["page_ir_path"] = str(Path(path).resolve())
    result["page_ir_sha256"] = page_ir_sha256(payload)
    return result


def _flatten_packed_cells(evaluation: dict[str, object]) -> list[int]:
    cells: list[int] = []
    for record in evaluation.get("translations", []):
        if isinstance(record, dict):
            cells.extend(int(value) for value in record.get("cells", []))
    return cells
