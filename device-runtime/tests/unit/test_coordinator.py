from __future__ import annotations

from asl_device.connectivity import (
    ConnectivityEvent,
    ConnectivityEventType,
    ConnectivitySnapshot,
    ConnectivityState,
)
from asl_device.coordinator import DeviceFlowCoordinator
from asl_device.events import CoordinatorEventType, FeedbackCode
from asl_device.types import (
    ArtifactId,
    ClientSpreadSequence,
    DatapackId,
    DatapackRevision,
    DeliveryStatus,
    DeliveryUpdate,
    DeviceControl,
    DeviceFlowState,
    DeviceId,
    DeviceInputEvent,
    FinalizeResult,
    FinalizeStatus,
    InputAction,
    ScanSessionId,
    ScannerArtifactReady,
    ScannerEvent,
    ScannerEventType,
)

from .fakes import (
    CollectingFeedback,
    FakeCatalogPort,
    FakeDeliveryPort,
    FakeReadingSessionPort,
    FakeScannerRuntime,
    FakeScanSessionPort,
    ManualClock,
    ready_entry,
)

SHA = "a" * 64


def make_coordinator(entries=(), connectivity=None):
    clock = ManualClock()
    catalog = FakeCatalogPort(tuple(entries))
    scan = FakeScanSessionPort()
    scanner = FakeScannerRuntime()
    delivery = FakeDeliveryPort()
    reading = FakeReadingSessionPort()
    feedback = CollectingFeedback()
    coordinator = DeviceFlowCoordinator(
        device_id=DeviceId("device-1"),
        viewport_size=10,
        clock=clock,
        catalog_port=catalog,
        scan_session_port=scan,
        scanner=scanner,
        delivery=delivery,
        reading=reading,
        feedback=feedback,
        connectivity=connectivity,
    )
    return coordinator, catalog, scan, scanner, delivery, reading, feedback


class FakeConnectivity:
    def __init__(self):
        self.state = ConnectivityState.STOPPED
        self.poll_events = []
        self.stopped = False

    def start(self):
        self.state = ConnectivityState.RETRY_WAIT
        return (ConnectivityEvent(ConnectivityEventType.CONNECTING, 0.0),)

    def poll(self):
        if not self.poll_events:
            return ()
        event, state = self.poll_events.pop(0)
        self.state = state
        return (event,)

    def current_status(self):
        return ConnectivitySnapshot(
            self.state,
            "presence-1",
            "boot-1",
            0,
            0,
            None,
            "server-1" if self.state is ConnectivityState.ONLINE else None,
        )

    def stop(self):
        self.stopped = True
        self.state = ConnectivityState.STOPPED
        return ()


def press(event_id: str, control: DeviceControl, action: InputAction = InputAction.SHORT) -> DeviceInputEvent:
    return DeviceInputEvent(event_id, control, action, 0.0)


def artifact_event(scan_session_id: ScanSessionId, event_id: str = "artifact-event", artifact_id: str = "artifact-1") -> ScannerEvent:
    artifact = ScannerArtifactReady(
        scan_session_id,
        ArtifactId(artifact_id),
        "spread-1",
        "frame-1",
        "ready/manifest.json",
        SHA,
    )
    return ScannerEvent(event_id, scan_session_id, ScannerEventType.ARTIFACT_READY, artifact=artifact)


def enter_scanning(coordinator: DeviceFlowCoordinator) -> None:
    coordinator.start()
    coordinator.handle_input(press("select", DeviceControl.CONFIRM))
    assert coordinator.state is DeviceFlowState.SCANNING


def test_start_loads_catalog_and_announces_current_title() -> None:
    coordinator, catalog, *_rest, feedback = make_coordinator((ready_entry(),))

    events = coordinator.start()

    assert coordinator.state is DeviceFlowState.SELECTING_DATAPACK
    assert catalog.list_calls == [DeviceId("device-1")]
    assert any(event.event_type is CoordinatorEventType.CATALOG_LOADED for event in events)
    assert feedback.events[-1].code is FeedbackCode.SPEAK_CATALOG_TITLE
    assert dict(feedback.events[-1].details)["title"] == "교재 A"


