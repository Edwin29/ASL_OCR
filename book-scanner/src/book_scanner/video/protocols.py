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
from .types import (
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


class ParserClient(Protocol):
    def preflight_and_submit(self, artifact: SpreadArtifactRef, idempotency_key: str) -> ReadinessDecision: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...
