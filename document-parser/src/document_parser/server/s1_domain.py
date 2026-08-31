"""Server S1 immutable values and configuration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from document_parser.server.s0_domain import require_id, require_sha256


class SpreadState(str, Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    READY = "ready"
    REJECTED = "rejected"
    ERROR = "error"


class FragmentState(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    REJECTED = "rejected"
    ERROR = "error"


class FinalizeState(str, Enum):
    WAITING = "waiting"
    ASSEMBLING = "assembling"
    VALIDATING = "validating"
    PROMOTED = "promoted"
    PUBLISHED = "published"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class VerifiedSpreadInput:
    scan_session_id: str
    sequence: int
    artifact_id: str
    spread_id: str
    source_frame_id: str
    bundle_storage_key: str
    manifest_sha256: str

    def __post_init__(self) -> None:
        require_id("scan_session_id", self.scan_session_id)
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence <= 0:
            raise ValueError("sequence must be a positive integer")
        require_id("artifact_id", self.artifact_id)
        require_id("spread_id", self.spread_id)
        require_id("source_frame_id", self.source_frame_id)
        if not isinstance(self.bundle_storage_key, str) or not self.bundle_storage_key:
            raise ValueError("bundle_storage_key must be non-empty")
        require_sha256("manifest_sha256", self.manifest_sha256)


@dataclass(frozen=True, slots=True)
class SpreadReceipt:
    receipt_id: str
    scan_session_id: str
    sequence: int
    artifact_id: str
    status: SpreadState


@dataclass(frozen=True, slots=True)
class S1Config:
    received_root: Path
    fragments_root: Path
    finalize_root: Path
    revisions_root: Path
    max_bundle_files: int = 32
    max_bundle_bytes: int = 128 * 1024 * 1024
    max_image_dimension: int = 16_384
    parser_max_attempts: int = 3
    lease_seconds: int = 300

    def __post_init__(self) -> None:
        for name in (
            "max_bundle_files",
            "max_bundle_bytes",
            "max_image_dimension",
            "parser_max_attempts",
            "lease_seconds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be positive")

    @classmethod
    def under(cls, datapacks_root: Path) -> "S1Config":
        server = datapacks_root / "_server"
        return cls(
            received_root=server / "received",
            fragments_root=server / "fragments",
            finalize_root=server / "finalize",
            revisions_root=datapacks_root / "_revisions",
        )
