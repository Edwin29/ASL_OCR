"""Axis 1: geometry judgment -- carried over from v1's judge.py almost
unchanged. Input is now background-subtraction-derived PageGeometry rather
than raw-frame geometry, but the decision logic itself (skew, area ratio,
frame-edge touch) is the same, including the touches_frame_edge fix from
v1 (checked against the raw contour, not the fitted minAreaRect corners --
see book-scanner v1 findings).

Thresholds are a first pass, not yet re-validated against this new
background-subtraction measurement (v1's were calibrated against raw-frame
Canny geometry, which measures slightly differently). Re-measure once real
capture-loop footage exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from book_scanner.detect.types import PageGeometry
from book_scanner.judge.types import TransmitBlockReason


@dataclass(frozen=True)
class GeometryThresholds:
    max_skew_deg: float = 12.0
    min_area_ratio: float = 0.15
    max_area_ratio: float = 0.98


DEFAULT_THRESHOLDS = GeometryThresholds()


def _skew_deg(angle_deg: float) -> float:
    mod = angle_deg % 90.0
    return min(mod, 90.0 - mod)


def judge_geometry(
    geometry: PageGeometry | None,
    thresholds: GeometryThresholds = DEFAULT_THRESHOLDS,
) -> TransmitBlockReason | None:
    """Returns None if geometry passes, otherwise the blocking reason."""
    if geometry is None:
        return TransmitBlockReason.PAGE_NOT_FOUND

    if geometry.touches_frame_edge:
        return TransmitBlockReason.OUT_OF_FRAME

    if _skew_deg(geometry.angle_deg) > thresholds.max_skew_deg:
        return TransmitBlockReason.ROTATED_TOO_MUCH

    if geometry.area_ratio < thresholds.min_area_ratio:
        return TransmitBlockReason.TOO_SMALL

    if geometry.area_ratio > thresholds.max_area_ratio:
        return TransmitBlockReason.TOO_LARGE

    return None
