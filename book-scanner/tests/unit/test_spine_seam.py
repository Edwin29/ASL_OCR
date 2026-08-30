from __future__ import annotations

import cv2
import numpy as np

from book_scanner.detect.spine_seam import (
    FixedCenterlineSeamDetector,
    LuminanceValleySeamDetector,
    MaskAwareSpineSeamDetector,
    SpineSeamConfig,
    apply_seam_ownership,
    seam_points_in_roi,
)


def _synthetic_spread() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    height, width = 160, 240
    image = np.full((height, width, 3), 215, dtype=np.uint8)
    gutter = (width // 2 + 8 * np.sin(np.arange(height) / 24.0)).round().astype(np.int32)
    for y, x in enumerate(gutter):
        image[y, max(0, x - 2) : min(width, x + 3)] = 12
    for y in range(25, 145, 24):
        cv2.line(image, (25, y), (100, y), (20, 20, 20), 2)
        cv2.line(image, (140, y), (215, y), (20, 20, 20), 2)
    left = np.zeros((height, width), dtype=np.uint8)
    right = np.zeros_like(left)
    left[:, :150] = 255
    right[:, 90:] = 255
    return image, left, right, gutter


def test_dynamic_seams_follow_continuous_gutter_inside_fixed_band():
    image, left, right, gutter = _synthetic_spread()
    config = SpineSeamConfig(allowed_half_width_fraction=0.15, smoothing_window_px=9)
    for detector in (LuminanceValleySeamDetector(config), MaskAwareSpineSeamDetector(config)):
        result = detector.detect(image, left, right)
        assert result.seam is not None
        path = result.seam.x_by_row
        assert float(np.abs(path - gutter).mean()) < 6.0
        assert int(np.abs(np.diff(path)).max()) <= config.max_step_px


def test_dark_distractor_outside_allowed_band_cannot_capture_seam():
    image, left, right, _ = _synthetic_spread()
    image[:, 20:25] = 0
    config = SpineSeamConfig(allowed_half_width_fraction=0.08)
    result = LuminanceValleySeamDetector(config).detect(image, left, right)
    assert result.seam is not None
    assert result.seam.x_by_row.min() >= round(240 * (0.5 - 0.08))


def test_ownership_is_disjoint_and_union_preserving():
    image, left, right, _ = _synthetic_spread()
    seam = FixedCenterlineSeamDetector().detect(image, left, right).seam
    assert seam is not None
    result = apply_seam_ownership(left, right, seam, "union-preserving")
    assert np.count_nonzero((result.left_mask > 0) & (result.right_mask > 0)) == 0
    assert result.diagnostics["union_lost_px"] == 0
    assert result.diagnostics["prediction_overlap_px_before"] > 0
    local = seam_points_in_roi(seam, (100, 10), (40, 30))
    assert local[0][1] == 0
    assert all(0 <= x < 40 and 0 <= y < 30 for x, y in local)


def test_uncertainty_band_is_explicit_and_not_silently_discarded():
    image, left, right, _ = _synthetic_spread()
    seam = FixedCenterlineSeamDetector(SpineSeamConfig(uncertainty_band_px=4)).detect(image, left, right).seam
    assert seam is not None
    result = apply_seam_ownership(left, right, seam, "uncertainty-band")
    assert np.count_nonzero(result.ambiguous_mask) > 0
    assert result.diagnostics["union_lost_px"] == result.diagnostics["ambiguous_px"]
    assert np.count_nonzero(result.left_conservative_mask) > np.count_nonzero(result.left_mask)


def test_empty_or_one_sided_masks_return_no_page():
    image, left, _right, _ = _synthetic_spread()
    empty = np.zeros_like(left)
    result = MaskAwareSpineSeamDetector().detect(image, left, empty)
    assert result.seam is None
    assert result.reason == "NO_PAGE"


def test_adaptive_detector_requires_overlap_support():
    image, left, right, _ = _synthetic_spread()
    left[:, 100:] = 0
    right[:, :140] = 0
    result = LuminanceValleySeamDetector().detect(image, left, right)
    assert result.seam is None
    assert result.reason == "NO_OVERLAP_SUPPORT"
