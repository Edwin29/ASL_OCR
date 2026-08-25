from __future__ import annotations

import numpy as np
import pytest

from book_scanner.detect.spread import SpreadConfig, split_spread


def test_default_centerline_splits_evenly():
    frame = np.zeros((100, 400, 3), dtype=np.uint8)
    left, right = split_spread(frame)
    assert left.shape[1] == 200
    assert right.shape[1] == 200
    assert left.shape[0] == right.shape[0] == 100


def test_custom_centerline_fraction():
    frame = np.zeros((100, 400, 3), dtype=np.uint8)
    left, right = split_spread(frame, SpreadConfig(centerline_fraction=0.25))
    assert left.shape[1] == 100
    assert right.shape[1] == 300


def test_split_preserves_content():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    frame[:, :5] = 111  # left half marked
    frame[:, 5:] = 222  # right half marked

    left, right = split_spread(frame, SpreadConfig(centerline_fraction=0.5))

    assert (left == 111).all()
    assert (right == 222).all()


def test_invalid_centerline_fraction_raises():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        split_spread(frame, SpreadConfig(centerline_fraction=1.5))
    with pytest.raises(ValueError):
        split_spread(frame, SpreadConfig(centerline_fraction=0.0))
