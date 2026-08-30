from __future__ import annotations

from pathlib import Path
import json

import cv2
import numpy as np

from book_scanner.detect.roi import PageSide
from book_scanner.evaluation.paired_ocr_inputs import (
    CropResult,
    _write_artifact,
    artifact_id,
    crop_with_mask,
    prepare_postprocess_manifest,
)


def test_artifact_id_is_stable_for_underscored_extraction():
    assert artifact_id(
        "20260826_174958", "right", "seam_conservative", "uvdoc_bilinear", "none"
    ) == "20260826_174958_right_seam_conservative_uvdoc_bilinear_none"


def test_crop_round_trip_bbox_and_local_mask():
    frame = np.zeros((100, 160, 3), dtype=np.uint8)
    mask = np.zeros((100, 160), dtype=np.uint8)
    mask[20:80, 30:130] = 255
    crop = crop_with_mask(frame, mask, padding_fraction=0.10)
    assert crop is not None
    assert crop.bbox_full == (20, 14, 120, 72)
    assert crop.image.shape[:2] == (72, 120)
    assert crop.mask.shape == crop.image.shape[:2]
    x, y, width, height = crop.bbox_full
    restored = np.zeros(mask.shape, dtype=np.uint8)
    restored[y : y + height, x : x + width] = crop.mask
    assert np.array_equal(restored > 0, mask > 0)


def test_manifest_artifact_records_distinct_mask_and_image_hashes(tmp_path: Path):
    image = np.full((20, 30, 3), 240, dtype=np.uint8)
    mask = np.zeros((20, 30), dtype=np.uint8)
    mask[2:18, 3:27] = 255
    record = _write_artifact(
        tmp_path,
        capture="20260826_174958",
        side=PageSide.RIGHT,
        extraction="seam_conservative",
        geometry="none",
        postprocess="none",
        crop=CropResult(image, mask, (10, 15, 30, 20)),
        source={"mask_provenance": "automatic_seam"},
        fallback={"accepted": True, "reasons": []},
    )
    assert record["status"] == "READY"
    assert Path(record["image_path"]).is_file()
    assert Path(record["mask_path"]).is_file()
    assert record["image_sha256"] != record["mask_sha256"]
    assert record["full_frame_round_trip"]["local_origin_full"] == [10, 15]
    assert record["full_frame_round_trip"]["direct_pixel_round_trip"] is True
    assert cv2.imread(record["mask_path"], cv2.IMREAD_GRAYSCALE).shape == (20, 30)


def test_phase_c_prepares_only_selected_control_and_fixed_unsharp(tmp_path: Path):
    image = np.full((30, 20, 3), 180, dtype=np.uint8)
    mask = np.full((30, 20), 255, dtype=np.uint8)
    source = _write_artifact(
        tmp_path, capture="20260826_174958", side=PageSide.RIGHT,
        extraction="seam_conservative", geometry="coarse", postprocess="none",
        crop=CropResult(image, mask, (0, 0, 20, 30)), source={},
        fallback={"accepted": True}, processing={"warp_count": 1, "interpolation": "linear"},
    )
    geometry_path = tmp_path / "geometry.json"
    geometry_path.write_text(json.dumps({"artifacts": [source]}), encoding="utf-8")

    class NeverCalledUvdoc:
        load_count = 0

        def unwarp_with_mode(self, *_args):
            raise AssertionError("bicubic is UVDoc-only")

    manifest = prepare_postprocess_manifest(
        geometry_path, tmp_path, [source["artifact_id"]], NeverCalledUvdoc()
    )
    assert manifest["full_batch_allowed"] is False
    assert len(manifest["artifacts"]) == 2
    assert manifest["artifacts"][0]["phase_c_control_reused"] is True
    assert manifest["artifacts"][1]["postprocess"] == "luminance_unsharp_fixed"
