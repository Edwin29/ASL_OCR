from __future__ import annotations

import pytest

from book_scanner.video.config import (
    CandidatePolicy,
    CorrectionPipeline,
    DeliveryAckLevel,
    ExtractionPipeline,
    IdentityPolicy,
    PageChangePolicy,
    PageNumberSchedulerMode,
    PageNumberSchedulerPolicy,
    ScannerPipelineConfig,
    VideoScannerConfig,
)


def test_default_pipeline_is_adopted_path_without_silent_fallback() -> None:
    config = VideoScannerConfig()

    assert config.pipeline.extraction is ExtractionPipeline.SEAM_CONSERVATIVE
    assert config.pipeline.correction is CorrectionPipeline.UVDOC_BILINEAR
    assert config.pipeline.allow_uncorrected_fallback is False
    assert config.delivery.success_ack_level is DeliveryAckLevel.PARSER_PREFLIGHT_ACCEPTED
    assert config.candidate.sample_interval_ms == 500
    assert config.candidate.stable_sample_count == 3
    assert config.candidate.preview_spine_overlap_fraction == 0.06
    assert config.pipeline.validated is False
    assert config.candidate.validated is False
    assert config.identity.algorithm_version == "page-identity-v3a-1"
    assert config.identity.validated is False
    assert config.page_change.sample_interval_ms == 750
    assert config.page_change.stable_sample_count == 3
    assert config.page_change.validated is False
    assert config.page_number_scheduler.mode is PageNumberSchedulerMode.EVERY_ELIGIBLE
    assert config.page_number_scheduler.validated is False


def test_identity_policy_keeps_visual_and_different_bands_separate() -> None:
    with pytest.raises(ValueError, match="hamming bands"):
        IdentityPolicy(visual_hamming_max=20, different_hamming_min=20)
    with pytest.raises(ValueError, match="feature-match bands"):
        IdentityPolicy(visual_feature_match_min=0.08, different_feature_match_max=0.08)


def test_page_change_policy_validates_pair_thresholds() -> None:
    with pytest.raises(ValueError, match="min_pair_hamming"):
        PageChangePolicy(min_pair_hamming=65)


def test_page_number_scheduler_policy_is_explicit_and_bounded() -> None:
    with pytest.raises(ValueError, match="audit_interval_eligible_samples"):
        PageNumberSchedulerPolicy(audit_interval_eligible_samples=0)
    with pytest.raises(TypeError, match="PageNumberSchedulerMode"):
        PageNumberSchedulerPolicy(mode="visual_triggered")  # type: ignore[arg-type]


def test_candidate_window_must_fit_stability_samples() -> None:
    with pytest.raises(ValueError, match="at least stable_sample_count"):
        CandidatePolicy(stable_sample_count=4, sample_window_size=3)


def test_silent_uncorrected_fallback_cannot_be_enabled() -> None:
    with pytest.raises(ValueError, match="fallback"):
        ScannerPipelineConfig(allow_uncorrected_fallback=True)


def test_provisional_configuration_requires_provenance() -> None:
    with pytest.raises(ValueError, match="provenance"):
        CandidatePolicy(provenance="")


def test_preview_seam_band_must_be_bounded() -> None:
    with pytest.raises(ValueError, match="less than 0.5"):
        CandidatePolicy(preview_seam_half_width_fraction=0.5)


def test_candidate_policy_requires_odd_motion_blur_kernel() -> None:
    with pytest.raises(ValueError, match="motion_blur_kernel_px must be odd"):
        CandidatePolicy(motion_blur_kernel_px=4)


def test_candidate_policy_requires_boolean_outer_contact_gate() -> None:
    with pytest.raises(TypeError, match="reject_outer_frame_contacts must be a bool"):
        CandidatePolicy(reject_outer_frame_contacts=1)  # type: ignore[arg-type]


def test_candidate_policy_validates_clipping_thresholds() -> None:
    with pytest.raises(ValueError, match="clipping_edge_depth_px"):
        CandidatePolicy(clipping_edge_depth_px=0)
    with pytest.raises(ValueError, match="clipping_ink_contrast"):
        CandidatePolicy(clipping_ink_contrast=256)
    with pytest.raises(TypeError, match="reject_confirmed_content_clipping"):
        CandidatePolicy(reject_confirmed_content_clipping=1)  # type: ignore[arg-type]
