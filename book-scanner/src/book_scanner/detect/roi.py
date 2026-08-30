"""Calibratable left/right regions of interest for page segmentation.

The original session loop still uses :mod:`book_scanner.detect.spread`.
This module is the mask pipeline's explicit coordinate boundary: every ROI
keeps the offset required to map a local mask back to the full camera frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import cv2
import numpy as np


class PageSide(Enum):
    LEFT = "left"
    RIGHT = "right"


NormalizedPolygon = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class ROIConfig:
    """Fraction split by default, optionally replaced by calibrated polygons.

    Polygon coordinates are normalized to the full frame (0..1).  Supplying
    one polygon requires supplying both so a run cannot silently mix two
    coordinate systems.
    """

    centerline_fraction: float = 0.5
    spine_overlap_fraction: float = 0.0
    left_polygon: NormalizedPolygon | None = None
    right_polygon: NormalizedPolygon | None = None

    def __post_init__(self) -> None:
        if not 0.0 < self.centerline_fraction < 1.0:
            raise ValueError("centerline_fraction must be in (0, 1)")
        if not 0.0 <= self.spine_overlap_fraction < 0.5:
            raise ValueError("spine_overlap_fraction must be in [0, 0.5)")
        if self.spine_overlap_fraction >= min(self.centerline_fraction, 1.0 - self.centerline_fraction):
            raise ValueError("spine_overlap_fraction leaves no outer-side ROI extent")
        if (self.left_polygon is None) != (self.right_polygon is None):
            raise ValueError("left_polygon and right_polygon must be supplied together")
        for polygon in (self.left_polygon, self.right_polygon):
            if polygon is None:
                continue
            if len(polygon) < 3:
                raise ValueError("ROI polygons need at least three points")
            if any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in polygon):
                raise ValueError("ROI polygon coordinates must be normalized to [0, 1]")


@dataclass(frozen=True)
class PageROI:
    side: PageSide
    image: np.ndarray
    allowed_mask: np.ndarray
    origin: tuple[int, int]
    full_frame_size: tuple[int, int]
    is_calibrated: bool

    @property
    def size(self) -> tuple[int, int]:
        height, width = self.image.shape[:2]
        return width, height

    def local_to_full(self, point: tuple[float, float]) -> tuple[float, float]:
        return point[0] + self.origin[0], point[1] + self.origin[1]


def _polygon_roi(frame: np.ndarray, side: PageSide, polygon: NormalizedPolygon) -> PageROI:
    full_h, full_w = frame.shape[:2]
    points = np.array(
        [[round(x * (full_w - 1)), round(y * (full_h - 1))] for x, y in polygon],
        dtype=np.int32,
    )
    x, y, width, height = cv2.boundingRect(points)
    local_points = points - np.array([x, y], dtype=np.int32)
    allowed = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(allowed, [local_points], 255)
    image = frame[y : y + height, x : x + width].copy()
    image[allowed == 0] = 0
    return PageROI(side, image, allowed, (x, y), (full_w, full_h), True)


def extract_page_rois(frame: np.ndarray, config: ROIConfig = ROIConfig()) -> dict[PageSide, PageROI]:
    if frame is None or frame.ndim not in (2, 3):
        raise ValueError("frame must be a grayscale or color image")
    full_h, full_w = frame.shape[:2]
    if full_w < 2 or full_h < 1:
        raise ValueError(f"frame is too small for two page ROIs: {full_w}x{full_h}")

    if config.left_polygon is not None and config.right_polygon is not None:
        return {
            PageSide.LEFT: _polygon_roi(frame, PageSide.LEFT, config.left_polygon),
            PageSide.RIGHT: _polygon_roi(frame, PageSide.RIGHT, config.right_polygon),
        }

    split_x = max(1, min(full_w - 1, round(full_w * config.centerline_fraction)))
    overlap_px = round(full_w * config.spine_overlap_fraction)
    left_end = min(full_w, split_x + overlap_px)
    right_start = max(0, split_x - overlap_px)
    left = frame[:, :left_end].copy()
    right = frame[:, right_start:].copy()
    return {
        PageSide.LEFT: PageROI(
            PageSide.LEFT,
            left,
            np.full(left.shape[:2], 255, dtype=np.uint8),
            (0, 0),
            (full_w, full_h),
            False,
        ),
        PageSide.RIGHT: PageROI(
            PageSide.RIGHT,
            right,
            np.full(right.shape[:2], 255, dtype=np.uint8),
            (right_start, 0),
            (full_w, full_h),
            False,
        ),
    }