def test_connectivity_gate_defers_catalog_until_authenticated_online() -> None:
    connectivity = FakeConnectivity()
    coordinator, catalog, *_ = make_coordinator((ready_entry(),), connectivity=connectivity)

    started = coordinator.start()

    assert coordinator.state is DeviceFlowState.CONNECTING
    assert catalog.list_calls == []
    assert any(event.event_type is CoordinatorEventType.SERVER_CONNECTING for event in started)

    connectivity.poll_events.append(
        (ConnectivityEvent(ConnectivityEventType.SERVER_ONLINE, 1.0), ConnectivityState.ONLINE)
    )
    events = coordinator.poll()
    assert coordinator.state is DeviceFlowState.SELECTING_DATAPACK
    assert catalog.list_calls == [DeviceId("device-1")]
    assert any(event.event_type is CoordinatorEventType.CATALOG_LOADED for event in events)


def test_coordinator_stop_also_stops_connectivity() -> None:
    connectivity = FakeConnectivity()
    coordinator, *_ = make_coordinator(connectivity=connectivity)
    coordinator.start()
    coordinator.stop()
    assert connectivity.stopped


def test_existing_selection_opens_append_scan_without_creating_datapack() -> None:
    coordinator, catalog, scan, scanner, *_ = make_coordinator((ready_entry(),))
    coordinator.start()

    coordinator.handle_input(press("select", DeviceControl.CONFIRM))

    assert catalog.create_calls == []
    assert scan.open_calls == [
        (DeviceId("device-1"), DatapackId("book-a"), "select:scan-open")
    ]
    assert len(scanner.start_calls) == 1
    assert coordinator.state is DeviceFlowState.SCANNING


def test_empty_catalog_new_selection_creates_draft_then_opens_scan() -> None:
    coordinator, catalog, scan, scanner, *_ = make_coordinator()
    coordinator.start()

    coordinator.handle_input(press("select-new", DeviceControl.CONFIRM))

    assert catalog.create_calls == [(DeviceId("device-1"), "select-new:create")]
    assert scan.open_calls[0][1] == DatapackId("new-1")
    assert scanner.start_calls[0].datapack_id == DatapackId("new-1")


def test_duplicate_confirm_event_does_not_open_two_scan_sessions() -> None:
    coordinator, _catalog, scan, *_ = make_coordinator((ready_entry(),))
    coordinator.start()
    event = press("same-confirm", DeviceControl.CONFIRM)

    coordinator.handle_input(event)
    assert coordinator.handle_input(event) == ()

    assert len(scan.open_calls) == 1


def test_selection_event_id_is_reused_as_server_operation_lineage() -> None:
    coordinator, catalog, scan, *_ = make_coordinator()
    coordinator.start()

    coordinator.handle_input(press("hardware-confirm-42", DeviceControl.CONFIRM))

    assert catalog.create_calls[0][1] == "hardware-confirm-42:create"
    assert scan.open_calls[0][2] == "hardware-confirm-42:scan-open"


def test_catalog_long_move_is_clamped_and_only_changed_highlight_announces() -> None:
    coordinator, *_rest, feedback = make_coordinator(
        (ready_entry("a", "A"), ready_entry("b", "B"), ready_entry("c", "C"))
    )
    coordinator.start()
    before = len(feedback.events)

    coordinator.handle_input(press("down", DeviceControl.DOWN, InputAction.LONG))
    coordinator.handle_input(press("down-edge", DeviceControl.DOWN, InputAction.LONG))

    assert coordinator.catalog is not None
    assert coordinator.catalog.current.title == "새 데이터팩 추가"
    assert len(feedback.events) == before + 1


def test_artifact_is_queued_once_with_monotonic_sequence_and_stale_event_ignored() -> None:
    coordinator, _catalog, _scan, scanner, delivery, *_ = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)
    current = coordinator.scan_session
    assert current is not None
    scanner.events.append(artifact_event(ScanSessionId("old-scan"), "stale"))
    scanner.events.append(artifact_event(current.scan_session_id))

    coordinator.poll()
    coordinator.poll()

    assert len(delivery.queue_calls) == 1
    assert delivery.queue_calls[0][1] == ClientSpreadSequence(1)


def test_queue_outage_retries_same_artifact_and_sequence_without_recapture() -> None:
    coordinator, _catalog, _scan, scanner, delivery, *_ = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)
    current = coordinator.scan_session
    assert current is not None
    delivery.fail_queue_once = True
    scanner.events.append(artifact_event(current.scan_session_id))

    coordinator.poll()

    assert coordinator.state is DeviceFlowState.RECOVERABLE_ERROR
    assert scanner.freeze_calls == 1
    assert len(delivery.queue_calls) == 1

    coordinator.handle_input(press("retry-same-artifact", DeviceControl.CONFIRM))

    assert coordinator.state is DeviceFlowState.SCANNING
    assert len(delivery.queue_calls) == 2
    first = delivery.queue_calls[0]
    retried = delivery.queue_calls[1]
    assert retried[1] == first[1] == ClientSpreadSequence(1)
    assert retried[2] == first[2]
    assert len(scanner.start_calls) == 2


