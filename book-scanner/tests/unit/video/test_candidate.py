from __future__ import annotations

import cv2
import numpy as np

from book_scanner.video.candidate import (
    CandidateObservation,
    CandidateWindow,
    OpenCVCandidateAnalyzer,
    StableWindowAssessor,
)
from book_scanner.video.config import CandidatePolicy
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import FrameCandidate, FrameId, ReadinessReason


def spread_frame(*, shift: int = 0, intensity: int = 220) -> np.ndarray:
    image = np.zeros((300, 400, 3), dtype=np.uint8)
    cv2.rectangle(image, (30 + shift, 25), (190 + shift, 275), (intensity,) * 3, -1)
    cv2.rectangle(image, (210 + shift, 25), (370 + shift, 275), (intensity,) * 3, -1)
    for y in range(50, 260, 25):
        cv2.line(image, (50 + shift, y), (170 + shift, y), (70,) * 3, 2)
        cv2.line(image, (230 + shift, y), (350 + shift, y), (70,) * 3, 2)
    return image


def sample(index: int, image: np.ndarray | None = None) -> FrameSample[np.ndarray]:
    return FrameSample(FrameId(f"frame-{index}"), index * 0.5, spread_frame() if image is None else image)


def test_identical_spread_samples_form_stable_window() -> None:
    analyzer = OpenCVCandidateAnalyzer()
    observations = tuple(analyzer.analyze(sample(index)) for index in range(1, 4))

    result = StableWindowAssessor().assess(observations)

    assert result.stable
    assert result.best is not None
    assert result.best.frame.frame_id == FrameId("frame-3")
    assert dict(result.metrics)["min_mask_iou"] == 1.0


def test_motion_in_third_sample_prevents_selection() -> None:
    analyzer = OpenCVCandidateAnalyzer()
    observations = (
        analyzer.analyze(sample(1)),
        analyzer.analyze(sample(2)),
        analyzer.analyze(sample(3, spread_frame(shift=12))),
    )

    result = StableWindowAssessor().assess(observations)

    assert not result.stable
    assert result.best is None
    assert result.reasons in {
        (ReadinessReason.PAGE_MOVING,),
        (ReadinessReason.HAND_OR_PAGE_TURN,),
    }


def test_seam_proxy_moves_with_gutter_instead_of_staying_at_center() -> None:
    analyzer = OpenCVCandidateAnalyzer()

    left = analyzer.analyze(sample(1, spread_frame(shift=-12)))
    center = analyzer.analyze(sample(2, spread_frame()))
    right = analyzer.analyze(sample(3, spread_frame(shift=12)))

    assert left.seam_proxy_fraction is not None
    assert center.seam_proxy_fraction is not None
    assert right.seam_proxy_fraction is not None
    assert left.seam_proxy_fraction < center.seam_proxy_fraction < right.seam_proxy_fraction
    assert len({left.seam_proxy_fraction, center.seam_proxy_fraction, right.seam_proxy_fraction}) == 3


def test_candidate_analysis_resizes_before_segmentation_but_retains_original_frame() -> None:
    policy = CandidatePolicy(preview_max_dimension=320)
    analyzer = OpenCVCandidateAnalyzer(policy)
    original = cv2.resize(spread_frame(), (2000, 1500), interpolation=cv2.INTER_NEAREST)
    frame = sample(1, original)

    observation = analyzer.analyze(frame)
    metrics = dict(observation.candidate.metrics)

    assert observation.frame.payload.shape == (1500, 2000, 3)
    assert observation.candidate.width == 2000
    assert observation.candidate.height == 1500
    assert metrics["preview_width"] == 320
    assert metrics["preview_height"] == 240
    assert observation.mask_preview.shape == (240, 320)


def test_missing_pages_do_not_fall_back_to_constant_center_seam() -> None:
    analyzer = OpenCVCandidateAnalyzer()
    blank = np.zeros((300, 400, 3), dtype=np.uint8)

    observation = analyzer.analyze(sample(1, blank))

    assert observation.seam_proxy_fraction is None
    assert ReadinessReason.SEAM_FAILED in observation.candidate.retry_reasons
    assert dict(observation.candidate.metrics)["seam_proxy_available"] is False


def test_duplicate_frame_id_is_stale_not_stable() -> None:
    analyzer = OpenCVCandidateAnalyzer()
    observations = [analyzer.analyze(sample(index)) for index in range(1, 4)]
    duplicate = CandidateObservation(
        frame=FrameSample(observations[1].frame.frame_id, 2.0, observations[2].frame.payload),
        candidate=observations[2].candidate,
        page_centroids=observations[2].page_centroids,
        page_area_fractions=observations[2].page_area_fractions,
        seam_proxy_fraction=observations[2].seam_proxy_fraction,
        mask_preview=observations[2].mask_preview,
        gray_preview=observations[2].gray_preview,
    )

    result = StableWindowAssessor().assess((observations[0], observations[1], duplicate))

    assert not result.stable
    assert result.reasons == (ReadinessReason.STALE_FRAME,)


def test_best_selection_applies_hard_gate_before_sharpness() -> None:
    eligible = _observation("eligible", 1.0, margin=0.05, sharpness=10.0)
    clipped_but_sharp = _observation(
        "clipped", 2.0, margin=0.5, sharpness=10000.0, reasons=(ReadinessReason.OUT_OF_FRAME,)
    )

    best = StableWindowAssessor.select_best((eligible, clipped_but_sharp))

    assert best.frame.frame_id == FrameId("eligible")


def test_best_selection_prefers_margin_before_sharpness_then_sharpness() -> None:
    sharp_small_margin = _observation("sharp", 1.0, margin=0.04, sharpness=1000.0)
    softer_full_page = _observation("full", 2.0, margin=0.08, sharpness=5.0)
    same_margin_soft = _observation("soft", 3.0, margin=0.08, sharpness=4.0)

    assert StableWindowAssessor.select_best((sharp_small_margin, softer_full_page)).frame.frame_id == FrameId("full")
    assert StableWindowAssessor.select_best((same_margin_soft, softer_full_page)).frame.frame_id == FrameId("full")


def test_bounded_window_discards_oldest_without_growing() -> None:
    window = CandidateWindow(2)
    assert not window.append(_observation("1", 1.0))
    assert not window.append(_observation("2", 2.0))
    assert window.append(_observation("3", 3.0))
    assert len(window) == 2
    assert [item.frame.frame_id.value for item in window.snapshot()] == ["2", "3"]


def _observation(
    name: str,
    timestamp: float,
    *,
    margin: float = 0.1,
    sharpness: float = 5.0,
    reasons: tuple[ReadinessReason, ...] = (),
) -> CandidateObservation:
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    frame = FrameSample(FrameId(name), timestamp, image)
    candidate = FrameCandidate(
        frame.frame_id,
        timestamp,
        8,
        8,
        "test",
        metrics={
            "physical_edge_margin_fraction": margin,
            "mask_confidence_min": 0.9,
            "white_clip_fraction": 0.0,
            "black_clip_fraction": 0.0,
            "illumination_range": 0.1,
            "tenengrad": sharpness,
            "laplacian_variance": sharpness,
        },
        retry_reasons=reasons,
    )
    preview = np.ones((8, 8), dtype=np.uint8) * 255
    return CandidateObservation(frame, candidate, ((0.25, 0.5), (0.75, 0.5)), (0.3, 0.3), 0.5, preview, preview)
