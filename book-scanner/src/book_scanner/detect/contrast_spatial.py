"""Black-background contrast plus external-contour page candidate.

Canny is an allowed boundary signal.  What this detector deliberately avoids
is declaring the largest rectangle/contour to be the page based on size alone.
Candidates combine brightness contrast, exterior-contour topology, spatial
coverage, dark-background adjacency, and edge support.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from book_scanner.detect.roi import PageROI
from book_scanner.detect.segmenter import SegmentationResult


@dataclass(frozen=True)
class ContrastSpatialConfig:
    min_page_luminance: int = 125
    blur_kernel_px: int = 9
    close_kernel_px: int = 31
    canny_low: int = 35
    canny_high: int = 110
    min_candidate_area_ratio: float = 0.12
    max_candidate_area_ratio: float = 0.96
    min_height_ratio: float = 0.45
    min_inside_luminance: float = 140.0
    min_contrast_score: float = 0.45
    min_score: float = 0.62


class ContrastSpatialPageSegmenter:
    name = "contrast-spatial"

    def __init__(self, config: ContrastSpatialConfig = ContrastSpatialConfig()):
        self.config = config

    def segment(self, roi: PageROI) -> SegmentationResult:
        cfg = self.config
        gray = cv2.cvtColor(roi.image, cv2.COLOR_BGR2GRAY) if roi.image.ndim == 3 else roi.image
        blur_size = cfg.blur_kernel_px if cfg.blur_kernel_px % 2 else cfg.blur_kernel_px + 1
        blurred = cv2.GaussianBlur(gray, (max(1, blur_size), max(1, blur_size)), 0)
        bright = np.where((blurred >= cfg.min_page_luminance) & (roi.allowed_mask > 0), 255, 0).astype(np.uint8)

        close_size = cfg.close_kernel_px if cfg.close_kernel_px % 2 else cfg.close_kernel_px + 1
        if close_size > 1:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size))
            bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, kernel)

        edges = cv2.Canny(blurred, cfg.canny_low, cfg.canny_high)
        edges[roi.allowed_mask == 0] = 0
        contours, _hierarchy = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        allowed_area = max(1, int(np.count_nonzero(roi.allowed_mask)))
        roi_h, roi_w = gray.shape[:2]
        candidates: list[dict[str, object]] = []

        for contour in contours:
            area = float(cv2.contourArea(contour))
            area_ratio = area / allowed_area
            x, y, width, height = cv2.boundingRect(contour)
            height_ratio = height / max(1, roi_h)
            if not (cfg.min_candidate_area_ratio <= area_ratio <= cfg.max_candidate_area_ratio):
                continue
            if height_ratio < cfg.min_height_ratio:
                continue

            filled = np.zeros(gray.shape, dtype=np.uint8)
            cv2.drawContours(filled, [contour], -1, 255, thickness=cv2.FILLED)
            filled[roi.allowed_mask == 0] = 0
            inside = filled > 0
            if not np.any(inside):
                continue
            ring_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))
            ring = (cv2.dilate(filled, ring_kernel) > 0) & ~inside & (roi.allowed_mask > 0)
            inside_mean = float(gray[inside].mean())
            ring_mean = float(gray[ring].mean()) if np.any(ring) else inside_mean
            contrast_score = float(np.clip((inside_mean - ring_mean) / 128.0, 0.0, 1.0))
            if inside_mean < cfg.min_inside_luminance or contrast_score < cfg.min_contrast_score:
                continue

            boundary = cv2.morphologyEx(filled, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
            dilated_edges = cv2.dilate(edges, np.ones((5, 5), np.uint8)) > 0
            boundary_count = int(np.count_nonzero(boundary))
            edge_support = (
                int(np.count_nonzero(boundary & dilated_edges)) / boundary_count if boundary_count else 0.0
            )
            coverage_score = float(np.clip((height_ratio - cfg.min_height_ratio) / 0.45, 0.0, 1.0))
            # Area participates only as a broad plausibility preference; it
            # cannot win without contrast/edge/spatial evidence.
            area_score = float(np.clip(1.0 - abs(area_ratio - 0.42) / 0.42, 0.0, 1.0))
            score = 0.40 * contrast_score + 0.30 * edge_support + 0.20 * coverage_score + 0.10 * area_score
            candidates.append({
                "contour": contour,
                "mask": filled,
                "score": score,
                "area_ratio": area_ratio,
                "height_ratio": height_ratio,
                "inside_luminance": inside_mean,
                "outside_ring_luminance": ring_mean,
                "contrast_score": contrast_score,
                "edge_support": edge_support,
                "bbox": [x, y, width, height],
            })

        if not candidates:
            return SegmentationResult(
                np.zeros(gray.shape, dtype=np.uint8),
                0.0,
                {"reason": "no_supported_external_contour", "external_contour_count": len(contours)},
            )

        selected = max(candidates, key=lambda candidate: float(candidate["score"]))
        score = float(selected["score"])
        if score < cfg.min_score:
            return SegmentationResult(
                np.zeros(gray.shape, dtype=np.uint8),
                score,
                {
                    "reason": "external_contour_score_below_threshold",
                    "external_contour_count": len(contours),
                    "candidate_count": len(candidates),
                    "best_score": score,
                },
            )

        diagnostics = {
            key: value for key, value in selected.items() if key not in {"contour", "mask"}
        }
        diagnostics.update({
            "source": "black_background_external_contour",
            "retrieval_mode": "RETR_EXTERNAL",
            "external_contour_count": len(contours),
            "candidate_count": len(candidates),
            "decision": "multi_signal_score_not_area_only",
        })
        return SegmentationResult(np.asarray(selected["mask"]).copy(), score, diagnostics)
