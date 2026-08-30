"""Offline seam experiment orchestration, isolated from the session loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable
import time

import cv2
import numpy as np

from book_scanner.detect.page_mask import build_page_mask
from book_scanner.detect.roi import ROIConfig, PageSide, extract_page_rois
from book_scanner.detect.segmenter import PageSegmenter
from book_scanner.detect.spine_seam import OwnershipResult, SpineSeamDetector, apply_seam_ownership
from book_scanner.evaluation.seam_metrics import calculate_seam_metrics, serialize_seam_metrics


@dataclass(frozen=True)
class SeamMethodSpec:
    key: str
    detector: SpineSeamDetector
    policy: str = "union-preserving"
    save_artifacts: bool = True


@dataclass(frozen=True)
class SeamMethodEvaluation:
    method: str
    policy: str
    status: str
    reason: str | None
    confidence: float | None
    seam_diagnostics: dict[str, object]
    ownership_diagnostics: dict[str, object] | None
    metrics: dict[str, object] | None
    processing_ms: float


def extract_full_page_masks(
    frame: np.ndarray,
    segmenter: PageSegmenter,
    roi_config: ROIConfig = ROIConfig(spine_overlap_fraction=0.06),
) -> tuple[dict[PageSide, np.ndarray], dict[str, np.ndarray], dict[str, object]]:
    height, width = frame.shape[:2]
    full_masks = {side: np.zeros((height, width), dtype=np.uint8) for side in PageSide}
    artifacts: dict[str, np.ndarray] = {}
    diagnostics: dict[str, object] = {"sides": {}}
    for side, roi in extract_page_rois(frame, roi_config).items():
        raw = segmenter.segment(roi)
        page = build_page_mask(roi, raw)
        artifacts[f"{side.value}_raw_mask"] = np.where(raw.mask > 0, 255, 0).astype(np.uint8)
        if page is None:
            diagnostics["sides"][side.value] = {"status": "no_page", **dict(raw.diagnostics)}
            continue
        ox, oy = roi.origin
        roi_width, roi_height = roi.size
        full_masks[side][oy : oy + roi_height, ox : ox + roi_width] = page.mask
        artifacts[f"{side.value}_page_mask_full"] = full_masks[side]
        diagnostics["sides"][side.value] = {
            "status": "page",
            "bbox_full": list(page.bbox_full),
            "confidence": page.confidence,
            **page.diagnostics,
        }
    return full_masks, artifacts, diagnostics


def _overlay(frame: np.ndarray, ownership: OwnershipResult, seam_points: tuple[tuple[int, int], ...]) -> np.ndarray:
    image = frame.copy()
    tint = np.zeros_like(image)
    left, right = ownership.left_mask > 0, ownership.right_mask > 0
    tint[left] = (0, 210, 0)
    tint[right] = (210, 0, 210)
    tint[ownership.ambiguous_mask > 0] = (0, 220, 255)
    selected = left | right | (ownership.ambiguous_mask > 0)
    image[selected] = cv2.addWeighted(image[selected], 0.58, tint[selected], 0.42, 0)
    points = np.asarray(seam_points, dtype=np.int32).reshape(-1, 1, 2)
    cv2.polylines(image, [points], False, (0, 0, 255), 3)
    return image


def _cost_visual(cost: np.ndarray, frame_shape: tuple[int, int], origin_x: int) -> np.ndarray:
    finite = np.isfinite(cost)
    normalized = np.zeros(cost.shape, dtype=np.uint8)
    if np.any(finite):
        values = cost[finite]
        low, high = float(np.percentile(values, 2)), float(np.percentile(values, 98))
        normalized = np.clip((cost - low) * 255.0 / max(1e-6, high - low), 0, 255).astype(np.uint8)
    colored = cv2.applyColorMap(255 - normalized, cv2.COLORMAP_TURBO)
    full = np.zeros((*frame_shape, 3), dtype=np.uint8)
    x1 = min(frame_shape[1], origin_x + colored.shape[1])
    full[:, origin_x:x1] = colored[:, : x1 - origin_x]
    return full


def crop_from_mask(frame: np.ndarray, mask: np.ndarray, padding_fraction: float = 0.03) -> np.ndarray | None:
    points = cv2.findNonZero(np.where(mask > 0, 255, 0).astype(np.uint8))
    if points is None:
        return None
    x, y, width, height = cv2.boundingRect(points)
    px, py = round(width * padding_fraction), round(height * padding_fraction)
    x0, y0 = max(0, x - px), max(0, y - py)
    x1, y1 = min(frame.shape[1], x + width + px), min(frame.shape[0], y + height + py)
    return frame[y0:y1, x0:x1].copy()


def run_seam_experiment(
    frame: np.ndarray,
    segmenter: PageSegmenter,
    specs: Iterable[SeamMethodSpec],
    truth_masks: dict[PageSide, np.ndarray] | None = None,
    roi_config: ROIConfig = ROIConfig(spine_overlap_fraction=0.06),
) -> tuple[list[SeamMethodEvaluation], dict[str, np.ndarray], dict[str, object]]:
    masks, artifacts, extraction_diagnostics = extract_full_page_masks(frame, segmenter, roi_config)
    evaluations: list[SeamMethodEvaluation] = []
    detection_cache: dict[tuple[str, str], tuple[object, float]] = {}
    if truth_masks is not None:
        baseline_metrics = calculate_seam_metrics(frame, masks, masks, truth_masks)
        evaluations.append(SeamMethodEvaluation(
            "overlap-baseline", "none", "page", None, None, {},
            {
                "prediction_overlap_px_before": baseline_metrics.prediction_overlap_px_before,
                "prediction_overlap_px_after": baseline_metrics.prediction_overlap_px_after,
                "union_lost_px": 0,
            },
            serialize_seam_metrics(baseline_metrics),
            0.0,
        ))
    for spec in specs:
        cache_key = (
            getattr(spec.detector, "name", type(spec.detector).__name__),
            repr(getattr(spec.detector, "config", None)),
        )
        cached = detection_cache.get(cache_key)
        if cached is None:
            started = time.perf_counter()
            detected = spec.detector.detect(frame, masks[PageSide.LEFT], masks[PageSide.RIGHT])
            detection_ms = (time.perf_counter() - started) * 1000.0
            detection_cache[cache_key] = (detected, detection_ms)
        else:
            detected, detection_ms = cached
        if detected.seam is None:
            evaluations.append(SeamMethodEvaluation(
                spec.key, spec.policy, "no_page" if detected.reason == "NO_PAGE" else "failed",
                detected.reason, None, dict(detected.diagnostics), None, None, detection_ms,
            ))
            if detected.cost_map is not None:
                artifacts[f"{spec.key}_{spec.policy}_cost"] = _cost_visual(detected.cost_map, frame.shape[:2], detected.band_origin_x)
            continue
        ownership_started = time.perf_counter()
        ownership = apply_seam_ownership(
            masks[PageSide.LEFT], masks[PageSide.RIGHT], detected.seam, policy=spec.policy
        )
        metrics = calculate_seam_metrics(
            frame,
            masks,
            {PageSide.LEFT: ownership.left_mask, PageSide.RIGHT: ownership.right_mask},
            truth_masks,
            ownership.ambiguous_mask,
        ) if truth_masks is not None else None
        processing_ms = detection_ms + (time.perf_counter() - ownership_started) * 1000.0
        key = f"{spec.key}_{spec.policy}"
        if spec.save_artifacts:
            artifacts[f"{key}_overlay"] = _overlay(frame, ownership, detected.seam.points_full)
            artifacts[f"{key}_left_mask"] = ownership.left_mask
            artifacts[f"{key}_right_mask"] = ownership.right_mask
            artifacts[f"{key}_ambiguous"] = ownership.ambiguous_mask
            for side, conservative in (
                (PageSide.LEFT, ownership.left_conservative_mask),
                (PageSide.RIGHT, ownership.right_conservative_mask),
            ):
                crop = crop_from_mask(frame, conservative)
                if crop is not None:
                    artifacts[f"{key}_{side.value}_conservative_crop"] = crop
            if detected.cost_map is not None:
                artifacts[f"{key}_cost"] = _cost_visual(detected.cost_map, frame.shape[:2], detected.band_origin_x)
        evaluations.append(SeamMethodEvaluation(
            spec.key,
            spec.policy,
            "page",
            None,
            detected.seam.confidence,
            dict(detected.seam.diagnostics),
            dict(ownership.diagnostics),
            serialize_seam_metrics(metrics),
            processing_ms,
        ))
    return evaluations, artifacts, extraction_diagnostics


def serialize_evaluations(evaluations: list[SeamMethodEvaluation]) -> list[dict[str, object]]:
    return [asdict(evaluation) for evaluation in evaluations]
