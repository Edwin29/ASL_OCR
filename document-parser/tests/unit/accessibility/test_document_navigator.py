import unittest

from document_parser.accessibility.application import (
    handle_document_command,
    move_braille_cursor,
    next_node,
    next_page,
    previous_node,
    previous_page,
)
from document_parser.accessibility.domain import NavigationCommand, NavigationState

from .support import load_accessible_document

VIEWPORT_SIZE = 3


def press(button: str, action: str = "SHORT") -> NavigationCommand:
    return NavigationCommand(button=button, action=action)


def number(value: str) -> dict:
    return {"type": "Number", "value": value}


def math_item(item_id: str, value: str) -> dict:
    return {
        "id": item_id, "kind": "MATH",
        "raw_formula": value, "presentation_ast": number(value),
        "unconsumed_tokens": [], "ast_status": "VALID",
    }


def math_span(value: str, ast_status: str = "VALID") -> dict:
    span = {"kind": "MATH", "text": value, "unconsumed_tokens": [], "ast_status": ast_status}
    span["presentation_ast"] = number(value) if ast_status == "VALID" else None
    return span


def text_item(item_id: str, spans: list) -> dict:
    return {"id": item_id, "kind": "TEXT", "spans": spans}


class DocumentNavigatorTests(unittest.TestCase):
    def setUp(self):
        self.document = load_accessible_document("p018")
        self.total_items = len(self.document["pages"][0]["focus_items"])
        self.start_state = NavigationState(document_id=self.document["document_id"], page_index=0, node_index=0)

    def test_next_node_advances_index_and_generation(self):
        result = next_node(self.document, self.start_state)
        self.assertEqual(result.state.node_index, 1)
        self.assertEqual(result.state.generation, self.start_state.generation + 1)
        self.assertIsNone(result.boundary_message)

    def test_previous_node_at_document_start_stays_put_with_message(self):
        result = previous_node(self.document, self.start_state)
        self.assertEqual(result.state.page_index, 0)
        self.assertEqual(result.state.node_index, 0)
        self.assertEqual(result.boundary_message, "문서의 시작입니다.")
        # Generation still advances so a stale earlier callback is not confused with this one.
        self.assertEqual(result.state.generation, self.start_state.generation + 1)

    def test_next_node_at_document_end_stays_put_with_message(self):
        last_state = NavigationState(
            document_id=self.document["document_id"], page_index=0, node_index=self.total_items - 1,
        )
        result = next_node(self.document, last_state)
        self.assertEqual(result.state.node_index, self.total_items - 1)
        self.assertEqual(result.boundary_message, "문서의 끝입니다.")

    def test_next_node_stops_at_page_boundary_instead_of_rolling_over(self):
        # p018 is a single-page fixture; build a tiny two-page document to
        # exercise page-boundary behavior directly. Project decision: page
        # crossing is exclusively the dedicated PAGE_NEXT button's job (see
        # NextPreviousPageTests below) -- next_node must stop and report the
        # boundary, not advance into the next page on its own.
        two_page_document = {
            "document_id": "doc",
            "pages": [
                {"page_id": "a", "focus_items": [{"id": "a1"}, {"id": "a2"}]},
                {"page_id": "b", "focus_items": [{"id": "b1"}]},
            ],
        }
        state = NavigationState(document_id="doc", page_index=0, node_index=1)
        result = next_node(two_page_document, state)
        self.assertEqual((result.state.page_index, result.state.node_index), (0, 1))
        self.assertEqual(result.boundary_message, "페이지의 끝입니다.")

    def test_previous_node_stops_at_page_boundary_instead_of_rolling_over(self):
        two_page_document = {
            "document_id": "doc",
            "pages": [
                {"page_id": "a", "focus_items": [{"id": "a1"}, {"id": "a2"}]},
                {"page_id": "b", "focus_items": [{"id": "b1"}]},
            ],
        }
        state = NavigationState(document_id="doc", page_index=1, node_index=0)
        result = previous_node(two_page_document, state)
        self.assertEqual((result.state.page_index, result.state.node_index), (1, 0))
        self.assertEqual(result.boundary_message, "페이지의 시작입니다.")

    def test_handle_command_routes_up_down(self):
        down_result = handle_document_command(self.document, self.start_state, press("DOWN"))
        self.assertEqual(down_result.state.node_index, 1)
        up_result = handle_document_command(self.document, down_result.state, press("UP"))
        self.assertEqual(up_result.state.node_index, 0)

    def test_handle_command_reports_unsupported_input_explicitly(self):
        result = handle_document_command(self.document, self.start_state, press("LEFT"))
        self.assertEqual(result.state.node_index, self.start_state.node_index)
        self.assertIsNotNone(result.boundary_message)


