from __future__ import annotations

import cv2
import numpy as np

from book_scanner.detect.corners import geometry_from_mask, order_corners

FRAME_SIZE = (400, 300)  # (w, h)


def _mask_with_rect(angle_deg: float, rect_w: int = 200, rect_h: int = 140) -> np.ndarray:
    w, h = FRAME_SIZE
    mask = np.zeros((h, w), dtype=np.uint8)
    box = cv2.boxPoints(((w / 2, h / 2), (rect_w, rect_h), angle_deg)).astype(np.int32)
    cv2.fillConvexPoly(mask, box, 255)
    return mask


def test_finds_axis_aligned_rectangle():
    mask = _mask_with_rect(angle_deg=0.0)
    geometry = geometry_from_mask(mask)

    assert geometry is not None
    assert geometry.frame_size == FRAME_SIZE
    expected_ratio = (200 * 140) / (FRAME_SIZE[0] * FRAME_SIZE[1])
    assert abs(geometry.area_ratio - expected_ratio) < 0.05


def test_recovers_known_rotation():
    mask = _mask_with_rect(angle_deg=25.0)
    geometry = geometry_from_mask(mask)

    assert geometry is not None
    skew = min(geometry.angle_deg % 90, 90 - geometry.angle_deg % 90)
    assert abs(skew - 25.0) < 2.0 or abs(skew - 65.0) < 2.0


def test_returns_none_for_empty_mask():
    mask = np.zeros((FRAME_SIZE[1], FRAME_SIZE[0]), dtype=np.uint8)
    assert geometry_from_mask(mask) is None


def test_out_of_frame_touch_detected():
    w, h = FRAME_SIZE
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[:, :] = 0
    mask[50:250, 0:300] = 255  # touches left edge (x=0)
    geometry = geometry_from_mask(mask)
    assert geometry is not None
    assert geometry.touches_frame_edge is True


def test_order_corners_canonicalizes_any_input_order():
    # a simple axis-aligned square; feed corners in a scrambled order
    tl, tr, br, bl = (10.0, 10.0), (110.0, 10.0), (110.0, 110.0), (10.0, 110.0)
    scrambled = (br, tl, bl, tr)

    ordered = order_corners(scrambled)

    assert ordered == (tl, tr, br, bl)
