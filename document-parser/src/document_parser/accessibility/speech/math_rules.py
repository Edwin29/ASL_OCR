"""presentation_ast -> Korean utterance string (plan document §8.4).

Pure functions, no TTS engine dependency. Korean surface wording is delegated
to the replaceable naturalization boundary instead of being embedded in AST
rendering rules.
"""

from __future__ import annotations

from typing import Any

from document_parser.math.latex_ast import aligned_row_cells

from document_parser.accessibility.naturalization import (
    DEFAULT_KOREAN_MATH_NATURALIZER,
    MathSpeechNaturalizer,
)

FUNCTION_NAME_SPEECH = {
    "sin": "사인", "cos": "코사인", "tan": "탄젠트",
    "cot": "코탄젠트", "sec": "시컨트", "csc": "코시컨트",
    "log": "로그", "ln": "자연로그", "lim": "리미트", "exp": "지수함수",
}

OPERATOR_SPEECH = {
    "+": "더하기", "-": "빼기", "*": "곱하기", "/": "나누기",
    "\\times": "곱하기", "\\div": "나누기", "\\cdot": "곱하기",
}

# A lone "+"/"-" with no operand (부호표 sign-table cells, e.g. f'(x)의 부호)
# reads as the sign itself, not as an operation -- "더하기"/"빼기" ("add"/
# "subtract") only makes sense between two operands. Only used for the
# top-level Operator case in `math_focus_item_to_speech` below, never for an
# Operator embedded inside a Row (that's still a real binary connective).
STANDALONE_SIGN_SPEECH = {"+": "플러스", "-": "마이너스"}

_ROW_ORDINAL_SPEECH = {
    1: "첫 번째",
    2: "두 번째",
    3: "세 번째",
    4: "네 번째",
    5: "다섯 번째",
    6: "여섯 번째",
    7: "일곱 번째",
    8: "여덟 번째",
    9: "아홉 번째",
    10: "열 번째",
}

def math_focus_item_to_speech(
    item: dict[str, Any],
    naturalizer: MathSpeechNaturalizer = DEFAULT_KOREAN_MATH_NATURALIZER,
) -> str:
    """Entry point for a MATH-kind focus item or inline MATH span fragment.
    Honors `ast_status` per §13.1: an INVALID formula's tree is never walked
    (only the fallback notice is spoken), since a broken AST cannot be
    trusted to read out correctly even partially.
    """
    ast_status = item.get("ast_status")
    if ast_status == "INVALID":
        return "수식 인식이 불확실합니다."
    ast = item.get("presentation_ast")
    if isinstance(ast, dict) and ast.get("type") == "Operator":
        # A *top-level* Operator node (the whole formula, not a Row child)
        # can only come from latex_ast.py's dedicated lone-sign special case
        # -- every other grammar path embeds Operator inside a Row instead.
        # Read it as a standalone sign, not a binary connective.
        value = str(ast.get("value", ""))
        body = STANDALONE_SIGN_SPEECH.get(value, value)
    else:
        body = math_ast_to_speech(ast, naturalizer)
    if ast_status == "PARTIAL":
        return f"일부 기호 인식이 불확실합니다. {body}"
    return body


