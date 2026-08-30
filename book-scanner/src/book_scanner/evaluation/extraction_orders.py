"""Execute the three approved page extraction/warp order experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

from book_scanner.correct.coarse_perspective import warp_from_mask
from book_scanner.detect.page_mask import PageMask, build_page_mask
from book_scanner.detect.roi import ROIConfig, PageROI, PageSide, extract_page_rois
from book_scanner.detect.segmenter import PageSegmenter
from book_scanner.evaluation.page_masks import calculate_mask_metrics


@dataclass(frozen=True)
class OrderSideResult:
    order: str
    side: str
    status: str
    reason: str | None
    stage_trace: tuple[str, ...]
    warp_count: int
    diagnostics: dict[str, object]
    metrics: dict[str, object] | None = None


def _local_roi(image: np.ndarray, side: PageSide) -> PageROI:
    height, width = image.shape[:2]
    return PageROI(side, image, np.full((height, width), 255, np.uint8), (0, 0), (width, height), False)


def _segment(image: np.ndarray, side: PageSide, segmenter: PageSegmenter) -> PageMask | None:
    roi = _local_roi(image, side)
    return build_page_mask(roi, segmenter.segment(roi))


def _crop_local(image: np.ndarray, page: PageMask, padding_fraction: float = 0.03) -> tuple[np.ndarray, np.ndarray]:
    x, y, width, height = page.bbox
    px, py = round(width * padding_fraction), round(height * padding_fraction)
    x0, y0, x1, y1 = max(0, x - px), max(0, y - py), min(image.shape[1], x + width + px), min(image.shape[0], y + height + py)
    return image[y0:y1, x0:x1].copy(), page.mask[y0:y1, x0:x1].copy()


def _coverage_for_page(page: PageMask) -> np.ndarray:
    coverage = np.zeros(page.mask.shape, dtype=np.uint8)
    x, y, width, height = page.bbox
    px, py = round(width * 0.03), round(height * 0.03)
    coverage[max(0, y - py) : min(page.mask.shape[0], y + height + py), max(0, x - px) : min(page.mask.shape[1], x + width + px)] = 255
    return coverage


def _metrics(page: PageMask, truth: np.ndarray | None, source: np.ndarray) -> dict[str, object] | None:
    if truth is None:
        return None
    return asdict(calculate_mask_metrics(page.mask, truth, crop_coverage=_coverage_for_page(page), source_image=source))


def _spread_reference_mask(frame: np.ndarray, luminance: int = 125) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    mask = np.where(cv2.GaussianBlur(gray, (9, 9), 0) >= luminance, 255, 0).astype(np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))


def run_extraction_orders(
    frame: np.ndarray,
    segmenter: PageSegmenter,
    roi_config: ROIConfig = ROIConfig(),
    truth_full_masks: dict[PageSide, np.ndarray] | None = None,
) -> tuple[list[OrderSideResult], dict[str, np.ndarray]]:
    results: list[OrderSideResult] = []
    artifacts: dict[str, np.ndarray] = {}
    rois = extract_page_rois(frame, roi_config)

    def truth_for_roi(side: PageSide, roi: PageROI) -> np.ndarray | None:
        if not truth_full_masks or side not in truth_full_masks:
            return None
        ox, oy = roi.origin
        width, height = roi.size
        return truth_full_masks[side][oy : oy + height, ox : ox + width].copy()

    # A: split -> rough segment/warp -> refined segment/crop.
    for side, roi in rois.items():
        rough = _segment(roi.image, side, segmenter)
        if rough is None:
            results.append(OrderSideResult("A", side.value, "failed", "NO_ROUGH_PAGE", ("center_split", "rough_segment"), 0, {}))
            continue
        artifacts[f"A_{side.value}_rough_mask"] = rough.mask
        warp = warp_from_mask(roi.image, rough.mask)
        if not warp.success:
            results.append(OrderSideResult("A", side.value, "failed", warp.reason, ("center_split", "rough_segment", "coarse_warp"), 0, warp.diagnostics))
            continue
        refined = _segment(warp.image, side, segmenter)
        if refined is None:
            results.append(OrderSideResult("A", side.value, "failed", "NO_PAGE_AFTER_WARP", ("center_split", "coarse_warp", "page_crop"), 1, warp.diagnostics))
            continue
        crop, _ = _crop_local(warp.image, refined)
        artifacts[f"A_{side.value}_crop"] = crop
        local_truth = truth_for_roi(side, roi)
        warped_truth = (
            cv2.warpPerspective(local_truth, warp.matrix, (warp.image.shape[1], warp.image.shape[0]), flags=cv2.INTER_NEAREST)
            if local_truth is not None and warp.matrix is not None else None
        )
        results.append(OrderSideResult("A", side.value, "page", None, ("center_split", "coarse_warp", "page_crop"), 1, warp.diagnostics, _metrics(refined, warped_truth, warp.image)))

    # B: one spread reference/warp -> split -> crop.  It deliberately uses
    # one homography for both V-shaped planes as the approved counter-baseline.
    spread_mask = _spread_reference_mask(frame)
    artifacts["B_spread_rough_mask"] = spread_mask
    spread_warp = warp_from_mask(frame, spread_mask)
    if not spread_warp.success:
        for side in PageSide:
            results.append(OrderSideResult("B", side.value, "not_run", "NOT_RUN_NO_REFERENCE", ("spread_reference",), 0, spread_warp.diagnostics))
    else:
        warped_truth_full = {
            side: cv2.warpPerspective(mask, spread_warp.matrix, (spread_warp.image.shape[1], spread_warp.image.shape[0]), flags=cv2.INTER_NEAREST)
            for side, mask in (truth_full_masks or {}).items()
        }
        for side, roi in extract_page_rois(spread_warp.image, roi_config).items():
            page = _segment(roi.image, side, segmenter)
            if page is None:
                results.append(OrderSideResult("B", side.value, "failed", "NO_PAGE_AFTER_SPREAD_WARP", ("spread_coarse_warp", "center_split", "page_crop"), 1, spread_warp.diagnostics))
                continue
            crop, _ = _crop_local(roi.image, page)
            artifacts[f"B_{side.value}_crop"] = crop
            ox, oy = roi.origin
            width, height = roi.size
            truth = warped_truth_full.get(side)
            truth = truth[oy : oy + height, ox : ox + width] if truth is not None else None
            results.append(OrderSideResult("B", side.value, "page", None, ("spread_coarse_warp", "center_split", "page_crop"), 1, spread_warp.diagnostics, _metrics(page, truth, roi.image)))

    # C: split -> curved-mask crop -> coarse warp.
    for side, roi in rois.items():
        page = _segment(roi.image, side, segmenter)
        if page is None:
            results.append(OrderSideResult("C", side.value, "failed", "NO_PAGE", ("center_split", "page_crop"), 0, {}))
            continue
        crop, crop_mask = _crop_local(roi.image, page)
        artifacts[f"C_{side.value}_crop_before_warp"] = crop
        warp = warp_from_mask(crop, crop_mask)
        if not warp.success:
            results.append(OrderSideResult("C", side.value, "failed", warp.reason, ("center_split", "page_crop", "coarse_warp"), 0, warp.diagnostics))
            continue
        artifacts[f"C_{side.value}_warped"] = warp.image
        results.append(OrderSideResult("C", side.value, "page", None, ("center_split", "page_crop", "coarse_warp"), 1, warp.diagnostics, _metrics(page, truth_for_roi(side, roi), roi.image)))
    return results, artifacts


def serialize_order_results(results: list[OrderSideResult]) -> list[dict[str, object]]:
    return [asdict(result) for result in results]
