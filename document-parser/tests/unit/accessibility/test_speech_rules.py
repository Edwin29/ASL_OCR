import unittest

from document_parser.accessibility.speech import (
    math_ast_to_speech,
    math_focus_item_to_speech,
    table_cell_announcement,
    table_entry_announcement,
    text_focus_item_to_speech,
    visual_focus_item_to_speech,
)


def math_item(ast, ast_status="VALID"):
    return {"presentation_ast": ast, "ast_status": ast_status, "unconsumed_tokens": []}


class MathAstSpeechTests(unittest.TestCase):
    def test_identifier_and_number(self):
        self.assertEqual(math_ast_to_speech({"type": "Identifier", "value": "x"}), "x")
        self.assertEqual(math_ast_to_speech({"type": "Number", "value": "27"}), "27")

    def test_list_joins_items_with_no_row_number_prefix(self):
        # List(콤마 목록)는 AlignedRows와 달리 "N번째 식" 접두사를 붙이지
        # 않는다 -- 실제 줄바꿈이 아니라 콤마로 나열된 항목이기 때문.
        ast = {
            "type": "List",
            "children": [
                {"type": "Number", "value": "2"},
                {"type": "Number", "value": "4"},
                {"type": "Number", "value": "6"},
            ],
        }
        self.assertEqual(math_ast_to_speech(ast), "2, 4, 6")

    def test_fraction_announces_boundaries(self):
        ast = {
            "type": "Fraction",
            "numerator": {"type": "Number", "value": "1"},
            "denominator": {"type": "Number", "value": "2"},
        }
        self.assertEqual(math_ast_to_speech(ast), "분수 시작, 1, 분모, 2, 분수 끝")

    def test_power(self):
        ast = {
            "type": "Power",
            "base": {"type": "Identifier", "value": "x"},
            "exponent": {"type": "Number", "value": "2"},
        }
        self.assertEqual(math_ast_to_speech(ast), "x의 2 제곱")

    def test_radical_with_index(self):
        ast = {
            "type": "Radical",
            "radicand": {"type": "Number", "value": "27"},
            "index": {"type": "Number", "value": "3"},
        }
        self.assertEqual(math_ast_to_speech(ast), "3 제곱근 27")

    def test_radical_without_index_is_square_root(self):
        ast = {"type": "Radical", "radicand": {"type": "Number", "value": "2"}}
        self.assertEqual(math_ast_to_speech(ast), "루트 2")

    def test_unary_minus_is_distinguished_from_subtraction(self):
        ast = {"type": "UnaryMinus", "body": {"type": "Number", "value": "5"}}
        self.assertEqual(math_ast_to_speech(ast), "음수 5")

    def test_relation_equals(self):
        ast = {
            "type": "Relation", "operator": "=",
            "left": {"type": "Identifier", "value": "x"},
            "right": {"type": "Number", "value": "1"},
        }
        self.assertEqual(math_ast_to_speech(ast), "x는 1와 같다")

    def test_relation_less_than(self):
        ast = {
            "type": "Relation", "operator": "<",
            "left": {"type": "Identifier", "value": "a"},
            "right": {"type": "Identifier", "value": "b"},
        }
        self.assertEqual(math_ast_to_speech(ast), "a는 b보다 작다")

    def test_function_application(self):
        ast = {"type": "FunctionApplication", "name": "sin", "argument": {"type": "Identifier", "value": "θ"}}
        self.assertEqual(math_ast_to_speech(ast), "사인 θ")

    def test_unknown_node_is_flagged_not_skipped(self):
        self.assertEqual(math_ast_to_speech({"type": "Unknown", "value": "\\sum"}), "인식할 수 없는 기호")


