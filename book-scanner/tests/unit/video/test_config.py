from __future__ import annotations

import pytest

from book_scanner.video.config import (
    CandidatePolicy,
    CorrectionPipeline,
    DeliveryAckLevel,
    ExtractionPipeline,
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
