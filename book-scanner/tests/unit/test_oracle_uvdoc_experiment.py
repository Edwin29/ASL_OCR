from __future__ import annotations

import json

import numpy as np

from book_scanner.correct.unwarper import UnwarpFailureReason, UnwarpResult
from book_scanner.evaluation.page_masks import write_image
from book_scanner.evaluation.unwarp_experiment import build_oracle_crops, run_oracle_unwarp_experiment
from book_scanner.annotations.labelme import load_labelme_pages
from book_scanner.detect.roi import PageSide


def _fixture(tmp_path):
    image = np.full((120, 200, 3), 30, dtype=np.uint8)
    image[15:105, 10:95] = 180
    image[15:105, 105:190] = 210
    image_path = tmp_path / "spread.png"
    label_path = tmp_path / "spread.json"
    write_image(image_path, image)
    label_path.write_text(
        json.dumps(
            {
                "imagePath": image_path.name,
                "imageWidth": 200,
                "imageHeight": 120,
                "shapes": [
                    {"label": "left_page", "shape_type": "polygon", "points": [[10, 15], [98, 15], [98, 105], [10, 105]]},
                    {"label": "right_page", "shape_type": "polygon", "points": [[102, 15], [190, 15], [190, 105], [102, 105]]},
                ],
            }
        ),
        encoding="utf-8",
    )
    return image, image_path, label_path


class CopyUnwarper:
    def __init__(self):
        self.calls = 0

    def unwarp(self, image):
        self.calls += 1
        return UnwarpResult(
            True,
            image.copy(),
            "copy",
            "cpu",
            1.0,
            (image.shape[1], image.shape[0]),
            (image.shape[1], image.shape[0]),
            diagnostics={"calls": self.calls},
        )


def test_oracle_crop_neutralization_preserves_page_pixels(tmp_path):
    frame, image_path, label_path = _fixture(tmp_path)
    labels = load_labelme_pages(image_path, label_path)
    annotation = labels.pages[PageSide.LEFT]
    crops = build_oracle_crops(frame, annotation, padding_fraction=0.1)

    original = crops["bbox_original"]
    neutral = crops["bbox_neutralized"]
    selected = original.mask > 0
    assert np.array_equal(original.image[selected], neutral.image[selected])
    assert np.all(neutral.image[~selected] == 255)
    assert np.any(original.image[~selected] != 255)


def test_experiment_writes_all_lineage_artifacts(tmp_path):
    _frame, image_path, label_path = _fixture(tmp_path)
    output_dir = tmp_path / "output"
    unwarper = CopyUnwarper()

    summary = run_oracle_unwarp_experiment(image_path, label_path, output_dir, unwarper)

    assert unwarper.calls == 4
    assert (output_dir / "raw.png").exists()
    assert (output_dir / "contact_sheet.png").exists()
    assert (output_dir / "summary.json").exists()
    for side in ("left", "right"):
        assert (output_dir / side / "mask.png").exists()
        assert (output_dir / side / "bbox_original.png").exists()
        assert (output_dir / side / "uvdoc_bbox_original.png").exists()
        assert summary["sides"][side]["variants"]["bbox_neutralized"]["success"]
        assert summary["sides"][side]["artifacts"][0]["sha256"]


def test_experiment_preserves_artifacts_when_one_inference_fails(tmp_path):
    class FirstCallFails(CopyUnwarper):
        def unwarp(self, image):
            self.calls += 1
            if self.calls == 1:
                return UnwarpResult(
                    False,
                    None,
                    "fake",
                    "cpu",
                    1.0,
                    (image.shape[1], image.shape[0]),
                    None,
                    UnwarpFailureReason.INFERENCE_FAILED,
                    {"message": "synthetic failure"},
                )
            return UnwarpResult(
                True,
                image.copy(),
                "fake",
                "cpu",
                1.0,
                (image.shape[1], image.shape[0]),
                (image.shape[1], image.shape[0]),
            )

    _frame, image_path, label_path = _fixture(tmp_path)
    output_dir = tmp_path / "partial"
    summary = run_oracle_unwarp_experiment(image_path, label_path, output_dir, FirstCallFails())

    assert not summary["sides"]["left"]["variants"]["bbox_original"]["success"]
    assert summary["sides"]["right"]["variants"]["bbox_neutralized"]["success"]
    assert (output_dir / "raw.png").exists()
    assert (output_dir / "left" / "bbox_original.png").exists()
    assert (output_dir / "right" / "uvdoc_bbox_neutralized.png").exists()
    assert (output_dir / "contact_sheet.png").exists()
