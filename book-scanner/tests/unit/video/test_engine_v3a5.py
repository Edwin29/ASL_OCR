from __future__ import annotations

import time
from dataclasses import replace

import pytest

from book_scanner.video.config import OpaqueFooterIdentityPolicy
from book_scanner.video.events import VideoEventType
from book_scanner.video.types import VideoSessionState
from book_scanner.video.types import FrameId, ReadinessReason

from .fakes import FakeIdentityProvider
from .test_engine_v3a import _artifact_id, _engine
from .test_engine_v3a1 import _FakePageNumberProvider


class _VisualDuplicateIdentityProvider(FakeIdentityProvider):
    def fingerprint_artifact(self, artifact):
        identity = super().fingerprint_artifact(artifact)
        if len(self.artifact_calls) == 1:
            return identity
        return replace(
            identity,
            left=replace(identity.left, corrected_sha256="d" * 64),
            right=replace(identity.right, corrected_sha256="e" * 64),
        )


def _policy(**overrides) -> OpaqueFooterIdentityPolicy:
    values = {
        "observation_interval_ms": 100,
        "query_sample_count": 5,
        "reference_bank_size": 5,
        "k_same": 1,
        "k_different": 0,
        "max_collection_ms": 1500,
    }
    values.update(overrides)
    return OpaqueFooterIdentityPolicy(**values)


def _poll_until(engine, clock, target: VideoSessionState, limit: int = 300):
    events = []
    for _ in range(limit):
        events.extend(engine.poll())
        if engine.state is target:
            return events
        clock.advance(0.1)
        time.sleep(0.001)
    raise AssertionError(f"engine did not reach {target.value}: {engine.state.value}")


def _start_and_reach_ready(engine, clock):
    events = list(engine.start())
    events.extend(_poll_until(engine, clock, VideoSessionState.READY_FOR_SERVER_PREFLIGHT))
    return events


def test_m1_requires_explicit_recognition_provider() -> None:
    with pytest.raises(ValueError, match="explicit page-number provider"):
        engine, *_ = _engine(opaque_identity_policy=_policy())
        engine.close()


def test_first_spread_collects_five_valid_pairs_before_single_v2_preparation() -> None:
    provider = _FakePageNumberProvider([], preview_labels=[("30", "309")] * 5)
    engine, clock, _camera, preparer, store, _visual_ledger = _engine(
        frame_count=12,
        page_number_provider=provider,
        opaque_identity_policy=_policy(),
    )

    events = _start_and_reach_ready(engine, clock)

    assert provider.preview_calls == 5
    assert len(preparer.calls) == 1
    assert len(store.commits) == 1
    assert sum(event.event_type is VideoEventType.OPAQUE_IDENTITY_OBSERVED for event in events) == 5
    assert sum(event.event_type is VideoEventType.OPAQUE_IDENTITY_BANK_PENDING for event in events) == 1
    assert engine.opaque_identity_ledger is not None
    assert engine.opaque_identity_ledger.recent_accepted() == ()
    assert engine.opaque_identity_ledger.pending_artifact_id == _artifact_id(events)
    engine.close()


def test_ack_promotes_bank_and_reject_discards_without_accepting() -> None:
    first_provider = _FakePageNumberProvider([], preview_labels=[("30", "309")] * 5)
    engine, clock, _camera, _preparer, _store, _visual_ledger = _engine(
        frame_count=12,
        page_number_provider=first_provider,
        opaque_identity_policy=_policy(),
    )
    artifact_id = _artifact_id(_start_and_reach_ready(engine, clock))

    ack_events = engine.delivery_confirmed(artifact_id, "receipt-a")

    assert engine.opaque_identity_ledger is not None
    assert engine.opaque_identity_ledger.pending_artifact_id is None
    assert engine.opaque_identity_ledger.recent_accepted()[0].artifact_id == artifact_id
    assert any(event.event_type is VideoEventType.OPAQUE_IDENTITY_BANK_ACCEPTED for event in ack_events)
    assert engine.delivery_confirmed(artifact_id, "receipt-a") == ()
    engine.close()

    second_provider = _FakePageNumberProvider([], preview_labels=[("30", "309")] * 5)
    engine2, clock2, _camera2, _preparer2, _store2, _visual_ledger2 = _engine(
        frame_count=12,
        page_number_provider=second_provider,
        opaque_identity_policy=_policy(),
    )
    artifact_id2 = _artifact_id(_start_and_reach_ready(engine2, clock2))
    reject_events = engine2.delivery_rejected(artifact_id2, "retry")

    assert engine2.opaque_identity_ledger is not None
    assert engine2.opaque_identity_ledger.pending_artifact_id is None
    assert engine2.opaque_identity_ledger.recent_accepted() == ()
    assert any(event.event_type is VideoEventType.OPAQUE_IDENTITY_BANK_DISCARDED for event in reject_events)
    engine2.close()


