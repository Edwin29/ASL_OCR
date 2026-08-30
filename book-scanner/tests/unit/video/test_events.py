from __future__ import annotations

import json

import pytest

from book_scanner.video.events import VideoEvent, VideoEventType
from book_scanner.video.types import ArtifactId, FrameId, ReadinessReason, VideoSessionState


def test_event_round_trip_includes_required_envelope() -> None:
    event = VideoEvent(
        event_type=VideoEventType.CANDIDATE_SELECTED,
        event_id="event-1",
        at_monotonic=2.5,
        session_id="session-1",
        producer_version="video-runtime-v1",
        session_state=VideoSessionState.PROCESSING_CANDIDATE,
        source_frame_id=FrameId("frame-1"),
        details={"rank": 1},
    )

    payload = json.loads(json.dumps(event.to_dict()))
    assert VideoEvent.from_dict(payload) == event


def test_frame_event_requires_source_frame_id() -> None:
    with pytest.raises(ValueError, match="requires source_frame_id"):
        VideoEvent(
            event_type=VideoEventType.CANDIDATE_OBSERVED,
            event_id="event-1",
            at_monotonic=0.0,
            session_id="session-1",
            producer_version="video-runtime-v1",
        )


def test_delivery_event_requires_artifact_id() -> None:
    with pytest.raises(ValueError, match="requires artifact_id"):
        VideoEvent(
            event_type=VideoEventType.DELIVERY_CONFIRMED,
            event_id="event-1",
            at_monotonic=0.0,
            session_id="session-1",
            producer_version="video-runtime-v1",
        )

    event = VideoEvent(
        event_type=VideoEventType.DELIVERY_CONFIRMED,
        event_id="event-2",
        at_monotonic=1.0,
        session_id="session-1",
        producer_version="video-runtime-v1",
        artifact_id=ArtifactId("artifact-1"),
    )
    assert event.artifact_id == ArtifactId("artifact-1")


def test_unknown_event_reason_is_rejected() -> None:
    payload = VideoEvent(
        event_type=VideoEventType.SESSION_ERROR,
        event_id="event-1",
        at_monotonic=0.0,
        session_id="session-1",
        producer_version="video-runtime-v1",
        reason=ReadinessReason.CAMERA_UNAVAILABLE,
    ).to_dict()
    payload["reason"] = "unknown"

    with pytest.raises(ValueError, match="unknown reason"):
        VideoEvent.from_dict(payload)
