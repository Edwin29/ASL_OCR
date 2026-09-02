from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from asl_device.adapters.book_scanner_runtime import BookScannerRuntimeAdapter
from asl_device.protocols import FatalPortError
from asl_device.types import (
    ArtifactId,
    ClientSpreadSequence,
    DatapackId,
    DeliveryStatus,
    DeliveryUpdate,
    ScanSessionId,
    ScanSessionRef,
    ScannerEventType,
)


def _value(value: str):
    return SimpleNamespace(value=value)


class FakeEngine:
    def __init__(self, session_id: str, artifact, start_events=()) -> None:
        self.session_id = session_id
        self.pending_artifact = artifact
        self.start_events = start_events
        self.poll_events: list[tuple[object, ...]] = []
        self.callbacks: list[tuple[str, str, str | None]] = []
        self.cancelled = False
        self.closed = False

    def start(self):
        return self.start_events

    def poll(self):
        return self.poll_events.pop(0) if self.poll_events else ()

    def delivery_queued(self, artifact_id):
        self.callbacks.append(("queued", artifact_id.value, None))
        return ()

    def delivery_retrying(self, artifact_id):
        self.callbacks.append(("retrying", artifact_id.value, None))
        return ()

    def delivery_confirmed(self, artifact_id, receipt_id):
        self.callbacks.append(("acked", artifact_id.value, receipt_id))
        self.pending_artifact = None
        return (
            SimpleNamespace(
                event_type=_value("delivery_confirmed"),
                event_id="delivery-confirmed-1",
                session_id=self.session_id,
                details=(),
            ),
            SimpleNamespace(
                event_type=_value("opaque_identity_collection_started"),
                event_id="page-change-started-1",
                session_id=self.session_id,
                source_frame_id=_value("frame-1"),
                spread_id=_value("spread-1"),
                details=(
                    ("identity_role", "page_change"),
                    ("query_sample_count", 5),
                    ("pair_digest", "must-not-leak"),
                ),
            ),
        )

    def delivery_rejected(self, artifact_id, reason):
        self.callbacks.append(("rejected", artifact_id.value, reason))
        self.pending_artifact = None
        return (
            SimpleNamespace(
                event_type=_value("parser_rejected"),
                event_id="parser-rejected-1",
                session_id=self.session_id,
                details=(),
            ),
        )

    def cancel(self):
        self.cancelled = True
        return ()

    def close(self):
        self.closed = True


class FakeFactory:
    def __init__(self, artifact, start_events=()) -> None:
        self.artifact = artifact
        self.start_events = start_events
        self.created: list[FakeEngine] = []

    def create(self, *, session_id: str, datapack_id: str):
        engine = FakeEngine(session_id, self.artifact, self.start_events)
        self.created.append(engine)
        return engine


