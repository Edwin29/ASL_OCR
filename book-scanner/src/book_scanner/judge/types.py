"""Shared data types for "transmittable" (post-capture) judgment.

Distinct from v1's "capturable" (pre-capture) judgment: this evaluates an
already-captured, already-corrected frame's fitness to send to
document-parser, not whether to trigger a capture in the first place. See
plan Context for why this reframing matters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TransmitBlockReason(Enum):
    """Why a frame is not yet transmittable. Three axes: geometry
    (PAGE_NOT_FOUND .. OUT_OF_FRAME), stability (UNSTABLE), quality
    (LOW_QUALITY, from document-parser's own ImageQualityGate)."""

    PAGE_NOT_FOUND = "page_not_found"
    ROTATED_TOO_MUCH = "rotated_too_much"
    TOO_SMALL = "too_small"
    TOO_LARGE = "too_large"
    OUT_OF_FRAME = "out_of_frame"
    UNSTABLE = "unstable"
    LOW_QUALITY = "low_quality"


@dataclass(frozen=True)
class TransmitVerdict:
    """Result of judging whether a captured (and, once stable, corrected)
    frame is ready to transmit to document-parser."""

    transmittable: bool
    reason: TransmitBlockReason | None
