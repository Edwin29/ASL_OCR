from __future__ import annotations

from pathlib import Path
import json
from types import SimpleNamespace

import cv2
import numpy as np

from book_scanner.detect.roi import PageSide
from book_scanner.evaluation.paired_ocr_inputs import (
    CropResult,
    _write_artifact,
    artifact_id,
    crop_with_mask,
    prepare_postprocess_manifest,
    prepare_extraction_manifest,
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


def test_extraction_manifest_accepts_p030_left_only_without_legacy_fallbacks(
    tmp_path: Path, monkeypatch,
):
    image_dir = tmp_path / "inputs"
    image_dir.mkdir()
    image = np.full((100, 160, 3), 220, dtype=np.uint8)
    cv2.imwrite(str(image_dir / "capture.jpg"), image)
    (image_dir / "capture.json").write_text(json.dumps({
        "imagePath": "capture.jpg", "imageWidth": 160, "imageHeight": 100,
        "shapes": [
            {"label": "left_page", "shape_type": "polygon",
             "points": [[5, 5], [78, 5], [78, 95], [5, 95]]},
            {"label": "right_page", "shape_type": "polygon",
             "points": [[82, 5], [155, 5], [155, 95], [82, 95]]},
        ],
    }), encoding="utf-8")
    left = np.zeros((100, 160), dtype=np.uint8)
    right = np.zeros((100, 160), dtype=np.uint8)
    left[5:96, 5:79] = 255
    right[5:96, 82:156] = 255
    assessment = SimpleNamespace(
        accepted=True, reasons=(), sides={}, diagnostics={},
    )
    detected = SimpleNamespace(
        seam=SimpleNamespace(confidence=0.9, method="fake"), reason=None, diagnostics={},
    )
    ownership = SimpleNamespace(
        left_mask=left, right_mask=right,
        left_conservative_mask=left, right_conservative_mask=right,
        diagnostics={},
    )
    monkeypatch.setattr(
        "book_scanner.evaluation.paired_ocr_inputs._automatic_state",
        lambda _frame: (
            {PageSide.LEFT: left, PageSide.RIGHT: right}, {}, assessment, detected, ownership,
        ),
    )

    manifest = prepare_extraction_manifest(
        image_dir, tmp_path / "out", captures=("capture",),
        sides=(PageSide.LEFT,), extraction_variants=("oracle",),
        control_capture=None, fallback_stress_captures=(),
    )

    assert manifest["labeled_capture_count"] == 1
    assert manifest["fallback_records"] == []
    assert manifest["configs"]["sides"] == ["left"]
    assert [item["artifact_id"] for item in manifest["artifacts"]] == [
        "capture_left_oracle_none_none"
    ]
