"""Pure geometric measurement of the page in a frame.

This module only measures -- it makes no decision about whether the result
is good enough to capture. That decision lives in `judge.py`. Swapping the
detection algorithm here (e.g. a different edge detector, or a learned
segmentation model later) should never require touching the judgment logic.

No assumption is made about page aspect ratio (A4, B5, ...) or page color:
detection works purely off the outer-border contour against the background.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from book_scanner.capture.types import PageGeometry

# Floor to reject noise specks (dust, small shadows) as "not a contour at
# all" -- distinct from and much smaller than the TOO_SMALL judgment
# threshold in judge.py, which is a capture-readiness decision, not a
# measurement-noise filter.
_MIN_NOISE_AREA_RATIO = 0.01

# Canny/blur/dilate below use fixed pixel-sized kernels, so they only find a
# single closed outer contour within a fairly narrow resolution band. Phone
# captures (3000-4000px on a side) are far outside that band: the same
# kernels leave the page's outer edge broken into many small disconnected
# edges instead of one loop. Detecting on a downscaled working copy first,
# then mapping the result back to the original frame's coordinates, keeps
# detection resolution-independent -- this also matches the project's own
# "프리뷰는 가볍게 분석" intent (cheap analysis now, full-res only at actual
# capture time).
_WORKING_MAX_DIM = 1200

# Margin (in working-resolution px) within which a raw contour point counts
# as "touching" the visible frame boundary.
_EDGE_TOUCH_MARGIN_PX = 2


def measure_page(frame: np.ndarray) -> PageGeometry | None:
    """Find the largest page-like region in `frame` (BGR or grayscale).

    Returns None if no plausible region is found at all.
    """
    if frame.ndim == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame

    frame_h, frame_w = gray.shape[:2]
    frame_area = float(frame_w * frame_h)

    scale = min(1.0, _WORKING_MAX_DIM / max(frame_w, frame_h))
    working = (
        cv2.resize(gray, (int(round(frame_w * scale)), int(round(frame_h * scale))), interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else gray
    )

    blurred = cv2.GaussianBlur(working, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    contour_area = cv2.contourArea(largest)
    working_h, working_w = working.shape[:2]
    working_area = float(working_w * working_h)
    if working_area <= 0 or contour_area / working_area < _MIN_NOISE_AREA_RATIO:
        return None

    rect = cv2.minAreaRect(largest)
    (cx, cy), (w, h), angle = rect
    box = cv2.boxPoints(rect)

    rect_area = float(w) * float(h)
    area_ratio = rect_area / working_area  # a ratio, so scale-invariant

    # Whether the *actual detected blob* reaches the visible frame boundary.
    # Deliberately checked against the raw contour points, not the fitted
    # minAreaRect corners: a fitted rectangle's corners are a mathematical
    # construct that can land outside the frame (or right at its edge) for a
    # large, slightly rotated blob even when the blob itself has real margin
    # -- found via a real phone photo during remote testing, where a
    # well-margined page was rejected as OUT_OF_FRAME purely because of this.
    touches_edge = bool(
        (largest[:, 0, 0] <= _EDGE_TOUCH_MARGIN_PX).any()
        or (largest[:, 0, 1] <= _EDGE_TOUCH_MARGIN_PX).any()
        or (largest[:, 0, 0] >= working_w - 1 - _EDGE_TOUCH_MARGIN_PX).any()
        or (largest[:, 0, 1] >= working_h - 1 - _EDGE_TOUCH_MARGIN_PX).any()
    )

    inv_scale = 1.0 / scale
    return PageGeometry(
        corners=tuple((float(x) * inv_scale, float(y) * inv_scale) for x, y in box),
        center=(float(cx) * inv_scale, float(cy) * inv_scale),
        size=(float(w) * inv_scale, float(h) * inv_scale),
        angle_deg=float(angle),
        area_ratio=area_ratio,
        frame_size=(frame_w, frame_h),
        touches_frame_edge=touches_edge,
    )


def measure_page_file(path: str | Path) -> PageGeometry | None:
    """Convenience wrapper: load an image file, then `measure_page`."""
    frame = cv2.imread(str(path))
    if frame is None:
        raise FileNotFoundError(f"could not read image: {path}")
    return measure_page(frame)
