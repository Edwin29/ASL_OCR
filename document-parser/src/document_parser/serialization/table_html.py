"""Parse PaddleOCR-VL's `raw_html` table blocks into Table IR (`table-ir.schema.json`).

`vl_page_ir.py` previously stored a TABLE node's HTML as-is and flagged
`VL_TABLE_ROW_COL_NOT_PARSED`, matching the same principle used everywhere else
in this project: a table flattened to raw text loses the row/column/cell
relationships a braille table navigator needs to walk (기획서 §13.1). This module
closes that gap using Python's stdlib `html.parser` (no new dependency), with
`colspan`/`rowspan` tracked through a row/column occupancy grid so merged cells
land in the right place instead of shifting every later cell in the row.

Each cell's text becomes real Page IR content nodes via the same inline-math
splitting and LaTeX->AST parsing already used for body text
(`document_parser.serialization.vl_page_ir.spans_from_inline_math`), verified on
p004's real table: cells like "$ \\sqrt[n]{a} $" become a MATH node with a parsed
`presentation_ast`, not a plain string.

No per-cell bbox is available from the source HTML (VL does not emit table-internal
coordinates), so a cell's bbox is proportionally interpolated from the parent
TABLE node's bbox and its grid position -- an approximation, not a measurement,
and is tagged as such via `bbox_is_estimated` on each cell (schema allows
additional properties) rather than presented as ground truth.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any


class _TableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, object]]] = []
        self._current_row: list[dict[str, object]] | None = None
        self._current_cell: dict[str, object] | None = None
        self._text_parts: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in ("td", "th"):
            attr_map = dict(attrs)
            self._current_cell = {
                "is_header": tag == "th",
                "colspan": safe_int(attr_map.get("colspan"), 1),
                "rowspan": safe_int(attr_map.get("rowspan"), 1),
            }
            self._text_parts = []
        elif tag == "br" and self._current_cell is not None:
            self._text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._current_cell is not None:
            self._current_cell["text"] = "".join(self._text_parts).strip()
            if self._current_row is not None:
                self._current_row.append(self._current_cell)
            self._current_cell = None
            self._text_parts = []
        elif tag == "tr" and self._current_row is not None:
            self.rows.append(self._current_row)
            self._current_row = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._text_parts.append(data)


def parse_table_html(html: str) -> list[list[dict[str, object]]]:
    """Return raw parsed rows: `[[{is_header, colspan, rowspan, text}, ...], ...]`."""
    parser = _TableHtmlParser()
    parser.feed(html)
    parser.close()
    return parser.rows


def build_table_ir(
    html: str,
    table_bbox: dict[str, float],
    node_id_prefix: str,
    content_node_builder: Any,
) -> dict[str, object]:
    """Build `{row_count, column_count, cells, structure_confidence}` from raw HTML.

    `content_node_builder(text, node_id, bbox) -> list[node dict]` turns a cell's
    text into Page IR content nodes (splitting inline math and attaching
    `presentation_ast`), using the cell's own estimated bbox since no finer
    coordinates exist. Passed in rather than imported to avoid a circular import
    with `vl_page_ir`, which is what needs this module.
    """
    raw_rows = parse_table_html(html)
    if not raw_rows:
        return {
            "row_count": 0,
            "column_count": 0,
            "cells": [],
            "structure_confidence": 0.0,
        }

    occupied: dict[tuple[int, int], bool] = {}
    cells: list[dict[str, object]] = []
    max_column = 0
    cell_index = 0

    for row_index_zero, raw_row in enumerate(raw_rows):
        row_index = row_index_zero + 1
        column_cursor = 1
        for raw_cell in raw_row:
            while occupied.get((row_index, column_cursor)):
                column_cursor += 1
            row_span = max(1, int(raw_cell["rowspan"]))
            col_span = max(1, int(raw_cell["colspan"]))
            for r in range(row_index, row_index + row_span):
                for c in range(column_cursor, column_cursor + col_span):
                    occupied[(r, c)] = True

            cell_index += 1
            cell_id = f"{node_id_prefix}-r{row_index:02d}c{column_cursor:02d}"
            cell_bbox = estimate_cell_bbox(
                table_bbox, row_index, column_cursor, row_span, col_span, len(raw_rows), estimate_row_columns(raw_rows)
            )
            content_nodes = content_node_builder(str(raw_cell["text"]), f"{cell_id}-content", cell_bbox)
            cells.append({
                "cell_id": cell_id,
                "row_index": row_index,
                "column_index": column_cursor,
                "row_span": row_span,
                "column_span": col_span,
                "bbox": cell_bbox,
                "bbox_is_estimated": True,
                "content_nodes": content_nodes,
                "header_candidate": bool(raw_cell["is_header"]) or row_index == 1,
            })
            max_column = max(max_column, column_cursor + col_span - 1)
            column_cursor += col_span

    row_count = len(raw_rows)
    column_count = max_column
    confidence = structure_confidence(raw_rows, column_count)

    return {
        "row_count": row_count,
        "column_count": column_count,
        "cells": cells,
        "structure_confidence": confidence,
    }


def estimate_row_columns(raw_rows: list[list[dict[str, object]]]) -> int:
    totals = [sum(max(1, int(cell["colspan"])) for cell in row) for row in raw_rows]
    return max(totals) if totals else 1


def estimate_cell_bbox(
    table_bbox: dict[str, float],
    row_index: int,
    column_index: int,
    row_span: int,
    col_span: int,
    row_count: int,
    column_count: int,
) -> dict[str, float]:
    row_count = max(row_count, 1)
    column_count = max(column_count, 1)
    cell_width = table_bbox["width"] / column_count
    cell_height = table_bbox["height"] / row_count
    return {
        "x": round(table_bbox["x"] + (column_index - 1) * cell_width, 3),
        "y": round(table_bbox["y"] + (row_index - 1) * cell_height, 3),
        "width": round(cell_width * col_span, 3),
        "height": round(cell_height * row_span, 3),
    }


def structure_confidence(raw_rows: list[list[dict[str, object]]], column_count: int) -> float:
    if not raw_rows or column_count == 0:
        return 0.0
    row_totals = [sum(max(1, int(cell["colspan"])) for cell in row) for row in raw_rows]
    # A clean rectangular grid (every row's cells, accounting for colspan, add up
    # to the same column count) is a strong structural signal even without an
    # independent confidence score from the source model.
    if all(total == column_count for total in row_totals):
        return 0.9
    return 0.5


def safe_int(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        return int(str(value))
    except ValueError:
        return default
