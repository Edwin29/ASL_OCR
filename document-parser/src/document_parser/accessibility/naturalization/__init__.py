"""Replaceable Korean accessibility naturalization policies.

This package is deliberately separate from AST parsing, speech rendering,
and braille encoding. A future morphology service or learned naturalizer can
replace these rule-based policies without changing those pipeline stages.
"""

from document_parser.accessibility.naturalization.inline_math import (
    INLINE_MATH_LEXICAL_SUFFIXES,
    adjacent_inline_math_lexical_suffix,
)
from document_parser.accessibility.naturalization.korean_math_speech import (
    DEFAULT_KOREAN_MATH_NATURALIZER,
    KoreanMathSpeechNaturalizer,
    MathSpeechNaturalizer,
)

__all__ = [
    "DEFAULT_KOREAN_MATH_NATURALIZER",
    "INLINE_MATH_LEXICAL_SUFFIXES",
    "KoreanMathSpeechNaturalizer",
    "MathSpeechNaturalizer",
    "adjacent_inline_math_lexical_suffix",
]
