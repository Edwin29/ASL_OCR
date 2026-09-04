"""presentation_ast -> logical braille cell buffer (plan document §9.2).

The `ast_status` gate is a fully-specified, already-decided policy (§23 #9:
PARTIAL formulas withhold braille entirely, same as INVALID -- unlike TTS,
braille never shows a partially-trusted result). Actual symbol shapes
(fractions, exponents, subscripts, radicals, most operators/identifiers) are
delegated to `cell_encoding.CharacterBrailleTranslator`, which raises
`NotImplementedError` for anything not yet verified against the 2024
규정 document -- that is intended behavior, not a bug to work around.
"""

from __future__ import annotations

from typing import Any

from document_parser.math.latex_ast import aligned_row_cells

from document_parser.accessibility.braille.cell_encoding import (
    ABSOLUTE_VALUE_CELL,
    BRACE_CLOSE_CELL,
    BRACE_OPEN_CELL,
    BRACKET_CLOSE_CELLS,
    BRACKET_OPEN_CELLS,
    BrailleCell,
    CharacterBrailleTranslator,
    COMMA_CELL,
    FRACTION_BAR_CELL,
    FUNCTION_NAME_CELLS,
    GROUPING_BRACKET_CLOSE,
    GROUPING_BRACKET_OPEN,
    PAREN_CLOSE_CELL,
    PAREN_OPEN_CELL,
    RADICAL_CELL,
    RADICAL_NTH_CELL,
    RegulationBrailleTranslator,
    SLASH_FRACTION_CELLS,
    SUBSCRIPT_INDICATOR_CELL,
    SUPERSCRIPT_INDICATOR_CELL,
)

_DEFAULT_TRANSLATOR = RegulationBrailleTranslator()


def math_focus_item_to_braille(
    item: dict[str, Any], translator: CharacterBrailleTranslator = _DEFAULT_TRANSLATOR
) -> list[BrailleCell]:
    """`item` is a MATH-kind focus item or inline MATH span fragment (both
    carry `ast_status` and `presentation_ast`, per the Phase 1 flattener)."""
    if item.get("ast_status") != "VALID":
        return []
    return _node_to_braille(item.get("presentation_ast"), translator)


