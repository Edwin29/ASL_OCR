"""Offline fixed-layout fallback diagnostics for seam experiment captures.

These checks do not alter the session judge.  They identify captures that
should not be counted as normal seam successes: partial/out-of-frame pages,
gross placement deviations, empty supports, and strong illumination
non-uniformity.  Thresholds are provisional image-coordinate priors derived
from the controlled fixture, not metric calibration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

from book_scanner.detect.roi import PageSide


@dataclass(frozen=True)
class FixedLayoutFallbackConfig:
    min_area_ratio_full: float = 0.20
    max_area_ratio_full: float = 0.44
    min_bbox_width_ratio: float = 0.28
    min_bbox_height_ratio: float = 0.70
    edge_margin_px: int = 2
    max_grid_luminance_range: float = 35.0


@dataclass(frozen=True)
class SideFallbackAssessment:
    side: str
    accepted: bool
    reasons: tuple[str, ...]
    features: dict[str, object]


@dataclass(frozen=True)
class SpreadFallbackAssessment:
    accepted: bool
    reasons: tuple[str, ...]
    sides: dict[str, SideFallbackAssessment]
    diagnostics: dict[str, object]


def _grid_luminance_range(gray: np.ndarray, mask: np.ndarray, bbox: tuple[int, int, int, int]) -> float:
    x, y, width, height = bbox
    medians: list[float] = []
    for row in range(3):
        for column in range(3):
            y0, y1 = y + height * row // 3, y + height * (row + 1) // 3
            x0, x1 = x + width * column // 3, x + width * (column + 1) // 3
            selected = mask[y0:y1, x0:x1] > 0
            values = gray[y0:y1, x0:x1][selected]
            if values.size >= 100:
                medians.append(float(np.median(values)))
    return max(medians) - min(medians) if len(medians) >= 2 else 0.0


def assess_fixed_layout_fallback(
    frame: np.ndarray,
    masks: dict[PageSide, np.ndarray],
    config: FixedLayoutFallbackConfig = FixedLayoutFallbackConfig(),
) -> SpreadFallbackAssessment:
    height, width = frame.shape[:2]
    if any(mask.shape[:2] != (height, width) for mask in masks.values()):
        raise ValueError("fallback masks must use full-frame coordinates")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    side_results: dict[str, SideFallbackAssessment] = {}
    spread_reasons: list[str] = []
    for side in PageSide:
        binary = masks[side] > 0
        count = int(np.count_nonzero(binary))
        reasons: list[str] = []
        if count == 0:
            reasons.append("PAGE_NOT_FOUND")
            features = {"page_px": 0, "area_ratio_full": 0.0}
        else:
            ys, xs = np.nonzero(binary)
            x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
            bbox = (x0, y0, x1 - x0 + 1, y1 - y0 + 1)
            area_ratio = count / (width * height)
            bbox_width_ratio = bbox[2] / width
            bbox_height_ratio = bbox[3] / height
            outer_contact = (
                x0 <= config.edge_margin_px
                if side is PageSide.LEFT
                else x1 >= width - 1 - config.edge_margin_px
            )
            bottom_contact = y1 >= height - 1 - config.edge_margin_px
            luminance_range = _grid_luminance_range(gray, binary.astype(np.uint8), bbox)
            if outer_contact or bottom_contact:
                reasons.append("OUT_OF_FRAME")
            if bbox_height_ratio < config.min_bbox_height_ratio:
                reasons.append("PARTIAL_VERTICAL_EXTENT")
            if bbox_width_ratio < config.min_bbox_width_ratio:
                reasons.append("NARROW_PAGE_EXTENT")
            if not config.min_area_ratio_full <= area_ratio <= config.max_area_ratio_full:
                reasons.append("PAGE_AREA_OUTLIER")
            if luminance_range > config.max_grid_luminance_range:
                reasons.append("UNEVEN_ILLUMINATION")
            features = {
                "page_px": count,
                "area_ratio_full": area_ratio,
                "bbox_full": list(bbox),
                "bbox_width_ratio": bbox_width_ratio,
                "bbox_height_ratio": bbox_height_ratio,
                "outer_contact": outer_contact,
                "bottom_contact": bottom_contact,
                "grid_luminance_range": luminance_range,
            }
        side_result = SideFallbackAssessment(side.value, not reasons, tuple(reasons), features)
        side_results[side.value] = side_result
        spread_reasons.extend(f"{side.value}:{reason}" for reason in reasons)
    return SpreadFallbackAssessment(
        accepted=not spread_reasons,
        reasons=tuple(spread_reasons),
        sides=side_results,
        diagnostics={
            "scope": "offline_fixed_layout_fallback_diagnostic",
            "metric_calibration": False,
            "session_policy_changed": False,
            "config": asdict(config),
        },
    )
