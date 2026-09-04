"""Small, deterministic OCR correction dictionary.

The source OCR string is never changed in place.  Callers store it as
``raw_text`` and use :func:`correct_ocr_text` only for ``normalized_text`` and
derived reading spans.  Every applied rule is returned so the Page IR can
retain an audit trail instead of silently rewriting recognized content.

Rules here are deliberately narrow.  They cover errors observed repeatedly
in the EBS mathematics capture corpus and should not become a general Korean
spell checker; ambiguous candidates belong in the review/LLM tier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    pattern: Pattern[str]
    replacement: str


@dataclass(frozen=True)
class AppliedCorrection:
    rule_id: str
    source: str
    replacement: str
    count: int


@dataclass(frozen=True)
class CorrectionResult:
    text: str
    applied: tuple[AppliedCorrection, ...]


# Longer/contextual patterns run before their shorter components.  A bare
# ``합수`` is corrected only when it is a token-like math word; embedded
# ordinary Korean strings are left alone.
_RULES: tuple[_Rule, ...] = (
    _Rule("ko_math_continuous_two_functions", re.compile(r"언속인\s+두\s+회수"), "연속인 두 함수"),
    _Rule(
        "ko_math_function_before_formula",
        re.compile(r"(?<![가-힣])(?:회수|한수|힘수)(?=\s+(?:[fFgG]\s*\(|\$))"),
        "함수",
    ),
    _Rule("ko_math_quadratic_function", re.compile(r"이차합수"), "이차함수"),
    _Rule("ko_math_two_functions_spacing", re.compile(r"두합수"), "두 함수"),
    _Rule("ko_math_absolute_value", re.compile(r"절맛값"), "절댓값"),
    _Rule("ko_math_minimum_value", re.compile(r"최앗값"), "최솟값"),
    _Rule("ko_math_function", re.compile(r"(?<![가-힣])합수(?=\s|$|[.,?!:;)])"), "함수"),
)


def correct_ocr_text(text: str) -> CorrectionResult:
    """Return corrected text plus the exact rules that changed it."""
    corrected = text
    applied: list[AppliedCorrection] = []
    for rule in _RULES:
        matches = list(rule.pattern.finditer(corrected))
        if not matches:
            continue
        sources = {match.group(0) for match in matches}
        corrected = rule.pattern.sub(rule.replacement, corrected)
        applied.append(AppliedCorrection(
            rule_id=rule.rule_id,
            source=" | ".join(sorted(sources)),
            replacement=rule.replacement,
            count=len(matches),
        ))
    return CorrectionResult(text=corrected, applied=tuple(applied))


def correction_issues(result: CorrectionResult) -> list[dict[str, object]]:
    """Serialize applied corrections into Page IR-compatible issue records."""
    return [
        {
            "code": "OCR_DICTIONARY_CORRECTION",
            "severity": "info",
            "message": (
                f"Applied OCR correction rule {item.rule_id}: "
                f"{item.source!r} -> {item.replacement!r} ({item.count} occurrence(s))."
            ),
            "rule_id": item.rule_id,
            "source": item.source,
            "replacement": item.replacement,
            "count": item.count,
        }
        for item in result.applied
    ]
