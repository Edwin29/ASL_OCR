from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from book_scanner.evaluation.paired_page_ir import (
    cache_key_matches,
    compare_repeated_captures,
    compare_same_source,
    evaluate_paired_page_ir,
    run_ocr_batch,
    select_postprocess_screening,
    select_ready_artifacts,
)


def _page_ir(text: str = "abc", content_type: str = "TEXT"):
    return {
        "document_manifest": {"book_id": "test", "page_count": 1},
        "engine_manifest": {
            "pipeline": {"mode": "paddleocr_vl_baseline"},
            "problem_unit_detection": {"engine_id": "test-detector"},
        },
        "pages": [{
            "page_id": "p001", "page_geometry": {"width": 10, "height": 10},
            "nodes": [{"node_id": "n1", "content_type": content_type, "normalized_text": text}],
            "reading_order": ["n1"], "parse_issues": [], "quality_report": {"status": "PASS", "issues": []},
        }],
        "validation_summary": {"schema_valid": True, "errors": [], "warnings": []},
    }


def test_paired_comparator_reports_text_and_node_deltas():
    anchor = evaluate_paired_page_ir(_page_ir("abcdef", "TEXT"))
    candidate = evaluate_paired_page_ir(_page_ir("abc", "FORMULA"))
    result = compare_same_source(anchor, candidate)
    assert result["schema_valid"] is True
    assert result["character_count_ratio"] == 0.5
    assert result["node_type_count_delta"] == {"FORMULA": 1, "TEXT": -1}
    assert result["node_sequence_similarity"] == 0.0
    assert result["accuracy_claim_allowed"] is False


def test_cache_key_requires_both_hash_and_engine():
    record = {"image_sha256": "abc", "engine_signature": "engine-a"}
    assert cache_key_matches(record, "abc", "engine-a")
    assert not cache_key_matches(record, "def", "engine-a")
    assert not cache_key_matches(record, "abc", "engine-b")


def test_batch_reuses_one_adapter_and_isolates_failures(tmp_path: Path):
    paths = []
    for index in range(2):
        path = tmp_path / f"input-{index}.png"
        cv2.imwrite(str(path), np.full((10, 10, 3), 200 + index, dtype=np.uint8))
        paths.append(path)
    artifacts = [
        {"artifact_id": f"a{index}", "status": "READY", "image_path": str(path)}
        for index, path in enumerate(paths)
    ]
    adapter = object()
    calls = []

    def build(paths, *, adapter, book_id):
        calls.append((book_id, adapter))
        if book_id == "a0":
            raise RuntimeError("isolated")
        return _page_ir(book_id)

    results = run_ocr_batch(
        artifacts, tmp_path / "ocr", adapter=adapter, engine_signature="engine",
        build_page_ir=build,
    )
    assert [item["status"] for item in results] == ["OCR_FAILED", "COMPLETE"]
    assert calls == [("a0", adapter), ("a1", adapter)]
    assert json.loads(Path(results[0]["record_path"]).read_text(encoding="utf-8"))["status"] == "OCR_FAILED"


def test_non_ready_artifact_never_enters_ocr_queue(tmp_path: Path):
    called = False

    def build(*args, **kwargs):
        nonlocal called
        called = True

    result = run_ocr_batch(
        [{"artifact_id": "stress", "status": "SKIPPED_FALLBACK_OUT_OF_FRAME"}],
        tmp_path, adapter=object(), engine_signature="engine", build_page_ir=build,
    )
    assert result == [{"artifact_id": "stress", "status": "SKIPPED_FALLBACK_OUT_OF_FRAME"}]
    assert called is False


def test_postprocess_screening_is_blocked_until_geometry_is_complete():
    decision = select_postprocess_screening({"status": "BLOCKED_DEVICE", "comparisons": []})
    assert decision["status"] == "BLOCKED_PREREQUISITE"
    assert decision["selected_artifacts"] == []
    assert decision["full_batch_allowed"] is False


def test_postprocess_screening_does_not_expand_without_regression():
    decision = select_postprocess_screening({
        "status": "COMPLETE",
        "comparisons": [{
            "geometry": "uvdoc_bilinear",
            "comparison": {"schema_valid": True, "character_count_drop_fraction": 0.05,
                           "node_sequence_similarity": 0.95},
        }],
    })
    assert decision["status"] == "NO_POSTPROCESS_EVIDENCE"
    assert decision["full_batch_allowed"] is False


def test_repeat_capture_comparison_matches_only_identical_variant_suffix():
    evaluation = evaluate_paired_page_ir(_page_ir("same"))
    records = {
        "20260826_174943_left_oracle_none_none": {"evaluation": evaluation},
        "20260826_174953_left_oracle_none_none": {"evaluation": evaluation},
        "20260826_174953_left_overlap_none_none": {"evaluation": evaluation},
    }
    comparisons = compare_repeated_captures(records)
    assert len(comparisons) == 1
    assert comparisons[0]["comparison"]["text_similarity"] == 1.0
    assert comparisons[0]["interpretation"] == "repeat_stability_only_not_accuracy"


def test_pilot_queue_selects_exact_three_capture_sides_and_four_variants():
    artifacts = []
    for capture, side in (
        ("20260826_174958", "right"),
        ("20260826_175109", "left"),
        ("20260826_175109", "right"),
        ("20260826_174943", "left"),
    ):
        for extraction in ("oracle", "overlap", "seam_confirmed", "seam_conservative"):
            artifacts.append({
                "artifact_id": f"{capture}_{side}_{extraction}_none_none", "status": "READY",
                "capture": capture, "side": side,
            })
    selected = select_ready_artifacts(
        {"artifacts": artifacts},
        capture_sides=(
            ("20260826_174958", "right"),
            ("20260826_175109", "left"),
            ("20260826_175109", "right"),
        ),
    )
    assert len(selected) == 12
    assert all(item["capture"] != "20260826_174943" for item in selected)
