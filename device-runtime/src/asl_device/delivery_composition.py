"""LAPTOP composition for the approved V3-B single-sender delivery path."""

from __future__ import annotations

from .adapters.http_v4 import V4HttpClient
from .connectivity_config import DeviceConnectivityConfig
from .delivery import DurableDeliveryPort
from .delivery_config import DeviceDeliveryConfig
from .delivery_store import DeliveryStore
from .protocols import Clock


def build_laptop_delivery(
    connectivity_config: DeviceConnectivityConfig,
    delivery_config: DeviceDeliveryConfig,
    clock: Clock,
) -> DurableDeliveryPort:
    store = DeliveryStore(delivery_config.outbox_db_path)
    transport = V4HttpClient(
        connectivity_config.server_base_url,
        connectivity_config.load_api_key(),
        delivery_config,
        allow_insecure_http=connectivity_config.allow_insecure_http,
    )
    return DurableDeliveryPort(
        connectivity_config.device_id,
        delivery_config,
        store,
        transport,
        clock.monotonic,
    )
