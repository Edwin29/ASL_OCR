"""Candidate analysis, bounded sample windows, and stability selection."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

import cv2
import numpy as np

from book_scanner.detect.contrast_spatial import ContrastSpatialPageSegmenter
from book_scanner.detect.page_mask import PageMask
from book_scanner.detect.roi import PageSide as DetectPageSide, ROIConfig
from book_scanner.session.mask_pipeline import MaskFramePipeline

from .config import CandidatePolicy
from .obstruction import EdgeChromaIntrusionObstructionDetector, ObstructionDetector
from .protocols import FrameSample
from .types import FrameCandidate, PageSide, ReadinessReason


@dataclass(frozen=True, slots=True)
class CandidateObservation:
    frame: FrameSample[np.ndarray] = field(compare=False)
    candidate: FrameCandidate
    page_centroids: tuple[tuple[float, float], tuple[float, float]]
    page_area_fractions: tuple[float, float]
    seam_proxy_fraction: float | None
    mask_preview: np.ndarray = field(repr=False, compare=False)
    gray_preview: np.ndarray = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class StabilityAssessment:
    stable: bool
    observations_considered: int
    reasons: tuple[ReadinessReason, ...] = ()
    best: CandidateObservation | None = None
    metrics: tuple[tuple[str, float | int | bool], ...] = ()


class CandidateAnalyzer(Protocol):
    def analyze(self, frame: FrameSample[np.ndarray]) -> CandidateObservation: ...


class CandidateWindow:
    """A bounded history that reports when an old observation was discarded."""

    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._items: deque[CandidateObservation] = deque(maxlen=capacity)

    def append(self, observation: CandidateObservation) -> bool:
        dropped = len(self._items) == self.capacity
        self._items.append(observation)
        return dropped

    def clear(self) -> None:
        self._items.clear()

    def snapshot(self) -> tuple[CandidateObservation, ...]:
        return tuple(self._items)

    def __len__(self) -> int:
        return len(self._items)


class OpenCVCandidateAnalyzer:
    """Cheap fixed-layout analysis used only to schedule expensive work.

    Page candidates reuse the existing contrast/external-contour multi-signal
    path.  These masks are not declared final page extraction; V2 remains the
    owner of seam-conservative artifact generation.
    """

    evaluator_version = "opencv-candidate-v1.2.2"

    def __init__(
        self,
        policy: CandidatePolicy = CandidatePolicy(),
        mask_pipeline: MaskFramePipeline | None = None,
        obstruction_detector: ObstructionDetector | None = None,
    ):
        self.policy = policy
        self.mask_pipeline = mask_pipeline or MaskFramePipeline(
            ContrastSpatialPageSegmenter(),
            ROIConfig(spine_overlap_fraction=policy.preview_spine_overlap_fraction),
        )
        self.obstruction_detector = (
            obstruction_detector
            if obstruction_detector is not None
            else EdgeChromaIntrusionObstructionDetector()
        )

    def evaluate(self, frame: FrameSample[np.ndarray]) -> FrameCandidate:
        return self.analyze(frame).candidate

    def analyze(self, frame: FrameSample[np.ndarray]) -> CandidateObservation:
        image = frame.payload
        if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3 or image.size == 0:
            raise ValueError("candidate frame must be a non-empty HxWx3 BGR image")
        height, width = image.shape[:2]
        reasons: list[ReadinessReason] = []
        if width < self.policy.min_frame_width or height < self.policy.min_frame_height:
            reasons.append(ReadinessReason.INSUFFICIENT_RESOLUTION)

        preview_image = _preview_image(image, self.policy.preview_max_dimension)
        preview_height, preview_width = preview_image.shape[:2]
        pages = self.mask_pipeline.process(preview_image)
        left = pages[DetectPageSide.LEFT].page_mask
        right = pages[DetectPageSide.RIGHT].page_mask
        outer_contact = bool(
            (left is not None and left.touches_outer_frame)
            or (right is not None and right.touches_outer_frame)
        )
        if left is None or right is None:
            reasons.append(ReadinessReason.PAGE_NOT_FOUND)
        elif outer_contact and self.policy.reject_outer_frame_contacts:
            reasons.append(ReadinessReason.OUT_OF_FRAME)

        full_mask = np.zeros((preview_height, preview_width), dtype=np.uint8)
        side_masks = {
            PageSide.LEFT: np.zeros_like(full_mask),
            PageSide.RIGHT: np.zeros_like(full_mask),
        }
        for side, page_mask in ((PageSide.LEFT, left), (PageSide.RIGHT, right)):
            if page_mask is not None:
                _paste_mask(full_mask, page_mask)
                _paste_mask(side_masks[side], page_mask)

        obstruction = self.obstruction_detector.detect(preview_image, side_masks)
        if obstruction.content_occluded:
            reasons.append(ReadinessReason.CONTENT_OCCLUDED)

        gray = cv2.cvtColor(preview_image, cv2.COLOR_BGR2GRAY)
        clipping = _clipping_evidence(gray, side_masks, left, right, self.policy)
        if clipping["confirmed_content_clipping"] and self.policy.reject_confirmed_content_clipping:
            reasons.append(ReadinessReason.OUT_OF_FRAME)

        page_values = gray[full_mask > 0]
        if page_values.size:
            white_clip = float(np.mean(page_values >= 250))
            black_clip = float(np.mean(page_values <= 5))
            if white_clip > self.policy.max_white_clip_fraction:
                reasons.append(ReadinessReason.OVEREXPOSED)
            if black_clip > self.policy.max_black_clip_fraction:
                reasons.append(ReadinessReason.UNDEREXPOSED)
        else:
            white_clip = 0.0
            black_clip = 1.0

        edge_margin = _physical_edge_margin(left, right, preview_width, preview_height)
        mask_confidence = min(_confidence(left), _confidence(right))
        illumination_range = _grid_illumination_range(gray, full_mask)
        tenengrad, laplacian = _sharpness(gray, full_mask)
        centroids = (
            _normalized_centroid(left, preview_width, preview_height),
            _normalized_centroid(right, preview_width, preview_height),
        )
        areas = (
            _full_area_fraction(left, preview_width, preview_height),
            _full_area_fraction(right, preview_width, preview_height),
        )
        seam_proxy, seam_dispersion, seam_confidence = _luminance_seam_proxy(
            gray,
            left,
            right,
            self.policy.preview_seam_half_width_fraction,
            self.policy.preview_seam_center_prior_weight,
        )
        if seam_proxy is None:
            reasons.append(ReadinessReason.SEAM_FAILED)
        metrics = {
            "page_pair_found": left is not None and right is not None,
            "source_width": width,
            "source_height": height,
            "preview_width": preview_width,
            "preview_height": preview_height,
            "physical_edge_margin_fraction": edge_margin,
            "outer_frame_contact_warning": outer_contact,
            "outer_frame_contacts_are_hard_gate": self.policy.reject_outer_frame_contacts,
            "left_top_contact": bool(left and left.edge_contacts["top"]),
            "left_bottom_contact": bool(left and left.edge_contacts["bottom"]),
            "left_outer_contact": bool(left and left.edge_contacts["outer"]),
            "right_top_contact": bool(right and right.edge_contacts["top"]),
            "right_bottom_contact": bool(right and right.edge_contacts["bottom"]),
            "right_outer_contact": bool(right and right.edge_contacts["outer"]),
            **clipping,
            "mask_confidence_min": mask_confidence,
            "white_clip_fraction": white_clip,
            "black_clip_fraction": black_clip,
            "illumination_range": illumination_range,
            "tenengrad": tenengrad,
            "laplacian_variance": laplacian,
            "left_area_fraction": areas[0],
            "right_area_fraction": areas[1],
            "seam_proxy_fraction": seam_proxy,
            "seam_dispersion_fraction": seam_dispersion,
            "seam_proxy_confidence": seam_confidence,
            "seam_proxy_available": seam_proxy is not None,
            "obstruction_detected": obstruction.detected,
            "content_occluded": obstruction.content_occluded,
            "obstruction_confidence": obstruction.confidence,
            "obstruction_side": obstruction.side.value if obstruction.side else None,
            "obstruction_bbox_preview": (
                ",".join(str(value) for value in obstruction.bbox_preview)
                if obstruction.bbox_preview
                else None
            ),
            "obstruction_component_area_fraction": obstruction.component_area_fraction,
            "obstruction_content_overlap_fraction": obstruction.content_overlap_fraction,
            "obstruction_detector": obstruction.detector_name,
            "obstruction_detector_version": obstruction.detector_version,
            "obstruction_runtime_provenance": obstruction.runtime_provenance,
        }
        candidate = FrameCandidate(
            frame_id=frame.frame_id,
            captured_at_monotonic=frame.captured_at_monotonic,
            width=width,
            height=height,
            evaluator_version=self.evaluator_version,
            metrics=metrics,
            retry_reasons=tuple(dict.fromkeys(reasons)),
        )
        return CandidateObservation(
            frame=frame,
            candidate=candidate,
            page_centroids=centroids,
            page_area_fractions=areas,
            seam_proxy_fraction=seam_proxy,
            mask_preview=full_mask,
            gray_preview=gray,
        )


class StableWindowAssessor:
    def __init__(self, policy: CandidatePolicy = CandidatePolicy()):
        self.policy = policy

    def assess(self, observations: tuple[CandidateObservation, ...]) -> StabilityAssessment:
        required = self.policy.stable_sample_count
        recent = observations[-required:]
        if len(recent) < required:
            return StabilityAssessment(False, len(recent))

        ids = [item.frame.frame_id for item in recent]
        timestamps = [item.frame.captured_at_monotonic for item in recent]
        if len(set(ids)) != len(ids) or any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
            return StabilityAssessment(False, len(recent), (ReadinessReason.STALE_FRAME,))

        hard_reasons = tuple(
            dict.fromkeys(reason for item in recent for reason in item.candidate.retry_reasons)
        )
        if hard_reasons:
            return StabilityAssessment(False, len(recent), hard_reasons)

        pair_metrics = [_compare(previous, current, self.policy) for previous, current in zip(recent, recent[1:])]
        metrics = {
            "min_mask_iou": min(item["mask_iou"] for item in pair_metrics),
            "max_centroid_shift_fraction": max(item["centroid_shift_fraction"] for item in pair_metrics),
            "max_area_change_fraction": max(item["area_change_fraction"] for item in pair_metrics),
            "max_seam_shift_fraction": max(item["seam_shift_fraction"] for item in pair_metrics),
            "max_motion_fraction": max(item["motion_fraction"] for item in pair_metrics),
            "max_connected_motion_fraction": max(
                item["connected_motion_fraction"] for item in pair_metrics
            ),
            "max_alignment_shift_fraction": max(
                item["alignment_shift_fraction"] for item in pair_metrics
            ),
            "min_alignment_correlation": min(
                item["alignment_correlation"] for item in pair_metrics
            ),
            "all_alignments_valid": all(
                bool(item["alignment_valid"]) for item in pair_metrics
            ),
            "stable_sample_count": len(recent),
        }
        stable = (
            metrics["min_mask_iou"] >= self.policy.min_mask_iou
            and metrics["max_centroid_shift_fraction"] <= self.policy.max_centroid_shift_fraction
            and metrics["max_area_change_fraction"] <= self.policy.max_area_change_fraction
            and metrics["max_seam_shift_fraction"] <= self.policy.max_seam_shift_fraction
            and metrics["max_motion_fraction"] <= self.policy.max_motion_fraction
            and metrics["max_connected_motion_fraction"]
            <= self.policy.max_connected_motion_fraction
            and bool(metrics["all_alignments_valid"])
        )
        if stable:
            reasons = ()
        elif metrics["max_connected_motion_fraction"] > self.policy.max_connected_motion_fraction:
            reasons = (ReadinessReason.HAND_OR_PAGE_TURN,)
        else:
            reasons = (ReadinessReason.PAGE_MOVING,)
        return StabilityAssessment(
            stable,
            len(recent),
            reasons,
            self.select_best(recent) if stable else None,
            tuple(metrics.items()),
        )

    @staticmethod
    def select_best(observations: tuple[CandidateObservation, ...]) -> CandidateObservation:
        if not observations:
            raise ValueError("cannot select from an empty observation sequence")
        eligible = [item for item in observations if not item.candidate.retry_reasons]
        if not eligible:
            raise ValueError("no hard-gate-eligible observation")

        def rank(item: CandidateObservation) -> tuple[float, ...]:
            metrics = dict(item.candidate.metrics)
            return (
                float(metrics["physical_edge_margin_fraction"]),
                float(metrics["mask_confidence_min"]),
                -float(metrics["white_clip_fraction"]) - float(metrics["black_clip_fraction"]),
                -float(metrics["illumination_range"]),
                float(metrics["tenengrad"]),
                float(metrics["laplacian_variance"]),
                item.frame.captured_at_monotonic,
            )

        return max(eligible, key=rank)


def _compare(
    previous: CandidateObservation,
    current: CandidateObservation,
    policy: CandidatePolicy,
) -> dict[str, float]:
    if previous.mask_preview.shape != current.mask_preview.shape:
        return {
            "mask_iou": 0.0,
            "centroid_shift_fraction": 1.0,
            "area_change_fraction": 1.0,
            "seam_shift_fraction": 1.0,
            "motion_fraction": 1.0,
            "connected_motion_fraction": 1.0,
            "alignment_shift_fraction": 1.0,
            "alignment_correlation": 0.0,
            "alignment_valid": 0.0,
        }
    before_mask = previous.mask_preview > 0
    after_mask = current.mask_preview > 0
    union = int(np.count_nonzero(before_mask | after_mask))
    intersection = int(np.count_nonzero(before_mask & after_mask))
    mask_iou = intersection / union if union else 0.0

    centroid_shift = max(
        math.dist(before, after)
        for before, after in zip(previous.page_centroids, current.page_centroids)
    )
    area_change = max(
        abs(before - after) / max(before, after, 1e-9)
        for before, after in zip(previous.page_area_fractions, current.page_area_fractions)
    )
    seam_shift = (
        1.0
        if previous.seam_proxy_fraction is None or current.seam_proxy_fraction is None
        else abs(previous.seam_proxy_fraction - current.seam_proxy_fraction)
    )
    active = before_mask & after_mask
    before_gray = _normalize_photometry(previous.gray_preview, active)
    after_gray = _normalize_photometry(current.gray_preview, active)
    before_blurred = cv2.GaussianBlur(
        before_gray, (policy.motion_blur_kernel_px, policy.motion_blur_kernel_px), 0
    )
    after_blurred = cv2.GaussianBlur(
        after_gray, (policy.motion_blur_kernel_px, policy.motion_blur_kernel_px), 0
    )
    aligned_after, alignment = _align_motion_preview(
        before_blurred,
        after_blurred,
        active,
        policy.motion_alignment_max_shift_fraction,
        policy.motion_alignment_min_correlation,
    )
    diff = cv2.absdiff(before_blurred, aligned_after)
    changed = (diff >= policy.motion_pixel_threshold) & active
    motion = int(np.count_nonzero(changed)) / max(1, int(np.count_nonzero(active)))
    changed_mask = changed.astype(np.uint8)
    component_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        changed_mask, connectivity=8
    )
    largest_component = int(stats[1:, cv2.CC_STAT_AREA].max()) if component_count > 1 else 0
    connected_motion = largest_component / max(1, int(np.count_nonzero(active)))
    return {
        "mask_iou": float(mask_iou),
        "centroid_shift_fraction": float(centroid_shift),
        "area_change_fraction": float(area_change),
        "seam_shift_fraction": float(seam_shift),
        "motion_fraction": float(motion),
        "connected_motion_fraction": float(connected_motion),
        "alignment_shift_fraction": alignment["shift_fraction"],
        "alignment_correlation": alignment["correlation"],
        "alignment_valid": 1.0 if alignment["valid"] else 0.0,
    }


def _normalize_photometry(gray: np.ndarray, active: np.ndarray) -> np.ndarray:
    values = gray[active]
    if values.size < 32:
        return gray.copy()
    low, high = (float(value) for value in np.percentile(values, (5.0, 95.0)))
    if high - low < 8.0:
        return gray.copy()
    normalized = (gray.astype(np.float32) - low) * (255.0 / (high - low))
    return np.clip(normalized, 0.0, 255.0).astype(np.uint8)


def _align_motion_preview(
    before: np.ndarray,
    after: np.ndarray,
    active: np.ndarray,
    max_shift_fraction: float,
    min_correlation: float,
) -> tuple[np.ndarray, dict[str, float | bool]]:
    height, width = before.shape[:2]
    warp = np.eye(2, 3, dtype=np.float32)
    support = (active.astype(np.uint8) * 255)
    try:
        correlation, warp = cv2.findTransformECC(
            before.astype(np.float32) / 255.0,
            after.astype(np.float32) / 255.0,
            warp,
            cv2.MOTION_TRANSLATION,
            (
                cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                30,
                1e-4,
            ),
            support,
            3,
        )
    except cv2.error:
        return after, {"valid": False, "correlation": 0.0, "shift_fraction": 1.0}
    shift_fraction = math.hypot(float(warp[0, 2]), float(warp[1, 2])) / max(1, min(width, height))
    valid = bool(
        math.isfinite(float(correlation))
        and float(correlation) >= min_correlation
        and shift_fraction <= max_shift_fraction
    )
    if not valid:
        return after, {
            "valid": False,
            "correlation": float(correlation),
            "shift_fraction": float(shift_fraction),
        }
    aligned = cv2.warpAffine(
        after,
        warp,
        (width, height),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REFLECT,
    )
    return aligned, {
        "valid": True,
        "correlation": float(correlation),
        "shift_fraction": float(shift_fraction),
    }


def _paste_mask(target: np.ndarray, page_mask: PageMask) -> None:
    ox, oy = page_mask.roi_origin
    local_h, local_w = page_mask.mask.shape[:2]
    target[oy : oy + local_h, ox : ox + local_w] = np.maximum(
        target[oy : oy + local_h, ox : ox + local_w], page_mask.mask
    )


def _preview_image(image: np.ndarray, max_dimension: int) -> np.ndarray:
    height, width = image.shape[:2]
    scale = min(1.0, max_dimension / max(height, width))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    if size == (width, height):
        return image.copy()
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


def _confidence(page_mask: PageMask | None) -> float:
    if page_mask is None or page_mask.confidence is None:
        return 0.0
    return float(page_mask.confidence)


def _normalized_centroid(page_mask: PageMask | None, width: int, height: int) -> tuple[float, float]:
    if page_mask is None:
        return (0.0, 0.0)
    return (page_mask.centroid_full[0] / width, page_mask.centroid_full[1] / height)


def _full_area_fraction(page_mask: PageMask | None, width: int, height: int) -> float:
    if page_mask is None:
        return 0.0
    return float(np.count_nonzero(page_mask.mask)) / (width * height)


def _luminance_seam_proxy(
    gray: np.ndarray,
    left: PageMask | None,
    right: PageMask | None,
    half_width_fraction: float,
    center_prior_weight: float,
) -> tuple[float | None, float | None, float | None]:
    if left is None or right is None:
        return None, None, None
    height, width = gray.shape[:2]
    center = width // 2
    half = max(2, round(width * half_width_fraction))
    x0, x1 = max(0, center - half), min(width, center + half + 1)
    left_full = np.zeros_like(gray, dtype=np.uint8)
    right_full = np.zeros_like(gray, dtype=np.uint8)
    _paste_mask(left_full, left)
    _paste_mask(right_full, right)
    local_center = center - x0
    left_support = np.any(left_full[:, x0 : center + 1] > 0, axis=1)
    right_support = np.any(right_full[:, center:x1] > 0, axis=1)
    valid_rows = left_support & right_support
    valid_rows[: max(1, height // 20)] = False
    valid_rows[min(height, height - max(1, height // 20)) :] = False
    if int(np.count_nonzero(valid_rows)) < max(16, height // 5):
        return None, None, None

    band = cv2.GaussianBlur(gray, (5, 5), 0)[:, x0:x1].astype(np.float32)
    positions = np.arange(band.shape[1], dtype=np.float32)
    center_penalty = (
        np.abs(positions - local_center)
        / max(1.0, float(half))
        * 255.0
        * center_prior_weight
    )
    profile = np.median(band[valid_rows], axis=0)
    scored_profile = profile + center_penalty
    local_x = int(np.argmin(scored_profile))
    row_minima = np.argmin(band[valid_rows] + center_penalty[None, :], axis=1)
    median_row = float(np.median(row_minima))
    dispersion = float(np.median(np.abs(row_minima - median_row))) / max(1, width)
    contrast = float(np.median(profile) - profile[local_x]) / 255.0
    return (x0 + local_x) / max(1, width), dispersion, max(0.0, contrast)


def _physical_edge_margin(
    left: PageMask | None,
    right: PageMask | None,
    width: int,
    height: int,
) -> float:
    if left is None or right is None:
        return 0.0
    lx, ly, lw, lh = left.bbox_full
    rx, ry, rw, rh = right.bbox_full
    margins = [lx, ly, height - (ly + lh), width - (rx + rw), ry, height - (ry + rh)]
    return max(0.0, min(margins) / max(1, min(width, height)))


def _clipping_evidence(
    gray: np.ndarray,
    side_masks: dict[PageSide, np.ndarray],
    left: PageMask | None,
    right: PageMask | None,
    policy: CandidatePolicy,
) -> dict[str, float | bool | str | None]:
    background = cv2.GaussianBlur(gray, (31, 31), 0).astype(np.int16)
    ink = (
        (background - gray.astype(np.int16) >= policy.clipping_ink_contrast)
        & (background >= policy.clipping_ink_background_luminance)
    )
    max_contact = 0.0
    max_bright = 0.0
    max_ink = 0.0
    physical_directions: list[str] = []
    confirmed_directions: list[str] = []
    metrics: dict[str, float | bool | str | None] = {}
    page_masks = {PageSide.LEFT: left, PageSide.RIGHT: right}
    for side in (PageSide.LEFT, PageSide.RIGHT):
        page_mask = page_masks[side]
        for direction in ("top", "bottom", "outer"):
            prefix = f"{side.value}_{direction}"
            if page_mask is None or not page_mask.edge_contacts[direction]:
                metrics[f"{prefix}_edge_contact_fraction"] = 0.0
                metrics[f"{prefix}_bright_edge_fraction"] = 0.0
                metrics[f"{prefix}_ink_edge_fraction"] = 0.0
                continue
            mask_strip = _physical_edge_strip(
                side_masks[side], side, direction, policy.clipping_edge_depth_px
            )
            gray_strip = _physical_edge_strip(
                gray, side, direction, policy.clipping_edge_depth_px
            )
            ink_strip = _physical_edge_strip(
                ink, side, direction, policy.clipping_edge_depth_px
            )
            active = mask_strip > 0
            denominator = max(1, active.size)
            contact_fraction = int(np.count_nonzero(active)) / denominator
            bright_fraction = int(
                np.count_nonzero(active & (gray_strip >= policy.clipping_bright_luminance))
            ) / denominator
            ink_fraction = int(np.count_nonzero(active & ink_strip)) / denominator
            metrics[f"{prefix}_edge_contact_fraction"] = float(contact_fraction)
            metrics[f"{prefix}_bright_edge_fraction"] = float(bright_fraction)
            metrics[f"{prefix}_ink_edge_fraction"] = float(ink_fraction)
            max_contact = max(max_contact, contact_fraction)
            max_bright = max(max_bright, bright_fraction)
            max_ink = max(max_ink, ink_fraction)
            label = f"{side.value}:{direction}"
            physical = bright_fraction >= policy.clipping_min_bright_edge_fraction
            confirmed = physical and ink_fraction >= policy.clipping_min_ink_edge_fraction
            if physical:
                physical_directions.append(label)
            if confirmed:
                confirmed_directions.append(label)
    metrics.update(
        {
            "max_edge_contact_fraction": float(max_contact),
            "max_bright_edge_fraction": float(max_bright),
            "max_ink_edge_fraction": float(max_ink),
            "physical_page_clipping_warning": bool(physical_directions),
            "physical_page_clipping_directions": ",".join(physical_directions) or None,
            "confirmed_content_clipping": bool(confirmed_directions),
            "confirmed_content_clipping_directions": ",".join(confirmed_directions) or None,
            "confirmed_content_clipping_is_hard_gate": policy.reject_confirmed_content_clipping,
        }
    )
    return metrics


def _physical_edge_strip(
    image: np.ndarray,
    side: PageSide,
    direction: str,
    depth: int,
) -> np.ndarray:
    if direction == "top":
        return image[:depth, :]
    if direction == "bottom":
        return image[-depth:, :]
    if direction == "outer" and side is PageSide.LEFT:
        return image[:, :depth]
    if direction == "outer" and side is PageSide.RIGHT:
        return image[:, -depth:]
    raise ValueError(f"unsupported physical edge direction: {side.value}:{direction}")


def _sharpness(gray: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    active = mask > 0
    if not np.any(active):
        return 0.0, 0.0
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    tenengrad = float(np.mean((gx[active] ** 2) + (gy[active] ** 2)))
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    return tenengrad, float(np.var(laplacian[active]))


def _grid_illumination_range(gray: np.ndarray, mask: np.ndarray, grid: int = 4) -> float:
    height, width = gray.shape[:2]
    means: list[float] = []
    for row in range(grid):
        y0, y1 = round(row * height / grid), round((row + 1) * height / grid)
        for column in range(grid):
            x0, x1 = round(column * width / grid), round((column + 1) * width / grid)
            active = mask[y0:y1, x0:x1] > 0
            if np.count_nonzero(active) >= 16:
                means.append(float(gray[y0:y1, x0:x1][active].mean()))
    return (max(means) - min(means)) / 255.0 if len(means) >= 2 else 1.0
