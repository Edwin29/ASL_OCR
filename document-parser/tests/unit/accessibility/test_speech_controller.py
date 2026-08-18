import unittest

from document_parser.accessibility.adapters.tts_engine import FakeTtsEngineAdapter
from document_parser.accessibility.application.speech_controller import SpeechController
from document_parser.accessibility.braille.braille_presenter import BraillePresenter
from document_parser.accessibility.domain.accessible_document import (
    build_accessible_document,
    build_focus_item,
    build_page,
)
from document_parser.accessibility.domain.commands import NavigationCommand
from document_parser.accessibility.domain.navigation_state import NavigationState
from document_parser.accessibility.speech.math_rules import math_focus_item_to_speech


def press(button: str, action: str = "SHORT") -> NavigationCommand:
    return NavigationCommand(button=button, action=action)


def build_test_document() -> dict:
    text_item = build_focus_item(
        "t1", "TEXT", "p1", 0, ["t1"], spans=[{"kind": "TEXT", "text": "hello"}],
    )
    math_item = build_focus_item(
        "m1", "MATH", "p1", 1, ["m1"],
        raw_formula="x", presentation_ast={"type": "Identifier", "value": "x"},
        unconsumed_tokens=[], ast_status="VALID",
    )
    table_item = build_focus_item(
        "tb1", "TABLE", "p1", 2, ["tb1"],
        row_count=2, column_count=2, structure_confidence=0.95,
        cells=[
            # Digit content, not Latin placeholders -- table_cell_braille
            # routes non-digit TEXT through translate_hangul_syllable, which
            # correctly raises for unsupported characters like plain Latin
            # letters (§ table_formatter.py docstring); real cell content is
            # digits or Hangul, so the test fixture should be too now that
            # SpeechController actually renders table-cell braille.
            {"id": "c11", "row_index": 1, "column_index": 1, "row_span": 1, "column_span": 1, "content_nodes": [{"kind": "TEXT", "text": "1"}]},
            {"id": "c12", "row_index": 1, "column_index": 2, "row_span": 1, "column_span": 1, "content_nodes": [{"kind": "TEXT", "text": "2"}]},
            {"id": "c21", "row_index": 2, "column_index": 1, "row_span": 1, "column_span": 1, "content_nodes": [{"kind": "TEXT", "text": "3"}]},
            {"id": "c22", "row_index": 2, "column_index": 2, "row_span": 1, "column_span": 1, "content_nodes": [{"kind": "TEXT", "text": "4"}]},
        ],
    )
    page = build_page("p1", [text_item, math_item, table_item])
    return build_accessible_document("doc", [page])


