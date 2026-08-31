"""Bottom-ROI page-number identity, cache, ledger, and consensus contracts."""

from __future__ import annotations

import hashlib
from collections import OrderedDict, deque
from dataclasses import dataclass
from enum import Enum

import numpy as np

from .config import PageNumberPolicy
from .types import ArtifactId, FrameId, PageSide


class PageNumberSource(str, Enum):
    CORRECTED = "corrected"
    PREVIEW = "preview"


class PageNumberStatus(str, Enum):
    OBSERVED = "observed"
    NOT_OBSERVED = "not_observed"
    INVALID = "invalid"
    CONFLICT = "conflict"


class SpreadPageNumberStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"
    CONFLICT = "conflict"


class PageKeyRelation(str, Enum):
    SAME = "same"
    DIFFERENT = "different"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class PageNumberRecognition:
    raw_text: str | None
    confidence: float | None
    bbox: tuple[int, int, int, int] | None
    variant_agreement: int
    status: PageNumberStatus

    def __post_init__(self) -> None:
        if self.raw_text is not None and not isinstance(self.raw_text, str):
            raise TypeError("raw_text must be a string or None")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.bbox is not None and (len(self.bbox) != 4 or any(value < 0 for value in self.bbox)):
            raise ValueError("bbox must contain four non-negative integers")
        if self.variant_agreement < 0:
            raise ValueError("variant_agreement must be non-negative")
        if not isinstance(self.status, PageNumberStatus):
            raise TypeError("status must be PageNumberStatus")


@dataclass(frozen=True, slots=True)
class PageNumberObservation:
    side: PageSide
    raw_text: str | None
    normalized_label: str | None
    confidence: float | None
    bbox: tuple[int, int, int, int] | None
    roi_sha256: str
    source_kind: PageNumberSource
    source_frame_id: FrameId
    artifact_id: ArtifactId | None
    engine_id: str
    engine_version: str
    preprocessing_version: str
    variant_agreement: int
    status: PageNumberStatus
    cache_hit: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.side, PageSide):
            raise TypeError("side must be PageSide")
        if self.raw_text is not None and not isinstance(self.raw_text, str):
            raise TypeError("raw_text must be a string or None")
        if self.normalized_label is not None and not _valid_label(self.normalized_label):
            raise ValueError("normalized_label must be an integer string in [1, 9999]")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.bbox is not None and (len(self.bbox) != 4 or any(value < 0 for value in self.bbox)):
            raise ValueError("bbox must contain four non-negative integers")
        if len(self.roi_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in self.roi_sha256):
            raise ValueError("roi_sha256 must be lowercase SHA-256")
        if not isinstance(self.source_kind, PageNumberSource):
            raise TypeError("source_kind must be PageNumberSource")
        if not isinstance(self.source_frame_id, FrameId):
            raise TypeError("source_frame_id must be FrameId")
        if self.artifact_id is not None and not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be ArtifactId or None")
        for value in (self.engine_id, self.engine_version, self.preprocessing_version):
            if not value.strip():
                raise ValueError("engine and preprocessing versions must be non-empty")
        if self.variant_agreement < 0:
            raise ValueError("variant_agreement must be non-negative")
        if not isinstance(self.status, PageNumberStatus):
            raise TypeError("status must be PageNumberStatus")


@dataclass(frozen=True, slots=True)
class SpreadPageKey:
    data_pack_id: str
    left_page_label: str
    right_page_label: str
    recognizer_version: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.data_pack_id.strip() or not self.recognizer_version.strip():
            raise ValueError("data_pack_id and recognizer_version must be non-empty")
        if not _valid_label(self.left_page_label) or not _valid_label(self.right_page_label):
            raise ValueError("page labels must be integer strings in [1, 9999]")
        if self.schema_version != 1:
            raise ValueError("unsupported SpreadPageKey schema")


@dataclass(frozen=True, slots=True)
class SpreadPageNumberObservation:
    left: PageNumberObservation
    right: PageNumberObservation
    key: SpreadPageKey | None
    status: SpreadPageNumberStatus
    processing_ms: float

    def __post_init__(self) -> None:
        if self.left.side is not PageSide.LEFT or self.right.side is not PageSide.RIGHT:
            raise ValueError("spread observation must preserve left/right")
        if self.left.source_frame_id != self.right.source_frame_id:
            raise ValueError("page-number observations must share source frame")
        if self.processing_ms < 0:
            raise ValueError("processing_ms must be non-negative")
        if self.status is SpreadPageNumberStatus.COMPLETE and self.key is None:
            raise ValueError("complete observation requires key")
        if self.status is not SpreadPageNumberStatus.COMPLETE and self.key is not None:
            raise ValueError("only complete observation may contain a key")


