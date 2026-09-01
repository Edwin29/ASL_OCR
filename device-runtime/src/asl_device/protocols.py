"""Narrow I/O boundaries used by the pure coordinator core."""

from __future__ import annotations

from typing import Protocol

from .connectivity import ConnectivityEvent, ConnectivitySnapshot
from .events import FeedbackEvent
from .types import (
    ArtifactId,
    CatalogEntry,
    ClientSpreadSequence,
    DatapackId,
    DeliveryUpdate,
    DeviceControl,
    DeviceId,
    FinalizeResult,
    FlushResult,
    InputAction,
    ReadingSessionId,
    ReadingSnapshot,
    ScanSessionId,
    ScanSessionRef,
    ScannerArtifactReady,
    ScannerEvent,
)


class RecoverablePortError(RuntimeError):
    """An operation may be retried or returned to a safe selection state."""


class FatalPortError(RuntimeError):
    """The active device flow cannot continue safely."""


class Clock(Protocol):
    def monotonic(self) -> float: ...


class FeedbackSink(Protocol):
    def emit(self, event: FeedbackEvent) -> None: ...


class ConnectivityPort(Protocol):
    def start(self) -> tuple[ConnectivityEvent, ...]: ...

    def poll(self) -> tuple[ConnectivityEvent, ...]: ...

    def current_status(self) -> ConnectivitySnapshot: ...

    def stop(self) -> tuple[ConnectivityEvent, ...]: ...


class CatalogPort(Protocol):
    def list_datapacks(self, device_id: DeviceId) -> tuple[CatalogEntry, ...]: ...

    def create_datapack(self, device_id: DeviceId, operation_id: str) -> CatalogEntry: ...


class ScanSessionPort(Protocol):
    def open(self, device_id: DeviceId, datapack_id: DatapackId, operation_id: str) -> ScanSessionRef: ...

    def seal(self, scan_session_id: ScanSessionId, through_sequence: int) -> FinalizeResult: ...

    def get_status(self, scan_session_id: ScanSessionId) -> FinalizeResult: ...


class ScannerRuntime(Protocol):
    def start(self, scan_session: ScanSessionRef) -> None: ...

    def poll(self) -> tuple[ScannerEvent, ...]: ...

    def freeze(self) -> None: ...

    def cancel(self) -> None: ...

    def apply_delivery_update(
        self,
        artifact_id: ArtifactId,
        update: DeliveryUpdate,
    ) -> tuple[ScannerEvent, ...]: ...


class DeliveryPort(Protocol):
    def queue(
        self,
        scan_session_id: ScanSessionId,
        sequence: ClientSpreadSequence,
        artifact: ScannerArtifactReady,
    ) -> DeliveryUpdate: ...

    def pending_status(self, scan_session_id: ScanSessionId) -> tuple[DeliveryUpdate, ...]: ...

    def flush_through(self, scan_session_id: ScanSessionId, through_sequence: int) -> FlushResult: ...


class ReadingSessionPort(Protocol):
    def open(
        self,
        device_id: DeviceId,
        datapack_id: DatapackId,
        viewport_size: int,
        operation_id: str,
    ) -> ReadingSnapshot: ...

    def get_current(self, reading_session_id: ReadingSessionId) -> ReadingSnapshot: ...

    def send_command(
        self,
        reading_session_id: ReadingSessionId,
        command_id: str,
        control: DeviceControl,
        action: InputAction,
    ) -> ReadingSnapshot: ...
