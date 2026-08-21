import unittest

from document_parser.math.latex_ast import parse_latex_to_ast, validate_ast


class LatexAstParserTests(unittest.TestCase):
    """Every case here is a real LaTeX string recognized during this project's
    own formula-OCR/PaddleOCR-VL runs (p004/p019/p050/p054), not invented syntax.
    """

    def test_relation_with_radical_and_index(self):
        result = parse_latex_to_ast("x=\\sqrt[n]{a}")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast, {
            "type": "Relation",
            "operator": "=",
            "left": {"type": "Identifier", "value": "x"},
            "right": {
                "type": "Radical",
                "radicand": {"type": "Identifier", "value": "a"},
                "index": {"type": "Identifier", "value": "n"},
            },
        })

    def test_property_equation_with_power_and_parenthesized_radical(self):
        # "(na)^n=a" -- 거듭제곱근의 성질 ①
        result = parse_latex_to_ast("(\\sqrt[n]{a})^{n}=a")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "Relation")
        power = result.ast["left"]
        self.assertEqual(power["type"], "Power")
        self.assertEqual(power["base"]["type"], "Parenthesized")
        self.assertEqual(power["base"]["body"]["type"], "Radical")
        self.assertEqual(power["exponent"], {"type": "Identifier", "value": "n"})

    def test_geq_relation_uses_real_unicode_operator(self):
        result = parse_latex_to_ast("a\\geq0")

        self.assertEqual(result.ast["operator"], "≥")  # ≥
        self.assertEqual(result.unconsumed_tokens, [])

    def test_law_of_cosines_relation_chain(self):
        result = parse_latex_to_ast("a^{2}=b^{2}+c^{2}-2bc\\cos A")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "Relation")
        self.assertEqual(result.ast["left"], {
            "type": "Power",
            "base": {"type": "Identifier", "value": "a"},
            "exponent": {"type": "Number", "value": "2"},
        })

    def test_function_with_exponent_binds_to_function_not_argument(self):
        # "sin^2 A" means (sin A)^2 -- the exponent must not be swallowed as the
        # function's argument (a real bug found and fixed during development).
        result = parse_latex_to_ast("\\sin^{2}A")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast, {
            "type": "Power",
            "base": {
                "type": "FunctionApplication",
                "name": "sin",
                "argument": {"type": "Identifier", "value": "A"},
            },
            "exponent": {"type": "Number", "value": "2"},
        })

    def test_left_right_parenthesized_group_is_fully_consumed(self):
        # A real bug found and fixed: \right) was not recognized as closing the
        # group opened by \left(, leaving everything after it unconsumed.
        result = parse_latex_to_ast("b\\cos\\left(180^{\\circ}-A\\right)=c")

        self.assertEqual(result.unconsumed_tokens, [])
        error_codes = {i["code"] for i in result.issues if i["severity"] == "error"}
        self.assertNotIn("AST_UNMATCHED_PAREN", error_codes)

    def test_nested_radical_power_and_left_right_all_consumed(self):
        result = parse_latex_to_ast("\\left(\\sqrt[3]{n^{\\sqrt{2}-1}}\\right)^{\\sqrt{2}+1}")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "Power")
        self.assertEqual(result.ast["base"]["type"], "Parenthesized")
        self.assertEqual(result.ast["base"]["body"]["type"], "Radical")

    def test_absolute_value_with_fraction_inside(self):
        result = parse_latex_to_ast("a\\sin^{2}x+\\left|\\cos x-\\frac{1}{2a}\\right|")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "Row")
        abs_value = result.ast["children"][2]
        self.assertEqual(abs_value["type"], "Parenthesized")
        self.assertEqual(abs_value["delimiter"], "|")
        self.assertEqual(abs_value["body"]["type"], "Row")
        self.assertEqual(abs_value["body"]["children"][2]["type"], "Fraction")

    def test_overline_decoration_preserves_notation_without_dedicated_node_type(self):
        # \overline{BH} (segment notation) has no dedicated AST type in the
        # schema; the decoration must not be silently dropped.
        result = parse_latex_to_ast("\\overline{BH}=\\overline{AB}+\\overline{AH}")

        self.assertEqual(result.unconsumed_tokens, [])
        left = result.ast["left"]
        self.assertEqual(left["decoration"], "overline")

    def test_function_application_with_explicit_parenthesized_argument(self):
        result = parse_latex_to_ast("f(x)=x^{2}+1")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["left"], {
            "type": "FunctionApplication",
            "name": "f",
            "argument": {"type": "Parenthesized", "body": {"type": "Identifier", "value": "x"}, "delimiter": "("},
        })

    def test_relation_operator_wrapped_alone_in_braces(self):
        # Real bug found on p019 GPU output: "x^{n}{=}m^{12}" -- the "=" wrapped
        # in its own brace group by the source model. Without special-casing
        # this, the entire right-hand side was lost as unconsumed tokens.
        result = parse_latex_to_ast("x^{n}{=}m^{12}")

        self.assertEqual(result.ast, {
            "type": "Relation",
            "operator": "=",
            "left": {"type": "Power", "base": {"type": "Identifier", "value": "x"}, "exponent": {"type": "Identifier", "value": "n"}},
            "right": {"type": "Power", "base": {"type": "Identifier", "value": "m"}, "exponent": {"type": "Number", "value": "12"}},
        })
        self.assertEqual(result.unconsumed_tokens, [])

    def test_double_subscript_relation(self):
        result = parse_latex_to_ast("M_{1}-m_{1}=M_{2}-m_{2}")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "Relation")

    def test_unrecognized_command_preserved_as_unknown_not_dropped(self):
        # \circ (degree symbol) is not in this parser's covered vocabulary yet.
        # It must survive as an Unknown leaf, not vanish or corrupt the sibling
        # content around it.
        result = parse_latex_to_ast("180^{\\circ}-A")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "Row")
        self.assertEqual(result.ast["children"][0]["exponent"], {"type": "Unknown", "value": "\\circ"})
        self.assertEqual(result.ast["children"][1], {"type": "Operator", "value": "-"})
        self.assertEqual(result.ast["children"][2], {"type": "Identifier", "value": "A"})

    def test_piecewise_case_block_preserves_all_branch_content(self):
        # Full \left\{\begin{array}...\end{array}\right. case block. The
        # \left\{...\right. wrapper is now a real Parenthesized(delimiter="{")
        # group (previously it was not closed at all -- a documented,
        # now-fixed limitation), and every real math fragment inside each
        # branch and condition must still come through -- none may be
        # silently dropped.
        content = (
            "f(x)=\\left\\{\\begin{array}{ll}\\cos x & (0\\leq x\\leq a) \\\\ "
            "b \\sin x-b \\sin a+\\cos a & (a<x\\leq2\\pi)\\end{array}\\right."
        )
        result = parse_latex_to_ast(content)

        self.assertEqual(result.unconsumed_tokens, [])
        rendered = repr(result.ast)
        self.assertIn("'cos'", rendered)
        self.assertIn("'sin'", rendered)
        brace_group = result.ast["right"]
        self.assertEqual(brace_group["type"], "Parenthesized")
        self.assertEqual(brace_group["delimiter"], "{")
        aligned = brace_group["body"]
        self.assertEqual(aligned["type"], "AlignedRows")
        self.assertEqual(aligned["environment"], "array")
        self.assertEqual(len(aligned["children"]), 4)


