from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

pytest.importorskip("document_parser.server.v4_upload")
werkzeug_serving = pytest.importorskip("werkzeug.serving")
Image = pytest.importorskip("PIL.Image")

from asl_device.adapters.http_v4 import V4HttpClient
from asl_device.delivery import DurableDeliveryPort
from asl_device.delivery_config import DeviceDeliveryConfig
from asl_device.delivery_domain import V4TransportError
from asl_device.delivery_store import DeliveryStore
from asl_device.types import (
    ArtifactId,
    ClientSpreadSequence,
    DeliveryStatus,
    DeviceId,
    ScanSessionId,
    ScannerArtifactReady,
)
from document_parser.server.s0_http import create_app
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store
from document_parser.server.s1_domain import S1Config
from document_parser.server.s1_services import S1Pipeline
from document_parser.server.v4_domain import V4Config
from document_parser.server.v4_upload import V4UploadService


class UnusedFragmentParser:
    def parse(self, *_args, **_kwargs):
        raise AssertionError("V3-B ACK does not run the parser worker")


class LocalServer:
    def __init__(self, app) -> None:
        self.server = werkzeug_serving.make_server("127.0.0.1", 0, app, threaded=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.thread.join(timeout=5)


class LoseFirstResponse:
    def __init__(self, client: V4HttpClient) -> None:
        self.client = client
        self.lost = False

    def upload(self, prepared):
        response = self.client.upload(prepared)
        if not self.lost:
            self.lost = True
            raise V4TransportError("simulated response loss after server commit")
        return response


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bundle(root: Path, session_id: str) -> ScannerArtifactReady:
    root.mkdir(parents=True)
    records = []
    pages = {}
    source = root / "source_frame.jpg"
    Image.new("RGB", (80, 60), "black").save(source, quality=90)

    def record(path: Path):
        with Image.open(path) as image:
            width, height = image.size
        value = {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha(path),
            "size_bytes": path.stat().st_size,
            "width": width,
            "height": height,
            "mime_type": "image/jpeg",
        }
        records.append(value)
        return value

    record(source)
    for side, color in (("left", "white"), ("right", "gray")):
        side_dir = root / side
        side_dir.mkdir()
        image = side_dir / "uvdoc.jpg"
        Image.new("RGB", (64, 96), color).save(image, quality=95)
        uvdoc = record(image)
        pages[side] = {
            "side": side,
            "source_frame_id": "frame-1",
            "files": {"uvdoc": uvdoc},
            "local_readiness": {"ready": True},
        }
    manifest = {
        "schema_version": "2.0",
        "artifact_id": "artifact-1",
        "session_id": session_id,
        "processing_job_id": "job-1",
        "spread_id": "spread-1",
        "source_frame_id": "frame-1",
        "files": records,
        "pages": pages,
        "local_readiness": {"ready": True, "requires_both_pages": True},
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return ScannerArtifactReady(
        ScanSessionId(session_id),
        ArtifactId("artifact-1"),
        "spread-1",
        "frame-1",
        str(manifest_path),
        _sha(manifest_path),
    )


def test_response_loss_then_adapter_restart_replays_one_server_spread(tmp_path: Path) -> None:
    server_store = S0Store(tmp_path / "server.sqlite3", tmp_path / "server-datapacks")
    s0 = S0ControlPlane(server_store)
    datapack = s0.create_datapack("device-1", "create-1")
    scan = s0.open_scan("device-1", datapack.datapack_id, "open-1")
    s1_config = S1Config.under(server_store.datapacks_root)
    pipeline = S1Pipeline(server_store, s0, s1_config, UnusedFragmentParser())
    v4 = V4UploadService(server_store, pipeline, V4Config.from_s1(s1_config))
    app = create_app(s0, "secret", pipeline, v4_service=v4)

    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    ready = _write_bundle(artifact_root / "artifact-1", scan.scan_session_id)
    config = DeviceDeliveryConfig(tmp_path / "device-outbox.sqlite3", artifact_root)
    clock = lambda: 0.0

    with LocalServer(app) as server:
        first_client = V4HttpClient(
            server.origin,
            "secret",
            config,
            allow_insecure_http=True,
        )
        first_store = DeliveryStore(config.outbox_db_path)
        first = DurableDeliveryPort(
            DeviceId("device-1"),
            config,
            first_store,
            LoseFirstResponse(first_client),
            clock,
        )
        first.queue(ScanSessionId(scan.scan_session_id), ClientSpreadSequence(1), ready)
        uncertain = first.pending_status(ScanSessionId(scan.scan_session_id))[0]
        assert uncertain.status is DeliveryStatus.RETRYING
        assert (artifact_root / "artifact-1").is_dir()

        restarted_store = DeliveryStore(config.outbox_db_path)
        restarted_client = V4HttpClient(
            server.origin,
            "secret",
            config,
            allow_insecure_http=True,
        )
        restarted = DurableDeliveryPort(
            DeviceId("device-1"), config, restarted_store, restarted_client, clock
        )
        accepted = restarted.pending_status(ScanSessionId(scan.scan_session_id))[0]

    assert accepted.status is DeliveryStatus.ACKED
    assert accepted.receipt_id
    assert not (artifact_root / "artifact-1").exists()
    spreads = pipeline.list_spreads(scan.scan_session_id)
    assert len(spreads) == 1
    assert len(spreads[0]["fragments"]) == 2
    row = restarted_store.list_scan(scan.scan_session_id)[0]
    assert row["attempt_count"] == 2
    assert row["receipt_id"] == spreads[0]["receipt_id"]
