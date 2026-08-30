from __future__ import annotations

import copy
import json
from pathlib import Path

from book_scanner.evaluation.p030_reference import (
    EXPECTED_PROBLEM_CODES,
    compare_p030_page_ir,
    extract_problem_units,
    p030_anchor_diagnostics,
    select_uvdoc_postprocess_sources,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
P030 = WORKSPACE_ROOT / "document-parser" / "tests" / "fixtures" / "accessibility" / "p030.json"


def _reference() -> dict[str, object]:
    return json.loads(P030.read_text(encoding="utf-8"))


def test_p030_fixture_self_comparison_enables_same_source_cells_without_accuracy_claim():
    reference = _reference()
    result = compare_p030_page_ir(reference, reference)

    assert result["comparison_kind"] == "same_printed_source_pipeline_regression"
    assert result["reference_is_human_golden"] is False
    assert result["absolute_accuracy_claim_allowed"] is False
    assert result["overall_text_similarity"] == 1.0
    assert result["braille"]["same_content"] is True
    assert result["braille"]["cell_similarity"] == 1.0
    assert result["hard_gate_passed"] is True


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