class CommaListTests(unittest.TestCase):
    """콤마 목록: "," between complete expressions is a list separator,
    distinct from `Row` (implicit multiplication) and `AlignedRows` (real
    row/cell splits, which get numbered-tag treatment downstream). Real
    fixture evidence: p004 ("\\sqrt[n]{a}, -\\sqrt[n]{a}") and p038
    ("\\sin\\theta=\\frac{y}{r},\\cos\\theta=\\frac{x}{r},..." -- a
    comma-list of three complete relations) both previously left every
    comma and everything after the first one as unconsumed."""

    def test_bare_comma_list_of_numbers(self):
        result = parse_latex_to_ast("2,4,6")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast, {
            "type": "List",
            "children": [
                {"type": "Number", "value": "2"},
                {"type": "Number", "value": "4"},
                {"type": "Number", "value": "6"},
            ],
        })

    def test_set_notation_with_escaped_braces(self):
        result = parse_latex_to_ast("A=\\{2,4,6\\}")

        self.assertEqual(result.unconsumed_tokens, [])
        group = result.ast["right"]
        self.assertEqual(group["type"], "Parenthesized")
        self.assertEqual(group["delimiter"], "{")
        self.assertEqual(group["body"]["type"], "List")
        self.assertEqual(len(group["body"]["children"]), 3)

    def test_interval_notation_with_square_brackets(self):
        result = parse_latex_to_ast("[0,1]")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["delimiter"], "[")
        self.assertEqual(result.ast["body"]["type"], "List")

    def test_real_fixture_p038_comma_separated_relations(self):
        # Real p038 raw_formula fragment: a list of three complete relations.
        result = parse_latex_to_ast(
            "\\sin\\theta=\\frac{y}{r},\\cos\\theta=\\frac{x}{r},\\tan\\theta=\\frac{y}{x}"
        )

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "List")
        self.assertEqual(len(result.ast["children"]), 3)
        for relation in result.ast["children"]:
            self.assertEqual(relation["type"], "Relation")

    def test_real_fixture_p004_comma_separated_radicals(self):
        result = parse_latex_to_ast("\\sqrt[n]{a}, -\\sqrt[n]{a}")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "List")
        self.assertEqual(len(result.ast["children"]), 2)

    def test_single_item_is_not_wrapped_in_a_list(self):
        # No comma present -- must return the item directly, not List[item].
        result = parse_latex_to_ast("f(x)=x^{2}+1")

        self.assertNotEqual(result.ast["left"]["argument"]["body"]["type"], "List")

    def test_comma_does_not_cross_a_row_break(self):
        # A comma inside one \cases branch must not merge with content after
        # the \\\\ row break into a single flat list.
        result = parse_latex_to_ast("\\begin{cases}1,2\\\\3\\end{cases}")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "AlignedRows")
        self.assertEqual(len(result.ast["children"]), 2)
        self.assertEqual(result.ast["children"][0]["type"], "List")
        self.assertEqual(result.ast["children"][1], {"type": "Number", "value": "3"})


