from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.config import CandidatePolicy, IdentityPolicy, PageChangePolicy
from book_scanner.video.engine import SampledFrameEngine as ProductionSampledFrameEngine
from book_scanner.video.events import VideoEventType
from book_scanner.video.identity import InMemoryPageIdentityLedger
from book_scanner.video.page_change import HysteresisPageChangeGate
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import (
    FrameId,
    PreparationDecision,
    PreparationState,
    ReadinessReason,
    VideoSessionState,
)

from .fakes import (
    FakeArtifactStore,
    FakeCameraSource,
    FakeIdentityProvider,
    FakeSpreadPreparer,
    ManualClock,
    make_prepared,
)
from .test_candidate import spread_frame


def SampledFrameEngine(*args, **kwargs):
    """Give legacy engine tests deterministic V3-A boundaries."""

    identity_policy = IdentityPolicy()
    kwargs.setdefault("identity_provider", FakeIdentityProvider())
    kwargs.setdefault("identity_ledger", InMemoryPageIdentityLedger(identity_policy))
    kwargs.setdefault(
        "page_change_gate",
        HysteresisPageChangeGate(identity_policy, PageChangePolicy()),
    )
    return ProductionSampledFrameEngine(*args, **kwargs)


def _frames(count: int) -> list[FrameSample[np.ndarray]]:
    return [FrameSample(FrameId(f"f-{index}"), index * 0.5, spread_frame()) for index in range(1, count + 1)]


def _policy(**overrides: object) -> CandidatePolicy:
    values = {
        "sample_interval_ms": 100,
        "stable_sample_count": 3,
        "sample_window_size": 3,
        "local_retry_cooldown_ms": 100,
    }
    values.update(overrides)
    return CandidatePolicy(**values)


def _ready(frame: FrameSample[np.ndarray], spread_id, job_id, session_id) -> PreparationDecision:
    prepared = make_prepared(
        frame.frame_id.value,
        artifact_name=f"artifact-{job_id.value}",
        spread=spread_id.value,
        job=job_id.value,
        session=session_id,
    )
    return PreparationDecision(
        PreparationState.PREPARED,
        "fake-processor-v1",
        job_id=job_id,
        source_frame_id=frame.frame_id,
        spread_id=spread_id,
        prepared=prepared,
    )


def _poll_until(engine: SampledFrameEngine, state: VideoSessionState, limit: int = 100):
    events = []
    for _ in range(limit):
        events.extend(engine.poll())
        if engine.state is state:
            return events
        time.sleep(0.002)
    raise AssertionError(f"engine did not reach {state.value}; current={engine.state.value}")


def test_start_stable_select_process_and_release_camera() -> None:
    clock = ManualClock()
    camera = FakeCameraSource(_frames(3))
    preparer = FakeSpreadPreparer(_ready)
    store = FakeArtifactStore()
    engine = SampledFrameEngine(
        camera,
        OpenCVCandidateAnalyzer(),
        preparer,
        store,
        session_id="test-session",
        clock=clock,
        policy=_policy(),
    )

    start_events = engine.start()
    assert engine.state is VideoSessionState.SEARCHING
    assert [event.event_type for event in start_events].count(VideoEventType.STATE_CHANGED) == 2
    for _ in range(3):
        engine.poll()
        clock.advance(0.1)
    events = _poll_until(engine, VideoSessionState.READY_FOR_SERVER_PREFLIGHT)

    assert camera.started and not camera.stopped
    assert preparer.calls[0][0].frame_id == FrameId("f-3")
    ready_event = next(event for event in events if event.event_type is VideoEventType.ARTIFACT_READY)
    assert ready_event.source_frame_id == preparer.calls[0][0].frame_id
    assert ready_event.spread_id == preparer.calls[0][1]
    assert len(store.commits) == 1
    assert engine.diagnostics.frames_received == 3
    assert engine.diagnostics.frames_selected == 1
    assert not engine.diagnostics.camera_resource_released
    engine.close()


def test_polling_faster_than_cadence_does_not_evaluate_every_poll() -> None:
    clock = ManualClock()
    engine = SampledFrameEngine(
        FakeCameraSource(_frames(4)),
        OpenCVCandidateAnalyzer(),
        FakeSpreadPreparer(_ready),
        FakeArtifactStore(),
        session_id="test-session",
        clock=clock,
        policy=_policy(),
    )
    engine.start()

    for _ in range(10):
        engine.poll()

    assert engine.diagnostics.frames_received == 1
    assert engine.diagnostics.frames_evaluated == 1
    engine.cancel()
    engine.close()


