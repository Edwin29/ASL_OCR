"""TTS-only pronunciation normalization.

These substitutions must never be written back to OCR/Page IR text.  They
exist solely to give the Korean voice engine unambiguous phonetic input while
keeping mathematical source notation (for example ``x축``) intact.
"""

from __future__ import annotations

import re


_AXIS_PRONUNCIATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<![A-Za-z])(?:x|X)\s*축"), "엑스축"),
    (re.compile(r"(?<![A-Za-z])(?:y|Y)\s*축"), "와이축"),
)

_VARIABLE_READINGS = {
    "a": "에이", "b": "비", "c": "씨", "d": "디", "e": "이", "f": "에프",
    "g": "지", "h": "에이치", "i": "아이", "j": "제이", "k": "케이", "l": "엘",
    "m": "엠", "n": "엔", "o": "오", "p": "피", "q": "큐", "r": "알",
    "s": "에스", "t": "티", "u": "유", "v": "브이", "w": "더블유", "x": "엑스",
    "y": "와이", "z": "제트",
}

# ASCII lookarounds keep these rules out of English words such as "text" and
# "xlsx", while still covering standalone math variables in f(x), 2x, x=1,
# and Korean postpositions such as a가.  Case does not change the spoken letter.
_STANDALONE_VARIABLE_PRONUNCIATIONS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rf"(?<![A-Za-z]){letter}(?![A-Za-z])", re.IGNORECASE), reading)
    for letter, reading in _VARIABLE_READINGS.items()
)

_SYMBOL_PRONUNCIATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\\(?:leq|le)\b"), " 작거나 같다 "),
    (re.compile(r"\\(?:geq|ge)\b"), " 크거나 같다 "),
    (re.compile(r"\\(?:neq|ne)\b"), " 같지 않다 "),
    (re.compile("≤"), " 작거나 같다 "),
    (re.compile("≥"), " 크거나 같다 "),
    (re.compile("≠"), " 같지 않다 "),
    (re.compile("≈"), " 거의 같다 "),
    (re.compile("≡"), " 항등적으로 같다 "),
)

_GREEK_PRONUNCIATIONS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(symbol), reading)
    for symbol, reading in {
        "α": "알파", "β": "베타", "γ": "감마", "Γ": "감마", "δ": "델타", "Δ": "델타",
        "ε": "엡실론", "ζ": "제타", "η": "에타", "θ": "세타", "Θ": "세타", "ι": "요타",
        "κ": "카파", "λ": "람다", "Λ": "람다", "μ": "뮤", "ν": "뉴", "ξ": "크시",
        "π": "파이", "Π": "파이", "ρ": "로", "σ": "시그마", "Σ": "시그마", "τ": "타우",
        "φ": "파이", "Φ": "파이", "χ": "카이", "ψ": "프사이", "Ψ": "프사이",
        "ω": "오메가", "Ω": "오메가", "∞": "무한대",
    }.items()
)

_LATEX_GREEK_PRONUNCIATIONS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rf"\\{name}\b"), reading)
    for name, reading in {
        "alpha": "알파", "beta": "베타", "gamma": "감마", "delta": "델타",
        "epsilon": "엡실론", "zeta": "제타", "eta": "에타", "theta": "세타",
        "iota": "요타", "kappa": "카파", "lambda": "람다", "mu": "뮤", "nu": "뉴",
        "xi": "크시", "pi": "파이", "rho": "로", "sigma": "시그마", "tau": "타우",
        "phi": "파이", "chi": "카이", "psi": "프사이", "omega": "오메가",
        "Gamma": "감마", "Delta": "델타", "Theta": "세타", "Lambda": "람다",
        "Pi": "파이", "Sigma": "시그마", "Phi": "파이", "Psi": "프사이", "Omega": "오메가",
        "infty": "무한대",
    }.items()
)

_ABSOLUTE_VALUE = re.compile(r"\|([A-Za-z0-9α-ωΑ-Ω+\-*/^() ]{1,40})\|")
_COMPACT_VARIABLE_PRODUCT = re.compile(r"(?<=[0-9=+\-*/^(])([A-Za-z]{2,4})(?=[0-9=+\-*/),^]|$)")


def _absolute_value_pronunciation(match: re.Match[str]) -> str:
    body = match.group(1).strip()
    # OCR sometimes emits |ab| as one ASCII word.  Inside absolute-value bars
    # this is mathematical adjacency, so expose each variable to the phonetic
    # variable rules below instead of treating it as English prose.
    if re.fullmatch(r"[A-Za-z]{2,4}", body):
        body = " ".join(body)
    return f"{body}의 절댓값"


def normalize_tts_pronunciation(text: str) -> str:
    normalized = _ABSOLUTE_VALUE.sub(_absolute_value_pronunciation, text)
    # Compact algebraic products such as ax and xy have no separator for the
    # ordinary standalone-letter matcher.  Only split them when operators,
    # parentheses, or digits establish an unmistakably mathematical context.
    normalized = _COMPACT_VARIABLE_PRODUCT.sub(lambda match: " ".join(match.group(1)), normalized)
    for pattern, replacement in _SYMBOL_PRONUNCIATIONS:
        normalized = pattern.sub(replacement, normalized)
    for pattern, replacement in _LATEX_GREEK_PRONUNCIATIONS:
        normalized = pattern.sub(replacement, normalized)
    for pattern, replacement in _GREEK_PRONUNCIATIONS:
        normalized = pattern.sub(replacement, normalized)
    for pattern, replacement in _AXIS_PRONUNCIATIONS:
        normalized = pattern.sub(replacement, normalized)
    for pattern, replacement in _STANDALONE_VARIABLE_PRONUNCIATIONS:
        normalized = pattern.sub(replacement, normalized)
    return re.sub(r"\s+", " ", normalized).strip()
