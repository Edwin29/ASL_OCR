"""Local configuration for the single-sender durable delivery adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DeviceDeliveryConfig:
    outbox_db_path: Path
    artifact_root: Path
    upload_timeout_seconds: float = 60.0
    retry_initial_seconds: float = 1.0
    retry_max_seconds: float = 30.0
    response_limit_bytes: int = 64 * 1024
    file_chunk_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        object.__setattr__(self, "outbox_db_path", Path(self.outbox_db_path).resolve())
        object.__setattr__(self, "artifact_root", Path(self.artifact_root).resolve())
        for name in ("upload_timeout_seconds", "retry_initial_seconds", "retry_max_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.retry_initial_seconds > self.retry_max_seconds:
            raise ValueError("retry_initial_seconds cannot exceed retry_max_seconds")
        for name in ("response_limit_bytes", "file_chunk_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.outbox_db_path == self.artifact_root or self.artifact_root in self.outbox_db_path.parents:
            raise ValueError("outbox_db_path cannot be inside artifact_root")
