from __future__ import annotations

import numpy as np
import pytest

from book_scanner.detect.roi import ROIConfig, PageSide, extract_page_rois


def test_fraction_rois_keep_full_frame_coordinates():
    frame = np.zeros((60, 100, 3), dtype=np.uint8)
    rois = extract_page_rois(frame, ROIConfig(centerline_fraction=0.4))

    assert rois[PageSide.LEFT].size == (40, 60)
    assert rois[PageSide.LEFT].origin == (0, 0)
    assert rois[PageSide.RIGHT].size == (60, 60)
    assert rois[PageSide.RIGHT].origin == (40, 0)
    assert rois[PageSide.RIGHT].local_to_full((5.0, 7.0)) == (45.0, 7.0)


def test_fraction_rois_can_overlap_at_spine():
    frame = np.zeros((40, 100, 3), dtype=np.uint8)
    rois = extract_page_rois(
        frame,
        ROIConfig(centerline_fraction=0.5, spine_overlap_fraction=0.1),
    )

    assert rois[PageSide.LEFT].size == (60, 40)
    assert rois[PageSide.RIGHT].size == (60, 40)
    assert rois[PageSide.RIGHT].origin == (40, 0)


def test_spine_overlap_cannot_remove_outer_extent():
    with pytest.raises(ValueError, match="outer-side ROI extent"):
        ROIConfig(centerline_fraction=0.2, spine_overlap_fraction=0.2)


def test_calibrated_polygon_is_masked_and_mapped():
    frame = np.full((100, 200, 3), 100, dtype=np.uint8)
    config = ROIConfig(
        left_polygon=((0.1, 0.1), (0.45, 0.2), (0.45, 0.8), (0.1, 0.9)),
        right_polygon=((0.55, 0.2), (0.9, 0.1), (0.9, 0.9), (0.55, 0.8)),
    )
    rois = extract_page_rois(frame, config)

    left = rois[PageSide.LEFT]
    assert left.is_calibrated
    assert left.origin[0] > 0
    assert np.count_nonzero(left.allowed_mask == 0) > 0
    assert np.all(left.image[left.allowed_mask == 0] == 0)


def test_roi_polygons_must_be_supplied_as_a_pair():
    with pytest.raises(ValueError, match="supplied together"):
        ROIConfig(left_polygon=((0, 0), (0.5, 0), (0.5, 1)))
