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
    def __init__(self, session_id: str, artifact) -> None:
        self.session_id = session_id
        self.pending_artifact = artifact
        self.poll_events: list[tuple[object, ...]] = []
        self.callbacks: list[tuple[str, str, str | None]] = []
        self.cancelled = False
        self.closed = False

    def start(self):
        return ()

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
        return (SimpleNamespace(event_type=_value("delivery_confirmed")),)

    def delivery_rejected(self, artifact_id, reason):
        self.callbacks.append(("rejected", artifact_id.value, reason))
        self.pending_artifact = None
        return (SimpleNamespace(event_type=_value("parser_rejected")),)

    def cancel(self):
        self.cancelled = True
        return ()

    def close(self):
        self.closed = True


class FakeFactory:
    def __init__(self, artifact) -> None:
        self.artifact = artifact
        self.created: list[FakeEngine] = []

    def create(self, *, session_id: str, datapack_id: str):
        engine = FakeEngine(session_id, self.artifact)
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
    bridge.apply_delivery_update(ArtifactId("artifact-1"), _update(DeliveryStatus.QUEUED))
    bridge.apply_delivery_update(ArtifactId("artifact-1"), _update(DeliveryStatus.RETRYING))
    bridge.apply_delivery_update(
        ArtifactId("artifact-1"),
        _update(DeliveryStatus.ACKED, receipt="receipt-1"),
    )
    bridge.apply_delivery_update(
        ArtifactId("artifact-1"),
        _update(DeliveryStatus.ACKED, receipt="receipt-1"),
    )

    assert engine.callbacks == [
        ("queued", "artifact-1", None),
        ("retrying", "artifact-1", None),
        ("acked", "artifact-1", "receipt-1"),
    ]


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
