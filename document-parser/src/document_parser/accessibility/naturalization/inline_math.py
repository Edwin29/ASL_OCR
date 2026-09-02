"""Context policy for inline math that should not be a standalone target.

The formula remains in the mixed-content sentence, so no recognized content
is dropped. This policy only suppresses an extra TTS utterance and braille
navigation stop when a registered Korean lexical suffix is directly adjacent.
"""

from __future__ import annotations

# Start conservatively. Add entries only with a reviewed corpus example and a
# regression test; a broad rule would incorrectly hide real variables such as
# "$a$의 값" or "$m$이라 할 때".
INLINE_MATH_LEXICAL_SUFFIXES = frozenset({"축"})


def adjacent_inline_math_lexical_suffix(following_text: object) -> str | None:
    if not isinstance(following_text, str):
        return None
    for suffix in sorted(INLINE_MATH_LEXICAL_SUFFIXES, key=len, reverse=True):
        if following_text.startswith(suffix):
            return suffix
    return None
