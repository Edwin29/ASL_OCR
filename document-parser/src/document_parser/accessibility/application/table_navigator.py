"""TABLE-mode navigation over one flattened TABLE focus item's cells.

Row/column indices are 1-based throughout, matching
`document_parser.serialization.table_html`'s already-1-based `row_index`/
`column_index` -- this module must never re-apply a `+1`.
"""

from __future__ import annotations

from document_parser.accessibility.braille.table_formatter import table_cell_braille
from document_parser.accessibility.braille.viewport import build_frame, scroll
from document_parser.accessibility.domain.events import NavigationResult
from document_parser.accessibility.domain.navigation_state import NavigationState

STRUCTURE_CONFIDENCE_THRESHOLD = 0.8


def can_enter_table(table_item: dict[str, object]) -> bool:
    """Table-navigation allow gate, per the plan document's §8.5 conditions:
    positive row/column counts and a structure confidence that clears the
    default 0.8 threshold (or an explicit low-confidence issue), so a
    doubtful table structure never gets exposed as if it were reliable
    coordinates."""
    if table_item.get("row_count", 0) <= 0 or table_item.get("column_count", 0) <= 0:
        return False
    if table_item.get("structure_confidence", 0.0) < STRUCTURE_CONFIDENCE_THRESHOLD:
        return False
    issues = table_item.get("issues") if isinstance(table_item.get("issues"), list) else []
    if any(issue.get("code") == "VL_TABLE_STRUCTURE_LOW_CONFIDENCE" for issue in issues):
        return False
    return True


def enter_table(table_item: dict[str, object], state: NavigationState) -> NavigationResult:
    if not can_enter_table(table_item):
        return NavigationResult(
            state.advanced(),
            boundary_message="표 구조를 인식하지 못했습니다. 표 탐색을 사용할 수 없습니다.",
        )
    return NavigationResult(state.advanced(mode="TABLE", table_row=1, table_column=1, braille_offset=0, math_span_index=0))


def exit_table(state: NavigationState) -> NavigationResult:
    return NavigationResult(state.advanced(
        mode="DOCUMENT", table_row=None, table_column=None, braille_offset=0, math_span_index=0,
    ))


def current_cell(table_item: dict[str, object], state: NavigationState) -> dict[str, object] | None:
    """Resolve the cell at the current (table_row, table_column). A merged
    cell's occupied coordinates all resolve to the same anchor cell object,
    since `table_html.build_table_ir` only emits one cell entry per merge,
    anchored at its top-left row/column."""
    if state.table_row is None or state.table_column is None:
        return None
    for cell in table_item.get("cells", []):
        row0 = cell.get("row_index")
        col0 = cell.get("column_index")
        if not isinstance(row0, int) or not isinstance(col0, int):
            continue
        row1 = row0 + cell.get("row_span", 1)
        col1 = col0 + cell.get("column_span", 1)
        if row0 <= state.table_row < row1 and col0 <= state.table_column < col1:
            return cell
    return None


def move(table_item: dict[str, object], state: NavigationState, direction: str) -> NavigationResult:
    row_count = table_item.get("row_count", 0)
    column_count = table_item.get("column_count", 0)
    row = state.table_row
    column = state.table_column
    if row is None or column is None:
        raise ValueError("table_navigator.move() requires an active table position; call enter_table() first.")

    if direction == "UP":
        if row <= 1:
            return NavigationResult(state.advanced(), boundary_message="첫 행입니다.")
        return NavigationResult(state.advanced(table_row=row - 1, braille_offset=0, math_span_index=0))
    if direction == "DOWN":
        if row >= row_count:
            return NavigationResult(state.advanced(), boundary_message="마지막 행입니다.")
        return NavigationResult(state.advanced(table_row=row + 1, braille_offset=0, math_span_index=0))
    if direction == "LEFT":
        if column <= 1:
            return NavigationResult(state.advanced(), boundary_message="첫 열입니다.")
        return NavigationResult(state.advanced(table_column=column - 1, braille_offset=0, math_span_index=0))
    if direction == "RIGHT":
        if column >= column_count:
            return NavigationResult(state.advanced(), boundary_message="마지막 열입니다.")
        return NavigationResult(state.advanced(table_column=column + 1, braille_offset=0, math_span_index=0))
    raise ValueError(f"Unknown table navigation direction: {direction!r}")


def move_table_braille_cursor(
    cell_item: dict[str, object] | None,
    state: NavigationState,
    direction: str,
    viewport_size: int,
) -> NavigationResult:
    """LEFT/RIGHT LONG in TABLE mode: scrolls the braille viewport within
    the current cell's content when it's longer than one window. Deliberately
    separate from `move()` (LEFT/RIGHT SHORT, cell-to-cell movement) --
    within-cell scroll never advances to a different cell, so the two
    already-tested SHORT semantics stay untouched."""
    if cell_item is None:
        return NavigationResult(state.advanced(), boundary_message="셀을 찾을 수 없습니다.")

    cells = table_cell_braille(cell_item)
    frame_id = str(cell_item.get("id", "cell"))
    current_frame = build_frame(frame_id, cells, state.braille_offset, viewport_size)

    if direction == "RIGHT":
        if current_frame["has_next"]:
            new_frame = scroll(frame_id, cells, state.braille_offset, viewport_size, "RIGHT")
            return NavigationResult(state.advanced(braille_offset=new_frame["offset"]))
        return NavigationResult(state.advanced(), boundary_message="셀 내용의 끝입니다.")

    if direction == "LEFT":
        if current_frame["has_previous"]:
            new_frame = scroll(frame_id, cells, state.braille_offset, viewport_size, "LEFT")
            return NavigationResult(state.advanced(braille_offset=new_frame["offset"]))
        return NavigationResult(state.advanced(), boundary_message="셀 내용의 시작입니다.")

    raise ValueError(f"Unknown braille scroll direction: {direction!r}")