def braille_scrollable_spans(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Ordered list of braille-scrollable math fragments for a focus item
    (좌우 연장, Decision 2): a MATH-kind item is its own single entry; a
    TEXT-kind item's entries are its `spans` filtered to `kind == "MATH"`,
    excluding fragments that the inline naturalization policy marks as not
    standalone-accessible, in original reading order; anything else (TABLE,
    UNSUPPORTED_VISUAL, plain TEXT with no math, ...) has none."""
    if item.get("kind") == "MATH":
        return [item]
    if item.get("kind") == "TEXT":
        spans = item.get("spans") if isinstance(item.get("spans"), list) else []
        return [
            span for span in spans
            if (
                isinstance(span, dict)
                and span.get("kind") == "MATH"
                and span.get("standalone_accessibility") is not False
            )
        ]
    return []


def _node_to_braille(node: object, translator: CharacterBrailleTranslator) -> list[BrailleCell]:
    if not isinstance(node, dict):
        return []
    node_type = node.get("type")

    if node_type == "Number":
        return translator.translate_digit(str(node.get("value", "")))

    if node_type == "Operator":
        return translator.translate_math_symbol(str(node.get("value", "")))

    if node_type == "Row":
        cells: list[BrailleCell] = []
        for child in node.get("children", []):
            cells.extend(_node_to_braille(child, translator))
        return cells

    if node_type == "List":
        # 제1항 [붙임](쉼표): 항목을 COMMA_CELL로 구분해 이어붙인다 -- 실제
        # 줄바꿈이 아니므로 AlignedRows의 번호 태그는 붙이지 않는다.
        cells = []
        for index, child in enumerate(node.get("children", [])):
            if index > 0:
                cells.append(COMMA_CELL)
            cells.extend(_node_to_braille(child, translator))
        return cells

    if node_type == "Relation":
        cells = _node_to_braille(node.get("left"), translator)
        cells.extend(translator.translate_math_symbol(str(node.get("operator", "="))))
        cells.extend(_node_to_braille(node.get("right"), translator))
        return cells

    if node_type == "Fraction":
        if node.get("notation") == "slash":
            # 제7항 2.(빗금 분수): 분자, 빗금(2칸), 분모 순서 -- 스택형과
            # 반대로 시각적 좌우 순서("2/3"의 2가 먼저)를 그대로 따른다.
            cells = _wrapped_operand_cells(node.get("numerator"), translator)
            cells.extend(SLASH_FRACTION_CELLS)
            cells.extend(_wrapped_operand_cells(node.get("denominator"), translator))
            return cells
        # 제7항: 분모, 분수표, 분자의 순서로 적는다.
        cells = _wrapped_operand_cells(node.get("denominator"), translator)
        cells.append(FRACTION_BAR_CELL)
        cells.extend(_wrapped_operand_cells(node.get("numerator"), translator))
        return cells

    if node_type == "Radical":
        # 제22항: 근호는 RADICAL_CELL 하나로 적고 그 뒤에 근호 안의 내용을
        # 적는다. index가 있으면(세제곱근 이상, [붙임1]) 근수를 먼저 적고
        # RADICAL_NTH_CELL(일반 근호와 다른 별도 점형)을 적는다.
        cells: list[BrailleCell] = []
        if node.get("index") is not None:
            cells.extend(_wrapped_operand_cells(node.get("index"), translator))
            cells.append(RADICAL_NTH_CELL)
        else:
            cells.append(RADICAL_CELL)
        cells.extend(_wrapped_operand_cells(node.get("radicand"), translator))
        return cells

    if node_type == "Power":
        # 제18항: 지수는 위첨자 기호를 적고 첨자 내용을 적는다. Base는 그
        # 자체의 규칙(Number 등)으로 먼저 적는다 -- base가 아직 미검증인
        # 노드 타입(예: Identifier)이면 재귀 호출에서 그대로 실패한다.
        cells = _node_to_braille(node.get("base"), translator)
        cells.append(SUPERSCRIPT_INDICATOR_CELL)
        cells.extend(_wrapped_operand_cells(node.get("exponent"), translator))
        return cells

    if node_type == "Subscript":
        # 제19항: 아래첨자는 아래첨자 기호를 적고 첨자 내용을 적는다.
        cells = _node_to_braille(node.get("base"), translator)
        cells.append(SUBSCRIPT_INDICATOR_CELL)
        cells.extend(_wrapped_operand_cells(node.get("subscript"), translator))
        return cells

    if node_type == "Identifier":
        # 로마자(제12항)와 그리스 문자(제13항) 모두 translate_math_symbol이
        # 처리한다 -- 둘 다 "수식에서 쓰이는 문자 기호"라는 점에서 Operator와
        # 같은 경로를 타는 게 자연스럽고, CharacterBrailleTranslator 프로토콜에
        # 새 메서드를 추가할 필요가 없다.
        return translator.translate_math_symbol(str(node.get("value", "")))

    if node_type == "Parenthesized":
        # 제6항 1.(괄호)/제21항(절댓값). 이 노드는 소스에 실제로 쓰인 괄호를
        # 나타내므로, 분수/근호/첨자용 묶음괄호(GROUPING_BRACKET_*)와는 다른
        # 별개의 점형을 쓴다 -- 내용물을 조건부로 감싸지 않고 항상 감싼다.
        body_cells = _node_to_braille(node.get("body"), translator)
        delimiter = node.get("delimiter", "(")
        if delimiter == "(":
            return [PAREN_OPEN_CELL, *body_cells, PAREN_CLOSE_CELL]
        if delimiter == "|":
            return [ABSOLUTE_VALUE_CELL, *body_cells, ABSOLUTE_VALUE_CELL]
        if delimiter == "{":
            return [BRACE_OPEN_CELL, *body_cells, BRACE_CLOSE_CELL]
        if delimiter == "[":
            return [*BRACKET_OPEN_CELLS, *body_cells, *BRACKET_CLOSE_CELLS]
        raise NotImplementedError(
            f"Parenthesized delimiter {delimiter!r} has no verified braille rule yet."
        )

    if node_type == "UnaryMinus":
        # 별도 조항 없음 -- "-5 < x < -2" 예시(제4항, p.52)에서 이항 뺄셈과
        # 단항 음수 부호가 점자에서 구별되지 않음을 직접 확인했다. 뺄셈표를
        # 그대로 재사용한다 (별도 "음수 부호" 점형을 만들면 규정과 불일치).
        minus_cells = translator.translate_math_symbol("-")
        return [*minus_cells, *_wrapped_operand_cells(node.get("body"), translator)]

    if node_type == "FunctionApplication":
        # 제46항(로그)/제47항(삼각함수): 함수명 지시 셀 + 인수. 인수가
        # 곱/다항식(compound Row)이면 제47항 [붙임]에 따라 묶음괄호로 감싼다
        # -- 분수/근호/첨자와 같은 패턴. 밑이 있는 로그(log_5, log_a)는
        # 현재 파서가 그 구조를 별도 AST 모양으로 만들지 않아 지원하지 않는다.
        name = str(node.get("name", ""))
        indicator = FUNCTION_NAME_CELLS.get(name)
        if indicator is None:
            # sin/log 같은 지정된 함수명이 아니라, 문제에서 임의로 정의한
            # 단일 로마자 함수 기호(예: "함수 f(x)="의 f, g, h)인 경우 --
            # `latex_ast.py`가 "단일 문자 뒤 괄호"를 전부 FunctionApplication
            # 으로 만들기 때문에 실전 데이터에 아주 흔하다(ln/exp보다도 흔함,
            # p030 실제 fixture에서 확인). 제12항(수식 내 로마자는 로마자표
            # 없이 그대로 적는다)을 그대로 적용해 ln/exp와 동일한 논리로
            # 한 글자를 그대로 적는다 -- 새 기호를 만드는 게 아니라 이미
            # 검증된 ROMAN_LOWER_CELLS 재사용.
            if len(name) == 1 and name.isascii() and name.isalpha():
                indicator = translator.translate_math_symbol(name)
            else:
                raise NotImplementedError(
                    f"Function name {name!r} has no verified braille rule yet. "
                    "sin/cos/tan/csc/sec/cot (제47항), 로그(log, 제46항, 밑 없는 "
                    "형태만), ln/exp/lim(전용 기호 없이 로마자 그대로, 첨자 없는 "
                    "단순 lim(식) 형태만), 단일 로마자 함수 기호(f/g/h 등, 제12항 "
                    "재사용)는 verified. 두 글자 이상의 미지정 함수명은 아직 미확인."
                )
        return [*indicator, *_wrapped_operand_cells(node.get("argument"), translator)]

    if node_type == "AlignedRows":
        # 물리 디스플레이는 한 줄이므로 각 *논리 행* 앞에 번호 태그를 붙여
        # 이어붙인다. 2D AST의 같은 행 안에 있는 정렬 셀은 COMMA_CELL로
        # 구분하며, `&` 셀마다 새 행 번호를 만들지 않는다. 번호 태그는
        # 규정에서 확인된 점형이 아니라 기존 프로젝트 표기 관례이므로
        # 묶음괄호로 감싸 본문 숫자와 구분한다. `aligned_row_cells`는 이미
        # 발행된 flat `children` AST도 종전 의미로 읽게 해 준다.
        cells: list[BrailleCell] = []
        for index, row_cells in enumerate(aligned_row_cells(node), start=1):
            cells.append(GROUPING_BRACKET_OPEN)
            cells.extend(translator.translate_digit(str(index)))
            cells.append(GROUPING_BRACKET_CLOSE)
            for cell_index, child in enumerate(row_cells):
                if cell_index > 0:
                    cells.append(COMMA_CELL)
                cells.extend(_node_to_braille(child, translator))
        return cells

    # Subsuperscript: 아래첨자와 위첨자를 동시에 적는 순서를 규정에서 아직
    # 명시적으로 확인하지 못했다 (제18항/제19항은 각각 단독 규칙만 확인됨)
    # -- 순서를 추측하지 않고 미구현으로 남긴다.
    raise NotImplementedError(
        f"AST node type {node_type!r} has no verified braille rule yet."
    )


def _is_compound_operand(node: object) -> bool:
    """수학 점자 규정 제7항 3./제22항 [붙임2]: 분모·분자·근호 안이 "곱 또는
    다항식"일 경우에만 묶음 괄호로 묶는다. 파서가 곱/다항식을 여러 항의
    `Row`로 표현하므로, 자식이 둘 이상인 `Row`를 "compound"로 취급한다 --
    단일 Number/Identifier/Fraction/Radical/Power 등은 그 자체로 이미 한
    덩어리이므로 감싸지 않는다 (p.54 "x+1/y" 예시: 분모 y는 단일 Identifier라
    괄호 없이 적힘; p.54 "1/(x+y)" 예시: 분모가 여러 항의 Row라 묶음괄호로
    감쌈)."""
    return isinstance(node, dict) and node.get("type") == "Row" and len(node.get("children", [])) != 1


def _wrapped_operand_cells(node: object, translator: CharacterBrailleTranslator) -> list[BrailleCell]:
    cells = _node_to_braille(node, translator)
    if _is_compound_operand(node):
        return [GROUPING_BRACKET_OPEN, *cells, GROUPING_BRACKET_CLOSE]
    return cells
