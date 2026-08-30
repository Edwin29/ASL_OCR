from __future__ import annotations

import json

import cv2
import numpy as np

from book_scanner.detect.roi import PageSide
from book_scanner.detect.segmenter import BrightnessPageSegmenter, StaticPageSegmenter
from book_scanner.evaluation.page_masks import calculate_mask_metrics, evaluate_frame


def test_mask_metrics_are_exact_for_identical_masks():
    mask = np.zeros((40, 40), dtype=np.uint8)
    mask[5:35, 8:32] = 255
    metrics = calculate_mask_metrics(mask, mask)
    assert metrics.iou == 1.0
    assert metrics.dice == 1.0
    assert metrics.boundary_f1 == 1.0
    assert metrics.page_recall == 1.0
    assert metrics.background_leakage == 0.0
    assert metrics.crop_missed_page_px == 0
    assert metrics.bbox_edge_delta == (0, 0, 0, 0)


def test_page_preservation_is_separate_from_tightness():
    truth = np.zeros((40, 40), dtype=np.uint8)
    truth[10:30, 12:28] = 255
    prediction = np.zeros_like(truth)
    prediction[5:35, 7:33] = 255
    metrics = calculate_mask_metrics(
        prediction,
        truth,
        crop_coverage=prediction,
    )

    assert metrics.page_recall == 1.0
    assert metrics.safe_crop_page_recall == 1.0
    assert metrics.iou < 1.0
    assert metrics.background_leakage > 0.0
    assert metrics.bbox_edge_delta == (-5, -5, 5, 5)


def test_evaluation_writes_visual_diagnostics_and_no_page(tmp_path):
    frame = np.zeros((80, 160, 3), dtype=np.uint8)
    left = np.zeros((80, 80), dtype=np.uint8)
    left[10:70, 8:75] = 255
    right = np.zeros((80, 80), dtype=np.uint8)
    segmenter = StaticPageSegmenter({PageSide.LEFT: left, PageSide.RIGHT: right})

    results = evaluate_frame(frame, tmp_path, segmenter)

    assert [result.status for result in results] == ["page", "no_page"]
    for name in ("raw.png", "left_roi.png", "left_mask.png", "left_overlay.png", "left_crop.png", "right_overlay.png"):
        assert (tmp_path / name).exists()
    diagnostics = json.loads((tmp_path / "diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostics[0]["bbox_full"] == [8, 10, 67, 60]
    assert diagnostics[1]["status"] == "no_page"
    assert diagnostics[1]["diagnostics"]["postprocess_reason"] == "no_plausible_page_component"


def test_brightness_baseline_rejects_uniform_empty_roi(tmp_path):
    frame = np.full((60, 120, 3), 100, dtype=np.uint8)
    results = evaluate_frame(frame, tmp_path, BrightnessPageSegmenter())
    assert all(result.status == "no_page" for result in results)
    assert all(result.diagnostics["reason"] == "low_luminance_variation" for result in results)
