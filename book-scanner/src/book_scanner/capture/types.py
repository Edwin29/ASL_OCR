"""Shared data types for page measurement and capture-suitability judgment.

Kept deliberately separate from both `measure.py` (which produces
`PageGeometry`) and `judge.py` (which consumes it) so the two can evolve or
be swapped independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RejectReason(Enum):
    """Why a capture was not permitted.

    Exposed as a stable, externally meaningful state (not just a bool) so a
    future caller -- e.g. a reset-beep trigger -- can react to *why* a
    capture was rejected without re-deriving it from raw geometry.
    """

    PAGE_NOT_FOUND = "page_not_found"
    ROTATED_TOO_MUCH = "rotated_too_much"
    TOO_SMALL = "too_small"
    TOO_LARGE = "too_large"
    OUT_OF_FRAME = "out_of_frame"


@dataclass(frozen=True)
class PageGeometry:
    """Pure measurement of the largest page-like region in a frame.

    `angle_deg` is OpenCV's `minAreaRect` convention: the rotation of the
    rectangle in degrees, in [-90, 0). It carries no assumption about the
    page's real-world aspect ratio or orientation.
    """

    corners: tuple[tuple[float, float], ...]  # 4 points, from cv2.boxPoints
    center: tuple[float, float]
    size: tuple[float, float]  # (width, height) of the fitted rectangle, px
    angle_deg: float
    area_ratio: float  # fitted rectangle area / full frame area
    frame_size: tuple[int, int]  # (width, height) of the source frame, px
    # Whether the *actual detected contour* reaches the frame boundary.
    # Deliberately not inferred from `corners`: a minAreaRect fit's corners
    # are a mathematical construct that can land outside the frame for a
    # large, slightly rotated blob even when the blob itself has real
    # margin, so judge.py's OUT_OF_FRAME check relies on this instead.
    touches_frame_edge: bool = False


@dataclass(frozen=True)
class CaptureVerdict:
    """Result of judging whether a measured frame is capture-ready."""

    allowed: bool
    reason: RejectReason | None
    geometry: PageGeometry | None
