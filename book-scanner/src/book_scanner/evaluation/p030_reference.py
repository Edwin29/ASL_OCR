"""Human-verified golden comparison for the photographed EBS Math I p30 page.

The committed p030 fixture was directly reviewed by a person during the
Document Parser development process.  It is therefore the golden reference for
this exact printed p30 source.  That status does not generalize to other pages.
"""

from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from typing import Any

from book_scanner.evaluation.document_parser_braille import compare_braille_evaluations
from book_scanner.evaluation.paired_page_ir import evaluate_paired_page_ir


EXPECTED_PROBLEM_CODES = tuple(f"26008-{number:04d}" for number in range(42, 46))
EXPECTED_PROBLEM_ORDER = (1, 2, 3, 4)
P030_REFERENCE_IS_HUMAN_GOLDEN = True
P030_ABSOLUTE_ACCURACY_CLAIM_ALLOWED = True
P030_GOLDEN_PROVENANCE = "human_verified_during_document_parser_development"
P030_GOLDEN_SCOPE = "exact_printed_p30_fixture_text_structure_and_braille"


def normalize_reference_text(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _canonical_math_signature(span: dict[str, object]) -> str:
    ast = span.get("presentation_ast")
    if ast is not None:
        return json.dumps(ast, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"text:{normalize_reference_text(span.get('text'))}"


def extract_math_braille_spans(page_ir: dict[str, object]) -> list[dict[str, object]]:
    """Extract ordered math spans and the exact production braille cells."""
    from document_parser.accessibility.braille import braille_scrollable_spans
    from document_parser.accessibility.braille.math_translator import math_focus_item_to_braille
    from document_parser.accessibility.braille.viewport import cell_to_int
    from document_parser.accessibility.flattening import flatten_document

    records: list[dict[str, object]] = []
    document = flatten_document(page_ir)
    for page in document.get("pages", []):
        if not isinstance(page, dict):
            continue
        for item in page.get("focus_items", []):
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("id") or "focus")
            for span_index, span in enumerate(braille_scrollable_spans(item)):
                if not isinstance(span, dict):
                    continue
                signature = _canonical_math_signature(span)
                record: dict[str, object] = {
                    "ordinal": len(records),
                    "source_id": source_id,
                    "span_index": span_index,
                    "text": str(span.get("text") or ""),
                    "normalized_text": normalize_reference_text(span.get("text")),
                    "ast_status": span.get("ast_status"),
                    "canonical_ast_sha256": hashlib.sha256(signature.encode("utf-8")).hexdigest(),
                    "_canonical_signature": signature,
                }
                try:
                    cells = [cell_to_int(cell) for cell in math_focus_item_to_braille(span)]
                    record.update({
                        "status": "TRANSLATED" if cells else "WITHHELD",
                        "cells": cells,
                        "unicode": "".join(chr(0x2800 + cell) for cell in cells),
                        "cell_count": len(cells),
                        "error": None,
                    })
                except Exception as exc:  # Keep the production translator failure visible.
                    record.update({
                        "status": "ERROR",
                        "cells": [],
                        "unicode": "",
                        "cell_count": 0,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                records.append(record)
    return records


def _public_span(record: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in record.items() if not key.startswith("_")}


def compare_p030_math_braille_alignment(
    candidate_page_ir: dict[str, object],
    reference_page_ir: dict[str, object],
) -> dict[str, object]:
    """Separate golden-common math cells from candidate-only math promotions."""
    candidate_spans = extract_math_braille_spans(candidate_page_ir)
    reference_spans = extract_math_braille_spans(reference_page_ir)
    candidate_signatures = [str(item["_canonical_signature"]) for item in candidate_spans]
    reference_signatures = [str(item["_canonical_signature"]) for item in reference_spans]
    matcher = SequenceMatcher(None, reference_signatures, candidate_signatures, autojunk=False)

    common_pairs: list[dict[str, object]] = []
    reference_only: list[dict[str, object]] = []
    candidate_added: list[dict[str, object]] = []
    reference_plain_text = normalize_reference_text(
        "\n".join(_node_text(node) for node in _all_nodes(reference_page_ir))
    )

    for tag, ref_start, ref_end, cand_start, cand_end in matcher.get_opcodes():
        if tag == "equal":
            for reference, candidate in zip(
                reference_spans[ref_start:ref_end],
                candidate_spans[cand_start:cand_end],
                strict=True,
            ):
                reference_cells = list(reference.get("cells", []))
                candidate_cells = list(candidate.get("cells", []))
                common_pairs.append({
                    "reference": _public_span(reference),
                    "candidate": _public_span(candidate),
                    "cells_exact": reference_cells == candidate_cells,
                    "cell_similarity": SequenceMatcher(
                        None, reference_cells, candidate_cells, autojunk=False
                    ).ratio(),
                })
        if tag in {"delete", "replace"}:
            reference_only.extend(_public_span(item) for item in reference_spans[ref_start:ref_end])
        if tag in {"insert", "replace"}:
            for item in candidate_spans[cand_start:cand_end]:
                public = _public_span(item)
                normalized = str(public.get("normalized_text") or "")
                public["present_in_reference_plain_text"] = bool(
                    normalized and normalized in reference_plain_text
                )
                candidate_added.append(public)

    common_reference_cells = [
        cell for pair in common_pairs for cell in pair["reference"].get("cells", [])
    ]
    common_candidate_cells = [
        cell for pair in common_pairs for cell in pair["candidate"].get("cells", [])
    ]
    reference_cell_count = sum(int(item.get("cell_count", 0)) for item in reference_spans)
    candidate_cell_count = sum(int(item.get("cell_count", 0)) for item in candidate_spans)
    added_plain_text_count = sum(
        bool(item.get("present_in_reference_plain_text")) for item in candidate_added
    )
    added_plain_text_cells = sum(
        int(item.get("cell_count", 0))
        for item in candidate_added
        if item.get("present_in_reference_plain_text")
    )
    common_similarity = (
        SequenceMatcher(
            None, common_reference_cells, common_candidate_cells, autojunk=False
        ).ratio()
        if common_reference_cells or common_candidate_cells else None
    )
    exact_common = sum(bool(pair["cells_exact"]) for pair in common_pairs)
    if reference_only or common_similarity != 1.0:
        verdict = "GOLDEN_COMMON_REGRESSION_OR_MISSING_SPANS"
    elif not candidate_added:
        verdict = "EXACT_GOLDEN_MATH_CELLS"
    elif added_plain_text_count == len(candidate_added):
        verdict = "GOLDEN_COMMON_EXACT_WITH_REFERENCE_PLAIN_TEXT_PROMOTIONS"
    else:
        verdict = "GOLDEN_COMMON_EXACT_WITH_UNVERIFIED_ADDITIONS"

    return {
        "alignment_method": "ordered_canonical_presentation_ast",
        "reference_is_human_golden": P030_REFERENCE_IS_HUMAN_GOLDEN,
        "golden_scope": P030_GOLDEN_SCOPE,
        "reference_span_count": len(reference_spans),
        "reference_cell_count": reference_cell_count,
        "candidate_span_count": len(candidate_spans),
        "candidate_cell_count": candidate_cell_count,
        "common_span_count": len(common_pairs),
        "exact_common_span_count": exact_common,
        "common_span_exact_rate": exact_common / len(common_pairs) if common_pairs else None,
        "common_reference_cell_count": len(common_reference_cells),
        "common_candidate_cell_count": len(common_candidate_cells),
        "common_cell_similarity": common_similarity,
        "reference_span_coverage": (
            len(common_pairs) / len(reference_spans) if reference_spans else None
        ),
        "reference_cell_coverage": (
            len(common_reference_cells) / reference_cell_count if reference_cell_count else None
        ),
        "reference_only_span_count": len(reference_only),
        "reference_only_cell_count": sum(
            int(item.get("cell_count", 0)) for item in reference_only
        ),
        "candidate_added_span_count": len(candidate_added),
        "candidate_added_cell_count": sum(
            int(item.get("cell_count", 0)) for item in candidate_added
        ),
        "candidate_added_present_in_reference_plain_text_count": added_plain_text_count,
        "candidate_added_present_in_reference_plain_text_cell_count": added_plain_text_cells,
        "common_pairs": common_pairs,
        "reference_only_spans": reference_only,
        "candidate_added_spans": candidate_added,
        "verdict": verdict,
    }


def _node_text(node: dict[str, Any]) -> str:
    return str(node.get("normalized_text") or node.get("raw_text") or node.get("raw_formula") or "")


def _all_nodes(page_ir: dict[str, object]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for page in page_ir.get("pages", []):
        if not isinstance(page, dict):
            continue
        nodes.extend(node for node in page.get("nodes", []) if isinstance(node, dict))
    return nodes


def extract_problem_units(page_ir: dict[str, object]) -> list[dict[str, object]]:
    """Extract detected problem-unit structure in reading order."""
    nodes = _all_nodes(page_ir)
    nodes_by_id = {str(node.get("node_id")): node for node in nodes}
    units = [
        node for node in nodes
        if isinstance(node.get("layout"), dict) and node["layout"].get("is_problem_unit") is True
    ]
    units.sort(key=lambda node: (int(node.get("reading_order_index", 1 << 30)), str(node.get("node_id"))))
    records: list[dict[str, object]] = []
    for ordinal, unit in enumerate(units, start=1):
        layout = unit.get("layout") if isinstance(unit.get("layout"), dict) else {}
        embedded = [
            nodes_by_id[node_id] for node_id in map(str, unit.get("embedded_text_nodes", []))
            if node_id in nodes_by_id
        ]
        marker_node = nodes_by_id.get(str(layout.get("problem_marker_node_id")))
        marker_text = _node_text(marker_node) if marker_node else ""
        combined = "\n".join(_node_text(node) for node in embedded)
        stem_text = str(layout.get("stem_text") or combined)
        choice_text = str(layout.get("choice_raw_text") or "")
        choices = layout.get("choice_options") if isinstance(layout.get("choice_options"), list) else []
        number_match = re.match(r"\s*([1-4])(?:\D|$)", stem_text)
        code_match = re.search(r"26008[-–]?00(4[2-5])", marker_text + "\n" + combined)
        code = f"26008-00{code_match.group(1)}" if code_match else None
        records.append({
            "ordinal": ordinal,
            "problem_number": int(number_match.group(1)) if number_match else None,
            "problem_code": code,
            "stem_text": stem_text,
            "choice_text": choice_text,
            "choice_count": len(choices),
            "normalized_text": normalize_reference_text(combined or stem_text + choice_text),
        })
    return records


def p030_anchor_diagnostics(page_ir: dict[str, object]) -> dict[str, object]:
    nodes = _all_nodes(page_ir)
    texts = [_node_text(node) for node in nodes]
    compact = normalize_reference_text("\n".join(texts))
    units = extract_problem_units(page_ir)
    problem_order = [unit["problem_number"] for unit in units]
    codes = {
        code for code in EXPECTED_PROBLEM_CODES
        if normalize_reference_text(code) in compact
    }
    return {
        "page_number_30_exact_node": any(normalize_reference_text(text) == "30" for text in texts),
        "problem_order": problem_order,
        "problem_order_complete": problem_order == list(EXPECTED_PROBLEM_ORDER),
        "problem_unit_count": len(units),
        "problem_codes_found": sorted(codes),
        "problem_codes_complete": len(codes) == len(EXPECTED_PROBLEM_CODES),
        "choice_counts": [int(unit["choice_count"]) for unit in units],
        "all_problem_units_have_choices": len(units) == 4 and all(int(unit["choice_count"]) > 0 for unit in units),
    }


def compare_p030_page_ir(
    candidate_page_ir: dict[str, object],
    reference_page_ir: dict[str, object],
) -> dict[str, object]:
    """Compare a photographed p30 Page IR with the committed same-source fixture."""
    candidate = evaluate_paired_page_ir(candidate_page_ir)
    reference = evaluate_paired_page_ir(reference_page_ir)
    candidate_units = extract_problem_units(candidate_page_ir)
    reference_units = extract_problem_units(reference_page_ir)
    problem_comparisons: list[dict[str, object]] = []
    for index in range(max(len(candidate_units), len(reference_units))):
        candidate_unit = candidate_units[index] if index < len(candidate_units) else None
        reference_unit = reference_units[index] if index < len(reference_units) else None
        problem_comparisons.append({
            "ordinal": index + 1,
            "candidate_present": candidate_unit is not None,
            "reference_present": reference_unit is not None,
            "candidate_problem_number": candidate_unit.get("problem_number") if candidate_unit else None,
            "reference_problem_number": reference_unit.get("problem_number") if reference_unit else None,
            "candidate_choice_count": candidate_unit.get("choice_count") if candidate_unit else 0,
            "reference_choice_count": reference_unit.get("choice_count") if reference_unit else 0,
            "text_similarity": (
                SequenceMatcher(
                    None,
                    str(reference_unit.get("normalized_text", "")),
                    str(candidate_unit.get("normalized_text", "")),
                ).ratio()
                if candidate_unit and reference_unit else 0.0
            ),
        })

    anchors = p030_anchor_diagnostics(candidate_page_ir)
    reference_anchors = p030_anchor_diagnostics(reference_page_ir)
    braille = compare_braille_evaluations(candidate, reference, same_content=True)
    math_braille_alignment = compare_p030_math_braille_alignment(
        candidate_page_ir, reference_page_ir
    )
    hard_gate = bool(
        candidate.get("schema_valid")
        and anchors["problem_order_complete"]
        and anchors["all_problem_units_have_choices"]
        and int(candidate.get("braille_error_count", 0)) <= int(reference.get("braille_error_count", 0))
    )
    return {
        "comparison_kind": "same_printed_source_human_verified_golden",
        "reference_is_human_golden": P030_REFERENCE_IS_HUMAN_GOLDEN,
        "absolute_accuracy_claim_allowed": P030_ABSOLUTE_ACCURACY_CLAIM_ALLOWED,
        "golden_provenance": P030_GOLDEN_PROVENANCE,
        "golden_scope": P030_GOLDEN_SCOPE,
        "schema_valid": bool(candidate.get("schema_valid")),
        "overall_text_similarity": SequenceMatcher(
            None,
            str(reference.get("normalized_content_text", "")),
            str(candidate.get("normalized_content_text", "")),
        ).ratio(),
        "character_count": int(candidate.get("preserved_text_character_count", 0)),
        "reference_character_count": int(reference.get("preserved_text_character_count", 0)),
        "node_type_sequence": list(candidate.get("node_type_sequence", [])),
        "reference_node_type_sequence": list(reference.get("node_type_sequence", [])),
        "parse_issue_count": int(candidate.get("parse_issue_count", 0)),
        "reference_parse_issue_count": int(reference.get("parse_issue_count", 0)),
        "braille": braille,
        "math_braille_alignment": math_braille_alignment,
        "candidate_braille_error_count": int(candidate.get("braille_error_count", 0)),
        "reference_braille_error_count": int(reference.get("braille_error_count", 0)),
        "anchors": anchors,
        "reference_anchors": reference_anchors,
        "problem_comparisons": problem_comparisons,
        "hard_gate_passed": hard_gate,
        "verdict": "P030_NO_CLEAR_REGRESSION" if hard_gate else "P030_HARD_REGRESSION_OR_OMISSION",
    }


def select_uvdoc_postprocess_sources(
    results: list[dict[str, object]],
    *,
    max_sources: int = 3,
) -> list[str]:
    """Select only UVDoc artifacts with a predeclared regression signal."""
    grouped: dict[tuple[str, str], dict[str, dict[str, object]]] = {}
    for item in results:
        if item.get("status") != "COMPLETE" or not isinstance(item.get("comparison"), dict):
            continue
        key = (str(item.get("capture")), str(item.get("extraction")))
        grouped.setdefault(key, {})[str(item.get("geometry"))] = item

    candidates: list[tuple[float, str]] = []
    for variants in grouped.values():
        control = variants.get("none")
        uvdoc = variants.get("uvdoc_bilinear")
        if not control or not uvdoc:
            continue
        control_comparison = control["comparison"]
        uvdoc_comparison = uvdoc["comparison"]
        control_text = float(control_comparison.get("overall_text_similarity", 0.0))
        uvdoc_text = float(uvdoc_comparison.get("overall_text_similarity", 0.0))
        control_cells = control_comparison.get("braille", {}).get("cell_similarity")
        uvdoc_cells = uvdoc_comparison.get("braille", {}).get("cell_similarity")
        cell_drop = (
            float(control_cells) - float(uvdoc_cells)
            if control_cells is not None and uvdoc_cells is not None else 0.0
        )
        error_increase = int(uvdoc_comparison.get("candidate_braille_error_count", 0)) - int(
            control_comparison.get("candidate_braille_error_count", 0)
        )
        hard_regression = bool(control_comparison.get("hard_gate_passed")) and not bool(
            uvdoc_comparison.get("hard_gate_passed")
        )
        text_drop = control_text - uvdoc_text
        if hard_regression or text_drop > 0.02 or cell_drop > 0.05 or error_increase > 0:
            severity = (1.0 if hard_regression else 0.0) + max(0.0, text_drop) + max(0.0, cell_drop)
            severity += max(0, error_increase)
            candidates.append((severity, str(uvdoc["artifact_id"])))
    candidates.sort(key=lambda pair: (-pair[0], pair[1]))
    return [identifier for _severity, identifier in candidates[:max_sources]]
