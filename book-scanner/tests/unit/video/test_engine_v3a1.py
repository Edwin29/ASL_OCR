from __future__ import annotations

import time

from book_scanner.video.config import (
    PageNumberPolicy,
    PageNumberSchedulerMode,
    PageNumberSchedulerPolicy,
)
from book_scanner.video.events import VideoEventType
from book_scanner.video.page_number import (
    PageNumberObservation,
    PageNumberSource,
    PageNumberStatus,
    SpreadPageKey,
    SpreadPageNumberObservation,
    SpreadPageNumberStatus,
)
from book_scanner.video.types import FrameId, PageSide, VideoSessionState

from .fakes import FakeIdentityProvider
from .test_engine_v3a import _artifact_id, _engine, _reach_ready


class _FakePageNumberProvider:
    def __init__(self, artifact_labels, preview_labels=()) -> None:
        self.artifact_labels = list(artifact_labels)
        self.preview_labels = list(preview_labels)
        self.preview_calls = 0

    def observe_artifact(self, artifact, data_pack_id):
        labels = self.artifact_labels.pop(0)
        return _observation(artifact.source_frame_id, data_pack_id, labels, artifact.artifact_id)

    def observe_preview(self, _gray, _mask, _seam, source_frame_id, data_pack_id):
        self.preview_calls += 1
        labels = self.preview_labels.pop(0)
        return _observation(source_frame_id, data_pack_id, labels, None, PageNumberSource.PREVIEW)


def _visual_triggered_policy() -> PageNumberSchedulerPolicy:
    return PageNumberSchedulerPolicy(mode=PageNumberSchedulerMode.VISUAL_TRIGGERED)


def _observation(
    frame_id: FrameId,
    data_pack_id: str,
    labels: tuple[str, str] | None,
    artifact_id,
    source: PageNumberSource = PageNumberSource.CORRECTED,
) -> SpreadPageNumberObservation:
    def side_observation(side: PageSide, label: str | None) -> PageNumberObservation:
        return PageNumberObservation(
            side,
            label,
            label,
            0.99 if label else None,
            (1, 2, 3, 4) if label else None,
            ("a" if side is PageSide.LEFT else "b") * 64,
            source,
            frame_id,
            artifact_id,
            "fake-page-number",
            "1",
            "fake-preprocess-v1",
            2 if label else 0,
            PageNumberStatus.OBSERVED if label else PageNumberStatus.NOT_OBSERVED,
        )

    left_label, right_label = labels if labels is not None else (None, None)
    left = side_observation(PageSide.LEFT, left_label)
    right = side_observation(PageSide.RIGHT, right_label)
    key = (
        SpreadPageKey(data_pack_id, left_label, right_label, "fake-page-number:1")
        if left_label and right_label
        else None
    )
    return SpreadPageNumberObservation(
        left,
        right,
        key,
        SpreadPageNumberStatus.COMPLETE if key else SpreadPageNumberStatus.MISSING,
        1.0,
    )


def test_confirmed_complete_page_key_enters_datapack_ledger() -> None:
    page_provider = _FakePageNumberProvider([("30", "309")])
    engine, clock, _camera, _preparer, _store, _identity_ledger = _engine(
        page_number_provider=page_provider
    )
    ready_events = _reach_ready(engine, clock)
    artifact_id = _artifact_id(ready_events)

    engine.delivery_confirmed(artifact_id, "receipt-page-key")

    entries = engine.page_key_ledger.recent_accepted()
    assert len(entries) == 1
    assert entries[0].key.left_page_label == "30"
    assert entries[0].key.right_page_label == "309"
    assert entries[0].receipt_id == "receipt-page-key"
    assert sum(event.event_type is VideoEventType.PAGE_NUMBER_OBSERVED for event in ready_events) == 2
    assert sum(event.event_type is VideoEventType.SPREAD_PAGE_KEY_CREATED for event in ready_events) == 1
    engine.close()


def test_same_page_number_resets_visual_page_change_false_positive() -> None:
    page_provider = _FakePageNumberProvider(
        [("30", "309")],
        preview_labels=[("30", "309")] * 4,
    )
    identity_provider = FakeIdentityProvider(preview_tokens=[0, 1, 1, 1, 1])
    engine, clock, _camera, _preparer, _store, _identity_ledger = _engine(
        frame_count=10,
        provider=identity_provider,
        page_number_provider=page_provider,
    )
    artifact_id = _artifact_id(_reach_ready(engine, clock))
    engine.delivery_confirmed(artifact_id, "receipt-page-key")
    events = []

    for _ in range(4):
        events.extend(engine.poll())
        clock.advance(0.75)

    assert engine.state is VideoSessionState.WAITING_FOR_PAGE_CHANGE
    assert not any(event.event_type is VideoEventType.PAGE_CHANGED for event in events)
    number_events = [event for event in events if event.event_type is VideoEventType.PAGE_CHANGE_NUMBER_EVIDENCE]
    assert number_events
    assert all(dict(event.details).get("relation") == "same" for event in number_events)
    engine.close()


