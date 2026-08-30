from __future__ import annotations

import copy
import json
from pathlib import Path

from book_scanner.evaluation.document_parser_braille import (
    compare_braille_evaluations,
    evaluate_page_ir_braille,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
P030 = WORKSPACE_ROOT / "document-parser" / "tests" / "fixtures" / "accessibility" / "p030.json"


def test_committed_p030_fixture_runs_through_real_braille_path():
    page_ir = json.loads(P030.read_text(encoding="utf-8"))
    result = evaluate_page_ir_braille(page_ir)

    assert result["schema_valid"] is True
    assert result["braille_opportunity_count"] > 0
    assert result["braille_translated_count"] > 0
    assert result["braille_error_count"] == 0
    assert any(record["unicode"] for record in result["translations"])


def test_plain_text_is_not_misreported_as_failed_braille():
    page_ir = json.loads(P030.read_text(encoding="utf-8"))
    for page in page_ir["pages"]:
        for node in page["nodes"]:
            if node.get("content_type") == "TEXT":
                node["spans"] = [{"span_type": "TEXT", "text": "일반 본문"}]

    result = evaluate_page_ir_braille(page_ir)
    assert result["braille_opportunity_count"] == 0
    assert result["braille_error_count"] == 0


def test_different_content_comparison_never_claims_cell_similarity():
    page_ir = json.loads(P030.read_text(encoding="utf-8"))
    reference = evaluate_page_ir_braille(page_ir)
    candidate = copy.deepcopy(reference)

    comparison = compare_braille_evaluations(candidate, reference, same_content=False)
    assert comparison["verdict"] == "SIMILAR_PIPELINE_HEALTH"
    assert comparison["cell_similarity"] is None
    assert "Different source content" in comparison["note"]
