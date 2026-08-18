"""TABLE focus item -> Korean utterance strings (plan document §8.5): entry
announcement and per-cell "열 -> 행 -> 값" order, matching the same order the
braille layer (Phase 3) will use for its logical buffer (§9.3).
"""

from __future__ import annotations

from typing import Any

from document_parser.accessibility.speech.text_rules import describe_content_nodes


def table_entry_announcement(table_item: dict[str, Any]) -> str:
    row_count = table_item.get("row_count", 0)
    column_count = table_item.get("column_count", 0)
    return f"표, {row_count}행 {column_count}열. 오른쪽 버튼을 눌러 표 탐색을 시작합니다."


def table_cell_announcement(cell: dict[str, Any]) -> str:
    location = _cell_location_phrase(cell)
    value = describe_content_nodes(cell.get("content_nodes", []))
    if not value:
        return f"{location}, 빈 셀"
    return f"{location}, 값 {value}"


def _cell_location_phrase(cell: dict[str, Any]) -> str:
    row = cell.get("row_index")
    column = cell.get("column_index")
    row_span = cell.get("row_span", 1)
    column_span = cell.get("column_span", 1)
    if row_span > 1 or column_span > 1:
        end_row = row + row_span - 1
        end_column = column + column_span - 1
        return f"{column}열 {row}행부터 {end_column}열 {end_row}행까지 병합"
    return f"{column}열 {row}행"
