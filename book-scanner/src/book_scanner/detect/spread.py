"""Split a two-page-spread frame into independent left/right subframes.

The camera sits fixed above the book's spine (V-shaped rest design), so the
spine's horizontal position in-frame is approximately constant across a
session. Rather than trying to model the spread's actual shape (verified
against real example photos to be a genuine curved surface near the spine,
not a clean two-trapezoid "ribbon" -- see plan/README), this module just
splits the frame at a configured x-position and hands each half to the
existing single-page detect/correct/judge pipeline independently. No
automatic centerline detection: the physical rest doesn't exist yet, so
there's nothing real to calibrate an algorithm against.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpreadConfig:
    """`centerline_fraction` is the spine's x-position as a fraction of
    frame width (0-1). Defaults to the frame's horizontal center; override
    once a real rig's actual spine position is measured."""

    centerline_fraction: float = 0.5


def split_spread(frame: np.ndarray, config: SpreadConfig = SpreadConfig()) -> tuple[np.ndarray, np.ndarray]:
    """Return (left_subframe, right_subframe), split at the configured
    centerline. Each subframe is a view/copy sized independently -- treat
    them as unrelated frames for detect/correct/judge purposes."""
    if not 0.0 < config.centerline_fraction < 1.0:
        raise ValueError(f"centerline_fraction must be in (0, 1), got {config.centerline_fraction}")

    height, width = frame.shape[:2]
    split_x = int(round(width * config.centerline_fraction))
    split_x = max(1, min(width - 1, split_x))

    left = frame[:, :split_x]
    right = frame[:, split_x:]
    return left, right
