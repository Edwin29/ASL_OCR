"""Pure, synchronous/poll-driven device application coordinator."""

from __future__ import annotations

from collections import deque

from .catalog import CatalogModel
from .connectivity import ConnectivityEvent, ConnectivityEventType, ConnectivityState
from .events import CoordinatorEvent, CoordinatorEventType, FeedbackCode, FeedbackEvent
from .protocols import (
    CatalogPort,
    Clock,
    ConnectivityPort,
    DeliveryPort,
    FatalPortError,
    FeedbackSink,
    ReadingSessionPort,
    RecoverablePortError,
    ScannerRuntime,
    ScanSessionPort,
)
from .types import (
    ArtifactId,
    CatalogChoiceKind,
    ClientSpreadSequence,
    DatapackId,
    DeliveryStatus,
    DeliveryUpdate,
    DeviceControl,
    DeviceFlowState,
    DeviceId,
    DeviceInputEvent,
    FinalizeResult,
    FinalizeStatus,
    FlushStatus,
    InputAction,
    ReadingSnapshot,
    ScanSessionRef,
    ScannerArtifactReady,
    ScannerEvent,
    ScannerEventType,
)


class DeviceFlowCoordinator:
    """Owns cross-component ordering, never the Scanner or server internals."""

    _BURST_STEPS = 5
    _INPUT_DEDUP_CAPACITY = 1024

    def __init__(
        self,
        *,
        device_id: DeviceId,
        viewport_size: int,
        clock: Clock,
        catalog_port: CatalogPort,
        scan_session_port: ScanSessionPort,
        scanner: ScannerRuntime,
        delivery: DeliveryPort,
        reading: ReadingSessionPort,
        feedback: FeedbackSink,
        connectivity: ConnectivityPort | None = None,
    ) -> None:
        if not isinstance(device_id, DeviceId):
            raise TypeError("device_id must be a DeviceId")
        if isinstance(viewport_size, bool) or not isinstance(viewport_size, int) or viewport_size <= 0:
            raise ValueError("viewport_size must be a positive integer")
        self.device_id = device_id
        self.viewport_size = viewport_size
        self.clock = clock
        self.catalog_port = catalog_port
        self.scan_session_port = scan_session_port
        self.scanner = scanner
        self.delivery = delivery
        self.reading = reading
        self.feedback = feedback
        self.connectivity = connectivity

        self.state = DeviceFlowState.BOOTING
        self.catalog: CatalogModel | None = None
        self.scan_session: ScanSessionRef | None = None
        self.reading_snapshot: ReadingSnapshot | None = None
        self._last_sequence = 0
        self._replacement_sequence: int | None = None
        self._cutoff_sequence: int | None = None
        self._seal_requested = False
        self._delivery_by_sequence: dict[int, DeliveryUpdate] = {}
        self._event_counter = 0
        self._seen_inputs: set[str] = set()
        self._input_order: deque[str] = deque()
        self._seen_scanner_events: set[str] = set()
        self._pending_queue: tuple[ClientSpreadSequence, ScannerArtifactReady] | None = None
        self._recovery = "connect"

    def start(self) -> tuple[CoordinatorEvent, ...]:
        if self.state is not DeviceFlowState.BOOTING:
            raise RuntimeError(f"cannot start from {self.state.value}")
        events: list[CoordinatorEvent] = []
        self._transition(DeviceFlowState.CONNECTING, events)
        if self.connectivity is None:
            self._load_catalog(events)
        else:
            self._handle_connectivity_events(self.connectivity.start(), events)
            self._poll_connectivity(events)
        return tuple(events)

    def handle_input(self, input_event: DeviceInputEvent) -> tuple[CoordinatorEvent, ...]:
        if not isinstance(input_event, DeviceInputEvent):
            raise TypeError("input_event must be a DeviceInputEvent")
        if input_event.event_id in self._seen_inputs:
            return ()
        self._remember_input(input_event.event_id)
        events: list[CoordinatorEvent] = []

        if self.state is DeviceFlowState.SELECTING_DATAPACK:
            self._handle_selection_input(input_event, events)
        elif self.state is DeviceFlowState.SCANNING:
            if input_event.control is DeviceControl.CONFIRM and input_event.action is InputAction.SHORT:
                self._request_scan_stop(events)
        elif self.state is DeviceFlowState.READING:
            self._handle_reading_input(input_event, events)
        elif self.state is DeviceFlowState.RECOVERABLE_ERROR:
            if input_event.control is DeviceControl.CONFIRM and input_event.action is InputAction.SHORT:
                self._retry_recovery(events)
        return tuple(events)

    def poll(self) -> tuple[CoordinatorEvent, ...]:
        events: list[CoordinatorEvent] = []
        self._poll_connectivity(events)
        if self.state is DeviceFlowState.STOPPED:
            return tuple(events)
        if self.state is DeviceFlowState.SCANNING:
            try:
                for scanner_event in self.scanner.poll():
                    self._handle_scanner_event(scanner_event, events)
            except FatalPortError as exc:
                self._fatal(str(exc), events)
                return tuple(events)
            except RecoverablePortError as exc:
                self._recoverable(str(exc), "resume_scanning", events)
                return tuple(events)

        if self.state in {DeviceFlowState.SCANNING, DeviceFlowState.FLUSHING_UPLOADS} and self.scan_session is not None:
            try:
                updates = self.delivery.pending_status(self.scan_session.scan_session_id)
            except RecoverablePortError:
                self._feedback(FeedbackCode.SERVER_RETRYING)
                updates = ()
            for update in updates:
                self._handle_delivery_update(update, events)

        if self.state is DeviceFlowState.FLUSHING_UPLOADS:
            self._advance_flushing(events)
        elif self.state is DeviceFlowState.FINALIZING_DATAPACK:
            self._poll_finalization(events)
        return tuple(events)

    def stop(self) -> tuple[CoordinatorEvent, ...]:
        if self.state is DeviceFlowState.STOPPED:
            return ()
        events: list[CoordinatorEvent] = []
        previous = self.state
        self._transition(DeviceFlowState.CANCELLING, events)
        if self.scan_session is not None and previous is not DeviceFlowState.READING:
            try:
                self.scanner.cancel()
            except Exception:
                pass
        if self.connectivity is not None:
            try:
                self.connectivity.stop()
            except Exception:
                pass
        self._transition(DeviceFlowState.STOPPED, events)
        return tuple(events)

    def _load_catalog(self, events: list[CoordinatorEvent]) -> None:
        try:
            entries = self.catalog_port.list_datapacks(self.device_id)
        except RecoverablePortError as exc:
            self._recoverable(str(exc), "connect", events)
            return
        except FatalPortError as exc:
            self._fatal(str(exc), events)
            return
        self.catalog = CatalogModel(entries)
        self._transition(DeviceFlowState.SELECTING_DATAPACK, events)
        self._emit(
            CoordinatorEventType.CATALOG_LOADED,
            events,
            (("server_entry_count", len(entries)), ("visible_item_count", len(self.catalog.items))),
        )
        self._announce_catalog_current(events, changed=False)

    def _handle_selection_input(self, input_event: DeviceInputEvent, events: list[CoordinatorEvent]) -> None:
        assert self.catalog is not None
        if input_event.control in {DeviceControl.UP, DeviceControl.DOWN}:
            steps = self._BURST_STEPS if input_event.action is InputAction.LONG else 1
            delta = -steps if input_event.control is DeviceControl.UP else steps
            if self.catalog.move(delta):
                self._announce_catalog_current(events, changed=True)
            return
        if input_event.control is DeviceControl.CONFIRM and input_event.action is InputAction.SHORT:
            self._open_selected_scan(input_event.event_id, events)

    def _open_selected_scan(self, operation_id: str, events: list[CoordinatorEvent]) -> None:
        assert self.catalog is not None
        choice = self.catalog.current.choice
        self._transition(DeviceFlowState.OPENING_SCAN_SESSION, events)
        try:
            if choice.kind is CatalogChoiceKind.NEW_DATAPACK:
                entry = self.catalog_port.create_datapack(
                    self.device_id, f"{operation_id}:create"
                )
                self._emit(
                    CoordinatorEventType.DATAPACK_CREATED,
                    events,
                    (("datapack_id", entry.datapack_id.value),),
                )
                datapack_id = entry.datapack_id
            else:
                assert choice.entry is not None
                datapack_id = choice.entry.datapack_id
            session = self.scan_session_port.open(
                self.device_id, datapack_id, f"{operation_id}:scan-open"
            )
            if session.datapack_id != datapack_id:
                raise FatalPortError("scan session datapack identity mismatch")
            self.scan_session = session
            self._last_sequence = 0
            self._replacement_sequence = None
            self._cutoff_sequence = None
            self._seal_requested = False
            self._delivery_by_sequence.clear()
            self._seen_scanner_events.clear()
            self._pending_queue = None
            self._emit(
                CoordinatorEventType.SCAN_SESSION_OPENED,
                events,
                (("scan_session_id", session.scan_session_id.value), ("datapack_id", datapack_id.value)),
            )
            self.scanner.start(session)
        except RecoverablePortError as exc:
            self._recoverable(str(exc), "select", events)
            return
        except FatalPortError as exc:
            self._fatal(str(exc), events)
            return
        self._transition(DeviceFlowState.SCANNING, events)
        self._emit(CoordinatorEventType.SCANNER_STARTED, events)
        self._feedback(FeedbackCode.CONFIRM_SELECTION, (("datapack_id", datapack_id.value),))
        self._feedback(FeedbackCode.SCAN_STARTED, (("datapack_id", datapack_id.value),))

    def _handle_scanner_event(self, scanner_event: ScannerEvent, events: list[CoordinatorEvent]) -> None:
        if scanner_event.event_id in self._seen_scanner_events:
            return
        self._seen_scanner_events.add(scanner_event.event_id)
        if self.scan_session is None or scanner_event.scan_session_id != self.scan_session.scan_session_id:
            return
        if scanner_event.event_type is ScannerEventType.GUIDANCE:
            self._feedback(
                FeedbackCode.SCANNER_GUIDANCE,
                (("guidance_code", scanner_event.code),) + scanner_event.details,
            )
            return
        if scanner_event.event_type is ScannerEventType.FATAL:
            self._fatal(scanner_event.code or "scanner fatal error", events)
            return
        if scanner_event.event_type is ScannerEventType.SOURCE_EXHAUSTED:
            details = (
                ("queued_count", len(self._delivery_by_sequence)),
                (
                    "acked_count",
                    sum(
                        update.status is DeliveryStatus.ACKED
                        for update in self._delivery_by_sequence.values()
                    ),
                ),
            )
            self._emit(CoordinatorEventType.SCAN_INPUT_EXHAUSTED, events, details)
            self._feedback(FeedbackCode.SCAN_INPUT_EXHAUSTED, details)
            return
        assert scanner_event.artifact is not None
        if scanner_event.artifact.scan_session_id != self.scan_session.scan_session_id:
            return
        if self._replacement_sequence is not None:
            sequence = ClientSpreadSequence(self._replacement_sequence)
            self._replacement_sequence = None
        else:
            self._last_sequence += 1
            sequence = ClientSpreadSequence(self._last_sequence)
        try:
            update = self.delivery.queue(self.scan_session.scan_session_id, sequence, scanner_event.artifact)
        except RecoverablePortError as exc:
            # Scanner already transferred ownership of this immutable artifact.
            # Keep its logical sequence stable and retry the exact same payload;
            # recapturing here could silently skip or duplicate a page.
            self._pending_queue = (sequence, scanner_event.artifact)
            try:
                self.scanner.freeze()
            except FatalPortError as freeze_exc:
                self._fatal(str(freeze_exc), events)
                return
            except RecoverablePortError:
                pass
            self._feedback(FeedbackCode.SERVER_RETRYING)
            self._recoverable(str(exc), "retry_queue", events)
            return
        except FatalPortError as exc:
            self._fatal(str(exc), events)
            return
        if update.sequence != sequence or update.artifact_id != scanner_event.artifact.artifact_id:
            self._fatal("delivery queue lineage mismatch", events)
            return
        self._delivery_by_sequence[sequence.value] = update
        self._emit(
            CoordinatorEventType.SPREAD_QUEUED,
            events,
            (("sequence", sequence.value), ("artifact_id", scanner_event.artifact.artifact_id.value)),
        )
        self._handle_delivery_update(update, events)

    def _handle_delivery_update(self, update: DeliveryUpdate, events: list[CoordinatorEvent]) -> None:
        if self.scan_session is None or update.scan_session_id != self.scan_session.scan_session_id:
            return
        previous = self._delivery_by_sequence.get(update.sequence.value)
        if previous is None or previous.artifact_id != update.artifact_id:
            return
        if previous.status in {DeliveryStatus.ACKED, DeliveryStatus.REJECTED}:
            return
        self._delivery_by_sequence[update.sequence.value] = update
        self.scanner.apply_delivery_update(update.artifact_id, update)
        if update.status is DeliveryStatus.ACKED:
            self._emit(
                CoordinatorEventType.SPREAD_DELIVERY_CONFIRMED,
                events,
                (("sequence", update.sequence.value), ("receipt_id", update.receipt_id)),
            )
            self._feedback(FeedbackCode.SPREAD_SENT, (("sequence", update.sequence.value),))
        elif update.status is DeliveryStatus.REJECTED:
            # The next recapture replaces this logical position instead of
            # leaving an unfillable hole in the final ordered sequence.
            self._replacement_sequence = update.sequence.value
            self._feedback(
                FeedbackCode.PARSER_REJECTED,
                (("sequence", update.sequence.value), ("reason", update.reason)),
            )

    def _request_scan_stop(self, events: list[CoordinatorEvent]) -> None:
        assert self.scan_session is not None
        self.scanner.freeze()
        self._cutoff_sequence = self._last_sequence
        self._transition(DeviceFlowState.FLUSHING_UPLOADS, events)
        self._emit(
            CoordinatorEventType.SCAN_STOP_REQUESTED,
            events,
            (("through_sequence", self._cutoff_sequence),),
        )
        self._feedback(FeedbackCode.SCAN_STOPPING, (("through_sequence", self._cutoff_sequence),))
        self._advance_flushing(events)

    def _advance_flushing(self, events: list[CoordinatorEvent]) -> None:
        if self.scan_session is None or self._cutoff_sequence is None or self._seal_requested:
            return
        try:
            result = self.delivery.flush_through(self.scan_session.scan_session_id, self._cutoff_sequence)
        except RecoverablePortError:
            self._feedback(FeedbackCode.SERVER_RETRYING)
            return
        if result.scan_session_id != self.scan_session.scan_session_id or result.through_sequence != self._cutoff_sequence:
            self._fatal("flush lineage mismatch", events)
            return
        if result.status is FlushStatus.PENDING:
            return
        if result.status is FlushStatus.BLOCKED:
            self._recoverable(result.reason or "delivery flush blocked", "resume_scanning", events)
            return
        self._emit(
            CoordinatorEventType.UPLOAD_FLUSH_COMPLETED,
            events,
            (("through_sequence", self._cutoff_sequence),),
        )
        self._seal_requested = True
        try:
            finalization = self.scan_session_port.seal(
                self.scan_session.scan_session_id,
                self._cutoff_sequence,
            )
        except RecoverablePortError:
            self._seal_requested = False
            self._feedback(FeedbackCode.SERVER_RETRYING)
            return
        self._transition(DeviceFlowState.FINALIZING_DATAPACK, events)
        self._emit(CoordinatorEventType.DATAPACK_FINALIZING, events)
        self._feedback(FeedbackCode.FINALIZING)
        self._handle_finalization(finalization, events)

    def _poll_finalization(self, events: list[CoordinatorEvent]) -> None:
        assert self.scan_session is not None
        try:
            result = self.scan_session_port.get_status(self.scan_session.scan_session_id)
        except RecoverablePortError:
            self._feedback(FeedbackCode.SERVER_RETRYING)
            return
        self._handle_finalization(result, events)

    def _handle_finalization(self, result: FinalizeResult, events: list[CoordinatorEvent]) -> None:
        if self.scan_session is None or result.scan_session_id != self.scan_session.scan_session_id:
            return
        if result.datapack_id != self.scan_session.datapack_id:
            self._fatal("finalization datapack identity mismatch", events)
            return
        if result.status is FinalizeStatus.FINALIZING:
            return
        if result.status is FinalizeStatus.ERROR:
            self._recoverable(result.reason or "datapack finalization failed", "select", events)
            return
        self._emit(
            CoordinatorEventType.DATAPACK_READY,
            events,
            (("datapack_id", result.datapack_id.value), ("revision", result.revision.value)),
        )
        self._feedback(
            FeedbackCode.DATAPACK_SAVED,
            (("datapack_id", result.datapack_id.value), ("revision", result.revision.value)),
        )
        self._open_reading(
            result.datapack_id,
            f"reading-open:{result.scan_session_id.value}:{result.revision.value}",
            events,
        )

    def _open_reading(
        self,
        datapack_id: DatapackId,
        operation_id: str,
        events: list[CoordinatorEvent],
    ) -> None:
        self._transition(DeviceFlowState.OPENING_READING_SESSION, events)
        try:
            snapshot = self.reading.open(
                self.device_id, datapack_id, self.viewport_size, operation_id
            )
        except RecoverablePortError as exc:
            self._recoverable(str(exc), "select", events)
            return
        if snapshot.datapack_id != datapack_id:
            self._fatal("reading session datapack identity mismatch", events)
            return
        self.reading_snapshot = snapshot
        self._transition(DeviceFlowState.READING, events)
        details = (("reading_session_id", snapshot.reading_session_id.value), ("datapack_id", datapack_id.value))
        self._emit(CoordinatorEventType.READING_SESSION_OPENED, events, details)
        self._emit(CoordinatorEventType.READING_RESUMED, events, snapshot.cursor)
        self._feedback(FeedbackCode.READING_RESUMED, snapshot.cursor)

    def _handle_reading_input(self, input_event: DeviceInputEvent, events: list[CoordinatorEvent]) -> None:
        assert self.reading_snapshot is not None
        if input_event.control is DeviceControl.CONFIRM and input_event.action is InputAction.LONG:
            self._emit(CoordinatorEventType.RETURNED_TO_SELECTION, events)
            self.reading_snapshot = None
            self.scan_session = None
            self._transition(DeviceFlowState.CONNECTING, events)
            self._load_catalog(events)
            return
        if input_event.control is DeviceControl.LEVER:
            return
        try:
            snapshot = self.reading.send_command(
                self.reading_snapshot.reading_session_id,
                input_event.event_id,
                input_event.control,
                input_event.action,
            )
        except RecoverablePortError as exc:
            self._recoverable(str(exc), "select", events)
            return
        if snapshot.reading_session_id != self.reading_snapshot.reading_session_id:
            self._fatal("reading command session identity mismatch", events)
            return
        self.reading_snapshot = snapshot

    def _retry_recovery(self, events: list[CoordinatorEvent]) -> None:
        if self.connectivity is not None and not self.connectivity.current_status().online:
            self._feedback(FeedbackCode.SERVER_RETRYING)
            return
        if self._recovery == "retry_queue" and self.scan_session is not None and self._pending_queue is not None:
            sequence, artifact = self._pending_queue
            try:
                update = self.delivery.queue(self.scan_session.scan_session_id, sequence, artifact)
            except RecoverablePortError:
                self._feedback(FeedbackCode.SERVER_RETRYING)
                return
            except FatalPortError as exc:
                self._fatal(str(exc), events)
                return
            if update.sequence != sequence or update.artifact_id != artifact.artifact_id:
                self._fatal("delivery queue lineage mismatch", events)
                return
            self._pending_queue = None
            self._delivery_by_sequence[sequence.value] = update
            self._emit(
                CoordinatorEventType.SPREAD_QUEUED,
                events,
                (("sequence", sequence.value), ("artifact_id", artifact.artifact_id.value)),
            )
            self._handle_delivery_update(update, events)
            self.scanner.start(self.scan_session)
            self._transition(DeviceFlowState.SCANNING, events)
            return
        if self._recovery == "resume_scanning" and self.scan_session is not None:
            self._cutoff_sequence = None
            self._seal_requested = False
            self.scanner.start(self.scan_session)
            self._transition(DeviceFlowState.SCANNING, events)
            return
        self._transition(DeviceFlowState.CONNECTING, events)
        self._load_catalog(events)

    def _poll_connectivity(self, events: list[CoordinatorEvent]) -> None:
        if self.connectivity is None or self.state in {DeviceFlowState.STOPPED, DeviceFlowState.CANCELLING}:
            return
        self._handle_connectivity_events(self.connectivity.poll(), events)
        snapshot = self.connectivity.current_status()
        if snapshot.state is ConnectivityState.FATAL and self.state is not DeviceFlowState.STOPPED:
            self._fatal(snapshot.fatal_code or "server connectivity fatal", events)
            return
        if snapshot.online and self.state is DeviceFlowState.CONNECTING:
            self._load_catalog(events)

    def _handle_connectivity_events(
        self,
        connectivity_events: tuple[ConnectivityEvent, ...],
        events: list[CoordinatorEvent],
    ) -> None:
        mapping = {
            ConnectivityEventType.CONNECTING: CoordinatorEventType.SERVER_CONNECTING,
            ConnectivityEventType.SERVER_ONLINE: CoordinatorEventType.SERVER_ONLINE,
            ConnectivityEventType.SERVER_CONNECTION_LOST: CoordinatorEventType.SERVER_CONNECTION_LOST,
            ConnectivityEventType.SERVER_RETRY_SCHEDULED: CoordinatorEventType.SERVER_RETRY_SCHEDULED,
            ConnectivityEventType.SERVER_RECOVERED: CoordinatorEventType.SERVER_RECOVERED,
        }
        for event in connectivity_events:
            coordinator_type = mapping.get(event.event_type)
            details: list[tuple[str, str | int | float | bool | None]] = []
            if event.detail:
                details.append(("detail", event.detail))
            if event.retry_after_seconds is not None:
                details.append(("retry_after_seconds", event.retry_after_seconds))
            if coordinator_type is not None:
                self._emit(coordinator_type, events, tuple(details))
            if event.event_type is ConnectivityEventType.CONNECTING:
                self._feedback(FeedbackCode.SERVER_CONNECTING)
            elif event.event_type is ConnectivityEventType.SERVER_CONNECTION_LOST:
                self._feedback(FeedbackCode.SERVER_CONNECTION_LOST)
                if self.state is DeviceFlowState.SCANNING:
                    try:
                        self.scanner.freeze()
                    except Exception:
                        pass
                    self._recoverable("server connection lost", "resume_scanning", events)
                elif self.state not in {
                    DeviceFlowState.CONNECTING,
                    DeviceFlowState.RECOVERABLE_ERROR,
                    DeviceFlowState.STOPPED,
                    DeviceFlowState.CANCELLING,
                }:
                    self._recoverable("server connection lost", "connect", events)
            elif event.event_type is ConnectivityEventType.SERVER_RETRY_SCHEDULED:
                self._feedback(FeedbackCode.SERVER_RETRYING)
            elif event.event_type is ConnectivityEventType.SERVER_RECOVERED:
                self._feedback(FeedbackCode.SERVER_RECOVERED)
            elif event.event_type is ConnectivityEventType.SERVER_AUTH_FAILED:
                self._feedback(FeedbackCode.SERVER_AUTH_FAILED)

    def _announce_catalog_current(self, events: list[CoordinatorEvent], *, changed: bool) -> None:
        assert self.catalog is not None
        item = self.catalog.current
        details = (("index", self.catalog.index), ("title", item.title), ("kind", item.choice.kind.value))
        if changed:
            self._emit(CoordinatorEventType.CATALOG_HIGHLIGHT_CHANGED, events, details)
        self._feedback(FeedbackCode.SPEAK_CATALOG_TITLE, details)

    def _recoverable(self, reason: str, recovery: str, events: list[CoordinatorEvent]) -> None:
        self._recovery = recovery
        self._transition(DeviceFlowState.RECOVERABLE_ERROR, events)
        self._emit(CoordinatorEventType.RECOVERABLE_ERROR, events, (("reason", reason), ("recovery", recovery)))

    def _fatal(self, reason: str, events: list[CoordinatorEvent]) -> None:
        self._emit(CoordinatorEventType.FATAL_ERROR, events, (("reason", reason),))
        self._transition(DeviceFlowState.STOPPED, events)

    def _transition(self, state: DeviceFlowState, events: list[CoordinatorEvent]) -> None:
        if self.state is state:
            return
        previous = self.state
        self.state = state
        self._emit(
            CoordinatorEventType.STATE_CHANGED,
            events,
            (("from", previous.value), ("to", state.value)),
        )

    def _emit(
        self,
        event_type: CoordinatorEventType,
        events: list[CoordinatorEvent],
        details: tuple[tuple[str, str | int | float | bool | None], ...] = (),
    ) -> None:
        self._event_counter += 1
        events.append(
            CoordinatorEvent(
                event_id=f"{self.device_id.value}-event-{self._event_counter:08d}",
                event_type=event_type,
                at_monotonic=self.clock.monotonic(),
                state=self.state,
                details=details,
            )
        )

    def _feedback(
        self,
        code: FeedbackCode,
        details: tuple[tuple[str, str | int | float | bool | None], ...] = (),
    ) -> None:
        try:
            self.feedback.emit(FeedbackEvent(code=code, at_monotonic=self.clock.monotonic(), details=details))
        except Exception:
            # Feedback is observable best-effort output; it never mutates a
            # successful server/scanner state transition into another state.
            return

    def _remember_input(self, event_id: str) -> None:
        self._seen_inputs.add(event_id)
        self._input_order.append(event_id)
        if len(self._input_order) > self._INPUT_DEDUP_CAPACITY:
            expired = self._input_order.popleft()
            self._seen_inputs.discard(expired)
