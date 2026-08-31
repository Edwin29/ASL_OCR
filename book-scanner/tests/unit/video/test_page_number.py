from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from book_scanner.video.config import PageNumberPolicy
from book_scanner.video.engine import _page_number_preview_inputs
from book_scanner.video.page_number import (
    InMemoryPageKeyLedger,
    PageKeyRelation,
    PageNumberChangeTracker,
    PageNumberRecognition,
    PageNumberRecognitionCache,
    PageNumberStatus,
    SpreadPageKey,
    normalize_page_label,
)
from book_scanner.video.page_number_provider import OpenCVBottomRoiPageNumberProvider
from book_scanner.video.page_number_recognizer import (
    OpenCVDnnDigitRecognizer,
    PaddleRoiDigitRecognizer,
)
from book_scanner.video.page_number_roi import corrected_page_number_roi, preview_page_number_roi
from book_scanner.video.types import ArtifactId, FrameId, PageArtifactRef, PageSide, SpreadArtifactRef, SpreadId


class _FixedRecognizer:
    engine_id = "fixed-test-digits"
    engine_version = "1"
    preprocessing_version = "fixed-v1"

    def __init__(self) -> None:
        self.calls = 0

    def recognize(self, roi: np.ndarray, side: PageSide) -> PageNumberRecognition:
        self.calls += 1
        assert roi.ndim == 2
        text = "30" if side is PageSide.LEFT else "309"
        return PageNumberRecognition(text, 0.99, (2, 3, 8, 9), 2, PageNumberStatus.OBSERVED)


def _artifact(tmp_path) -> SpreadArtifactRef:
    left_path = tmp_path / "left.jpg"
    right_path = tmp_path / "right.jpg"
    assert cv2.imwrite(str(left_path), np.full((200, 100, 3), 240, dtype=np.uint8))
    assert cv2.imwrite(str(right_path), np.full((200, 100, 3), 230, dtype=np.uint8))
    frame_id = FrameId("frame-page-number")
    return SpreadArtifactRef(
        ArtifactId("artifact-page-number"),
        SpreadId("spread-page-number"),
        frame_id,
        PageArtifactRef(PageSide.LEFT, frame_id, str(left_path), "a" * 64, 100, 200),
        PageArtifactRef(PageSide.RIGHT, frame_id, str(right_path), "b" * 64, 100, 200),
        str(tmp_path / "manifest.json"),
        "c" * 64,
        "test-evaluator",
    )


def test_side_aware_corrected_and_preview_rois_preserve_outer_bottom_coordinates() -> None:
    policy = PageNumberPolicy()
    image = np.arange(200 * 100, dtype=np.uint16).reshape(200, 100).astype(np.uint8)
    left, left_bbox = corrected_page_number_roi(image, PageSide.LEFT, policy)
    right, right_bbox = corrected_page_number_roi(image, PageSide.RIGHT, policy)

    assert left_bbox == (0, 160, 35, 40)
    assert right_bbox == (65, 160, 35, 40)
    assert left.shape == right.shape == (40, 35)

    preview = np.full((240, 400), 200, dtype=np.uint8)
    mask = np.zeros_like(preview)
    mask[20:220, 20:190] = 255
    mask[20:220, 210:380] = 255
    preview_left, preview_left_bbox = preview_page_number_roi(preview, mask, 0.5, PageSide.LEFT, policy)
    preview_right, preview_right_bbox = preview_page_number_roi(preview, mask, 0.5, PageSide.RIGHT, policy)

    assert preview_left_bbox == (20, 180, 59, 40)
    assert preview_right_bbox == (320, 180, 60, 40)
    assert preview_left.shape == (40, 59)
    assert preview_right.shape == (40, 60)


def test_page_number_preview_uses_footer_readable_resolution_and_projected_mask() -> None:
    frame = np.full((2160, 3840, 3), 180, dtype=np.uint8)
    mask = np.zeros((540, 960), dtype=np.uint8)
    mask[20:520, 40:920] = 255

    gray, projected = _page_number_preview_inputs(frame, mask, 1920)

    assert gray.shape == projected.shape == (1080, 1920)
    assert gray.ndim == 2
    assert set(np.unique(projected)).issubset({0, 255})


def test_normalization_rejects_zero_non_ascii_and_out_of_range_labels() -> None:
    policy = PageNumberPolicy()
    assert normalize_page_label("0030", policy) == "30"
    assert normalize_page_label("0", policy) is None
    assert normalize_page_label("000", policy) is None
    assert normalize_page_label("１２", policy) is None
    assert normalize_page_label("12345", policy) is None
    assert normalize_page_label("30p", policy) is None


