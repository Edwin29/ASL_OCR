from __future__ import annotations

import numpy as np

from book_scanner.correct.coarse_perspective import estimate_quad_from_mask, warp_from_mask


def test_coarse_warp_records_non_metric_anchor_and_matrix():
    image = np.zeros((100, 120, 3), dtype=np.uint8)
    mask = np.zeros((100, 120), dtype=np.uint8)
    mask[10:90, 20:100] = 255
    image[mask > 0] = 220

    result = warp_from_mask(image, mask)

    assert result.success
    assert result.matrix is not None
    assert result.diagnostics["metric_calibration"] is False
    assert result.diagnostics["interpolation"].startswith("INTER_LINEAR")
    assert "gradient_sharpness_ratio" in result.diagnostics


def test_missing_and_degenerate_anchors_fail_explicitly():
    empty = np.zeros((50, 50), dtype=np.uint8)
    quad, diagnostics = estimate_quad_from_mask(empty)
    assert quad is None
    assert diagnostics["reason"] == "WARP_ANCHOR_NOT_FOUND"
