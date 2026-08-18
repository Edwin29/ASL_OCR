import unittest

from document_parser.accessibility.application import (
    can_enter_table,
    current_cell,
    enter_table,
    exit_table,
    move_table_braille_cursor,
    move_table_cursor,
)
from document_parser.accessibility.braille.table_formatter import table_cell_braille
from document_parser.accessibility.domain import NavigationState

from .support import load_accessible_document

VIEWPORT_SIZE = 3


def table_item_from(document, page_id="p038"):
    return next(item for item in document["pages"][0]["focus_items"] if item["kind"] == "TABLE")


class TableNavigatorTests(unittest.TestCase):
    def setUp(self):
        self.document = load_accessible_document("p038")
        self.table = table_item_from(self.document)
        self.state = NavigationState(document_id="doc", page_index=0, node_index=0)

    def test_enter_table_defaults_to_first_row_first_column(self):
        result = enter_table(self.table, self.state)
        self.assertEqual(result.state.mode, "TABLE")
        self.assertEqual((result.state.table_row, result.state.table_column), (1, 1))

    def test_exit_table_clears_table_position(self):
        entered = enter_table(self.table, self.state).state
        result = exit_table(entered)
        self.assertEqual(result.state.mode, "DOCUMENT")
        self.assertIsNone(result.state.table_row)
        self.assertIsNone(result.state.table_column)

    def test_move_right_then_down_reaches_expected_cell(self):
        state = enter_table(self.table, self.state).state
        state = move_table_cursor(self.table, state, "RIGHT").state
        state = move_table_cursor(self.table, state, "DOWN").state
        self.assertEqual((state.table_row, state.table_column), (2, 2))
        cell = current_cell(self.table, state)
        self.assertEqual(cell["row_index"], 2)
        self.assertEqual(cell["column_index"], 2)

    def test_boundary_at_first_row_stays_put_with_message(self):
        state = enter_table(self.table, self.state).state
        result = move_table_cursor(self.table, state, "UP")
        self.assertEqual(result.state.table_row, 1)
        self.assertEqual(result.boundary_message, "첫 행입니다.")

    def test_boundary_at_last_column_stays_put_with_message(self):
        state = enter_table(self.table, self.state).state
        for _ in range(self.table["column_count"] - 1):
            state = move_table_cursor(self.table, state, "RIGHT").state
        result = move_table_cursor(self.table, state, "RIGHT")
        self.assertEqual(result.state.table_column, self.table["column_count"])
        self.assertEqual(result.boundary_message, "마지막 열입니다.")

    def test_all_real_cells_are_reachable_within_reported_bounds(self):
        for cell in self.table["cells"]:
            state = NavigationState(
                document_id="doc", page_index=0, node_index=0,
                mode="TABLE", table_row=cell["row_index"], table_column=cell["column_index"],
            )
            resolved = current_cell(self.table, state)
            self.assertIsNotNone(resolved, cell)
            self.assertEqual(resolved["id"], cell["id"])


class MergedCellAnchorTests(unittest.TestCase):
    def setUp(self):
        self.table = {
            "row_count": 2,
            "column_count": 2,
            "structure_confidence": 0.95,
            "issues": [],
            "cells": [
                {"id": "anchor", "row_index": 1, "column_index": 1, "row_span": 1, "column_span": 2, "content_nodes": []},
                {"id": "r2c1", "row_index": 2, "column_index": 1, "row_span": 1, "column_span": 1, "content_nodes": []},
                {"id": "r2c2", "row_index": 2, "column_index": 2, "row_span": 1, "column_span": 1, "content_nodes": []},
            ],
        }

    def test_both_occupied_columns_of_a_merged_cell_resolve_to_the_anchor(self):
        left = NavigationState(document_id="d", page_index=0, node_index=0, mode="TABLE", table_row=1, table_column=1)
        right = NavigationState(document_id="d", page_index=0, node_index=0, mode="TABLE", table_row=1, table_column=2)
        self.assertEqual(current_cell(self.table, left)["id"], "anchor")
        self.assertEqual(current_cell(self.table, right)["id"], "anchor")


