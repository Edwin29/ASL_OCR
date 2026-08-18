import unittest

from document_parser.accessibility.braille import (
    ABSOLUTE_VALUE_CELL,
    BRACE_CLOSE_CELL,
    BRACE_OPEN_CELL,
    BRACKET_CLOSE_CELLS,
    BRACKET_OPEN_CELLS,
    BraillePresenter,
    CAPITAL_INDICATOR_CELL,
    COMMA_CELL,
    DIGIT_CELLS,
    DIGIT_INDICATOR_CELL,
    FINAL_CONSONANT_CELLS,
    FRACTION_BAR_CELL,
    FUNCTION_NAME_CELLS,
    GREEK_LETTER_CELLS,
    GROUPING_BRACKET_CLOSE,
    GROUPING_BRACKET_OPEN,
    INITIAL_CONSONANT_CELLS,
    last_window_offset,
    LOG_CELL,
    MATH_OPERATOR_CELLS,
    PAREN_CLOSE_CELL,
    PAREN_OPEN_CELL,
    RADICAL_CELL,
    RADICAL_NTH_CELL,
    RegulationBrailleTranslator,
    ROMAN_LOWER_CELLS,
    SLASH_FRACTION_CELLS,
    SUBSCRIPT_INDICATOR_CELL,
    SUPERSCRIPT_INDICATOR_CELL,
    build_frame,
    cell,
    cell_to_int,
    clear_frame,
    math_focus_item_to_braille,
    scroll,
    table_cell_braille,
)


class DigitEncodingTests(unittest.TestCase):
    def setUp(self):
        self.translator = RegulationBrailleTranslator()

    def test_all_ten_digits_are_distinct(self):
        self.assertEqual(len(set(DIGIT_CELLS.values())), 10)

    def test_digit_indicator_precedes_every_digit_string(self):
        cells = self.translator.translate_digit("375")
        self.assertEqual(cells[0], DIGIT_INDICATOR_CELL)
        self.assertEqual(cells[1:], [DIGIT_CELLS["3"], DIGIT_CELLS["7"], DIGIT_CELLS["5"]])

    def test_rejects_non_digit_input(self):
        with self.assertRaises(ValueError):
            self.translator.translate_digit("3a")


class ConsonantEncodingTests(unittest.TestCase):
    def test_fourteen_initial_consonants_all_distinct(self):
        self.assertEqual(len(INITIAL_CONSONANT_CELLS), 13)  # 'ㅇ' intentionally omitted, see module docstring
        self.assertEqual(len(set(INITIAL_CONSONANT_CELLS.values())), 13)

    def test_fourteen_final_consonants_all_distinct(self):
        self.assertEqual(len(FINAL_CONSONANT_CELLS), 14)
        self.assertEqual(len(set(FINAL_CONSONANT_CELLS.values())), 14)

    def test_initial_and_final_forms_differ_for_same_letter(self):
        # 초성/종성 점형은 서로 다르다 (예: ㄱ 초성={4}, 종성={1}).
        self.assertNotEqual(INITIAL_CONSONANT_CELLS["ㄱ"], FINAL_CONSONANT_CELLS["ㄱ"])


class UnverifiedSymbolStubTests(unittest.TestCase):
    """These must fail loudly, not silently return a guessed pattern."""

    def setUp(self):
        self.translator = RegulationBrailleTranslator()

    def test_hangul_syllable_translation_raises_for_unsupported_characters(self):
        # 한글 음절/공백은 지원하지만, 그 밖의 문자(라틴 문자, 한자 등)가
        # 섞여 있으면 여전히 추측하지 않고 실패해야 한다.
        with self.assertRaises(NotImplementedError):
            self.translator.translate_hangul_syllable("A")

    def test_unverified_math_symbol_raises(self):
        with self.assertRaises(NotImplementedError):
            self.translator.translate_math_symbol("\\frac")

    def test_verified_operator_does_not_raise(self):
        self.assertEqual(self.translator.translate_math_symbol("+"), [cell(2, 6)])

    def test_equals_sign_is_the_corrected_value(self):
        # Regression test: this was initially misread as {1,3,4,6};{1,3,4,6}
        # and corrected to {2,5};{2,5} after re-reading "ax=b" and
        # "32+24=56" (printed p.51) directly -- see cell_encoding.py's
        # module docstring and MATH_OPERATOR_CELLS comment for the full story.
        self.assertEqual(MATH_OPERATOR_CELLS["="], (cell(2, 5), cell(2, 5)))


