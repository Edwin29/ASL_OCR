from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

import cv2
import numpy as np

from book_scanner.detect.types import PageGeometry
from book_scanner.judge.transmit_judge import judge_final, judge_geometry_and_stability
from book_scanner.judge.types import TransmitBlockReason

FRAME = (400, 300)


@contextmanager
def _tmp_dir():
    with tempfile.TemporaryDirectory(prefix="book_scanner_transmit_judge_test_") as d:
        yield Path(d)


def _geometry(center=(200.0, 150.0), area_ratio=0.5, angle_deg=0.0, touches_frame_edge=False) -> PageGeometry:
    return PageGeometry(
        corners=((50.0, 50.0), (350.0, 50.0), (350.0, 250.0), (50.0, 250.0)),
        center=center,
        size=(300.0, 200.0),
        angle_deg=angle_deg,
        area_ratio=area_ratio,
        frame_size=FRAME,
        touches_frame_edge=touches_frame_edge,
    )


def test_bad_geometry_blocks_before_stability_is_checked():
    verdict = judge_geometry_and_stability(_geometry(area_ratio=0.99), history=[])
    assert not verdict.transmittable
    assert verdict.reason is TransmitBlockReason.TOO_LARGE


def test_good_geometry_but_insufficient_history_is_unstable():
    verdict = judge_geometry_and_stability(_geometry(), history=[])
    assert not verdict.transmittable
    assert verdict.reason is TransmitBlockReason.UNSTABLE


def test_good_geometry_and_settled_history_passes():
    history = [_geometry()] * 5
    verdict = judge_geometry_and_stability(_geometry(), history=history)
    assert verdict.transmittable
    assert verdict.reason is None


def test_final_quality_check_blocks_low_resolution():
    with _tmp_dir() as tmp:
        path = tmp / "low_res.png"
        cv2.imwrite(str(path), np.full((650, 500, 3), 255, dtype=np.uint8))

        verdict = judge_final(path)
        assert not verdict.transmittable
        assert verdict.reason is TransmitBlockReason.LOW_QUALITY


def test_final_quality_check_passes_good_resolution():
    with _tmp_dir() as tmp:
        path = tmp / "good_res.png"
        cv2.imwrite(str(path), np.full((2600, 2000, 3), 255, dtype=np.uint8))

        verdict = judge_final(path)
        assert verdict.transmittable
        assert verdict.reason is None
