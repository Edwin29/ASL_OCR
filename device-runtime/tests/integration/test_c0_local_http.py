from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import pytest

pytest.importorskip("flask")
werkzeug_serving = pytest.importorskip("werkzeug.serving")
pytest.importorskip("document_parser.server.s0_http")

from asl_device.adapters.http_connectivity import HttpConnectivityTransport
from asl_device.connectivity import ConnectivityEventType, DeviceConnectivitySupervisor
from asl_device.connectivity_config import DeviceConnectivityConfig
from asl_device.types import DeviceId
from document_parser.server.c0_presence import DevicePresenceService
from document_parser.server.s0_http import create_app
from document_parser.server.s0_services import S0ControlPlane
from document_parser.server.s0_store import S0Store
from tests.unit.fakes import ManualClock


class LocalServer:
    def __init__(self, app, port=0):
        self.server = werkzeug_serving.make_server("127.0.0.1", port, app, threaded=True)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)


def test_laptop_loopback_server_stop_restart_recovers_same_presence_session() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        store = S0Store(root / "state.sqlite3", root / "datapacks")
        presence = DevicePresenceService(store)

        first_server = LocalServer(create_app(S0ControlPlane(store), "secret", presence_service=presence))
        first_server.start()
        secret = root / "secret.txt"
        secret.write_text("secret", encoding="utf-8")
        config = DeviceConnectivityConfig(
            DeviceId("laptop-device-1"),
            f"http://127.0.0.1:{first_server.port}",
            secret,
            allow_insecure_http=True,
        )
        clock = ManualClock()
        supervisor = DeviceConnectivitySupervisor(
            config,
            HttpConnectivityTransport(config.server_base_url, config.load_api_key(), timeout_seconds=1),
            clock,
            presence_session_id="presence-laptop-1",
            boot_id="process-laptop-1",
            random_unit=lambda: 0.5,
        )
        try:
            supervisor.start()
            assert supervisor.poll()[0].event_type is ConnectivityEventType.SERVER_ONLINE
            assert presence.get_device("laptop-device-1")["status"] == "online"

            port = first_server.port
            first_server.stop()
            clock.advance(config.heartbeat_interval_seconds)
            lost = supervisor.poll()
            assert lost[0].event_type is ConnectivityEventType.SERVER_CONNECTION_LOST

            restarted_presence = DevicePresenceService(store)
            restarted = LocalServer(
                create_app(S0ControlPlane(store), "secret", presence_service=restarted_presence),
                port=port,
            )
            restarted.start()
            try:
                clock.advance(config.retry_initial_seconds)
                recovered = supervisor.poll()
                assert recovered[0].event_type is ConnectivityEventType.SERVER_RECOVERED
                view = restarted_presence.get_device("laptop-device-1")
                assert view["status"] == "online"
                assert view["active_session_count"] == 1
            finally:
                restarted.stop()
        finally:
            if first_server.thread.is_alive():
                first_server.stop()