def test_confirm_freezes_before_flush_and_does_not_seal_until_ack() -> None:
    coordinator, _catalog, scan, scanner, delivery, reading, feedback = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)
    current = coordinator.scan_session
    assert current is not None
    scanner.events.append(artifact_event(current.scan_session_id))
    coordinator.poll()

    first = coordinator.handle_input(press("stop", DeviceControl.CONFIRM))

    assert scanner.freeze_calls == 1
    assert coordinator.state is DeviceFlowState.FLUSHING_UPLOADS
    assert scan.seal_calls == []
    assert any(event.event_type is CoordinatorEventType.SCAN_STOP_REQUESTED for event in first)

    delivery.acknowledge(1)
    events = coordinator.poll()

    assert scan.seal_calls == [(current.scan_session_id, 1)]
    assert coordinator.state is DeviceFlowState.FINALIZING_DATAPACK
    assert reading.open_calls == []
    assert any(event.event_type is CoordinatorEventType.UPLOAD_FLUSH_COMPLETED for event in events)
    assert FeedbackCode.SPREAD_SENT in [event.code for event in feedback.events]


def test_finalize_ready_opens_reading_at_server_cursor() -> None:
    coordinator, _catalog, scan, scanner, delivery, reading, feedback = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)
    current = coordinator.scan_session
    assert current is not None
    scanner.events.append(artifact_event(current.scan_session_id))
    coordinator.poll()
    delivery.acknowledge(1)
    coordinator.poll()
    coordinator.handle_input(press("stop", DeviceControl.CONFIRM))
    assert coordinator.state is DeviceFlowState.FINALIZING_DATAPACK
    scan.status_results.append(
        FinalizeResult(current.scan_session_id, current.datapack_id, FinalizeStatus.READY, DatapackRevision(2))
    )

    events = coordinator.poll()

    assert coordinator.state is DeviceFlowState.READING
    assert reading.open_calls == [
        (DeviceId("device-1"), DatapackId("book-a"), 10, "reading-open:scan-1:2")
    ]
    assert dict(coordinator.reading_snapshot.cursor) == {"page_index": 3, "node_index": 7}
    assert any(event.event_type is CoordinatorEventType.READING_RESUMED for event in events)
    assert feedback.events[-1].code is FeedbackCode.READING_RESUMED


def test_repeated_confirm_after_freeze_cannot_create_second_seal() -> None:
    coordinator, _catalog, scan, scanner, delivery, *_ = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)
    current = coordinator.scan_session
    assert current is not None
    scanner.events.append(artifact_event(current.scan_session_id))
    coordinator.poll()
    delivery.acknowledge(1)
    coordinator.poll()

    coordinator.handle_input(press("stop-1", DeviceControl.CONFIRM))
    coordinator.handle_input(press("stop-2", DeviceControl.CONFIRM))
    coordinator.poll()

    assert scanner.freeze_calls == 1
    assert len(scan.seal_calls) == 1


def test_rejected_delivery_blocks_seal_and_can_resume_same_scan() -> None:
    coordinator, _catalog, scan, scanner, delivery, *_ = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)
    current = coordinator.scan_session
    assert current is not None
    scanner.events.append(artifact_event(current.scan_session_id))
    coordinator.poll()
    delivery.reject(1)
    coordinator.poll()

    coordinator.handle_input(press("stop", DeviceControl.CONFIRM))

    assert coordinator.state is DeviceFlowState.RECOVERABLE_ERROR
    assert scan.seal_calls == []
    coordinator.handle_input(press("retry", DeviceControl.CONFIRM))
    assert coordinator.state is DeviceFlowState.SCANNING
    assert len(scanner.start_calls) == 2

    scanner.events.append(artifact_event(current.scan_session_id, "replacement-event", "artifact-2"))
    coordinator.poll()
    assert delivery.queue_calls[-1][1] == ClientSpreadSequence(1)
    delivery.acknowledge(1, "replacement-receipt")
    coordinator.poll()
    coordinator.handle_input(press("stop-after-recapture", DeviceControl.CONFIRM))
    assert scan.seal_calls == [(current.scan_session_id, 1)]


