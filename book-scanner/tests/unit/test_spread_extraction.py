from __future__ import annotations

import numpy as np

from book_scanner.detect.roi import PageSide
from book_scanner.detect.segmenter import SegmentationResult
from book_scanner.detect.spine_seam import FixedCenterlineSeamDetector, SpineSeamConfig
from book_scanner.detect.spread_extraction import (
    SeamConservativeSpreadExtractor,
    SpreadExtractionConfig,
)


class FullROISegmenter:
    name = "full-roi-test"

    def segment(self, roi):
        mask = np.zeros(roi.image.shape[:2], dtype=np.uint8)
        mask[12:-12, 12:-12] = 255
        return SegmentationResult(mask, 1.0, {"source": "unit"})


def test_production_extractor_returns_two_crops_from_same_full_frame() -> None:
    frame = np.zeros((240, 360, 3), dtype=np.uint8)
    frame[12:228, 12:348] = 230
    config = SpreadExtractionConfig(padding_fraction=0.03)
    extractor = SeamConservativeSpreadExtractor(
        config,
        segmenter=FullROISegmenter(),
        seam_detector=FixedCenterlineSeamDetector(
            SpineSeamConfig(centerline_fraction=0.5, uncertainty_band_px=8)
        ),
    )

    result = extractor.extract(frame)

    assert result.success
    assert result.left is not None and result.right is not None
    assert result.left.side is PageSide.LEFT
    assert result.right.side is PageSide.RIGHT
    assert result.left.crop.shape[:2] == result.left.crop_mask.shape
    assert result.right.crop.shape[:2] == result.right.crop_mask.shape
    assert result.left.bbox_full[0] < result.right.bbox_full[0]
    assert result.seam is not None and len(result.seam.points_full) == frame.shape[0]


def test_production_extractor_rejects_invalid_frame_without_throwing() -> None:
    result = SeamConservativeSpreadExtractor().extract(np.zeros((10, 10), dtype=np.uint8))

    assert not result.success
    assert result.reason == "INVALID_FRAME"
    assert result.left is None and result.right is None
