"""One common offline runner for replaceable page segmenters."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from book_scanner.detect.page_mask import MaskPostprocessConfig, PageMask, build_page_mask, crop_page
from book_scanner.detect.roi import ROIConfig, PageROI, PageSide, extract_page_rois
from book_scanner.detect.segmenter import PageSegmenter


@dataclass(frozen=True)
class MaskMetrics:
    iou: float
    dice: float
    boundary_f1: float
    page_recall: float
    background_leakage: float
    missed_page_px: int
    extra_background_px: int
    safe_crop_page_recall: float
    content_proxy_recall: float
    crop_missed_page_px: int
    bbox_edge_delta: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class SideEvaluation:
    side: str
    status: str
    confidence: float | None
    area_ratio: float
    centroid: tuple[float, float] | None
    bbox_full: tuple[int, int, int, int] | None
    edge_contacts: dict[str, bool]
    processing_ms: float
    diagnostics: dict[str, object]
    metrics: MaskMetrics | None = None


def read_image(path: Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray:
    """Read through bytes so Windows non-ASCII paths do not depend on cv2 path handling."""
    path = Path(path)
    try:
        encoded = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    except OSError as exc:
        raise ValueError(f"could not read image: {path}") from exc
    image = cv2.imdecode(encoded, flags)
    if image is None:
        raise ValueError(f"could not decode image: {path}")
    return image


def write_image(path: Path, image: np.ndarray) -> None:
    """Encode first and fail loudly instead of accepting cv2.imwrite(False)."""
    path = Path(path)
    suffix = path.suffix or ".png"
    ok, encoded = cv2.imencode(suffix, image)
    if not ok:
        raise ValueError(f"could not encode image for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded.tobytes())


def calculate_mask_metrics(
    predicted: np.ndarray,
    truth: np.ndarray,
    boundary_tolerance_px: int = 2,
    crop_coverage: np.ndarray | None = None,
    source_image: np.ndarray | None = None,
) -> MaskMetrics:
    if predicted.shape[:2] != truth.shape[:2]:
        raise ValueError("predicted and truth masks must have the same dimensions")
    pred = predicted > 0
    target = truth > 0
    intersection = int(np.count_nonzero(pred & target))
    union = int(np.count_nonzero(pred | target))
    pred_count = int(np.count_nonzero(pred))
    target_count = int(np.count_nonzero(target))
    iou = intersection / union if union else 1.0
    dice_denom = pred_count + target_count
    dice = (2.0 * intersection / dice_denom) if dice_denom else 1.0
    missed_page_px = int(np.count_nonzero(target & ~pred))
    extra_background_px = int(np.count_nonzero(pred & ~target))
    page_recall = intersection / target_count if target_count else 1.0
    background_leakage = extra_background_px / pred_count if pred_count else 0.0

    kernel = np.ones((3, 3), dtype=np.uint8)
    pred_u8 = pred.astype(np.uint8) * 255
    target_u8 = target.astype(np.uint8) * 255
    pred_boundary = cv2.morphologyEx(pred_u8, cv2.MORPH_GRADIENT, kernel) > 0
    target_boundary = cv2.morphologyEx(target_u8, cv2.MORPH_GRADIENT, kernel) > 0
    radius = max(0, boundary_tolerance_px)
    tolerance_kernel = np.ones((radius * 2 + 1, radius * 2 + 1), dtype=np.uint8)
    pred_near = cv2.dilate(pred_boundary.astype(np.uint8), tolerance_kernel) > 0
    target_near = cv2.dilate(target_boundary.astype(np.uint8), tolerance_kernel) > 0
    pred_boundary_count = int(np.count_nonzero(pred_boundary))
    target_boundary_count = int(np.count_nonzero(target_boundary))
    precision = (
        int(np.count_nonzero(pred_boundary & target_near)) / pred_boundary_count
        if pred_boundary_count
        else float(target_boundary_count == 0)
    )
    recall = (
        int(np.count_nonzero(target_boundary & pred_near)) / target_boundary_count
        if target_boundary_count
        else float(pred_boundary_count == 0)
    )
    boundary_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    covered = (crop_coverage > 0) if crop_coverage is not None else pred
    safe_crop_intersection = int(np.count_nonzero(target & covered))
    safe_crop_page_recall = safe_crop_intersection / target_count if target_count else 1.0
    crop_missed_page_px = int(np.count_nonzero(target & ~covered))

    def bounds(binary: np.ndarray) -> tuple[int, int, int, int] | None:
        ys, xs = np.nonzero(binary)
        return None if not len(xs) else (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))

    pred_bounds, target_bounds = bounds(pred), bounds(target)
    bbox_edge_delta = (
        tuple(pred_bounds[index] - target_bounds[index] for index in range(4))
        if pred_bounds is not None and target_bounds is not None
        else None
    )

    content_proxy_recall = safe_crop_page_recall
    if source_image is not None:
        if source_image.shape[:2] != truth.shape[:2]:
            raise ValueError("source image and truth mask must have the same dimensions")
        gray = cv2.cvtColor(source_image, cv2.COLOR_BGR2GRAY) if source_image.ndim == 3 else source_image
        content_proxy = (cv2.Canny(gray, 45, 135) > 0) & target
        proxy_count = int(np.count_nonzero(content_proxy))
        content_proxy_recall = (
            int(np.count_nonzero(content_proxy & covered)) / proxy_count if proxy_count else safe_crop_page_recall
        )

    return MaskMetrics(
        iou=iou,
        dice=dice,
        boundary_f1=boundary_f1,
        page_recall=page_recall,
        background_leakage=background_leakage,
        missed_page_px=missed_page_px,
        extra_background_px=extra_background_px,
        safe_crop_page_recall=safe_crop_page_recall,
        content_proxy_recall=content_proxy_recall,
        crop_missed_page_px=crop_missed_page_px,
        bbox_edge_delta=bbox_edge_delta,
    )


def _overlay(roi: PageROI, page_mask: PageMask | None) -> np.ndarray:
    image = roi.image.copy()
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if page_mask is None:
        return image
    green = np.zeros_like(image)
    green[:, :, 1] = 255
    selected = page_mask.mask > 0
    image[selected] = cv2.addWeighted(image[selected], 0.55, green[selected], 0.45, 0)
    x, y, width, height = page_mask.bbox
    cv2.rectangle(image, (x, y), (x + width - 1, y + height - 1), (0, 0, 255), 2)
    return image


def _comparison_overlay(roi: PageROI, predicted: np.ndarray, truth: np.ndarray) -> np.ndarray:
    image = roi.image.copy()
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    pred, target = predicted > 0, truth > 0
    # Green: overlap, red: missed page, blue: extra background.
    tint = np.zeros_like(image)
    tint[pred & target] = (0, 255, 0)
    tint[target & ~pred] = (0, 0, 255)
    tint[pred & ~target] = (255, 0, 0)
    selected = pred | target
    image[selected] = cv2.addWeighted(image[selected], 0.45, tint[selected], 0.55, 0)
    return image


def _load_truth(path: Path | None, roi: PageROI) -> np.ndarray | None:
    if path is None or not path.exists():
        return None
    truth = read_image(path, cv2.IMREAD_GRAYSCALE)
    if truth.shape == roi.allowed_mask.shape:
        return truth
    full_w, full_h = roi.full_frame_size
    if truth.shape == (full_h, full_w):
        ox, oy = roi.origin
        roi_w, roi_h = roi.size
        return truth[oy : oy + roi_h, ox : ox + roi_w]
    raise ValueError(f"ground-truth mask {path} has incompatible size {truth.shape}")


def evaluate_frame(
    frame: np.ndarray,
    output_dir: Path,
    segmenter: PageSegmenter,
    roi_config: ROIConfig = ROIConfig(),
    postprocess_config: MaskPostprocessConfig = MaskPostprocessConfig(),
    truth_paths: dict[PageSide, Path] | None = None,
    truth_masks: dict[PageSide, np.ndarray] | None = None,
    neutralize_outside: bool = False,
) -> list[SideEvaluation]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_image(output_dir / "raw.png", frame)
    rois = extract_page_rois(frame, roi_config)
    evaluations: list[SideEvaluation] = []
    for side, roi in rois.items():
        started = time.perf_counter()
        raw_result = segmenter.segment(roi)
        page_mask = build_page_mask(roi, raw_result, postprocess_config)
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        write_image(output_dir / f"{side.value}_roi.png", roi.image)
        write_image(
            output_dir / f"{side.value}_mask.png",
            page_mask.mask if page_mask is not None else np.zeros(roi.image.shape[:2], dtype=np.uint8),
        )
        write_image(output_dir / f"{side.value}_overlay.png", _overlay(roi, page_mask))

        metrics = None
        if page_mask is not None:
            crop = crop_page(frame, page_mask, neutralize_outside=neutralize_outside)
            write_image(output_dir / f"{side.value}_crop.png", crop.image)
            truth = (truth_masks or {}).get(side)
            if truth is not None:
                truth = np.asarray(truth)
                if truth.shape != roi.allowed_mask.shape:
                    raise ValueError(f"ground-truth mask for {side.value} has incompatible size {truth.shape}")
            else:
                truth = _load_truth((truth_paths or {}).get(side), roi)
            if truth is not None:
                crop_coverage = np.zeros(roi.image.shape[:2], dtype=np.uint8)
                crop_x, crop_y, crop_w, crop_h = crop.bbox_full
                local_x, local_y = crop_x - roi.origin[0], crop_y - roi.origin[1]
                crop_coverage[local_y : local_y + crop_h, local_x : local_x + crop_w] = 255
                metrics = calculate_mask_metrics(
                    page_mask.mask,
                    truth,
                    crop_coverage=crop_coverage,
                    source_image=roi.image,
                )
                write_image(output_dir / f"{side.value}_truth.png", np.where(truth > 0, 255, 0).astype(np.uint8))
                write_image(
                    output_dir / f"{side.value}_comparison.png",
                    _comparison_overlay(roi, page_mask.mask, truth),
                )
            evaluation = SideEvaluation(
                side=side.value,
                status="page",
                confidence=page_mask.confidence,
                area_ratio=page_mask.area_ratio,
                centroid=page_mask.centroid_full,
                bbox_full=page_mask.bbox_full,
                edge_contacts=page_mask.edge_contacts,
                processing_ms=elapsed_ms,
                diagnostics=page_mask.diagnostics,
                metrics=metrics,
            )
        else:
            no_page_diagnostics = dict(raw_result.diagnostics)
            no_page_diagnostics["postprocess_reason"] = "no_plausible_page_component"
            evaluation = SideEvaluation(
                side=side.value,
                status="no_page",
                confidence=raw_result.confidence,
                area_ratio=0.0,
                centroid=None,
                bbox_full=None,
                edge_contacts={},
                processing_ms=elapsed_ms,
                diagnostics=no_page_diagnostics,
            )
            truth = (truth_masks or {}).get(side)
            if truth is None:
                truth = _load_truth((truth_paths or {}).get(side), roi)
            if truth is not None:
                zero = np.zeros(roi.image.shape[:2], dtype=np.uint8)
                metrics = calculate_mask_metrics(zero, truth, crop_coverage=zero, source_image=roi.image)
                write_image(output_dir / f"{side.value}_truth.png", np.where(truth > 0, 255, 0).astype(np.uint8))
                write_image(output_dir / f"{side.value}_comparison.png", _comparison_overlay(roi, zero, truth))
                evaluation = SideEvaluation(**{**asdict(evaluation), "metrics": metrics})
        evaluations.append(evaluation)

    payload = [asdict(item) for item in evaluations]
    (output_dir / "diagnostics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return evaluations


def evaluate_image(
    image_path: Path,
    output_dir: Path,
    segmenter: PageSegmenter,
    **kwargs,
) -> list[SideEvaluation]:
    image_path = Path(image_path)
    frame = read_image(image_path)
    return evaluate_frame(frame, output_dir, segmenter, **kwargs)
