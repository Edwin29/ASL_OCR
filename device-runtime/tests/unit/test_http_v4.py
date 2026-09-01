from __future__ import annotations

import json
from pathlib import Path

from asl_device.adapters.http_v4 import V4HttpClient
from asl_device.delivery_config import DeviceDeliveryConfig
from asl_device.delivery_domain import prepare_delivery
from asl_device.types import ClientSpreadSequence, DeviceId, ScanSessionId
from .test_delivery_v3b import make_artifact


class FakeResponse:
    status = 201

    def __init__(self, body):
        self._raw = json.dumps(body).encode("utf-8")

    def read(self, _limit):
        return self._raw

    def getheader(self, name):
        return "3" if name == "Retry-After" else None


class RecordingConnection:
    def __init__(self):
        self.method = None
        self.path = None
        self.headers = {}
        self.body = bytearray()
        self.closed = False
        self.response_body = {}

    def putrequest(self, method, path):
        self.method = method
        self.path = path

    def putheader(self, name, value):
        self.headers[name] = value

    def endheaders(self):
        pass

    def send(self, value):
        self.body.extend(value)

    def getresponse(self):
        return FakeResponse(self.response_body)

    def close(self):
        self.closed = True


def test_v4_http_client_streams_exact_content_length_and_required_parts(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    ready, _bundle = make_artifact(artifact_root)
    config = DeviceDeliveryConfig(tmp_path / "outbox.sqlite3", artifact_root, file_chunk_bytes=3)
    prepared = prepare_delivery(
        config,
        DeviceId("device-1"),
        ScanSessionId("scan-1"),
        ClientSpreadSequence(1),
        ready,
    )
    connection = RecordingConnection()
    connection.response_body = {
        "status": "acked",
        "receipt_id": "receipt-1",
        "scan_session_id": prepared.scan_session_id,
        "sequence": prepared.sequence,
        "artifact_id": prepared.artifact_id,
        "manifest_sha256": prepared.manifest_sha256,
        "upload_digest": prepared.upload_digest,
        "accepted_at": "2026-09-01T00:00:00+00:00",
    }
    client = V4HttpClient(
        "http://127.0.0.1:8420",
        "secret",
        config,
        allow_insecure_http=True,
        connection_factory=lambda _host, _port, _timeout: connection,
    )

    response = client.upload(prepared)

    assert response.status == 201
    assert response.retry_after_seconds == 3
    assert connection.method == "POST"
    assert connection.path == "/api/v1/scan-sessions/scan-1/spreads"
    assert int(connection.headers["Content-Length"]) == len(connection.body)
    assert connection.headers["Idempotency-Key"] == prepared.idempotency_key
    assert connection.headers["X-ASL-Upload-Digest"] == prepared.upload_digest
    assert "Transfer-Encoding" not in connection.headers
    assert connection.body.find(b'name="metadata"') < connection.body.find(b'name="manifest"')
    assert connection.body.count(b'name="bundle_file"') == len(prepared.files)
    assert b"left-image" in connection.body
    assert b"right-image" in connection.body
    assert connection.closed
