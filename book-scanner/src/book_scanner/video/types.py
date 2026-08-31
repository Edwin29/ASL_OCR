"""Immutable domain and wire types for the sampled-frame scanner runtime."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, TypeVar

VIDEO_SCHEMA_VERSION = "1.0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

JsonScalar = str | int | float | bool | None
MetricItems = tuple[tuple[str, JsonScalar], ...]


class VideoSessionState(str, Enum):
    IDLE = "idle"
    ARMING = "arming"
    SEARCHING = "searching"
    SETTLING = "settling"
    VERIFYING_IDENTITY = "verifying_identity"
    PROCESSING_CANDIDATE = "processing_candidate"
    LOCAL_RETRY = "local_retry"
    READY_FOR_SERVER_PREFLIGHT = "ready_for_server_preflight"
    UPLOADING = "uploading"
    REMOTE_RETRY = "remote_retry"
    PARSER_REJECTED = "parser_rejected"
    DELIVERY_CONFIRMED = "delivery_confirmed"
    WAITING_FOR_PAGE_CHANGE = "waiting_for_page_change"
    CANCELLING = "cancelling"
    ERROR = "error"


class ReadinessState(str, Enum):
    RETRY_LOCAL = "retry_local"
    READY_FOR_PREFLIGHT = "ready_for_preflight"
    RETRY_REMOTE = "retry_remote"
    ACCEPTED = "accepted"
    FATAL = "fatal"


class PreparationState(str, Enum):
    RETRY_LOCAL = "retry_local"
    PREPARED = "prepared"
    FATAL = "fatal"


class ReasonCategory(str, Enum):
    ACQUISITION = "acquisition"
    MOTION = "motion"
    LAYOUT = "layout"
    ILLUMINATION = "illumination"
    QUALITY = "quality"
    CORRECTION = "correction"
    PARSER = "parser"
    TRANSPORT = "transport"
    STORAGE = "storage"


class ReadinessReason(str, Enum):
    CAMERA_UNAVAILABLE = "camera_unavailable"
    FRAME_DECODE_FAILED = "frame_decode_failed"
    STALE_FRAME = "stale_frame"

    PAGE_MOVING = "page_moving"
    HAND_OR_PAGE_TURN = "hand_or_page_turn"

    PAGE_NOT_FOUND = "page_not_found"
    MOVE_LEFT = "move_left"
    MOVE_RIGHT = "move_right"
    MOVE_UP = "move_up"
    MOVE_DOWN = "move_down"
    ROTATE_CW = "rotate_cw"
    ROTATE_CCW = "rotate_ccw"
    OUT_OF_FRAME = "out_of_frame"

    UNDEREXPOSED = "underexposed"
    OVEREXPOSED = "overexposed"
    GLARE = "glare"
    SHADOW_UNEVEN = "shadow_uneven"

    BLUR = "blur"
    CONTENT_OCCLUDED = "content_occluded"
    INSUFFICIENT_RESOLUTION = "insufficient_resolution"
    WARP_ARTIFACT = "warp_artifact"

    SEAM_FAILED = "seam_failed"
    UVDOC_FAILED = "uvdoc_failed"
    UVDOC_CONFIGURATION_FAILED = "uvdoc_configuration_failed"
    UVDOC_INVALID_OUTPUT = "uvdoc_invalid_output"

    ARTIFACT_COMMIT_FAILED = "artifact_commit_failed"
    ARTIFACT_COLLISION = "artifact_collision"
    IDENTITY_FAILED = "identity_failed"
    FOOTER_IDENTITY_UNAVAILABLE = "footer_identity_unavailable"
    PAGE_NUMBER_FAILED = "page_number_failed"

    PARSER_QUALITY_REJECTED = "parser_quality_rejected"
    STRUCTURE_PREFLIGHT_FAILED = "structure_preflight_failed"

    NETWORK_UNAVAILABLE = "network_unavailable"
    SERVER_BUSY = "server_busy"
    AUTH_FAILED = "auth_failed"
    UPLOAD_CORRUPT = "upload_corrupt"


_REASON_CATEGORIES: dict[ReadinessReason, ReasonCategory] = {
    ReadinessReason.CAMERA_UNAVAILABLE: ReasonCategory.ACQUISITION,
    ReadinessReason.FRAME_DECODE_FAILED: ReasonCategory.ACQUISITION,
    ReadinessReason.STALE_FRAME: ReasonCategory.ACQUISITION,
    ReadinessReason.PAGE_MOVING: ReasonCategory.MOTION,
    ReadinessReason.HAND_OR_PAGE_TURN: ReasonCategory.MOTION,
    ReadinessReason.PAGE_NOT_FOUND: ReasonCategory.LAYOUT,
    ReadinessReason.MOVE_LEFT: ReasonCategory.LAYOUT,
    ReadinessReason.MOVE_RIGHT: ReasonCategory.LAYOUT,
    ReadinessReason.MOVE_UP: ReasonCategory.LAYOUT,
    ReadinessReason.MOVE_DOWN: ReasonCategory.LAYOUT,
    ReadinessReason.ROTATE_CW: ReasonCategory.LAYOUT,
    ReadinessReason.ROTATE_CCW: ReasonCategory.LAYOUT,
    ReadinessReason.OUT_OF_FRAME: ReasonCategory.LAYOUT,
    ReadinessReason.UNDEREXPOSED: ReasonCategory.ILLUMINATION,
    ReadinessReason.OVEREXPOSED: ReasonCategory.ILLUMINATION,
    ReadinessReason.GLARE: ReasonCategory.ILLUMINATION,
    ReadinessReason.SHADOW_UNEVEN: ReasonCategory.ILLUMINATION,
    ReadinessReason.BLUR: ReasonCategory.QUALITY,
    ReadinessReason.CONTENT_OCCLUDED: ReasonCategory.QUALITY,
    ReadinessReason.INSUFFICIENT_RESOLUTION: ReasonCategory.QUALITY,
    ReadinessReason.WARP_ARTIFACT: ReasonCategory.QUALITY,
    ReadinessReason.SEAM_FAILED: ReasonCategory.CORRECTION,
    ReadinessReason.UVDOC_FAILED: ReasonCategory.CORRECTION,
    ReadinessReason.UVDOC_CONFIGURATION_FAILED: ReasonCategory.CORRECTION,
    ReadinessReason.UVDOC_INVALID_OUTPUT: ReasonCategory.CORRECTION,
    ReadinessReason.ARTIFACT_COMMIT_FAILED: ReasonCategory.STORAGE,
    ReadinessReason.ARTIFACT_COLLISION: ReasonCategory.STORAGE,
    ReadinessReason.IDENTITY_FAILED: ReasonCategory.STORAGE,
    ReadinessReason.FOOTER_IDENTITY_UNAVAILABLE: ReasonCategory.QUALITY,
    ReadinessReason.PAGE_NUMBER_FAILED: ReasonCategory.QUALITY,
    ReadinessReason.PARSER_QUALITY_REJECTED: ReasonCategory.PARSER,
    ReadinessReason.STRUCTURE_PREFLIGHT_FAILED: ReasonCategory.PARSER,
    ReadinessReason.NETWORK_UNAVAILABLE: ReasonCategory.TRANSPORT,
    ReadinessReason.SERVER_BUSY: ReasonCategory.TRANSPORT,
    ReadinessReason.AUTH_FAILED: ReasonCategory.TRANSPORT,
    ReadinessReason.UPLOAD_CORRUPT: ReasonCategory.TRANSPORT,
}

_PHYSICAL_GUIDANCE_CATEGORIES = {
    ReasonCategory.MOTION,
    ReasonCategory.LAYOUT,
    ReasonCategory.ILLUMINATION,
    ReasonCategory.QUALITY,
}


def reason_category(reason: ReadinessReason) -> ReasonCategory:
    return _REASON_CATEGORIES[reason]


def is_physical_guidance_reason(reason: ReadinessReason) -> bool:
    """Whether the reason can reasonably ask the user to adjust the book/camera."""

    return reason_category(reason) in _PHYSICAL_GUIDANCE_CATEGORIES


class PageSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class FrameId:
    value: str

    def __post_init__(self) -> None:
        _require_nonempty("frame_id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SpreadId:
    value: str

    def __post_init__(self) -> None:
        _require_nonempty("spread_id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ArtifactId:
    value: str

    def __post_init__(self) -> None:
        _require_nonempty("artifact_id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ProcessingJobId:
    value: str

    def __post_init__(self) -> None:
        _require_nonempty("processing_job_id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class FrameCandidate:
    frame_id: FrameId
    captured_at_monotonic: float
    width: int
    height: int
    evaluator_version: str
    metrics: MetricItems | Mapping[str, JsonScalar] = ()
    retry_reasons: tuple[ReadinessReason, ...] = ()
    schema_version: str = VIDEO_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_nonempty("evaluator_version", self.evaluator_version)
        _require_nonnegative_finite("captured_at_monotonic", self.captured_at_monotonic)
        _require_positive_int("width", self.width)
        _require_positive_int("height", self.height)
        object.__setattr__(self, "metrics", _freeze_items(self.metrics))
        object.__setattr__(self, "retry_reasons", tuple(self.retry_reasons))
        _require_enum_items("retry_reasons", self.retry_reasons, ReadinessReason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "frame_id": self.frame_id.value,
            "captured_at_monotonic": self.captured_at_monotonic,
            "width": self.width,
            "height": self.height,
            "evaluator_version": self.evaluator_version,
            "metrics": dict(self.metrics),
            "retry_reasons": [item.value for item in self.retry_reasons],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> FrameCandidate:
        _require_schema(payload.get("schema_version"))
        return cls(
            frame_id=FrameId(_required_string(payload, "frame_id")),
            captured_at_monotonic=float(payload["captured_at_monotonic"]),
            width=_required_int(payload, "width"),
            height=_required_int(payload, "height"),
            evaluator_version=_required_string(payload, "evaluator_version"),
            metrics=_required_mapping(payload, "metrics"),
            retry_reasons=tuple(_parse_enum(ReadinessReason, value, "retry_reasons") for value in _required_list(payload, "retry_reasons")),
            schema_version=VIDEO_SCHEMA_VERSION,
        )


@dataclass(frozen=True, slots=True)
class PageArtifactRef:
    side: PageSide
    source_frame_id: FrameId
    image_path: str
    sha256: str
    width: int
    height: int

    def __post_init__(self) -> None:
        if not isinstance(self.side, PageSide):
            raise TypeError("side must be a PageSide")
        if not isinstance(self.source_frame_id, FrameId):
            raise TypeError("source_frame_id must be a FrameId")
        _require_nonempty("image_path", self.image_path)
        _require_sha256("sha256", self.sha256)
        _require_positive_int("width", self.width)
        _require_positive_int("height", self.height)

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side.value,
            "source_frame_id": self.source_frame_id.value,
            "image_path": self.image_path,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PageArtifactRef:
        return cls(
            side=_parse_enum(PageSide, payload.get("side"), "side"),
            source_frame_id=FrameId(_required_string(payload, "source_frame_id")),
            image_path=_required_string(payload, "image_path"),
            sha256=_required_string(payload, "sha256"),
            width=_required_int(payload, "width"),
            height=_required_int(payload, "height"),
        )


@dataclass(frozen=True, slots=True)
class PreparedPageArtifact:
    side: PageSide
    source_frame_id: FrameId
    image_relative_path: str
    sha256: str
    width: int
    height: int

    def __post_init__(self) -> None:
        if not isinstance(self.side, PageSide):
            raise TypeError("side must be a PageSide")
        if not isinstance(self.source_frame_id, FrameId):
            raise TypeError("source_frame_id must be a FrameId")
        _require_nonempty("image_relative_path", self.image_relative_path)
        _require_sha256("sha256", self.sha256)
        _require_positive_int("width", self.width)
        _require_positive_int("height", self.height)

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side.value,
            "source_frame_id": self.source_frame_id.value,
            "image_relative_path": self.image_relative_path,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PreparedPageArtifact:
        return cls(
            side=_parse_enum(PageSide, payload.get("side"), "side"),
            source_frame_id=FrameId(_required_string(payload, "source_frame_id")),
            image_relative_path=_required_string(payload, "image_relative_path"),
            sha256=_required_string(payload, "sha256"),
            width=_required_int(payload, "width"),
            height=_required_int(payload, "height"),
        )


@dataclass(frozen=True, slots=True)
class PreparedSpreadArtifact:
    artifact_id: ArtifactId
    session_id: str
    job_id: ProcessingJobId
    spread_id: SpreadId
    source_frame_id: FrameId
    staging_path: str
    manifest_relative_path: str
    manifest_sha256: str
    left: PreparedPageArtifact
    right: PreparedPageArtifact
    evaluator_version: str
    schema_version: str = VIDEO_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        _require_nonempty("session_id", self.session_id)
        if not isinstance(self.job_id, ProcessingJobId):
            raise TypeError("job_id must be a ProcessingJobId")
        if not isinstance(self.spread_id, SpreadId):
            raise TypeError("spread_id must be a SpreadId")
        if not isinstance(self.source_frame_id, FrameId):
            raise TypeError("source_frame_id must be a FrameId")
        if not isinstance(self.left, PreparedPageArtifact) or not isinstance(self.right, PreparedPageArtifact):
            raise TypeError("left and right must be PreparedPageArtifact values")
        if self.left.side is not PageSide.LEFT or self.right.side is not PageSide.RIGHT:
            raise ValueError("prepared page sides do not match left/right")
        if self.left.source_frame_id != self.source_frame_id or self.right.source_frame_id != self.source_frame_id:
            raise ValueError("prepared pages must share source_frame_id")
        _require_nonempty("staging_path", self.staging_path)
        _require_nonempty("manifest_relative_path", self.manifest_relative_path)
        _require_sha256("manifest_sha256", self.manifest_sha256)
        _require_nonempty("evaluator_version", self.evaluator_version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id.value,
            "session_id": self.session_id,
            "job_id": self.job_id.value,
            "spread_id": self.spread_id.value,
            "source_frame_id": self.source_frame_id.value,
            "staging_path": self.staging_path,
            "manifest_relative_path": self.manifest_relative_path,
            "manifest_sha256": self.manifest_sha256,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "evaluator_version": self.evaluator_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PreparedSpreadArtifact:
        _require_schema(payload.get("schema_version"))
        return cls(
            artifact_id=ArtifactId(_required_string(payload, "artifact_id")),
            session_id=_required_string(payload, "session_id"),
            job_id=ProcessingJobId(_required_string(payload, "job_id")),
            spread_id=SpreadId(_required_string(payload, "spread_id")),
            source_frame_id=FrameId(_required_string(payload, "source_frame_id")),
            staging_path=_required_string(payload, "staging_path"),
            manifest_relative_path=_required_string(payload, "manifest_relative_path"),
            manifest_sha256=_required_string(payload, "manifest_sha256"),
            left=PreparedPageArtifact.from_dict(_required_mapping(payload, "left")),
            right=PreparedPageArtifact.from_dict(_required_mapping(payload, "right")),
            evaluator_version=_required_string(payload, "evaluator_version"),
        )


@dataclass(frozen=True, slots=True)
class PreparationDecision:
    state: PreparationState
    evaluator_version: str
    job_id: ProcessingJobId
    source_frame_id: FrameId
    spread_id: SpreadId
    reasons: tuple[ReadinessReason, ...] = ()
    prepared: PreparedSpreadArtifact | None = None
    metrics: MetricItems | Mapping[str, JsonScalar] = ()
    retry_after_ms: int | None = None
    schema_version: str = VIDEO_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.state, PreparationState):
            raise TypeError("state must be a PreparationState")
        if not isinstance(self.job_id, ProcessingJobId):
            raise TypeError("job_id must be a ProcessingJobId")
        if not isinstance(self.source_frame_id, FrameId):
            raise TypeError("source_frame_id must be a FrameId")
        if not isinstance(self.spread_id, SpreadId):
            raise TypeError("spread_id must be a SpreadId")
        _require_nonempty("evaluator_version", self.evaluator_version)
        object.__setattr__(self, "reasons", tuple(self.reasons))
        _require_enum_items("reasons", self.reasons, ReadinessReason)
        object.__setattr__(self, "metrics", _freeze_items(self.metrics))
        if self.state in {PreparationState.RETRY_LOCAL, PreparationState.FATAL} and not self.reasons:
            raise ValueError(f"{self.state.value} requires at least one reason")
        if self.state is PreparationState.PREPARED and self.prepared is None:
            raise ValueError("prepared state requires a prepared artifact")
        if self.state is not PreparationState.PREPARED and self.prepared is not None:
            raise ValueError("only prepared state may contain a prepared artifact")
        if self.prepared is not None and (
            self.prepared.job_id != self.job_id
            or self.prepared.source_frame_id != self.source_frame_id
            or self.prepared.spread_id != self.spread_id
        ):
            raise ValueError("preparation decision lineage does not match prepared artifact")
        if self.retry_after_ms is not None and (
            isinstance(self.retry_after_ms, bool)
            or not isinstance(self.retry_after_ms, int)
            or self.retry_after_ms < 0
        ):
            raise ValueError("retry_after_ms must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "state": self.state.value,
            "evaluator_version": self.evaluator_version,
            "job_id": self.job_id.value,
            "source_frame_id": self.source_frame_id.value,
            "spread_id": self.spread_id.value,
            "reasons": [reason.value for reason in self.reasons],
            "prepared": self.prepared.to_dict() if self.prepared else None,
            "metrics": dict(self.metrics),
            "retry_after_ms": self.retry_after_ms,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PreparationDecision:
        _require_schema(payload.get("schema_version"))
        prepared = payload.get("prepared")
        if prepared is not None and not isinstance(prepared, Mapping):
            raise ValueError("prepared must be an object or null")
        return cls(
            state=_parse_enum(PreparationState, payload.get("state"), "state"),
            evaluator_version=_required_string(payload, "evaluator_version"),
            job_id=ProcessingJobId(_required_string(payload, "job_id")),
            source_frame_id=FrameId(_required_string(payload, "source_frame_id")),
            spread_id=SpreadId(_required_string(payload, "spread_id")),
            reasons=tuple(
                _parse_enum(ReadinessReason, value, "reasons")
                for value in _required_list(payload, "reasons")
            ),
            prepared=PreparedSpreadArtifact.from_dict(prepared) if isinstance(prepared, Mapping) else None,
            metrics=_required_mapping(payload, "metrics"),
            retry_after_ms=_optional_int(payload, "retry_after_ms"),
        )


@dataclass(frozen=True, slots=True)
class SpreadArtifactRef:
    artifact_id: ArtifactId
    spread_id: SpreadId
    source_frame_id: FrameId
    left: PageArtifactRef
    right: PageArtifactRef
    manifest_path: str
    manifest_sha256: str
    evaluator_version: str
    schema_version: str = VIDEO_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        if not isinstance(self.spread_id, SpreadId):
            raise TypeError("spread_id must be a SpreadId")
        if not isinstance(self.source_frame_id, FrameId):
            raise TypeError("source_frame_id must be a FrameId")
        if not isinstance(self.left, PageArtifactRef) or not isinstance(self.right, PageArtifactRef):
            raise ValueError("both left and right page artifacts are required")
        if self.left.side is not PageSide.LEFT or self.right.side is not PageSide.RIGHT:
            raise ValueError("left/right page artifacts must have matching sides")
        if self.left.source_frame_id != self.source_frame_id or self.right.source_frame_id != self.source_frame_id:
            raise ValueError("left and right page artifacts must share source_frame_id")
        _require_nonempty("manifest_path", self.manifest_path)
        _require_sha256("manifest_sha256", self.manifest_sha256)
        _require_nonempty("evaluator_version", self.evaluator_version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id.value,
            "spread_id": self.spread_id.value,
            "source_frame_id": self.source_frame_id.value,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
            "evaluator_version": self.evaluator_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SpreadArtifactRef:
        _require_schema(payload.get("schema_version"))
        return cls(
            artifact_id=ArtifactId(_required_string(payload, "artifact_id")),
            spread_id=SpreadId(_required_string(payload, "spread_id")),
            source_frame_id=FrameId(_required_string(payload, "source_frame_id")),
            left=PageArtifactRef.from_dict(_required_mapping(payload, "left")),
            right=PageArtifactRef.from_dict(_required_mapping(payload, "right")),
            manifest_path=_required_string(payload, "manifest_path"),
            manifest_sha256=_required_string(payload, "manifest_sha256"),
            evaluator_version=_required_string(payload, "evaluator_version"),
            schema_version=VIDEO_SCHEMA_VERSION,
        )


@dataclass(frozen=True, slots=True)
class ReadinessDecision:
    state: ReadinessState
    evaluator_version: str
    reasons: tuple[ReadinessReason, ...] = ()
    primary_guidance_reason: ReadinessReason | None = None
    source_frame_id: FrameId | None = None
    spread_id: SpreadId | None = None
    artifact: SpreadArtifactRef | None = None
    metrics: MetricItems | Mapping[str, JsonScalar] = ()
    retry_after_ms: int | None = None
    delivery_receipt_id: str | None = None
    schema_version: str = VIDEO_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.state, ReadinessState):
            raise TypeError("state must be a ReadinessState")
        _require_nonempty("evaluator_version", self.evaluator_version)
        object.__setattr__(self, "reasons", tuple(self.reasons))
        _require_enum_items("reasons", self.reasons, ReadinessReason)
        object.__setattr__(self, "metrics", _freeze_items(self.metrics))

        if self.primary_guidance_reason is not None and self.primary_guidance_reason not in self.reasons:
            raise ValueError("primary_guidance_reason must be present in reasons")
        if self.state in {ReadinessState.RETRY_LOCAL, ReadinessState.RETRY_REMOTE, ReadinessState.FATAL} and not self.reasons:
            raise ValueError(f"{self.state.value} requires at least one reason")
        if self.state in {ReadinessState.READY_FOR_PREFLIGHT, ReadinessState.RETRY_REMOTE, ReadinessState.ACCEPTED} and self.artifact is None:
            raise ValueError(f"{self.state.value} requires an artifact")
        if self.artifact is not None:
            if self.source_frame_id is not None and self.artifact.source_frame_id != self.source_frame_id:
                raise ValueError("decision source_frame_id does not match artifact")
            if self.spread_id is not None and self.artifact.spread_id != self.spread_id:
                raise ValueError("decision spread_id does not match artifact")
        if self.retry_after_ms is not None and (isinstance(self.retry_after_ms, bool) or self.retry_after_ms < 0):
            raise ValueError("retry_after_ms must be a non-negative integer")
        if self.state is ReadinessState.ACCEPTED:
            _require_nonempty("delivery_receipt_id", self.delivery_receipt_id)
        elif self.delivery_receipt_id is not None:
            raise ValueError("delivery_receipt_id is only valid for accepted decisions")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "state": self.state.value,
            "evaluator_version": self.evaluator_version,
            "reasons": [item.value for item in self.reasons],
            "primary_guidance_reason": self.primary_guidance_reason.value if self.primary_guidance_reason else None,
            "source_frame_id": self.source_frame_id.value if self.source_frame_id else None,
            "spread_id": self.spread_id.value if self.spread_id else None,
            "artifact": self.artifact.to_dict() if self.artifact else None,
            "metrics": dict(self.metrics),
            "retry_after_ms": self.retry_after_ms,
            "delivery_receipt_id": self.delivery_receipt_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ReadinessDecision:
        _require_schema(payload.get("schema_version"))
        primary = payload.get("primary_guidance_reason")
        artifact = payload.get("artifact")
        frame_id = payload.get("source_frame_id")
        spread_id = payload.get("spread_id")
        if artifact is not None and not isinstance(artifact, Mapping):
            raise ValueError("artifact must be an object or null")
        _require_optional_string_value("source_frame_id", frame_id)
        _require_optional_string_value("spread_id", spread_id)
        return cls(
            state=_parse_enum(ReadinessState, payload.get("state"), "state"),
            evaluator_version=_required_string(payload, "evaluator_version"),
            reasons=tuple(_parse_enum(ReadinessReason, value, "reasons") for value in _required_list(payload, "reasons")),
            primary_guidance_reason=(
                _parse_enum(ReadinessReason, primary, "primary_guidance_reason") if primary is not None else None
            ),
            source_frame_id=FrameId(frame_id) if isinstance(frame_id, str) else None,
            spread_id=SpreadId(spread_id) if isinstance(spread_id, str) else None,
            artifact=SpreadArtifactRef.from_dict(artifact) if isinstance(artifact, Mapping) else None,
            metrics=_required_mapping(payload, "metrics"),
            retry_after_ms=_optional_int(payload, "retry_after_ms"),
            delivery_receipt_id=_optional_string(payload, "delivery_receipt_id"),
            schema_version=VIDEO_SCHEMA_VERSION,
        )


EnumT = TypeVar("EnumT", bound=Enum)


def _parse_enum(enum_type: type[EnumT], value: object, field_name: str) -> EnumT:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unknown {field_name}: {value!r}") from exc


def _freeze_items(items: MetricItems | Mapping[str, JsonScalar] | Iterable[tuple[str, JsonScalar]]) -> MetricItems:
    source = items.items() if isinstance(items, Mapping) else items
    result: list[tuple[str, JsonScalar]] = []
    seen: set[str] = set()
    for key, value in source:
        _require_nonempty("metric key", key)
        if key in seen:
            raise ValueError(f"duplicate metric key: {key}")
        if not isinstance(value, (str, int, float, bool)) and value is not None:
            raise TypeError(f"metric {key!r} must be a JSON scalar")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"metric {key!r} must be finite")
        seen.add(key)
        result.append((key, value))
    return tuple(result)


def _require_enum_items(field_name: str, values: Iterable[object], enum_type: type[Enum]) -> None:
    if any(not isinstance(value, enum_type) for value in values):
        raise TypeError(f"{field_name} must contain only {enum_type.__name__} values")


def _require_schema(value: object) -> None:
    if value != VIDEO_SCHEMA_VERSION:
        raise ValueError(f"unsupported video schema version: {value!r}")


def _require_nonempty(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_sha256(field_name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")


def _require_positive_int(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_nonnegative_finite(field_name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    _require_nonempty(key, value)
    return value


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    _require_nonempty(key, value)
    return value


def _require_optional_string_value(field_name: str, value: object) -> None:
    if value is not None:
        _require_nonempty(field_name, value)


def _required_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _required_list(payload: Mapping[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value
