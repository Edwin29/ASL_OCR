from __future__ import annotations

import numpy as np
import pytest

from book_scanner.correct.perspective import warp_to_rectangle
from book_scanner.correct.types import Corners


def test_warp_recovers_expected_output_size():
    frame = np.zeros((400, 300, 3), dtype=np.uint8)
    corners = Corners(
        top_left=(10.0, 20.0),
        top_right=(210.0, 20.0),
        bottom_right=(210.0, 320.0),
        bottom_left=(10.0, 320.0),
    )
    result = warp_to_rectangle(frame, corners)
    # axis-aligned quad -> output size matches its own width/height exactly
    assert result.shape[1] == 200  # width
    assert result.shape[0] == 300  # height


def test_warp_does_not_upscale_beyond_measured_quad():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    corners = Corners(
        top_left=(0.0, 0.0),
        top_right=(50.0, 0.0),
        bottom_right=(50.0, 50.0),
        bottom_left=(0.0, 50.0),
    )
    result = warp_to_rectangle(frame, corners)
    assert result.shape[1] == 50
    assert result.shape[0] == 50


def test_degenerate_corners_raise():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    corners = Corners(
        top_left=(5.0, 5.0),
        top_right=(5.0, 5.0),
        bottom_right=(5.0, 5.0),
        bottom_left=(5.0, 5.0),
    )
    with pytest.raises(ValueError):
        warp_to_rectangle(frame, corners)
