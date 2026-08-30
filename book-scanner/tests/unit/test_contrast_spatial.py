from __future__ import annotations

import cv2
import numpy as np

from book_scanner.detect.contrast_spatial import ContrastSpatialPageSegmenter
from book_scanner.detect.roi import PageROI, PageSide


def _roi(image: np.ndarray) -> PageROI:
    return PageROI(
        side=PageSide.LEFT,
        image=image,
        allowed_mask=np.full(image.shape[:2], 255, dtype=np.uint8),
        origin=(0, 0),
        full_frame_size=(image.shape[1], image.shape[0]),
        is_calibrated=False,
    )


def test_external_page_contour_beats_internal_edges_and_small_distractor():
    image = np.zeros((240, 200, 3), dtype=np.uint8)
    page = np.array([[28, 15], [174, 25], [185, 218], [20, 225], [12, 120]], np.int32)
    cv2.fillPoly(image, [page], (220, 220, 220))
    for y in range(50, 195, 25):
        cv2.line(image, (45, y), (155, y), (40, 40, 40), 2)
    cv2.rectangle(image, (180, 5), (197, 30), (255, 255, 255), -1)

    result = ContrastSpatialPageSegmenter().segment(_roi(image))

    assert np.count_nonzero(result.mask) > 0
    assert result.diagnostics["retrieval_mode"] == "RETR_EXTERNAL"
    assert result.diagnostics["decision"] == "multi_signal_score_not_area_only"
    assert result.mask[120, 80] == 255


def test_patterned_mid_gray_background_is_rejected():
    image = np.full((240, 200, 3), 110, dtype=np.uint8)
    for y in range(0, 240, 12):
        cv2.line(image, (0, y), (199, y), (135, 135, 135), 2)

    result = ContrastSpatialPageSegmenter().segment(_roi(image))

    assert np.count_nonzero(result.mask) == 0
    assert result.diagnostics["reason"] == "no_supported_external_contour"
