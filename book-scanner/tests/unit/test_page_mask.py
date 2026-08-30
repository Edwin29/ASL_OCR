from __future__ import annotations

import numpy as np

from book_scanner.detect.page_mask import MaskPostprocessConfig, build_page_mask, crop_page
from book_scanner.detect.roi import ROIConfig, PageSide, extract_page_rois
from book_scanner.detect.segmenter import SegmentationResult, StaticPageSegmenter
from book_scanner.session.mask_pipeline import MaskFramePipeline


def test_static_segmenter_to_mask_crop_preserves_coordinate_spaces():
    frame = np.zeros((80, 200, 3), dtype=np.uint8)
    frame[10:70, 110:195] = (10, 20, 30)
    right_roi = extract_page_rois(frame, ROIConfig())[PageSide.RIGHT]
    local_mask = np.zeros((80, 100), dtype=np.uint8)
    local_mask[10:70, 10:95] = 255
    result = StaticPageSegmenter({PageSide.RIGHT: local_mask}).segment(right_roi)

    page_mask = build_page_mask(
        right_roi,
        result,
        MaskPostprocessConfig(close_kernel_px=1, open_kernel_px=1),
    )

    assert page_mask is not None
    assert page_mask.bbox == (10, 10, 85, 60)
    assert page_mask.bbox_full == (110, 10, 85, 60)
    assert page_mask.centroid_full[0] > 150
    assert not page_mask.touches_spine
    assert not page_mask.touches_outer_frame

    crop = crop_page(frame, page_mask, padding_fraction=0, neutralize_outside=True)
    assert crop.bbox_full == (110, 10, 85, 60)
    assert crop.image.shape[:2] == (60, 85)
    assert tuple(crop.image[0, 0]) == (10, 20, 30)


def test_spine_contact_is_distinct_from_physical_outer_contact():
    frame = np.zeros((50, 100, 3), dtype=np.uint8)
    rois = extract_page_rois(frame)

    left_mask = np.zeros((50, 50), dtype=np.uint8)
    left_mask[5:45, 10:50] = 255
    left = build_page_mask(
        rois[PageSide.LEFT],
        SegmentationResult(left_mask),
        MaskPostprocessConfig(close_kernel_px=1, open_kernel_px=1),
    )
    assert left is not None
    assert left.touches_spine
    assert not left.touches_outer_frame

    right_mask = np.zeros((50, 50), dtype=np.uint8)
    right_mask[5:45, 10:50] = 255
    right = build_page_mask(
        rois[PageSide.RIGHT],
        SegmentationResult(right_mask),
        MaskPostprocessConfig(close_kernel_px=1, open_kernel_px=1),
    )
    assert right is not None
    assert not right.touches_spine
    assert right.touches_outer_frame


def test_calibrated_roi_boundary_is_not_mislabeled_as_full_frame_edge():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    config = ROIConfig(
        left_polygon=((0.1, 0.1), (0.45, 0.1), (0.45, 0.9), (0.1, 0.9)),
        right_polygon=((0.55, 0.1), (0.9, 0.1), (0.9, 0.9), (0.55, 0.9)),
    )
    roi = extract_page_rois(frame, config)[PageSide.LEFT]
    mask = roi.allowed_mask.copy()
    page_mask = build_page_mask(
        roi,
        SegmentationResult(mask),
        MaskPostprocessConfig(close_kernel_px=1, open_kernel_px=1),
    )
    assert page_mask is not None
    assert page_mask.edge_contacts["roi_boundary"]
    assert not page_mask.touches_outer_frame


def test_tiny_component_is_a_diagnosable_no_page_result():
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    roi = extract_page_rois(frame)[PageSide.LEFT]
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[2:5, 2:5] = 255
    assert build_page_mask(roi, SegmentationResult(mask, diagnostics={"model": "fake"})) is None


def test_mask_session_preparation_runs_with_fake_segmenter():
    frame = np.zeros((60, 120, 3), dtype=np.uint8)

    def fake_mask(roi):
        mask = np.zeros(roi.image.shape[:2], dtype=np.uint8)
        if roi.side is PageSide.LEFT:
            mask[5:55, 5:55] = 255
        return mask

    candidates = MaskFramePipeline(
        StaticPageSegmenter(fake_mask),
        postprocess_config=MaskPostprocessConfig(close_kernel_px=1, open_kernel_px=1),
    ).process(frame)

    assert candidates[PageSide.LEFT].crop is not None
    assert candidates[PageSide.LEFT].reject_reason is None
    assert candidates[PageSide.RIGHT].crop is None
    assert candidates[PageSide.RIGHT].reject_reason == "no_plausible_page_component"