class BraceAndBracketDelimiterTests(unittest.TestCase):
    """중괄호/대괄호: no real fixture example exists yet for these as literal
    content delimiters (unlike AlignedRows' environment field, which was
    grounded in real p019/p038 formulas), so these are hand-authored per the
    braille regulation's request rather than reproducing an observed bug."""

    def test_escaped_curly_braces_produce_parenthesized_with_brace_delimiter(self):
        # Set-builder notation "{x>0}" written with escaped braces. Note:
        # comma-separated content ("{2,4,6,...}") is a separate, still-open
        # gap -- bare "," has no grammar rule at all yet (falls through as
        # unconsumed), so it is deliberately not exercised by this test; see
        # the braille-regulation-extraction memory for the follow-up note.
        result = parse_latex_to_ast("A=\\{x>0\\}")

        self.assertEqual(result.unconsumed_tokens, [])
        group = result.ast["right"]
        self.assertEqual(group["type"], "Parenthesized")
        self.assertEqual(group["delimiter"], "{")
        self.assertEqual(group["body"], {
            "type": "Relation", "operator": ">",
            "left": {"type": "Identifier", "value": "x"},
            "right": {"type": "Number", "value": "0"},
        })

    def test_bare_square_brackets_produce_parenthesized_with_bracket_delimiter(self):
        result = parse_latex_to_ast("[x+1]")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast, {
            "type": "Parenthesized",
            "delimiter": "[",
            "body": {
                "type": "Row",
                "children": [
                    {"type": "Identifier", "value": "x"},
                    {"type": "Operator", "value": "+"},
                    {"type": "Number", "value": "1"},
                ],
            },
        })

    def test_sqrt_index_bracket_is_unaffected_by_the_new_bracket_delimiter(self):
        # \sqrt[n]{a} must still consume its index the old way, not as a
        # standalone Parenthesized(delimiter="[").
        result = parse_latex_to_ast("\\sqrt[n]{a}")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "Radical")
        self.assertEqual(result.ast["index"], {"type": "Identifier", "value": "n"})

    def test_escaped_brace_without_matching_close_is_flagged_not_silently_wrong(self):
        result = parse_latex_to_ast("\\{x+1")

        error_codes = {i["code"] for i in result.issues if i["severity"] == "error"}
        self.assertIn("AST_UNMATCHED_BRACE", error_codes)


