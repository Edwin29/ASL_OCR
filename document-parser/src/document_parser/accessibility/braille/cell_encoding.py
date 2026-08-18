"""6-dot braille cell encoding.

Most patterns in this file were read directly off the rendered dot diagrams
in the official regulation document the user supplied: 문화체육관광부고시
제2024-0005호 [개정] 한국 점자 규정 (2024, "개정 한국 점자 규정(2024).zip").
Dot numbering follows the document's own definition (한국 점자 표기의 기본
원칙 제2항): left column top-to-bottom is dots 1/2/3, right column
top-to-bottom is dots 4/5/6.

A second batch of patterns (로마자 전체, 그리스 문자, 괄호, 절댓값,
근삽값(≒), n제곱근 근호) came from a delegated extraction pass done by
other agents against the same source PDF, using an explicit "dot-number-set
per cell" format specifically to avoid the ambiguity of shorthand notation.
Before trusting that batch, several of its claims that overlapped with
already-verified values here were spot-checked directly against this
session's own PDF renders (소괄호, the c/x/y-a-b Roman letters, the
n제곱근 근호 cell) and all matched -- see `project-braille-regulation-
extraction` memory for the full cross-check log. That cross-check is also
what caught a real bug in THIS file: `=` had been misread early in the
session as `{1,3,4,6}` and was corrected to the verified `{2,5}` after
re-reading two original worked examples ("ax=b", "32+24=56") directly.

A third batch (한글 자모: 모음자 21개, 초성/중성/종성 결합, 약자·약어) came
from a second delegated extraction pass and is implemented in
`hangul.py`, not this file -- every value there was cross-checked by
hand-deriving all 20 of that batch's real worked example words/phrases
through the decomposition algorithm and confirming an exact match; see
`project-braille-hangul-jamo` memory for the full log.

A fourth, smaller batch (`FUNCTION_NAME_CELLS["ln"/"exp"/"lim"]`) came from
an external research report the user pasted directly (not independently
re-read from the PDF this session). Its individual cell claims are not new
data, though: they are exactly this file's own already-verified
`ROMAN_LOWER_CELLS` letters (l, n, i, m, e, x, p) applied mechanically to
spell those three function names, per the report's own conclusion that none
of the three have a dedicated single-cell symbol. The report's specific
article-number claims (제46항 2., 제51항) were not independently verified.

Symbols not yet located and decoded in the source document raise
`NotImplementedError` with a pointer to where to find them, rather than a
plausible-looking wrong value. Getting this wrong would hand a blind student
incorrect information with no way to notice, which is worse than refusing.
"""

from __future__ import annotations

from typing import Protocol

BrailleCell = frozenset[int]


def cell(*dots: int) -> BrailleCell:
    """A braille cell as the set of raised dot numbers (1-6). No dots raised
    (a blank cell) is `cell()`."""
    return frozenset(dots)


# ---- 한글 점자 규정 제1절 제1항: 첫소리로 쓰인 자음자 (초성, 14개) ----
# "ㅇ"이 없는 것은 실수가 아니다 -- 제1항 [다만1]에 따라 첫소리 'ㅇ'은 점자로
# 표기하지 않는다 (받침 첫소리 'ㅇ'을 예외적으로 표기해야 할 때 쓰는 별도
# 기호는 아직 확인하지 못했다).
INITIAL_CONSONANT_CELLS: dict[str, BrailleCell] = {
    "ㄱ": cell(4),
    "ㄴ": cell(1, 4),
    "ㄷ": cell(2, 4),
    "ㄹ": cell(5),
    "ㅁ": cell(1, 5),
    "ㅂ": cell(4, 5),
    "ㅅ": cell(6),
    "ㅈ": cell(4, 6),
    "ㅊ": cell(5, 6),
    "ㅋ": cell(1, 2, 4),
    "ㅌ": cell(1, 2, 5),
    "ㅍ": cell(1, 4, 5),
    "ㅎ": cell(2, 4, 5),
}

