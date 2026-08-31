from __future__ import annotations

from book_scanner.evaluation.footer_identity_replay import (
    cadence_frame_step,
    sample_block,
    score_threshold,
    threshold_grid,
)


def test_cadence_is_converted_to_at_least_one_frame():
    assert cadence_frame_step(59.7, 100) == 6
    assert cadence_frame_step(1.0, 100) == 1


def test_sample_block_does_not_backfill_rejected_grid_frame():
    records = [
        {"frame_index": 10, "eligible": True},
        {"frame_index": 16, "eligible": False},
        {"frame_index": 17, "eligible": True},
        {"frame_index": 22, "eligible": True},
    ]
    block = {"start_frame_inclusive": 10, "end_frame_inclusive": 22}
    assert [item["frame_index"] for item in sample_block(records, block, fps=60.0, cadence_ms=100)] == [10, 22]


def test_threshold_grid_contains_every_ordered_valid_pair():
    assert threshold_grid(3) == ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))


def test_threshold_scoring_keeps_unknown_separate_from_errors():
    relations = [
        {"relation_id": "same", "expected": "same", "match_count": 2, "indicators": [True, False, True]},
        {"relation_id": "different", "expected": "different", "match_count": 1, "indicators": [False, False, True]},
    ]
    result = score_threshold(relations, n=3, k_different=0, k_same=2)
    assert result["false_duplicate_count"] == 0
    assert result["false_different_count"] == 0
    assert result["unknown_count"] == 1
    assert result["decisions"][0]["first_decision_sample"] == 3