class SlashFractionTests(unittest.TestCase):
    """빗금 분수 (수학 점자 규정 제7항 2.): no real fixture example exists yet
    (every observed fraction so far uses `\\frac{}{}`), so these are
    hand-authored. A bare "/" previously always fell through as `Unknown`
    (never matched any grammar rule), so this is additive with no regression
    risk -- confirmed by `test_stacked_frac_is_unaffected` below."""

    def test_slash_between_numbers_is_a_notation_slash_fraction(self):
        result = parse_latex_to_ast("2/3")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast, {
            "type": "Fraction",
            "numerator": {"type": "Number", "value": "2"},
            "denominator": {"type": "Number", "value": "3"},
            "notation": "slash",
        })

    def test_slash_between_letters(self):
        result = parse_latex_to_ast("a/b")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "Fraction")
        self.assertEqual(result.ast["notation"], "slash")

    def test_slash_fraction_binds_tighter_than_addition(self):
        result = parse_latex_to_ast("1+2/3")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "Row")
        self.assertEqual(result.ast["children"][0], {"type": "Number", "value": "1"})
        self.assertEqual(result.ast["children"][1], {"type": "Operator", "value": "+"})
        self.assertEqual(result.ast["children"][2]["type"], "Fraction")

    def test_stacked_frac_is_unaffected_and_has_no_notation_field(self):
        result = parse_latex_to_ast("\\frac{1}{2}")

        self.assertEqual(result.ast, {
            "type": "Fraction",
            "numerator": {"type": "Number", "value": "1"},
            "denominator": {"type": "Number", "value": "2"},
        })
        self.assertNotIn("notation", result.ast)


class EnvironmentAwareAlignedRowsTests(unittest.TestCase):
    """`AlignedRows` now carries which `\\begin{...}` environment produced it
    (or omits the field entirely for a bare `a \\\\ b` outside any
    environment) -- braille/TTS need this to tell cases/piecewise apart from
    a plain aligned/array block, since there is no single universal
    "multiple rows" presentation rule. This also exercises a real tokenizer
    bug found while adding this: a row break (`\\\\`) immediately followed by
    a single letter (e.g. "...\\\\b(x-1)", a common \\cases pattern) used to
    greedily tokenize as a bogus one-letter command "\\b" instead of two
    row-break backslashes, silently breaking the row split.
    """

    def test_cases_environment_is_captured(self):
        result = parse_latex_to_ast("\\begin{cases}a(1-x) & x\\leq0\\\\b(x-1) & x>0\\end{cases}")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "AlignedRows")
        self.assertEqual(result.ast["environment"], "cases")

    def test_aligned_environment_is_captured_matching_real_fixture(self):
        # Same shape as the real p019 fixture's raw_formula.
        result = parse_latex_to_ast(
            "\\begin{aligned}\\sum_{m=2}^{9}f(m)=&f(2)+f(3)\\\\=&5\\times5+7\\times2+8\\end{aligned}"
        )

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["type"], "AlignedRows")
        self.assertEqual(result.ast["environment"], "aligned")

    def test_array_environment_with_column_spec_is_captured(self):
        # Same shape as the real p038 fixture's raw_formula.
        result = parse_latex_to_ast("\\begin{array}{l}a\\\\b\\end{array}")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast["environment"], "array")

    def test_row_break_outside_any_environment_has_no_environment_field(self):
        result = parse_latex_to_ast("a\\\\b")

        self.assertEqual(result.ast["type"], "AlignedRows")
        self.assertNotIn("environment", result.ast)

    def test_row_break_immediately_followed_by_letter_still_splits(self):
        # The tokenizer bug described in the class docstring: "\\\\b" used to
        # be misread as command "\b" instead of row-break + letter "b".
        result = parse_latex_to_ast("a\\\\b")

        self.assertEqual(result.ast, {
            "type": "AlignedRows",
            "children": [
                {"type": "Identifier", "value": "a"},
                {"type": "Identifier", "value": "b"},
            ],
        })
        self.assertEqual(result.unconsumed_tokens, [])


