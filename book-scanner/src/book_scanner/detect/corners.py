"""Fit a page rectangle from a foreground mask (see background.py).

Unlike v1's Canny+contour approach, this runs on an already-binary mask, so
there's no edge-competition failure mode to work around -- the page
silhouette is simply the largest connected foreground blob, regardless of
what's printed on it or what texture the background has. The downscale
step below is purely a performance optimization for the repeated-capture
loop (finding contours on a full ~4000px mask on every frame would be
slow), not a correctness fix like it was in v1.
"""

from __future__ import annotations

import cv2
import numpy as np

from book_scanner.detect.types import PageGeometry

_WORKING_MAX_DIM = 1200
_EDGE_TOUCH_MARGIN_PX = 2
_MIN_NOISE_AREA_RATIO = 0.01


def geometry_from_mask(mask: np.ndarray) -> PageGeometry | None:
    """Find the largest foreground blob in a binary mask and fit a rotated
    rectangle to it. Returns None if no plausible blob is found."""
    frame_h, frame_w = mask.shape[:2]

    scale = min(1.0, _WORKING_MAX_DIM / max(frame_w, frame_h))
    working = (
        cv2.resize(mask, (int(round(frame_w * scale)), int(round(frame_h * scale))), interpolation=cv2.INTER_NEAREST)
        if scale < 1.0
        else mask
    )
    working_h, working_w = working.shape[:2]
    working_area = float(working_w * working_h)

    contours, _ = cv2.findContours(working, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    contour_area = cv2.contourArea(largest)
    if working_area <= 0 or contour_area / working_area < _MIN_NOISE_AREA_RATIO:
        return None

    rect = cv2.minAreaRect(largest)
    (cx, cy), (w, h), angle = rect
    box = cv2.boxPoints(rect)

    rect_area = float(w) * float(h)
    area_ratio = rect_area / working_area

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


def order_corners(
    points: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]:
    """Canonicalize 4 arbitrary corner points (`cv2.boxPoints`' output order
    depends on the rectangle's rotation angle, not a fixed TL/TR/BR/BL
    convention) into (top_left, top_right, bottom_right, bottom_left), for
    handoff to `correct.types.Corners`. Standard sum/difference heuristic:
    smallest x+y is top-left, largest x+y is bottom-right; of the
    remaining two, smallest y-x is top-right, largest y-x is bottom-left.
    """
    pts = sorted(points, key=lambda p: p[0] + p[1])
    top_left, bottom_right = pts[0], pts[-1]
    remaining = sorted(pts[1:-1], key=lambda p: p[1] - p[0])
    top_right, bottom_left = remaining[0], remaining[-1]
    return top_left, top_right, bottom_right, bottom_left
