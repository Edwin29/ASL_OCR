"""Pure capture-suitability decision logic.

Takes a `PageGeometry` (or None) from `measure.py` and decides whether the
frame is good enough to trigger a high-resolution capture. Contains no
OpenCV / pixel-level code -- swapping the measurement algorithm never
requires touching this module, and vice versa.

Threshold values below are a first pass, calibrated against the six real
sample photos in `tests/fixtures/real/` (see `tests/unit/test_judge.py`).
They are NOT final: the physical mounting jig / book-placement guide
described for the real MVP deployment does not exist yet, so these numbers
should be re-measured once that rig is built, per the project's rule against
locking in thresholds before stage-specific real conditions are known.
"""

from __future__ import annotations

from dataclasses import dataclass

from book_scanner.capture.types import CaptureVerdict, PageGeometry, RejectReason


@dataclass(frozen=True)
class JudgeThresholds:
    """Provisional, pre-rig-calibration thresholds. See module docstring."""

    max_skew_deg: float = 12.0
    min_area_ratio: float = 0.15
    max_area_ratio: float = 0.98
    edge_margin_px: float = 4.0


DEFAULT_THRESHOLDS = JudgeThresholds()


def _skew_deg(angle_deg: float) -> float:
    """Deviation from axis-aligned, in [0, 45], independent of which axis
    `minAreaRect` happened to measure from."""
    mod = angle_deg % 90.0
    return min(mod, 90.0 - mod)


def _touches_frame_edge(geometry: PageGeometry, margin_px: float) -> bool:
    frame_w, frame_h = geometry.frame_size
    for x, y in geometry.corners:
        if x <= margin_px or y <= margin_px:
            return True
        if x >= frame_w - margin_px or y >= frame_h - margin_px:
            return True
    return False


def judge_capture(
    geometry: PageGeometry | None,
    thresholds: JudgeThresholds = DEFAULT_THRESHOLDS,
) -> CaptureVerdict:
    """Decide whether `geometry` represents a capture-ready frame."""
    if geometry is None:
        return CaptureVerdict(allowed=False, reason=RejectReason.PAGE_NOT_FOUND, geometry=None)

    if _touches_frame_edge(geometry, thresholds.edge_margin_px):
        return CaptureVerdict(allowed=False, reason=RejectReason.OUT_OF_FRAME, geometry=geometry)

    if _skew_deg(geometry.angle_deg) > thresholds.max_skew_deg:
        return CaptureVerdict(allowed=False, reason=RejectReason.ROTATED_TOO_MUCH, geometry=geometry)

    if geometry.area_ratio < thresholds.min_area_ratio:
        return CaptureVerdict(allowed=False, reason=RejectReason.TOO_SMALL, geometry=geometry)

    if geometry.area_ratio > thresholds.max_area_ratio:
        return CaptureVerdict(allowed=False, reason=RejectReason.TOO_LARGE, geometry=geometry)

    return CaptureVerdict(allowed=True, reason=None, geometry=geometry)
