"""Plain-data shapes for the accessibility layer: AccessibleDocument builders,
navigation state, and the command/result types navigators exchange."""

from document_parser.accessibility.domain.accessible_document import (
    FOCUS_KINDS,
    build_accessible_document,
    build_focus_item,
    build_page,
)
from document_parser.accessibility.domain.commands import NavigationCommand
from document_parser.accessibility.domain.events import NavigationResult
from document_parser.accessibility.domain.navigation_state import NavigationState

__all__ = [
    "FOCUS_KINDS",
    "NavigationCommand",
    "NavigationResult",
    "NavigationState",
    "build_accessible_document",
    "build_focus_item",
    "build_page",
]
