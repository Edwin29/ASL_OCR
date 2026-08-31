from __future__ import annotations

import cv2
import numpy as np

from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.obstruction import (
    DiagnosticChromaContourObstructionDetector,
    EdgeChromaIntrusionConfig,
    EdgeChromaIntrusionObstructionDetector,
    MediaPipeHandConfig,
    MediaPipeHandObstructionDetector,
    ObstructionResult,
)
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import FrameId, PageSide, ReadinessReason


def test_chroma_contour_baseline_is_diagnostic_only() -> None:
    image = np.full((200, 300, 3), 220, dtype=np.uint8)
    cv2.rectangle(image, (80, 80), (220, 190), (80, 140, 210), -1)
    page = np.ones((200, 300), dtype=np.uint8) * 255

    result = DiagnosticChromaContourObstructionDetector().detect(
        image,
        {PageSide.LEFT: page, PageSide.RIGHT: np.zeros_like(page)},
    )

    assert result.detected
    assert not result.content_occluded
    assert result.runtime_provenance == "local-classical-baseline-no-model"


def test_edge_chroma_intrusion_rejects_partial_hand_entering_page() -> None:
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    left = np.zeros((200, 300), dtype=np.uint8)
    right = np.zeros_like(left)
    left[20:190, 20:145] = 255
    right[20:190, 155:280] = 255
    skin_bgr = cv2.cvtColor(
        np.array([[[100, 145, 120]]], dtype=np.uint8), cv2.COLOR_YCrCb2BGR
    )[0, 0]
    cv2.rectangle(image, (185, 172), (245, 199), tuple(int(v) for v in skin_bgr), -1)

    result = EdgeChromaIntrusionObstructionDetector().detect(
        image, {PageSide.LEFT: left, PageSide.RIGHT: right}
    )

    assert result.detected
    assert result.content_occluded
    assert result.side is PageSide.RIGHT
    assert result.bbox_preview is not None
    assert result.runtime_provenance == "local-classical-fixed-camera-provisional"


def test_edge_chroma_intrusion_ignores_skin_like_component_away_from_border() -> None:
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    page = np.ones((200, 300), dtype=np.uint8) * 255
    skin_bgr = cv2.cvtColor(
        np.array([[[100, 145, 120]]], dtype=np.uint8), cv2.COLOR_YCrCb2BGR
    )[0, 0]
    cv2.rectangle(image, (110, 80), (190, 140), tuple(int(v) for v in skin_bgr), -1)

    result = EdgeChromaIntrusionObstructionDetector().detect(
        image, {PageSide.LEFT: page, PageSide.RIGHT: np.zeros_like(page)}
    )

    assert not result.detected
    assert not result.content_occluded


def test_edge_chroma_intrusion_ignores_tiny_border_artifact() -> None:
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    page = np.ones((200, 300), dtype=np.uint8) * 255
    skin_bgr = cv2.cvtColor(
        np.array([[[100, 145, 120]]], dtype=np.uint8), cv2.COLOR_YCrCb2BGR
    )[0, 0]
    cv2.rectangle(image, (120, 194), (135, 199), tuple(int(v) for v in skin_bgr), -1)

    result = EdgeChromaIntrusionObstructionDetector().detect(
        image, {PageSide.LEFT: page, PageSide.RIGHT: np.zeros_like(page)}
    )

    assert not result.detected


def test_edge_chroma_intrusion_config_validates_ranges() -> None:
    try:
        EdgeChromaIntrusionConfig(cr_min=190, cr_max=180)
    except ValueError as exc:
        assert "minimums" in str(exc)
    else:
        raise AssertionError("expected invalid chroma range")


def test_authoritative_detector_can_hard_reject_content_occlusion() -> None:
    analyzer = OpenCVCandidateAnalyzer(obstruction_detector=_RejectingDetector())
    image = np.zeros((300, 400, 3), dtype=np.uint8)
    cv2.rectangle(image, (30, 25), (190, 275), (220,) * 3, -1)
    cv2.rectangle(image, (210, 25), (370, 275), (220,) * 3, -1)

    observation = analyzer.analyze(FrameSample(FrameId("frame-1"), 0.0, image))

    assert ReadinessReason.CONTENT_OCCLUDED in observation.candidate.retry_reasons
    assert dict(observation.candidate.metrics)["obstruction_detector"] == "test-detector"


class _RejectingDetector:
    def detect(self, _image: np.ndarray, _page_masks: object) -> ObstructionResult:
        return ObstructionResult(
            detected=True,
            content_occluded=True,
            confidence=0.9,
            side=PageSide.RIGHT,
            bbox_preview=(200, 180, 100, 100),
            component_area_fraction=0.1,
            content_overlap_fraction=0.8,
            detector_name="test-detector",
            detector_version="v1",
            runtime_provenance="unit-test",
        )


def test_mediapipe_adapter_rejects_model_hash_mismatch_before_runtime_import(tmp_path) -> None:
    model = tmp_path / "hand.task"
    model.write_bytes(b"not-the-pinned-model")

    try:
        MediaPipeHandObstructionDetector(
            MediaPipeHandConfig(model_path=model, expected_sha256="0" * 64)
        )
    except ValueError as exc:
        assert "SHA-256 mismatch" in str(exc)
    else:
        raise AssertionError("expected a model hash mismatch")
