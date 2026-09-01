from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from asl_device.delivery import DurableDeliveryPort
from asl_device.delivery_config import DeviceDeliveryConfig
from asl_device.delivery_domain import V4HttpResponse, V4TransportError
from asl_device.delivery_store import DeliveryStore
from asl_device.protocols import FatalPortError
from asl_device.types import (
    ArtifactId,
    ClientSpreadSequence,
    DeliveryStatus,
    DeviceId,
    FlushStatus,
    ScanSessionId,
    ScannerArtifactReady,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class FakeTransport:
    def __init__(self, outcomes=()) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def upload(self, prepared):
        self.calls.append(prepared)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return outcome(prepared)
        return outcome


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_artifact(root: Path, scan="scan-1", artifact="artifact-1", spread="spread-1", frame="frame-1"):
    bundle = root / artifact
    (bundle / "left").mkdir(parents=True)
    (bundle / "right").mkdir()
    left = bundle / "left" / "uvdoc.jpg"
    right = bundle / "right" / "uvdoc.jpg"
    source = bundle / "source_frame.jpg"
    left.write_bytes(b"left-image")
    right.write_bytes(b"right-image")
    source.write_bytes(b"source-image")

    def record(path: Path):
        return {
            "path": path.relative_to(bundle).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha(path),
            "width": 64,
            "height": 96,
            "mime_type": "image/jpeg",
        }

    files = [record(source), record(left), record(right)]
    manifest = {
        "schema_version": "2.0",
        "artifact_id": artifact,
        "session_id": scan,
        "processing_job_id": "job-1",
        "spread_id": spread,
        "source_frame_id": frame,
        "files": files,
        "pages": {
            "left": {"side": "left", "files": {"uvdoc": files[1]}},
            "right": {"side": "right", "files": {"uvdoc": files[2]}},
        },
        "local_readiness": {"ready": True, "requires_both_pages": True},
    }
    manifest_path = bundle / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    ready = ScannerArtifactReady(
        ScanSessionId(scan),
        ArtifactId(artifact),
        spread,
        frame,
        str(manifest_path),
        sha(manifest_path),
    )
    return ready, bundle


def make_stack(tmp_path: Path, transport: FakeTransport, clock=None):
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    config = DeviceDeliveryConfig(tmp_path / "state" / "outbox.sqlite3", artifact_root)
    store = DeliveryStore(config.outbox_db_path)
    clock = clock or FakeClock()
    port = DurableDeliveryPort(DeviceId("device-1"), config, store, transport, clock)
    return config, store, port, clock


def ack(prepared):
    return V4HttpResponse(
        201,
        {
            "status": "acked",
            "receipt_id": "receipt-1",
            "scan_session_id": prepared.scan_session_id,
            "sequence": prepared.sequence,
            "artifact_id": prepared.artifact_id,
            "manifest_sha256": prepared.manifest_sha256,
            "upload_digest": prepared.upload_digest,
            "accepted_at": "2026-09-01T00:00:00+00:00",
        },
    )


def test_queue_is_durable_idempotent_and_does_not_call_network(tmp_path: Path) -> None:
    transport = FakeTransport()
    config, store, port, _clock = make_stack(tmp_path, transport)
    ready, _bundle = make_artifact(config.artifact_root)

    first = port.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), ready)
    replay = port.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), ready)

    assert first == replay
    assert first.status is DeliveryStatus.QUEUED
    assert transport.calls == []
    rows = store.list_scan("scan-1")
    assert len(rows) == 1
    assert rows[0]["idempotency_key"] == f"v3b-{rows[0]['upload_digest']}"


def test_same_sequence_different_artifact_is_fatal(tmp_path: Path) -> None:
    transport = FakeTransport()
    config, _store, port, _clock = make_stack(tmp_path, transport)
    first, _ = make_artifact(config.artifact_root)
    second, _ = make_artifact(
        config.artifact_root,
        artifact="artifact-2",
        spread="spread-2",
        frame="frame-2",
    )
    port.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), first)

    with pytest.raises(FatalPortError, match="different content"):
        port.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), second)


def test_timeout_retries_same_digest_after_backoff(tmp_path: Path) -> None:
    transport = FakeTransport([V4TransportError("lost"), ack])
    config, store, port, clock = make_stack(tmp_path, transport)
    ready, bundle = make_artifact(config.artifact_root)
    port.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), ready)

    first = port.pending_status(ScanSessionId("scan-1"))[0]
    assert first.status is DeliveryStatus.RETRYING
    assert bundle.exists()
    port.pending_status(ScanSessionId("scan-1"))
    assert len(transport.calls) == 1
    clock.value = config.retry_initial_seconds
    final = port.pending_status(ScanSessionId("scan-1"))[0]

    assert final.status is DeliveryStatus.ACKED
    assert transport.calls[0].upload_digest == transport.calls[1].upload_digest
    assert transport.calls[0].idempotency_key == transport.calls[1].idempotency_key
    assert not bundle.exists()
    assert store.list_scan("scan-1")[0]["attempt_count"] == 2


