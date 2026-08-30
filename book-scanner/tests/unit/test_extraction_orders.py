from __future__ import annotations

import numpy as np

from book_scanner.detect.segmenter import SegmentationResult
from book_scanner.evaluation.extraction_orders import run_extraction_orders


class InsetSegmenter:
    def segment(self, roi):
        height, width = roi.image.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        mask[max(2, height // 10) : max(3, height - height // 10), max(2, width // 10) : max(3, width - width // 10)] = 255
        return SegmentationResult(mask, 0.9, {"fake": True})


def test_orders_execute_distinct_stage_sequences():
    frame = np.full((120, 240, 3), 200, dtype=np.uint8)
    results, artifacts = run_extraction_orders(frame, InsetSegmenter())

    by_order = {order: [item for item in results if item.order == order] for order in ("A", "B", "C")}
    assert by_order["A"][0].stage_trace == ("center_split", "coarse_warp", "page_crop")
    assert by_order["B"][0].stage_trace == ("spread_coarse_warp", "center_split", "page_crop")
    assert by_order["C"][0].stage_trace == ("center_split", "page_crop", "coarse_warp")
    assert "C_left_crop_before_warp" in artifacts
