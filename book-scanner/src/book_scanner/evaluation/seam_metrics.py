"""Ambiguity-aware metrics for spine seam ownership experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

from book_scanner.detect.roi import PageSide


@dataclass(frozen=True)
class SeamSideMetrics:
    side: str
    own_page_recall: float
    own_page_recall_excluding_truth_overlap: float
    opposite_page_inclusion_px: int
    opposite_page_inclusion_ratio: float
    seam_cut_truth_px: int
    seam_cut_content_proxy_px: int
    seam_cut_content_proxy_ratio: float
    content_proxy_recall_after: float
    uncertainty_truth_px: int
    uncertainty_content_proxy_px: int


@dataclass(frozen=True)
class SeamPairMetrics:
    prediction_overlap_px_before: int
    prediction_overlap_px_after: int
    truth_overlap_px: int
    union_page_recall: float
    union_lost_px: int
    sides: dict[str, SeamSideMetrics]


def calculate_seam_metrics(
    frame: np.ndarray,
    original_masks: dict[PageSide, np.ndarray],
    owned_masks: dict[PageSide, np.ndarray],
    truth_masks: dict[PageSide, np.ndarray],
    ambiguous_mask: np.ndarray | None = None,
) -> SeamPairMetrics:
    shape = frame.shape[:2]
    masks = [*original_masks.values(), *owned_masks.values(), *truth_masks.values()]
    if any(mask.shape[:2] != shape for mask in masks):
        raise ValueError("all seam metric masks must use full-frame coordinates")
    original = {side: original_masks[side] > 0 for side in PageSide}
    owned = {side: owned_masks[side] > 0 for side in PageSide}
    truth = {side: truth_masks[side] > 0 for side in PageSide}
    truth_overlap = truth[PageSide.LEFT] & truth[PageSide.RIGHT]
    ambiguous = (ambiguous_mask > 0) if ambiguous_mask is not None else np.zeros(shape, dtype=bool)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    edges = cv2.Canny(gray, 45, 135) > 0
    # Page silhouettes are strong Canny edges but are not printed content.
    # Restrict the proxy to an eroded truth interior before measuring cuts.
    interior_kernel = np.ones((15, 15), dtype=np.uint8)
    content = {
        side: edges & (cv2.erode(truth[side].astype(np.uint8), interior_kernel) > 0)
        for side in PageSide
    }
    side_metrics: dict[str, SeamSideMetrics] = {}
    for side in PageSide:
        opposite = PageSide.RIGHT if side is PageSide.LEFT else PageSide.LEFT
        own_truth = truth[side]
        exclusive_truth = own_truth & ~truth_overlap
        opposite_only = truth[opposite] & ~own_truth
        own_count = int(np.count_nonzero(own_truth))
        exclusive_count = int(np.count_nonzero(exclusive_truth))
        opposite_inclusion_px = int(np.count_nonzero(owned[side] & opposite_only))
        owned_count = int(np.count_nonzero(owned[side]))
        cut_truth = original[side] & own_truth & ~owned[side]
        side_content = content[side]
        original_content = original[side] & own_truth & side_content
        cut_content = original_content & ~owned[side]
        original_content_count = int(np.count_nonzero(original_content))
        truth_content = own_truth & side_content
        truth_content_count = int(np.count_nonzero(truth_content))
        side_metrics[side.value] = SeamSideMetrics(
            side=side.value,
            own_page_recall=(int(np.count_nonzero(owned[side] & own_truth)) / own_count if own_count else 1.0),
            own_page_recall_excluding_truth_overlap=(
                int(np.count_nonzero(owned[side] & exclusive_truth)) / exclusive_count if exclusive_count else 1.0
            ),
            opposite_page_inclusion_px=opposite_inclusion_px,
            opposite_page_inclusion_ratio=opposite_inclusion_px / owned_count if owned_count else 0.0,
            seam_cut_truth_px=int(np.count_nonzero(cut_truth)),
            seam_cut_content_proxy_px=int(np.count_nonzero(cut_content)),
            seam_cut_content_proxy_ratio=(
                int(np.count_nonzero(cut_content)) / original_content_count if original_content_count else 0.0
            ),
            content_proxy_recall_after=(
                int(np.count_nonzero(owned[side] & truth_content)) / truth_content_count
                if truth_content_count else 1.0
            ),
            uncertainty_truth_px=int(np.count_nonzero(ambiguous & own_truth)),
            uncertainty_content_proxy_px=int(np.count_nonzero(ambiguous & own_truth & side_content)),
        )
    original_overlap = original[PageSide.LEFT] & original[PageSide.RIGHT]
    owned_overlap = owned[PageSide.LEFT] & owned[PageSide.RIGHT]
    truth_union = truth[PageSide.LEFT] | truth[PageSide.RIGHT]
    owned_union = owned[PageSide.LEFT] | owned[PageSide.RIGHT]
    truth_union_count = int(np.count_nonzero(truth_union))
    return SeamPairMetrics(
        prediction_overlap_px_before=int(np.count_nonzero(original_overlap)),
        prediction_overlap_px_after=int(np.count_nonzero(owned_overlap)),
        truth_overlap_px=int(np.count_nonzero(truth_overlap)),
        union_page_recall=(int(np.count_nonzero(owned_union & truth_union)) / truth_union_count if truth_union_count else 1.0),
        union_lost_px=int(np.count_nonzero((original[PageSide.LEFT] | original[PageSide.RIGHT]) & ~owned_union)),
        sides=side_metrics,
    )


def serialize_seam_metrics(metrics: SeamPairMetrics | None) -> dict[str, object] | None:
    return asdict(metrics) if metrics is not None else None