def test_cancel_before_ack_discards_pending_opaque_bank() -> None:
    provider = _FakePageNumberProvider([], preview_labels=[("30", "309")] * 5)
    engine, clock, _camera, _preparer, _store, _visual_ledger = _engine(
        frame_count=12,
        page_number_provider=provider,
        opaque_identity_policy=_policy(),
    )
    artifact_id = _artifact_id(_start_and_reach_ready(engine, clock))

    events = engine.cancel()

    assert engine.state is VideoSessionState.IDLE
    assert engine.opaque_identity_ledger is not None
    assert engine.opaque_identity_ledger.pending_artifact_id is None
    assert engine.opaque_identity_ledger.recent_accepted() == ()
    assert any(event.event_type is VideoEventType.OPAQUE_IDENTITY_BANK_DISCARDED for event in events)
    assert engine.delivery_confirmed(artifact_id, "late") == ()
    engine.close()


def test_accepted_older_spread_is_suppressed_before_v2_when_it_reappears() -> None:
    a = ("30", "309")
    b = ("31", "310")
    provider = _FakePageNumberProvider(
        [],
        preview_labels=[a] * 5 + [b] * 5 + [b] * 5 + [a] * 5 + [a],
    )
    engine, clock, _camera, preparer, store, _visual_ledger = _engine(
        frame_count=34,
        page_number_provider=provider,
        opaque_identity_policy=_policy(),
        provider=FakeIdentityProvider(
            artifact_tokens={
                "artifact-v3a-session-job-000001": 0,
                "artifact-v3a-session-job-000002": 1,
            }
        ),
    )

    first_events = _start_and_reach_ready(engine, clock)
    first_id = _artifact_id(first_events)
    engine.delivery_confirmed(first_id, "receipt-a")
    _poll_until(engine, clock, VideoSessionState.SEARCHING)
    second_events = _poll_until(engine, clock, VideoSessionState.READY_FOR_SERVER_PREFLIGHT)
    second_id = _artifact_id(second_events)
    engine.delivery_confirmed(second_id, "receipt-b")
    _poll_until(engine, clock, VideoSessionState.SEARCHING)
    duplicate_events = _poll_until(engine, clock, VideoSessionState.WAITING_FOR_PAGE_CHANGE)

    assert len(preparer.calls) == 2
    assert len(store.commits) == 2
    assert any(event.event_type is VideoEventType.DUPLICATE_SUPPRESSED for event in duplicate_events)
    assert not any(event.event_type is VideoEventType.ARTIFACT_READY for event in duplicate_events)
    assert engine.opaque_identity_ledger is not None
    assert len(engine.opaque_identity_ledger.recent_accepted()) == 2
    engine.close()


