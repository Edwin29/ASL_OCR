"""Integration test: actually imports and runs document-parser's own
ImageQualityGate (not a book-scanner-side reimplementation) -- this module
has no paddle/torch dependency, so it's expected to run in book-scanner's
normal venv without the special GPU OCR venv."""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

import cv2
import numpy as np

from book_scanner.judge.quality_judge import judge_quality
from book_scanner.judge.types import TransmitBlockReason


@contextmanager
def _tmp_dir():
    # See book-scanner v1's note: pytest's tmp_path fixture hit a stale-ACL
    # permission error on this dev machine's shared temp base; avoid it.
    with tempfile.TemporaryDirectory(prefix="book_scanner_quality_test_") as d:
        yield Path(d)


def test_low_resolution_image_is_blocked():
    with _tmp_dir() as tmp:
        path = tmp / "low_res.png"
        frame = np.full((650, 500, 3), 255, dtype=np.uint8)  # long edge 650 << min 1800
        cv2.imwrite(str(path), frame)

        assert judge_quality(path) is TransmitBlockReason.LOW_QUALITY


def test_sufficient_resolution_image_passes():
    with _tmp_dir() as tmp:
        path = tmp / "good_res.png"
        frame = np.full((2600, 2000, 3), 255, dtype=np.uint8)  # aspect ratio 0.77, in [0.68,0.82]
        cv2.imwrite(str(path), frame)

        assert judge_quality(path) is None
