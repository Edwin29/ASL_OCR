from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Button = Literal["UP", "DOWN", "LEFT", "RIGHT"]
ButtonAction = Literal["SHORT", "LONG"]


@dataclass(frozen=True)
class NavigationCommand:
    """A debounced logical button event, as defined by the hardware input
    contract (one physical press produces exactly one SHORT or one LONG, never
    both). `sequence` and `timestamp_ms` are omitted here since the pure
    navigation logic in `application/` does not need them; the hardware
    transport layer (Phase 5) is responsible for ordering and dedup before a
    command reaches this type.
    """

    button: Button
    action: ButtonAction
