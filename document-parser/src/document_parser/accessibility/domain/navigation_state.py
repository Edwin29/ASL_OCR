from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

NavigationMode = Literal["DOCUMENT", "TABLE"]


@dataclass(frozen=True)
class NavigationState:
    """Current tracked focus, shared by TTS and the braille display.

    `generation` increments on every focus change so that late-arriving TTS
    completion callbacks or hardware ACKs from a superseded focus can be
    detected and ignored by comparing generations, rather than assumed current.
    """

    document_id: str
    page_index: int
    node_index: int
    mode: NavigationMode = "DOCUMENT"
    table_row: int | None = None
    table_column: int | None = None
    braille_offset: int = 0
    math_span_index: int = 0
    generation: int = 0

    def advanced(self, **changes: object) -> "NavigationState":
        """Return a copy with `changes` applied and `generation` incremented.

        Any actual focus change (page/node/mode/table position) must go
        through this method rather than direct field assignment, so the
        generation counter cannot be forgotten at a call site.
        """
        return replace(self, generation=self.generation + 1, **changes)