def _fixture(tmp_path: Path):
    artifact_id = "artifact-1"
    root = tmp_path / "ready"
    artifact_root = root / artifact_id
    artifact_root.mkdir(parents=True)
    manifest = artifact_root / "manifest.json"
    manifest.write_text('{"schema_version":"2.0"}', encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    artifact = SimpleNamespace(
        artifact_id=_value(artifact_id),
        spread_id=_value("spread-1"),
        source_frame_id=_value("frame-1"),
        manifest_path=str(manifest.resolve()),
        manifest_sha256=digest,
    )
    event = SimpleNamespace(
        event_type=_value("artifact_ready"),
        event_id="scanner-event-1",
        session_id="scan-1",
        artifact_id=_value(artifact_id),
        spread_id=_value("spread-1"),
        source_frame_id=_value("frame-1"),
        details=(),
    )
    return root, artifact, event


def _session() -> ScanSessionRef:
    return ScanSessionRef(ScanSessionId("scan-1"), DatapackId("datapack-1"))


def _update(status: DeliveryStatus, *, receipt: str | None = None, reason: str | None = None):
    return DeliveryUpdate(
        ScanSessionId("scan-1"),
        ClientSpreadSequence(1),
        ArtifactId("artifact-1"),
        status,
        receipt,
        reason,
    )


def test_artifact_event_and_delivery_callbacks_preserve_lineage(tmp_path: Path) -> None:
    root, artifact, event = _fixture(tmp_path)
    factory = FakeFactory(artifact)
    bridge = BookScannerRuntimeAdapter(factory, root)
    bridge.start(_session())
    engine = factory.created[0]
    engine.poll_events.append((event,))

    mapped = bridge.poll()

    assert len(mapped) == 1
    assert mapped[0].event_type is ScannerEventType.ARTIFACT_READY
    assert mapped[0].artifact is not None
    assert mapped[0].artifact.artifact_id == ArtifactId("artifact-1")
    assert bridge.apply_delivery_update(
        ArtifactId("artifact-1"), _update(DeliveryStatus.QUEUED)
    ) == ()
    assert bridge.apply_delivery_update(
        ArtifactId("artifact-1"), _update(DeliveryStatus.RETRYING)
    ) == ()
    callback_events = bridge.apply_delivery_update(
        ArtifactId("artifact-1"),
        _update(DeliveryStatus.ACKED, receipt="receipt-1"),
    )
    repeated_events = bridge.apply_delivery_update(
        ArtifactId("artifact-1"),
        _update(DeliveryStatus.ACKED, receipt="receipt-1"),
    )

    assert engine.callbacks == [
        ("queued", "artifact-1", None),
        ("retrying", "artifact-1", None),
        ("acked", "artifact-1", "receipt-1"),
    ]
    assert len(callback_events) == 1
    assert callback_events[0].event_type is ScannerEventType.DIAGNOSTIC
    assert callback_events[0].code == "identity_collection_started"
    assert dict(callback_events[0].details) == {
        "source_frame_id": "frame-1",
        "spread_id": "spread-1",
        "identity_role": "page_change",
        "query_sample_count": 5,
    }
    assert repeated_events == ()


def test_start_failure_event_is_fatal_and_closes_engine(tmp_path: Path) -> None:
    root, artifact, _event = _fixture(tmp_path)
    start_failure = SimpleNamespace(
        event_type=_value("session_error"),
        event_id="start-failure-1",
        session_id="scan-1",
        reason=_value("camera_unavailable"),
        details=(),
    )
    factory = FakeFactory(artifact, (start_failure,))
    bridge = BookScannerRuntimeAdapter(factory, root)

    with pytest.raises(FatalPortError, match="camera_unavailable"):
        bridge.start(_session())

    assert factory.created[0].closed is True
    assert bridge.poll() == ()


def test_mismatched_artifact_event_is_fatal(tmp_path: Path) -> None:
    root, artifact, event = _fixture(tmp_path)
    event.artifact_id = _value("different")
    factory = FakeFactory(artifact)
    bridge = BookScannerRuntimeAdapter(factory, root)
    bridge.start(_session())
    factory.created[0].poll_events.append((event,))

    with pytest.raises(FatalPortError, match="lineage"):
        bridge.poll()


def test_freeze_waits_for_pending_terminal_then_closes_engine(tmp_path: Path) -> None:
    root, artifact, event = _fixture(tmp_path)
    factory = FakeFactory(artifact)
    bridge = BookScannerRuntimeAdapter(factory, root)
    bridge.start(_session())
    engine = factory.created[0]
    engine.poll_events.append((event,))
    bridge.poll()

    bridge.freeze()
    assert not engine.closed
    assert bridge.poll() == ()

    bridge.apply_delivery_update(
        ArtifactId("artifact-1"),
        _update(DeliveryStatus.ACKED, receipt="receipt-1"),
    )

    assert engine.cancelled
    assert engine.closed


def test_guidance_and_fatal_events_map_without_artifacts(tmp_path: Path) -> None:
    root, artifact, _event = _fixture(tmp_path)
    factory = FakeFactory(artifact)
    bridge = BookScannerRuntimeAdapter(factory, root)
    bridge.start(_session())
    engine = factory.created[0]
    engine.poll_events.append(
        (
            SimpleNamespace(
                event_type=_value("guidance_requested"),
                event_id="guidance-1",
                session_id="scan-1",
                reason=_value("move_left"),
                details=(),
            ),
            SimpleNamespace(
                event_type=_value("session_error"),
                event_id="fatal-1",
                session_id="scan-1",
                reason=_value("camera_unavailable"),
                details=(),
            ),
        )
    )

    events = bridge.poll()

    assert [(event.event_type, event.code) for event in events] == [
        (ScannerEventType.GUIDANCE, "move_left"),
        (ScannerEventType.FATAL, "camera_unavailable"),
    ]


def test_source_exhausted_maps_with_session_lineage_and_details(tmp_path: Path) -> None:
    root, artifact, _event = _fixture(tmp_path)
    factory = FakeFactory(artifact)
    bridge = BookScannerRuntimeAdapter(factory, root)
    bridge.start(_session())
    factory.created[0].poll_events.append(
        (
            SimpleNamespace(
                event_type=_value("source_exhausted"),
                event_id="source-exhausted-1",
                session_id="scan-1",
                details=(("frames_received", 90),),
            ),
        )
    )

    events = bridge.poll()

    assert len(events) == 1
    assert events[0].event_type is ScannerEventType.SOURCE_EXHAUSTED
    assert events[0].scan_session_id == ScanSessionId("scan-1")
    assert events[0].artifact is None
    assert dict(events[0].details) == {"frames_received": 90}


def test_identity_diagnostics_are_bounded_and_missing_observations_are_not_progress(
    tmp_path: Path,
) -> None:
    root, artifact, _event = _fixture(tmp_path)
    factory = FakeFactory(artifact)
    bridge = BookScannerRuntimeAdapter(factory, root)
    bridge.start(_session())
    factory.created[0].poll_events.append(
        (
            SimpleNamespace(
                event_type=_value("candidate_selected"),
                event_id="candidate-1",
                session_id="scan-1",
                source_frame_id=_value("frame-1866"),
                spread_id=_value("spread-314-315"),
                details=(("tenengrad", 123.0), ("identity_role", "candidate_verification")),
            ),
            SimpleNamespace(
                event_type=_value("opaque_identity_collection_started"),
                event_id="identity-started-1",
                session_id="scan-1",
                source_frame_id=_value("frame-1866"),
                spread_id=_value("spread-314-315"),
                details=(
                    ("identity_role", "candidate_verification"),
                    ("query_sample_count", 5),
                    ("provenance", "private"),
                ),
            ),
            SimpleNamespace(
                event_type=_value("opaque_identity_observed"),
                event_id="identity-missing-1",
                session_id="scan-1",
                source_frame_id=_value("frame-1872"),
                spread_id=_value("spread-314-315"),
                details=(("valid", False), ("valid_observations", 0)),
            ),
            SimpleNamespace(
                event_type=_value("opaque_identity_observed"),
                event_id="identity-valid-1",
                session_id="scan-1",
                source_frame_id=_value("frame-1890"),
                spread_id=_value("spread-314-315"),
                details=(
                    ("valid", True),
                    ("identity_role", "candidate_verification"),
                    ("valid_observations", 4),
                    ("query_sample_count", 5),
                    ("pair_digest", "secret-digest"),
                    ("left_token_length", 3),
                ),
            ),
            SimpleNamespace(
                event_type=_value("opaque_identity_aborted"),
                event_id="identity-aborted-1",
                session_id="scan-1",
                source_frame_id=_value("frame-1896"),
                spread_id=_value("spread-314-315"),
                details=(
                    ("terminal_reason", "content_occluded"),
                    ("identity_role", "candidate_verification"),
                    ("valid_observations", 4),
                    ("missing_observations", 0),
                    ("query_sample_count", 5),
                    ("pair_digest", "secret-digest"),
                ),
            ),
        )
    )

    events = bridge.poll()

    assert [event.code for event in events] == [
        "candidate_selected",
        "identity_collection_started",
        "identity_collection_progress",
        "identity_collection_aborted",
    ]
    assert all(event.event_type is ScannerEventType.DIAGNOSTIC for event in events)
    progress = dict(events[2].details)
    aborted = dict(events[3].details)
    assert progress["valid_observations"] == 4
    assert progress["identity_role"] == "candidate_verification"
    assert progress["query_sample_count"] == 5
    assert aborted["terminal_reason"] == "content_occluded"
    assert aborted["identity_role"] == "candidate_verification"
    assert "pair_digest" not in progress
    assert "pair_digest" not in aborted
    assert "left_token_length" not in progress
