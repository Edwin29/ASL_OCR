from __future__ import annotations

import pytest

from asl_device.adapters.http_connectivity import HttpConnectivityTransport
from asl_device.connectivity import FatalConnectivityError, RetryableConnectivityError


class Wire:
    def __init__(self):
        self.calls = []
        self.responses = []

    def __call__(self, method, path, payload, headers, timeout):
        self.calls.append((method, path, payload, headers, timeout))
        return self.responses.pop(0)


def test_health_is_public_and_presence_is_authenticated() -> None:
    wire = Wire()
    wire.responses = [
        (200, {"status": "ok", "service": "asl-ocr-server", "api_versions": ["v1"], "schema_version": 3, "server_instance_id": "server-1"}),
        (201, {"accepted_heartbeat_sequence": 0}),
    ]
    adapter = HttpConnectivityTransport("https://server.test", "secret", transport=wire)
    adapter.probe_health()
    adapter.start_presence(
        device_id="device-1",
        presence_session_id="presence-1",
        boot_id="boot-1",
        client_version="0.1.0",
        platform="windows-laptop",
        capabilities=("scanner",),
    )
    assert "X-API-Key" not in wire.calls[0][3]
    assert wire.calls[1][3]["X-API-Key"] == "secret"
    assert "secret" not in repr(adapter)


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (401, {"code": "UNAUTHORIZED"}, FatalConnectivityError),
        (404, {"code": "NOT_FOUND"}, FatalConnectivityError),
        (503, {"code": "DATABASE_BUSY", "retryable": True}, RetryableConnectivityError),
    ],
)
def test_http_error_classification(status, body, error) -> None:
    wire = Wire()
    wire.responses = [(status, body)]
    adapter = HttpConnectivityTransport("https://server.test", "secret", transport=wire)
    with pytest.raises(error):
        adapter.start_presence(
            device_id="device-1",
            presence_session_id="presence-1",
            boot_id="boot-1",
            client_version="0.1.0",
            platform="windows-laptop",
            capabilities=(),
        )


def test_health_rejects_wrong_service_or_old_schema() -> None:
    wire = Wire()
    wire.responses = [
        (200, {"status": "ok", "service": "other", "api_versions": ["v1"], "schema_version": 3})
    ]
    adapter = HttpConnectivityTransport("https://server.test", "secret", transport=wire)
    with pytest.raises(FatalConnectivityError, match="not a healthy"):
        adapter.probe_health()
