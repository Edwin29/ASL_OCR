"""Deterministic test doubles; never selected as production adapters."""

from __future__ import annotations

from collections import deque

from asl_device.events import FeedbackEvent
from asl_device.protocols import RecoverablePortError
from asl_device.types import (
    ArtifactId,
    CatalogEntry,
    ClientSpreadSequence,
    DatapackId,
    DatapackRevision,
    DatapackStatus,
    DeliveryStatus,
    DeliveryUpdate,
    DeviceControl,
    DeviceId,
    FinalizeResult,
    FinalizeStatus,
    FlushResult,
    FlushStatus,
    InputAction,
    ReadingSessionId,
    ReadingSnapshot,
    ScanSessionId,
    ScanSessionRef,
    ScannerArtifactReady,
    ScannerEvent,
)


class ManualClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class CollectingFeedback:
    def __init__(self, fail: bool = False) -> None:
        self.events: list[FeedbackEvent] = []
        self.fail = fail

    def emit(self, event: FeedbackEvent) -> None:
        if self.fail:
            raise RuntimeError("speaker unavailable")
        self.events.append(event)


class FakeCatalogPort:
    def __init__(self, entries: tuple[CatalogEntry, ...] = ()) -> None:
        self.entries = entries
        self.list_calls: list[DeviceId] = []
        self.create_calls: list[tuple[DeviceId, str]] = []
        self.fail_list = False

    def list_datapacks(self, device_id: DeviceId) -> tuple[CatalogEntry, ...]:
        self.list_calls.append(device_id)
        if self.fail_list:
            raise RecoverablePortError("catalog unavailable")
        return self.entries

    def create_datapack(self, device_id: DeviceId, operation_id: str) -> CatalogEntry:
        self.create_calls.append((device_id, operation_id))
        index = len(self.create_calls)
        entry = CatalogEntry(
            DatapackId(f"new-{index}"),
            f"새 데이터팩 {index}",
            DatapackStatus.DRAFT,
            DatapackRevision(0),
        )
        self.entries = self.entries + (entry,)
        return entry


class FakeScanSessionPort:
    def __init__(self) -> None:
        self.open_calls: list[tuple[DeviceId, DatapackId, str]] = []
        self.seal_calls: list[tuple[ScanSessionId, int]] = []
        self.get_status_calls: list[ScanSessionId] = []
        self.seal_result: FinalizeResult | None = None
        self.status_results: deque[FinalizeResult] = deque()

    def open(self, device_id: DeviceId, datapack_id: DatapackId, operation_id: str) -> ScanSessionRef:
        self.open_calls.append((device_id, datapack_id, operation_id))
        return ScanSessionRef(ScanSessionId(f"scan-{len(self.open_calls)}"), datapack_id)

    def seal(self, scan_session_id: ScanSessionId, through_sequence: int) -> FinalizeResult:
        self.seal_calls.append((scan_session_id, through_sequence))
        if self.seal_result is not None:
            return self.seal_result
        datapack_id = self.open_calls[-1][1]
        return FinalizeResult(scan_session_id, datapack_id, FinalizeStatus.FINALIZING)

    def get_status(self, scan_session_id: ScanSessionId) -> FinalizeResult:
        self.get_status_calls.append(scan_session_id)
        if self.status_results:
            return self.status_results.popleft()
        datapack_id = self.open_calls[-1][1]
        return FinalizeResult(scan_session_id, datapack_id, FinalizeStatus.FINALIZING)


class FakeScannerRuntime:
    def __init__(self) -> None:
        self.start_calls: list[ScanSessionRef] = []
        self.freeze_calls = 0
        self.cancel_calls = 0
        self.delivery_updates: list[tuple[ArtifactId, DeliveryUpdate]] = []
        self.delivery_callback_events: deque[tuple[ScannerEvent, ...]] = deque()
        self.events: deque[ScannerEvent] = deque()
        self.diagnostics: tuple[
            tuple[str, str | int | float | bool | None], ...
        ] = ()

    def start(self, scan_session: ScanSessionRef) -> None:
        self.start_calls.append(scan_session)

    def runtime_diagnostics(self):
        return self.diagnostics

    def poll(self) -> tuple[ScannerEvent, ...]:
        if not self.events:
            return ()
        return (self.events.popleft(),)

    def freeze(self) -> None:
        self.freeze_calls += 1

    def cancel(self) -> None:
        self.cancel_calls += 1

    def apply_delivery_update(
        self,
        artifact_id: ArtifactId,
        update: DeliveryUpdate,
    ) -> tuple[ScannerEvent, ...]:
        self.delivery_updates.append((artifact_id, update))
        if not self.delivery_callback_events:
            return ()
        return self.delivery_callback_events.popleft()


