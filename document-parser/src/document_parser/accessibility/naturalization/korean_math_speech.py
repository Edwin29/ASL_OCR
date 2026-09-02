"""Rule-based Korean wording applied after math AST speech rendering.

The naturalizer owns language-specific surface choices only. It never changes
the math AST or decides whether the underlying recognition is valid.
"""

from __future__ import annotations

import re
from typing import Literal, Protocol

ParticleRole = Literal["topic", "subject", "object", "comitative"]

_PARTICLES: dict[ParticleRole, tuple[str, str]] = {
    # (after a final consonant, after a vowel)
    "topic": ("은", "는"),
    "subject": ("이", "가"),
    "object": ("을", "를"),
    "comitative": ("과", "와"),
}

_DIGIT_FINAL_CONSONANT = {
    "0": True,   # 영
    "1": True,   # 일
    "2": False,  # 이
    "3": True,   # 삼
    "4": False,  # 사
    "5": False,  # 오
    "6": True,   # 육
    "7": True,   # 칠
    "8": True,   # 팔
    "9": False,  # 구
}

# Korean names of Latin letters whose final spoken syllable has a jongseong.
# All unlisted Latin letters end in a vowel sound (에이, 비, 엑스, 와이, ...).
_LATIN_FINAL_CONSONANT = frozenset("LMNRlmnr")
_NUMBER_AT_END = re.compile(r"[+-]?(\d[\d,]*)(?:\.(\d+))?$")


class MathSpeechNaturalizer(Protocol):
    """Language surface policy consumed by the math speech renderer."""

    def attach_particle(self, phrase: str, role: ParticleRole) -> str: ...

    def fraction(self, numerator: str, denominator: str) -> str: ...


class KoreanMathSpeechNaturalizer:
    """Deterministic Korean particle agreement and fraction word order."""

    def attach_particle(self, phrase: str, role: ParticleRole) -> str:
        consonant_form, vowel_form = _PARTICLES[role]
        particle = consonant_form if _has_final_consonant(phrase) else vowel_form
        return f"{phrase}{particle}"

    def fraction(self, numerator: str, denominator: str) -> str:
        # Korean reads a fraction denominator-first. Keeping this policy here
        # also aligns speech with the project's Korean math-braille ordering.
        return f"{denominator}분의 {numerator}".strip()


DEFAULT_KOREAN_MATH_NATURALIZER: MathSpeechNaturalizer = KoreanMathSpeechNaturalizer()


def _has_final_consonant(phrase: str) -> bool:
    text = phrase.rstrip()
    if not text:
        return False

    number_match = _NUMBER_AT_END.search(text)
    if number_match is not None:
        fractional_digits = number_match.group(2)
        if fractional_digits:
            return _DIGIT_FINAL_CONSONANT[fractional_digits[-1]]
        return _integer_has_final_consonant(number_match.group(1).replace(",", ""))

    final = text[-1]
    codepoint = ord(final)
    if 0xAC00 <= codepoint <= 0xD7A3:
        return (codepoint - 0xAC00) % 28 != 0
    if final.isascii() and final.isalpha():
        return final in _LATIN_FINAL_CONSONANT
    return False


def _integer_has_final_consonant(digits: str) -> bool:
    digits = digits.lstrip("0") or "0"
    if digits == "0" or digits[-1] != "0":
        return _DIGIT_FINAL_CONSONANT[digits[-1]]

    trailing_zero_count = len(digits) - len(digits.rstrip("0"))
    if trailing_zero_count < 4:
        return True  # 십, 백, 천

    large_unit_index = trailing_zero_count // 4
    # 만(ㄴ), 억(ㄱ), 조(no jongseong), 경(ㅇ), 해(no jongseong).
    large_unit_final = (True, True, False, True, False)
    if 1 <= large_unit_index <= len(large_unit_final):
        return large_unit_final[large_unit_index - 1]
    return False
