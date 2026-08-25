"""measure_page tested against synthetic images with known ground truth --
no dependency on real photos, deterministic."""

from __future__ import annotations

import cv2
import numpy as np

from book_scanner.capture.measure import measure_page

FRAME_SIZE = (400, 300)  # (w, h)


def _blank_frame() -> np.ndarray:
    w, h = FRAME_SIZE
    return np.zeros((h, w, 3), dtype=np.uint8)


def _draw_rect(angle_deg: float, rect_w: int = 200, rect_h: int = 140) -> np.ndarray:
    """A white axis-then-rotated rectangle on a black background."""
    frame = _blank_frame()
    w, h = FRAME_SIZE
    box = cv2.boxPoints(((w / 2, h / 2), (rect_w, rect_h), angle_deg)).astype(np.int32)
    cv2.fillConvexPoly(frame, box, (255, 255, 255))
    return frame


def test_finds_axis_aligned_rectangle():
    frame = _draw_rect(angle_deg=0.0)
    geometry = measure_page(frame)

    assert geometry is not None
    assert geometry.frame_size == FRAME_SIZE
    # angle should be close to a multiple of 90 (axis aligned)
    assert min(geometry.angle_deg % 90, 90 - geometry.angle_deg % 90) < 2.0
    expected_ratio = (200 * 140) / (FRAME_SIZE[0] * FRAME_SIZE[1])
    assert abs(geometry.area_ratio - expected_ratio) < 0.05


def test_recovers_known_rotation_angle():
    frame = _draw_rect(angle_deg=25.0)
    geometry = measure_page(frame)

    assert geometry is not None
    skew = min(geometry.angle_deg % 90, 90 - geometry.angle_deg % 90)
    # minAreaRect's angle convention can land on either the drawn angle or
    # its 90-degree-complement depending on which side it measures from --
    # both represent the same 25 degree skew.
    assert abs(skew - 25.0) < 2.0 or abs(skew - 65.0) < 2.0


def test_returns_none_for_blank_frame():
    frame = _blank_frame()
    assert measure_page(frame) is None


def test_returns_none_for_noise_speck():
    frame = _blank_frame()
    cv2.rectangle(frame, (10, 10), (13, 13), (255, 255, 255), -1)
    assert measure_page(frame) is None