class TableEntryGatingTests(unittest.TestCase):
    def test_zero_row_count_blocks_entry(self):
        table = {"row_count": 0, "column_count": 3, "structure_confidence": 1.0, "issues": []}
        self.assertFalse(can_enter_table(table))

    def test_low_structure_confidence_blocks_entry(self):
        table = {"row_count": 2, "column_count": 2, "structure_confidence": 0.5, "issues": []}
        self.assertFalse(can_enter_table(table))

    def test_low_confidence_issue_blocks_entry_even_at_high_score(self):
        table = {
            "row_count": 2, "column_count": 2, "structure_confidence": 0.95,
            "issues": [{"code": "VL_TABLE_STRUCTURE_LOW_CONFIDENCE", "severity": "warning"}],
        }
        self.assertFalse(can_enter_table(table))

    def test_entering_a_blocked_table_leaves_document_mode_with_a_message(self):
        table = {"row_count": 0, "column_count": 0, "structure_confidence": 0.0, "issues": []}
        state = NavigationState(document_id="d", page_index=0, node_index=0)
        result = enter_table(table, state)
        self.assertEqual(result.state.mode, "DOCUMENT")
        self.assertIsNotNone(result.boundary_message)

    def test_real_p038_table_passes_the_gate(self):
        document = load_accessible_document("p038")
        table = table_item_from(document)
        self.assertTrue(can_enter_table(table))


class MoveTableBrailleCursorTests(unittest.TestCase):
    """LEFT/RIGHT LONG in TABLE mode: within-cell braille scroll, kept
    separate from LEFT/RIGHT SHORT's cell-to-cell movement (tested above).
    Small VIEWPORT_SIZE=3 makes multi-window scrolling exercisable."""

    def setUp(self):
        self.state = NavigationState(document_id="doc", page_index=0, node_index=0, mode="TABLE", table_row=1, table_column=1)

    def move(self, cell_item, state, direction):
        return move_table_braille_cursor(cell_item, state, direction, VIEWPORT_SIZE)

    def long_cell(self):
        # column(1)+row(1) digit prefix (2+2 cells) + digit content "123456789" (10 cells) = 14 total.
        return {"id": "c11", "row_index": 1, "column_index": 1, "content_nodes": [{"kind": "TEXT", "text": "123456789"}]}

    def test_right_scrolls_window_by_window_then_hits_end_boundary(self):
        cell = self.long_cell()
        total = len(table_cell_braille(cell))
        self.assertEqual(total, 14)
        state = self.state
        for expected_offset in (3, 6, 9, 12):
            result = self.move(cell, state, "RIGHT")
            self.assertIsNone(result.boundary_message)
            self.assertEqual(result.state.braille_offset, expected_offset)
            state = result.state
        boundary = self.move(cell, state, "RIGHT")
        self.assertEqual(boundary.boundary_message, "셀 내용의 끝입니다.")
        self.assertEqual(boundary.state.braille_offset, 12)

    def test_left_scrolls_back_then_hits_start_boundary(self):
        cell = self.long_cell()
        state = self.state
        for _ in range(4):
            state = self.move(cell, state, "RIGHT").state
        self.assertEqual(state.braille_offset, 12)
        for expected_offset in (9, 6, 3, 0):
            result = self.move(cell, state, "LEFT")
            self.assertIsNone(result.boundary_message)
            self.assertEqual(result.state.braille_offset, expected_offset)
            state = result.state
        boundary = self.move(cell, state, "LEFT")
        self.assertEqual(boundary.boundary_message, "셀 내용의 시작입니다.")

    def test_short_cell_that_fits_one_window_reports_boundary_immediately(self):
        # column(1)+row(1) prefix (4 cells) + digit "5" (2 cells) = 6 cells --
        # needs a bigger viewport than VIEWPORT_SIZE=3 to fit in one window.
        cell = {"id": "c11", "row_index": 1, "column_index": 1, "content_nodes": [{"kind": "TEXT", "text": "5"}]}
        result = move_table_braille_cursor(cell, self.state, "RIGHT", 10)
        self.assertEqual(result.boundary_message, "셀 내용의 끝입니다.")
        self.assertEqual(result.state.braille_offset, 0)

    def test_none_cell_reports_boundary_without_raising(self):
        result = self.move(None, self.state, "RIGHT")
        self.assertEqual(result.boundary_message, "셀을 찾을 수 없습니다.")


if __name__ == "__main__":
    unittest.main()
