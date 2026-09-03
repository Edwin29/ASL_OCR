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


class PageNumberSchedulerMode(str, Enum):
    EVERY_ELIGIBLE = "every_eligible"
    VISUAL_TRIGGERED = "visual_triggered"
    HYBRID_AUDITED = "hybrid_audited"


class OpaqueIdentityStrategy(str, Enum):
    M1_SELECTED_RAW_PAIR = "m1_selected_raw_pair"
    LEGACY_VISUAL = "legacy_visual"


class OpaqueFooterInputStage(str, Enum):
    PREVIEW_1920 = "preview_1920"
    PREVIEW_NATIVE = "preview_native"


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
    motion_blur_kernel_px: int = 9
    motion_alignment_max_shift_fraction: float = 0.012
    motion_alignment_min_correlation: float = 0.70
    reject_outer_frame_contacts: bool = False
    # Edge-strip ink is only a diagnostic proxy. Real p30 sample 104447 keeps
    # all OCR content even though the proxy fires at the physical page edge.
    reject_confirmed_content_clipping: bool = False
    clipping_edge_depth_px: int = 3
    clipping_bright_luminance: int = 110
    clipping_min_bright_edge_fraction: float = 0.04
    clipping_ink_background_luminance: int = 105
    clipping_ink_contrast: int = 22
    clipping_min_ink_edge_fraction: float = 0.005
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
        _positive("motion_blur_kernel_px", self.motion_blur_kernel_px)
        if self.motion_blur_kernel_px % 2 == 0:
            raise ValueError("motion_blur_kernel_px must be odd")
        _fraction("motion_alignment_max_shift_fraction", self.motion_alignment_max_shift_fraction)
        _fraction("motion_alignment_min_correlation", self.motion_alignment_min_correlation)
        if not isinstance(self.reject_outer_frame_contacts, bool):
            raise TypeError("reject_outer_frame_contacts must be a bool")
        if not isinstance(self.reject_confirmed_content_clipping, bool):
            raise TypeError("reject_confirmed_content_clipping must be a bool")
        _positive("clipping_edge_depth_px", self.clipping_edge_depth_px)
        for name in (
            "clipping_bright_luminance",
            "clipping_ink_background_luminance",
            "clipping_ink_contrast",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
                raise ValueError(f"{name} must be in [0, 255]")
        _fraction("clipping_min_bright_edge_fraction", self.clipping_min_bright_edge_fraction)
        _fraction("clipping_min_ink_edge_fraction", self.clipping_min_ink_edge_fraction)
        _fraction("max_white_clip_fraction", self.max_white_clip_fraction)
        _fraction("max_black_clip_fraction", self.max_black_clip_fraction)
        if self.sample_window_size < self.stable_sample_count:
            raise ValueError("sample_window_size must be at least stable_sample_count")
        _validate_provisional(self.validated, self.provenance)


@dataclass(frozen=True, slots=True)
class GuidancePolicy:
    reason_hold_samples: int = 3
    reason_hold_ms: int = 1000
    repeat_cooldown_ms: int = 15000
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
class IdentityPolicy:
    algorithm_version: str = "page-identity-v3a-1"
    normalized_width: int = 256
    normalized_height: int = 384
    projection_bins: int = 16
    orb_max_dimension: int = 768
    orb_features: int = 384
    visual_hamming_max: int = 8
    visual_hamming_relaxed_max: int = 28
    visual_projection_mae_max: float = 0.03
    visual_feature_match_min: float = 0.18
    different_hamming_min: int = 20
    different_projection_mae_min: float = 0.06
    different_feature_match_max: float = 0.08
    accepted_capacity: int = 32
    validated: bool = False
    provenance: str = "v3a_provisional_unvalidated"

    def __post_init__(self) -> None:
        if not isinstance(self.algorithm_version, str) or not self.algorithm_version.strip():
            raise ValueError("algorithm_version must be non-empty")
        _positive("normalized_width", self.normalized_width)
        _positive("normalized_height", self.normalized_height)
        _positive("projection_bins", self.projection_bins)
        _positive("orb_max_dimension", self.orb_max_dimension)
        _positive("orb_features", self.orb_features)
        if self.projection_bins > min(self.normalized_width, self.normalized_height):
            raise ValueError("projection_bins must fit both normalized dimensions")
        for name in ("visual_hamming_max", "visual_hamming_relaxed_max", "different_hamming_min"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 64:
                raise ValueError(f"{name} must be in [0, 64]")
        if self.visual_hamming_max >= self.different_hamming_min:
            raise ValueError("visual and different hamming bands must not overlap")
        if self.visual_hamming_relaxed_max < self.visual_hamming_max:
            raise ValueError("visual_hamming_relaxed_max must include the strict match band")
        _fraction("visual_projection_mae_max", self.visual_projection_mae_max)
        _fraction("visual_feature_match_min", self.visual_feature_match_min)
        _fraction("different_projection_mae_min", self.different_projection_mae_min)
        _fraction("different_feature_match_max", self.different_feature_match_max)
        if self.visual_projection_mae_max >= self.different_projection_mae_min:
            raise ValueError("visual and different projection bands must not overlap")
        if self.different_feature_match_max >= self.visual_feature_match_min:
            raise ValueError("different and visual feature-match bands must not overlap")
        _positive("accepted_capacity", self.accepted_capacity)
        _validate_provisional(self.validated, self.provenance)


@dataclass(frozen=True, slots=True)
class PageChangePolicy:
    sample_interval_ms: int = 750
    stable_sample_count: int = 3
    min_pair_hamming: int = 20
    min_pair_projection_mae: float = 0.02
    validated: bool = False
    provenance: str = "v3a_provisional_unvalidated"

    def __post_init__(self) -> None:
        _positive("sample_interval_ms", self.sample_interval_ms)
        _positive("stable_sample_count", self.stable_sample_count)
        if isinstance(self.min_pair_hamming, bool) or not isinstance(self.min_pair_hamming, int) or not 0 <= self.min_pair_hamming <= 64:
            raise ValueError("min_pair_hamming must be in [0, 64]")
        _fraction("min_pair_projection_mae", self.min_pair_projection_mae)
        _validate_provisional(self.validated, self.provenance)


@dataclass(frozen=True, slots=True)
class PageNumberPolicy:
    algorithm_version: str = "bottom-roi-page-number-v3a1-1"
    left_x_min: float = 0.0
    left_x_max: float = 0.35
    right_x_min: float = 0.65
    right_x_max: float = 1.0
    y_min: float = 0.80
    y_max: float = 1.0
    preview_max_dimension: int = 1920
    min_digits: int = 1
    max_digits: int = 4
    min_confidence: float = 0.62
    required_variant_agreement: int = 2
    stable_sample_count: int = 3
    cache_capacity: int = 32
    accepted_capacity: int = 32
    allow_number_only_duplicate: bool = False
    validated: bool = False
    provenance: str = "v3a1_provisional_unvalidated"

    def __post_init__(self) -> None:
        if not isinstance(self.algorithm_version, str) or not self.algorithm_version.strip():
            raise ValueError("algorithm_version must be non-empty")
        for name in ("left_x_min", "left_x_max", "right_x_min", "right_x_max", "y_min", "y_max"):
            _fraction(name, getattr(self, name))
        if self.left_x_min >= self.left_x_max or self.right_x_min >= self.right_x_max:
            raise ValueError("page-number ROI x bounds must be ordered")
        if self.y_min >= self.y_max:
            raise ValueError("page-number ROI y bounds must be ordered")
        _positive("preview_max_dimension", self.preview_max_dimension)
        _positive("min_digits", self.min_digits)
        _positive("max_digits", self.max_digits)
        if self.min_digits > self.max_digits:
            raise ValueError("min_digits must not exceed max_digits")
        _fraction("min_confidence", self.min_confidence)
        _positive("required_variant_agreement", self.required_variant_agreement)
        _positive("stable_sample_count", self.stable_sample_count)
        _positive("cache_capacity", self.cache_capacity)
        _positive("accepted_capacity", self.accepted_capacity)
        if not isinstance(self.allow_number_only_duplicate, bool):
            raise TypeError("allow_number_only_duplicate must be a bool")
        _validate_provisional(self.validated, self.provenance)


@dataclass(frozen=True, slots=True)
class PageNumberSchedulerPolicy:
    mode: PageNumberSchedulerMode = PageNumberSchedulerMode.EVERY_ELIGIBLE
    audit_interval_eligible_samples: int = 4
    burst_max_eligible_samples: int = 5
    validated: bool = False
    provenance: str = "v3a3_provisional_unvalidated"

    def __post_init__(self) -> None:
        if not isinstance(self.mode, PageNumberSchedulerMode):
            raise TypeError("mode must be a PageNumberSchedulerMode")
        _positive("audit_interval_eligible_samples", self.audit_interval_eligible_samples)
        _positive("burst_max_eligible_samples", self.burst_max_eligible_samples)
        _validate_provisional(self.validated, self.provenance)


@dataclass(frozen=True, slots=True)
class OpaqueFooterIdentityPolicy:
    strategy: OpaqueIdentityStrategy = OpaqueIdentityStrategy.M1_SELECTED_RAW_PAIR
    input_stage: OpaqueFooterInputStage = OpaqueFooterInputStage.PREVIEW_NATIVE
    observation_interval_ms: int = 100
    reference_bank_size: int = 5
    query_sample_count: int = 5
    k_same: int = 1
    k_different: int = 0
    max_collection_ms: int = 1500
    accepted_bank_capacity: int = 32
    max_recognition_in_flight: int = 1
    validated: bool = False
    provenance: str = "v3a4_two_spread_default_validation_deferred"

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, OpaqueIdentityStrategy):
            raise TypeError("strategy must be an OpaqueIdentityStrategy")
        if not isinstance(self.input_stage, OpaqueFooterInputStage):
            raise TypeError("input_stage must be an OpaqueFooterInputStage")
        for name in (
            "observation_interval_ms",
            "reference_bank_size",
            "query_sample_count",
            "max_collection_ms",
            "accepted_bank_capacity",
            "max_recognition_in_flight",
        ):
            _positive(name, getattr(self, name))
        if self.max_recognition_in_flight != 1:
            raise ValueError("M1 currently supports exactly one recognition in flight")
        if (
            isinstance(self.k_different, bool)
            or not isinstance(self.k_different, int)
            or isinstance(self.k_same, bool)
            or not isinstance(self.k_same, int)
            or not 0 <= self.k_different < self.k_same <= self.query_sample_count
        ):
            raise ValueError("thresholds must satisfy 0 <= k_different < k_same <= query_sample_count")
        _validate_provisional(self.validated, self.provenance)


@dataclass(frozen=True, slots=True)
class VideoScannerConfig:
    pipeline: ScannerPipelineConfig = field(default_factory=ScannerPipelineConfig)
    candidate: CandidatePolicy = field(default_factory=CandidatePolicy)
    guidance: GuidancePolicy = field(default_factory=GuidancePolicy)
    delivery: DeliveryPolicy = field(default_factory=DeliveryPolicy)
    identity: IdentityPolicy = field(default_factory=IdentityPolicy)
    page_change: PageChangePolicy = field(default_factory=PageChangePolicy)
    page_number: PageNumberPolicy = field(default_factory=PageNumberPolicy)
    page_number_scheduler: PageNumberSchedulerPolicy = field(
        default_factory=PageNumberSchedulerPolicy
    )
    opaque_footer_identity: OpaqueFooterIdentityPolicy = field(
        default_factory=OpaqueFooterIdentityPolicy
    )


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
