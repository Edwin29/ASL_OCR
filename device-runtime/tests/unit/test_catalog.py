from __future__ import annotations

from asl_device.catalog import CatalogModel
from asl_device.types import (
    CatalogChoiceKind,
    CatalogEntry,
    DatapackId,
    DatapackStatus,
    DeviceOperatingMode,
)


def test_empty_server_catalog_still_has_one_new_datapack_item() -> None:
    model = CatalogModel(())

    assert len(model.items) == 1
    assert model.current.choice.kind is CatalogChoiceKind.NEW_DATAPACK


def test_catalog_filters_nonselectable_states_and_appends_new_exactly_once() -> None:
    model = CatalogModel(
        (
            CatalogEntry(DatapackId("ready"), "준비", DatapackStatus.READY),
            CatalogEntry(DatapackId("draft"), "작성 중", DatapackStatus.DRAFT),
            CatalogEntry(DatapackId("busy"), "완성 중", DatapackStatus.FINALIZING),
            CatalogEntry(DatapackId("bad"), "오류", DatapackStatus.ERROR),
        )
    )

    assert [item.title for item in model.items] == ["준비", "작성 중", "새 데이터팩 추가"]


def test_catalog_movement_is_clamped() -> None:
    model = CatalogModel(())
    assert not model.move(-5)
    assert not model.move(5)


def test_reading_catalog_contains_only_ready_datapacks_and_can_be_empty() -> None:
    model = CatalogModel(
        (
            CatalogEntry(DatapackId("ready"), "준비", DatapackStatus.READY),
            CatalogEntry(DatapackId("draft"), "작성 중", DatapackStatus.DRAFT),
        ),
        DeviceOperatingMode.READING,
    )
    assert [item.title for item in model.items] == ["준비"]

    empty = CatalogModel((), DeviceOperatingMode.READING)
    assert empty.items == ()
    assert not empty.move(1)

