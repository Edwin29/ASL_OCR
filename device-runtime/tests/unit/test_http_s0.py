from __future__ import annotations

import pytest

from asl_device.adapters.http_s0 import (
    S0CatalogHttpAdapter,
    S0HttpClient,
    S0ReadingHttpAdapter,
    S0ScanHttpAdapter,
)
from asl_device.protocols import FatalPortError, RecoverablePortError
from asl_device.types import (
    DatapackId,
    DeviceControl,
    DeviceId,
    InputAction,
    ReadingSessionId,
    ScanSessionId,
)


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, path, payload, headers):
        self.calls.append((method, path, payload, headers))
        return self.responses.pop(0)


def test_catalog_and_scan_operations_forward_stable_idempotency_keys():
    transport = FakeTransport([
        (201, {"datapack_id": "draft-1", "title": "Draft", "status": "draft", "revision": None}),
        (201, {"scan_session_id": "scan-1", "datapack_id": "draft-1", "status": "open"}),
    ])
    client = S0HttpClient("http://server", "secret", transport=transport)
    catalog = S0CatalogHttpAdapter(client)
    scan = S0ScanHttpAdapter(client)

    created = catalog.create_datapack(DeviceId("device-1"), "confirm-1:create")
    opened = scan.open(DeviceId("device-1"), created.datapack_id, "confirm-1:scan-open")

    assert opened.scan_session_id == ScanSessionId("scan-1")
    assert transport.calls[0][3]["Idempotency-Key"] == "confirm-1:create"
    assert transport.calls[1][3]["Idempotency-Key"] == "confirm-1:scan-open"


def test_reading_open_and_command_map_wire_response():
    snapshot = {
        "reading_session_id": "reading-1",
        "datapack_id": "book-a",
        "cursor": {"page_index": 2, "node_index": 4, "table_row": None, "generation": 0},
        "braille_frame": {"cells": [1, 2, 3]},
        "audio": {"audio_ref": "s0-audio:abc"},
    }
    transport = FakeTransport([(201, snapshot), (200, snapshot)])
    client = S0HttpClient("http://server", "secret", transport=transport)
    reading = S0ReadingHttpAdapter(client)

    opened = reading.open(DeviceId("device-1"), DatapackId("book-a"), 10, "reading-open-1")
    replay = reading.send_command(
        ReadingSessionId("reading-1"),
        "button-event-1",
        DeviceControl.PAGE_NEXT,
        InputAction.SHORT,
    )

    assert opened.braille_cells == (1, 2, 3)
    assert opened.audio_ref == "s0-audio:abc"
    assert replay.cursor == (
        ("page_index", 2),
        ("node_index", 4),
        ("table_row", None),
        ("generation", 0),
    )
    assert transport.calls[0][3]["Idempotency-Key"] == "reading-open-1"
    assert transport.calls[1][2]["button"] == "PAGE_NEXT"
    assert transport.calls[1][2]["command_id"] == "button-event-1"


def test_sealing_maps_to_finalizing_without_claiming_ready():
    transport = FakeTransport([(
        202,
        {
            "scan_session_id": "scan-1",
            "datapack_id": "draft-1",
            "status": "sealing",
            "through_sequence": 3,
        },
    )])
    client = S0HttpClient("http://server", "secret", transport=transport)

    result = client.seal(ScanSessionId("scan-1"), 3)

    assert result.status.value == "finalizing"
    assert result.revision is None


def test_s1_sealed_status_maps_to_ready_with_published_revision():
    transport = FakeTransport([(
        200,
        {
            "scan_session_id": "scan-1",
            "datapack_id": "book-a",
            "status": "sealed",
            "published_revision": 2,
            "revision": 2,
        },
    )])
    client = S0HttpClient("http://server", "secret", transport=transport)

    result = client.get_status(ScanSessionId("scan-1"))

    assert result.status.value == "ready"
    assert result.revision.value == 2


@pytest.mark.parametrize(
    ("status", "body", "error_type"),
    [
        (503, {"code": "DATABASE_BUSY", "message": "busy", "retryable": True}, RecoverablePortError),
        (409, {"code": "SCAN_BUSY", "message": "busy", "retryable": False}, RecoverablePortError),
        (401, {"code": "UNAUTHORIZED", "message": "bad key", "retryable": False}, FatalPortError),
    ],
)
def test_http_errors_map_to_coordinator_error_classes(status, body, error_type):
    client = S0HttpClient("http://server", "secret", transport=FakeTransport([(status, body)]))
    with pytest.raises(error_type):
        client.get_status(ScanSessionId("scan-1"))
