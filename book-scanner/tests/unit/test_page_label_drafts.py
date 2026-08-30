from __future__ import annotations

import cv2
import numpy as np
import pytest

from book_scanner.detect.segmenter import SegmentationResult
from book_scanner.evaluation.label_drafts import export_labelme_draft


class DraftSegmenter:
    name = "draft-test"

    def segment(self, roi):
        mask = np.zeros(roi.image.shape[:2], dtype=np.uint8)
        mask[5:-5, 5:-5] = 255
        return SegmentationResult(mask, 0.9, {})


def test_draft_has_provenance_masks_and_no_overwrite(tmp_path):
    image_path = tmp_path / "책.jpg"
    ok, encoded = cv2.imencode(".jpg", np.full((50, 100, 3), 200, dtype=np.uint8))
    assert ok
    image_path.write_bytes(encoded.tobytes())
    output = tmp_path / "draft.json"

    payload = export_labelme_draft(image_path, output, DraftSegmenter())

    assert payload["_book_scanner_draft"]["human_verified"] is False
    assert len(payload["_book_scanner_draft"]["source_sha256"]) == 64
    assert {shape["label"] for shape in payload["shapes"]} == {"left_page", "right_page"}
    assert (tmp_path / "draft_left_draft_mask.png").exists()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        export_labelme_draft(image_path, output, DraftSegmenter())