class SpeechControllerDocumentModeTests(unittest.TestCase):
    def setUp(self):
        self.document = build_test_document()
        self.engine = FakeTtsEngineAdapter()
        self.state = NavigationState(document_id="doc", page_index=0, node_index=0)
        self.controller = SpeechController(self.document, self.state, self.engine)

    def test_speak_current_speaks_first_item(self):
        self.controller.speak_current()
        self.assertEqual(len(self.engine.spoken), 1)
        self.assertIn("hello", self.engine.spoken[0][0])

    def test_down_cancels_then_speaks_next_with_new_generation(self):
        self.controller.speak_current()
        cancels_before = self.engine.cancel_count
        self.controller.handle_command(press("DOWN"))
        self.assertGreater(self.engine.cancel_count, cancels_before)
        self.assertEqual(len(self.engine.spoken), 2)
        text, generation = self.engine.spoken[-1]
        self.assertEqual(text, "x")
        self.assertEqual(generation, self.controller.state.generation)
        self.assertNotEqual(self.engine.spoken[0][1], self.engine.spoken[1][1])

    def test_stale_completion_event_is_ignored(self):
        self.controller.handle_command(press("DOWN"))  # move to m1
        stale_generation = self.controller.state.generation
        self.controller.handle_command(press("DOWN"))  # move to tb1; the m1 generation is now stale
        self.controller.handle_command(press("DOWN", "LONG"))  # turn on continuous reading (re-announces tb1)
        spoken_before = len(self.engine.spoken)
        node_index_before = self.controller.state.node_index

        self.engine.complete(stale_generation)  # late callback tagged with the superseded generation

        self.assertEqual(len(self.engine.spoken), spoken_before)
        self.assertEqual(self.controller.state.node_index, node_index_before)

    def test_continuous_reading_advances_on_complete_and_stops_at_document_end(self):
        self.controller.handle_command(press("DOWN", "LONG"))  # start continuous reading from t1
        self.assertTrue(self.controller.continuous_reading)
        spoken_count_after_start = len(self.engine.spoken)

        self.engine.complete(self.controller.state.generation)  # t1 finished -> advance to m1
        self.assertEqual(self.controller.state.node_index, 1)
        self.assertGreater(len(self.engine.spoken), spoken_count_after_start)

        self.engine.complete(self.controller.state.generation)  # m1 finished -> advance to tb1
        self.assertEqual(self.controller.state.node_index, 2)

        self.engine.complete(self.controller.state.generation)  # tb1 finished -> document end
        self.assertFalse(self.controller.continuous_reading)
        self.assertIn("끝", self.engine.spoken[-1][0])

    def test_any_navigation_input_interrupts_continuous_reading(self):
        self.controller.handle_command(press("DOWN", "LONG"))
        self.assertTrue(self.controller.continuous_reading)
        self.controller.handle_command(press("UP"))
        self.assertFalse(self.controller.continuous_reading)


class SpeechControllerTableModeTests(unittest.TestCase):
    def setUp(self):
        self.document = build_test_document()
        self.engine = FakeTtsEngineAdapter()
        # Start already focused on the TABLE item (node_index 2).
        self.state = NavigationState(document_id="doc", page_index=0, node_index=2)
        self.controller = SpeechController(self.document, self.state, self.engine)

    def test_right_short_enters_table_mode_at_first_cell(self):
        self.controller.handle_command(press("RIGHT"))
        self.assertEqual(self.controller.state.mode, "TABLE")
        self.assertEqual((self.controller.state.table_row, self.controller.state.table_column), (1, 1))
        self.assertIn("값 1", self.engine.spoken[-1][0])

    def test_move_within_table_speaks_correct_cell(self):
        self.controller.handle_command(press("RIGHT"))  # enter
        self.controller.handle_command(press("RIGHT"))  # move to column 2
        self.assertIn("값 2", self.engine.spoken[-1][0])

    def test_up_long_exits_table_mode(self):
        self.controller.handle_command(press("RIGHT"))  # enter
        self.controller.handle_command(press("UP", "LONG"))  # exit
        self.assertEqual(self.controller.state.mode, "DOCUMENT")


def build_document_with_inline_math() -> dict:
    """Sibling of `build_test_document()` -- kept separate so the braille
    좌우 연장 tests don't disturb the node indices/counts the existing
    DOCUMENT/TABLE mode tests above rely on (e.g. "document end at tb1")."""
    plain_text_item = build_focus_item(
        "t1", "TEXT", "p1", 0, ["t1"], spans=[{"kind": "TEXT", "text": "hello"}],
    )
    text_with_math = build_focus_item(
        "tm1", "TEXT", "p1", 1, ["tm1"],
        spans=[
            {"kind": "TEXT", "text": "함수"},
            {"kind": "MATH", "text": "1", "presentation_ast": {"type": "Number", "value": "1"}, "unconsumed_tokens": [], "ast_status": "VALID"},
            {"kind": "TEXT", "text": "와"},
            {"kind": "MATH", "text": "22", "presentation_ast": {"type": "Number", "value": "22"}, "unconsumed_tokens": [], "ast_status": "VALID"},
        ],
    )
    long_math_item = build_focus_item(
        "m1", "MATH", "p1", 2, ["m1"],
        raw_formula="123456789", presentation_ast={"type": "Number", "value": "123456789"},
        unconsumed_tokens=[], ast_status="VALID",
    )
    table_item = build_focus_item(
        "tb1", "TABLE", "p1", 3, ["tb1"],
        row_count=1, column_count=1, structure_confidence=0.95,
        cells=[{"id": "c11", "row_index": 1, "column_index": 1, "row_span": 1, "column_span": 1, "content_nodes": [{"kind": "TEXT", "text": "1"}]}],
    )
    page = build_page("p1", [plain_text_item, text_with_math, long_math_item, table_item])
    return build_accessible_document("doc", [page])