# ---- 한글 점자 규정 제1절 제3항: 받침으로 쓰인 자음자 (종성, 14개) ----
FINAL_CONSONANT_CELLS: dict[str, BrailleCell] = {
    "ㄱ": cell(1),
    "ㄴ": cell(2, 5),
    "ㄷ": cell(3, 5),
    "ㄹ": cell(2),
    "ㅁ": cell(2, 6),
    "ㅂ": cell(1, 2),
    "ㅅ": cell(3),
    "ㅇ": cell(2, 3, 5, 6),
    "ㅈ": cell(1, 3),
    "ㅊ": cell(2, 3),
    "ㅋ": cell(2, 3, 5),
    "ㅌ": cell(2, 3, 6),
    "ㅍ": cell(2, 5, 6),
    "ㅎ": cell(3, 5, 6),
}

# ---- 한글 점자 규정 제40항: 수표(digit indicator) + 숫자 0-9 ----
# 수학 점자 규정 제1항이 그대로 재사용한다고 명시.
DIGIT_INDICATOR_CELL: BrailleCell = cell(3, 4, 5, 6)
DIGIT_CELLS: dict[str, BrailleCell] = {
    "1": cell(1),
    "2": cell(1, 2),
    "3": cell(1, 4),
    "4": cell(1, 4, 5),
    "5": cell(1, 5),
    "6": cell(1, 2, 4),
    "7": cell(1, 2, 4, 5),
    "8": cell(1, 2, 5),
    "9": cell(2, 4),
    "0": cell(2, 4, 5),
}

# ---- 수학 점자 규정 제1항 [붙임]: 쉼표 ----
# "수의 세 자리마다 표기되어 있는 쉼표는 [X]으로 적는다" (printed p.51),
# "5,700,000" 예시로 확인 -- 국제 표준 점자 comma(⠂)와 동일. 이 조항은
# 숫자 세 자리 구분용 쉼표를 규정하지만, 점자에서 쉼표는 문맥에 상관없이
# 하나의 구두점 기호이므로 List 노드(집합/구간 표기, 콤마로 나열된 식
# 목록)의 항목 구분자로도 재사용한다 -- "="가 등호로서 이미 그랬듯, 이
# 재사용은 규정에서 직접 확인한 게 아니라 프로젝트 차원의 합리적 확장이다.
COMMA_CELL: BrailleCell = cell(2)

# ---- 수학 점자 규정 제2항(사칙연산 기호), 제3항(등호) ----
# 값은 tuple: 한 기호가 여러 칸으로 이루어진 경우(나눗셈표, 등호)를 그대로 표현.
MATH_OPERATOR_CELLS: dict[str, tuple[BrailleCell, ...]] = {
    "+": (cell(2, 6),),  # 덧셈표
    "-": (cell(3, 5),),  # 뺄셈표
    "*": (cell(1, 6),),  # 곱셈표(×)
    "/": (cell(1, 2, 4), cell(1, 5)),  # 나눗셈표(÷) -- 두 칸
    "=": (cell(2, 5), cell(2, 5)),  # 등호 -- 두 칸, 같은 점형 반복. 최초 판독은
    # {1,3,4,6}으로 잘못 기록되어 있었으나, "ax=b"와 "32+24=56" 두 예시를
    # 원문에서 재확인한 결과 {2,5};{2,5}가 맞다 (다른 경로로 받은 정리본의
    # "ω²-ω+1=0" 예시와도 일치).
    # 제20항 근삽값 기호(≒), printed p.62. AST 파서(\approx -> "≈")가 만드는
    # 문자는 원문 조항이 쓰는 "≒"와 유니코드가 다르지만 같은 "근사적으로
    # 같다" 개념이라 같은 점형을 재사용한다. "√3≒1.732" 예시로 확인.
    "≈": (cell(5), cell(2, 5), cell(2, 5)),
    # ---- 제4항 부등호, printed p.52 ----
    # 두 칸씩 같은 점형을 반복하는 일관된 패턴이 보인다: 사칙연산 기호를
    # 그대로 두 번 적거나(>는 덧셈표 {2,6} 반복, <는 뺄셈표 {3,5} 반복),
    # >/<와 =의 점을 합친다(≥={2,6}∪{2,5}, ≤={3,5}∪{2,5}). "a>b", "x<0",
    # "x≥5", "x≤0" 예시로 각각 재확인.
    ">": (cell(2, 6), cell(2, 6)),
    "<": (cell(3, 5), cell(3, 5)),
    "≥": (cell(2, 5, 6), cell(2, 5, 6)),
    "≤": (cell(2, 3, 5), cell(2, 3, 5)),
    # 같지않다(≠) = 부정 접두 {4,6} + 등호(=) 반복. "y≠0" 예시로 확인.
    "≠": (cell(4, 6), cell(2, 5), cell(2, 5)),
    # 제43항 합동(≡), printed p.68 (제4장 기하). "△ABC≡△DEF" 예시로 확인.
    # 규정은 이 점형을 "합동"이라는 의미로 설명하지만, 점자 표기 자체는
    # "≡" 글리프에 대응하므로 AST의 \equiv가 만드는 모든 "≡"에 재사용한다
    # (다른 의미의 "동치"/"필요충분조건" 기호는 별도 조항(제61항 등)이며
    # 이 코드베이스의 파서는 아직 그 기호들을 만들지 않는다).
    "≡": (cell(2, 3, 5, 6), cell(2, 3, 5, 6)),
}