class RelationOperatorBrailleTests(unittest.TestCase):
    """수학 점자 규정 제4항(부등호, printed p.52). "a>b", "x<0", "x≥5", "x≤0",
    "y≠0" 예시로 각각 재확인했다. 두 칸씩 같은 점형을 반복하는 일관된
    패턴이다: >와 <는 사칙연산 기호(+, -)를 그대로 반복하고, ≥/≤는 그
    사칙연산 기호와 등호(=)의 점을 합친다, ≠는 부정 접두 {4,6} + 등호 반복."""

    def setUp(self):
        self.translator = RegulationBrailleTranslator()

    def test_greater_than_repeats_the_addition_cell(self):
        self.assertEqual(self.translator.translate_math_symbol(">"), [cell(2, 6), cell(2, 6)])
        self.assertEqual(MATH_OPERATOR_CELLS[">"], MATH_OPERATOR_CELLS["+"] * 2)

    def test_less_than_repeats_the_subtraction_cell(self):
        self.assertEqual(self.translator.translate_math_symbol("<"), [cell(3, 5), cell(3, 5)])
        self.assertEqual(MATH_OPERATOR_CELLS["<"], MATH_OPERATOR_CELLS["-"] * 2)

    def test_greater_or_equal_unions_greater_than_and_equals_dots(self):
        self.assertEqual(self.translator.translate_math_symbol("≥"), [cell(2, 5, 6), cell(2, 5, 6)])

    def test_less_or_equal_unions_less_than_and_equals_dots(self):
        self.assertEqual(self.translator.translate_math_symbol("≤"), [cell(2, 3, 5), cell(2, 3, 5)])

    def test_not_equal_is_negation_prefix_then_equals(self):
        self.assertEqual(
            self.translator.translate_math_symbol("≠"),
            [cell(4, 6), cell(2, 5), cell(2, 5)],
        )

    def test_relation_node_routes_operator_through_translate_math_symbol(self):
        node = {
            "type": "Relation", "operator": ">",
            "left": {"type": "Number", "value": "5"},
            "right": {"type": "Number", "value": "3"},
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["5"],
            cell(2, 6), cell(2, 6),
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["3"],
        ])

    def test_congruence_is_verified_separately_from_the_other_relations(self):
        # 제43항(기하, 합동), printed p.68 -- "△ABC≡△DEF" 예시로 확인. 제4항
        # 부등호와는 다른 조항이라 별도로 검증한다.
        self.assertEqual(self.translator.translate_math_symbol("≡"), [cell(2, 3, 5, 6), cell(2, 3, 5, 6)])