class NextPreviousPageTests(unittest.TestCase):
    """Dedicated page-turn buttons: jump straight to the next/previous
    page's first item, skipping whatever remains of the current page --
    unlike next_node/previous_node, which only cross a page boundary
    incidentally once they run out of items."""

    def setUp(self):
        self.document = {
            "document_id": "doc",
            "pages": [
                {"page_id": "a", "focus_items": [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]},
                {"page_id": "b", "focus_items": [{"id": "b1"}]},
                {"page_id": "c", "focus_items": [{"id": "c1"}]},
            ],
        }

    def test_next_page_skips_remaining_items_on_current_page(self):
        state = NavigationState(document_id="doc", page_index=0, node_index=1)  # mid-page, not the last item
        result = next_page(self.document, state)
        self.assertEqual((result.state.page_index, result.state.node_index), (1, 0))
        self.assertIsNone(result.boundary_message)
        self.assertEqual(result.state.generation, state.generation + 1)

    def test_previous_page_lands_on_first_item_not_last(self):
        state = NavigationState(document_id="doc", page_index=1, node_index=0)
        result = previous_page(self.document, state)
        self.assertEqual((result.state.page_index, result.state.node_index), (0, 0))
        self.assertIsNone(result.boundary_message)

    def test_next_page_at_last_page_stays_put_with_message(self):
        state = NavigationState(document_id="doc", page_index=2, node_index=0)
        result = next_page(self.document, state)
        self.assertEqual(result.state.page_index, 2)
        self.assertEqual(result.boundary_message, "문서의 마지막 페이지입니다.")

    def test_previous_page_at_first_page_stays_put_with_message(self):
        state = NavigationState(document_id="doc", page_index=0, node_index=2)
        result = previous_page(self.document, state)
        self.assertEqual(result.state.page_index, 0)
        self.assertEqual(result.boundary_message, "문서의 첫 페이지입니다.")

    def test_next_page_from_table_mode_resets_to_document_mode(self):
        state = NavigationState(
            document_id="doc", page_index=0, node_index=1,
            mode="TABLE", table_row=2, table_column=3, braille_offset=5, math_span_index=1,
        )
        result = next_page(self.document, state)
        self.assertEqual(result.state.mode, "DOCUMENT")
        self.assertIsNone(result.state.table_row)
        self.assertIsNone(result.state.table_column)
        self.assertEqual(result.state.braille_offset, 0)
        self.assertEqual(result.state.math_span_index, 0)

    def test_previous_page_from_table_mode_resets_to_document_mode(self):
        state = NavigationState(
            document_id="doc", page_index=1, node_index=0,
            mode="TABLE", table_row=1, table_column=1,
        )
        result = previous_page(self.document, state)
        self.assertEqual(result.state.mode, "DOCUMENT")
        self.assertIsNone(result.state.table_row)
        self.assertIsNone(result.state.table_column)


