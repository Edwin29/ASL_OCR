from __future__ import annotations

import pytest

from asl_device.types import (
    ArtifactId,
    CatalogChoice,
    ClientSpreadSequence,
    DatapackId,
    DeliveryStatus,
    DeliveryUpdate,
    DeviceControl,
    DeviceInputEvent,
    InputAction,
    ScanSessionId,
    ScannerArtifactReady,
)


def test_new_catalog_choice_cannot_carry_existing_entry() -> None:
    assert CatalogChoice.new_datapack().entry is None


def test_input_event_rejects_negative_monotonic_time() -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        DeviceInputEvent("event", DeviceControl.CONFIRM, InputAction.SHORT, -1)


def test_acked_delivery_requires_receipt() -> None:
    with pytest.raises(ValueError, match="receipt_id"):
        DeliveryUpdate(
            ScanSessionId("scan"),
            ClientSpreadSequence(1),
            ArtifactId("artifact"),
            DeliveryStatus.ACKED,
        )


def test_scanner_artifact_requires_sha256() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        ScannerArtifactReady(
            ScanSessionId("scan"),
            ArtifactId("artifact"),
            "spread",
            "frame",
            "manifest.json",
            "bad",
        )


def test_sequence_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        ClientSpreadSequence(0)