class FunctionApplicationBrailleTests(unittest.TestCase):
    """수학 점자 규정 제46항(로그)/제47항(삼각함수, printed p.69-70). 밑
    없는 "log 2" 예시와 제47항 규정 표에서 직접 재확인했다."""

    def test_log_without_base_is_log_cell_then_argument(self):
        node = {"type": "FunctionApplication", "name": "log", "argument": {"type": "Number", "value": "2"}}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            LOG_CELL, DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
        ])

    def test_trig_function_names_match_the_regulation_table(self):
        expected = {
            "sin": (cell(2, 3, 5), cell(2, 3, 4)),
            "cos": (cell(2, 3, 5), cell(1, 4)),
            "tan": (cell(2, 3, 5), cell(2, 3, 4, 5)),
            "csc": (cell(2, 3, 5), cell(1, 2, 6)),
            "sec": (cell(2, 3, 5), cell(3, 6)),
            "cot": (cell(2, 3, 5), cell(1, 2, 5, 6)),
        }
        self.assertEqual(FUNCTION_NAME_CELLS, {
            **expected,
            "log": (LOG_CELL,),
            "ln": (ROMAN_LOWER_CELLS["l"], ROMAN_LOWER_CELLS["n"]),
            "exp": (ROMAN_LOWER_CELLS["e"], ROMAN_LOWER_CELLS["x"], ROMAN_LOWER_CELLS["p"]),
            "lim": (ROMAN_LOWER_CELLS["l"], ROMAN_LOWER_CELLS["i"], ROMAN_LOWER_CELLS["m"]),
        })

    def test_ln_is_spelled_as_plain_roman_letters_then_argument(self):
        # 전용 기호 없이 로마자 l, n을 그대로 이어 적는다(외부 조사 보고서
        # 근거, 셀 값 자체는 기존 검증된 ROMAN_LOWER_CELLS 재사용).
        node = {"type": "FunctionApplication", "name": "ln", "argument": {"type": "Identifier", "value": "x"}}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            ROMAN_LOWER_CELLS["l"], ROMAN_LOWER_CELLS["n"], ROMAN_LOWER_CELLS["x"],
        ])

    def test_exp_is_spelled_literally_as_alphabet_exp_then_argument(self):
        # 사용자 지시: "exp는 알파벳 그대로 exp(수식)라고 적는다".
        node = {"type": "FunctionApplication", "name": "exp", "argument": {"type": "Identifier", "value": "x"}}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            ROMAN_LOWER_CELLS["e"], ROMAN_LOWER_CELLS["x"], ROMAN_LOWER_CELLS["p"],
            ROMAN_LOWER_CELLS["x"],
        ])

    def test_lim_without_a_limit_target_is_spelled_as_plain_roman_letters(self):
        # 첨자 없는 단순 lim(식) 형태만 지원 -- \lim_{x\to b} 같은 극한 범위
        # 구조는 파서가 아직 못 만든다(별도 미해결 항목).
        node = {"type": "FunctionApplication", "name": "lim", "argument": {"type": "Identifier", "value": "x"}}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            ROMAN_LOWER_CELLS["l"], ROMAN_LOWER_CELLS["i"], ROMAN_LOWER_CELLS["m"],
            ROMAN_LOWER_CELLS["x"],
        ])

    def test_compound_argument_is_wrapped_in_grouping_brackets(self):
        # 제47항 [붙임]: 인수가 곱/다항식이면 묶음괄호로 감싼다.
        node = {
            "type": "FunctionApplication", "name": "sin",
            "argument": {
                "type": "Row",
                "children": [{"type": "Number", "value": "1"}, {"type": "Number", "value": "2"}],
            },
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        cells = math_focus_item_to_braille(item)
        self.assertEqual(cells, [
            cell(2, 3, 5), cell(2, 3, 4),
            GROUPING_BRACKET_OPEN,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["1"],
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
            GROUPING_BRACKET_CLOSE,
        ])

    def test_unverified_function_name_raises(self):
        # arcsin 등은 FUNCTION_NAME_CELLS에 없는 이름이라 아직 미확인이다.
        node = {"type": "FunctionApplication", "name": "arcsin", "argument": {"type": "Number", "value": "2"}}
        item = {"ast_status": "VALID", "presentation_ast": node}
        with self.assertRaises(NotImplementedError):
            math_focus_item_to_braille(item)


class UnaryMinusBrailleTests(unittest.TestCase):
    """별도 조항 없음 -- "-5 < x < -2" 예시(제4항, p.52)에서 이항 뺄셈과
    단항 음수 부호가 점자에서 구별되지 않음을 직접 확인했다."""

    def test_unary_minus_reuses_the_subtraction_cell(self):
        node = {"type": "UnaryMinus", "body": {"type": "Number", "value": "5"}}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            cell(3, 5), DIGIT_INDICATOR_CELL, DIGIT_CELLS["5"],
        ])
        self.assertEqual(MATH_OPERATOR_CELLS["-"], (cell(3, 5),))

    def test_compound_body_is_wrapped_in_grouping_brackets(self):
        node = {
            "type": "UnaryMinus",
            "body": {
                "type": "Row",
                "children": [{"type": "Number", "value": "1"}, {"type": "Number", "value": "2"}],
            },
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        cells = math_focus_item_to_braille(item)
        self.assertEqual(cells, [
            cell(3, 5),
            GROUPING_BRACKET_OPEN,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["1"],
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
            GROUPING_BRACKET_CLOSE,
        ])


class AlignedRowsBrailleTests(unittest.TestCase):
    """설계 결정(2026-08-17): 연립식/aligned/array를 규정의 실제 줄바꿈
    방식 대신, TTS의 기존 "N번째 식, ..." 방식(speech/math_rules.py)에
    맞춰 각 행 앞에 번호 태그를 붙이고 한 줄짜리 버퍼로 이어붙인다. 번호
    태그는 규정에서 읽어낸 값이 아니라 프로젝트 표기 관례이므로, 이미
    검증된 묶음괄호로 감싸 본문 숫자와 구분한다."""

    def test_two_rows_get_numbered_and_concatenated(self):
        node = {
            "type": "AlignedRows",
            "environment": "cases",
            "children": [
                {"type": "Number", "value": "1"},
                {"type": "Number", "value": "2"},
            ],
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            GROUPING_BRACKET_OPEN, DIGIT_INDICATOR_CELL, DIGIT_CELLS["1"], GROUPING_BRACKET_CLOSE,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["1"],
            GROUPING_BRACKET_OPEN, DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"], GROUPING_BRACKET_CLOSE,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
        ])

    def test_environment_value_does_not_change_the_output(self):
        # 세 규정(연립식/행렬/줄바꿈)을 각각 재현하지 않고 하나의 방식으로
        # 통일했으므로, environment 값이 달라도 결과는 같아야 한다.
        base = {"type": "Number", "value": "7"}
        cases_item = {"ast_status": "VALID", "presentation_ast": {
            "type": "AlignedRows", "environment": "cases", "children": [base],
        }}
        no_env_item = {"ast_status": "VALID", "presentation_ast": {
            "type": "AlignedRows", "children": [base],
        }}
        self.assertEqual(
            math_focus_item_to_braille(cases_item),
            math_focus_item_to_braille(no_env_item),
        )

    def test_row_number_tag_is_distinguishable_from_row_content(self):
        # 번호 태그가 묶음괄호로 감싸져 있어, 내용이 우연히 같은 숫자여도
        # 태그와 본문이 같은 셀 시퀀스로 뭉개지지 않는다.
        node = {
            "type": "AlignedRows",
            "children": [{"type": "Number", "value": "1"}],
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        cells = math_focus_item_to_braille(item)
        self.assertEqual(cells[0], GROUPING_BRACKET_OPEN)
        self.assertEqual(cells[-2], DIGIT_INDICATOR_CELL)
        self.assertEqual(cells[-1], DIGIT_CELLS["1"])


class ListBrailleTests(unittest.TestCase):
    """수학 점자 규정 제1항 [붙임](쉼표), printed p.51. "5,700,000" 예시로
    COMMA_CELL={2}를 확인했다 (숫자 세 자리 구분용 쉼표 조항이지만, 점자
    쉼표는 문맥과 무관한 하나의 구두점이라 List의 항목 구분자로도 재사용
    -- AlignedRows와 달리 번호 태그를 붙이지 않는다: 실제 줄바꿈이 아니라
    콤마로 나열된 항목일 뿐이므로)."""

    def test_items_are_joined_by_a_single_comma_cell(self):
        node = {
            "type": "List",
            "children": [
                {"type": "Number", "value": "2"},
                {"type": "Number", "value": "4"},
                {"type": "Number", "value": "6"},
            ],
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
            COMMA_CELL,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["4"],
            COMMA_CELL,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["6"],
        ])

    def test_list_gets_no_numbered_tag_unlike_aligned_rows(self):
        # List는 실제 줄바꿈이 아니므로 AlignedRows의 묶음괄호 번호 태그를
        # 붙이지 않는다 -- 콤마로만 구분한다.
        node = {"type": "List", "children": [{"type": "Number", "value": "1"}]}
        item = {"ast_status": "VALID", "presentation_ast": node}
        cells = math_focus_item_to_braille(item)
        self.assertNotIn(GROUPING_BRACKET_OPEN, cells)

    def test_set_notation_inside_braces(self):
        # "A={2,4,6}" 예시: 중괄호로 감싼 List.
        node = {
            "type": "Parenthesized",
            "delimiter": "{",
            "body": {
                "type": "List",
                "children": [{"type": "Number", "value": "2"}, {"type": "Number", "value": "4"}],
            },
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            BRACE_OPEN_CELL,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
            COMMA_CELL,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["4"],
            BRACE_CLOSE_CELL,
        ])


