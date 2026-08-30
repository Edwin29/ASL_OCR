from __future__ import annotations

import json

import numpy as np

from book_scanner.correct.unwarper import UnwarpResult
from book_scanner.evaluation.ocr_ab_experiment import (
    VARIANT_NAMES,
    image_quality_metrics,
    run_uvdoc_ocr_ab_experiment,
    screen_candidate,
)
from book_scanner.evaluation.page_masks import write_image
from document_parser.ocr.base import BBox, OcrPageResult, OcrToken


class FakeUnwarper:
    def __init__(self):
        self.calls = 0

    @property
    def load_count(self):
        return int(self.calls > 0)

    def unwarp_with_mode(self, image, sampling_mode):
        self.calls += 1
        output = image.copy()
        if sampling_mode == "bicubic":
            output = np.clip(output.astype(np.int16) + 1, 0, 255).astype(np.uint8)
        return UnwarpResult(
            True,
            output,
            "fake-uvdoc",
            "cpu",
            1.0,
            (image.shape[1], image.shape[0]),
            (image.shape[1], image.shape[0]),
            diagnostics={"sampling_mode": sampling_mode, "load_count": 1},
        )


class FakeOcrAdapter:
    engine_id = "fake-ocr"
    engine_version = "1.0"
    cache_signature = "fake:stable"

    def __init__(self):
        self.calls = 0

    def recognize(self, image):
        self.calls += 1
        tokens = [
            OcrToken("테스트", BBox(10, 10, 35, 12), 0.9, token_id=f"{image.page_id}-t1"),
            OcrToken("문장", BBox(10, 28, 30, 12), 0.8, token_id=f"{image.page_id}-t2"),
        ]
        return OcrPageResult(
            image.page_id,
            self.engine_id,
            self.engine_version,
            tokens,
            {"cache_signature": self.cache_signature},
            [],
        )


def _fixture(tmp_path):
    image = np.full((120, 200, 3), 25, dtype=np.uint8)
    image[15:105, 10:98] = 180
    image[15:105, 102:190] = 205
    image_path = tmp_path / "capture.jpg"
    label_path = tmp_path / "capture.json"
    write_image(image_path, image)
    label_path.write_text(
        json.dumps({
            "imagePath": image_path.name,
            "imageWidth": 200,
            "imageHeight": 120,
            "shapes": [
                {"label": "left_page", "shape_type": "polygon", "points": [[10, 15], [98, 15], [98, 105], [10, 105]]},
                {"label": "right_page", "shape_type": "polygon", "points": [[102, 15], [190, 15], [190, 105], [102, 105]]},
            ],
        }),
        encoding="utf-8",
    )
    return image_path, label_path


def test_image_quality_metrics_include_inner_and_proxy_measurements():
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    image[:, 100:] = 255
    metrics = image_quality_metrics(image, proxy_long_edge=80)
    assert metrics["size"] == [200, 100]
    assert metrics["proxy_long_edge"] == 80
    assert metrics["full"]["laplacian_variance"] > 0
    assert metrics["inner_5_percent"]["tenengrad_mean"] > 0


def test_screen_candidate_enforces_registered_guards():
    controls = []
    candidates = []
    for index in range(8):
        controls.append(_metric_record(f"p{index}", 100, 0.80, 0.10))
        candidates.append(_metric_record(f"p{index}", 102, 0.82, 0.07))
    screen = screen_candidate(candidates, controls)
    assert screen["metric_pass"]
    assert all(screen["checks"].values())


def test_full_fake_matrix_writes_artifacts_and_reuses_ocr_cache(tmp_path):
    image_path, label_path = _fixture(tmp_path)
    output_dir = tmp_path / "output"
    unwarper = FakeUnwarper()
    ocr = FakeOcrAdapter()

    first = run_uvdoc_ocr_ab_experiment([(image_path, label_path)], output_dir, unwarper, ocr)
    assert first["expected_page_count"] == 2
    assert set(first["variant_names"]) == set(VARIANT_NAMES)
    assert ocr.calls == len(VARIANT_NAMES) * 2
    assert unwarper.load_count == 1
    assert (output_dir / "capture" / "contact_sheet.jpg").exists()
    assert (output_dir / "capture" / "left" / "ocr" / "uvdoc_bicubic_original.json").exists()

    second = run_uvdoc_ocr_ab_experiment([(image_path, label_path)], output_dir, unwarper, ocr)
    assert ocr.calls == len(VARIANT_NAMES) * 2
    assert second["variant_summaries"]["crop_original_control"]["cache_hit_count"] == 2


def _metric_record(page_id, chars, mean_confidence, low_rate):
    token_count = 100
    low_count = round(token_count * low_rate)
    confidences = [0.4] * low_count + [mean_confidence] * (token_count - low_count)
    tokens = [{"confidence": value} for value in confidences]
    return {
        "page_id": page_id,
        "ocr_result": {"tokens": tokens},
        "metrics": {
            "token_count": token_count,
            "non_whitespace_character_count": chars,
            "mean_confidence": mean_confidence,
            "median_confidence": mean_confidence,
            "min_confidence": min(confidences),
            "p10_confidence": 0.4,
            "low_confidence_count": low_count,
            "low_confidence_rate": low_rate,
            "ocr_processing_ms": 1.0,
            "normalized_text": "테스트",
            "issue_codes": [],
        },
    }