def test_m1_different_visual_duplicate_is_conflict_and_not_transferable() -> None:
    a = ("30", "309")
    b = ("31", "310")
    provider = _FakePageNumberProvider([], preview_labels=[a] * 5 + [b] * 5 + [b] * 5)
    visual = _VisualDuplicateIdentityProvider(
        artifact_tokens={
            "artifact-v3a-session-job-000001": 0,
            "artifact-v3a-session-job-000002": 0,
        }
    )
    engine, clock, _camera, preparer, _store, _visual_ledger = _engine(
        frame_count=24,
        page_number_provider=provider,
        opaque_identity_policy=_policy(),
        provider=visual,
    )
    first_id = _artifact_id(_start_and_reach_ready(engine, clock))
    engine.delivery_confirmed(first_id, "receipt-a")
    _poll_until(engine, clock, VideoSessionState.SEARCHING)

    events = _poll_until(engine, clock, VideoSessionState.LOCAL_RETRY)

    assert len(preparer.calls) == 2
    assert any(event.event_type is VideoEventType.PAGE_NUMBER_IDENTITY_CONFLICT for event in events)
    assert not any(event.event_type is VideoEventType.ARTIFACT_READY for event in events)
    assert engine.opaque_identity_ledger is not None
    assert engine.opaque_identity_ledger.pending_artifact_id is None
    engine.close()


def test_missing_observations_timeout_unknown_without_v2_or_pending_bank() -> None:
    provider = _FakePageNumberProvider([], preview_labels=[None] * 20)
    engine, clock, _camera, preparer, store, _visual_ledger = _engine(
        frame_count=24,
        page_number_provider=provider,
        opaque_identity_policy=_policy(max_collection_ms=500),
    )
    engine.start()

    events = _poll_until(engine, clock, VideoSessionState.LOCAL_RETRY)

    assert len(preparer.calls) == 0
    assert len(store.commits) == 0
    assert any(
        event.event_type is VideoEventType.OPAQUE_IDENTITY_DECIDED
        and dict(event.details)["decision"] == "unknown"
        and dict(event.details)["timed_out"] is True
        for event in events
    )
    assert engine.diagnostics.opaque_identity_missing_observations > 0
    engine.close()


class _HardRejectEighthFrameAnalyzer:
    def __init__(self, delegate) -> None:
        self.delegate = delegate

    def analyze(self, frame):
        observation = self.delegate.analyze(frame)
        if frame.frame_id == FrameId("f-8"):
            return replace(
                observation,
                candidate=replace(
                    observation.candidate,
                    retry_reasons=(ReadinessReason.CONTENT_OCCLUDED,),
                ),
            )
        return observation


def test_four_of_five_identity_observations_then_hard_reject_emits_terminal_summary() -> None:
    provider = _FakePageNumberProvider([], preview_labels=[("314", "315")] * 4)
    engine, clock, _camera, preparer, store, _visual_ledger = _engine(
        frame_count=8,
        page_number_provider=provider,
        opaque_identity_policy=_policy(),
    )
    engine.analyzer = _HardRejectEighthFrameAnalyzer(engine.analyzer)
    events = list(engine.start())

    for _ in range(8):
        events.extend(engine.poll())
        clock.advance(0.1)

    aborted = [
        event
        for event in events
        if event.event_type is VideoEventType.OPAQUE_IDENTITY_ABORTED
    ]
    assert len(aborted) == 1
    assert dict(aborted[0].details)["terminal_reason"] == "content_occluded"
    assert dict(aborted[0].details)["valid_observations"] == 4
    assert dict(aborted[0].details)["query_sample_count"] == 5
    assert provider.preview_calls == 4
    assert preparer.calls == []
    assert store.commits == []
    engine.close()


def test_one_of_five_identity_observations_then_eof_emits_abort_before_source_exhausted() -> None:
    provider = _FakePageNumberProvider([], preview_labels=[("318", "12")] * 1)
    engine, clock, _camera, preparer, store, _visual_ledger = _engine(
        frame_count=4,
        page_number_provider=provider,
        opaque_identity_policy=_policy(),
    )
    events = list(engine.start())

    for _ in range(5):
        events.extend(engine.poll())
        clock.advance(0.1)

    event_types = [event.event_type for event in events]
    aborted_index = event_types.index(VideoEventType.OPAQUE_IDENTITY_ABORTED)
    exhausted_index = event_types.index(VideoEventType.SOURCE_EXHAUSTED)
    details = dict(events[aborted_index].details)
    assert aborted_index < exhausted_index
    assert details["terminal_reason"] == "source_exhausted"
    assert details["valid_observations"] == 1
    assert details["query_sample_count"] == 5
    assert provider.preview_calls == 1
    assert preparer.calls == []
    assert store.commits == []
    engine.close()