class AstStatusFallbackTests(unittest.TestCase):
    def test_valid_reads_the_tree(self):
        item = math_item({"type": "Number", "value": "5"}, "VALID")
        self.assertEqual(math_focus_item_to_speech(item), "5")

    def test_invalid_never_walks_the_tree(self):
        # Even if presentation_ast looks fine, INVALID must not be read as if trustworthy.
        item = math_item({"type": "Number", "value": "5"}, "INVALID")
        self.assertEqual(math_focus_item_to_speech(item), "수식 인식이 불확실합니다.")

    def test_partial_warns_then_reads(self):
        item = math_item({"type": "Number", "value": "5"}, "PARTIAL")
        speech = math_focus_item_to_speech(item)
        self.assertTrue(speech.startswith("일부 기호 인식이 불확실합니다."))
        self.assertIn("5", speech)

    def test_standalone_sign_reads_as_the_sign_not_an_operation(self):
        # 부호표 cell: the whole formula is one bare "+"/"-", not a binary
        # connective -- "더하기"("add") would be wrong here.
        self.assertEqual(math_focus_item_to_speech(math_item({"type": "Operator", "value": "+"})), "플러스")
        self.assertEqual(math_focus_item_to_speech(math_item({"type": "Operator", "value": "-"})), "마이너스")

    def test_operator_embedded_in_a_row_still_reads_as_an_operation(self):
        # Regression guard: only a *top-level* Operator node gets the
        # standalone-sign wording -- "a+b" must still say "더하기".
        ast = {
            "type": "Row",
            "children": [
                {"type": "Identifier", "value": "a"},
                {"type": "Operator", "value": "+"},
                {"type": "Identifier", "value": "b"},
            ],
        }
        self.assertEqual(math_focus_item_to_speech(math_item(ast)), "a 더하기 b")


class TextFocusItemSpeechTests(unittest.TestCase):
    def test_assembles_mixed_text_and_math_spans_in_order(self):
        item = {
            "spans": [
                {"kind": "TEXT", "text": "함수 "},
                {"kind": "MATH", "text": "f(x)", "ast_status": "VALID", "presentation_ast": {"type": "Identifier", "value": "f"}},
                {"kind": "TEXT", "text": "에 대하여"},
            ]
        }
        self.assertEqual(text_focus_item_to_speech(item), "함수 f 에 대하여")

    def test_invalid_inline_math_span_falls_back_safely(self):
        item = {
            "spans": [
                {"kind": "TEXT", "text": "값은"},
                {"kind": "MATH", "text": "\\sum", "ast_status": "INVALID", "presentation_ast": None, "unconsumed_tokens": ["x"]},
            ]
        }
        self.assertIn("수식 인식이 불확실합니다.", text_focus_item_to_speech(item))


class TableSpeechTests(unittest.TestCase):
    def test_entry_announcement(self):
        table = {"row_count": 4, "column_count": 5}
        self.assertEqual(table_entry_announcement(table), "표, 4행 5열. 오른쪽 버튼을 눌러 표 탐색을 시작합니다.")

    def test_cell_order_is_column_row_value(self):
        cell = {"row_index": 2, "column_index": 3, "row_span": 1, "column_span": 1, "content_nodes": [{"kind": "TEXT", "text": "0.2"}]}
        self.assertEqual(table_cell_announcement(cell), "3열 2행, 값 0.2")

    def test_empty_cell(self):
        cell = {"row_index": 1, "column_index": 1, "row_span": 1, "column_span": 1, "content_nodes": []}
        self.assertEqual(table_cell_announcement(cell), "1열 1행, 빈 셀")

    def test_merged_cell_reports_full_span(self):
        cell = {"row_index": 1, "column_index": 2, "row_span": 1, "column_span": 2, "content_nodes": [{"kind": "TEXT", "text": "제목"}]}
        self.assertEqual(table_cell_announcement(cell), "2열 1행부터 3열 1행까지 병합, 값 제목")

    def test_math_cell(self):
        cell = {
            "row_index": 1, "column_index": 1, "row_span": 1, "column_span": 1,
            "content_nodes": [{"kind": "MATH", "ast_status": "VALID", "presentation_ast": {"type": "Identifier", "value": "θ"}}],
        }
        self.assertEqual(table_cell_announcement(cell), "1열 1행, 값 θ")


class VisualSpeechTests(unittest.TestCase):
    def test_announces_existence_even_with_no_preserved_text(self):
        self.assertEqual(
            visual_focus_item_to_speech({"preserved_content": []}),
            "현재 지원하지 않는 그래프 또는 도형 영역입니다.",
        )

    def test_includes_preserved_text_when_present(self):
        item = {"preserved_content": [{"kind": "TEXT", "text": "y = x^2"}]}
        speech = visual_focus_item_to_speech(item)
        self.assertIn("현재 지원하지 않는 그래프 또는 도형 영역입니다.", speech)
        self.assertIn("y = x^2", speech)


if __name__ == "__main__":
    unittest.main()
