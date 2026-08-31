"""Client-side catalog projection with one synthetic new-datapack item."""

from __future__ import annotations

from dataclasses import dataclass

from .types import CatalogChoice, CatalogEntry


@dataclass(frozen=True, slots=True)
class CatalogItem:
    choice: CatalogChoice
    title: str
    title_audio_ref: str | None = None


class CatalogModel:
    """Clamped selection model; server catalog remains the source of truth."""

    NEW_DATAPACK_TITLE = "새 데이터팩 추가"

    def __init__(self, entries: tuple[CatalogEntry, ...]) -> None:
        visible = tuple(entry for entry in entries if entry.selectable)
        self._items = tuple(
            CatalogItem(CatalogChoice.existing(entry), entry.title, entry.title_audio_ref)
            for entry in visible
        ) + (CatalogItem(CatalogChoice.new_datapack(), self.NEW_DATAPACK_TITLE),)
        self._index = 0

    @property
    def items(self) -> tuple[CatalogItem, ...]:
        return self._items

    @property
    def index(self) -> int:
        return self._index

    @property
    def current(self) -> CatalogItem:
        return self._items[self._index]

    def move(self, delta: int) -> bool:
        if isinstance(delta, bool) or not isinstance(delta, int):
            raise TypeError("delta must be an integer")
        before = self._index
        self._index = min(max(0, self._index + delta), len(self._items) - 1)
        return self._index != before

