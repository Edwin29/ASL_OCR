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
        abs_value = result.ast["right"]
        self.assertEqual(abs_value["type"], "Parenthesized")
        self.assertEqual(abs_value["delimiter"], "|")
        self.assertEqual(abs_value["body"]["right"]["type"], "Fraction")

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
        self.assertEqual(result.ast["left"]["exponent"], {"type": "Unknown", "value": "\\circ"})
        self.assertEqual(result.ast["right"], {"type": "Identifier", "value": "A"})

    def test_piecewise_case_block_preserves_all_branch_content(self):
        # Full \left\{\begin{array}...\end{array}\right. case block. The outer
        # \left\{...\right. wrapper is not perfectly closed (a documented,
        # separately-tracked limitation), but every real math fragment inside
        # each branch and condition must still come through -- none may be
        # silently dropped.
        content = (
            "f(x)=\\left\\{\\begin{array}{ll}\\cos x & (0\\leq x\\leq a) \\\\ "
            "b \\sin x-b \\sin a+\\cos a & (a<x\\leq2\\pi)\\end{array}\\right."
        )
        result = parse_latex_to_ast(content)

        rendered = repr(result.ast)
        self.assertIn("'cos'", rendered)
        self.assertIn("'sin'", rendered)
        branches = result.ast["right"]["children"]
        self.assertEqual(len(branches), 4)


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


if __name__ == "__main__":
    unittest.main()