class SpeechControllerBrailleTests(unittest.TestCase):
    """좌우 연장 (Decision 2) end-to-end through `SpeechController`: braille
    viewport scroll is silent, span-to-span extension announces just the
    new formula, and boundaries/mode-switches behave correctly. Uses
    viewport_size=3 (matches `MoveBrailleCursorTests` in
    test_document_navigator.py) so multi-window scrolling is exercisable."""

    def setUp(self):
        self.document = build_document_with_inline_math()
        self.engine = FakeTtsEngineAdapter()
        self.state = NavigationState(document_id="doc", page_index=0, node_index=0)
        self.controller = SpeechController(
            self.document, self.state, self.engine, braille_presenter=BraillePresenter(viewport_size=3),
        )

    def test_plain_text_focus_clears_braille_then_inline_math_shows_first_span(self):
        self.controller.speak_current()
        self.assertEqual(self.controller.braille_frame["cells"], [])
        self.controller.handle_command(press("DOWN"))  # move to tm1, span 0
        self.assertNotEqual(self.controller.braille_frame["cells"], [])

    def test_right_extends_to_next_span_and_announces_only_that_formula(self):
        self.controller.handle_command(press("DOWN"))  # tm1, span 0 ("1", fits one window)
        spoken_before = len(self.engine.spoken)
        self.controller.handle_command(press("RIGHT"))
        self.assertEqual(self.controller.state.math_span_index, 1)
        self.assertEqual(len(self.engine.spoken), spoken_before + 1)
        expected_span1 = {"kind": "MATH", "presentation_ast": {"type": "Number", "value": "22"}, "ast_status": "VALID"}
        self.assertEqual(self.engine.spoken[-1][0], math_focus_item_to_speech(expected_span1))

    def test_pure_within_span_scroll_is_silent_but_updates_braille_and_cancels(self):
        self.controller.handle_command(press("DOWN"))  # tm1
        self.controller.handle_command(press("DOWN"))  # m1 (long single-span MATH item)
        spoken_before = len(self.engine.spoken)
        cancels_before = self.engine.cancel_count
        frame_before = self.controller.braille_frame
        self.controller.handle_command(press("RIGHT"))  # offset 0 -> 3, same span
        self.assertEqual(len(self.engine.spoken), spoken_before)  # silent
        self.assertGreater(self.engine.cancel_count, cancels_before)  # still cancels every press
        self.assertEqual(self.controller.state.math_span_index, 0)
        self.assertNotEqual(self.controller.braille_frame, frame_before)

    def test_right_at_the_end_of_the_block_speaks_boundary_and_leaves_braille_unchanged(self):
        self.controller.handle_command(press("DOWN"))  # tm1
        self.controller.handle_command(press("DOWN"))  # m1
        for _ in range(3):
            self.controller.handle_command(press("RIGHT"))  # offsets 3, 6, 9 -- last window
        frame_at_last_window = self.controller.braille_frame
        self.controller.handle_command(press("RIGHT"))  # boundary
        self.assertIn("더 이상", self.engine.spoken[-1][0])
        self.assertEqual(self.controller.braille_frame, frame_at_last_window)

    def test_moving_to_next_top_level_item_resets_braille_scroll_state(self):
        self.controller.handle_command(press("DOWN"))  # tm1
        self.controller.handle_command(press("DOWN"))  # m1
        self.controller.handle_command(press("RIGHT"))  # scroll into m1 (offset=3)
        self.assertNotEqual(self.controller.state.braille_offset, 0)
        self.controller.handle_command(press("DOWN"))  # move on to tb1
        self.assertEqual(self.controller.state.braille_offset, 0)
        self.assertEqual(self.controller.state.math_span_index, 0)
        self.assertEqual(self.controller.braille_frame["cells"], [])  # tb1 has no scrollable math

    def test_right_on_a_table_item_still_enters_table_mode_not_braille_scroll(self):
        self.controller.handle_command(press("DOWN"))  # tm1
        self.controller.handle_command(press("DOWN"))  # m1
        self.controller.handle_command(press("DOWN"))  # tb1
        self.controller.handle_command(press("RIGHT"))
        self.assertEqual(self.controller.state.mode, "TABLE")
        self.assertEqual((self.controller.state.table_row, self.controller.state.table_column), (1, 1))

    def test_left_on_plain_text_with_no_math_reports_boundary(self):
        node_index_before = self.controller.state.node_index
        self.controller.handle_command(press("LEFT"))
        self.assertEqual(self.controller.state.node_index, node_index_before)
        self.assertIn("수식이 없습니다", self.engine.spoken[-1][0])
        self.assertEqual(self.controller.braille_frame["cells"], [])


