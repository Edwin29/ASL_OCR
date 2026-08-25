"""Composes the three transmittability axes into one TransmitVerdict.

Order matters for cost, not just correctness: geometry is cheap and runs
every frame; stability only matters once geometry already passed (no point
checking whether a rejected frame is "stable"); quality is the only axis
with file I/O (it needs the corrected image to already be written), so it
only runs once geometry+stability both pass -- never wasted on a frame
that's going to be rejected anyway.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from book_scanner.detect.types import PageGeometry
from book_scanner.judge.geometry_judge import DEFAULT_THRESHOLDS as DEFAULT_GEOMETRY_THRESHOLDS
from book_scanner.judge.geometry_judge import GeometryThresholds, judge_geometry
from book_scanner.judge.quality_judge import judge_quality
from book_scanner.judge.stability_judge import DEFAULT_THRESHOLDS as DEFAULT_STABILITY_THRESHOLDS
from book_scanner.judge.stability_judge import StabilityThresholds, judge_stability
from book_scanner.judge.types import TransmitVerdict


def judge_geometry_and_stability(
    geometry: PageGeometry | None,
    history: Sequence[PageGeometry],
    geometry_thresholds: GeometryThresholds = DEFAULT_GEOMETRY_THRESHOLDS,
    stability_thresholds: StabilityThresholds = DEFAULT_STABILITY_THRESHOLDS,
) -> TransmitVerdict:
    """The two axes that can run on every frame, before a corrected image
    exists. The caller (session/loop.py) only proceeds to correction +
    `judge_quality` when this returns transmittable=True."""
    geometry_reason = judge_geometry(geometry, geometry_thresholds)
    if geometry_reason is not None:
        return TransmitVerdict(transmittable=False, reason=geometry_reason)

    stability_reason = judge_stability(history, stability_thresholds)
    if stability_reason is not None:
        return TransmitVerdict(transmittable=False, reason=stability_reason)

    return TransmitVerdict(transmittable=True, reason=None)


def judge_final(corrected_path: Path) -> TransmitVerdict:
    """The quality axis, run only after geometry+stability already passed
    and a corrected image has been written."""
    quality_reason = judge_quality(corrected_path)
    if quality_reason is not None:
        return TransmitVerdict(transmittable=False, reason=quality_reason)
    return TransmitVerdict(transmittable=True, reason=None)
