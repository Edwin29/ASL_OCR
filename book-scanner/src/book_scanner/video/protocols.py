"""Dependency-inversion boundaries for the future video runtime.

This module deliberately imports no OpenCV, Picamera2, GPIO, TTS, or HTTP
implementation.  V1+ adapters implement these protocols.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Generic, Iterator, Protocol, TypeVar

from .events import GuidanceRequest
from .identity import LedgerEntry, LedgerMatch, SpreadIdentity, SpreadVisualFingerprint
from .page_change import PageChangeDecision
from .page_number import PageNumberRecognition, SpreadPageNumberObservation
from .types import (
    ArtifactId,
    FrameCandidate,
    FrameId,
    PreparationDecision,
    PreparedSpreadArtifact,
    ProcessingJobId,
    ReadinessDecision,
    SpreadArtifactRef,
    SpreadId,
)

FramePayloadT = TypeVar("FramePayloadT")
FramePayloadT_co = TypeVar("FramePayloadT_co", covariant=True)


@dataclass(frozen=True, slots=True)
class FrameSample(Generic[FramePayloadT]):
    frame_id: FrameId
    captured_at_monotonic: float
    payload: FramePayloadT

    def __post_init__(self) -> None:
        if not isinstance(self.frame_id, FrameId):
            raise TypeError("frame_id must be a FrameId")
        if (
            isinstance(self.captured_at_monotonic, bool)
            or not isinstance(self.captured_at_monotonic, (int, float))
            or not math.isfinite(self.captured_at_monotonic)
            or self.captured_at_monotonic < 0
        ):
            raise ValueError("captured_at_monotonic must be finite and non-negative")


class ButtonCommand(str, Enum):
    START = "start"
    CANCEL = "cancel"


class CameraSource(Protocol[FramePayloadT_co]):
    @property
    def exhausted(self) -> bool: ...

    def start(self) -> None: ...

    def read(self) -> FrameSample[FramePayloadT_co] | None: ...

    def stop(self) -> None: ...


class ButtonSource(Protocol):
    def events(self) -> Iterator[ButtonCommand]: ...


class GuidanceSink(Protocol):
    def emit(self, request: GuidanceRequest) -> None: ...


class CandidateEvaluator(Protocol[FramePayloadT]):
    def evaluate(self, frame: FrameSample[FramePayloadT]) -> FrameCandidate: ...


class SpreadProcessor(Protocol[FramePayloadT]):
    def process(self, frame: FrameSample[FramePayloadT], spread_id: SpreadId) -> ReadinessDecision: ...


class SpreadPreparer(Protocol[FramePayloadT]):
    def prepare(
        self,
        frame: FrameSample[FramePayloadT],
        spread_id: SpreadId,
        job_id: ProcessingJobId,
        session_id: str,
    ) -> PreparationDecision: ...


class ArtifactStore(Protocol):
    def commit(self, prepared: PreparedSpreadArtifact) -> SpreadArtifactRef: ...

    def discard(self, prepared: PreparedSpreadArtifact) -> None: ...

    def discard_job(self, job_id: ProcessingJobId) -> None: ...


class SpreadIdentityProvider(Protocol):
    def fingerprint_artifact(self, artifact: SpreadArtifactRef) -> SpreadIdentity: ...

    def fingerprint_preview(
        self,
        gray_preview: object,
        mask_preview: object,
        seam_fraction: float | None,
    ) -> SpreadVisualFingerprint: ...


class PageIdentityLedger(Protocol):
    @property
    def pending(self) -> LedgerEntry | None: ...

    def register_pending(self, identity: SpreadIdentity, artifact_id: ArtifactId) -> LedgerEntry: ...

    def find_match(self, identity: SpreadIdentity) -> LedgerMatch: ...

    def confirm(self, artifact_id: ArtifactId, receipt_id: str) -> bool: ...

    def reject_or_release(self, artifact_id: ArtifactId) -> bool: ...

    def recent_accepted(self) -> tuple[LedgerEntry, ...]: ...


class PageChangeGate(Protocol):
    def arm(self, baseline: SpreadVisualFingerprint) -> None: ...

    def reset(self) -> None: ...

    def observe(
        self,
        fingerprint: SpreadVisualFingerprint | None,
        *,
        eligible: bool,
        motion_observed: bool = False,
    ) -> PageChangeDecision: ...


class PageNumberRecognizer(Protocol):
    engine_id: str
    engine_version: str
    preprocessing_version: str

    def recognize(self, roi: object, side: object) -> PageNumberRecognition: ...


class PageNumberProvider(Protocol):
    def observe_artifact(
        self,
        artifact: SpreadArtifactRef,
        data_pack_id: str,
    ) -> SpreadPageNumberObservation: ...

    def observe_preview(
        self,
        gray_preview: object,
        mask_preview: object,
        seam_fraction: float | None,
        source_frame_id: FrameId,
        data_pack_id: str,
    ) -> SpreadPageNumberObservation: ...


class ParserClient(Protocol):
    def preflight_and_submit(self, artifact: SpreadArtifactRef, idempotency_key: str) -> ReadinessDecision: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...