class ViewportTests(unittest.TestCase):
    def _buffer(self, n):
        return [cell(i % 6 + 1) for i in range(n)]

    def test_first_window_matches_viewport_size(self):
        frame = build_frame("s1", self._buffer(25), offset=0, viewport_size=10)
        self.assertEqual(len(frame["cells"]), 10)
        self.assertFalse(frame["has_previous"])
        self.assertTrue(frame["has_next"])

    def test_last_window_may_be_shorter(self):
        frame = build_frame("s1", self._buffer(25), offset=20, viewport_size=10)
        self.assertEqual(len(frame["cells"]), 5)
        self.assertFalse(frame["has_next"])

    def test_scroll_right_then_left_returns_to_start(self):
        buf = self._buffer(37)
        f1 = build_frame("s1", buf, offset=0, viewport_size=10)
        f2 = scroll("s1", buf, f1["offset"], 10, "RIGHT")
        self.assertEqual(f2["offset"], 10)
        f3 = scroll("s1", buf, f2["offset"], 10, "LEFT")
        self.assertEqual(f3["offset"], 0)

    def test_every_cell_reachable_at_10_15_and_20_width(self):
        buf = self._buffer(47)
        for size in (10, 15, 20):
            seen = 0
            offset = 0
            while True:
                frame = build_frame("s1", buf, offset, size)
                seen += len(frame["cells"])
                if not frame["has_next"]:
                    break
                offset += size
            self.assertEqual(seen, len(buf), f"viewport_size={size}")

    def test_clear_frame_is_empty(self):
        frame = clear_frame("s1")
        self.assertEqual(frame["cells"], [])
        self.assertEqual(frame["total_cell_count"], 0)

    def test_cell_to_int_packs_dots_as_bits(self):
        self.assertEqual(cell_to_int(cell(1)), 0b000001)
        self.assertEqual(cell_to_int(cell(6)), 0b100000)
        self.assertEqual(cell_to_int(cell(1, 6)), 0b100001)
        self.assertEqual(cell_to_int(cell()), 0)


