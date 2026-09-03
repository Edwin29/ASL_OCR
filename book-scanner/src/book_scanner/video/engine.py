"""Sampled-frame state engine for the PC scanner prototype."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np
import cv2

from .artifacts import ArtifactCollisionError
from .candidate import CandidateAnalyzer, CandidateObservation, CandidateWindow, StableWindowAssessor
from .config import (
    CandidatePolicy,
    GuidancePolicy,
    IdentityPolicy,
    OpaqueFooterIdentityPolicy,
    OpaqueFooterInputStage,
    OpaqueIdentityStrategy,
    PageChangePolicy,
    PageNumberPolicy,
    PageNumberSchedulerPolicy,
)
from .events import OpaqueIdentityRole, VideoEvent, VideoEventType
from .guidance import GuidanceArbiter
from .identity import (
    IdentityFingerprintError,
    IdentityMatchKind,
    InMemoryPageIdentityLedger,
    LedgerMatch,
    OpenCVIdentityFingerprinter,
    SpreadIdentity,
    SpreadVisualFingerprint,
)
from .page_change import HysteresisPageChangeGate
from .page_number import (
    InMemoryPageKeyLedger,
    PageKeyRelation,
    PageNumberChangeTracker,
    PageNumberStatus,
    SpreadPageKey,
    SpreadPageNumberObservation,
)
from .page_number_scheduler import PageNumberVerificationScheduler
from .opaque_identity import (
    InMemoryOpaqueIdentityLedger,
    OpaqueFooterTokenPair,
    OpaqueIdentityDecision,
    OpaqueIdentityDecisionKind,
    OpaqueQueryCollector,
    OpaqueReferenceBank,
    token_pair_from_page_observation,
)
from .protocols import (
    ArtifactStore,
    CameraSource,
    Clock,
    PageChangeGate,
    PageIdentityLedger,
    PageNumberProvider,
    SpreadIdentityProvider,
    SpreadPreparer,
)
from .sources import CameraUnavailableError, FrameDecodeError, SystemClock
from .types import (
    ArtifactId,
    PreparationDecision,
    PreparationState,
    ProcessingJobId,
    ReadinessReason,
    SpreadArtifactRef,
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
    identity_latency_ms: float | None
    waiting_preview_frames: int
    duplicates_suppressed: int
    identity_ambiguous: int
    page_changes: int
    page_number_latency_ms: float | None
    page_number_conflicts: int
    page_number_sampled_spreads: int
    page_number_hard_gate_rejected_spreads: int
    page_number_eligible_spreads: int
    page_number_requested_spreads: int
    page_number_skipped_spreads: int
    page_number_audit_requests: int
    page_number_verification_bursts: int
    page_number_burst_timeouts: int
    opaque_identity_valid_observations: int
    opaque_identity_missing_observations: int
    opaque_identity_same_decisions: int
    opaque_identity_different_decisions: int
    opaque_identity_unknown_timeouts: int
    opaque_identity_hard_rejected_observations: int
    opaque_identity_busy_skipped_observations: int
    opaque_identity_effective_interval_ms: float | None


class SampledFrameEngine:
    """Drive a sampled capture session without coupling it to delivery.

    ``poll`` never waits for the processor.  This keeps start/cancel responsive
    even when the V2 seam/UVDoc implementation is later plugged in.
    """

    producer_version = "sampled-frame-engine-v3a5"

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
        guidance_policy: GuidancePolicy = GuidancePolicy(),
        assessor: StableWindowAssessor | None = None,
        identity_policy: IdentityPolicy = IdentityPolicy(),
        page_change_policy: PageChangePolicy = PageChangePolicy(),
        page_number_policy: PageNumberPolicy = PageNumberPolicy(),
        page_number_scheduler_policy: PageNumberSchedulerPolicy = PageNumberSchedulerPolicy(),
        identity_provider: SpreadIdentityProvider | None = None,
        identity_ledger: PageIdentityLedger | None = None,
        page_change_gate: PageChangeGate | None = None,
        page_number_provider: PageNumberProvider | None = None,
        page_key_ledger: InMemoryPageKeyLedger | None = None,
        page_number_scheduler: PageNumberVerificationScheduler | None = None,
        opaque_identity_policy: OpaqueFooterIdentityPolicy | None = None,
        opaque_identity_ledger: InMemoryOpaqueIdentityLedger | None = None,
        data_pack_id: str | None = None,
    ):
        if not session_id.strip():
            raise ValueError("session_id must be non-empty")
        self.camera = camera
        self.analyzer = analyzer
        self.preparer = preparer
        self.artifact_store = artifact_store
        self.clock = clock or SystemClock()
        self.policy = policy
        self.guidance = GuidanceArbiter(guidance_policy)
        self.assessor = assessor or StableWindowAssessor(policy)
        self.identity_policy = identity_policy
        self.page_change_policy = page_change_policy
        self.page_number_policy = page_number_policy
        self.identity_provider = identity_provider or OpenCVIdentityFingerprinter(identity_policy)
        self.identity_ledger = identity_ledger or InMemoryPageIdentityLedger(identity_policy)
        self.page_change_gate = page_change_gate or HysteresisPageChangeGate(
            identity_policy,
            page_change_policy,
        )
        self.page_number_provider = page_number_provider
        self.page_key_ledger = page_key_ledger or InMemoryPageKeyLedger(page_number_policy)
        self.page_number_change_tracker = PageNumberChangeTracker(page_number_policy)
        self.page_number_scheduler = page_number_scheduler or PageNumberVerificationScheduler(
            page_number_scheduler_policy
        )
        self.page_number_scheduler_policy = self.page_number_scheduler.policy
        self.session_id = session_id
        self.data_pack_id = data_pack_id or f"session:{session_id}"
        if not self.data_pack_id.strip():
            raise ValueError("data_pack_id must be non-empty")
        self.opaque_identity_policy = opaque_identity_policy
        self._opaque_identity_active = bool(
            opaque_identity_policy is not None
            and opaque_identity_policy.strategy is OpaqueIdentityStrategy.M1_SELECTED_RAW_PAIR
        )
        if self._opaque_identity_active and page_number_provider is None:
            raise ValueError("M1 opaque identity requires an explicit page-number provider")
        self.opaque_identity_ledger = (
            opaque_identity_ledger
            if opaque_identity_ledger is not None
            else (
                InMemoryOpaqueIdentityLedger(opaque_identity_policy, self.data_pack_id)
                if opaque_identity_policy is not None
                else None
            )
        )

        self.state = VideoSessionState.IDLE
        self._window = CandidateWindow(policy.sample_window_size)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scanner-frame")
        self._future: Future[PreparationDecision] | None = None
        self._selected: CandidateObservation | None = None
        self._selected_spread: SpreadId | None = None
        self._active_job_id: ProcessingJobId | None = None
        self._processing_job_id: ProcessingJobId | None = None
        self._processing_started_at: float | None = None
        self._pending_artifact: SpreadArtifactRef | None = None
        self._pending_identity: SpreadIdentity | None = None
        self._pending_preview: SpreadVisualFingerprint | None = None
        self._pending_page_number: SpreadPageNumberObservation | None = None
        self._page_change_key: SpreadPageKey | None = None
        self._page_change_baseline_preview: SpreadVisualFingerprint | None = None
        self._opaque_collector: OpaqueQueryCollector | None = None
        self._opaque_candidate_pairs: tuple[OpaqueFooterTokenPair, ...] = ()
        self._opaque_waiting_reference: OpaqueReferenceBank | None = None
        self._next_opaque_sample_at = 0.0
        self._last_opaque_observation_at: float | None = None
        self._opaque_effective_interval_ms: float | None = None
        self._next_sample_at = 0.0
        self._next_page_change_sample_at = 0.0
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
        self._identity_latency_ms: float | None = None
        self._waiting_preview_frames = 0
        self._duplicates_suppressed = 0
        self._identity_ambiguous = 0
        self._page_changes = 0
        self._page_number_latency_ms: float | None = None
        self._page_number_conflicts = 0
        self._opaque_identity_valid_observations = 0
        self._opaque_identity_missing_observations = 0
        self._opaque_identity_same_decisions = 0
        self._opaque_identity_different_decisions = 0
        self._opaque_identity_unknown_timeouts = 0
        self._opaque_identity_hard_rejected_observations = 0
        # Recognition is synchronous at this boundary, so requests cannot queue.
        self._opaque_identity_busy_skipped_observations = 0
        self._lock = threading.RLock()

    @property
    def diagnostics(self) -> FrameEngineDiagnostics:
        with self._lock:
            scheduler = self.page_number_scheduler.diagnostics
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
                identity_latency_ms=self._identity_latency_ms,
                waiting_preview_frames=self._waiting_preview_frames,
                duplicates_suppressed=self._duplicates_suppressed,
                identity_ambiguous=self._identity_ambiguous,
                page_changes=self._page_changes,
                page_number_latency_ms=self._page_number_latency_ms,
                page_number_conflicts=self._page_number_conflicts,
                page_number_sampled_spreads=scheduler.sampled_spreads,
                page_number_hard_gate_rejected_spreads=scheduler.hard_gate_rejected_spreads,
                page_number_eligible_spreads=scheduler.eligible_spreads,
                page_number_requested_spreads=scheduler.requested_spreads,
                page_number_skipped_spreads=scheduler.skipped_spreads,
                page_number_audit_requests=scheduler.audit_requests,
                page_number_verification_bursts=scheduler.verification_bursts,
                page_number_burst_timeouts=scheduler.burst_timeouts,
                opaque_identity_valid_observations=self._opaque_identity_valid_observations,
                opaque_identity_missing_observations=self._opaque_identity_missing_observations,
                opaque_identity_same_decisions=self._opaque_identity_same_decisions,
                opaque_identity_different_decisions=self._opaque_identity_different_decisions,
                opaque_identity_unknown_timeouts=self._opaque_identity_unknown_timeouts,
                opaque_identity_hard_rejected_observations=(
                    self._opaque_identity_hard_rejected_observations
                ),
                opaque_identity_busy_skipped_observations=(
                    self._opaque_identity_busy_skipped_observations
                ),
                opaque_identity_effective_interval_ms=self._opaque_effective_interval_ms,
            )

    @property
    def pending_artifact(self) -> SpreadArtifactRef | None:
        """Return the immutable artifact currently awaiting delivery settlement."""

        with self._lock:
            return self._pending_artifact

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
            self._release_pending()
            self._pending_preview = None
            self._pending_page_number = None
            self._page_change_key = None
            self._page_change_baseline_preview = None
            self._opaque_collector = None
            self._opaque_candidate_pairs = ()
            self._opaque_waiting_reference = None
            self._last_opaque_observation_at = None
            self._opaque_effective_interval_ms = None
            self.page_change_gate.reset()
            self.page_number_change_tracker.reset()
            self.page_number_scheduler.reset()
            self.guidance.reset()
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
            if self.state is VideoSessionState.VERIFYING_IDENTITY:
                self._poll_opaque_identity(events)
                return tuple(events)
            if self.state is VideoSessionState.WAITING_FOR_PAGE_CHANGE:
                if self._opaque_identity_active:
                    self._poll_opaque_page_change(events)
                else:
                    self._poll_page_change(events)
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
            primary_reason = assessment.reasons[0] if assessment.reasons else None
            self._publish_preview_diagnostics(
                observation,
                primary_reason=primary_reason,
            )
            if not assessment.stable or assessment.best is None:
                self._transition(VideoSessionState.SETTLING, events)
                guidance = self.guidance.observe(primary_reason, now)
                if guidance is not None:
                    events.append(
                        self._event(
                            VideoEventType.GUIDANCE_REQUESTED,
                            source_frame_id=frame.frame_id,
                            reason=guidance.reason,
                            details={
                                "observations_considered": assessment.observations_considered,
                                "stable_for_samples": guidance.stable_for_samples,
                                "stable_for_ms": guidance.stable_for_ms,
                            },
                        )
                    )
                return tuple(events)

            self.guidance.observe(None, now)
            self._selected = assessment.best
            self._spread_counter += 1
            self._selected_spread = SpreadId(f"{self.session_id}-spread-{self._spread_counter:06d}")
            self._frames_selected += 1
            events.append(
                self._event(
                    VideoEventType.CANDIDATE_SELECTED,
                    source_frame_id=self._selected.frame.frame_id,
                    spread_id=self._selected_spread,
                    details={
                        **dict(assessment.metrics),
                        "identity_role": OpaqueIdentityRole.CANDIDATE_VERIFICATION.value,
                    },
                )
            )
            if self._opaque_identity_active:
                assert self.opaque_identity_policy is not None
                assert self.opaque_identity_ledger is not None
                self._opaque_collector = OpaqueQueryCollector(
                    self.opaque_identity_policy,
                    self.opaque_identity_ledger.recent_accepted(),
                    started_at=self.clock.monotonic(),
                )
                self._next_opaque_sample_at = self.clock.monotonic()
                self._last_opaque_observation_at = None
                self._transition(VideoSessionState.VERIFYING_IDENTITY, events)
                events.append(
                    self._event(
                        VideoEventType.OPAQUE_IDENTITY_COLLECTION_STARTED,
                        source_frame_id=self._selected.frame.frame_id,
                        spread_id=self._selected_spread,
                        details={
                            **self._opaque_policy_details(),
                            "identity_role": OpaqueIdentityRole.CANDIDATE_VERIFICATION.value,
                        },
                    )
                )
            else:
                self._begin_processing_selected(events)
            return tuple(events)

    def _begin_processing_selected(self, events: list[VideoEvent]) -> None:
        assert self._selected is not None and self._selected_spread is not None
        self._job_counter += 1
        self._active_job_id = ProcessingJobId(
            f"{self.session_id}-job-{self._job_counter:06d}"
        )
        self._processing_job_id = self._active_job_id
        self._transition(VideoSessionState.PROCESSING_CANDIDATE, events)
        self._processing_started_at = self.clock.monotonic()
        self._future = self._executor.submit(
            self.preparer.prepare,
            self._selected.frame,
            self._selected_spread,
            self._active_job_id,
            self.session_id,
        )

    def _poll_opaque_identity(self, events: list[VideoEvent]) -> None:
        assert self._opaque_identity_active
        assert self.opaque_identity_policy is not None
        assert self.opaque_identity_ledger is not None
        assert self._opaque_collector is not None
        assert self._selected is not None and self._selected_spread is not None
        now = self.clock.monotonic()
        timeout = self._opaque_collector.decision(now=now)
        if timeout.timed_out:
            self._emit_opaque_decision(
                timeout,
                self._selected.frame.frame_id,
                OpaqueIdentityRole.CANDIDATE_VERIFICATION,
                events,
            )
            events.append(
                self._event(
                    VideoEventType.GUIDANCE_REQUESTED,
                    source_frame_id=self._selected.frame.frame_id,
                    spread_id=self._selected_spread,
                    reason=ReadinessReason.FOOTER_IDENTITY_UNAVAILABLE,
                    details={"valid_observations": timeout.valid_observations},
                )
            )
            self._opaque_collector = None
            self._opaque_candidate_pairs = ()
            self._complete_local_retry(ReadinessReason.FOOTER_IDENTITY_UNAVAILABLE, events)
            return
        if now < self._next_opaque_sample_at:
            return
        self._next_opaque_sample_at = now + self.opaque_identity_policy.observation_interval_ms / 1000.0
        frame = self._read_frame_for_opaque(events)
        if frame is None:
            return
        try:
            analyzed = self.analyzer.analyze(frame)
        except Exception:
            self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
            return
        self._frames_evaluated += 1
        self._publish_preview_diagnostics(analyzed)
        if analyzed.candidate.retry_reasons:
            self._opaque_identity_hard_rejected_observations += 1
            self._emit_opaque_abort(
                analyzed.candidate.retry_reasons[0].value,
                frame.frame_id,
                OpaqueIdentityRole.CANDIDATE_VERIFICATION,
                events,
            )
            self._window.clear()
            self._opaque_collector = None
            self._opaque_candidate_pairs = ()
            self._clear_processing()
            self._next_sample_at = now + self.policy.sample_interval_ms / 1000.0
            self._transition(
                VideoSessionState.SETTLING,
                events,
                reason=analyzed.candidate.retry_reasons[0],
            )
            return
        pair = self._observe_opaque_pair(frame, analyzed, events)
        decision = (
            self._opaque_collector.observe(pair)
            if pair is not None
            else self._opaque_collector.observe_missing()
        )
        self._emit_opaque_observation(
            frame.frame_id,
            pair,
            decision,
            OpaqueIdentityRole.CANDIDATE_VERIFICATION,
            events,
        )
        if decision.kind is OpaqueIdentityDecisionKind.UNKNOWN:
            return
        self._emit_opaque_decision(
            decision,
            frame.frame_id,
            OpaqueIdentityRole.CANDIDATE_VERIFICATION,
            events,
        )
        if decision.kind is OpaqueIdentityDecisionKind.SAME:
            matched = (
                self.opaque_identity_ledger.find(decision.matched_artifact_id)
                if decision.matched_artifact_id is not None
                else None
            )
            if matched is None:
                self._complete_local_retry(ReadinessReason.FOOTER_IDENTITY_UNAVAILABLE, events)
                return
            self._duplicates_suppressed += 1
            events.append(
                self._event(
                    VideoEventType.DUPLICATE_SUPPRESSED,
                    source_frame_id=frame.frame_id,
                    spread_id=self._selected_spread,
                    artifact_id=matched.artifact_id,
                    details={
                        **self._opaque_policy_details(),
                        "match_count": decision.match_count,
                        "valid_observations": decision.valid_observations,
                        "matched_artifact_id": matched.artifact_id.value,
                    },
                )
            )
            spread_id = self._selected_spread
            self._window.clear()
            self._opaque_waiting_reference = matched
            self._opaque_collector = OpaqueQueryCollector(
                self.opaque_identity_policy,
                (matched,),
                started_at=now,
            )
            self._next_opaque_sample_at = now
            self._clear_processing()
            self._transition(VideoSessionState.WAITING_FOR_PAGE_CHANGE, events)
            events.append(
                self._event(
                    VideoEventType.OPAQUE_IDENTITY_COLLECTION_STARTED,
                    source_frame_id=frame.frame_id,
                    spread_id=spread_id,
                    details={
                        **self._opaque_policy_details(),
                        "identity_role": OpaqueIdentityRole.PAGE_CHANGE.value,
                    },
                )
            )
            events.append(
                self._event(
                    VideoEventType.WAITING_FOR_PAGE_CHANGE,
                    source_frame_id=frame.frame_id,
                    spread_id=spread_id,
                    artifact_id=matched.artifact_id,
                    details={"duplicate_suppressed": True, "strategy": "m1_selected_raw_pair"},
                )
            )
            return
        self._opaque_candidate_pairs = self._opaque_collector.observations[
            : self.opaque_identity_policy.reference_bank_size
        ]
        self._opaque_collector = None
        self._begin_processing_selected(events)

    def _poll_opaque_page_change(self, events: list[VideoEvent]) -> None:
        assert self._opaque_identity_active
        assert self.opaque_identity_policy is not None
        reference = self._opaque_waiting_reference
        if reference is None and self.opaque_identity_ledger is not None:
            accepted = self.opaque_identity_ledger.recent_accepted()
            reference = accepted[0] if accepted else None
            self._opaque_waiting_reference = reference
        if reference is None:
            self._fail(ReadinessReason.FOOTER_IDENTITY_UNAVAILABLE, events)
            return
        now = self.clock.monotonic()
        if self._opaque_collector is None:
            self._opaque_collector = OpaqueQueryCollector(
                self.opaque_identity_policy,
                (reference,),
                started_at=now,
            )
        timeout = self._opaque_collector.decision(now=now)
        if timeout.timed_out:
            self._emit_opaque_decision(
                timeout,
                reference.observations[0].source_frame_id,
                OpaqueIdentityRole.PAGE_CHANGE,
                events,
            )
            self._opaque_collector = OpaqueQueryCollector(
                self.opaque_identity_policy,
                (reference,),
                started_at=now,
            )
        if now < self._next_opaque_sample_at:
            return
        self._next_opaque_sample_at = now + self.opaque_identity_policy.observation_interval_ms / 1000.0
        frame = self._read_frame_for_opaque(events)
        if frame is None:
            return
        self._waiting_preview_frames += 1
        try:
            analyzed = self.analyzer.analyze(frame)
        except Exception:
            self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
            return
        self._frames_evaluated += 1
        self._publish_preview_diagnostics(analyzed)
        if analyzed.candidate.retry_reasons:
            self._opaque_identity_hard_rejected_observations += 1
            self._opaque_collector = OpaqueQueryCollector(
                self.opaque_identity_policy,
                (reference,),
                started_at=now,
            )
            return
        pair = self._observe_opaque_pair(frame, analyzed, events)
        decision = (
            self._opaque_collector.observe(pair)
            if pair is not None
            else self._opaque_collector.observe_missing()
        )
        self._emit_opaque_observation(
            frame.frame_id,
            pair,
            decision,
            OpaqueIdentityRole.PAGE_CHANGE,
            events,
        )
        if decision.kind is OpaqueIdentityDecisionKind.UNKNOWN:
            return
        self._emit_opaque_decision(
            decision,
            frame.frame_id,
            OpaqueIdentityRole.PAGE_CHANGE,
            events,
        )
        if decision.kind is OpaqueIdentityDecisionKind.SAME:
            self._opaque_collector = OpaqueQueryCollector(
                self.opaque_identity_policy,
                (reference,),
                started_at=now,
            )
            return
        self._page_changes += 1
        self._window.clear()
        self._opaque_collector = None
        self._opaque_waiting_reference = None
        self.guidance.reset()
        events.append(
            self._event(
                VideoEventType.PAGE_CHANGED,
                source_frame_id=frame.frame_id,
                details={
                    "strategy": "m1_selected_raw_pair",
                    "valid_observations": decision.valid_observations,
                    "match_count": decision.match_count,
                },
            )
        )
        self._transition(VideoSessionState.SEARCHING, events)
        self._next_sample_at = now + self.policy.sample_interval_ms / 1000.0

    def _read_frame_for_opaque(self, events: list[VideoEvent]):
        try:
            frame = self.camera.read()
        except FrameDecodeError:
            self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
            return None
        except CameraUnavailableError:
            self._fail(ReadinessReason.CAMERA_UNAVAILABLE, events)
            return None
        except Exception:
            self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
            return None
        if frame is None and self.camera.exhausted:
            if self.state is VideoSessionState.VERIFYING_IDENTITY:
                self._emit_opaque_abort(
                    "source_exhausted",
                    self._selected.frame.frame_id if self._selected is not None else None,
                    OpaqueIdentityRole.CANDIDATE_VERIFICATION,
                    events,
                )
            events.append(self._event(VideoEventType.SOURCE_EXHAUSTED))
            self._stop_camera()
            self._opaque_collector = None
            self._opaque_candidate_pairs = ()
            self._transition(VideoSessionState.IDLE, events)
            return None
        if frame is not None:
            self._frames_received += 1
        return frame

    def _observe_opaque_pair(
        self,
        frame,
        analyzed: CandidateObservation,
        events: list[VideoEvent],
    ) -> OpaqueFooterTokenPair | None:
        assert self.opaque_identity_policy is not None
        assert self.page_number_provider is not None
        maximum = (
            self.page_number_policy.preview_max_dimension
            if self.opaque_identity_policy.input_stage is OpaqueFooterInputStage.PREVIEW_1920
            else max(frame.payload.shape[:2])
        )
        try:
            gray, mask = _page_number_preview_inputs(
                frame.payload,
                analyzed.mask_preview,
                maximum,
            )
            observation = self.page_number_provider.observe_preview(
                gray,
                mask,
                analyzed.seam_proxy_fraction,
                frame.frame_id,
                self.data_pack_id,
            )
            self._page_number_latency_ms = observation.processing_ms
            return token_pair_from_page_observation(
                observation,
                captured_at_monotonic=frame.captured_at_monotonic,
                recognition_stage=self.opaque_identity_policy.input_stage.value,
            )
        except (OSError, RuntimeError, ValueError, TypeError):
            return None

    def _emit_opaque_observation(
        self,
        frame_id,
        pair: OpaqueFooterTokenPair | None,
        decision: OpaqueIdentityDecision,
        identity_role: OpaqueIdentityRole,
        events: list[VideoEvent],
    ) -> None:
        observed_at = self.clock.monotonic()
        if self._last_opaque_observation_at is not None:
            self._opaque_effective_interval_ms = max(
                0.0,
                (observed_at - self._last_opaque_observation_at) * 1000.0,
            )
        self._last_opaque_observation_at = observed_at
        if pair is None:
            self._opaque_identity_missing_observations += 1
        else:
            self._opaque_identity_valid_observations += 1
        events.append(
            self._event(
                VideoEventType.OPAQUE_IDENTITY_OBSERVED,
                source_frame_id=frame_id,
                spread_id=self._selected_spread,
                details={
                    **self._opaque_policy_details(),
                    "identity_role": identity_role.value,
                    "valid": pair is not None,
                    "pair_digest": pair.digest if pair is not None else None,
                    "left_token_length": len(pair.left_raw_token) if pair is not None else None,
                    "right_token_length": len(pair.right_raw_token) if pair is not None else None,
                    "valid_observations": decision.valid_observations,
                    "match_count": decision.match_count,
                    "decision": decision.kind.value,
                    "recognition_processing_ms": self._page_number_latency_ms,
                    "effective_interval_ms": self._opaque_effective_interval_ms,
                },
            )
        )

    def _emit_opaque_decision(
        self,
        decision: OpaqueIdentityDecision,
        frame_id,
        identity_role: OpaqueIdentityRole,
        events: list[VideoEvent],
    ) -> None:
        if decision.kind is OpaqueIdentityDecisionKind.SAME:
            self._opaque_identity_same_decisions += 1
        elif decision.kind is OpaqueIdentityDecisionKind.DIFFERENT:
            self._opaque_identity_different_decisions += 1
        elif decision.timed_out:
            self._opaque_identity_unknown_timeouts += 1
        events.append(
            self._event(
                VideoEventType.OPAQUE_IDENTITY_DECIDED,
                source_frame_id=frame_id,
                spread_id=self._selected_spread,
                details={
                    **self._opaque_policy_details(),
                    "identity_role": identity_role.value,
                    "decision": decision.kind.value,
                    "valid_observations": decision.valid_observations,
                    "match_count": decision.match_count,
                    "matched_artifact_id": (
                        decision.matched_artifact_id.value
                        if decision.matched_artifact_id is not None
                        else None
                    ),
                    "timed_out": decision.timed_out,
                },
            )
        )

    def _emit_opaque_abort(
        self,
        terminal_reason: str,
        frame_id,
        identity_role: OpaqueIdentityRole,
        events: list[VideoEvent],
    ) -> None:
        collector = self._opaque_collector
        if collector is None:
            return
        events.append(
            self._event(
                VideoEventType.OPAQUE_IDENTITY_ABORTED,
                source_frame_id=frame_id,
                spread_id=self._selected_spread,
                details={
                    **self._opaque_policy_details(),
                    "identity_role": identity_role.value,
                    "terminal_reason": terminal_reason,
                    "valid_observations": len(collector.observations),
                    "missing_observations": collector.missing_observations,
                },
            )
        )

    def _opaque_policy_details(self) -> dict[str, str | int | float | bool | None]:
        assert self.opaque_identity_policy is not None
        recognizer = getattr(self.page_number_provider, "recognizer", None)
        cache = getattr(self.page_number_provider, "cache", None)
        return {
            "strategy": self.opaque_identity_policy.strategy.value,
            "input_stage": self.opaque_identity_policy.input_stage.value,
            "query_sample_count": self.opaque_identity_policy.query_sample_count,
            "k_same": self.opaque_identity_policy.k_same,
            "k_different": self.opaque_identity_policy.k_different,
            "validated": self.opaque_identity_policy.validated,
            "provenance": self.opaque_identity_policy.provenance,
            "recognizer_load_count": getattr(recognizer, "load_count", None),
            "recognizer_call_count": getattr(recognizer, "calls", None),
            "recognition_cache_hits": getattr(cache, "hits", None),
            "recognition_cache_depth": len(cache) if cache is not None else None,
        }

    def delivery_queued(self, artifact_id: ArtifactId) -> tuple[VideoEvent, ...]:
        """Record local outbox ownership without claiming remote acceptance."""

        with self._lock:
            if not self._is_current_pending(artifact_id):
                return ()
            if self.state is VideoSessionState.UPLOADING:
                return ()
            if self.state not in {
                VideoSessionState.READY_FOR_SERVER_PREFLIGHT,
                VideoSessionState.REMOTE_RETRY,
            }:
                return ()
            events: list[VideoEvent] = []
            self._transition(VideoSessionState.UPLOADING, events)
            events.append(self._pending_event(VideoEventType.UPLOAD_QUEUED))
            return tuple(events)

    def delivery_retrying(self, artifact_id: ArtifactId) -> tuple[VideoEvent, ...]:
        """Keep the same immutable artifact pending during remote retry."""

        with self._lock:
            if not self._is_current_pending(artifact_id):
                return ()
            if self.state is VideoSessionState.REMOTE_RETRY:
                return ()
            if self.state not in {
                VideoSessionState.READY_FOR_SERVER_PREFLIGHT,
                VideoSessionState.UPLOADING,
            }:
                return ()
            events: list[VideoEvent] = []
            self._transition(VideoSessionState.REMOTE_RETRY, events)
            events.append(self._pending_event(VideoEventType.UPLOAD_RETRYING))
            return tuple(events)

    def delivery_confirmed(
        self,
        artifact_id: ArtifactId,
        receipt_id: str,
    ) -> tuple[VideoEvent, ...]:
        """Move PENDING to ACCEPTED exactly once, then arm page-change waiting."""

        with self._lock:
            if not isinstance(receipt_id, str) or not receipt_id.strip():
                raise ValueError("receipt_id must be non-empty")
            if not self._is_current_pending(artifact_id):
                return ()
            if (
                self._opaque_identity_active
                and (
                    self.opaque_identity_ledger is None
                    or self.opaque_identity_ledger.pending_artifact_id != artifact_id
                )
            ):
                return ()
            if self._pending_preview is None or not self.identity_ledger.confirm(artifact_id, receipt_id):
                return ()
            events: list[VideoEvent] = []
            accepted_opaque_bank = (
                self.opaque_identity_ledger.confirm(artifact_id, receipt_id)
                if self._opaque_identity_active and self.opaque_identity_ledger is not None
                else None
            )
            if self._opaque_identity_active and accepted_opaque_bank is None:
                raise RuntimeError("opaque identity pending bank disappeared during ACK")
            self._transition(VideoSessionState.DELIVERY_CONFIRMED, events)
            events.append(
                self._pending_event(
                    VideoEventType.DELIVERY_CONFIRMED,
                    details={"receipt_id": receipt_id},
                )
            )
            confirmed_page_key = (
                self._pending_page_number.key
                if self._pending_page_number is not None
                else None
            )
            self.page_key_ledger.accept(confirmed_page_key, artifact_id, receipt_id)
            self._page_change_key = confirmed_page_key
            self._page_change_baseline_preview = self._pending_preview
            self.page_number_change_tracker.arm(confirmed_page_key)
            self.page_number_scheduler.reset()
            self.page_change_gate.arm(self._pending_preview)
            self._window.clear()
            self._next_page_change_sample_at = self.clock.monotonic()
            if accepted_opaque_bank is not None:
                self._opaque_waiting_reference = accepted_opaque_bank
                assert self.opaque_identity_policy is not None
                self._opaque_collector = OpaqueQueryCollector(
                    self.opaque_identity_policy,
                    (accepted_opaque_bank,),
                    started_at=self.clock.monotonic(),
                )
                self._next_opaque_sample_at = self.clock.monotonic()
                events.append(
                    self._pending_event(
                        VideoEventType.OPAQUE_IDENTITY_BANK_ACCEPTED,
                        details={
                            "receipt_id": receipt_id,
                            "reference_bank_depth": len(accepted_opaque_bank.observations),
                            **self._opaque_policy_details(),
                        },
                    )
                )
            self._transition(VideoSessionState.WAITING_FOR_PAGE_CHANGE, events)
            if accepted_opaque_bank is not None:
                events.append(
                    self._pending_event(
                        VideoEventType.OPAQUE_IDENTITY_COLLECTION_STARTED,
                        details={
                            **self._opaque_policy_details(),
                            "identity_role": OpaqueIdentityRole.PAGE_CHANGE.value,
                        },
                    )
                )
            events.append(
                self._pending_event(
                    VideoEventType.WAITING_FOR_PAGE_CHANGE,
                    details={
                        "sample_interval_ms": self.page_change_policy.sample_interval_ms,
                        "stable_sample_count": self.page_change_policy.stable_sample_count,
                        "validated": self.page_change_policy.validated,
                    },
                )
            )
            self._pending_artifact = None
            self._pending_identity = None
            self._pending_preview = None
            self._pending_page_number = None
            return tuple(events)

    def delivery_rejected(
        self,
        artifact_id: ArtifactId,
        reason: str,
    ) -> tuple[VideoEvent, ...]:
        """Release pending ownership and permit a better local recapture."""

        with self._lock:
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("reason must be non-empty")
            if not self._is_current_pending(artifact_id):
                return ()
            if not self.identity_ledger.reject_or_release(artifact_id):
                return ()
            assert self._pending_artifact is not None
            events: list[VideoEvent] = []
            opaque_released = bool(
                self._opaque_identity_active
                and self.opaque_identity_ledger is not None
                and self.opaque_identity_ledger.reject_or_release(artifact_id)
            )
            self._transition(VideoSessionState.PARSER_REJECTED, events)
            events.append(
                self._pending_event(
                    VideoEventType.PARSER_REJECTED,
                    reason=ReadinessReason.PARSER_QUALITY_REJECTED,
                    details={"reason": reason},
                )
            )
            if opaque_released:
                events.append(
                    self._pending_event(
                        VideoEventType.OPAQUE_IDENTITY_BANK_DISCARDED,
                        details={"reason": "parser_rejected", **self._opaque_policy_details()},
                    )
                )
            self._pending_artifact = None
            self._pending_identity = None
            self._pending_preview = None
            self._pending_page_number = None
            self.page_change_gate.reset()
            self.page_number_change_tracker.reset()
            self.page_number_scheduler.reset()
            self._page_change_key = None
            self._page_change_baseline_preview = None
            self._window.clear()
            self._retry_until = self.clock.monotonic()
            self._transition(
                VideoSessionState.LOCAL_RETRY,
                events,
                reason=ReadinessReason.PARSER_QUALITY_REJECTED,
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
            self._discard_processing_job()
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
            self._discard_processing_job()
            self._complete_local_retry(decision.reasons[0], events, decision.retry_after_ms)
            return
        if decision.state is PreparationState.PREPARED and decision.prepared is not None:
            if (
                self._active_job_id != decision.prepared.job_id
                or decision.prepared.session_id != self.session_id
            ):
                self._discard_prepared(decision)
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
            identity_started = self.clock.monotonic()
            try:
                identity = self.identity_provider.fingerprint_artifact(artifact)
                preview = self.identity_provider.fingerprint_preview(
                    self._selected.gray_preview,
                    self._selected.mask_preview,
                    self._selected.seam_proxy_fraction,
                )
            except (IdentityFingerprintError, OSError, ValueError, TypeError):
                self._fail(ReadinessReason.IDENTITY_FAILED, events)
                return
            self._identity_latency_ms = max(
                0.0,
                (self.clock.monotonic() - identity_started) * 1000.0,
            )
            match = self.identity_ledger.find_match(identity)
            page_observation: SpreadPageNumberObservation | None = None
            page_relation = PageKeyRelation.UNAVAILABLE
            page_match_entry = None
            if self.page_number_provider is not None and not self._opaque_identity_active:
                try:
                    page_observation = self.page_number_provider.observe_artifact(
                        artifact,
                        self.data_pack_id,
                    )
                    self._page_number_latency_ms = page_observation.processing_ms
                    events.extend(self._page_number_events(page_observation, artifact))
                    page_relation, page_match_entry = self.page_key_ledger.relation(page_observation.key)
                except (OSError, RuntimeError, ValueError, TypeError):
                    events.append(
                        self._event(
                            VideoEventType.PAGE_NUMBER_OBSERVED,
                            source_frame_id=selected_frame_id,
                            spread_id=self._selected_spread,
                            artifact_id=artifact.artifact_id,
                            reason=ReadinessReason.PAGE_NUMBER_FAILED,
                            details={"status": "provider_error", "fallback": "visual_identity"},
                        )
                    )
            events.append(
                self._event(
                    VideoEventType.SPREAD_IDENTITY_CREATED,
                    source_frame_id=selected_frame_id,
                    spread_id=self._selected_spread,
                    artifact_id=artifact.artifact_id,
                    details=self._identity_details(identity, match),
                )
            )
            visual_duplicate = match.comparison.kind in {
                IdentityMatchKind.EXACT_DUPLICATE,
                IdentityMatchKind.VISUAL_DUPLICATE,
            }
            identity_conflict = (
                page_relation is PageKeyRelation.SAME
                and match.comparison.kind is IdentityMatchKind.NEW_SPREAD
            ) or (
                page_relation is PageKeyRelation.DIFFERENT
                and visual_duplicate
            )
            if (
                self._opaque_identity_active
                and match.comparison.kind is IdentityMatchKind.VISUAL_DUPLICATE
            ):
                identity_conflict = True
            if identity_conflict:
                self._page_number_conflicts += 1
                events.append(
                    self._event(
                        VideoEventType.PAGE_NUMBER_IDENTITY_CONFLICT,
                        source_frame_id=selected_frame_id,
                        spread_id=self._selected_spread,
                        artifact_id=artifact.artifact_id,
                        reason=ReadinessReason.PAGE_NUMBER_FAILED,
                        details={
                            "page_key_relation": page_relation.value,
                            "visual_match_kind": match.comparison.kind.value,
                            "automatic_decision": False,
                        },
                    )
                )
                self._complete_local_retry(ReadinessReason.PAGE_NUMBER_FAILED, events)
                return
            number_only_duplicate = (
                page_relation is PageKeyRelation.SAME
                and match.comparison.kind is IdentityMatchKind.AMBIGUOUS
                and self.page_number_policy.allow_number_only_duplicate
            )
            suppress_visual_duplicate = (
                match.comparison.kind is IdentityMatchKind.EXACT_DUPLICATE
                or (not self._opaque_identity_active and visual_duplicate)
            )
            if suppress_visual_duplicate or number_only_duplicate:
                target_artifact = (
                    match.entry.artifact_id if match.entry is not None else artifact.artifact_id
                )
                if self._opaque_identity_active:
                    assert self.opaque_identity_ledger is not None
                    matched_bank = self.opaque_identity_ledger.find(target_artifact)
                    if matched_bank is None:
                        self._complete_local_retry(
                            ReadinessReason.FOOTER_IDENTITY_UNAVAILABLE,
                            events,
                        )
                        return
                    assert self.opaque_identity_policy is not None
                    self._opaque_waiting_reference = matched_bank
                    self._opaque_collector = OpaqueQueryCollector(
                        self.opaque_identity_policy,
                        (matched_bank,),
                        started_at=self.clock.monotonic(),
                    )
                    self._next_opaque_sample_at = self.clock.monotonic()
                self._duplicates_suppressed += 1
                details = self._identity_details(identity, match)
                details["page_key_relation"] = page_relation.value
                details["number_only_duplicate"] = number_only_duplicate
                events.append(
                    self._event(
                        VideoEventType.DUPLICATE_SUPPRESSED,
                        source_frame_id=selected_frame_id,
                        spread_id=self._selected_spread,
                        artifact_id=artifact.artifact_id,
                        details=details,
                    )
                )
                self._window.clear()
                self.page_change_gate.arm(preview)
                self._page_change_baseline_preview = preview
                self._page_change_key = (
                    page_match_entry.key
                    if page_match_entry is not None
                    else (page_observation.key if page_observation is not None else None)
                )
                self.page_number_change_tracker.arm(self._page_change_key)
                self._next_page_change_sample_at = self.clock.monotonic()
                self._clear_processing()
                self._transition(VideoSessionState.WAITING_FOR_PAGE_CHANGE, events)
                events.append(
                    self._event(
                        VideoEventType.WAITING_FOR_PAGE_CHANGE,
                        source_frame_id=selected_frame_id,
                        spread_id=artifact.spread_id,
                        artifact_id=target_artifact,
                        details={"duplicate_suppressed": True},
                    )
                )
                return
            if (
                not self._opaque_identity_active
                and
                match.comparison.kind is IdentityMatchKind.AMBIGUOUS
                and page_relation is not PageKeyRelation.DIFFERENT
            ):
                self._identity_ambiguous += 1
                events.append(
                    self._event(
                        VideoEventType.IDENTITY_AMBIGUOUS,
                        source_frame_id=selected_frame_id,
                        spread_id=self._selected_spread,
                        artifact_id=artifact.artifact_id,
                        details=self._identity_details(identity, match),
                    )
                )
                self._complete_local_retry(ReadinessReason.IDENTITY_FAILED, events)
                return
            try:
                self.identity_ledger.register_pending(identity, artifact.artifact_id)
            except RuntimeError:
                self._fail(ReadinessReason.IDENTITY_FAILED, events)
                return
            if self._opaque_identity_active:
                assert self.opaque_identity_ledger is not None
                try:
                    self.opaque_identity_ledger.register_pending(
                        artifact.artifact_id,
                        self._opaque_candidate_pairs,
                    )
                except (RuntimeError, ValueError):
                    self.identity_ledger.reject_or_release(artifact.artifact_id)
                    self._fail(ReadinessReason.IDENTITY_FAILED, events)
                    return
            self._pending_artifact = artifact
            self._pending_identity = identity
            self._pending_preview = preview
            self._pending_page_number = page_observation
            events.append(
                self._event(
                    VideoEventType.ARTIFACT_READY,
                    source_frame_id=selected_frame_id,
                    spread_id=self._selected_spread,
                    artifact_id=artifact.artifact_id,
                )
            )
            if self._opaque_identity_active:
                events.append(
                    self._pending_event(
                        VideoEventType.OPAQUE_IDENTITY_BANK_PENDING,
                        details={
                            "reference_bank_depth": len(self._opaque_candidate_pairs),
                            **self._opaque_policy_details(),
                        },
                    )
                )
                self._opaque_candidate_pairs = ()
            self._clear_processing()
            self._transition(VideoSessionState.READY_FOR_SERVER_PREFLIGHT, events)
            return
        reason = decision.reasons[0] if decision.reasons else ReadinessReason.FRAME_DECODE_FAILED
        self._discard_processing_job()
        self._fail(reason, events)

    def _poll_page_change(self, events: list[VideoEvent]) -> None:
        now = self.clock.monotonic()
        if now < self._next_page_change_sample_at:
            return
        self._next_page_change_sample_at = now + self.page_change_policy.sample_interval_ms / 1000.0
        try:
            frame = self.camera.read()
        except FrameDecodeError:
            self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
            return
        except CameraUnavailableError:
            self._fail(ReadinessReason.CAMERA_UNAVAILABLE, events)
            return
        except Exception:
            self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
            return
        if frame is None:
            if self.camera.exhausted:
                events.append(self._event(VideoEventType.SOURCE_EXHAUSTED))
                self._stop_camera()
                self.page_change_gate.reset()
                self.page_number_change_tracker.reset()
                self.page_number_scheduler.reset()
                self._page_change_key = None
                self._page_change_baseline_preview = None
                self._transition(VideoSessionState.IDLE, events)
            return

        self._frames_received += 1
        self._waiting_preview_frames += 1
        try:
            observation = self.analyzer.analyze(frame)
        except Exception:
            self._fail(ReadinessReason.FRAME_DECODE_FAILED, events)
            return
        self._frames_evaluated += 1
        self._publish_preview_diagnostics(observation)
        reasons = set(observation.candidate.retry_reasons)
        motion_observed = bool(
            reasons
            & {
                ReadinessReason.PAGE_MOVING,
                ReadinessReason.HAND_OR_PAGE_TURN,
            }
        )
        eligible = not reasons
        preview: SpreadVisualFingerprint | None = None
        if eligible:
            try:
                preview = self.identity_provider.fingerprint_preview(
                    observation.gray_preview,
                    observation.mask_preview,
                    observation.seam_proxy_fraction,
                )
            except (IdentityFingerprintError, OSError, ValueError, TypeError):
                eligible = False
        decision = self.page_change_gate.observe(
            preview,
            eligible=eligible,
            motion_observed=motion_observed,
        )
        number_decision = None
        number_observation: SpreadPageNumberObservation | None = None
        schedule_decision = None
        if self.page_number_provider is not None:
            schedule_decision = self.page_number_scheduler.observe(
                eligible=eligible,
                visual_match_kind=(
                    decision.comparison.kind if decision.comparison is not None else None
                ),
                visual_stable_count=decision.stable_count,
            )
            events.append(
                self._event(
                    VideoEventType.PAGE_NUMBER_VERIFICATION_DECISION,
                    source_frame_id=frame.frame_id,
                    details={
                        "requested": schedule_decision.requested,
                        "reason": schedule_decision.reason.value,
                        "mode": self.page_number_scheduler_policy.mode.value,
                        "burst_active": schedule_decision.burst_active,
                        "burst_sample_count": schedule_decision.burst_sample_count,
                        "audit_counter": schedule_decision.audit_counter,
                    },
                )
            )
        if (
            self.page_number_provider is not None
            and schedule_decision is not None
            and schedule_decision.requested
        ):
            try:
                number_gray, number_mask = _page_number_preview_inputs(
                    frame.payload,
                    observation.mask_preview,
                    self.page_number_policy.preview_max_dimension,
                )
                number_observation = self.page_number_provider.observe_preview(
                    number_gray,
                    number_mask,
                    observation.seam_proxy_fraction,
                    frame.frame_id,
                    self.data_pack_id,
                )
                self._page_number_latency_ms = number_observation.processing_ms
                events.extend(self._page_number_events(number_observation, None))
                number_decision = self.page_number_change_tracker.observe(
                    number_observation.key,
                    eligible=True,
                )
                events.append(
                    self._event(
                        VideoEventType.PAGE_CHANGE_NUMBER_EVIDENCE,
                        source_frame_id=frame.frame_id,
                        details={
                            "status": number_observation.status.value,
                            "relation": number_decision.relation.value,
                            "stable_count": number_decision.stable_count,
                            "changed": number_decision.changed,
                            "left_page_label": (
                                number_observation.key.left_page_label
                                if number_observation.key is not None
                                else None
                            ),
                            "right_page_label": (
                                number_observation.key.right_page_label
                                if number_observation.key is not None
                                else None
                            ),
                            "processing_ms": number_observation.processing_ms,
                        },
                    )
                )
            except (OSError, RuntimeError, ValueError, TypeError):
                self.page_number_change_tracker.observe(None, eligible=False)
                events.append(
                    self._event(
                        VideoEventType.PAGE_CHANGE_NUMBER_EVIDENCE,
                        source_frame_id=frame.frame_id,
                        reason=ReadinessReason.PAGE_NUMBER_FAILED,
                        details={"status": "provider_error", "fallback": "visual_identity"},
                    )
                )
        elif self.page_number_provider is not None:
            self.page_number_change_tracker.observe(None, eligible=False)
        events.append(
            self._event(
                VideoEventType.PAGE_CHANGE_OBSERVED,
                source_frame_id=frame.frame_id,
                reason=(
                    observation.candidate.retry_reasons[0]
                    if observation.candidate.retry_reasons
                    else None
                ),
                details={
                    "eligible": decision.eligible,
                    "stable_count": decision.stable_count,
                    "motion_seen": decision.motion_seen,
                    "match_kind": (
                        decision.comparison.kind.value if decision.comparison is not None else None
                    ),
                },
            )
        )
        changed = decision.changed
        if number_decision is not None:
            if number_decision.relation is PageKeyRelation.SAME:
                changed = False
                if self._page_change_baseline_preview is not None:
                    self.page_change_gate.arm(self._page_change_baseline_preview)
            elif number_decision.relation is PageKeyRelation.DIFFERENT:
                visual_kind = (
                    decision.comparison.kind if decision.comparison is not None else None
                )
                if visual_kind in {
                    IdentityMatchKind.EXACT_DUPLICATE,
                    IdentityMatchKind.VISUAL_DUPLICATE,
                }:
                    changed = False
                    if number_decision.changed:
                        self._page_number_conflicts += 1
                        events.append(
                            self._event(
                                VideoEventType.PAGE_CHANGE_NUMBER_EVIDENCE,
                                source_frame_id=frame.frame_id,
                                reason=ReadinessReason.PAGE_NUMBER_FAILED,
                                details={
                                    "status": "identity_conflict",
                                    "relation": number_decision.relation.value,
                                    "visual_match_kind": visual_kind.value,
                                    "automatic_decision": False,
                                },
                            )
                        )
                else:
                    changed = number_decision.changed
        if not changed:
            return
        self._page_changes += 1
        self._window.clear()
        self.page_change_gate.reset()
        self.page_number_change_tracker.reset()
        self.page_number_scheduler.reset()
        self._page_change_key = None
        self._page_change_baseline_preview = None
        self.guidance.reset()
        events.append(
            self._event(
                VideoEventType.PAGE_CHANGED,
                source_frame_id=frame.frame_id,
                details={
                    "stable_count": decision.stable_count,
                    "motion_seen": decision.motion_seen,
                    "match_kind": (
                        decision.comparison.kind.value if decision.comparison is not None else None
                    ),
                    "number_relation": (
                        number_decision.relation.value if number_decision is not None else None
                    ),
                },
            )
        )
        self._transition(VideoSessionState.SEARCHING, events)
        self._next_sample_at = now + self.policy.sample_interval_ms / 1000.0

    def _complete_local_retry(
        self,
        reason: ReadinessReason,
        events: list[VideoEvent],
        retry_after_ms: int | None = None,
    ) -> None:
        self._window.clear()
        self._opaque_collector = None
        self._opaque_candidate_pairs = ()
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
        self._emit_pending_opaque_discard("session_cancelled", events)
        self._release_pending()
        self._pending_preview = None
        self._pending_page_number = None
        self.page_change_gate.reset()
        self.page_number_change_tracker.reset()
        self.page_number_scheduler.reset()
        self._page_change_key = None
        self._page_change_baseline_preview = None
        self._opaque_collector = None
        self._opaque_candidate_pairs = ()
        self._opaque_waiting_reference = None
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
        self._emit_pending_opaque_discard(f"session_error:{reason.value}", events)
        self._release_pending()
        self._pending_preview = None
        self._pending_page_number = None
        self.page_change_gate.reset()
        self.page_number_change_tracker.reset()
        self.page_number_scheduler.reset()
        self._page_change_key = None
        self._page_change_baseline_preview = None
        self._opaque_collector = None
        self._opaque_candidate_pairs = ()
        self._opaque_waiting_reference = None
        self._clear_processing()
        self._transition(VideoSessionState.ERROR, events, reason=reason)
        events.append(self._event(VideoEventType.SESSION_ERROR, reason=reason))

    def _publish_preview_diagnostics(
        self,
        observation: CandidateObservation,
        *,
        primary_reason: ReadinessReason | None = None,
    ) -> None:
        update = getattr(self.camera, "update_diagnostics", None)
        if not callable(update):
            return
        try:
            update(
                observation,
                primary_reason=primary_reason,
                state=self.state.value,
            )
        except Exception:
            # Operator diagnostics must never affect capture acceptance.
            return

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

    def _is_current_pending(self, artifact_id: ArtifactId) -> bool:
        return bool(
            isinstance(artifact_id, ArtifactId)
            and self._pending_artifact is not None
            and self._pending_artifact.artifact_id == artifact_id
            and self.identity_ledger.pending is not None
            and self.identity_ledger.pending.artifact_id == artifact_id
        )

    def _release_pending(self) -> None:
        if self._pending_artifact is not None:
            self.identity_ledger.reject_or_release(self._pending_artifact.artifact_id)
            if self.opaque_identity_ledger is not None:
                self.opaque_identity_ledger.reject_or_release(self._pending_artifact.artifact_id)
        self._pending_artifact = None
        self._pending_identity = None
        self._pending_page_number = None

    def _emit_pending_opaque_discard(
        self,
        reason: str,
        events: list[VideoEvent],
    ) -> None:
        if (
            not self._opaque_identity_active
            or self._pending_artifact is None
            or self.opaque_identity_ledger is None
            or self.opaque_identity_ledger.pending_artifact_id
            != self._pending_artifact.artifact_id
        ):
            return
        events.append(
            self._pending_event(
                VideoEventType.OPAQUE_IDENTITY_BANK_DISCARDED,
                details={"reason": reason, **self._opaque_policy_details()},
            )
        )

    def _pending_event(
        self,
        event_type: VideoEventType,
        *,
        reason: ReadinessReason | None = None,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> VideoEvent:
        assert self._pending_artifact is not None
        return self._event(
            event_type,
            source_frame_id=self._pending_artifact.source_frame_id,
            spread_id=self._pending_artifact.spread_id,
            artifact_id=self._pending_artifact.artifact_id,
            reason=reason,
            details=details or {},
        )

    def _page_number_events(
        self,
        observation: SpreadPageNumberObservation,
        artifact: SpreadArtifactRef | None,
    ) -> list[VideoEvent]:
        events: list[VideoEvent] = []
        spread_id = artifact.spread_id if artifact is not None else None
        artifact_id = artifact.artifact_id if artifact is not None else None
        for side_observation in (observation.left, observation.right):
            bbox = side_observation.bbox
            events.append(
                self._event(
                    VideoEventType.PAGE_NUMBER_OBSERVED,
                    source_frame_id=side_observation.source_frame_id,
                    spread_id=spread_id,
                    artifact_id=artifact_id,
                    details={
                        "side": side_observation.side.value,
                        "raw_text": side_observation.raw_text,
                        "normalized_label": side_observation.normalized_label,
                        "confidence": side_observation.confidence,
                        "bbox_x": bbox[0] if bbox is not None else None,
                        "bbox_y": bbox[1] if bbox is not None else None,
                        "bbox_width": bbox[2] if bbox is not None else None,
                        "bbox_height": bbox[3] if bbox is not None else None,
                        "source_kind": side_observation.source_kind.value,
                        "status": side_observation.status.value,
                        "engine_id": side_observation.engine_id,
                        "engine_version": side_observation.engine_version,
                        "preprocessing_version": side_observation.preprocessing_version,
                        "variant_agreement": side_observation.variant_agreement,
                        "cache_hit": side_observation.cache_hit,
                    },
                )
            )
        if observation.key is not None and artifact is not None:
            events.append(
                self._event(
                    VideoEventType.SPREAD_PAGE_KEY_CREATED,
                    source_frame_id=observation.left.source_frame_id,
                    spread_id=artifact.spread_id,
                    artifact_id=artifact.artifact_id,
                    details={
                        "data_pack_id": observation.key.data_pack_id,
                        "left_page_label": observation.key.left_page_label,
                        "right_page_label": observation.key.right_page_label,
                        "recognizer_version": observation.key.recognizer_version,
                        "schema_version": observation.key.schema_version,
                        "validated": self.page_number_policy.validated,
                    },
                )
            )
        return events

    @staticmethod
    def _identity_details(identity: SpreadIdentity, match: LedgerMatch) -> dict[str, str | int | float | bool | None]:
        comparison = match.comparison
        return {
            "algorithm_version": identity.algorithm_version,
            "match_kind": comparison.kind.value,
            "compatible": comparison.compatible,
            "left_hamming": comparison.left_hamming,
            "right_hamming": comparison.right_hamming,
            "left_projection_mae": comparison.left_projection_mae,
            "right_projection_mae": comparison.right_projection_mae,
            "left_feature_match": comparison.left_feature_match,
            "right_feature_match": comparison.right_feature_match,
            "left_agrees": comparison.left_agrees,
            "right_agrees": comparison.right_agrees,
            "matched_artifact_id": match.entry.artifact_id.value if match.entry else None,
            "matched_status": match.entry.status.value if match.entry else None,
            "matched_receipt_id": match.entry.receipt_id if match.entry else None,
            "validated": False,
        }


def _page_number_preview_inputs(
    frame: np.ndarray,
    mask_preview: np.ndarray,
    max_dimension: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Project the cheap page mask onto a footer-readable grayscale frame."""

    if not isinstance(frame, np.ndarray) or frame.size == 0:
        raise ValueError("page-number preview frame must be a non-empty ndarray")
    if frame.ndim == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    elif frame.ndim == 2:
        gray = frame
    else:
        raise ValueError("page-number preview frame must be grayscale or BGR")
    height, width = gray.shape
    scale = min(1.0, max_dimension / max(height, width))
    target_width = max(1, round(width * scale))
    target_height = max(1, round(height * scale))
    if (target_width, target_height) != (width, height):
        gray = cv2.resize(gray, (target_width, target_height), interpolation=cv2.INTER_AREA)
    if not isinstance(mask_preview, np.ndarray) or mask_preview.ndim != 2 or mask_preview.size == 0:
        raise ValueError("page-number preview mask must be a non-empty 2D ndarray")
    mask = cv2.resize(
        mask_preview,
        (target_width, target_height),
        interpolation=cv2.INTER_NEAREST,
    )
    return gray, mask
