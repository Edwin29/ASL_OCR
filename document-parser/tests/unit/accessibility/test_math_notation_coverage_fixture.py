"""Regression coverage for `tests/fixtures/accessibility/math_notation_coverage.json`.

The 6 original fixtures (p004/p018/p019/p030/p038/p088) were captured
2026-08-15, before slash-fraction notation, `ln`/`exp`/`lim`, and the `List`
AST node existed -- none of those features appear in any of them, so a
regression in their braille/speech wiring wouldn't be caught by the existing
fixture-based tests. This fixture closes that gap. It's hand-built (not a
real OCR run) but goes through the exact same production code path real
fixtures do: `vl_page_ir.build_page_ir_from_vl_result` (which calls the real
`parse_latex_to_ast`, same as the OCR pipeline) + `detect_problem_units_in_document`
+ `validate_document_ir`, matching the pattern already validated in
`tests/unit/test_vl_page_ir.py::VlPageIrTests::test_schema_valid_end_to_end`.
"""

import unittest

from document_parser.accessibility.braille.math_translator import math_focus_item_to_braille
from document_parser.accessibility.speech.math_rules import math_focus_item_to_speech

from .support import load_accessible_document


def math_spans(document):
    """Inline MATH span fragments only (each carries a `text` key) --
    top-level MATH focus items use `raw_formula` instead and are handled
    separately by `test_top_level_display_formula_slash_fraction_also_renders`."""
    spans = []
    for item in document["pages"][0]["focus_items"]:
        if item["kind"] == "TEXT":
            spans.extend(span for span in item.get("spans", []) if span.get("kind") == "MATH")
    return spans


class MathNotationCoverageFixtureTests(unittest.TestCase):
    def setUp(self):
        self.document = load_accessible_document("math_notation_coverage")
        self.spans = math_spans(self.document)

    def test_every_new_feature_span_parsed_as_valid(self):
        # If any of these regress to PARTIAL/INVALID, braille output for that
        # formula would be withheld entirely (§23 #9) -- catch that here
        # rather than discovering it only via a real device.
        statuses = {span["text"]: span["ast_status"] for span in self.spans}
        self.assertEqual(statuses, {
            "2/3": "VALID",
            "\\ln x": "VALID",
            "\\exp(x)": "VALID",
            "\\lim x": "VALID",
            "\\{1, 2, 3\\}": "VALID",
        })

    def test_slash_fraction_inline_span_renders_numerator_first(self):
        span = next(s for s in self.spans if s["text"] == "2/3")
        self.assertEqual(span["presentation_ast"]["type"], "Fraction")
        self.assertEqual(span["presentation_ast"]["notation"], "slash")
        self.assertTrue(math_focus_item_to_braille(span))  # must not raise
        self.assertEqual(math_focus_item_to_speech(span), "분수 시작, 2, 분모, 3, 분수 끝")

    def test_top_level_display_formula_slash_fraction_also_renders(self):
        top_level = next(i for i in self.document["pages"][0]["focus_items"] if i["kind"] == "MATH")
        self.assertEqual(top_level["ast_status"], "VALID")
        self.assertEqual(top_level["presentation_ast"]["notation"], "slash")
        self.assertTrue(math_focus_item_to_braille(top_level))

    def test_ln_exp_lim_render_without_raising(self):
        for text in ("\\ln x", "\\exp(x)", "\\lim x"):
            span = next(s for s in self.spans if s["text"] == text)
            with self.subTest(text=text):
                self.assertTrue(math_focus_item_to_braille(span))
                self.assertTrue(math_focus_item_to_speech(span))

    def test_brace_delimited_comma_list_renders_as_list_inside_parenthesized(self):
        span = next(s for s in self.spans if s["text"] == "\\{1, 2, 3\\}")
        ast = span["presentation_ast"]
        self.assertEqual(ast["type"], "Parenthesized")
        self.assertEqual(ast["delimiter"], "{")
        self.assertEqual(ast["body"]["type"], "List")
        self.assertEqual([c["value"] for c in ast["body"]["children"]], ["1", "2", "3"])
        self.assertTrue(math_focus_item_to_braille(span))
        self.assertEqual(math_focus_item_to_speech(span), "괄호 열고 1, 2, 3 괄호 닫고")


if __name__ == "__main__":
    unittest.main()
