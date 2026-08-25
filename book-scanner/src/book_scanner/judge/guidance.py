"""TransmitBlockReason -> user-facing guidance text.

Text only -- actual beep pattern / TTS engine wiring is out of scope until
hardware exists (see plan). This function is that later step's input.

LOW_QUALITY deliberately maps to None: it's usually not something
repositioning fixes (focus, lighting), the user often can't tell what to
change, and the repeated-capture loop's natural retry on the next frame
is a reasonable first response. Revisit once real footage shows whether
LOW_QUALITY needs its own guidance after all.
"""

from __future__ import annotations

from book_scanner.judge.types import TransmitBlockReason

_MESSAGES: dict[TransmitBlockReason, str] = {
    TransmitBlockReason.PAGE_NOT_FOUND: "책이 보이지 않습니다. 책을 올려주세요.",
    TransmitBlockReason.ROTATED_TOO_MUCH: "책이 기울어져 있습니다. 반듯하게 놓아주세요.",
    TransmitBlockReason.TOO_SMALL: "더 가까이 가져가 주세요.",
    TransmitBlockReason.TOO_LARGE: "더 멀리 놓아주세요.",
    TransmitBlockReason.OUT_OF_FRAME: "책을 중앙으로 옮겨주세요.",
    TransmitBlockReason.UNSTABLE: "잠시 움직이지 말아주세요.",
}


def guidance_for(reason: TransmitBlockReason) -> str | None:
    """Returns None when no actionable text is defined for `reason` (see
    LOW_QUALITY note above) -- callers should treat that as "keep trying,
    say nothing new," not as an error."""
    return _MESSAGES.get(reason)