class MathBrailleGatingTests(unittest.TestCase):
    """The ast_status gate is fully specified policy (§23 #9) and testable
    without any unverified symbol table."""

    def test_invalid_status_withholds_braille_entirely(self):
        item = {"ast_status": "INVALID", "presentation_ast": {"type": "Number", "value": "5"}}
        self.assertEqual(math_focus_item_to_braille(item), [])

    def test_partial_status_also_withholds_braille_entirely(self):
        # User decision: PARTIAL gets the same treatment as INVALID for braille,
        # unlike TTS which may still announce the validated part.
        item = {"ast_status": "PARTIAL", "presentation_ast": {"type": "Number", "value": "5"}}
        self.assertEqual(math_focus_item_to_braille(item), [])

    def test_valid_simple_number_produces_digit_cells(self):
        item = {"ast_status": "VALID", "presentation_ast": {"type": "Number", "value": "5"}}
        cells = math_focus_item_to_braille(item)
        self.assertEqual(cells, [DIGIT_INDICATOR_CELL, DIGIT_CELLS["5"]])

    def test_valid_unsupported_node_type_raises_rather_than_guessing(self):
        item = {
            "ast_status": "VALID",
            "presentation_ast": {
                "type": "Subsuperscript",
                "base": {"type": "Number", "value": "2"},
                "subscript": {"type": "Number", "value": "1"},
                "exponent": {"type": "Number", "value": "3"},
            },
        }
        with self.assertRaises(NotImplementedError):
            math_focus_item_to_braille(item)


class FractionBrailleTests(unittest.TestCase):
    """수학 점자 규정 제7항. 값은 printed p.54의 3/4, 3-1/6(대분수),
    x+1/y, 1/(x+y) 예시를 직접 읽어 재확인했다."""

    def test_simple_fraction_is_denominator_bar_numerator(self):
        # 3/4 예시(p.54): 분모(4), 분수표, 분자(3) 순서 -- 괄호 없음.
        node = {
            "type": "Fraction",
            "numerator": {"type": "Number", "value": "3"},
            "denominator": {"type": "Number", "value": "4"},
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["4"],
            FRACTION_BAR_CELL,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["3"],
        ])

    def test_atomic_denominator_is_not_bracketed(self):
        # p.54 "x+1/y" 예시: 분모 y는 단일 Identifier라 괄호 없이 적힌다.
        # (Identifier 자체는 아직 미검증이므로 Number로 구조만 검증.)
        node = {
            "type": "Fraction",
            "numerator": {"type": "Number", "value": "1"},
            "denominator": {"type": "Number", "value": "5"},
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        cells = math_focus_item_to_braille(item)
        self.assertNotIn(GROUPING_BRACKET_OPEN, cells)
        self.assertNotIn(GROUPING_BRACKET_CLOSE, cells)

    def test_compound_denominator_is_wrapped_in_grouping_brackets(self):
        # p.54 "1/(x+y)" 예시: 분모가 여러 항의 Row라 묶음괄호로 감싼다.
        node = {
            "type": "Fraction",
            "numerator": {"type": "Number", "value": "1"},
            "denominator": {
                "type": "Row",
                "children": [{"type": "Number", "value": "2"}, {"type": "Number", "value": "3"}],
            },
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        cells = math_focus_item_to_braille(item)
        self.assertEqual(cells, [
            GROUPING_BRACKET_OPEN,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["3"],
            GROUPING_BRACKET_CLOSE,
            FRACTION_BAR_CELL,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["1"],
        ])

    def test_slash_notation_is_numerator_slash_denominator(self):
        # 제7항 2., printed p.54 "2/3" 예시: 분자, 빗금(2칸), 분모 순서 --
        # 스택형(분모 먼저)과 반대다.
        node = {
            "type": "Fraction", "notation": "slash",
            "numerator": {"type": "Number", "value": "2"},
            "denominator": {"type": "Number", "value": "3"},
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
            *SLASH_FRACTION_CELLS,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["3"],
        ])


class RadicalBrailleTests(unittest.TestCase):
    """수학 점자 규정 제22항. 값은 printed p.63의 √2, √xy 예시를 직접 읽어
    재확인했다."""

    def test_simple_radical_is_radical_cell_then_radicand(self):
        node = {"type": "Radical", "radicand": {"type": "Number", "value": "2"}}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            RADICAL_CELL, DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
        ])

    def test_compound_radicand_is_wrapped_in_grouping_brackets(self):
        # p.63 [붙임2] "√xy" 예시: 근호 안이 여러 항의 Row라 묶음괄호로 감싼다.
        node = {
            "type": "Radical",
            "radicand": {
                "type": "Row",
                "children": [{"type": "Number", "value": "7"}, {"type": "Number", "value": "8"}],
            },
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        cells = math_focus_item_to_braille(item)
        self.assertEqual(cells, [
            RADICAL_CELL,
            GROUPING_BRACKET_OPEN,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["7"],
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["8"],
            GROUPING_BRACKET_CLOSE,
        ])

    def test_nth_root_is_index_then_nth_radical_cell_then_radicand(self):
        # p.63 [붙임1] "⁵√32" 예시: 근수(5), 별도 근호 기호(RADICAL_NTH_CELL,
        # 일반 RADICAL_CELL과 다름), 근호 안 내용(32) 순서.
        node = {
            "type": "Radical",
            "radicand": {"type": "Number", "value": "32"},
            "index": {"type": "Number", "value": "5"},
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["5"],
            RADICAL_NTH_CELL,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["3"], DIGIT_CELLS["2"],
        ])
        self.assertNotEqual(RADICAL_NTH_CELL, RADICAL_CELL)


