from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from asl_device.connectivity import (
    ConnectivityEventType,
    ConnectivityState,
    DeviceConnectivitySupervisor,
    FatalConnectivityError,
    RetryableConnectivityError,
)
from asl_device.connectivity_config import DeviceConnectivityConfig
from asl_device.types import DeviceId

from .fakes import ManualClock


class FakeTransport:
    def __init__(self) -> None:
        self.probe_failures = 0
        self.heartbeat_failures = 0
        self.auth_failure = False
        self.started = []
        self.heartbeats = []
        self.disconnects = []
        self.accepted_sequence = 0

    def probe_health(self):
        if self.probe_failures:
            self.probe_failures -= 1
            raise RetryableConnectivityError("server unavailable")
        return {"server_instance_id": "server-1"}

    def start_presence(self, **kwargs):
        self.started.append(kwargs)
        if self.auth_failure:
            raise FatalConnectivityError("bad key", code="SERVER_AUTH_FAILED")
        return {"accepted_heartbeat_sequence": self.accepted_sequence}

    def heartbeat(self, **kwargs):
        self.heartbeats.append(kwargs)
        if self.heartbeat_failures:
            self.heartbeat_failures -= 1
            raise RetryableConnectivityError("heartbeat timeout")
        self.accepted_sequence = kwargs["sequence"]
        return {"accepted_heartbeat_sequence": self.accepted_sequence}

    def disconnect(self, **kwargs):
        self.disconnects.append(kwargs)


def config(root: Path) -> DeviceConnectivityConfig:
    secret = root / "api-key.txt"
    secret.write_text("top-secret\n", encoding="utf-8")
    return DeviceConnectivityConfig(
        DeviceId("device-1"),
        "http://127.0.0.1:8420",
        secret,
        allow_insecure_http=True,
    )


def test_config_loads_relative_secret_and_environment_endpoint_override() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "secret.txt").write_text("secret-value\n", encoding="utf-8")
        (root / "device.toml").write_text(
            """
schema_version = 1
device_id = "device-file"
server_base_url = "http://127.0.0.1:8420"
api_key_file = "secret.txt"
allow_insecure_http = true
""".strip(),
            encoding="utf-8",
        )
        loaded = DeviceConnectivityConfig.from_toml(
            root / "device.toml",
            environ={"ASL_DEVICE_ID": "device-env"},
        )
        assert loaded.device_id == DeviceId("device-env")
        assert loaded.load_api_key() == "secret-value"
        assert "secret-value" not in repr(loaded)


def test_config_rejects_insecure_or_non_origin_url_and_secret_escape() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        secret = root / "secret.txt"
        secret.write_text("secret", encoding="utf-8")
        with pytest.raises(ValueError, match="allow_insecure"):
            DeviceConnectivityConfig(DeviceId("device-1"), "http://example.test", secret)
        with pytest.raises(ValueError, match="without a path"):
            DeviceConnectivityConfig(
                DeviceId("device-1"), "https://example.test/path", secret
            )
        (root / "device.toml").write_text(
            'schema_version=1\ndevice_id="device-1"\nserver_base_url="https://example.test"\napi_key_file="../outside.txt"',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="inside the config directory"):
            DeviceConnectivityConfig.from_toml(root / "device.toml", environ={})


def test_supervisor_retries_then_connects_heartbeats_and_disconnects() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        clock = ManualClock()
        transport = FakeTransport()
        transport.probe_failures = 1
        supervisor = DeviceConnectivitySupervisor(
            config(Path(temp_dir)),
            transport,
            clock,
            presence_session_id="presence-1",
            boot_id="boot-1",
            random_unit=lambda: 0.5,
        )
        assert supervisor.start()[0].event_type is ConnectivityEventType.CONNECTING
        events = supervisor.poll()
        assert [event.event_type for event in events] == [ConnectivityEventType.SERVER_RETRY_SCHEDULED]
        assert supervisor.current_status().state is ConnectivityState.RETRY_WAIT
        assert supervisor.current_status().next_action_at == 1.0

        clock.advance(1)
        assert supervisor.poll()[0].event_type is ConnectivityEventType.SERVER_ONLINE
        assert supervisor.current_status().online
        clock.advance(15)
        assert supervisor.poll() == ()
        assert supervisor.current_status().heartbeat_sequence == 1
        assert transport.heartbeats[0]["sequence"] == 1

        supervisor.stop()
        assert transport.disconnects == [
            {"device_id": "device-1", "presence_session_id": "presence-1"}
        ]


def test_heartbeat_loss_emits_loss_and_recovered_without_resetting_server_sequence() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        clock = ManualClock()
        transport = FakeTransport()
        supervisor = DeviceConnectivitySupervisor(
            config(Path(temp_dir)),
            transport,
            clock,
            presence_session_id="presence-1",
            boot_id="boot-1",
            random_unit=lambda: 0.5,
        )
        supervisor.start()
        supervisor.poll()
        transport.heartbeat_failures = 1
        clock.advance(15)
        events = supervisor.poll()
        assert [event.event_type for event in events] == [
            ConnectivityEventType.SERVER_CONNECTION_LOST,
            ConnectivityEventType.SERVER_RETRY_SCHEDULED,
        ]
        clock.advance(1)
        transport.accepted_sequence = 1
        assert supervisor.poll()[0].event_type is ConnectivityEventType.SERVER_RECOVERED
        assert supervisor.current_status().heartbeat_sequence == 1


def test_auth_failure_is_fatal_without_retry() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        transport = FakeTransport()
        transport.auth_failure = True
        supervisor = DeviceConnectivitySupervisor(
            config(Path(temp_dir)),
            transport,
            ManualClock(),
            presence_session_id="presence-1",
            boot_id="boot-1",
        )
        supervisor.start()
        events = supervisor.poll()
        assert events[0].event_type is ConnectivityEventType.SERVER_AUTH_FAILED
        assert supervisor.current_status().state is ConnectivityState.FATAL
        assert supervisor.poll() == ()
