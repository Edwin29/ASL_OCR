from __future__ import annotations

import numpy as np

from book_scanner.detect.roi import PageSide
from book_scanner.evaluation.fallback_assessment import assess_fixed_layout_fallback


def _normal() -> tuple[np.ndarray, dict[PageSide, np.ndarray]]:
    frame = np.full((100, 200, 3), 180, dtype=np.uint8)
    left = np.zeros((100, 200), dtype=np.uint8)
    right = np.zeros_like(left)
    left[10:90, 15:95] = 255
    right[10:90, 105:190] = 255
    return frame, {PageSide.LEFT: left, PageSide.RIGHT: right}


def test_normal_fixed_layout_is_accepted():
    frame, masks = _normal()
    result = assess_fixed_layout_fallback(frame, masks)
    assert result.accepted
    assert not result.reasons


def test_partial_and_outer_page_are_rejected_with_explicit_reasons():
    frame, masks = _normal()
    masks[PageSide.LEFT][:] = 0
    masks[PageSide.LEFT][5:45, :70] = 255
    result = assess_fixed_layout_fallback(frame, masks)
    reasons = result.sides["left"].reasons
    assert "OUT_OF_FRAME" in reasons
    assert "PARTIAL_VERTICAL_EXTENT" in reasons
    assert "PAGE_AREA_OUTLIER" in reasons


def test_empty_side_is_page_not_found():
    frame, masks = _normal()
    masks[PageSide.RIGHT][:] = 0
    result = assess_fixed_layout_fallback(frame, masks)
    assert not result.accepted
    assert result.sides["right"].reasons == ("PAGE_NOT_FOUND",)


def test_uneven_illumination_is_diagnostic_not_silently_accepted():
    frame, masks = _normal()
    frame[10:50, 15:95] = 40
    result = assess_fixed_layout_fallback(frame, masks)
    assert "UNEVEN_ILLUMINATION" in result.sides["left"].reasons
