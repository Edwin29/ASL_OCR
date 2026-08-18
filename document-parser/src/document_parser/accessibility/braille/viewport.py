"""10~20-cell braille viewport windowing (plan document §9.4). Pure logic,
independent of the encoding tables in `cell_encoding.py` -- works for any
`BrailleCell` sequence regardless of which symbols are verified yet.
"""

from __future__ import annotations

from document_parser.accessibility.braille.cell_encoding import BrailleCell


def cell_to_int(dots: BrailleCell) -> int:
    """Pack a cell into the 6-bit wire format used by SET_FRAME (§9.6):
    bit 0 = dot 1 ... bit 5 = dot 6."""
    value = 0
    for dot in dots:
        if not (1 <= dot <= 6):
            raise ValueError(f"Invalid dot number: {dot}")
        value |= 1 << (dot - 1)
    return value


def build_frame(source_id: str, cells: list[BrailleCell], offset: int, viewport_size: int) -> dict[str, object]:
    if viewport_size <= 0:
        raise ValueError("viewport_size must be positive")
    total = len(cells)
    offset = max(0, min(offset, max(total - 1, 0)))
    window = cells[offset:offset + viewport_size]
    return {
        "source_id": source_id,
        "cells": [cell_to_int(c) for c in window],
        "offset": offset,
        "viewport_size": viewport_size,
        "total_cell_count": total,
        "has_previous": offset > 0,
        "has_next": offset + viewport_size < total,
    }


def scroll(source_id: str, cells: list[BrailleCell], offset: int, viewport_size: int, direction: str) -> dict[str, object]:
    """Moves by a whole window, not one cell at a time (§9.4: "긴 셀 값은
    길게 누르기 동작으로 앞·뒤 창을 탐색")."""
    if direction == "RIGHT":
        new_offset = offset + viewport_size
    elif direction == "LEFT":
        new_offset = offset - viewport_size
    else:
        raise ValueError(f"Unknown scroll direction: {direction!r}")
    return build_frame(source_id, cells, max(0, new_offset), viewport_size)


def last_window_offset(total_cell_count: int, viewport_size: int) -> int:
    """Start offset of the last whole-window page for `total_cell_count`
    cells, matching the windowing convention `scroll()`/`build_frame()`
    already use (moves by whole `viewport_size` windows). Used when
    entering a span from its right edge (LEFT-ward 좌우 연장) so the user
    lands on the span's tail window, not offset 0."""
    if viewport_size <= 0:
        raise ValueError("viewport_size must be positive")
    if total_cell_count <= viewport_size:
        return 0
    return ((total_cell_count - 1) // viewport_size) * viewport_size


def clear_frame(source_id: str) -> dict[str, object]:
    """§9.5: 일반 텍스트 포커스에서는 점자판을 비운다."""
    return {
        "source_id": source_id,
        "cells": [],
        "offset": 0,
        "viewport_size": 0,
        "total_cell_count": 0,
        "has_previous": False,
        "has_next": False,
    }
