"""presentation_ast -> Korean utterance string (plan document §8.4).

Pure functions, no TTS engine dependency. Korean particle agreement (은/는,
이/가, 와/과 selection based on whether the preceding syllable ends in a
consonant) is intentionally simplified to fixed forms here -- getting that
exactly right requires phonological analysis of arbitrary generated content
and is exactly the kind of wording the plan document defers to real user
testing (§18.6), not something to over-engineer before that feedback exists.
"""

from __future__ import annotations

from typing import Any

FUNCTION_NAME_SPEECH = {
    "sin": "사인", "cos": "코사인", "tan": "탄젠트",
    "cot": "코탄젠트", "sec": "시컨트", "csc": "코시컨트",
    "log": "로그", "ln": "자연로그", "lim": "리미트", "exp": "지수함수",
}

OPERATOR_SPEECH = {
    "+": "더하기", "-": "빼기", "*": "곱하기", "/": "나누기",
    "\\times": "곱하기", "\\div": "나누기", "\\cdot": "곱하기",
}

# Full sentence templates, not bare words -- Korean inequality/equality
# phrasing needs the right operand slotted between particles ("A는 B보다
# 작다"), not just a word appended after both operands.
RELATION_TEMPLATES = {
    "=": "{left}는 {right}와 같다",
    "<": "{left}는 {right}보다 작다",
    ">": "{left}는 {right}보다 크다",
    "\\leq": "{left}는 {right}보다 작거나 같다",
    "\\geq": "{left}는 {right}보다 크거나 같다",
    "\\neq": "{left}는 {right}와 같지 않다",
}


def math_focus_item_to_speech(item: dict[str, Any]) -> str:
    """Entry point for a MATH-kind focus item or inline MATH span fragment.
    Honors `ast_status` per §13.1: an INVALID formula's tree is never walked
    (only the fallback notice is spoken), since a broken AST cannot be
    trusted to read out correctly even partially.
    """
    ast_status = item.get("ast_status")
    if ast_status == "INVALID":
        return "수식 인식이 불확실합니다."
    body = math_ast_to_speech(item.get("presentation_ast"))
    if ast_status == "PARTIAL":
        return f"일부 기호 인식이 불확실합니다. {body}"
    return body


def math_ast_to_speech(node: object) -> str:
    if not isinstance(node, dict):
        return ""
    node_type = node.get("type")

    if node_type in ("Identifier", "Number"):
        return str(node.get("value", ""))
    if node_type == "Operator":
        value = str(node.get("value", ""))
        return OPERATOR_SPEECH.get(value, value)
    if node_type == "Row":
        return " ".join(part for part in (math_ast_to_speech(c) for c in node.get("children", [])) if part)
    if node_type == "Relation":
        return _relation_to_speech(node)
    if node_type == "FunctionApplication":
        name = str(node.get("name", ""))
        name_speech = FUNCTION_NAME_SPEECH.get(name, name)
        argument = math_ast_to_speech(node.get("argument"))
        return f"{name_speech} {argument}".strip()
    if node_type == "Fraction":
        numerator = math_ast_to_speech(node.get("numerator"))
        denominator = math_ast_to_speech(node.get("denominator"))
        return f"분수 시작, {numerator}, 분모, {denominator}, 분수 끝"
    if node_type == "Power":
        base = math_ast_to_speech(node.get("base"))
        exponent = math_ast_to_speech(node.get("exponent"))
        return f"{base}의 {exponent} 제곱"
    if node_type == "Subscript":
        base = math_ast_to_speech(node.get("base"))
        subscript = math_ast_to_speech(node.get("subscript"))
        return f"{base} 아래첨자 {subscript}"
    if node_type == "Subsuperscript":
        base = math_ast_to_speech(node.get("base"))
        subscript = math_ast_to_speech(node.get("subscript"))
        exponent = math_ast_to_speech(node.get("exponent"))
        return f"{base} 아래첨자 {subscript} 위첨자 {exponent}"
    if node_type == "Radical":
        radicand = math_ast_to_speech(node.get("radicand"))
        index = node.get("index")
        if index is not None:
            return f"{math_ast_to_speech(index)} 제곱근 {radicand}"
        return f"루트 {radicand}"
    if node_type == "Parenthesized":
        body = math_ast_to_speech(node.get("body"))
        return f"괄호 열고 {body} 괄호 닫고"
    if node_type == "UnaryMinus":
        return f"음수 {math_ast_to_speech(node.get('body'))}"
    if node_type == "AlignedRows":
        rows = [row for row in (math_ast_to_speech(c) for c in node.get("children", [])) if row]
        return ", ".join(f"{index}번째 식, {row}" for index, row in enumerate(rows, start=1))
    if node_type == "List":
        # 콤마로 나열된 항목(집합 표기, 구간, 독립된 식 목록) -- 실제
        # 줄바꿈이 아니므로 AlignedRows의 "N번째 식" 접두사는 붙이지 않는다.
        items = [item for item in (math_ast_to_speech(c) for c in node.get("children", [])) if item]
        return ", ".join(items)
    if node_type == "Unknown":
        return "인식할 수 없는 기호"
    return ""


def _relation_to_speech(node: dict[str, Any]) -> str:
    left = math_ast_to_speech(node.get("left"))
    right = math_ast_to_speech(node.get("right"))
    operator = str(node.get("operator", "="))
    template = RELATION_TEMPLATES.get(operator)
    if template is not None:
        return template.format(left=left, right=right)
    return f"{left} {operator} {right}".strip()
