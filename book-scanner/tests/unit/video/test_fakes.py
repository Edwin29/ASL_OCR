from __future__ import annotations

import pytest

from book_scanner.video.events import GuidanceRequest
from book_scanner.video.protocols import ButtonCommand, FrameSample
from book_scanner.video.types import (
    FrameId,
    ReadinessDecision,
    ReadinessReason,
    ReadinessState,
    SpreadId,
)
from tests.unit.video.fakes import (
    FakeButtonSource,
    FakeCameraSource,
    FakeGuidanceSink,
    FakeParserClient,
    FakeSpreadProcessor,
    ManualClock,
    ParserResponseSpec,
    make_artifact,
)


def test_fake_camera_stops_producing_frames() -> None:
    frames = [FrameSample(FrameId("frame-1"), 0.0, "pixels")]
    camera = FakeCameraSource(frames)

    assert camera.read() is None
    camera.start()
    camera.stop()
    assert camera.read() is None


def test_fake_parser_is_idempotent_per_key() -> None:
    item = make_artifact()
    parser = FakeParserClient(
        [
            ParserResponseSpec(ReadinessState.ACCEPTED, delivery_receipt_id="job-1"),
            ParserResponseSpec(
                ReadinessState.RETRY_REMOTE,
                reasons=(ReadinessReason.SERVER_BUSY,),
                retry_after_ms=100,
            ),
        ]
    )

    first = parser.preflight_and_submit(item, "same-key")
    second = parser.preflight_and_submit(item, "same-key")
    third = parser.preflight_and_submit(item, "new-key")

    assert first is second
    assert first.delivery_receipt_id == "job-1"
    assert third.state is ReadinessState.RETRY_REMOTE
    assert len(parser.calls) == 3


def test_fake_parser_rejects_same_key_for_different_artifact() -> None:
    parser = FakeParserClient(
        [ParserResponseSpec(ReadinessState.ACCEPTED, delivery_receipt_id="job-1")]
    )
    parser.preflight_and_submit(make_artifact(), "same-key")

    with pytest.raises(ValueError, match="different artifact"):
        parser.preflight_and_submit(
            make_artifact(frame="frame-2", artifact_name="artifact-2"),
            "same-key",
        )


def test_fake_dependencies_record_deterministic_inputs() -> None:
    frame = FrameSample(FrameId("frame-1"), 2.0, "pixels")
    spread_id = SpreadId("spread-1")
    processor = FakeSpreadProcessor(
        lambda incoming, _spread: ReadinessDecision(
            ReadinessState.RETRY_LOCAL,
            "fake-spread-v1",
            reasons=(ReadinessReason.PAGE_MOVING,),
            source_frame_id=incoming.frame_id,
        )
    )
    guidance = FakeGuidanceSink()
    request = GuidanceRequest("session-1", ReadinessReason.MOVE_RIGHT, 2.0, source_frame_id=frame.frame_id)

    decision = processor.process(frame, spread_id)
    guidance.emit(request)

    assert processor.calls == [(frame, spread_id)]
    assert decision.source_frame_id == frame.frame_id
    assert guidance.requests == [request]
    assert list(FakeButtonSource([ButtonCommand.START, ButtonCommand.CANCEL]).events()) == [
        ButtonCommand.START,
        ButtonCommand.CANCEL,
    ]


def test_manual_clock_only_moves_forward() -> None:
    clock = ManualClock(1.0)
    assert clock.advance(0.5) == 1.5
    assert clock.monotonic() == 1.5
