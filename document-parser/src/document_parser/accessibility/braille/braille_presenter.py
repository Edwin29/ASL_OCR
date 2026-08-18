"""Focus item -> BrailleFrame (plan document §9.5 display-refresh rules).

Kept alongside `application.speech_controller.SpeechController`, not merged
into it -- syncing both presenters under one `generation` is Phase 4's
(통합 Controller) responsibility, per the approved Phase 3 plan.
"""

from __future__ import annotations

from typing import Any

from document_parser.accessibility.braille.math_translator import (
    braille_scrollable_spans,
    math_focus_item_to_braille,
)
from document_parser.accessibility.braille.table_formatter import table_cell_braille
from document_parser.accessibility.braille.viewport import build_frame, clear_frame

DEFAULT_VIEWPORT_SIZE = 20


class BraillePresenter:
    def __init__(self, viewport_size: int = DEFAULT_VIEWPORT_SIZE) -> None:
        self._viewport_size = viewport_size

    @property
    def viewport_size(self) -> int:
        return self._viewport_size

    def present_focus(self, item: dict[str, Any] | None, offset: int = 0, span_index: int = 0) -> dict[str, object]:
        """§9.5 + 좌우 연장 (Decision 2): plain-text/math-less focus clears
        the display. A MATH item or a TEXT item with inline MATH spans
        (see `braille_scrollable_spans`) shows the `span_index`-th
        scrollable span's window, if it produced any cells. TABLE entry
        itself stays cleared here -- table *cell* content is shown via
        `present_table_cell` once the user is inside table mode."""
        if item is None:
            return clear_frame("none")
        source_id = str(item.get("id", "focus"))
        spans = braille_scrollable_spans(item)
        if not spans or not (0 <= span_index < len(spans)):
            return clear_frame(source_id)
        cells = math_focus_item_to_braille(spans[span_index])
        if not cells:
            return clear_frame(source_id)
        frame_id = source_id if len(spans) == 1 and item.get("kind") == "MATH" else f"{source_id}#{span_index}"
        return build_frame(frame_id, cells, offset, self._viewport_size)

    def present_table_cell(self, cell_item: dict[str, Any], offset: int = 0) -> dict[str, object]:
        source_id = str(cell_item.get("id", "cell"))
        cells = table_cell_braille(cell_item)
        return build_frame(source_id, cells, offset, self._viewport_size)