class SpeechControllerTableBrailleScrollTests(unittest.TestCase):
    """LEFT/RIGHT LONG in TABLE mode: within-cell braille scroll, kept off
    the already-tested SHORT (cell-to-cell) behavior. viewport_size=3 so a
    long cell needs multiple windows."""

    def build_document(self):
        table_item = build_focus_item(
            "tb1", "TABLE", "p1", 0, ["tb1"],
            row_count=1, column_count=1, structure_confidence=0.95,
            cells=[{
                "id": "c11", "row_index": 1, "column_index": 1, "row_span": 1, "column_span": 1,
                "content_nodes": [{"kind": "TEXT", "text": "123456789"}],
            }],
        )
        page = build_page("p1", [table_item])
        return build_accessible_document("doc", [page])

    def setUp(self):
        self.document = self.build_document()
        self.engine = FakeTtsEngineAdapter()
        self.state = NavigationState(document_id="doc", page_index=0, node_index=0)
        self.controller = SpeechController(
            self.document, self.state, self.engine, braille_presenter=BraillePresenter(viewport_size=3),
        )
        self.controller.handle_command(press("RIGHT"))  # enter table mode, cell (1,1)

    def test_right_long_scrolls_within_cell_silently(self):
        spoken_before = len(self.engine.spoken)
        self.controller.handle_command(press("RIGHT", "LONG"))
        self.assertEqual(len(self.engine.spoken), spoken_before)  # silent
        self.assertGreater(self.controller.state.braille_offset, 0)
        self.assertEqual(self.controller.state.mode, "TABLE")

    def test_right_short_still_means_move_to_a_different_cell_not_scroll(self):
        # Only one column exists, so SHORT should hit the existing "마지막
        # 열입니다" boundary rather than doing anything scroll-related.
        self.controller.handle_command(press("RIGHT"))
        self.assertEqual(self.engine.spoken[-1][0], "마지막 열입니다.")
        self.assertEqual(self.controller.state.braille_offset, 0)

    def test_right_long_repeated_reaches_end_boundary_and_speaks_it(self):
        for _ in range(10):
            self.controller.handle_command(press("RIGHT", "LONG"))
        self.assertEqual(self.engine.spoken[-1][0], "셀 내용의 끝입니다.")

    def test_left_long_scrolls_back_to_start_boundary(self):
        for _ in range(4):
            self.controller.handle_command(press("RIGHT", "LONG"))
        self.assertGreater(self.controller.state.braille_offset, 0)
        for _ in range(10):
            self.controller.handle_command(press("LEFT", "LONG"))
        self.assertEqual(self.engine.spoken[-1][0], "셀 내용의 시작입니다.")
        self.assertEqual(self.controller.state.braille_offset, 0)


if __name__ == "__main__":
    unittest.main()
