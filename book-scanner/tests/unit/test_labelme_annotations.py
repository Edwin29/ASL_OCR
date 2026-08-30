from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from book_scanner.annotations.labelme import load_labelme_pages
from book_scanner.detect.roi import PageSide
from book_scanner.evaluation.page_masks import write_image


def _write_fixture(tmp_path, *, size=(120, 80), include_right=True, json_size=None):
    width, height = size
    image_path = tmp_path / "한글_페이지.png"
    label_path = image_path.with_suffix(".json")
    write_image(image_path, np.zeros((height, width, 3), dtype=np.uint8))
    shapes = [
        {"label": "left_page", "shape_type": "polygon", "points": [[5, 5], [65, 8], [62, 72], [4, 75]]},
    ]
    if include_right:
        shapes.append(
            {"label": "right_page", "shape_type": "polygon", "points": [[62, 72], [116, 75], [114, 5], [60, 8]]}
        )
    json_width, json_height = json_size or size
    label_path.write_text(
        json.dumps(
            {
                "imagePath": image_path.name,
                "imageWidth": json_width,
                "imageHeight": json_height,
                "shapes": shapes,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return image_path, label_path


def test_load_labelme_pages_rasterizes_and_reports_overlap(tmp_path):
    image_path, label_path = _write_fixture(tmp_path)
    labels = load_labelme_pages(image_path, label_path)

    assert labels.image_size == (120, 80)
    assert set(labels.pages) == {PageSide.LEFT, PageSide.RIGHT}
    assert labels.pages[PageSide.LEFT].bbox_full == (4, 5, 62, 71)
    assert labels.pages[PageSide.LEFT].area_px > 0
    assert labels.overlap_px > 0
    assert labels.diagnostics["winding_mismatch"] is True


def test_load_labelme_pages_rejects_size_mismatch(tmp_path):
    image_path, label_path = _write_fixture(tmp_path, json_size=(121, 80))
    with pytest.raises(ValueError, match="does not match actual"):
        load_labelme_pages(image_path, label_path)


def test_load_labelme_pages_rejects_missing_side(tmp_path):
    image_path, label_path = _write_fixture(tmp_path, include_right=False)
    with pytest.raises(ValueError, match="missing required"):
        load_labelme_pages(image_path, label_path)


def test_load_labelme_pages_rejects_self_intersection(tmp_path):
    image_path, label_path = _write_fixture(tmp_path)
    payload = json.loads(label_path.read_text(encoding="utf-8"))
    payload["shapes"][0]["points"] = [[5, 5], [60, 70], [5, 70], [60, 5]]
    label_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="self-intersects"):
        load_labelme_pages(image_path, label_path)
