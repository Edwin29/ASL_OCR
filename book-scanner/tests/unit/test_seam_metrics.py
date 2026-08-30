from __future__ import annotations

import numpy as np

from book_scanner.detect.roi import PageSide
from book_scanner.evaluation.seam_metrics import calculate_seam_metrics


def test_metrics_separate_opposite_page_and_truth_overlap():
    frame = np.full((40, 100, 3), 200, dtype=np.uint8)
    left_truth = np.zeros((40, 100), dtype=np.uint8)
    right_truth = np.zeros_like(left_truth)
    left_truth[5:35, 5:54] = 255
    right_truth[5:35, 46:95] = 255
    left_original = np.zeros_like(left_truth)
    right_original = np.zeros_like(left_truth)
    left_original[5:35, 5:65] = 255
    right_original[5:35, 35:95] = 255
    left_owned = np.zeros_like(left_truth)
    right_owned = np.zeros_like(left_truth)
    left_owned[5:35, 5:50] = 255
    right_owned[5:35, 50:95] = 255

    metrics = calculate_seam_metrics(
        frame,
        {PageSide.LEFT: left_original, PageSide.RIGHT: right_original},
        {PageSide.LEFT: left_owned, PageSide.RIGHT: right_owned},
        {PageSide.LEFT: left_truth, PageSide.RIGHT: right_truth},
    )

    assert metrics.prediction_overlap_px_before > 0
    assert metrics.prediction_overlap_px_after == 0
    assert metrics.truth_overlap_px > 0
    assert metrics.sides["left"].opposite_page_inclusion_px == 0
    assert metrics.sides["left"].own_page_recall < 1.0
    assert metrics.sides["left"].own_page_recall_excluding_truth_overlap == 1.0
    assert metrics.sides["left"].content_proxy_recall_after == 1.0
