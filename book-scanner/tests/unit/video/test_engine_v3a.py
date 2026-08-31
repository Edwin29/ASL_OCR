from __future__ import annotations

import time

import numpy as np

from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.config import (
    CandidatePolicy,
    IdentityPolicy,
    OpaqueFooterIdentityPolicy,
    PageChangePolicy,
    PageNumberPolicy,
    PageNumberSchedulerPolicy,
)
from book_scanner.video.engine import SampledFrameEngine
from book_scanner.video.events import VideoEventType
from book_scanner.video.identity import InMemoryPageIdentityLedger
from book_scanner.video.page_change import HysteresisPageChangeGate
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import ArtifactId, FrameId, VideoSessionState

from .fakes import FakeArtifactStore, FakeCameraSource, FakeIdentityProvider, FakeSpreadPreparer, ManualClock, make_prepared
from .test_candidate import spread_frame


def _frames(count: int) -> list[FrameSample[np.ndarray]]:
    return [FrameSample(FrameId(f"f-{index}"), index * 0.1, spread_frame()) for index in range(1, count + 1)]


def _ready(frame, spread_id, job_id, session_id):
    from book_scanner.video.types import PreparationDecision, PreparationState

    prepared = make_prepared(
        frame.frame_id.value,
        artifact_name=f"artifact-{job_id.value}",
        spread=spread_id.value,
        job=job_id.value,
        session=session_id,
    )
    return PreparationDecision(
        PreparationState.PREPARED,
        "fake-v3a-preparer",
        job_id,
        frame.frame_id,
        spread_id,
        prepared=prepared,
    )


def _engine(
    frame_count: int = 12,
    provider: FakeIdentityProvider | None = None,
    page_number_provider=None,
    page_number_policy: PageNumberPolicy = PageNumberPolicy(),
    page_number_scheduler_policy: PageNumberSchedulerPolicy = PageNumberSchedulerPolicy(),
    opaque_identity_policy: OpaqueFooterIdentityPolicy | None = None,
    opaque_identity_ledger=None,
):
    clock = ManualClock()
    identity_policy = IdentityPolicy()
    camera = FakeCameraSource(_frames(frame_count))
    preparer = FakeSpreadPreparer(_ready)
    store = FakeArtifactStore()
    ledger = InMemoryPageIdentityLedger(identity_policy)
    engine = SampledFrameEngine(
        camera,
        OpenCVCandidateAnalyzer(),
        preparer,
        store,
        session_id="v3a-session",
        clock=clock,
        policy=CandidatePolicy(
            sample_interval_ms=100,
            stable_sample_count=3,
            sample_window_size=3,
            local_retry_cooldown_ms=0,
        ),
        identity_policy=identity_policy,
        page_change_policy=PageChangePolicy(sample_interval_ms=750, stable_sample_count=3),
        identity_provider=provider or FakeIdentityProvider(),
        identity_ledger=ledger,
        page_change_gate=HysteresisPageChangeGate(
            identity_policy,
            PageChangePolicy(sample_interval_ms=750, stable_sample_count=3),
        ),
        page_number_provider=page_number_provider,
        page_number_policy=page_number_policy,
        page_number_scheduler_policy=page_number_scheduler_policy,
        opaque_identity_policy=opaque_identity_policy,
        opaque_identity_ledger=opaque_identity_ledger,
        data_pack_id="test-pack",
    )
    return engine, clock, camera, preparer, store, ledger


def _reach_ready(engine: SampledFrameEngine, clock: ManualClock):
    engine.start()
    for _ in range(3):
        engine.poll()
        clock.advance(0.1)
    events = []
    for _ in range(100):
        events.extend(engine.poll())
        if engine.state is VideoSessionState.READY_FOR_SERVER_PREFLIGHT:
            return events
        time.sleep(0.001)
    raise AssertionError(f"engine did not become ready: {engine.state}")


def _artifact_id(events) -> ArtifactId:
    return next(event.artifact_id for event in events if event.event_type is VideoEventType.ARTIFACT_READY)


def test_pending_spread_blocks_new_frame_evaluation_and_retry_keeps_same_artifact() -> None:
    engine, clock, _camera, preparer, _store, ledger = _engine()
    artifact_id = _artifact_id(_reach_ready(engine, clock))
    before = engine.diagnostics.frames_received

    engine.delivery_queued(artifact_id)
    engine.delivery_retrying(artifact_id)
    clock.advance(10)
    for _ in range(5):
        engine.poll()

    assert engine.state is VideoSessionState.REMOTE_RETRY
    assert engine.diagnostics.frames_received == before
    assert len(preparer.calls) == 1
    assert ledger.pending is not None and ledger.pending.artifact_id == artifact_id
    engine.close()