@dataclass(frozen=True, slots=True)
class PageKeyLedgerEntry:
    key: SpreadPageKey
    artifact_id: ArtifactId
    receipt_id: str


@dataclass(frozen=True, slots=True)
class PageNumberChangeDecision:
    relation: PageKeyRelation
    stable_count: int
    changed: bool
    key: SpreadPageKey | None


class InMemoryPageKeyLedger:
    def __init__(self, policy: PageNumberPolicy = PageNumberPolicy()) -> None:
        self._accepted: deque[PageKeyLedgerEntry] = deque(maxlen=policy.accepted_capacity)

    def relation(self, key: SpreadPageKey | None) -> tuple[PageKeyRelation, PageKeyLedgerEntry | None]:
        if key is None or not self._accepted:
            return PageKeyRelation.UNAVAILABLE, None
        for entry in reversed(self._accepted):
            if entry.key == key:
                return PageKeyRelation.SAME, entry
        if any(entry.key.data_pack_id == key.data_pack_id for entry in self._accepted):
            return PageKeyRelation.DIFFERENT, None
        return PageKeyRelation.UNAVAILABLE, None

    def accept(self, key: SpreadPageKey | None, artifact_id: ArtifactId, receipt_id: str) -> None:
        if key is None:
            return
        if any(entry.artifact_id == artifact_id for entry in self._accepted):
            return
        self._accepted.append(PageKeyLedgerEntry(key, artifact_id, receipt_id))

    def recent_accepted(self) -> tuple[PageKeyLedgerEntry, ...]:
        return tuple(reversed(self._accepted))


class PageNumberChangeTracker:
    def __init__(self, policy: PageNumberPolicy = PageNumberPolicy()) -> None:
        self.policy = policy
        self._baseline: SpreadPageKey | None = None
        self._candidate: SpreadPageKey | None = None
        self._stable_count = 0

    def arm(self, key: SpreadPageKey | None) -> None:
        self._baseline = key
        self._candidate = None
        self._stable_count = 0

    def reset(self) -> None:
        self.arm(None)

    def observe(self, key: SpreadPageKey | None, *, eligible: bool) -> PageNumberChangeDecision:
        if not eligible or self._baseline is None or key is None:
            self._candidate = None
            self._stable_count = 0
            return PageNumberChangeDecision(PageKeyRelation.UNAVAILABLE, 0, False, key)
        if key == self._baseline:
            self._candidate = None
            self._stable_count = 0
            return PageNumberChangeDecision(PageKeyRelation.SAME, 0, False, key)
        if key != self._candidate:
            self._candidate = key
            self._stable_count = 1
        else:
            self._stable_count += 1
        return PageNumberChangeDecision(
            PageKeyRelation.DIFFERENT,
            self._stable_count,
            self._stable_count >= self.policy.stable_sample_count,
            key,
        )


class PageNumberRecognitionCache:
    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._items: OrderedDict[tuple[str, str, str, str, str], PageNumberRecognition] = OrderedDict()
        self.hits = 0

    def get(self, key: tuple[str, str, str, str, str]) -> PageNumberRecognition | None:
        value = self._items.get(key)
        if value is not None:
            self._items.move_to_end(key)
            self.hits += 1
        return value

    def put(self, key: tuple[str, str, str, str, str], value: PageNumberRecognition) -> None:
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self._capacity:
            self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)


def normalize_page_label(raw_text: str | None, policy: PageNumberPolicy) -> str | None:
    if raw_text is None or not raw_text.isascii() or not raw_text.isdigit():
        return None
    if not policy.min_digits <= len(raw_text) <= policy.max_digits:
        return None
    normalized = raw_text.lstrip("0")
    if not normalized or not _valid_label(normalized):
        return None
    return normalized


def roi_sha256(roi: np.ndarray) -> str:
    if not isinstance(roi, np.ndarray) or roi.size == 0:
        raise ValueError("ROI must be a non-empty ndarray")
    digest = hashlib.sha256()
    digest.update(str(roi.shape).encode("ascii"))
    digest.update(str(roi.dtype).encode("ascii"))
    digest.update(roi.tobytes())
    return digest.hexdigest()


def _valid_label(value: str) -> bool:
    return value.isascii() and value.isdigit() and not value.startswith("0") and 1 <= int(value) <= 9999
