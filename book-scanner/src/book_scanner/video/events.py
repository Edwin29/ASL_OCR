"""Serializable observations and guidance requests for video sessions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .types import (
    ArtifactId,
    FrameId,
    JsonScalar,
    MetricItems,
    ReadinessReason,
    SpreadId,
    VIDEO_SCHEMA_VERSION,
    VideoSessionState,
    _freeze_items,
    _parse_enum,
    _require_nonempty,
    _require_optional_string_value,
    _require_schema,
)


class VideoEventType(str, Enum):
    SESSION_STARTED = "session_started"
    SESSION_CANCELLED = "session_cancelled"
    SESSION_ERROR = "session_error"
    STATE_CHANGED = "state_changed"
    SOURCE_EXHAUSTED = "source_exhausted"
    CANDIDATE_OBSERVED = "candidate_observed"
    CANDIDATE_SELECTED = "candidate_selected"
    CANDIDATE_PROCESSED = "candidate_processed"
    GUIDANCE_REQUESTED = "guidance_requested"
    ARTIFACT_READY = "artifact_ready"
    UPLOAD_QUEUED = "upload_queued"
    UPLOAD_RETRYING = "upload_retrying"
    PARSER_REJECTED = "parser_rejected"
    DELIVERY_CONFIRMED = "delivery_confirmed"
    WAITING_FOR_PAGE_CHANGE = "waiting_for_page_change"
    PAGE_CHANGED = "page_changed"


_FRAME_EVENTS = {
    VideoEventType.CANDIDATE_OBSERVED,
    VideoEventType.CANDIDATE_SELECTED,
    VideoEventType.CANDIDATE_PROCESSED,
    VideoEventType.ARTIFACT_READY,
}
_ARTIFACT_EVENTS = {
    VideoEventType.ARTIFACT_READY,
    VideoEventType.UPLOAD_QUEUED,
    VideoEventType.UPLOAD_RETRYING,
    VideoEventType.PARSER_REJECTED,
    VideoEventType.DELIVERY_CONFIRMED,
    VideoEventType.WAITING_FOR_PAGE_CHANGE,
}


@dataclass(frozen=True, slots=True)
class VideoEvent:
    event_type: VideoEventType
    event_id: str
    at_monotonic: float
    session_id: str
    producer_version: str
    session_state: VideoSessionState | None = None
    source_frame_id: FrameId | None = None
    spread_id: SpreadId | None = None
    artifact_id: ArtifactId | None = None
    reason: ReadinessReason | None = None
    details: MetricItems | Mapping[str, JsonScalar] = ()
    schema_version: str = VIDEO_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(self.event_type, VideoEventType):
            raise TypeError("event_type must be a VideoEventType")
        _require_nonempty("event_id", self.event_id)
        _require_nonempty("session_id", self.session_id)
        _require_nonempty("producer_version", self.producer_version)
        if isinstance(self.at_monotonic, bool) or not isinstance(self.at_monotonic, (int, float)) or not math.isfinite(self.at_monotonic) or self.at_monotonic < 0:
            raise ValueError("at_monotonic must be finite and non-negative")
        if self.session_state is not None and not isinstance(self.session_state, VideoSessionState):
            raise TypeError("session_state must be a VideoSessionState")
        if self.reason is not None and not isinstance(self.reason, ReadinessReason):
            raise TypeError("reason must be a ReadinessReason")
        object.__setattr__(self, "details", _freeze_items(self.details))
        if self.event_type in _FRAME_EVENTS and self.source_frame_id is None:
            raise ValueError(f"{self.event_type.value} requires source_frame_id")
        if self.event_type in _ARTIFACT_EVENTS and self.artifact_id is None:
            raise ValueError(f"{self.event_type.value} requires artifact_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_type": self.event_type.value,
            "event_id": self.event_id,
            "at_monotonic": self.at_monotonic,
            "session_id": self.session_id,
            "producer_version": self.producer_version,
            "session_state": self.session_state.value if self.session_state else None,
            "source_frame_id": self.source_frame_id.value if self.source_frame_id else None,
            "spread_id": self.spread_id.value if self.spread_id else None,
            "artifact_id": self.artifact_id.value if self.artifact_id else None,
            "reason": self.reason.value if self.reason else None,
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> VideoEvent:
        _require_schema(payload.get("schema_version"))
        state = payload.get("session_state")
        reason = payload.get("reason")
        frame_id = payload.get("source_frame_id")
        spread_id = payload.get("spread_id")
        artifact_id = payload.get("artifact_id")
        _require_optional_string_value("source_frame_id", frame_id)
        _require_optional_string_value("spread_id", spread_id)
        _require_optional_string_value("artifact_id", artifact_id)
        details = payload.get("details")
        if not isinstance(details, Mapping):
            raise ValueError("details must be an object")
        return cls(
            event_type=_parse_enum(VideoEventType, payload.get("event_type"), "event_type"),
            event_id=_required_text(payload, "event_id"),
            at_monotonic=float(payload["at_monotonic"]),
            session_id=_required_text(payload, "session_id"),
            producer_version=_required_text(payload, "producer_version"),
            session_state=_parse_enum(VideoSessionState, state, "session_state") if state is not None else None,
            source_frame_id=FrameId(frame_id) if isinstance(frame_id, str) else None,
            spread_id=SpreadId(spread_id) if isinstance(spread_id, str) else None,
            artifact_id=ArtifactId(artifact_id) if isinstance(artifact_id, str) else None,
            reason=_parse_enum(ReadinessReason, reason, "reason") if reason is not None else None,
            details=details,
            schema_version=VIDEO_SCHEMA_VERSION,
        )


@dataclass(frozen=True, slots=True)
class GuidanceRequest:
    session_id: str
    reason: ReadinessReason
    requested_at_monotonic: float
    source_frame_id: FrameId | None = None
    spread_id: SpreadId | None = None
    stable_for_samples: int = 1
    stable_for_ms: int = 0

    def __post_init__(self) -> None:
        _require_nonempty("session_id", self.session_id)
        if not isinstance(self.reason, ReadinessReason):
            raise TypeError("reason must be a ReadinessReason")
        if not math.isfinite(self.requested_at_monotonic) or self.requested_at_monotonic < 0:
            raise ValueError("requested_at_monotonic must be finite and non-negative")
        if isinstance(self.stable_for_samples, bool) or self.stable_for_samples <= 0:
            raise ValueError("stable_for_samples must be positive")
        if isinstance(self.stable_for_ms, bool) or self.stable_for_ms < 0:
            raise ValueError("stable_for_ms must be non-negative")


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    _require_nonempty(key, value)
    return value