def test_page_key_ledger_is_datapack_scoped_and_bounded() -> None:
    policy = PageNumberPolicy(accepted_capacity=2)
    ledger = InMemoryPageKeyLedger(policy)
    key = SpreadPageKey("pack-a", "30", "309", "recognizer-v1")
    assert ledger.relation(key) == (PageKeyRelation.UNAVAILABLE, None)
    ledger.accept(key, ArtifactId("artifact-a"), "receipt-a")
    assert ledger.relation(key)[0] is PageKeyRelation.SAME
    assert ledger.relation(SpreadPageKey("pack-a", "31", "310", "recognizer-v1"))[0] is PageKeyRelation.DIFFERENT
    assert ledger.relation(SpreadPageKey("pack-b", "30", "309", "recognizer-v1"))[0] is PageKeyRelation.UNAVAILABLE

    ledger.accept(SpreadPageKey("pack-a", "31", "310", "recognizer-v1"), ArtifactId("artifact-b"), "receipt-b")
    ledger.accept(SpreadPageKey("pack-a", "32", "311", "recognizer-v1"), ArtifactId("artifact-c"), "receipt-c")
    assert [entry.artifact_id.value for entry in ledger.recent_accepted()] == ["artifact-c", "artifact-b"]


def test_page_number_change_requires_consecutive_different_complete_keys() -> None:
    tracker = PageNumberChangeTracker(PageNumberPolicy(stable_sample_count=3))
    baseline = SpreadPageKey("pack", "30", "309", "recognizer-v1")
    changed = SpreadPageKey("pack", "32", "311", "recognizer-v1")
    spike = SpreadPageKey("pack", "80", "999", "recognizer-v1")
    tracker.arm(baseline)

    assert tracker.observe(changed, eligible=True).stable_count == 1
    assert tracker.observe(spike, eligible=True).stable_count == 1
    assert tracker.observe(baseline, eligible=True).relation is PageKeyRelation.SAME
    assert not tracker.observe(changed, eligible=True).changed
    assert not tracker.observe(changed, eligible=True).changed
    assert tracker.observe(changed, eligible=True).changed
    assert tracker.observe(None, eligible=False).stable_count == 0


def test_provider_builds_complete_key_and_exact_roi_cache_skips_recognition(tmp_path) -> None:
    recognizer = _FixedRecognizer()
    provider = OpenCVBottomRoiPageNumberProvider(recognizer=recognizer)
    artifact = _artifact(tmp_path)

    first = provider.observe_artifact(artifact, "pack-a")
    second = provider.observe_artifact(artifact, "pack-a")

    assert first.key == SpreadPageKey(
        "pack-a",
        "30",
        "309",
        "bottom-roi-page-number-v3a1-1:fixed-test-digits:1",
    )
    assert recognizer.calls == 2
    assert not first.left.cache_hit and not first.right.cache_hit
    assert second.left.cache_hit and second.right.cache_hit
    assert provider.cache.hits == 2


def test_recognition_cache_is_bounded_lru() -> None:
    cache = PageNumberRecognitionCache(2)
    value = PageNumberRecognition("30", 0.9, None, 2, PageNumberStatus.OBSERVED)
    keys = [("engine", "prep", "left", "corrected", str(index)) for index in range(3)]
    cache.put(keys[0], value)
    cache.put(keys[1], value)
    assert cache.get(keys[0]) == value
    cache.put(keys[2], value)
    assert len(cache) == 2
    assert cache.get(keys[1]) is None


def _dnn_asset() -> tuple[Path, dict[str, object]]:
    project = Path(__file__).resolve().parents[3]
    manifest = json.loads(
        (project / "experiment_inputs" / "scanner_video_v3a2_model_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return project / "models" / "page_number_digit_v1.onnx", manifest


def test_opencv_dnn_digit_model_is_hash_pinned_small_and_classifies_all_digits() -> None:
    model_path, manifest = _dnn_asset()
    asset = manifest["asset"]
    recognizer = OpenCVDnnDigitRecognizer(
        model_path,
        asset["sha256"],
        confidence_temperature=manifest["confidence_temperature"],
    )

    assert recognizer.load_count == 1
    assert recognizer.model_bytes < 2 * 1024 * 1024
    for expected in range(10):
        canvas = np.zeros((72, 64), dtype=np.uint8)
        cv2.putText(
            canvas,
            str(expected),
            (15, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.6,
            255,
            2,
            cv2.LINE_AA,
        )
        digit, confidence = recognizer._classify(canvas)
        assert digit == str(expected)
        assert confidence >= 0.90


def test_opencv_dnn_digit_model_rejects_missing_or_mismatched_assets() -> None:
    model_path, manifest = _dnn_asset()
    with pytest.raises(FileNotFoundError):
        OpenCVDnnDigitRecognizer(model_path.with_name("missing.onnx"), "0" * 64)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        OpenCVDnnDigitRecognizer(model_path, "0" * 64)


def test_paddle_recognizer_rejects_hash_mismatch_before_runtime_import(tmp_path: Path) -> None:
    for name in ("inference.json", "inference.pdiparams", "inference.yml"):
        (tmp_path / name).write_bytes(name.encode("ascii"))

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        PaddleRoiDigitRecognizer(
            tmp_path,
            expected_file_hashes={"inference.json": "0" * 64},
        )


def test_paddle_recognizer_rejects_asset_path_escape(tmp_path: Path) -> None:
    for name in ("inference.json", "inference.pdiparams", "inference.yml"):
        (tmp_path / name).write_bytes(name.encode("ascii"))

    with pytest.raises(ValueError, match="inside model_dir"):
        PaddleRoiDigitRecognizer(
            tmp_path,
            expected_file_hashes={"../outside": "0" * 64},
        )