# ---- 수학 점자 규정 제46항: 로그(log) ----
# "log = {4,5,6}" (printed p.69), 진수는 바로 이어 적는다 -- "log 2" 예시로
# 확인. 밑이 있는 경우(log_5, log_a)는 별도 구조가 필요하지만, 현재
# `latex_ast.py` 파서가 "밑 지정 로그"를 별도 AST 모양으로 만들지 않아
# (일반 FunctionApplication 뒤에 Subscript가 덧씌워지는 형태가 되거나 아예
# 파싱되지 않음) 지금은 밑 없는 단순 log만 지원한다.
LOG_CELL: BrailleCell = cell(4, 5, 6)

# ---- 수학 점자 규정 제47항: 삼각함수 ----
# 공통 첫 칸 {2,3,5} + 함수별 둘째 칸 (printed p.70 규정 표에서 직접 읽음).
FUNCTION_NAME_CELLS: dict[str, tuple[BrailleCell, ...]] = {
    "sin": (cell(2, 3, 5), cell(2, 3, 4)),
    "cos": (cell(2, 3, 5), cell(1, 4)),
    "tan": (cell(2, 3, 5), cell(2, 3, 4, 5)),
    "csc": (cell(2, 3, 5), cell(1, 2, 6)),
    "sec": (cell(2, 3, 5), cell(3, 6)),
    "cot": (cell(2, 3, 5), cell(1, 2, 5, 6)),
    "log": (LOG_CELL,),
    # ---- ln, lim, exp: 전용 기호 없이 로마자를 그대로 이어 적는다 ----
    # 위임 대상이 아니라 사용자가 전달한 외부 조사 보고서 근거("ln x=log_e x"
    # 예시가 제46항 2., 제12항 "수식 내 로마자는 로마자표 생략" 규칙 적용;
    # lim은 제51항 본문이 "l,i,m으로 적는다"고 명시; exp는 규정에 전용 표기가
    # 없어 사용자가 "알파벳 그대로 exp(수식)"로 적으라고 확정 지시함).
    # 다만 이 셀 값 자체는 새로 신뢰해야 할 데이터가 아니라, 이미 이 세션에서
    # √xy/c²/x₂/ax=b 예시로 직접 검증한 ROMAN_LOWER_CELLS의 l/n/i/m/e/x/p 값을
    # 그대로 가져온 것뿐이다(아래 각 튜플 옆 주석 참고). 보고서의 조항 번호
    # 자체는 PDF로 재확인하지 않았다.
    "ln": (cell(1, 2, 3), cell(1, 3, 4, 5)),  # l, n
    "exp": (cell(1, 5), cell(1, 3, 4, 6), cell(1, 2, 3, 4)),  # e, x, p
    # lim은 규정상 항상 극한 범위(예: \lim_{x\to b})를 동반하지만, 현재
    # latex_ast.py의 FUNCTION_NAMES 파싱 분기는 함수명 뒤 "_"(아래첨자)를
    # 별도로 처리하지 않아 그 구조를 아직 AST로 담아내지 못한다(로그의 밑과
    # 같은 종류의 파서 한계) -- 여기서는 첨자 없는 단순 "lim(식)" 형태만
    # 다루고, 실제로 흔한 극한-범위 형태는 파서 확장이 먼저 필요하다.
    "lim": (cell(1, 2, 3), cell(2, 4), cell(1, 3, 4)),  # l, i, m
}

# ---- 수학 점자 규정 제7항: 분수표(fraction bar) ----
# "분수는 분모, 분수표, 분자의 순서로 적고 분수표(-)는 [X]으로 적는다"
# (printed p.54). 3/4, 3-1/6(대분수) 예시로 재확인: 숫자 점형(DIGIT_CELLS)과
# 수표(DIGIT_INDICATOR_CELL)도 이 예시에서 독립적으로 다시 검증됨.
FRACTION_BAR_CELL: BrailleCell = cell(3, 4)

