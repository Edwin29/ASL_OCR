import unittest

from document_parser.accessibility.speech import (
    focus_item_announcement,
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

    def test_aligned_rows_use_natural_korean_ordinals(self):
        ast = {
            "type": "AlignedRows",
            "environment": "cases",
            "rows": [
                {
                    "type": "AlignedRow",
                    "cells": [
                        {"type": "Identifier", "value": "x"},
                        {"type": "Identifier", "value": "a"},
                    ],
                },
                {
                    "type": "AlignedRow",
                    "cells": [
                        {"type": "Identifier", "value": "y"},
                        {"type": "Identifier", "value": "b"},
                    ],
                },
            ],
        }

        self.assertEqual(
            math_ast_to_speech(ast),
            "첫 번째 식, x, a, 두 번째 식, y, b",
        )

    def test_legacy_flat_aligned_rows_remain_readable(self):
        ast = {
            "type": "AlignedRows",
            "children": [
                {"type": "Identifier", "value": "x"},
                {"type": "Identifier", "value": "y"},
            ],
        }

        self.assertEqual(math_ast_to_speech(ast), "첫 번째 식, x, 두 번째 식, y")

    def test_fraction_uses_natural_korean_denominator_first_order(self):
        ast = {
            "type": "Fraction",
            "numerator": {"type": "Number", "value": "1"},
            "denominator": {"type": "Number", "value": "2"},
        }
        self.assertEqual(math_ast_to_speech(ast), "2분의 1")

    def test_fraction_with_radical_matches_p030_natural_reading(self):
        ast = {
            "type": "Fraction",
            "numerator": {"type": "Radical", "radicand": {"type": "Number", "value": "71"}},
            "denominator": {"type": "Number", "value": "4"},
        }
        self.assertEqual(math_ast_to_speech(ast), "4분의 루트 71")

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
        self.assertEqual(math_ast_to_speech(ast), "x는 1과 같다")

    def test_relation_particles_follow_spoken_math_ending(self):
        ast = {
            "type": "Relation", "operator": "=",
            "left": {"type": "Identifier", "value": "m"},
            "right": {
                "type": "Power",
                "base": {"type": "Number", "value": "2"},
                "exponent": {"type": "Identifier", "value": "x"},
            },
        }
        self.assertEqual(math_ast_to_speech(ast), "m은 2의 x 제곱과 같다")

    def test_relation_less_than(self):
        ast = {
            "type": "Relation", "operator": "<",
            "left": {"type": "Identifier", "value": "a"},
            "right": {"type": "Identifier", "value": "b"},
        }
        self.assertEqual(math_ast_to_speech(ast), "a는 b보다 작다")

    def test_unicode_inequality_relations_use_spoken_korean(self):
        expected = {
            "≤": "x는 1보다 작거나 같다",
            "≥": "x는 1보다 크거나 같다",
            "≠": "x는 1과 같지 않다",
        }
        for operator, speech in expected.items():
            with self.subTest(operator=operator):
                ast = {
                    "type": "Relation", "operator": operator,
                    "left": {"type": "Identifier", "value": "x"},
                    "right": {"type": "Number", "value": "1"},
                }
                self.assertEqual(math_ast_to_speech(ast), speech)

    def test_absolute_value_delimiter_is_not_read_as_parentheses(self):
        ast = {
            "type": "Parenthesized",
            "delimiter": "|",
            "body": {"type": "Identifier", "value": "x"},
        }
        self.assertEqual(math_ast_to_speech(ast), "x의 절댓값")

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

    def test_axis_notation_is_phonetic_only_in_final_tts_announcement(self):
        item = {
            "kind": "TEXT",
            "spans": [
                {"kind": "MATH", "text": "x", "ast_status": "VALID", "presentation_ast": {"type": "Identifier", "value": "x"}, "standalone_accessibility": False},
                {"kind": "TEXT", "text": "축과 y축"},
            ],
        }
        self.assertEqual(text_focus_item_to_speech(item), "x축과 y축")
        self.assertEqual(focus_item_announcement(item), "엑스축과 와이축")

    def test_standalone_x_is_pronounced_without_rewriting_english_words(self):
        item = {
            "kind": "TEXT",
            "spans": [{"kind": "TEXT", "text": "text에서 f(x)와 2x, x=1을 확인한다."}],
        }
        self.assertEqual(
            focus_item_announcement(item),
            "text에서 에프(엑스)와 2엑스, 엑스=1을 확인한다.",
        )

    def test_other_standalone_variables_are_pronounced_but_words_are_untouched(self):
        item = {
            "kind": "TEXT",
            "spans": [{"kind": "TEXT", "text": "EBS text에서 f(x)=ax+b, g(y)=c이다."}],
        }
        self.assertEqual(
            focus_item_announcement(item),
            "EBS text에서 에프(엑스)=에이 엑스+비, 지(와이)=씨이다.",
        )

    def test_raw_relations_greek_symbols_and_absolute_value_have_fallback_readings(self):
        item = {
            "kind": "TEXT",
            "spans": [{"kind": "TEXT", "text": "|αx|≤π, y≠0, |ab|≥3"}],
        }
        self.assertEqual(
            focus_item_announcement(item),
            "알파엑스의 절댓값 작거나 같다 파이, 와이 같지 않다 0, 에이 비의 절댓값 크거나 같다 3",
        )

    def test_latex_relation_and_greek_fallbacks_are_pronounced(self):
        item = {
            "kind": "TEXT",
            "spans": [{"kind": "TEXT", "text": r"\theta \leq \pi, \Delta x \neq \infty"}],
        }
        self.assertEqual(
            focus_item_announcement(item),
            "세타 작거나 같다 파이, 델타 엑스 같지 않다 무한대",
        )


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
