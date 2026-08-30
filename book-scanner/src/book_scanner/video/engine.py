"""Sampled-frame state engine for the PC scanner prototype."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np

from .artifacts import ArtifactCollisionError
from .candidate import CandidateAnalyzer, CandidateObservation, CandidateWindow, StableWindowAssessor
from .config import CandidatePolicy
from .events import VideoEvent, VideoEventType
from .protocols import ArtifactStore, CameraSource, Clock, SpreadPreparer
from .sources import CameraUnavailableError, FrameDecodeError, SystemClock
from .types import (
    PreparationDecision,
    PreparationState,
    ProcessingJobId,
    ReadinessReason,
    SpreadId,
    VideoSessionState,
)


@dataclass(frozen=True, slots=True)
class FrameEngineDiagnostics:
    frames_received: int
    frames_evaluated: int
    frames_dropped: int
    frames_selected: int
    frames_processed: int
    peak_window_depth: int
    processing_latency_ms: float | None
    cancel_latency_ms: float | None
    camera_resource_released: bool


class SampledFrameEngine:
    """Drive a sampled capture session without coupling it to delivery.

    ``poll`` never waits for the processor.  This keeps start/cancel responsive
    even when the V2 seam/UVDoc implementation is later plugged in.
    """

    producer_version = "sampled-frame-engine-v1"

    def __init__(
        self,
        camera: CameraSource[np.ndarray],
        analyzer: CandidateAnalyzer,
        preparer: SpreadPreparer[np.ndarray],
        artifact_store: ArtifactStore,
        *,
        session_id: str,
        clock: Clock | None = None,
        policy: CandidatePolicy = CandidatePolicy(),
        assessor: StableWindowAssessor | None = None,
    ):
        if not session_id.strip():
            raise ValueError("session_id must be non-empty")
        self.camera = camera
        self.analyzer = analyzer
        self.preparer = preparer
        self.artifact_store = artifact_store
        self.clock = clock or SystemClock()
        self.policy = policy
        self.assessor = assessor or StableWindowAssessor(policy)
        self.session_id = session_id

        self.state = VideoSessionState.IDLE
        self._window = CandidateWindow(policy.sample_window_size)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scanner-frame")
        self._future: Future[PreparationDecision] | None = None
        self._selected: CandidateObservation | None = None
        self._selected_spread: SpreadId | None = None
        self._active_job_id: ProcessingJobId | None = None
        self._processing_job_id: ProcessingJobId | None = None
        self._processing_started_at: float | None = None
        self._next_sample_at = 0.0
        self._retry_until = 0.0
        self._cancel_started_at: float | None = None
        self._camera_started = False
        self._closed = False
        self._event_counter = 0
        self._spread_counter = 0
        self._job_counter = 0
        self._frames_received = 0
        self._frames_evaluated = 0
        self._frames_dropped = 0
        self._frames_selected = 0
        self._frames_processed = 0
        self._peak_window_depth = 0
        self._processing_latency_ms: float | None = None
        self._cancel_latency_ms: float | None = None
        self._camera_resource_released = True
        self._lock = threading.RLock()

    @property
    def diagnostics(self) -> FrameEngineDiagnostics:
        with self._lock:
            return FrameEngineDiagnostics(
                frames_received=self._frames_received,
                frames_evaluated=self._frames_evaluated,
                frames_dropped=self._frames_dropped,
                frames_selected=self._frames_selected,
                frames_processed=self._frames_processed,
                peak_window_depth=self._peak_window_depth,
                processing_latency_ms=self._processing_latency_ms,
                cancel_latency_ms=self._cancel_latency_ms,
                camera_resource_released=self._camera_resource_released,
            )

    def start(self) -> tuple[VideoEvent, ...]:
        with self._lock:
            if self._closed:
                raise RuntimeError("engine is closed")
            if self.state is not VideoSessionState.IDLE:
                raise RuntimeError(f"cannot start from {self.state.value}")
            events: list[VideoEvent] = []
            self._window.clear()
            self._selected = None
            self._selected_spread = None
            self._active_job_id = None
            self._processing_job_id = None
            self._transition(VideoSessionState.ARMING, events)
            events.append(self._event(VideoEventType.SESSION_STARTED))
            try:
                self.camera.start()
                self._camera_started = True
                self._camera_resource_released = False
            except CameraUnavailableError:
                self._fail(ReadinessReason.CAMERA_UNAVAILABLE, events)
                return tuple(events)
            except Exception:
                self._fail(ReadinessReason.CAMERA_UNAVAILABLE, events)
                return tuple(events)
            self._next_sample_at = self.clock.monotonic()
            self._transition(VideoSessionState.SEARCHING, events)
            return tuple(events)

    def poll(self) -> tuple[VideoEvent, ...]:
        with self._lock:
            events: list[VideoEvent] = []
            if self.state is VideoSessionState.CANCELLING:
                self._poll_cancelling(events)
                return tuple(events)
            if self.state is VideoSessionState.PROCESSING_CANDIDATE:
                self._poll_processing(events)
                return tuple(events)
            if self.state is VideoSessionState.LOCAL_RETRY:
                if self.clock.monotonic() < self._retry_until:
                    return ()
                self._transition(VideoSessionState.SEARCHING, events)
                self._next_sample_at = self.clock.monotonic()
            if self.state not in {VideoSessionState.SEARCHING, VideoSessionState.SETTLING}:
                return tuple(events)

            now = self.clock.monotonic()
            if now < self._next_sample_at:
                return tuple(events)
            self._next_sample_at = now + self.policy.sample_interval_ms / 1000.0
            try:
                frame = self.camera.read()
            except FrameDecodeError:
                self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
                return tuple(events)
            except CameraUnavailableError:
                self._fail(ReadinessReason.CAMERA_UNAVAILABLE, events)
                return tuple(events)
            except Exception:
                self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
                return tuple(events)

            if frame is None:
                if self.camera.exhausted:
                    events.append(self._event(VideoEventType.SOURCE_EXHAUSTED))
                    self._stop_camera()
                    self._transition(VideoSessionState.IDLE, events)
                return tuple(events)

            self._frames_received += 1
            try:
                observation = self.analyzer.analyze(frame)
            except Exception:
                self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
                return tuple(events)
            self._frames_evaluated += 1
            if self._window.append(observation):
                self._frames_dropped += 1
            self._peak_window_depth = max(self._peak_window_depth, len(self._window))
            first_reason = observation.candidate.retry_reasons[0] if observation.candidate.retry_reasons else None
            details = dict(observation.candidate.metrics)
            details.update({"window_depth": len(self._window), "dropped_total": self._frames_dropped})
            events.append(
                self._event(
                    VideoEventType.CANDIDATE_OBSERVED,
                    source_frame_id=frame.frame_id,
                    reason=first_reason,
                    details=details,
                )
            )

            assessment = self.assessor.assess(self._window.snapshot())
            if not assessment.stable or assessment.best is None:
                self._transition(VideoSessionState.SETTLING, events)
                if assessment.reasons:
                    events.append(
                        self._event(
                            VideoEventType.GUIDANCE_REQUESTED,
                            source_frame_id=frame.frame_id,
                            reason=assessment.reasons[0],
                            details={"observations_considered": assessment.observations_considered},
                        )
                    )
                return tuple(events)

            self._selected = assessment.best
            self._spread_counter += 1
            self._selected_spread = SpreadId(f"{self.session_id}-spread-{self._spread_counter:06d}")
            self._job_counter += 1
            self._active_job_id = ProcessingJobId(
                f"{self.session_id}-job-{self._job_counter:06d}"
            )
            self._processing_job_id = self._active_job_id
            self._frames_selected += 1
            events.append(
                self._event(
                    VideoEventType.CANDIDATE_SELECTED,
                    source_frame_id=self._selected.frame.frame_id,
                    spread_id=self._selected_spread,
                    details=dict(assessment.metrics),
                )
            )
            self._transition(VideoSessionState.PROCESSING_CANDIDATE, events)
            self._processing_started_at = self.clock.monotonic()
            self._future = self._executor.submit(
                self.preparer.prepare,
                self._selected.frame,
                self._selected_spread,
                self._active_job_id,
            )
            return tuple(events)

    def cancel(self) -> tuple[VideoEvent, ...]:
        with self._lock:
            if self.state is VideoSessionState.IDLE:
                return ()
            if self.state is VideoSessionState.CANCELLING:
                return ()
            events: list[VideoEvent] = []
            self._cancel_started_at = self.clock.monotonic()
            self._transition(VideoSessionState.CANCELLING, events)
            self._active_job_id = None
            self._stop_camera()
            if self._future is None or self._future.cancel():
                self._discard_processing_job()
                self._finalize_cancel(events)
            elif self._future.done():
                self._discard_completed_preparation()
                self._finalize_cancel(events)
            return tuple(events)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self.state is not VideoSessionState.IDLE:
                self.cancel()
            self._stop_camera()
            self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)

    def __enter__(self) -> SampledFrameEngine:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _poll_processing(self, events: list[VideoEvent]) -> None:
        future = self._future
        if future is None or not future.done():
            return
        try:
            decision = future.result()
        except Exception:
            self._discard_processing_job()
            self._complete_local_retry(ReadinessReason.SEAM_FAILED, events)
            return
        self._frames_processed += 1
        if self._processing_started_at is not None:
            self._processing_latency_ms = max(
                0.0, (self.clock.monotonic() - self._processing_started_at) * 1000.0
            )
        assert (
            self._selected is not None
            and self._selected_spread is not None
            and self._active_job_id is not None
            and self._processing_job_id == self._active_job_id
        )
        selected_frame_id = self._selected.frame.frame_id
        if (
            decision.source_frame_id != selected_frame_id
            or decision.spread_id != self._selected_spread
            or decision.job_id != self._active_job_id
        ):
            self._discard_prepared(decision)
            self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
            return
        events.append(
            self._event(
                VideoEventType.CANDIDATE_PROCESSED,
                source_frame_id=selected_frame_id,
                spread_id=self._selected_spread,
                reason=decision.reasons[0] if decision.reasons else None,
                details=dict(decision.metrics),
            )
        )
        if decision.state is PreparationState.RETRY_LOCAL:
            self._complete_local_retry(decision.reasons[0], events, decision.retry_after_ms)
            return
        if decision.state is PreparationState.PREPARED and decision.prepared is not None:
            if (
                self._active_job_id != decision.prepared.job_id
                or decision.prepared.session_id != self.session_id
            ):
                self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
                return
            try:
                artifact = self.artifact_store.commit(decision.prepared)
            except ArtifactCollisionError:
                self._discard_prepared(decision)
                self._fail(ReadinessReason.ARTIFACT_COLLISION, events)
                return
            except Exception:
                self._discard_prepared(decision)
                self._fail(ReadinessReason.ARTIFACT_COMMIT_FAILED, events)
                return
            if (
                artifact.source_frame_id != selected_frame_id
                or artifact.spread_id != self._selected_spread
            ):
                self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
                return
            events.append(
                self._event(
                    VideoEventType.ARTIFACT_READY,
                    source_frame_id=selected_frame_id,
                    spread_id=self._selected_spread,
                    artifact_id=artifact.artifact_id,
                )
            )
            self._stop_camera()
            self._clear_processing()
            self._transition(VideoSessionState.READY_FOR_SERVER_PREFLIGHT, events)
            return
        reason = decision.reasons[0] if decision.reasons else ReadinessReason.FRAME_DECODE_FAILED
        self._fail(reason, events)

    def _complete_local_retry(
        self,
        reason: ReadinessReason,
        events: list[VideoEvent],
        retry_after_ms: int | None = None,
    ) -> None:
        self._window.clear()
        self._clear_processing()
        cooldown = self.policy.local_retry_cooldown_ms if retry_after_ms is None else retry_after_ms
        self._retry_until = self.clock.monotonic() + cooldown / 1000.0
        self._transition(VideoSessionState.LOCAL_RETRY, events, reason=reason)

    def _poll_cancelling(self, events: list[VideoEvent]) -> None:
        if self._future is None or self._future.done():
            if self._future is not None and self._future.done():
                self._discard_completed_preparation()
            self._finalize_cancel(events)

    def _discard_completed_preparation(self) -> None:
        assert self._future is not None and self._future.done()
        try:
            decision = self._future.result()
        except BaseException:
            self._discard_processing_job()
            return
        self._discard_prepared(decision)

    def _discard_prepared(self, decision: PreparationDecision) -> None:
        if decision.prepared is None:
            return
        try:
            self.artifact_store.discard(decision.prepared)
        except Exception:
            pass

    def _discard_processing_job(self) -> None:
        if self._processing_job_id is None:
            return
        try:
            self.artifact_store.discard_job(self._processing_job_id)
        except Exception:
            pass

    def _finalize_cancel(self, events: list[VideoEvent]) -> None:
        if self._cancel_started_at is not None:
            self._cancel_latency_ms = max(
                0.0, (self.clock.monotonic() - self._cancel_started_at) * 1000.0
            )
        self._window.clear()
        self._clear_processing()
        events.append(self._event(VideoEventType.SESSION_CANCELLED))
        self._transition(VideoSessionState.IDLE, events)

    def _clear_processing(self) -> None:
        self._future = None
        self._selected = None
        self._selected_spread = None
        self._active_job_id = None
        self._processing_job_id = None
        self._processing_started_at = None

    def _fail(self, reason: ReadinessReason, events: list[VideoEvent]) -> None:
        self._stop_camera()
        self._clear_processing()
        self._transition(VideoSessionState.ERROR, events, reason=reason)
        events.append(self._event(VideoEventType.SESSION_ERROR, reason=reason))

    def _stop_camera(self) -> None:
        if not self._camera_started:
            self._camera_resource_released = True
            return
        try:
            self.camera.stop()
        finally:
            self._camera_started = False
            self._camera_resource_released = True

    def _transition(
        self,
        state: VideoSessionState,
        events: list[VideoEvent],
        *,
        reason: ReadinessReason | None = None,
    ) -> None:
        if state is self.state:
            return
        previous = self.state
        self.state = state
        events.append(
            self._event(
                VideoEventType.STATE_CHANGED,
                reason=reason,
                details={"from": previous.value, "to": state.value},
            )
        )

    def _event(self, event_type: VideoEventType, **kwargs: Any) -> VideoEvent:
        self._event_counter += 1
        return VideoEvent(
            event_type=event_type,
            event_id=f"{self.session_id}-event-{self._event_counter:08d}",
            at_monotonic=self.clock.monotonic(),
            session_id=self.session_id,
            producer_version=self.producer_version,
            session_state=self.state,
            **kwargs,
        )
