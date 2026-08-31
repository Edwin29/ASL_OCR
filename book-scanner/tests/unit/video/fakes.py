"""Deterministic V0 test doubles; never selected as production backends."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
import hashlib
from dataclasses import dataclass
from typing import Generic, TypeVar

from book_scanner.video.events import GuidanceRequest
from book_scanner.video.identity import (
    PageIdentity,
    SpreadIdentity,
    SpreadVisualFingerprint,
    VisualFingerprint,
)
from book_scanner.video.protocols import ButtonCommand, FrameSample
from book_scanner.video.types import (
    ArtifactId,
    FrameId,
    PageArtifactRef,
    PageSide,
    PreparationDecision,
    PreparedPageArtifact,
    PreparedSpreadArtifact,
    ProcessingJobId,
    ReadinessDecision,
    ReadinessReason,
    ReadinessState,
    SpreadArtifactRef,
    SpreadId,
)

PayloadT = TypeVar("PayloadT")


class FakeCameraSource(Generic[PayloadT]):
    def __init__(self, frames: Iterable[FrameSample[PayloadT]]):
        self._frames = list(frames)
        self._index = 0
        self.started = False
        self.stopped = False

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self._frames)

    def start(self) -> None:
        if self.stopped:
            raise RuntimeError("a stopped fake camera cannot be restarted")
        self.started = True

    def read(self) -> FrameSample[PayloadT] | None:
        if not self.started or self.stopped or self._index >= len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        return frame

    def stop(self) -> None:
        self.stopped = True


class FakeButtonSource:
    def __init__(self, commands: Iterable[ButtonCommand]):
        self._commands = tuple(commands)

    def events(self) -> Iterator[ButtonCommand]:
        return iter(self._commands)


class FakeGuidanceSink:
    def __init__(self) -> None:
        self.requests: list[GuidanceRequest] = []

    def emit(self, request: GuidanceRequest) -> None:
        self.requests.append(request)


class FakeSpreadProcessor(Generic[PayloadT]):
    def __init__(self, result_factory: Callable[[FrameSample[PayloadT], SpreadId], ReadinessDecision]):
        self._result_factory = result_factory
        self.calls: list[tuple[FrameSample[PayloadT], SpreadId]] = []

    def process(self, frame: FrameSample[PayloadT], spread_id: SpreadId) -> ReadinessDecision:
        self.calls.append((frame, spread_id))
        return self._result_factory(frame, spread_id)


class FakeSpreadPreparer(Generic[PayloadT]):
    def __init__(
        self,
        result_factory: Callable[
            [FrameSample[PayloadT], SpreadId, ProcessingJobId, str], PreparationDecision
        ],
    ):
        self._result_factory = result_factory
        self.calls: list[tuple[FrameSample[PayloadT], SpreadId, ProcessingJobId, str]] = []

    def prepare(
        self,
        frame: FrameSample[PayloadT],
        spread_id: SpreadId,
        job_id: ProcessingJobId,
        session_id: str,
    ) -> PreparationDecision:
        self.calls.append((frame, spread_id, job_id, session_id))
        return self._result_factory(frame, spread_id, job_id, session_id)


class FakeArtifactStore:
    def __init__(self) -> None:
        self.commits: list[PreparedSpreadArtifact] = []
        self.discards: list[PreparedSpreadArtifact] = []
        self.discarded_jobs: list[ProcessingJobId] = []

    def commit(self, prepared: PreparedSpreadArtifact) -> SpreadArtifactRef:
        self.commits.append(prepared)
        return make_artifact(
            prepared.source_frame_id.value,
            artifact_name=prepared.artifact_id.value,
            spread=prepared.spread_id.value,
        )

    def discard(self, prepared: PreparedSpreadArtifact) -> None:
        self.discards.append(prepared)

    def discard_job(self, job_id: ProcessingJobId) -> None:
        self.discarded_jobs.append(job_id)


class FakeIdentityProvider:
    def __init__(
        self,
        artifact_tokens: dict[str, int] | None = None,
        preview_tokens: Iterable[int] = (),
    ) -> None:
        self.artifact_tokens = artifact_tokens or {}
        self.preview_tokens = list(preview_tokens)
        self.artifact_calls: list[ArtifactId] = []
        self.preview_calls = 0

    def fingerprint_artifact(self, artifact: SpreadArtifactRef) -> SpreadIdentity:
        self.artifact_calls.append(artifact.artifact_id)
        token = self.artifact_tokens.get(artifact.artifact_id.value, 0)
        source_sha = hashlib.sha256(f"source-{token}".encode()).hexdigest()
        return SpreadIdentity(
            "page-identity-v3a-1",
            source_sha,
            hashlib.sha256(f"manifest-{token}".encode()).hexdigest(),
            PageIdentity(
                PageSide.LEFT,
                hashlib.sha256(f"corrected-left-{token}".encode()).hexdigest(),
                hashlib.sha256(f"crop-left-{token}".encode()).hexdigest(),
                source_sha,
                artifact.left.width,
                artifact.left.height,
                "fake-extractor-v1",
                "fake-correction-v1",
                _visual(token),
            ),
            PageIdentity(
                PageSide.RIGHT,
                hashlib.sha256(f"corrected-right-{token}".encode()).hexdigest(),
                hashlib.sha256(f"crop-right-{token}".encode()).hexdigest(),
                source_sha,
                artifact.right.width,
                artifact.right.height,
                "fake-extractor-v1",
                "fake-correction-v1",
                _visual(token + 100),
            ),
        )

    def fingerprint_preview(self, _gray: object, _mask: object, _seam: float | None) -> SpreadVisualFingerprint:
        self.preview_calls += 1
        token = self.preview_tokens.pop(0) if self.preview_tokens else 0
        return SpreadVisualFingerprint("page-identity-v3a-1", _visual(token), _visual(token + 100))


@dataclass(frozen=True, slots=True)
class ParserResponseSpec:
    state: ReadinessState
    reasons: tuple[ReadinessReason, ...] = ()
    retry_after_ms: int | None = None
    delivery_receipt_id: str | None = None


class FakeParserClient:
    def __init__(self, responses: Iterable[ParserResponseSpec], evaluator_version: str = "fake-parser-v1"):
        self._responses = list(responses)
        self._evaluator_version = evaluator_version
        self._cache: dict[str, tuple[SpreadArtifactRef, ReadinessDecision]] = {}
        self.calls: list[tuple[SpreadArtifactRef, str]] = []

    def preflight_and_submit(self, artifact: SpreadArtifactRef, idempotency_key: str) -> ReadinessDecision:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty")
        self.calls.append((artifact, idempotency_key))
        cached = self._cache.get(idempotency_key)
        if cached is not None:
            cached_artifact, cached_decision = cached
            if cached_artifact != artifact:
                raise ValueError("idempotency_key was already used for a different artifact")
            return cached_decision
        if not self._responses:
            raise RuntimeError("no fake parser response remains")
        spec = self._responses.pop(0)
        decision = ReadinessDecision(
            state=spec.state,
            evaluator_version=self._evaluator_version,
            reasons=spec.reasons,
            source_frame_id=artifact.source_frame_id,
            spread_id=artifact.spread_id,
            artifact=artifact,
            retry_after_ms=spec.retry_after_ms,
            delivery_receipt_id=spec.delivery_receipt_id,
        )
        self._cache[idempotency_key] = (artifact, decision)
        return decision


class ManualClock:
    def __init__(self, initial: float = 0.0):
        if initial < 0:
            raise ValueError("initial time must be non-negative")
        self._now = float(initial)

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> float:
        if seconds < 0:
            raise ValueError("seconds must be non-negative")
        self._now += seconds
        return self._now


def make_artifact(
    frame: str = "frame-1",
    artifact_name: str = "artifact-1",
    spread: str = "spread-1",
) -> SpreadArtifactRef:
    frame_id = FrameId(frame)
    return SpreadArtifactRef(
        artifact_id=ArtifactId(artifact_name),
        spread_id=SpreadId(spread),
        source_frame_id=frame_id,
        left=PageArtifactRef(PageSide.LEFT, frame_id, "left.jpg", "a" * 64, 100, 200),
        right=PageArtifactRef(PageSide.RIGHT, frame_id, "right.jpg", "b" * 64, 100, 200),
        manifest_path="manifest.json",
        manifest_sha256="c" * 64,
        evaluator_version="artifact-evaluator-v1",
    )


def make_prepared(
    frame: str = "frame-1",
    artifact_name: str = "artifact-1",
    spread: str = "spread-1",
    job: str = "job-1",
    staging_path: str = "staging/artifact-1",
    session: str = "test-session",
) -> PreparedSpreadArtifact:
    frame_id = FrameId(frame)
    return PreparedSpreadArtifact(
        artifact_id=ArtifactId(artifact_name),
        session_id=session,
        job_id=ProcessingJobId(job),
        spread_id=SpreadId(spread),
        source_frame_id=frame_id,
        staging_path=staging_path,
        manifest_relative_path="manifest.json",
        manifest_sha256="c" * 64,
        left=PreparedPageArtifact(PageSide.LEFT, frame_id, "left/uvdoc.jpg", "a" * 64, 100, 200),
        right=PreparedPageArtifact(PageSide.RIGHT, frame_id, "right/uvdoc.jpg", "b" * 64, 100, 200),
        evaluator_version="prepared-evaluator-v1",
    )


def _visual(token: int) -> VisualFingerprint:
    digest = hashlib.sha256(f"visual-{token}".encode()).hexdigest()[:16]
    level = 30 if token == 0 or token == 100 else 220
    return VisualFingerprint(
        "page-identity-v3a-1",
        digest,
        (level,) * 16,
        (level,) * 16,
        256,
        384,
    )