# ---- 수학 점자 규정 제7항 2.: 빗금 분수(slash-notation fraction) ----
# "2/3" 예시로 확인: {3,4,5,6};{1,2};{4,5,6};{3,4};{3,4,5,6};{1,4} = 분자(2),
# 빗금(2칸), 분모(3) -- 스택형 분수(분모,분수표,분자 순서)와 반대로, 분자가
# 먼저 오는 시각적 좌우 순서를 그대로 따른다는 점에 주의.
SLASH_FRACTION_CELLS: tuple[BrailleCell, ...] = (cell(4, 5, 6), cell(3, 4))

# ---- 수학 점자 규정 제6항 1.: 중괄호/대괄호/연립식 괄호 (real delimiters) ----
# printed p.53. 제6항 2.의 묶음괄호(GROUPING_BRACKET_*, 분수/근호/첨자 내부용
# 구조 기호)와는 별개로, 소스에 실제로 쓰인 괄호를 나타낸다.
BRACE_OPEN_CELL: BrailleCell = cell(2, 3, 5, 6)
BRACE_CLOSE_CELL: BrailleCell = cell(2, 3, 5, 6)
BRACKET_OPEN_CELLS: tuple[BrailleCell, ...] = (cell(1, 2, 3, 5, 6), cell(3))
BRACKET_CLOSE_CELLS: tuple[BrailleCell, ...] = (cell(6), cell(2, 3, 4, 5, 6))
# 연립식 괄호(원문 규정 값): math_translator.py의 AlignedRows 처리는
# 2026-08-17 설계 결정에 따라 이 괄호 대신 번호 태그 + 한 줄 이어붙이기
# 방식(TTS의 "N번째 식" 관례와 통일)을 쓰기로 해서 지금은 쓰이지 않는다 --
# 원문 값 자체는 다른 용도(예: 실제 다중 행 프레임을 나중에 지원하게 될
# 경우)를 위해 상수로만 남겨 둔다.
SYSTEM_BRACKET_OPEN_CELLS: tuple[BrailleCell, ...] = (cell(2, 3, 5, 6), cell(3))
SYSTEM_BRACKET_CLOSE_CELLS: tuple[BrailleCell, ...] = (cell(6), cell(2, 3, 5, 6))

# ---- 수학 점자 규정 제22항: 근호(radical, √) ----
# "근호(√‾)는 [X]으로 적는다" (printed p.63). 규정 본문 예시(√2)와
# [붙임2] 예시(√xy) 두 곳에서 독립적으로 동일하게 재확인.
RADICAL_CELL: BrailleCell = cell(3, 4, 5)

# ---- 수학 점자 규정 제22항 [붙임1]: 세제곱근 이상(n제곱근) 근호 ----
# "세제곱근 이상은 제곱근 기호로 적고 근수를 그 앞에 적는다"는 조문과 달리
# 실제로는 일반 RADICAL_CELL과 다른 별도 점형을 쓴다 -- 이 세션에서 처음
# ⁵√32 예시를 읽었을 때 나온 {1,2,4,5,6}을 "예시가 조문과 안 맞는다"며
# 미확정으로 보류했었으나, ³√x³/⁵√32/ᵐ√n 세 예시를 다시 대조한 결과 오독이
# 아니라 실제로 쓰이는 별도 근호 기호로 확인되었다. 순서: 근수(수/문자,
# 필요시 묶음괄호) + 이 기호 + 근호 안 내용.
RADICAL_NTH_CELL: BrailleCell = cell(1, 2, 4, 5, 6)

# ---- 수학 점자 규정 제18항: 위첨자(exponent/superscript) 지시 기호 ----
# "지수는 위첨자 기호 [X]을 적고..." (printed p.61). 규정 본문 예시(c^2)에서
# 독립적으로 재확인 -- 이 예시에서 로마자 c(={1,4})도 국제 표준 점자와 일치함을
# 추가로 확인(x, y에 이은 3번째 사례).
SUPERSCRIPT_INDICATOR_CELL: BrailleCell = cell(4, 5)