def math_ast_to_speech(
    node: object,
    naturalizer: MathSpeechNaturalizer = DEFAULT_KOREAN_MATH_NATURALIZER,
) -> str:
    if not isinstance(node, dict):
        return ""
    node_type = node.get("type")

    if node_type in ("Identifier", "Number"):
        return str(node.get("value", ""))
    if node_type == "Operator":
        value = str(node.get("value", ""))
        return OPERATOR_SPEECH.get(value, value)
    if node_type == "Row":
        return " ".join(
            part for part in (math_ast_to_speech(c, naturalizer) for c in node.get("children", [])) if part
        )
    if node_type == "Relation":
        return _relation_to_speech(node, naturalizer)
    if node_type == "FunctionApplication":
        name = str(node.get("name", ""))
        name_speech = FUNCTION_NAME_SPEECH.get(name, name)
        argument = math_ast_to_speech(node.get("argument"), naturalizer)
        return f"{name_speech} {argument}".strip()
    if node_type == "Fraction":
        numerator = math_ast_to_speech(node.get("numerator"), naturalizer)
        denominator = math_ast_to_speech(node.get("denominator"), naturalizer)
        return naturalizer.fraction(numerator, denominator)
    if node_type == "Power":
        base = math_ast_to_speech(node.get("base"), naturalizer)
        exponent = math_ast_to_speech(node.get("exponent"), naturalizer)
        return f"{base}의 {exponent} 제곱"
    if node_type == "Subscript":
        base = math_ast_to_speech(node.get("base"), naturalizer)
        subscript = math_ast_to_speech(node.get("subscript"), naturalizer)
        return f"{base} 아래첨자 {subscript}"
    if node_type == "Subsuperscript":
        base = math_ast_to_speech(node.get("base"), naturalizer)
        subscript = math_ast_to_speech(node.get("subscript"), naturalizer)
        exponent = math_ast_to_speech(node.get("exponent"), naturalizer)
        return f"{base} 아래첨자 {subscript} 위첨자 {exponent}"
    if node_type == "Radical":
        radicand = math_ast_to_speech(node.get("radicand"), naturalizer)
        index = node.get("index")
        if index is not None:
            return f"{math_ast_to_speech(index, naturalizer)} 제곱근 {radicand}"
        return f"루트 {radicand}"
    if node_type == "Parenthesized":
        body = math_ast_to_speech(node.get("body"), naturalizer)
        if node.get("delimiter") == "|":
            return f"{body}의 절댓값"
        return f"괄호 열고 {body} 괄호 닫고"
    if node_type == "UnaryMinus":
        return f"음수 {math_ast_to_speech(node.get('body'), naturalizer)}"
    if node_type == "AlignedRows":
        rows = []
        for cells in aligned_row_cells(node):
            spoken_cells = [
                speech
                for speech in (math_ast_to_speech(cell, naturalizer) for cell in cells)
                if speech
            ]
            if spoken_cells:
                rows.append(", ".join(spoken_cells))
        return ", ".join(
            f"{_ROW_ORDINAL_SPEECH.get(index, f'{index}번째')} 식, {row}"
            for index, row in enumerate(rows, start=1)
        )
    if node_type == "List":
        # 콤마로 나열된 항목(집합 표기, 구간, 독립된 식 목록) -- 실제
        # 줄바꿈이 아니므로 AlignedRows의 "N번째 식" 접두사는 붙이지 않는다.
        items = [item for item in (math_ast_to_speech(c, naturalizer) for c in node.get("children", [])) if item]
        return ", ".join(items)
    if node_type == "Unknown":
        return "인식할 수 없는 기호"
    return ""


def _relation_to_speech(node: dict[str, Any], naturalizer: MathSpeechNaturalizer) -> str:
    left = math_ast_to_speech(node.get("left"), naturalizer)
    right = math_ast_to_speech(node.get("right"), naturalizer)
    operator = str(node.get("operator", "="))
    subject = naturalizer.attach_particle(left, "topic")
    if operator == "=":
        return f"{subject} {naturalizer.attach_particle(right, 'comitative')} 같다"
    if operator == "<":
        return f"{subject} {right}보다 작다"
    if operator == ">":
        return f"{subject} {right}보다 크다"
    if operator in ("\\leq", "≤"):
        return f"{subject} {right}보다 작거나 같다"
    if operator in ("\\geq", "≥"):
        return f"{subject} {right}보다 크거나 같다"
    if operator in ("\\neq", "≠"):
        return f"{subject} {naturalizer.attach_particle(right, 'comitative')} 같지 않다"
    return f"{left} {operator} {right}".strip()
