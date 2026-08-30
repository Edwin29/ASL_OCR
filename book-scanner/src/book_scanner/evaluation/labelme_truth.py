"""Bridge strict LabelMe page polygons into ROI-local evaluation masks."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from book_scanner.annotations.labelme import LabelMeAnnotationSet, load_labelme_pages
from book_scanner.detect.roi import PageROI, PageSide


def labelme_truth_for_rois(
    labels: LabelMeAnnotationSet,
    rois: dict[PageSide, PageROI],
) -> tuple[dict[PageSide, np.ndarray], dict[str, object]]:
    masks: dict[PageSide, np.ndarray] = {}
    diagnostics: dict[str, object] = {"sides": {}}
    for side, roi in rois.items():
        truth_full = labels.pages[side].mask
        ox, oy = roi.origin
        roi_w, roi_h = roi.size
        truth_local = truth_full[oy : oy + roi_h, ox : ox + roi_w].copy()
        truth_local[roi.allowed_mask == 0] = 0
        full_count = int(np.count_nonzero(truth_full))
        local_count = int(np.count_nonzero(truth_local))
        masks[side] = truth_local
        diagnostics["sides"][side.value] = {
            "truth_page_px_full": full_count,
            "truth_page_px_in_roi": local_count,
            "roi_page_recall": local_count / full_count if full_count else 1.0,
            "clipped_page_px": full_count - local_count,
        }
    return masks, diagnostics


def load_labelme_truth_for_rois(
    image_path: Path,
    label_path: Path,
    rois: dict[PageSide, PageROI],
) -> tuple[dict[PageSide, np.ndarray], dict[str, object]]:
    labels = load_labelme_pages(image_path, label_path)
    masks, diagnostics = labelme_truth_for_rois(labels, rois)
    diagnostics.update({
        "label_path": str(Path(label_path)),
        "label_overlap_px": labels.overlap_px,
    })
    return masks, diagnostics