def test_different_page_number_requires_stable_k_before_releasing_search() -> None:
    page_provider = _FakePageNumberProvider(
        [("30", "309")],
        preview_labels=[("31", "310")] * 3,
    )
    identity_provider = FakeIdentityProvider(preview_tokens=[0, 1, 1, 1])
    engine, clock, _camera, _preparer, _store, _identity_ledger = _engine(
        frame_count=10,
        provider=identity_provider,
        page_number_provider=page_provider,
        page_number_policy=PageNumberPolicy(stable_sample_count=3),
    )
    artifact_id = _artifact_id(_reach_ready(engine, clock))
    engine.delivery_confirmed(artifact_id, "receipt-page-key")

    first = engine.poll()
    clock.advance(0.75)
    second = engine.poll()
    clock.advance(0.75)
    third = engine.poll()

    assert engine.state is VideoSessionState.SEARCHING
    assert not any(event.event_type is VideoEventType.PAGE_CHANGED for event in (*first, *second))
    assert sum(event.event_type is VideoEventType.PAGE_CHANGED for event in third) == 1
    engine.close()


def test_visual_triggered_scheduler_skips_provider_on_visual_same() -> None:
    page_provider = _FakePageNumberProvider([("30", "309")])
    identity_provider = FakeIdentityProvider(preview_tokens=[0, 0, 0, 0])
    engine, clock, _camera, _preparer, _store, _identity_ledger = _engine(
        frame_count=10,
        provider=identity_provider,
        page_number_provider=page_provider,
        page_number_scheduler_policy=_visual_triggered_policy(),
    )
    artifact_id = _artifact_id(_reach_ready(engine, clock))
    engine.delivery_confirmed(artifact_id, "receipt-visual-same")

    for _ in range(3):
        engine.poll()
        clock.advance(0.75)

    assert page_provider.preview_calls == 0
    assert engine.diagnostics.page_number_eligible_spreads == 3
    assert engine.diagnostics.page_number_requested_spreads == 0
    assert engine.diagnostics.page_number_skipped_spreads == 3
    engine.close()


def test_visual_triggered_scheduler_requests_stable_changed_burst() -> None:
    page_provider = _FakePageNumberProvider(
        [("30", "309")],
        preview_labels=[("31", "310")] * 3,
    )
    identity_provider = FakeIdentityProvider(preview_tokens=[0, 1, 1, 1])
    engine, clock, _camera, _preparer, _store, _identity_ledger = _engine(
        frame_count=10,
        provider=identity_provider,
        page_number_provider=page_provider,
        page_number_scheduler_policy=_visual_triggered_policy(),
    )
    artifact_id = _artifact_id(_reach_ready(engine, clock))
    engine.delivery_confirmed(artifact_id, "receipt-visual-change")
    events = []

    for _ in range(3):
        events.extend(engine.poll())
        clock.advance(0.75)

    assert page_provider.preview_calls == 3
    assert engine.diagnostics.page_number_requested_spreads == 3
    assert engine.diagnostics.page_number_verification_bursts == 1
    assert sum(event.event_type is VideoEventType.PAGE_CHANGED for event in events) == 1
    engine.close()


def test_same_complete_key_plus_visual_new_is_conflict_not_duplicate_or_transfer() -> None:
    page_provider = _FakePageNumberProvider(
        [("30", "309"), ("30", "309")],
        preview_labels=[("31", "310")] * 3,
    )
    identity_provider = FakeIdentityProvider(
        artifact_tokens={
            "artifact-v3a-session-job-000001": 0,
            "artifact-v3a-session-job-000002": 1,
        },
        preview_tokens=[0, 1, 1, 1, 1],
    )
    engine, clock, _camera, _preparer, _store, _identity_ledger = _engine(
        frame_count=14,
        provider=identity_provider,
        page_number_provider=page_provider,
    )
    first_artifact = _artifact_id(_reach_ready(engine, clock))
    engine.delivery_confirmed(first_artifact, "receipt-first")
    for _ in range(3):
        engine.poll()
        clock.advance(0.75)
    assert engine.state is VideoSessionState.SEARCHING

    for _ in range(3):
        engine.poll()
        clock.advance(0.1)
    events = []
    for _ in range(100):
        events.extend(engine.poll())
        if engine.state is VideoSessionState.LOCAL_RETRY:
            break
        time.sleep(0.001)

    assert engine.state is VideoSessionState.LOCAL_RETRY
    assert sum(event.event_type is VideoEventType.PAGE_NUMBER_IDENTITY_CONFLICT for event in events) == 1
    assert not any(event.event_type is VideoEventType.ARTIFACT_READY for event in events)
    assert not any(event.event_type is VideoEventType.DUPLICATE_SUPPRESSED for event in events)
    assert engine.diagnostics.page_number_conflicts == 1
    engine.close()
