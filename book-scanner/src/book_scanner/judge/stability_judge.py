"""Axis 2: stability judgment -- new in v2, enabled by the repeated-capture
loop (roadmap Stage 4's "안정성 평가" was never implemented in v1's
single-shot design). Checks whether the most recent geometries agree
closely enough to conclude the book has actually settled, not mid-motion
(a hand moving the page, or the page still being placed).

History accumulation is the caller's (session/loop.py's) responsibility --
this module only judges a given sequence, so it stays a pure function
testable without any loop/state machinery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from book_scanner.detect.types import PageGeometry
from book_scanner.judge.types import TransmitBlockReason


@dataclass(frozen=True)
class StabilityThresholds:
    """Provisional, pre-real-footage thresholds -- no live capture-loop
    footage exists yet to calibrate against."""

    min_frames: int = 5
    max_center_drift_px: float = 15.0
    max_area_ratio_delta: float = 0.05


DEFAULT_THRESHOLDS = StabilityThresholds()


def judge_stability(
    history: Sequence[PageGeometry],
    thresholds: StabilityThresholds = DEFAULT_THRESHOLDS,
) -> TransmitBlockReason | None:
    """Returns None if the most recent `thresholds.min_frames` geometries
    in `history` are consistent enough to call stable, otherwise UNSTABLE.
    Not enough history yet also counts as UNSTABLE -- there's nothing to
    compare against."""
    if len(history) < thresholds.min_frames:
        return TransmitBlockReason.UNSTABLE

    recent = history[-thresholds.min_frames :]
    xs = [g.center[0] for g in recent]
    ys = [g.center[1] for g in recent]
    areas = [g.area_ratio for g in recent]

    x_drift = max(xs) - min(xs)
    y_drift = max(ys) - min(ys)
    area_delta = max(areas) - min(areas)

    if (
        x_drift > thresholds.max_center_drift_px
        or y_drift > thresholds.max_center_drift_px
        or area_delta > thresholds.max_area_ratio_delta
    ):
        return TransmitBlockReason.UNSTABLE

    return None
