"""Replaceable page-surface segmentation boundary and initial baselines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol

import cv2
import numpy as np

from book_scanner.detect.background import BackgroundRef, foreground_mask
from book_scanner.detect.roi import PageROI, PageSide


@dataclass(frozen=True)
class SegmentationResult:
    mask: np.ndarray
    confidence: float | None = None
    diagnostics: Mapping[str, object] = field(default_factory=dict)


class PageSegmenter(Protocol):
    name: str

    def segment(self, roi: PageROI) -> SegmentationResult:
        """Return an ROI-local binary-like mask and diagnostics."""
        ...


class StaticPageSegmenter:
    """Fake segmenter for session/pipeline tests without an ML runtime."""

    name = "static"

    def __init__(
        self,
        masks: Mapping[PageSide, np.ndarray] | Callable[[PageROI], np.ndarray],
        confidence: float = 1.0,
    ):
        self._masks = masks
        self._confidence = confidence

    def segment(self, roi: PageROI) -> SegmentationResult:
        mask = self._masks(roi) if callable(self._masks) else self._masks[roi.side]
        return SegmentationResult(np.asarray(mask).copy(), self._confidence, {"source": "static"})


class BrightnessPageSegmenter:
    """OpenCV measurement baseline, not a production page detector.

    It assumes page pixels are generally brighter than their surroundings.
    The result is useful for bootstrapping labels and exposing failure modes;
    its thresholds are deliberately configurable and are not claimed to be
    calibrated for the physical scanner.
    """

    name = "brightness"

    def __init__(self, min_luminance_stddev: float = 3.0):
        self.min_luminance_stddev = min_luminance_stddev

    def segment(self, roi: PageROI) -> SegmentationResult:
        gray = cv2.cvtColor(roi.image, cv2.COLOR_BGR2GRAY) if roi.image.ndim == 3 else roi.image
        valid_values = gray[roi.allowed_mask > 0]
        stddev = float(valid_values.std()) if valid_values.size else 0.0
        if stddev < self.min_luminance_stddev:
            return SegmentationResult(
                np.zeros(gray.shape, dtype=np.uint8),
                0.0,
                {"reason": "low_luminance_variation", "luminance_stddev": stddev},
            )

        blurred = cv2.GaussianBlur(gray, (9, 9), 0)
        threshold, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        mask[roi.allowed_mask == 0] = 0
        high = valid_values[valid_values > threshold]
        low = valid_values[valid_values <= threshold]
        separation = float(high.mean() - low.mean()) if high.size and low.size else 0.0
        confidence = max(0.0, min(1.0, separation / 128.0))
        return SegmentationResult(
            mask,
            confidence,
            {"otsu_threshold": float(threshold), "luminance_stddev": stddev, "class_separation": separation},
        )


class LegacyBackgroundSegmenter:
    """Adapter retaining the existing background subtraction for A/B runs."""

    name = "legacy-background"

    def __init__(self, backgrounds: Mapping[PageSide, BackgroundRef]):
        self._backgrounds = backgrounds

    def segment(self, roi: PageROI) -> SegmentationResult:
        mask = foreground_mask(roi.image, self._backgrounds[roi.side])
        mask[roi.allowed_mask == 0] = 0
        return SegmentationResult(mask, None, {"source": "registered_background"})