# ---- 수학 점자 규정 제19항: 아래첨자(subscript) 지시 기호 ----
# "아래첨자는 아래첨자 기호 [X]을 적고..." (printed p.62). 규정 본문 예시(x_2)
# 에서 독립적으로 재확인.
SUBSCRIPT_INDICATOR_CELL: BrailleCell = cell(5, 6)

# ---- 수학 점자 규정 제6항 2.: 묶음 괄호 (grouping brackets) ----
# "단항의 곱, 다항 등을 묶어 표현해야 할 경우에 사용하는 기호로 점자에서만
# 사용" (printed p.53). 분수의 분모/분자가 곱 또는 다항식일 때(제7항 3.),
# 근호 안이 분수/곱/다항식일 때([붙임2])에 재사용된다 -- √xy 예시에서
# 근호+여는 묶음괄호+x+y+닫는 묶음괄호 순서로 재확인.
GROUPING_BRACKET_OPEN: BrailleCell = cell(1, 2, 3, 5, 6)
GROUPING_BRACKET_CLOSE: BrailleCell = cell(2, 3, 4, 5, 6)

# ---- 수학 점자 규정 제6항 1.: 괄호(real parentheses) ----
# printed p.53. AST의 `Parenthesized` 노드는 delimiter가 "(" (실제 괄호) 또는
# "|" (절댓값)인 경우만 만들어지므로, 여기서는 그 둘만 다룬다 -- 중괄호/
# 대괄호/연립식 괄호는 AST가 구분해서 만들지 않아 지금은 배선하지 않는다.
# "58-(17+14)" 예시로 재확인.
PAREN_OPEN_CELL: BrailleCell = cell(2, 3, 6)
PAREN_CLOSE_CELL: BrailleCell = cell(3, 5, 6)

# ---- 수학 점자 규정 제21항: 절댓값(| |) ----
# printed p.62-63. 여는/닫는 점형이 동일하다. "|x|", "|2x+7|-8" 예시로 확인.
ABSOLUTE_VALUE_CELL: BrailleCell = cell(1, 2, 5, 6)

# ---- 수학 점자 규정 제18항 2./제19항 2.: 왼쪽 위첨자/아래첨자용 대문자표 ----
# 전치행렬 "ᵗA" 예시(printed p.62)에서 로마자 대문자 A가
# CAPITAL_INDICATOR_CELL + ROMAN_LOWER_CELLS["a"] 순서로 확인됨.
CAPITAL_INDICATOR_CELL: BrailleCell = cell(6)

# ---- 수학 점자 규정 제12항: 로마자(Roman letters) a-z ----
# printed p.57-58. "수식에 사용하는 로마자는 로마자표를 적지 않는다"(제12항
# 1호)는 조문에 따라, 수식 안에서는 아래 점형을 로마자표 없이 그대로 쓴다.
# c={1,4}, x={1,3,4,6}, y={1,3,4,5,6}는 이 세션에서 √xy·c²·x₂ 세 예시로
# 이미 독립 확인했고, a={1}, b={1,2}는 "ax=b" 예시로 추가 재확인했다 --
# 국제 표준 점자 로마자와 전부 일치한다(단, 표 전체를 p.57에서 직접
# 재확인한 것은 아니고 위 다섯 글자만 원문과 대조했다).
ROMAN_LOWER_CELLS: dict[str, BrailleCell] = {
    "a": cell(1), "b": cell(1, 2), "c": cell(1, 4), "d": cell(1, 4, 5),
    "e": cell(1, 5), "f": cell(1, 2, 4), "g": cell(1, 2, 4, 5), "h": cell(1, 2, 5),
    "i": cell(2, 4), "j": cell(2, 4, 5), "k": cell(1, 3), "l": cell(1, 2, 3),
    "m": cell(1, 3, 4), "n": cell(1, 3, 4, 5), "o": cell(1, 3, 5), "p": cell(1, 2, 3, 4),
    "q": cell(1, 2, 3, 4, 5), "r": cell(1, 2, 3, 5), "s": cell(2, 3, 4), "t": cell(2, 3, 4, 5),
    "u": cell(1, 3, 6), "v": cell(1, 2, 3, 6), "w": cell(2, 4, 5, 6), "x": cell(1, 3, 4, 6),
    "y": cell(1, 3, 4, 5, 6), "z": cell(1, 3, 5, 6),
}

