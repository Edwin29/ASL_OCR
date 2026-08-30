"""Explicit, provisional policy configuration for the video runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .types import ReasonCategory


class ExtractionPipeline(str, Enum):
    SEAM_CONSERVATIVE = "seam_conservative"


class CorrectionPipeline(str, Enum):
    UVDOC_BILINEAR = "uvdoc_bilinear"


class DeliveryAckLevel(str, Enum):
    INGEST_ACCEPTED = "ingest_accepted"
    PARSER_PREFLIGHT_ACCEPTED = "parser_preflight_accepted"


@dataclass(frozen=True, slots=True)
class ScannerPipelineConfig:
    extraction: ExtractionPipeline = ExtractionPipeline.SEAM_CONSERVATIVE
    correction: CorrectionPipeline = CorrectionPipeline.UVDOC_BILINEAR
    allow_uncorrected_fallback: bool = False
    validated: bool = False
    provenance: str = "v0_provisional"

    def __post_init__(self) -> None:
        if not isinstance(self.extraction, ExtractionPipeline):
            raise TypeError("extraction must be an ExtractionPipeline")
        if not isinstance(self.correction, CorrectionPipeline):
            raise TypeError("correction must be a CorrectionPipeline")
        if self.allow_uncorrected_fallback:
            raise ValueError("silent uncorrected fallback is not allowed")
        _validate_provisional(self.validated, self.provenance)


@dataclass(frozen=True, slots=True)
class CandidatePolicy:
    sample_interval_ms: int = 500
    stable_sample_count: int = 3
    sample_window_size: int = 5
    local_retry_cooldown_ms: int = 1000
    preview_max_dimension: int = 640
    preview_spine_overlap_fraction: float = 0.06
    preview_seam_half_width_fraction: float = 0.08
    preview_seam_center_prior_weight: float = 0.08
    min_frame_width: int = 320
    min_frame_height: int = 240
    min_mask_iou: float = 0.96
    max_centroid_shift_fraction: float = 0.015
    max_area_change_fraction: float = 0.05
    max_seam_shift_fraction: float = 0.02
    max_motion_fraction: float = 0.03
    max_connected_motion_fraction: float = 0.08
    motion_pixel_threshold: int = 24
    max_white_clip_fraction: float = 0.65
    max_black_clip_fraction: float = 0.65
    validated: bool = False
    provenance: str = "v0_provisional"

    def __post_init__(self) -> None:
        _positive("sample_interval_ms", self.sample_interval_ms)
        _positive("stable_sample_count", self.stable_sample_count)
        _positive("sample_window_size", self.sample_window_size)
        _nonnegative("local_retry_cooldown_ms", self.local_retry_cooldown_ms)
        _positive("preview_max_dimension", self.preview_max_dimension)
        _fraction("preview_spine_overlap_fraction", self.preview_spine_overlap_fraction)
        _fraction(
            "preview_seam_half_width_fraction",
            self.preview_seam_half_width_fraction,
            allow_zero=False,
        )
        if self.preview_seam_half_width_fraction >= 0.5:
            raise ValueError("preview_seam_half_width_fraction must be less than 0.5")
        _fraction("preview_seam_center_prior_weight", self.preview_seam_center_prior_weight)
        _positive("min_frame_width", self.min_frame_width)
        _positive("min_frame_height", self.min_frame_height)
        _fraction("min_mask_iou", self.min_mask_iou, allow_zero=False)
        _fraction("max_centroid_shift_fraction", self.max_centroid_shift_fraction)
        _fraction("max_area_change_fraction", self.max_area_change_fraction)
        _fraction("max_seam_shift_fraction", self.max_seam_shift_fraction)
        _fraction("max_motion_fraction", self.max_motion_fraction)
        _fraction("max_connected_motion_fraction", self.max_connected_motion_fraction)
        if isinstance(self.motion_pixel_threshold, bool) or not 0 <= self.motion_pixel_threshold <= 255:
            raise ValueError("motion_pixel_threshold must be in [0, 255]")
        _fraction("max_white_clip_fraction", self.max_white_clip_fraction)
        _fraction("max_black_clip_fraction", self.max_black_clip_fraction)
        if self.sample_window_size < self.stable_sample_count:
            raise ValueError("sample_window_size must be at least stable_sample_count")
        _validate_provisional(self.validated, self.provenance)


@dataclass(frozen=True, slots=True)
class GuidancePolicy:
    reason_hold_samples: int = 3
    reason_hold_ms: int = 1000
    repeat_cooldown_ms: int = 5000
    validated: bool = False
    provenance: str = "v0_provisional"

    def __post_init__(self) -> None:
        _positive("reason_hold_samples", self.reason_hold_samples)
        _nonnegative("reason_hold_ms", self.reason_hold_ms)
        _nonnegative("repeat_cooldown_ms", self.repeat_cooldown_ms)
        _validate_provisional(self.validated, self.provenance)


@dataclass(frozen=True, slots=True)
class DeliveryPolicy:
    success_ack_level: DeliveryAckLevel = DeliveryAckLevel.PARSER_PREFLIGHT_ACCEPTED
    retry_categories: tuple[ReasonCategory, ...] = (ReasonCategory.TRANSPORT,)
    validated: bool = False
    provenance: str = "v0_provisional"

    def __post_init__(self) -> None:
        if not isinstance(self.success_ack_level, DeliveryAckLevel):
            raise TypeError("success_ack_level must be a DeliveryAckLevel")
        object.__setattr__(self, "retry_categories", tuple(self.retry_categories))
        if not self.retry_categories or any(not isinstance(item, ReasonCategory) for item in self.retry_categories):
            raise TypeError("retry_categories must contain ReasonCategory values")
        _validate_provisional(self.validated, self.provenance)


@dataclass(frozen=True, slots=True)
class VideoScannerConfig:
    pipeline: ScannerPipelineConfig = field(default_factory=ScannerPipelineConfig)
    candidate: CandidatePolicy = field(default_factory=CandidatePolicy)
    guidance: GuidancePolicy = field(default_factory=GuidancePolicy)
    delivery: DeliveryPolicy = field(default_factory=DeliveryPolicy)


def _validate_provisional(validated: bool, provenance: str) -> None:
    if not isinstance(validated, bool):
        raise TypeError("validated must be a bool")
    if not isinstance(provenance, str) or not provenance.strip():
        raise ValueError("provenance must be a non-empty string")


def _positive(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _nonnegative(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _fraction(name: str, value: float, *, allow_zero: bool = True) -> None:
    lower_ok = value >= 0 if allow_zero else value > 0
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lower_ok or value > 1:
        interval = "[0, 1]" if allow_zero else "(0, 1]"
        raise ValueError(f"{name} must be in {interval}")
