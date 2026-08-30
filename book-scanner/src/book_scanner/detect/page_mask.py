"""Mask post-processing, measurements, coordinate mapping, and safe crop."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from book_scanner.detect.roi import PageROI, PageSide
from book_scanner.detect.segmenter import SegmentationResult


@dataclass(frozen=True)
class MaskPostprocessConfig:
    min_component_area_ratio: float = 0.02
    close_kernel_px: int = 9
    open_kernel_px: int = 3
    edge_margin_px: int = 1


@dataclass(frozen=True)
class PageMask:
    side: PageSide
    mask: np.ndarray
    confidence: float | None
    bbox: tuple[int, int, int, int]
    bbox_full: tuple[int, int, int, int]
    area_ratio: float
    centroid: tuple[float, float]
    centroid_full: tuple[float, float]
    edge_contacts: dict[str, bool]
    roi_origin: tuple[int, int]
    roi_size: tuple[int, int]
    full_frame_size: tuple[int, int]
    diagnostics: dict[str, object]

    @property
    def touches_spine(self) -> bool:
        return self.edge_contacts["spine"]

    @property
    def touches_outer_frame(self) -> bool:
        return any(self.edge_contacts[key] for key in ("top", "bottom", "outer"))


@dataclass(frozen=True)
class PageCrop:
    image: np.ndarray
    mask: np.ndarray
    bbox_full: tuple[int, int, int, int]


def _odd_kernel(size: int) -> np.ndarray | None:
    if size <= 1:
        return None
    size = size if size % 2 else size + 1
    return np.ones((size, size), dtype=np.uint8)


def build_page_mask(
    roi: PageROI,
    result: SegmentationResult,
    config: MaskPostprocessConfig = MaskPostprocessConfig(),
) -> PageMask | None:
    if result.mask.shape[:2] != roi.image.shape[:2]:
        raise ValueError(
            f"segmenter mask size {result.mask.shape[:2]} does not match ROI {roi.image.shape[:2]}"
        )
    binary = np.where(result.mask > 0, 255, 0).astype(np.uint8)
    binary[roi.allowed_mask == 0] = 0
    close_kernel = _odd_kernel(config.close_kernel_px)
    open_kernel = _odd_kernel(config.open_kernel_px)
    if close_kernel is not None:
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_kernel)
    if open_kernel is not None:
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, open_kernel)
    # Morphology can grow pixels across a polygon ROI boundary; calibrated
    # pixels outside the physical support region must remain impossible.
    binary[roi.allowed_mask == 0] = 0

    count, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if count <= 1:
        return None
    component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    component_area = int(stats[component, cv2.CC_STAT_AREA])
    allowed_area = int(np.count_nonzero(roi.allowed_mask))
    area_ratio = component_area / allowed_area if allowed_area else 0.0
    if area_ratio < config.min_component_area_ratio:
        return None

    cleaned = np.where(labels == component, 255, 0).astype(np.uint8)
    x = int(stats[component, cv2.CC_STAT_LEFT])
    y = int(stats[component, cv2.CC_STAT_TOP])
    width = int(stats[component, cv2.CC_STAT_WIDTH])
    height = int(stats[component, cv2.CC_STAT_HEIGHT])
    cx, cy = (float(v) for v in centroids[component])
    ox, oy = roi.origin
    roi_w, roi_h = roi.size
    margin = config.edge_margin_px
    contacts_local = {
        "left": bool(np.any(cleaned[:, : margin + 1])),
        "right": bool(np.any(cleaned[:, max(0, roi_w - margin - 1) :])),
        "top": bool(np.any(cleaned[: margin + 1, :])),
        "bottom": bool(np.any(cleaned[max(0, roi_h - margin - 1) :, :])),
    }
    edge_contacts = {
        "top": contacts_local["top"] and oy <= margin,
        "bottom": contacts_local["bottom"] and oy + roi_h >= roi.full_frame_size[1] - margin,
        "spine": contacts_local["right"] if roi.side is PageSide.LEFT else contacts_local["left"],
        "outer": (
            contacts_local["left"] and ox <= margin
            if roi.side is PageSide.LEFT
            else contacts_local["right"] and ox + roi_w >= roi.full_frame_size[0] - margin
        ),
        "roi_boundary": any(contacts_local.values()),
    }
    diagnostics = dict(result.diagnostics)
    diagnostics.update({"component_area_px": component_area, "allowed_area_px": allowed_area})
    return PageMask(
        side=roi.side,
        mask=cleaned,
        confidence=result.confidence,
        bbox=(x, y, width, height),
        bbox_full=(x + ox, y + oy, width, height),
        area_ratio=area_ratio,
        centroid=(cx, cy),
        centroid_full=(cx + ox, cy + oy),
        edge_contacts=edge_contacts,
        roi_origin=roi.origin,
        roi_size=roi.size,
        full_frame_size=roi.full_frame_size,
        diagnostics=diagnostics,
    )


def crop_page(
    full_frame: np.ndarray,
    page_mask: PageMask,
    padding_fraction: float = 0.03,
    neutralize_outside: bool = False,
    neutral_value: int | tuple[int, int, int] = 255,
) -> PageCrop:
    if padding_fraction < 0:
        raise ValueError("padding_fraction must be non-negative")
    x, y, width, height = page_mask.bbox
    pad_x = round(width * padding_fraction)
    pad_y = round(height * padding_fraction)
    roi_w, roi_h = page_mask.roi_size
    x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
    x1, y1 = min(roi_w, x + width + pad_x), min(roi_h, y + height + pad_y)
    ox, oy = page_mask.roi_origin
    crop = full_frame[oy + y0 : oy + y1, ox + x0 : ox + x1].copy()
    mask = page_mask.mask[y0:y1, x0:x1].copy()
    if neutralize_outside:
        crop[mask == 0] = neutral_value
    return PageCrop(crop, mask, (ox + x0, oy + y0, x1 - x0, y1 - y0))
