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

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    contour_area = cv2.contourArea(largest)
    if frame_area <= 0 or contour_area / frame_area < _MIN_NOISE_AREA_RATIO:
        return None

    rect = cv2.minAreaRect(largest)
    (cx, cy), (w, h), angle = rect
    box = cv2.boxPoints(rect)

    rect_area = float(w) * float(h)

    return PageGeometry(
        corners=tuple((float(x), float(y)) for x, y in box),
        center=(float(cx), float(cy)),
        size=(float(w), float(h)),
        angle_deg=float(angle),
        area_ratio=rect_area / frame_area,
        frame_size=(frame_w, frame_h),
    )


def measure_page_file(path: str | Path) -> PageGeometry | None:
    """Convenience wrapper: load an image file, then `measure_page`."""
    frame = cv2.imread(str(path))
    if frame is None:
        raise FileNotFoundError(f"could not read image: {path}")
    return measure_page(frame)
