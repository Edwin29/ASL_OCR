from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from book_scanner.annotations.labelme import LabelMeAnnotationSet, OraclePageAnnotation
from book_scanner.detect.roi import ROIConfig, PageSide, extract_page_rois
from book_scanner.evaluation.labelme_truth import labelme_truth_for_rois


def _annotation(side: PageSide, mask: np.ndarray) -> OraclePageAnnotation:
    contour = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0][0]
    x, y, width, height = cv2.boundingRect(contour)
    return OraclePageAnnotation(
        side=side,
        label=f"{side.value}_page",
        points=tuple((float(point[0][0]), float(point[0][1])) for point in contour),
        mask=mask,
        bbox_full=(x, y, width, height),
        area_px=int(np.count_nonzero(mask)),
        area_ratio=float(np.count_nonzero(mask) / mask.size),
        winding="clockwise",
        touches_frame_edge=False,
    )


def test_spine_overlap_recovers_truth_crossing_nominal_centerline():
    frame = np.zeros((40, 100, 3), dtype=np.uint8)
    left = np.zeros((40, 100), dtype=np.uint8)
    right = np.zeros_like(left)
    left[5:35, 10:56] = 255
    right[5:35, 44:90] = 255
    labels = LabelMeAnnotationSet(
        image_path=Path("sample.jpg"),
        label_path=Path("sample.json"),
        image_size=(100, 40),
        pages={PageSide.LEFT: _annotation(PageSide.LEFT, left), PageSide.RIGHT: _annotation(PageSide.RIGHT, right)},
        overlap_px=int(np.count_nonzero((left > 0) & (right > 0))),
        diagnostics={},
    )

    _, split_diagnostics = labelme_truth_for_rois(labels, extract_page_rois(frame))
    _, overlap_diagnostics = labelme_truth_for_rois(
        labels,
        extract_page_rois(frame, ROIConfig(spine_overlap_fraction=0.06)),
    )

    assert split_diagnostics["sides"]["left"]["roi_page_recall"] < 1.0
    assert split_diagnostics["sides"]["right"]["roi_page_recall"] < 1.0
    assert overlap_diagnostics["sides"]["left"]["roi_page_recall"] == 1.0
    assert overlap_diagnostics["sides"]["right"]["roi_page_recall"] == 1.0
