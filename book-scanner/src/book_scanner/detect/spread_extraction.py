"""Production seam-conservative extraction for one fixed open-book view.

The detector intentionally assembles the same primitives used by the offline
paired experiment.  It does not import evaluation code and it does not treat a
rectangular contour or equal page sizes as calibration evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol

import cv2
import numpy as np

from book_scanner.detect.contrast_spatial import ContrastSpatialPageSegmenter
from book_scanner.detect.page_mask import MaskPostprocessConfig, PageMask, build_page_mask
from book_scanner.detect.roi import ROIConfig, PageSide, extract_page_rois
from book_scanner.detect.segmenter import PageSegmenter
from book_scanner.detect.spine_seam import (
    LuminanceValleySeamDetector,
    SpineSeam,
    SpineSeamConfig,
    SpineSeamDetector,
    apply_seam_ownership,
)


@dataclass(frozen=True)
class SpreadExtractionConfig:
    roi: ROIConfig = field(default_factory=lambda: ROIConfig(spine_overlap_fraction=0.06))
    seam: SpineSeamConfig = field(
        default_factory=lambda: SpineSeamConfig(
            centerline_fraction=0.5,
            uncertainty_band_px=8,
        )
    )
    mask_postprocess: MaskPostprocessConfig = field(default_factory=MaskPostprocessConfig)
    ownership_policy: str = "union-preserving"
    padding_fraction: float = 0.03

    def __post_init__(self) -> None:
        if self.padding_fraction < 0:
            raise ValueError("padding_fraction must be non-negative")
        if self.ownership_policy not in {"hard", "union-preserving", "uncertainty-band"}:
            raise ValueError(f"unsupported ownership policy: {self.ownership_policy}")


@dataclass(frozen=True)
class ExtractedPage:
    side: PageSide
    crop: np.ndarray
    crop_mask: np.ndarray
    bbox_full: tuple[int, int, int, int]
    padding_px: tuple[int, int]
    edge_contacts: Mapping[str, bool]
    detector_bbox_full: tuple[int, int, int, int]
    detector_confidence: float | None
    diagnostics: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SpreadExtractionResult:
    success: bool
    left: ExtractedPage | None
    right: ExtractedPage | None
    seam: SpineSeam | None
    ownership_diagnostics: Mapping[str, object] | None
    reason: str | None = None
    diagnostics: Mapping[str, object] = field(default_factory=dict)


class SpreadExtractor(Protocol):
    name: str

    def extract(self, frame: np.ndarray) -> SpreadExtractionResult: ...


class SeamConservativeSpreadExtractor:
    """Extract both pages from one full-resolution frame."""

    name = "contrast-spatial+luminance-valley+seam-conservative"

    def __init__(
        self,
        config: SpreadExtractionConfig = SpreadExtractionConfig(),
        *,
        segmenter: PageSegmenter | None = None,
        seam_detector: SpineSeamDetector | None = None,
    ):
        self.config = config
        self.segmenter = segmenter or ContrastSpatialPageSegmenter()
        self.seam_detector = seam_detector or LuminanceValleySeamDetector(config.seam)

    def extract(self, frame: np.ndarray) -> SpreadExtractionResult:
        if (
            not isinstance(frame, np.ndarray)
            or frame.ndim != 3
            or frame.shape[2] != 3
            or frame.dtype != np.uint8
            or frame.size == 0
        ):
            return SpreadExtractionResult(
                False,
                None,
                None,
                None,
                None,
                "INVALID_FRAME",
                {"message": "spread frame must be a non-empty HxWx3 uint8 BGR image"},
            )

        height, width = frame.shape[:2]
        full_masks = {side: np.zeros((height, width), dtype=np.uint8) for side in PageSide}
        pages: dict[PageSide, PageMask] = {}
        side_diagnostics: dict[str, object] = {}
        try:
            rois = extract_page_rois(frame, self.config.roi)
            for side, roi in rois.items():
                segmented = self.segmenter.segment(roi)
                page = build_page_mask(roi, segmented, self.config.mask_postprocess)
                if page is None:
                    side_diagnostics[side.value] = {
                        "status": "no_page",
                        "segmenter": self.segmenter.name,
                        **dict(segmented.diagnostics),
                    }
                    continue
                ox, oy = roi.origin
                roi_width, roi_height = roi.size
                full_masks[side][oy : oy + roi_height, ox : ox + roi_width] = page.mask
                pages[side] = page
                side_diagnostics[side.value] = {
                    "status": "page",
                    "segmenter": self.segmenter.name,
                    "bbox_full": list(page.bbox_full),
                    "confidence": page.confidence,
                    "area_ratio": page.area_ratio,
                    "edge_contacts": dict(page.edge_contacts),
                    **dict(page.diagnostics),
                }
        except Exception as exc:
            return SpreadExtractionResult(
                False,
                None,
                None,
                None,
                None,
                "PAGE_EXTRACTION_FAILED",
                {"message": f"{type(exc).__name__}: {exc}", "sides": side_diagnostics},
            )

        missing = [side.value for side in PageSide if side not in pages]
        if missing:
            return SpreadExtractionResult(
                False,
                None,
                None,
                None,
                None,
                "PAGE_NOT_FOUND",
                {"missing_sides": missing, "sides": side_diagnostics},
            )

        try:
            detected = self.seam_detector.detect(
                frame,
                full_masks[PageSide.LEFT],
                full_masks[PageSide.RIGHT],
            )
        except Exception as exc:
            return SpreadExtractionResult(
                False,
                None,
                None,
                None,
                None,
                "SEAM_FAILED",
                {"message": f"{type(exc).__name__}: {exc}", "sides": side_diagnostics},
            )
        if detected.seam is None:
            return SpreadExtractionResult(
                False,
                None,
                None,
                None,
                None,
                detected.reason or "SEAM_FAILED",
                {"seam": dict(detected.diagnostics), "sides": side_diagnostics},
            )

        try:
            ownership = apply_seam_ownership(
                full_masks[PageSide.LEFT],
                full_masks[PageSide.RIGHT],
                detected.seam,
                self.config.ownership_policy,
            )
            left = _crop_page(
                frame,
                PageSide.LEFT,
                ownership.left_conservative_mask,
                pages[PageSide.LEFT],
                self.config.padding_fraction,
            )
            right = _crop_page(
                frame,
                PageSide.RIGHT,
                ownership.right_conservative_mask,
                pages[PageSide.RIGHT],
                self.config.padding_fraction,
            )
        except Exception as exc:
            return SpreadExtractionResult(
                False,
                None,
                None,
                detected.seam,
                None,
                "CROP_FAILED",
                {"message": f"{type(exc).__name__}: {exc}", "sides": side_diagnostics},
            )
        if left is None or right is None:
            return SpreadExtractionResult(
                False,
                left,
                right,
                detected.seam,
                dict(ownership.diagnostics),
                "EMPTY_CONSERVATIVE_MASK",
                {"sides": side_diagnostics, "ownership": dict(ownership.diagnostics)},
            )

        return SpreadExtractionResult(
            True,
            left,
            right,
            detected.seam,
            dict(ownership.diagnostics),
            None,
            {
                "extractor": self.name,
                "frame_size": [width, height],
                "sides": side_diagnostics,
                "seam": dict(detected.diagnostics),
                "ownership": dict(ownership.diagnostics),
            },
        )


def _crop_page(
    frame: np.ndarray,
    side: PageSide,
    full_mask: np.ndarray,
    detector_page: PageMask,
    padding_fraction: float,
) -> ExtractedPage | None:
    binary = np.where(full_mask > 0, 255, 0).astype(np.uint8)
    points = cv2.findNonZero(binary)
    if points is None:
        return None
    x, y, width, height = (int(value) for value in cv2.boundingRect(points))
    pad_x, pad_y = round(width * padding_fraction), round(height * padding_fraction)
    x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
    x1 = min(frame.shape[1], x + width + pad_x)
    y1 = min(frame.shape[0], y + height + pad_y)
    crop = frame[y0:y1, x0:x1].copy()
    crop_mask = binary[y0:y1, x0:x1].copy()
    if crop.size == 0 or not np.any(crop_mask):
        return None
    margin = 1
    edge_contacts = {
        "top": bool(np.any(binary[: margin + 1, :])),
        "bottom": bool(np.any(binary[max(0, binary.shape[0] - margin - 1) :, :])),
        "outer": (
            bool(np.any(binary[:, : margin + 1]))
            if side is PageSide.LEFT
            else bool(np.any(binary[:, max(0, binary.shape[1] - margin - 1) :]))
        ),
        "spine": (
            bool(np.any(binary[:, max(0, binary.shape[1] // 2 - margin) : binary.shape[1] // 2 + margin + 1]))
        ),
    }
    return ExtractedPage(
        side=side,
        crop=crop,
        crop_mask=crop_mask,
        bbox_full=(x0, y0, x1 - x0, y1 - y0),
        padding_px=(pad_x, pad_y),
        edge_contacts=edge_contacts,
        detector_bbox_full=detector_page.bbox_full,
        detector_confidence=detector_page.confidence,
        diagnostics={
            "mask_pixels": int(np.count_nonzero(binary)),
            "crop_mask_coverage": float(np.count_nonzero(crop_mask) / max(1, crop_mask.size)),
        },
    )
