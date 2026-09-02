from __future__ import annotations

import importlib.util
import json
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = WORKSPACE_ROOT / "book-scanner" / "tools" / "run_p030_mp4_production_diagnostic.py"
REFERENCE = WORKSPACE_ROOT / "document-parser" / "tests" / "fixtures" / "accessibility" / "p030.json"


def _module():
    spec = importlib.util.spec_from_file_location("p030_mp4_production_diagnostic", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_speech_diagnostic_separates_inline_math_from_math_focus_items():
    diagnostic = _module().speech_diagnostic(json.loads(REFERENCE.read_text(encoding="utf-8")))

    assert diagnostic["focus_item_kinds"]["TEXT"] > 0
    assert diagnostic["inline_math_span_count"] > 0
    assert diagnostic["semantic_accuracy_proven_by_ast_status"] is False


def test_comparison_summary_keeps_semantic_math_differences_visible():
    comparison = {
        "verdict": "P030_NO_CLEAR_REGRESSION",
        "hard_gate_passed": True,
        "overall_text_similarity": 0.9,
        "anchors": {"problem_order": [1, 2, 3, 4], "choice_counts": [5, 5, 5, 5]},
        "braille": {"cell_similarity": 0.8},
        "math_braille_alignment": {
            "reference_span_coverage": 0.95,
            "common_cell_similarity": 1.0,
            "reference_only_span_count": 1,
            "candidate_added_span_count": 1,
            "reference_only_spans": [{"text": "x"}],
            "candidate_added_spans": [{"text": "2"}],
        },
    }
    speech = {"uncertain_math_utterance_count": 0, "utterance_count": 10, "inline_math_span_count": 4}

    summary = _module().comparison_summary(comparison, speech)

    assert summary["math_reference_only_examples"] == [{"text": "x"}]
    assert summary["math_candidate_added_examples"] == [{"text": "2"}]
    assert summary["semantic_accuracy_proven_by_ast_status"] is False