class PowerBrailleTests(unittest.TestCase):
    """수학 점자 규정 제18항. 값은 printed p.61의 c^2 예시를 직접 읽어
    재확인했다 (base c는 아직 미검증인 로마자라 Number로 구조만 검증)."""

    def test_simple_power_is_base_then_indicator_then_exponent(self):
        # 8^2 예시(p.61)와 동일한 구조: base(8), 위첨자 기호, exponent(2).
        node = {
            "type": "Power",
            "base": {"type": "Number", "value": "8"},
            "exponent": {"type": "Number", "value": "2"},
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["8"],
            SUPERSCRIPT_INDICATOR_CELL,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
        ])

    def test_compound_exponent_is_wrapped_in_grouping_brackets(self):
        # p.61 [붙임] "x^{7+9}" 예시: 지수가 여러 항의 Row라 묶음괄호로 감싼다.
        node = {
            "type": "Power",
            "base": {"type": "Number", "value": "5"},
            "exponent": {
                "type": "Row",
                "children": [{"type": "Number", "value": "7"}, {"type": "Number", "value": "9"}],
            },
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        cells = math_focus_item_to_braille(item)
        self.assertEqual(cells, [
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["5"],
            SUPERSCRIPT_INDICATOR_CELL,
            GROUPING_BRACKET_OPEN,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["7"],
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["9"],
            GROUPING_BRACKET_CLOSE,
        ])


class SubscriptBrailleTests(unittest.TestCase):
    """수학 점자 규정 제19항. 값은 printed p.62의 x_2 예시를 직접 읽어
    재확인했다."""

    def test_simple_subscript_is_base_then_indicator_then_subscript(self):
        node = {
            "type": "Subscript",
            "base": {"type": "Number", "value": "3"},
            "subscript": {"type": "Number", "value": "2"},
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["3"],
            SUBSCRIPT_INDICATOR_CELL,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
        ])

    def test_compound_subscript_is_wrapped_in_grouping_brackets(self):
        # p.62 [붙임] "a_{n+3}" 예시: 아래첨자가 여러 항의 Row라 묶음괄호로 감싼다.
        node = {
            "type": "Subscript",
            "base": {"type": "Number", "value": "1"},
            "subscript": {
                "type": "Row",
                "children": [{"type": "Number", "value": "4"}, {"type": "Number", "value": "6"}],
            },
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        cells = math_focus_item_to_braille(item)
        self.assertEqual(cells, [
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["1"],
            SUBSCRIPT_INDICATOR_CELL,
            GROUPING_BRACKET_OPEN,
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["4"],
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["6"],
            GROUPING_BRACKET_CLOSE,
        ])

    def test_subsuperscript_combined_ordering_is_not_yet_implemented(self):
        # 아래첨자+위첨자를 동시에 적는 순서는 규정에서 아직 확인하지 못했다.
        node = {
            "type": "Subsuperscript",
            "base": {"type": "Number", "value": "2"},
            "subscript": {"type": "Number", "value": "1"},
            "exponent": {"type": "Number", "value": "3"},
        }
        item = {"ast_status": "VALID", "presentation_ast": node}
        with self.assertRaises(NotImplementedError):
            math_focus_item_to_braille(item)


class RomanAndGreekLetterTests(unittest.TestCase):
    """수학 점자 규정 제12항(로마자)/제13항(그리스 문자). c, x, y는 √xy·c²·x₂
    예시로, a, b는 "ax=b" 예시로 이 세션에서 직접 재확인했다. 나머지는 위임
    추출 문서의 표를 따른다 (전체 표를 p.57에서 직접 재대조하지는 않음)."""

    def setUp(self):
        self.translator = RegulationBrailleTranslator()

    def test_lowercase_roman_letter_has_no_indicator(self):
        self.assertEqual(self.translator.translate_math_symbol("x"), [cell(1, 3, 4, 6)])

    def test_uppercase_roman_letter_gets_capital_indicator(self):
        # "전치행렬 A" 예시(p.62)에서 {6};{1} = 대문자표 + 로마자 a로 확인.
        self.assertEqual(
            self.translator.translate_math_symbol("A"),
            [CAPITAL_INDICATOR_CELL, ROMAN_LOWER_CELLS["a"]],
        )

    def test_all_26_roman_lowercase_letters_are_distinct(self):
        self.assertEqual(len(ROMAN_LOWER_CELLS), 26)
        self.assertEqual(len(set(ROMAN_LOWER_CELLS.values())), 26)

    def test_greek_lowercase_letter_uses_greek_indicator(self):
        self.assertEqual(self.translator.translate_math_symbol("ω"), [cell(4, 6), cell(2, 4, 5, 6)])

    def test_greek_uppercase_letter_adds_capital_indicator(self):
        self.assertEqual(
            self.translator.translate_math_symbol("Δ"),
            [CAPITAL_INDICATOR_CELL, cell(4, 6), cell(1, 4, 5)],
        )

    def test_non_greek_constant_symbol_still_raises(self):
        # "∞"(infty)는 그리스 문자가 아니라서 GREEK_LETTER_CELLS에 없다 --
        # 추측해서 채우지 않고 여전히 실패해야 한다.
        with self.assertRaises(NotImplementedError):
            self.translator.translate_math_symbol("∞")


class IdentifierBrailleTests(unittest.TestCase):
    def test_roman_identifier_routes_through_translate_math_symbol(self):
        node = {"type": "Identifier", "value": "y"}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [cell(1, 3, 4, 5, 6)])

    def test_greek_identifier_routes_through_translate_math_symbol(self):
        node = {"type": "Identifier", "value": "π"}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), list(GREEK_LETTER_CELLS["π"]))


