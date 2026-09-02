"""Immutable domain values shared by the coordinator and its adapters."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
JsonScalar = str | int | float | bool | None
DetailItems = tuple[tuple[str, JsonScalar], ...]


class DeviceFlowState(str, Enum):
    BOOTING = "booting"
    CONNECTING = "connecting"
    SELECTING_DATAPACK = "selecting_datapack"
    OPENING_SCAN_SESSION = "opening_scan_session"
    SCANNING = "scanning"
    FLUSHING_UPLOADS = "flushing_uploads"
    FINALIZING_DATAPACK = "finalizing_datapack"
    OPENING_READING_SESSION = "opening_reading_session"
    READING = "reading"
    RECOVERABLE_ERROR = "recoverable_error"
    CANCELLING = "cancelling"
    STOPPED = "stopped"


class DeviceOperatingMode(str, Enum):
    CAPTURE = "capture"
    READING = "reading"


class DatapackStatus(str, Enum):
    DRAFT = "draft"
    FINALIZING = "finalizing"
    READY = "ready"
    ERROR = "error"


class ScanSessionStatus(str, Enum):
    OPEN = "open"
    SEALING = "sealing"
    SEALED = "sealed"
    ERROR = "error"


class DeliveryStatus(str, Enum):
    QUEUED = "queued"
    SENDING = "sending"
    RETRYING = "retrying"
    ACKED = "acked"
    REJECTED = "rejected"


class FlushStatus(str, Enum):
    PENDING = "pending"
    FLUSHED = "flushed"
    BLOCKED = "blocked"


class FinalizeStatus(str, Enum):
    FINALIZING = "finalizing"
    READY = "ready"
    ERROR = "error"


class DeviceControl(str, Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    PAGE_NEXT = "page_next"
    PAGE_PREVIOUS = "page_previous"
    CONFIRM = "confirm"
    LEVER = "lever"


class InputAction(str, Enum):
    SHORT = "short"
    LONG = "long"
    ACTIVATED = "activated"
    RELEASED = "released"


class CatalogChoiceKind(str, Enum):
    EXISTING = "existing"
    NEW_DATAPACK = "new_datapack"


class ScannerEventType(str, Enum):
    GUIDANCE = "guidance"
    DIAGNOSTIC = "diagnostic"
    ARTIFACT_READY = "artifact_ready"
    SOURCE_EXHAUSTED = "source_exhausted"
    FATAL = "fatal"


@dataclass(frozen=True, slots=True)
class DeviceId:
    value: str

    def __post_init__(self) -> None:
        _require_text("device_id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DatapackId:
    value: str

    def __post_init__(self) -> None:
        _require_text("datapack_id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ScanSessionId:
    value: str

    def __post_init__(self) -> None:
        _require_text("scan_session_id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ReadingSessionId:
    value: str

    def __post_init__(self) -> None:
        _require_text("reading_session_id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ArtifactId:
    value: str

    def __post_init__(self) -> None:
        _require_text("artifact_id", self.value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class DatapackRevision:
    value: int

    def __post_init__(self) -> None:
        _require_nonnegative_int("datapack revision", self.value)


@dataclass(frozen=True, slots=True, order=True)
class ClientSpreadSequence:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value <= 0:
            raise ValueError("client spread sequence must be a positive integer")


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    datapack_id: DatapackId
    title: str
    status: DatapackStatus
    revision: DatapackRevision | None = None
    title_audio_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.datapack_id, DatapackId):
            raise TypeError("datapack_id must be a DatapackId")
        _require_text("title", self.title)
        if not isinstance(self.status, DatapackStatus):
            raise TypeError("status must be a DatapackStatus")
        if self.revision is not None and not isinstance(self.revision, DatapackRevision):
            raise TypeError("revision must be a DatapackRevision")
        if self.title_audio_ref is not None:
            _require_text("title_audio_ref", self.title_audio_ref)

    @property
    def selectable(self) -> bool:
        return self.status in {DatapackStatus.READY, DatapackStatus.DRAFT}


@dataclass(frozen=True, slots=True)
class CatalogChoice:
    kind: CatalogChoiceKind
    entry: CatalogEntry | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CatalogChoiceKind):
            raise TypeError("kind must be a CatalogChoiceKind")
        if self.kind is CatalogChoiceKind.EXISTING and self.entry is None:
            raise ValueError("existing catalog choice requires an entry")
        if self.kind is CatalogChoiceKind.NEW_DATAPACK and self.entry is not None:
            raise ValueError("new datapack choice cannot contain an entry")

    @classmethod
    def existing(cls, entry: CatalogEntry) -> CatalogChoice:
        return cls(CatalogChoiceKind.EXISTING, entry)

    @classmethod
    def new_datapack(cls) -> CatalogChoice:
        return cls(CatalogChoiceKind.NEW_DATAPACK)


@dataclass(frozen=True, slots=True)
class ScanSessionRef:
    scan_session_id: ScanSessionId
    datapack_id: DatapackId
    status: ScanSessionStatus = ScanSessionStatus.OPEN

    def __post_init__(self) -> None:
        if not isinstance(self.scan_session_id, ScanSessionId):
            raise TypeError("scan_session_id must be a ScanSessionId")
        if not isinstance(self.datapack_id, DatapackId):
            raise TypeError("datapack_id must be a DatapackId")
        if not isinstance(self.status, ScanSessionStatus):
            raise TypeError("status must be a ScanSessionStatus")


@dataclass(frozen=True, slots=True)
class ScannerArtifactReady:
    scan_session_id: ScanSessionId
    artifact_id: ArtifactId
    spread_id: str
    source_frame_id: str
    manifest_path: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.scan_session_id, ScanSessionId):
            raise TypeError("scan_session_id must be a ScanSessionId")
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        _require_text("spread_id", self.spread_id)
        _require_text("source_frame_id", self.source_frame_id)
        _require_text("manifest_path", self.manifest_path)
        if _SHA256_RE.fullmatch(self.manifest_sha256) is None:
            raise ValueError("manifest_sha256 must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class ScannerEvent:
    event_id: str
    scan_session_id: ScanSessionId
    event_type: ScannerEventType
    artifact: ScannerArtifactReady | None = None
    code: str | None = None
    details: DetailItems = ()

    def __post_init__(self) -> None:
        _require_text("scanner event_id", self.event_id)
        if not isinstance(self.scan_session_id, ScanSessionId):
            raise TypeError("scan_session_id must be a ScanSessionId")
        if not isinstance(self.event_type, ScannerEventType):
            raise TypeError("event_type must be a ScannerEventType")
        if self.event_type is ScannerEventType.ARTIFACT_READY and self.artifact is None:
            raise ValueError("artifact_ready event requires artifact")
        if self.event_type is not ScannerEventType.ARTIFACT_READY and self.artifact is not None:
            raise ValueError("only artifact_ready event may contain artifact")
        if self.event_type in {
            ScannerEventType.GUIDANCE,
            ScannerEventType.DIAGNOSTIC,
            ScannerEventType.FATAL,
        }:
            _require_text("scanner event code", self.code)
        object.__setattr__(self, "details", _freeze_details(self.details))


@dataclass(frozen=True, slots=True)
class DeliveryUpdate:
    scan_session_id: ScanSessionId
    sequence: ClientSpreadSequence
    artifact_id: ArtifactId
    status: DeliveryStatus
    receipt_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scan_session_id, ScanSessionId):
            raise TypeError("scan_session_id must be a ScanSessionId")
        if not isinstance(self.sequence, ClientSpreadSequence):
            raise TypeError("sequence must be a ClientSpreadSequence")
        if not isinstance(self.artifact_id, ArtifactId):
            raise TypeError("artifact_id must be an ArtifactId")
        if not isinstance(self.status, DeliveryStatus):
            raise TypeError("status must be a DeliveryStatus")
        if self.status is DeliveryStatus.ACKED:
            _require_text("receipt_id", self.receipt_id)
        elif self.receipt_id is not None:
            _require_text("receipt_id", self.receipt_id)
        if self.status is DeliveryStatus.REJECTED:
            _require_text("reason", self.reason)


@dataclass(frozen=True, slots=True)
class FlushResult:
    scan_session_id: ScanSessionId
    through_sequence: int
    status: FlushStatus
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scan_session_id, ScanSessionId):
            raise TypeError("scan_session_id must be a ScanSessionId")
        _require_nonnegative_int("through_sequence", self.through_sequence)
        if not isinstance(self.status, FlushStatus):
            raise TypeError("status must be a FlushStatus")
        if self.status is FlushStatus.BLOCKED:
            _require_text("reason", self.reason)


@dataclass(frozen=True, slots=True)
class FinalizeResult:
    scan_session_id: ScanSessionId
    datapack_id: DatapackId
    status: FinalizeStatus
    revision: DatapackRevision | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scan_session_id, ScanSessionId):
            raise TypeError("scan_session_id must be a ScanSessionId")
        if not isinstance(self.datapack_id, DatapackId):
            raise TypeError("datapack_id must be a DatapackId")
        if not isinstance(self.status, FinalizeStatus):
            raise TypeError("status must be a FinalizeStatus")
        if self.status is FinalizeStatus.READY and self.revision is None:
            raise ValueError("ready finalization requires revision")
        if self.status is FinalizeStatus.ERROR:
            _require_text("reason", self.reason)


@dataclass(frozen=True, slots=True)
class ReadingSnapshot:
    reading_session_id: ReadingSessionId
    datapack_id: DatapackId
    cursor: DetailItems
    braille_cells: tuple[int, ...] = ()
    audio_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reading_session_id, ReadingSessionId):
            raise TypeError("reading_session_id must be a ReadingSessionId")
        if not isinstance(self.datapack_id, DatapackId):
            raise TypeError("datapack_id must be a DatapackId")
        object.__setattr__(self, "cursor", _freeze_details(self.cursor))
        if any(isinstance(cell, bool) or not isinstance(cell, int) or not 0 <= cell <= 255 for cell in self.braille_cells):
            raise ValueError("braille cells must be integers in [0, 255]")
        _reading_generation(self.cursor)
        if self.audio_ref is not None:
            _require_text("audio_ref", self.audio_ref)

    @property
    def generation(self) -> int:
        return _reading_generation(self.cursor)


@dataclass(frozen=True, slots=True)
class AudioResource:
    wav_bytes: bytes
    sha256: str
    content_length: int
    sample_rate: int
    channels: int
    sample_width: int
    duration_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.wav_bytes, bytes) or not self.wav_bytes:
            raise ValueError("audio resource wav_bytes must be non-empty bytes")
        if not isinstance(self.sha256, str) or len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("audio resource sha256 must be lowercase hexadecimal")
        if self.content_length != len(self.wav_bytes):
            raise ValueError("audio resource content_length must match wav_bytes")
        for name in ("sample_rate", "channels", "sample_width", "duration_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"audio resource {name} must be a positive integer")


def _reading_generation(cursor: DetailItems) -> int:
    values = dict(cursor)
    generation = values.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise ValueError("reading cursor generation must be a non-negative integer")
    return generation


@dataclass(frozen=True, slots=True)
class DeviceInputEvent:
    event_id: str
    control: DeviceControl
    action: InputAction
    at_monotonic: float
    hardware_sequence: int | None = None

    def __post_init__(self) -> None:
        _require_text("input event_id", self.event_id)
        if not isinstance(self.control, DeviceControl):
            raise TypeError("control must be a DeviceControl")
        if not isinstance(self.action, InputAction):
            raise TypeError("action must be an InputAction")
        if isinstance(self.at_monotonic, bool) or not isinstance(self.at_monotonic, (int, float)) or not math.isfinite(self.at_monotonic) or self.at_monotonic < 0:
            raise ValueError("at_monotonic must be finite and non-negative")
        if self.hardware_sequence is not None:
            _require_nonnegative_int("hardware_sequence", self.hardware_sequence)


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_nonnegative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _freeze_details(values: DetailItems) -> DetailItems:
    result: list[tuple[str, JsonScalar]] = []
    seen: set[str] = set()
    for key, value in values:
        _require_text("detail key", key)
        if key in seen:
            raise ValueError(f"duplicate detail key: {key}")
        if not isinstance(value, (str, int, float, bool)) and value is not None:
            raise TypeError(f"detail {key!r} must be a JSON scalar")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"detail {key!r} must be finite")
        seen.add(key)
        result.append((key, value))
    return tuple(result)