def test_empty_source_reaches_idle_and_releases_resource() -> None:
    camera = FakeCameraSource([])
    engine = SampledFrameEngine(
        camera,
        OpenCVCandidateAnalyzer(),
        FakeSpreadPreparer(_ready),
        FakeArtifactStore(),
        session_id="test-session",
        clock=ManualClock(),
        policy=_policy(),
    )
    engine.start()

    events = engine.poll()

    assert engine.state is VideoSessionState.IDLE
    assert camera.stopped
    assert any(event.event_type is VideoEventType.SOURCE_EXHAUSTED for event in events)
    engine.close()


def test_local_retry_clears_window_then_next_same_frame_pair_succeeds() -> None:
    clock = ManualClock()
    calls = 0

    def result(frame, spread_id, job_id, session_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            return PreparationDecision(
                PreparationState.RETRY_LOCAL,
                "fake-processor-v1",
                job_id=job_id,
                reasons=(ReadinessReason.SEAM_FAILED,),
                source_frame_id=frame.frame_id,
                spread_id=spread_id,
            )
        return _ready(frame, spread_id, job_id, session_id)

    preparer = FakeSpreadPreparer(result)
    store = FakeArtifactStore()
    engine = SampledFrameEngine(
        FakeCameraSource(_frames(6)),
        OpenCVCandidateAnalyzer(),
        preparer,
        store,
        session_id="test-session",
        clock=clock,
        policy=_policy(),
    )
    engine.start()
    for _ in range(3):
        engine.poll(); clock.advance(0.1)
    _poll_until(engine, VideoSessionState.LOCAL_RETRY)
    clock.advance(0.1)
    for _ in range(3):
        engine.poll(); clock.advance(0.1)
    _poll_until(engine, VideoSessionState.READY_FOR_SERVER_PREFLIGHT)

    assert len(preparer.calls) == 2
    assert preparer.calls[0][0].frame_id == FrameId("f-3")
    assert preparer.calls[1][0].frame_id == FrameId("f-6")
    assert engine.diagnostics.frames_processed == 2
    assert len(store.discarded_jobs) == 1
    engine.close()


def test_cancel_during_processing_releases_camera_and_discards_result() -> None:
    clock = ManualClock()
    entered = threading.Event()
    release = threading.Event()

    def blocking(frame, spread_id, job_id, session_id):
        entered.set()
        release.wait(2)
        return _ready(frame, spread_id, job_id, session_id)

    camera = FakeCameraSource(_frames(3))
    store = FakeArtifactStore()
    engine = SampledFrameEngine(
        camera,
        OpenCVCandidateAnalyzer(),
        FakeSpreadPreparer(blocking),
        store,
        session_id="test-session",
        clock=clock,
        policy=_policy(),
    )
    engine.start()
    for _ in range(3):
        engine.poll(); clock.advance(0.1)
    assert entered.wait(1)

    cancel_events = list(engine.cancel())
    assert camera.stopped
    assert engine.state is VideoSessionState.CANCELLING
    release.set()
    cancel_events.extend(_poll_until(engine, VideoSessionState.IDLE))

    assert not any(event.event_type is VideoEventType.ARTIFACT_READY for event in cancel_events)
    assert store.commits == []
    assert len(store.discards) == 1
    assert engine.diagnostics.camera_resource_released
    engine.close()


def test_processor_cannot_return_another_source_frame() -> None:
    clock = ManualClock()

    def wrong_frame(_frame, spread_id, job_id, session_id):
        prepared = make_prepared(
            "other-frame", spread=spread_id.value, job=job_id.value, session=session_id
        )
        return PreparationDecision(
            PreparationState.PREPARED,
            "fake-processor-v1",
            job_id=job_id,
            source_frame_id=prepared.source_frame_id,
            spread_id=spread_id,
            prepared=prepared,
        )

    engine = SampledFrameEngine(
        FakeCameraSource(_frames(3)),
        OpenCVCandidateAnalyzer(),
        FakeSpreadPreparer(wrong_frame),
        FakeArtifactStore(),
        session_id="test-session",
        clock=clock,
        policy=_policy(),
    )
    engine.start()
    for _ in range(3):
        engine.poll(); clock.advance(0.1)
    events = _poll_until(engine, VideoSessionState.ERROR)

    assert any(event.event_type is VideoEventType.SESSION_ERROR for event in events)
    assert engine.diagnostics.camera_resource_released
    engine.close()


def test_source_read_exception_enters_error_and_releases_camera() -> None:
    class BrokenCamera(FakeCameraSource[np.ndarray]):
        def read(self):
            raise RuntimeError("camera disconnected")

    camera = BrokenCamera(_frames(1))
    engine = SampledFrameEngine(
        camera,
        OpenCVCandidateAnalyzer(),
        FakeSpreadPreparer(_ready),
        FakeArtifactStore(),
        session_id="test-session",
        clock=ManualClock(),
        policy=_policy(),
    )
    engine.start()

    events = engine.poll()

    assert engine.state is VideoSessionState.ERROR
    assert camera.stopped
    error = next(event for event in events if event.event_type is VideoEventType.SESSION_ERROR)
    assert error.reason is ReadinessReason.FRAME_DECODE_FAILED
    engine.close()


def test_production_engine_requires_explicit_session_id() -> None:
    with pytest.raises(TypeError, match="session_id"):
        SampledFrameEngine(  # type: ignore[call-arg]
            FakeCameraSource(_frames(1)),
            OpenCVCandidateAnalyzer(),
            FakeSpreadPreparer(_ready),
            FakeArtifactStore(),
        )


def test_cancel_after_prepare_before_poll_discards_without_commit() -> None:
    clock = ManualClock()
    prepared_done = threading.Event()

    def immediate(frame, spread_id, job_id, session_id):
        decision = _ready(frame, spread_id, job_id, session_id)
        prepared_done.set()
        return decision

    store = FakeArtifactStore()
    engine = SampledFrameEngine(
        FakeCameraSource(_frames(3)),
        OpenCVCandidateAnalyzer(),
        FakeSpreadPreparer(immediate),
        store,
        session_id="cancel-before-commit",
        clock=clock,
        policy=_policy(),
    )
    engine.start()
    for _ in range(3):
        engine.poll(); clock.advance(0.1)
    assert prepared_done.wait(1)
    for _ in range(100):
        if engine._future is not None and engine._future.done():  # noqa: SLF001
            break
        time.sleep(0.001)

    events = engine.cancel()

    assert engine.state is VideoSessionState.IDLE
    assert store.commits == []
    assert len(store.discards) == 1
    assert not any(event.event_type is VideoEventType.ARTIFACT_READY for event in events)
    engine.close()


def test_commit_then_cancel_preserves_committed_artifact() -> None:
    clock = ManualClock()
    store = FakeArtifactStore()
    engine = SampledFrameEngine(
        FakeCameraSource(_frames(3)),
        OpenCVCandidateAnalyzer(),
        FakeSpreadPreparer(_ready),
        store,
        session_id="commit-before-cancel",
        clock=clock,
        policy=_policy(),
    )
    engine.start()
    for _ in range(3):
        engine.poll(); clock.advance(0.1)
    _poll_until(engine, VideoSessionState.READY_FOR_SERVER_PREFLIGHT)

    engine.cancel()

    assert engine.state is VideoSessionState.IDLE
    assert len(store.commits) == 1
    assert store.discards == []
    engine.close()


def test_job_and_spread_ids_are_namespaced_by_explicit_session() -> None:
    calls = []
    engines = []
    for session_id in ("session-alpha", "session-beta"):
        clock = ManualClock()
        preparer = FakeSpreadPreparer(_ready)
        engine = SampledFrameEngine(
            FakeCameraSource(_frames(3)),
            OpenCVCandidateAnalyzer(),
            preparer,
            FakeArtifactStore(),
            session_id=session_id,
            clock=clock,
            policy=_policy(),
        )
        engines.append(engine)
        engine.start()
        for _ in range(3):
            engine.poll(); clock.advance(0.1)
        calls.append(preparer.calls[0])

    assert calls[0][1] != calls[1][1]
    assert calls[0][2] != calls[1][2]
    assert calls[0][1].value.startswith("session-alpha-")
    assert calls[1][2].value.startswith("session-beta-")
    for engine in engines:
        engine.cancel()
        engine.close()


def test_prepare_exception_discards_job_staging_before_local_retry() -> None:
    clock = ManualClock()

    def broken(_frame, _spread_id, _job_id, _session_id):
        raise RuntimeError("prepare failed after partial staging")

    store = FakeArtifactStore()
    engine = SampledFrameEngine(
        FakeCameraSource(_frames(3)),
        OpenCVCandidateAnalyzer(),
        FakeSpreadPreparer(broken),
        store,
        session_id="failed-prepare",
        clock=clock,
        policy=_policy(),
    )
    engine.start()
    for _ in range(3):
        engine.poll(); clock.advance(0.1)

    _poll_until(engine, VideoSessionState.LOCAL_RETRY)

    assert len(store.discarded_jobs) == 1
    assert store.discarded_jobs[0].value.startswith("failed-prepare-job-")
    assert store.commits == []
    engine.cancel()
    engine.close()