class ParenthesizedBrailleTests(unittest.TestCase):
    """수학 점자 규정 제6항 1.(괄호)/제21항(절댓값). "58-(17+14)", "|x|"
    예시로 확인. 분수/근호용 묶음괄호와는 별개의 점형을 쓴다."""

    def test_real_parentheses_wrap_body_unconditionally(self):
        node = {"type": "Parenthesized", "delimiter": "(", "body": {"type": "Number", "value": "5"}}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            PAREN_OPEN_CELL, DIGIT_INDICATOR_CELL, DIGIT_CELLS["5"], PAREN_CLOSE_CELL,
        ])

    def test_absolute_value_uses_same_cell_both_sides(self):
        node = {"type": "Parenthesized", "delimiter": "|", "body": {"type": "Number", "value": "5"}}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            ABSOLUTE_VALUE_CELL, DIGIT_INDICATOR_CELL, DIGIT_CELLS["5"], ABSOLUTE_VALUE_CELL,
        ])

    def test_parentheses_and_grouping_brackets_are_different_cells(self):
        self.assertNotEqual(PAREN_OPEN_CELL, GROUPING_BRACKET_OPEN)
        self.assertNotEqual(PAREN_CLOSE_CELL, GROUPING_BRACKET_CLOSE)

    def test_curly_brace_delimiter_wraps_body_unconditionally(self):
        # 제6항 1., printed p.53. AST의 delimiter="{"는 실제 소스에 쓰인
        # 이스케이프된 중괄호(예: 집합 표기 "\{x>0\}")를 나타낸다.
        node = {"type": "Parenthesized", "delimiter": "{", "body": {"type": "Number", "value": "5"}}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            BRACE_OPEN_CELL, DIGIT_INDICATOR_CELL, DIGIT_CELLS["5"], BRACE_CLOSE_CELL,
        ])

    def test_square_bracket_delimiter_wraps_body_unconditionally(self):
        node = {"type": "Parenthesized", "delimiter": "[", "body": {"type": "Number", "value": "5"}}
        item = {"ast_status": "VALID", "presentation_ast": node}
        self.assertEqual(math_focus_item_to_braille(item), [
            *BRACKET_OPEN_CELLS, DIGIT_INDICATOR_CELL, DIGIT_CELLS["5"], *BRACKET_CLOSE_CELLS,
        ])

    def test_brace_cell_is_distinct_from_parens_and_grouping_brackets(self):
        self.assertNotEqual(BRACE_OPEN_CELL, PAREN_OPEN_CELL)
        self.assertNotEqual(BRACE_OPEN_CELL, GROUPING_BRACKET_OPEN)

    def test_bracket_cells_are_two_cells_distinguished_by_the_second(self):
        # 대괄호 여는 점형의 첫 칸은 묶음괄호 여는({1,2,3,5,6})과 우연히
        # 같다(규정 원문에서 확인된 값) -- 두 번째 칸({3})으로만 구별된다.
        self.assertEqual(BRACKET_OPEN_CELLS[0], GROUPING_BRACKET_OPEN)
        self.assertNotEqual(BRACKET_OPEN_CELLS[1], GROUPING_BRACKET_OPEN)
        self.assertEqual(len(BRACKET_OPEN_CELLS), 2)