def test_stale_and_repeated_confirm_cannot_complete_current_artifact_twice() -> None:
    engine, clock, _camera, _preparer, _store, ledger = _engine()
    artifact_id = _artifact_id(_reach_ready(engine, clock))

    assert engine.delivery_confirmed(ArtifactId("stale"), "stale-receipt") == ()
    events = engine.delivery_confirmed(artifact_id, "receipt-1")
    repeated = engine.delivery_confirmed(artifact_id, "receipt-1")

    assert engine.state is VideoSessionState.WAITING_FOR_PAGE_CHANGE
    assert sum(event.event_type is VideoEventType.DELIVERY_CONFIRMED for event in events) == 1
    assert repeated == ()
    assert ledger.pending is None
    assert ledger.recent_accepted()[0].artifact_id == artifact_id
    engine.close()


def test_ack_waits_on_same_page_then_emits_one_page_changed_after_three_stable_changes() -> None:
    provider = FakeIdentityProvider(preview_tokens=[0, 0, 1, 1, 1])
    engine, clock, _camera, preparer, _store, _ledger = _engine(provider=provider)
    artifact_id = _artifact_id(_reach_ready(engine, clock))
    engine.delivery_confirmed(artifact_id, "receipt-1")
    all_events = []

    for _ in range(4):
        all_events.extend(engine.poll())
        clock.advance(0.75)

    assert engine.state is VideoSessionState.SEARCHING
    assert sum(event.event_type is VideoEventType.PAGE_CHANGED for event in all_events) == 1
    assert len(preparer.calls) == 1
    assert engine.diagnostics.waiting_preview_frames == 4
    assert engine.diagnostics.page_changes == 1
    engine.close()


def test_parser_reject_releases_pending_without_polluting_accepted_ledger() -> None:
    engine, clock, _camera, _preparer, _store, ledger = _engine()
    artifact_id = _artifact_id(_reach_ready(engine, clock))

    events = engine.delivery_rejected(artifact_id, "parser quality gate")

    assert engine.state is VideoSessionState.LOCAL_RETRY
    assert ledger.pending is None
    assert ledger.recent_accepted() == ()
    assert any(event.event_type is VideoEventType.PARSER_REJECTED for event in events)
    engine.close()


def test_cancel_before_ack_releases_pending_but_confirm_before_cancel_stays_accepted() -> None:
    engine, clock, _camera, _preparer, _store, ledger = _engine()
    artifact_id = _artifact_id(_reach_ready(engine, clock))
    engine.cancel()
    assert ledger.pending is None
    assert engine.delivery_confirmed(artifact_id, "late") == ()

    engine2, clock2, _camera2, _preparer2, _store2, ledger2 = _engine()
    artifact_id2 = _artifact_id(_reach_ready(engine2, clock2))
    engine2.delivery_confirmed(artifact_id2, "winner")
    engine2.cancel()
    assert ledger2.recent_accepted()[0].receipt_id == "winner"
    engine.close()
    engine2.close()


def test_accepted_duplicate_commits_identity_evidence_but_emits_no_new_transfer_request() -> None:
    provider = FakeIdentityProvider(
        artifact_tokens={
            "artifact-v3a-session-job-000001": 0,
            "artifact-v3a-session-job-000002": 0,
        },
        preview_tokens=[0, 1, 1, 1, 0],
    )
    engine, clock, _camera, preparer, store, ledger = _engine(frame_count=12, provider=provider)
    first_id = _artifact_id(_reach_ready(engine, clock))
    engine.delivery_confirmed(first_id, "receipt-first")
    for _ in range(3):
        engine.poll()
        clock.advance(0.75)
    assert engine.state is VideoSessionState.SEARCHING

    clock.advance(0.1)
    for _ in range(3):
        engine.poll()
        clock.advance(0.1)
    events = []
    for _ in range(100):
        events.extend(engine.poll())
        if engine.state is VideoSessionState.WAITING_FOR_PAGE_CHANGE:
            break
        time.sleep(0.001)

    assert engine.state is VideoSessionState.WAITING_FOR_PAGE_CHANGE
    assert sum(event.event_type is VideoEventType.DUPLICATE_SUPPRESSED for event in events) == 1
    assert not any(event.event_type is VideoEventType.ARTIFACT_READY for event in events)
    assert len(preparer.calls) == 2
    assert len(store.commits) == 2
    assert len(ledger.recent_accepted()) == 1
    assert engine.diagnostics.duplicates_suppressed == 1
    engine.close()