# ---- 수학 점자 규정 제13항: 그리스 문자 ----
# printed p.59-60. 소문자는 그리스 문자표 {4,6} + 해당 셀, 대문자는
# CAPITAL_INDICATOR_CELL + {4,6} + 해당 셀. "ω²-ω+1=0" 예시(printed p.60)로
# 소문자 ω와 등호(=)를 함께 재확인. `latex_ast.GREEK_AND_CONSTANTS`가 실제로
# 만들어낼 수 있는 문자만 담았다 -- "∞"(infty)는 그리스 문자가 아니라서
# 여기 없고 여전히 미구현이다.
GREEK_LETTER_CELLS: dict[str, tuple[BrailleCell, ...]] = {
    "α": (cell(4, 6), cell(1)),
    "β": (cell(4, 6), cell(1, 2)),
    "γ": (cell(4, 6), cell(1, 2, 4, 5)),
    "δ": (cell(4, 6), cell(1, 4, 5)),
    "Δ": (CAPITAL_INDICATOR_CELL, cell(4, 6), cell(1, 4, 5)),
    "θ": (cell(4, 6), cell(1, 4, 5, 6)),
    "λ": (cell(4, 6), cell(1, 2, 3)),
    "μ": (cell(4, 6), cell(1, 3, 4)),
    "π": (cell(4, 6), cell(1, 2, 3, 4)),
    "σ": (cell(4, 6), cell(2, 3, 4)),
    "Σ": (CAPITAL_INDICATOR_CELL, cell(4, 6), cell(2, 3, 4)),
    "φ": (cell(4, 6), cell(1, 2, 4)),
    "ω": (cell(4, 6), cell(2, 4, 5, 6)),
}


class CharacterBrailleTranslator(Protocol):
    def translate_digit(self, text: str) -> list[BrailleCell]: ...
    def translate_hangul_syllable(self, text: str) -> list[BrailleCell]: ...
    def translate_math_symbol(self, text: str) -> list[BrailleCell]: ...


class RegulationBrailleTranslator:
    """The only `CharacterBrailleTranslator` implementation. Methods raise
    `NotImplementedError` (not a guessed value) for anything not yet located
    and decoded in the source document -- see each method's message for
    exactly what is missing and where to look for it.
    """

    def translate_digit(self, text: str) -> list[BrailleCell]:
        try:
            return [DIGIT_INDICATOR_CELL, *(DIGIT_CELLS[ch] for ch in text)]
        except KeyError as exc:
            raise ValueError(f"Not a digit string: {text!r}") from exc

    def translate_hangul_syllable(self, text: str) -> list[BrailleCell]:
        from document_parser.accessibility.braille.hangul import translate_hangul_text
        return translate_hangul_text(text)

    def translate_math_symbol(self, text: str) -> list[BrailleCell]:
        if text in MATH_OPERATOR_CELLS:
            return list(MATH_OPERATOR_CELLS[text])
        if text in GREEK_LETTER_CELLS:
            return list(GREEK_LETTER_CELLS[text])
        if len(text) == 1 and text.isascii() and text.isalpha():
            lower_cell = ROMAN_LOWER_CELLS.get(text.lower())
            if lower_cell is not None:
                if text.isupper():
                    return [CAPITAL_INDICATOR_CELL, lower_cell]
                return [lower_cell]
        raise NotImplementedError(
            f"Math symbol {text!r} is not verified against the 2024 규정 yet. "
            "Verified so far: digit indicator + 0-9 (제1항), + - * / = ≈ "
            "> < ≥ ≤ ≠ ≡ (제2항, 제3항, 제4항, 제20항, 제43항), 로마자 a-z "
            "(제12항), 그리스 문자 α β γ δ Δ θ λ μ π σ Σ φ ω (제13항). "
            "분수/빗금분수/제곱근/n제곱근/위첨자/아래첨자/괄호(소·중·대)/"
            "절댓값/콤마 목록/함수명(sin 등, ln/lim/exp 포함)/UnaryMinus/"
            "AlignedRows는 verified but are structural AST node handlers in "
            "math_translator.py, not text symbols looked up here. Still "
            "missing: lim의 극한 범위 구조(\\lim_{x\\to b} 형태, 파서 한계로 "
            "AST 자체가 아직 못 만들어짐), 연립식 괄호(값은 있으나 "
            "AlignedRows가 번호 태그 방식을 쓰기로 해서 배선 안 함), "
            "Subsuperscript(동시 표기 순서 미확인)."
        )