class FakeDeliveryPort:
    def __init__(self) -> None:
        self.queue_calls: list[tuple[ScanSessionId, ClientSpreadSequence, ScannerArtifactReady]] = []
        self.flush_calls: list[tuple[ScanSessionId, int]] = []
        self._current: dict[int, DeliveryUpdate] = {}
        self._pending_updates: deque[DeliveryUpdate] = deque()
        self.forced_flush: FlushResult | None = None
        self.fail_queue_once = False

    def queue(
        self,
        scan_session_id: ScanSessionId,
        sequence: ClientSpreadSequence,
        artifact: ScannerArtifactReady,
    ) -> DeliveryUpdate:
        self.queue_calls.append((scan_session_id, sequence, artifact))
        if self.fail_queue_once:
            self.fail_queue_once = False
            raise RecoverablePortError("local delivery queue unavailable")
        update = DeliveryUpdate(scan_session_id, sequence, artifact.artifact_id, DeliveryStatus.QUEUED)
        self._current[sequence.value] = update
        return update

    def pending_status(self, scan_session_id: ScanSessionId) -> tuple[DeliveryUpdate, ...]:
        if not self._pending_updates:
            return ()
        update = self._pending_updates.popleft()
        self._current[update.sequence.value] = update
        return (update,)

    def flush_through(self, scan_session_id: ScanSessionId, through_sequence: int) -> FlushResult:
        self.flush_calls.append((scan_session_id, through_sequence))
        if self.forced_flush is not None:
            return self.forced_flush
        relevant = [self._current.get(i) for i in range(1, through_sequence + 1)]
        if any(update is not None and update.status is DeliveryStatus.REJECTED for update in relevant):
            return FlushResult(scan_session_id, through_sequence, FlushStatus.BLOCKED, "delivery rejected")
        if all(update is not None and update.status is DeliveryStatus.ACKED for update in relevant):
            return FlushResult(scan_session_id, through_sequence, FlushStatus.FLUSHED)
        return FlushResult(scan_session_id, through_sequence, FlushStatus.PENDING)

    def acknowledge(self, sequence: int, receipt_id: str | None = None) -> None:
        current = self._current[sequence]
        self._pending_updates.append(
            DeliveryUpdate(
                current.scan_session_id,
                current.sequence,
                current.artifact_id,
                DeliveryStatus.ACKED,
                receipt_id=receipt_id or f"receipt-{sequence}",
            )
        )

    def reject(self, sequence: int, reason: str = "parser rejected") -> None:
        current = self._current[sequence]
        self._pending_updates.append(
            DeliveryUpdate(
                current.scan_session_id,
                current.sequence,
                current.artifact_id,
                DeliveryStatus.REJECTED,
                reason=reason,
            )
        )

    def inject_update(self, update: DeliveryUpdate) -> None:
        self._pending_updates.append(update)


class FakeReadingSessionPort:
    def __init__(self) -> None:
        self.open_calls: list[tuple[DeviceId, DatapackId, int, str]] = []
        self.command_calls: list[tuple[ReadingSessionId, str, DeviceControl, InputAction]] = []
        self.current_calls: list[ReadingSessionId] = []

    def open(
        self, device_id: DeviceId, datapack_id: DatapackId, viewport_size: int, operation_id: str
    ) -> ReadingSnapshot:
        self.open_calls.append((device_id, datapack_id, viewport_size, operation_id))
        return ReadingSnapshot(
            ReadingSessionId(f"reading-{len(self.open_calls)}"),
            datapack_id,
            (("page_index", 3), ("node_index", 7), ("generation", 0)),
            braille_cells=(1, 2, 3),
        )

    def get_current(self, reading_session_id: ReadingSessionId) -> ReadingSnapshot:
        self.current_calls.append(reading_session_id)
        datapack_id = self.open_calls[-1][1]
        return ReadingSnapshot(
            reading_session_id,
            datapack_id,
            (("page_index", 3), ("node_index", 7), ("generation", 0)),
        )

    def send_command(
        self,
        reading_session_id: ReadingSessionId,
        command_id: str,
        control: DeviceControl,
        action: InputAction,
    ) -> ReadingSnapshot:
        self.command_calls.append((reading_session_id, command_id, control, action))
        datapack_id = self.open_calls[-1][1]
        return ReadingSnapshot(
            reading_session_id,
            datapack_id,
            (("page_index", 3), ("node_index", 8), ("generation", 1)),
        )


def ready_entry(book_id: str = "book-a", title: str = "교재 A") -> CatalogEntry:
    return CatalogEntry(DatapackId(book_id), title, DatapackStatus.READY, DatapackRevision(1))
