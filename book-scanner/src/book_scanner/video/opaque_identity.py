"""M1 opaque footer token banks and ACK-scoped lifecycle."""

from __future__ import annotations

import hashlib
import math
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .config import OpaqueFooterIdentityPolicy
from .page_number import SpreadPageNumberObservation
from .types import ArtifactId, FrameId


class OpaqueIdentityDecisionKind(str, Enum):
    SAME = "same"
    DIFFERENT = "different"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OpaqueFooterTokenPair:
    left_raw_token: str
    right_raw_token: str
    source_frame_id: FrameId
    captured_at_monotonic: float
    recognition_stage: str
    recognizer_version: str
    left_roi_sha256: str
    right_roi_sha256: str

    def __post_init__(self) -> None:
        if not self.left_raw_token.strip() or not self.right_raw_token.strip():
            raise ValueError("opaque token pair requires two non-empty raw tokens")
        if not isinstance(self.source_frame_id, FrameId):
            raise TypeError("source_frame_id must be a FrameId")
        if (
            isinstance(self.captured_at_monotonic, bool)
            or not isinstance(self.captured_at_monotonic, (int, float))
            or not math.isfinite(self.captured_at_monotonic)
            or self.captured_at_monotonic < 0.0
        ):
            raise ValueError("captured_at_monotonic must be finite and non-negative")
        if not self.recognition_stage.strip() or not self.recognizer_version.strip():
            raise ValueError("stage and recognizer version must be non-empty")
        for digest in (self.left_roi_sha256, self.right_roi_sha256):
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ValueError("ROI digests must be lowercase SHA-256")

    @property
    def value(self) -> tuple[str, str]:
        return self.left_raw_token, self.right_raw_token

    @property
    def digest(self) -> str:
        payload = f"{self.left_raw_token}\0{self.right_raw_token}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class OpaqueReferenceBank:
    artifact_id: ArtifactId
    receipt_id: str
    data_pack_id: str
    observations: tuple[OpaqueFooterTokenPair, ...]
    policy_provenance: str

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        if not self.receipt_id.strip() or not self.data_pack_id.strip() or not self.policy_provenance.strip():
            raise ValueError("reference bank lineage must be non-empty")
        if not self.observations:
            raise ValueError("reference bank observations must not be empty")


@dataclass(frozen=True, slots=True)
class OpaqueIdentityDecision:
    kind: OpaqueIdentityDecisionKind
    valid_observations: int
    match_count: int
    matched_artifact_id: ArtifactId | None = None
    timed_out: bool = False


def token_pair_from_page_observation(
    observation: SpreadPageNumberObservation,
    *,
    captured_at_monotonic: float,
    recognition_stage: str,
) -> OpaqueFooterTokenPair | None:
    left = observation.left.raw_text
    right = observation.right.raw_text
    if not isinstance(left, str) or not left.strip() or not isinstance(right, str) or not right.strip():
        return None
    version = (
        f"{observation.left.engine_id}:{observation.left.engine_version}:"
        f"{observation.left.preprocessing_version}"
    )
    return OpaqueFooterTokenPair(
        left.strip(),
        right.strip(),
        observation.left.source_frame_id,
        captured_at_monotonic,
        recognition_stage,
        version,
        observation.left.roi_sha256,
        observation.right.roi_sha256,
    )