def test_valid_ack_is_committed_before_artifact_cleanup(tmp_path: Path) -> None:
    transport = FakeTransport([ack])
    config, store, port, _clock = make_stack(tmp_path, transport)
    ready, bundle = make_artifact(config.artifact_root)
    port.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), ready)

    update = port.pending_status(ScanSessionId("scan-1"))[0]

    assert update.status is DeliveryStatus.ACKED
    assert update.receipt_id == "receipt-1"
    assert store.list_scan("scan-1")[0]["status"] == "acked"
    assert not bundle.exists()


def test_mismatched_success_never_acks_or_deletes(tmp_path: Path) -> None:
    bad = lambda prepared: V4HttpResponse(
        201,
        {
            **ack(prepared).body,
            "artifact_id": "other-artifact",
        },
    )
    transport = FakeTransport([bad])
    config, store, port, _clock = make_stack(tmp_path, transport)
    ready, bundle = make_artifact(config.artifact_root)
    port.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), ready)

    with pytest.raises(FatalPortError, match="identity"):
        port.pending_status(ScanSessionId("scan-1"))

    row = store.list_scan("scan-1")[0]
    assert row["status"] == "retrying"
    assert row["receipt_id"] is None
    assert bundle.exists()


def test_deterministic_reject_blocks_flush_and_preserves_artifact(tmp_path: Path) -> None:
    transport = FakeTransport(
        [V4HttpResponse(422, {"code": "BUNDLE_HASH_MISMATCH", "message": "bad", "retryable": False})]
    )
    config, _store, port, _clock = make_stack(tmp_path, transport)
    ready, bundle = make_artifact(config.artifact_root)
    port.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), ready)

    result = port.flush_through(ScanSessionId("scan-1"), 1)

    assert result.status is FlushStatus.BLOCKED
    assert bundle.exists()


def test_restart_normalizes_sending_and_resends_same_key(tmp_path: Path) -> None:
    first_transport = FakeTransport()
    config, store, port, clock = make_stack(tmp_path, first_transport)
    ready, _bundle = make_artifact(config.artifact_root)
    port.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), ready)
    original = store.next_nonterminal("scan-1")
    claimed = store.claim(original["outbox_id"])
    assert claimed["status"] == "sending"

    restarted_store = DeliveryStore(config.outbox_db_path)
    restarted = DurableDeliveryPort(
        DeviceId("device-1"), config, restarted_store, FakeTransport([ack]), clock
    )
    update = restarted.pending_status(ScanSessionId("scan-1"))[0]

    assert update.status is DeliveryStatus.ACKED
    assert restarted_store.list_scan("scan-1")[0]["attempt_count"] == 2


def test_restart_after_success_before_local_ack_commit_replays_same_key(tmp_path: Path) -> None:
    transport = FakeTransport([ack])
    config, store, _port, clock = make_stack(tmp_path, transport)
    ready, bundle = make_artifact(config.artifact_root)

    def crash():
        raise SystemExit("simulated process exit before ACK commit")

    crashing = DurableDeliveryPort(
        DeviceId("device-1"),
        config,
        store,
        transport,
        clock,
        before_ack_commit=crash,
    )
    crashing.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), ready)
    with pytest.raises(SystemExit, match="before ACK"):
        crashing.pending_status(ScanSessionId("scan-1"))
    assert store.list_scan("scan-1")[0]["status"] == "sending"
    assert bundle.exists()

    replay_transport = FakeTransport([ack])
    restarted_store = DeliveryStore(config.outbox_db_path)
    restarted = DurableDeliveryPort(
        DeviceId("device-1"), config, restarted_store, replay_transport, clock
    )
    update = restarted.pending_status(ScanSessionId("scan-1"))[0]

    assert update.status is DeliveryStatus.ACKED
    assert transport.calls[0].idempotency_key == replay_transport.calls[0].idempotency_key
    assert not bundle.exists()


def test_file_mutation_after_queue_becomes_terminal_local_reject(tmp_path: Path) -> None:
    transport = FakeTransport()
    config, _store, port, _clock = make_stack(tmp_path, transport)
    ready, bundle = make_artifact(config.artifact_root)
    port.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), ready)
    (bundle / "left" / "uvdoc.jpg").write_bytes(b"mutated")

    update = port.pending_status(ScanSessionId("scan-1"))[0]

    assert update.status is DeliveryStatus.REJECTED
    assert transport.calls == []
    assert bundle.exists()


def test_flush_requires_every_position_to_be_acked(tmp_path: Path) -> None:
    transport = FakeTransport([ack])
    config, _store, port, _clock = make_stack(tmp_path, transport)
    ready, _bundle = make_artifact(config.artifact_root)
    port.queue(ScanSessionId("scan-1"), ClientSpreadSequence(1), ready)

    assert port.flush_through(ScanSessionId("scan-1"), 2).status is FlushStatus.PENDING
    assert port.flush_through(ScanSessionId("scan-1"), 1).status is FlushStatus.FLUSHED