class AstValidatorTests(unittest.TestCase):
    def test_flags_missing_fraction_denominator(self):
        node = {"type": "Fraction", "numerator": {"type": "Number", "value": "1"}}

        issues = validate_ast(node)

        self.assertTrue(any(i["code"] == "AST_MISSING_REQUIRED_CHILD" for i in issues))

    def test_flags_missing_power_exponent(self):
        node = {"type": "Power", "base": {"type": "Identifier", "value": "x"}}

        issues = validate_ast(node)

        self.assertTrue(any(i["code"] == "AST_MISSING_REQUIRED_CHILD" for i in issues))

    def test_complete_fraction_has_no_issues(self):
        node = {
            "type": "Fraction",
            "numerator": {"type": "Number", "value": "1"},
            "denominator": {"type": "Identifier", "value": "x"},
        }

        issues = validate_ast(node)

        self.assertEqual(issues, [])

    def test_recurses_into_nested_children(self):
        node = {
            "type": "Relation",
            "operator": "=",
            "left": {"type": "Identifier", "value": "x"},
            "right": {"type": "Power", "base": {"type": "Identifier", "value": "a"}},  # missing exponent
        }

        issues = validate_ast(node)

        self.assertTrue(any(i["code"] == "AST_MISSING_REQUIRED_CHILD" and "$.right" in i["message"] for i in issues))

    def test_flags_unknown_nodes_as_info_not_error(self):
        node = {"type": "Unknown", "value": "\\garbled"}

        issues = validate_ast(node)

        unknown_issues = [i for i in issues if i["code"] == "AST_UNKNOWN_NODE"]
        self.assertEqual(len(unknown_issues), 1)
        self.assertEqual(unknown_issues[0]["severity"], "info")


class StandaloneSignTests(unittest.TestCase):
    """부호표(sign table) cells are often just a bare "+"/"-" with no operand
    -- previously fell through to Unknown/PARTIAL since every grammar rule
    for +/- expects an already-parsed left operand first."""

    def test_bare_plus_parses_as_a_clean_operator_node(self):
        result = parse_latex_to_ast("+")

        self.assertEqual(result.ast, {"type": "Operator", "value": "+"})
        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.issues, [])

    def test_bare_minus_parses_as_a_clean_operator_node(self):
        result = parse_latex_to_ast("-")

        self.assertEqual(result.ast, {"type": "Operator", "value": "-"})
        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.issues, [])

    def test_surrounding_whitespace_does_not_prevent_the_special_case(self):
        result = parse_latex_to_ast("  +  ")

        self.assertEqual(result.ast, {"type": "Operator", "value": "+"})
        self.assertEqual(result.unconsumed_tokens, [])

    def test_binary_usage_is_unaffected(self):
        # Regression guard: "a+b" must still go through the normal grammar
        # (Row of [Identifier, Operator, Identifier]), not the lone-sign
        # special case -- that only fires when the *entire* formula is one
        # bare sign token.
        result = parse_latex_to_ast("a+b")

        self.assertEqual(result.unconsumed_tokens, [])
        self.assertEqual(result.ast, {
            "type": "Row",
            "children": [
                {"type": "Identifier", "value": "a"},
                {"type": "Operator", "value": "+"},
                {"type": "Identifier", "value": "b"},
            ],
        })


if __name__ == "__main__":
    unittest.main()
