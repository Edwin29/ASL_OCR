from __future__ import annotations

from dataclasses import dataclass

from document_parser.accessibility.domain.navigation_state import NavigationState


@dataclass(frozen=True)
class NavigationResult:
    """Outcome of applying one `NavigationCommand`.

    `state` always carries the current `generation`, even when the command hit
    a boundary and the focus did not move (`state` is then the unchanged input
    state with the same generation). `boundary_message` describes a boundary
    condition ("첫 행입니다" etc.); it is None when the command moved focus
    normally. Some boundary details are diagnostic state rather than
    user-facing speech; those set `boundary_is_audible` to False.
    """

    state: NavigationState
    boundary_message: str | None = None
    boundary_is_audible: bool = True
