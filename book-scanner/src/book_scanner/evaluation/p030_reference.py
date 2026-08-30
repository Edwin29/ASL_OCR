"""Same-source regression comparison for the photographed EBS Math I p30 page.

The committed p030 fixture is a pipeline regression reference, not a human
transcription.  These helpers therefore report reproducibility and omissions
without claiming absolute OCR accuracy.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from book_scanner.evaluation.document_parser_braille import compare_braille_evaluations
from book_scanner.evaluation.paired_page_ir import evaluate_paired_page_ir


EXPECTED_PROBLEM_CODES = tuple(f"26008-{number:04d}" for number in range(42, 46))
EXPECTED_PROBLEM_ORDER = (1, 2, 3, 4)


def normalize_reference_text(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


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
    hard_gate = bool(
        candidate.get("schema_valid")
        and anchors["problem_order_complete"]
        and anchors["all_problem_units_have_choices"]
        and int(candidate.get("braille_error_count", 0)) <= int(reference.get("braille_error_count", 0))
    )
    return {
        "comparison_kind": "same_printed_source_pipeline_regression",
        "reference_is_human_golden": False,
        "absolute_accuracy_claim_allowed": False,
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