class TableBrailleTests(unittest.TestCase):
    def test_column_then_row_then_digit_value_order(self):
        cell_item = {
            "row_index": 2, "column_index": 3,
            "content_nodes": [{"kind": "TEXT", "text": "5"}],
        }
        cells = table_cell_braille(cell_item)
        # column(3) digits, then row(2) digits, then value(5) digits -- each
        # prefixed by its own digit indicator per translate_digit().
        self.assertEqual(cells, [
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["3"],
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["2"],
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["5"],
        ])

    def test_hangul_cell_value_is_translated(self):
        # "가"는 제13항 약자 -- 단독으로 쓰이면(뒤에 모음-초성 음절이 없으면)
        # 항상 약자로 적힌다.
        cell_item = {"row_index": 1, "column_index": 1, "content_nodes": [{"kind": "TEXT", "text": "가"}]}
        cells = table_cell_braille(cell_item)
        self.assertEqual(cells, [
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["1"],
            DIGIT_INDICATOR_CELL, DIGIT_CELLS["1"],
            cell(1, 2, 4, 6),
        ])


class BraillePresenterTests(unittest.TestCase):
    def setUp(self):
        self.presenter = BraillePresenter(viewport_size=10)

    def test_text_focus_clears_display(self):
        frame = self.presenter.present_focus({"id": "t1", "kind": "TEXT"})
        self.assertEqual(frame["cells"], [])

    def test_invalid_math_focus_clears_display(self):
        item = {"id": "m1", "kind": "MATH", "ast_status": "INVALID", "presentation_ast": None}
        frame = self.presenter.present_focus(item)
        self.assertEqual(frame["cells"], [])

    def test_valid_math_focus_shows_first_window(self):
        item = {"id": "m1", "kind": "MATH", "ast_status": "VALID", "presentation_ast": {"type": "Number", "value": "5"}}
        frame = self.presenter.present_focus(item)
        self.assertEqual(frame["offset"], 0)
        self.assertGreater(len(frame["cells"]), 0)

    def test_viewport_size_property_returns_constructor_value(self):
        self.assertEqual(self.presenter.viewport_size, 10)

    def test_text_item_with_inline_math_spans_renders_the_selected_span(self):
        # 좌우 연장 (Decision 2): a TEXT item's inline MATH spans are each
        # individually renderable via `span_index`.
        span0 = {"kind": "MATH", "presentation_ast": {"type": "Number", "value": "1"}, "ast_status": "VALID"}
        span1 = {"kind": "MATH", "presentation_ast": {"type": "Number", "value": "22"}, "ast_status": "VALID"}
        item = {"id": "t1", "kind": "TEXT", "spans": [{"kind": "TEXT", "text": "값"}, span0, span1]}
        frame0 = self.presenter.present_focus(item, span_index=0)
        frame1 = self.presenter.present_focus(item, span_index=1)
        self.assertEqual(frame0["cells"], [cell_to_int(c) for c in math_focus_item_to_braille(span0)])
        self.assertEqual(frame1["cells"], [cell_to_int(c) for c in math_focus_item_to_braille(span1)])
        self.assertNotEqual(frame0["cells"], frame1["cells"])

    def test_span_index_out_of_range_clears_display(self):
        item = {
            "id": "t1", "kind": "TEXT",
            "spans": [{"kind": "MATH", "presentation_ast": {"type": "Number", "value": "1"}, "ast_status": "VALID"}],
        }
        frame = self.presenter.present_focus(item, span_index=5)
        self.assertEqual(frame["cells"], [])

    def test_invalid_span_at_requested_index_clears_display(self):
        item = {
            "id": "t1", "kind": "TEXT",
            "spans": [{"kind": "MATH", "presentation_ast": None, "ast_status": "INVALID"}],
        }
        frame = self.presenter.present_focus(item, span_index=0)
        self.assertEqual(frame["cells"], [])


class LastWindowOffsetTests(unittest.TestCase):
    def test_total_at_or_under_viewport_size_starts_at_zero(self):
        self.assertEqual(last_window_offset(0, 3), 0)
        self.assertEqual(last_window_offset(3, 3), 0)

    def test_total_exactly_on_a_window_boundary(self):
        # 6 cells at viewport_size=3 -> windows [0:3], [3:6]; last window starts at 3.
        self.assertEqual(last_window_offset(6, 3), 3)

    def test_total_one_past_a_window_boundary(self):
        # 7 cells at viewport_size=3 -> windows [0:3], [3:6], [6:7]; last window starts at 6.
        self.assertEqual(last_window_offset(7, 3), 6)


if __name__ == "__main__":
    unittest.main()