class OpaqueQueryCollector:
    def __init__(
        self,
        policy: OpaqueFooterIdentityPolicy,
        references: Sequence[OpaqueReferenceBank],
        *,
        started_at: float,
    ) -> None:
        self.policy = policy
        self.references = tuple(references)
        self.started_at = float(started_at)
        self._observations: list[OpaqueFooterTokenPair] = []
        self.missing_observations = 0

    @property
    def observations(self) -> tuple[OpaqueFooterTokenPair, ...]:
        return tuple(self._observations)

    def observe(self, pair: OpaqueFooterTokenPair) -> OpaqueIdentityDecision:
        reference_frames = {
            item.source_frame_id
            for bank in self.references
            for item in bank.observations
        }
        if pair.source_frame_id in reference_frames:
            raise ValueError("reference and query banks must be frame-disjoint")
        if pair.source_frame_id in {item.source_frame_id for item in self._observations}:
            raise ValueError("query frame must not be counted twice")
        self._observations.append(pair)
        return self.decision()

    def observe_missing(self) -> OpaqueIdentityDecision:
        self.missing_observations += 1
        return self.decision()

    def decision(self, *, now: float | None = None) -> OpaqueIdentityDecision:
        count = len(self._observations)
        if not self.references:
            if count >= self.policy.query_sample_count:
                return OpaqueIdentityDecision(OpaqueIdentityDecisionKind.DIFFERENT, count, 0)
            return self._unknown(now)
        best_count = 0
        best_artifact = None
        for bank in self.references:
            values = {item.value for item in bank.observations}
            matches = sum(item.value in values for item in self._observations)
            if matches > best_count:
                best_count = matches
                best_artifact = bank.artifact_id
            if matches >= self.policy.k_same:
                return OpaqueIdentityDecision(
                    OpaqueIdentityDecisionKind.SAME,
                    count,
                    matches,
                    bank.artifact_id,
                )
        if count >= self.policy.query_sample_count and all(
            sum(item.value in {reference.value for reference in bank.observations} for item in self._observations)
            <= self.policy.k_different
            for bank in self.references
        ):
            return OpaqueIdentityDecision(OpaqueIdentityDecisionKind.DIFFERENT, count, best_count)
        return self._unknown(now, best_count, best_artifact)

    def _unknown(
        self,
        now: float | None,
        match_count: int = 0,
        artifact_id: ArtifactId | None = None,
    ) -> OpaqueIdentityDecision:
        timed_out = now is not None and (now - self.started_at) * 1000.0 >= self.policy.max_collection_ms
        return OpaqueIdentityDecision(
            OpaqueIdentityDecisionKind.UNKNOWN,
            len(self._observations),
            match_count,
            artifact_id,
            timed_out,
        )


class InMemoryOpaqueIdentityLedger:
    def __init__(self, policy: OpaqueFooterIdentityPolicy, data_pack_id: str) -> None:
        if not data_pack_id.strip():
            raise ValueError("data_pack_id must be non-empty")
        self.policy = policy
        self.data_pack_id = data_pack_id
        self._pending: tuple[ArtifactId, tuple[OpaqueFooterTokenPair, ...]] | None = None
        self._accepted: deque[OpaqueReferenceBank] = deque(maxlen=policy.accepted_bank_capacity)

    @property
    def pending_artifact_id(self) -> ArtifactId | None:
        return self._pending[0] if self._pending is not None else None

    def register_pending(
        self,
        artifact_id: ArtifactId,
        observations: Sequence[OpaqueFooterTokenPair],
    ) -> None:
        frozen = tuple(observations[: self.policy.reference_bank_size])
        if not frozen:
            raise ValueError("pending opaque bank must not be empty")
        if self._pending is not None:
            if self._pending == (artifact_id, frozen):
                return
            raise RuntimeError("only one pending opaque bank is allowed")
        self._pending = artifact_id, frozen

    def confirm(self, artifact_id: ArtifactId, receipt_id: str) -> OpaqueReferenceBank | None:
        if self._pending is None or self._pending[0] != artifact_id:
            return None
        bank = OpaqueReferenceBank(
            artifact_id,
            receipt_id,
            self.data_pack_id,
            self._pending[1],
            self.policy.provenance,
        )
        self._pending = None
        self._accepted.append(bank)
        return bank

    def reject_or_release(self, artifact_id: ArtifactId) -> bool:
        if self._pending is None or self._pending[0] != artifact_id:
            return False
        self._pending = None
        return True

    def recent_accepted(self) -> tuple[OpaqueReferenceBank, ...]:
        return tuple(reversed(self._accepted))

    def find(self, artifact_id: ArtifactId) -> OpaqueReferenceBank | None:
        return next((item for item in self._accepted if item.artifact_id == artifact_id), None)
