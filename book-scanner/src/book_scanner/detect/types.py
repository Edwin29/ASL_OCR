"""Shared data types for background-subtraction-based page detection."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackgroundRef:
    """A registered "empty" reference frame (grayscale, blurred) to diff
    subsequent frames against."""

    gray_blurred: "object"  # np.ndarray, kept loosely typed to avoid importing cv2/np here
    frame_size: tuple[int, int]  # (width, height)


@dataclass(frozen=True)
class PageGeometry:
    """Pure measurement of the largest foreground region in a frame.

    `angle_deg` is OpenCV's `minAreaRect` convention: the rotation of the
    rectangle in degrees. Carries no assumption about the page's real-world
    aspect ratio or orientation.
    """

    corners: tuple[tuple[float, float], ...]  # 4 points, from cv2.boxPoints
    center: tuple[float, float]
    size: tuple[float, float]  # (width, height) of the fitted rectangle, px
    angle_deg: float
    area_ratio: float  # fitted rectangle area / full frame area
    frame_size: tuple[int, int]  # (width, height) of the source (sub)frame, px
    # Whether the *actual detected contour* reaches the visible frame
    # boundary -- computed from raw contour points, not the fitted
    # minAreaRect corners (see book-scanner v1 findings: a fitted
    # rectangle's corners can land outside the frame for a large, slightly
    # rotated blob even when the blob itself has real margin).
    touches_frame_edge: bool = False
