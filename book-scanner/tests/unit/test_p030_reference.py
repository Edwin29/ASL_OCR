from __future__ import annotations

import copy
import json
from pathlib import Path

from book_scanner.evaluation.p030_reference import (
    EXPECTED_PROBLEM_CODES,
    compare_p030_math_braille_alignment,
    compare_p030_page_ir,
    extract_problem_units,
    p030_anchor_diagnostics,
    select_uvdoc_postprocess_sources,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
P030 = WORKSPACE_ROOT / "document-parser" / "tests" / "fixtures" / "accessibility" / "p030.json"


def _reference() -> dict[str, object]:
    return json.loads(P030.read_text(encoding="utf-8"))


def test_p030_fixture_self_comparison_uses_human_verified_golden():
    reference = _reference()
    result = compare_p030_page_ir(reference, reference)

    assert result["comparison_kind"] == "same_printed_source_human_verified_golden"
    assert result["reference_is_human_golden"] is True
    assert result["absolute_accuracy_claim_allowed"] is True
    assert result["golden_provenance"] == "human_verified_during_document_parser_development"
    assert result["golden_scope"] == "exact_printed_p30_fixture_text_structure_and_braille"
    assert result["overall_text_similarity"] == 1.0
    assert result["braille"]["same_content"] is True
    assert result["braille"]["cell_similarity"] == 1.0
    assert result["math_braille_alignment"]["common_span_count"] == 30
    assert result["math_braille_alignment"]["common_reference_cell_count"] == 207
    assert result["math_braille_alignment"]["candidate_added_span_count"] == 0
    assert result["math_braille_alignment"]["reference_only_span_count"] == 0
    assert result["math_braille_alignment"]["verdict"] == "EXACT_GOLDEN_MATH_CELLS"
    assert result["hard_gate_passed"] is True


def test_p030_math_alignment_separates_plain_text_math_promotion():
    reference = _reference()
    candidate = copy.deepcopy(reference)
    problem_four = next(
        node for node in candidate["pages"][0]["nodes"]
        if node.get("node_id") == "p030-vl012-L01"
    )
    problem_four["spans"].append({
        "span_type": "UNKNOWN",
        "text": "y=m",
        "math_span_candidate": True,
        "presentation_ast": {
            "type": "Relation",
            "operator": "=",
            "left": {"type": "Identifier", "value": "y"},
            "right": {"type": "Identifier", "value": "m"},
        },
        "unconsumed_tokens": [],
        "ast_issues": [],
    })

    result = compare_p030_math_braille_alignment(candidate, reference)

    assert result["common_span_count"] == 30
    assert result["common_cell_similarity"] == 1.0
    assert result["reference_only_span_count"] == 0
    assert result["candidate_added_span_count"] == 1
    assert result["candidate_added_cell_count"] == 4
    assert result["candidate_added_present_in_reference_plain_text_count"] == 1
    assert result["candidate_added_spans"][0]["text"] == "y=m"
    assert result["verdict"] == "GOLDEN_COMMON_EXACT_WITH_REFERENCE_PLAIN_TEXT_PROMOTIONS"


def test_p030_math_alignment_reports_missing_golden_span():
    reference = _reference()
    candidate = copy.deepcopy(reference)
    removed = False
    for node in candidate["pages"][0]["nodes"]:
        spans = node.get("spans")
        if not isinstance(spans, list):
            continue
        for index, span in enumerate(spans):
            if isinstance(span, dict) and span.get("math_span_candidate") is True:
                del spans[index]
                removed = True
                break
        if removed:
            break
    assert removed is True

    result = compare_p030_math_braille_alignment(candidate, reference)

    assert result["common_span_count"] == 29
    assert result["reference_only_span_count"] == 1
    assert result["reference_span_coverage"] < 1.0
    assert result["verdict"] == "GOLDEN_COMMON_REGRESSION_OR_MISSING_SPANS"


def test_p030_fixture_exposes_four_ordered_problem_units_and_anchors():
    reference = _reference()
    units = extract_problem_units(reference)
    anchors = p030_anchor_diagnostics(reference)

    assert [unit["problem_number"] for unit in units] == [1, 2, 3, 4]
    assert [unit["choice_count"] for unit in units] == [5, 5, 5, 5]
    assert anchors["page_number_30_exact_node"] is True
    assert anchors["problem_codes_found"] == list(EXPECTED_PROBLEM_CODES)
    assert anchors["problem_codes_complete"] is True


def test_missing_problem_unit_is_reported_as_hard_omission():
    reference = _reference()
    candidate = copy.deepcopy(reference)
    candidate["pages"][0]["nodes"] = [
        node for node in candidate["pages"][0]["nodes"]
        if node.get("node_id") != "p030-problem-004"
    ]

    result = compare_p030_page_ir(candidate, reference)
    assert result["anchors"]["problem_unit_count"] == 3
    assert result["hard_gate_passed"] is False
    assert result["verdict"] == "P030_HARD_REGRESSION_OR_OMISSION"
    assert result["problem_comparisons"][3]["candidate_present"] is False


def _screening_result(artifact_id: str, geometry: str, text: float, cells: float, *, hard=True):
    return {
        "artifact_id": artifact_id, "status": "COMPLETE", "capture": "capture",
        "extraction": "oracle", "geometry": geometry,
        "comparison": {
            "overall_text_similarity": text, "hard_gate_passed": hard,
            "candidate_braille_error_count": 0,
            "braille": {"cell_similarity": cells},
        },
    }


def test_postprocess_screening_is_not_triggered_by_small_uvdoc_delta():
    results = [
        _screening_result("control", "none", 0.90, 0.90),
        _screening_result("uvdoc", "uvdoc_bilinear", 0.89, 0.86),
    ]
    assert select_uvdoc_postprocess_sources(results) == []


def test_postprocess_screening_selects_uvdoc_regression_only():
    results = [
        _screening_result("control", "none", 0.90, 0.90),
        _screening_result("uvdoc", "uvdoc_bilinear", 0.84, 0.80),
        _screening_result("coarse", "coarse", 0.20, 0.20),
    ]
    assert select_uvdoc_postprocess_sources(results) == ["uvdoc"]
