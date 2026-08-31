"""LAPTOP composition helper; no Scanner, upload, or outbox ownership."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .adapters.http_connectivity import HttpConnectivityTransport
from .connectivity import DeviceConnectivitySupervisor, MonotonicClock
from .connectivity_config import DeviceConnectivityConfig


def build_laptop_connectivity(
    config_path: str | Path,
    clock: MonotonicClock,
    *,
    boot_id: str | None = None,
    presence_session_id: str | None = None,
    random_unit: Callable[[], float] | None = None,
) -> DeviceConnectivitySupervisor:
    config = DeviceConnectivityConfig.from_toml(config_path)
    transport = HttpConnectivityTransport(
        config.server_base_url,
        config.load_api_key(),
        timeout_seconds=config.request_timeout_seconds,
        health_timeout_seconds=config.connect_timeout_seconds,
    )
    return DeviceConnectivitySupervisor(
        config,
        transport,
        clock,
        boot_id=boot_id,
        presence_session_id=presence_session_id,
        random_unit=random_unit,
    )