def test_stale_delivery_update_does_not_confirm_current_artifact() -> None:
    coordinator, _catalog, _scan, scanner, delivery, *_ = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)
    current = coordinator.scan_session
    assert current is not None
    scanner.events.append(artifact_event(current.scan_session_id))
    coordinator.poll()
    delivery.inject_update(
        DeliveryUpdate(
            ScanSessionId("old-scan"),
            ClientSpreadSequence(1),
            ArtifactId("artifact-1"),
            DeliveryStatus.ACKED,
            receipt_id="old-receipt",
        )
    )

    coordinator.poll()

    assert all(update.receipt_id != "old-receipt" for _, update in scanner.delivery_updates)


def test_stale_finalization_result_cannot_open_reading() -> None:
    coordinator, _catalog, scan, _scanner, _delivery, reading, *_ = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)
    current = coordinator.scan_session
    assert current is not None
    coordinator.handle_input(press("stop", DeviceControl.CONFIRM))
    assert coordinator.state is DeviceFlowState.FINALIZING_DATAPACK
    scan.status_results.append(
        FinalizeResult(
            ScanSessionId("old-scan"),
            current.datapack_id,
            FinalizeStatus.READY,
            DatapackRevision(9),
        )
    )

    coordinator.poll()

    assert coordinator.state is DeviceFlowState.FINALIZING_DATAPACK
    assert reading.open_calls == []


def test_reading_confirm_short_is_forwarded_and_long_returns_to_selection() -> None:
    coordinator, catalog, scan, scanner, delivery, reading, *_ = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)
    current = coordinator.scan_session
    assert current is not None
    scan.seal_result = FinalizeResult(
        current.scan_session_id,
        current.datapack_id,
        FinalizeStatus.READY,
        DatapackRevision(2),
    )
    coordinator.handle_input(press("stop", DeviceControl.CONFIRM))
    assert coordinator.state is DeviceFlowState.READING

    coordinator.handle_input(press("replay", DeviceControl.CONFIRM, InputAction.SHORT))
    assert reading.command_calls[-1][1:] == ("replay", DeviceControl.CONFIRM, InputAction.SHORT)

    events = coordinator.handle_input(press("back", DeviceControl.CONFIRM, InputAction.LONG))
    assert coordinator.state is DeviceFlowState.SELECTING_DATAPACK
    assert len(catalog.list_calls) == 2
    assert any(event.event_type is CoordinatorEventType.RETURNED_TO_SELECTION for event in events)


def test_duplicate_reading_command_event_is_forwarded_once() -> None:
    coordinator, _catalog, scan, _scanner, _delivery, reading, *_ = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)
    current = coordinator.scan_session
    assert current is not None
    scan.seal_result = FinalizeResult(
        current.scan_session_id,
        current.datapack_id,
        FinalizeStatus.READY,
        DatapackRevision(2),
    )
    coordinator.handle_input(press("stop", DeviceControl.CONFIRM))
    command = press("move-once", DeviceControl.DOWN)

    coordinator.handle_input(command)
    coordinator.handle_input(command)

    assert len(reading.command_calls) == 1


def test_scanner_guidance_is_semantic_feedback_not_server_command() -> None:
    coordinator, _catalog, _scan, scanner, delivery, _reading, feedback = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)
    current = coordinator.scan_session
    assert current is not None
    scanner.events.append(
        ScannerEvent(
            "guidance",
            current.scan_session_id,
            ScannerEventType.GUIDANCE,
            code="move_right",
        )
    )

    coordinator.poll()

    assert delivery.queue_calls == []
    assert feedback.events[-1].code is FeedbackCode.SCANNER_GUIDANCE
    assert dict(feedback.events[-1].details)["guidance_code"] == "move_right"


def test_stop_cancels_scanner_outside_reading_but_not_after_reading_entry() -> None:
    coordinator, _catalog, _scan, scanner, *_ = make_coordinator((ready_entry(),))
    enter_scanning(coordinator)

    coordinator.stop()

    assert coordinator.state is DeviceFlowState.STOPPED
    assert scanner.cancel_calls == 1


def test_feedback_failure_does_not_change_successful_domain_state() -> None:
    coordinator, *_rest = make_coordinator((ready_entry(),))
    coordinator.feedback = CollectingFeedback(fail=True)

    coordinator.start()
    coordinator.handle_input(press("select", DeviceControl.CONFIRM))

    assert coordinator.state is DeviceFlowState.SCANNING
