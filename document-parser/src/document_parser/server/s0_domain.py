"""Immutable Server S0 control-plane values and structured errors."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DatapackState(str, Enum):
    DRAFT = "draft"
    FINALIZING = "finalizing"
    READY = "ready"
    ERROR = "error"


class ScanState(str, Enum):
    OPEN = "open"
    SEALING = "sealing"
    SEALED = "sealed"
    ERROR = "error"


class RevisionState(str, Enum):
    STAGING = "staging"
    READY = "ready"
    SUPERSEDED = "superseded"
    ERROR = "error"


class ReadingState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    ERROR = "error"


class S0Error(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


class S0ValidationError(S0Error):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None):
        super().__init__(code, message, http_status=400, details=details)


class S0NotFoundError(S0Error):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None):
        super().__init__(code, message, http_status=404, details=details)


class S0ConflictError(S0Error):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None):
        super().__init__(code, message, http_status=409, details=details)


class S0TemporaryError(S0Error):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None):
        super().__init__(code, message, http_status=503, retryable=True, details=details)


@dataclass(frozen=True, slots=True)
class CatalogRecord:
    datapack_id: str
    title: str
    status: DatapackState
    current_revision: int | None
    title_audio_ref: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ScanSessionRecord:
    scan_session_id: str
    datapack_id: str
    device_id: str
    base_revision: int | None
    status: ScanState
    through_sequence: int | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ReadingSessionRecord:
    reading_session_id: str
    device_id: str
    datapack_id: str
    revision: int
    viewport_size: int
    status: ReadingState
    created_at: str
    last_seen_at: str


def require_id(name: str, value: object) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise S0ValidationError(
            "INVALID_ID",
            f"{name} must be 1-128 safe ASCII characters",
            {"field": name},
        )
    return value


def require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise S0ValidationError("INVALID_SHA256", f"{name} must be lowercase SHA-256")
    return value


def require_positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise S0ValidationError("INVALID_INTEGER", f"{name} must be a positive integer")
    return value


def require_nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise S0ValidationError("INVALID_INTEGER", f"{name} must be a non-negative integer")
    return value
