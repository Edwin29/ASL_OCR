from __future__ import annotations

import numpy as np

from book_scanner.detect.roi import PageSide
from book_scanner.detect.segmenter import SegmentationResult
from book_scanner.detect.spine_seam import FixedCenterlineSeamDetector
from book_scanner.evaluation.seam_experiment import SeamMethodSpec, run_seam_experiment


class FullRoiSegmenter:
    name = "full-roi"

    def segment(self, roi):
        return SegmentationResult(np.full(roi.image.shape[:2], 255, dtype=np.uint8), 1.0, {})


def test_experiment_preserves_other_side_when_one_spec_fails_and_writes_artifacts():
    frame = np.full((60, 120, 3), 200, dtype=np.uint8)
    left_truth = np.zeros((60, 120), dtype=np.uint8)
    right_truth = np.zeros_like(left_truth)
    left_truth[:, :60] = 255
    right_truth[:, 60:] = 255
    evaluations, artifacts, diagnostics = run_seam_experiment(
        frame,
        FullRoiSegmenter(),
        [SeamMethodSpec("fixed", FixedCenterlineSeamDetector(), "union-preserving")],
        truth_masks={PageSide.LEFT: left_truth, PageSide.RIGHT: right_truth},
    )

    assert [item.method for item in evaluations] == ["overlap-baseline", "fixed"]
    assert evaluations[1].metrics["prediction_overlap_px_after"] == 0
    assert evaluations[1].metrics["union_page_recall"] == 1.0
    assert "fixed_union-preserving_overlay" in artifacts
    assert diagnostics["sides"]["left"]["status"] == "page"