class MoveBrailleCursorTests(unittest.TestCase):
    """좌우 연장 (Decision 2): LEFT/RIGHT scrolls the braille viewport within
    the active math span, and once that span's window is exhausted,
    continues into the next/previous inline span in the same block --
    never rolling over to an adjacent top-level focus item. Uses a small
    VIEWPORT_SIZE=3 so multi-window scrolling is exercisable without huge
    ASTs (real fixtures top out at 8 cells, below the production default of
    20)."""

    def setUp(self):
        self.state = NavigationState(document_id="doc", page_index=0, node_index=0)

    def move(self, item, state, direction):
        return move_braille_cursor(item, state, direction, VIEWPORT_SIZE)

    def test_right_scrolls_window_by_window_within_a_single_math_item(self):
        item = math_item("m1", "123456789")  # 10 cells: indicator + 9 digits
        state = self.state
        for expected_offset in (3, 6, 9):
            result = self.move(item, state, "RIGHT")
            self.assertIsNone(result.boundary_message)
            self.assertEqual(result.state.braille_offset, expected_offset)
            self.assertEqual(result.state.math_span_index, 0)
            state = result.state
        boundary = self.move(item, state, "RIGHT")
        self.assertEqual(boundary.boundary_message, "더 이상 표시할 수식이 없습니다.")
        self.assertEqual(boundary.state.braille_offset, 9)

    def test_left_scrolls_back_then_hits_start_boundary(self):
        item = math_item("m1", "123456789")
        state = self.state
        for _ in range(3):
            state = self.move(item, state, "RIGHT").state
        self.assertEqual(state.braille_offset, 9)
        for expected_offset in (6, 3, 0):
            result = self.move(item, state, "LEFT")
            self.assertIsNone(result.boundary_message)
            self.assertEqual(result.state.braille_offset, expected_offset)
            state = result.state
        boundary = self.move(item, state, "LEFT")
        self.assertEqual(boundary.boundary_message, "이전에 표시할 수식이 없습니다.")
        self.assertEqual(boundary.state.braille_offset, 0)

    def test_right_extends_into_next_span_once_current_span_is_exhausted(self):
        item = text_item("t1", [math_span("12"), math_span("34")])  # each span: 3 cells, fits one window
        first = self.move(item, self.state, "RIGHT")
        self.assertIsNone(first.boundary_message)
        self.assertEqual((first.state.math_span_index, first.state.braille_offset), (1, 0))
        second = self.move(item, first.state, "RIGHT")
        self.assertEqual(second.boundary_message, "더 이상 표시할 수식이 없습니다.")
        self.assertEqual(second.state.math_span_index, 1)

    def test_left_extends_into_previous_span_landing_on_its_tail_window(self):
        item = text_item("t1", [math_span("12"), math_span("34")])
        at_span_1 = self.move(item, self.state, "RIGHT").state
        self.assertEqual(at_span_1.math_span_index, 1)
        back = self.move(item, at_span_1, "LEFT")
        self.assertIsNone(back.boundary_message)
        self.assertEqual((back.state.math_span_index, back.state.braille_offset), (0, 0))
        boundary = self.move(item, back.state, "LEFT")
        self.assertEqual(boundary.boundary_message, "이전에 표시할 수식이 없습니다.")

    def test_within_span_scrolling_happens_before_span_to_span_advance(self):
        # span0 (8 cells: indicator + 7 digits) needs 3 windows before it's
        # exhausted; span1 is short. Confirms `has_next` is checked before
        # `math_span_index` changes.
        item = text_item("t1", [math_span("1234567"), math_span("8")])
        state = self.state
        for expected_offset in (3, 6):
            result = self.move(item, state, "RIGHT")
            self.assertEqual((result.state.math_span_index, result.state.braille_offset), (0, expected_offset))
            state = result.state
        advance = self.move(item, state, "RIGHT")
        self.assertIsNone(advance.boundary_message)
        self.assertEqual((advance.state.math_span_index, advance.state.braille_offset), (1, 0))

    def test_text_item_with_no_math_spans_reports_boundary_without_moving(self):
        item = text_item("t1", [{"kind": "TEXT", "text": "hello"}])
        result = self.move(item, self.state, "RIGHT")
        self.assertEqual(result.boundary_message, "이 항목에는 점자로 표시할 수식이 없습니다.")
        self.assertEqual(result.state.braille_offset, self.state.braille_offset)
        self.assertEqual(result.state.math_span_index, self.state.math_span_index)

    def test_table_item_reports_no_scrollable_spans(self):
        item = {"id": "tb1", "kind": "TABLE"}
        result = self.move(item, self.state, "RIGHT")
        self.assertEqual(result.boundary_message, "이 항목에는 점자로 표시할 수식이 없습니다.")

    def test_none_item_reports_boundary_without_raising(self):
        result = self.move(None, self.state, "RIGHT")
        self.assertEqual(result.boundary_message, "현재 항목을 찾을 수 없습니다.")

    def test_invalid_span_is_skipped_without_raising(self):
        item = text_item("t1", [math_span("1"), math_span("x", ast_status="INVALID"), math_span("2")])
        state = self.state.advanced(math_span_index=1, braille_offset=0)
        result = self.move(item, state, "RIGHT")
        self.assertIsNone(result.boundary_message)
        self.assertEqual(result.state.math_span_index, 2)


if __name__ == "__main__":
    unittest.main()
