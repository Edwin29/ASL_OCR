"""DOCUMENT-mode navigation over an AccessibleDocument's flattened focus items.

Position is `(page_index, node_index)`, not a single flat index, matching the
plan document's navigation-state shape -- moving past the last item on a page
rolls over to the first item of the next page rather than stopping.
"""

from __future__ import annotations

from document_parser.accessibility.braille.math_translator import (
    braille_scrollable_spans,
    math_focus_item_to_braille,
)
from document_parser.accessibility.braille.viewport import build_frame, last_window_offset, scroll
from document_parser.accessibility.domain.commands import NavigationCommand
from document_parser.accessibility.domain.events import NavigationResult
from document_parser.accessibility.domain.navigation_state import NavigationState


def current_focus_item(document: dict[str, object], state: NavigationState) -> dict[str, object] | None:
    pages = document["pages"]
    if not (0 <= state.page_index < len(pages)):
        return None
    focus_items = pages[state.page_index]["focus_items"]
    if not (0 <= state.node_index < len(focus_items)):
        return None
    return focus_items[state.node_index]


def next_node(document: dict[str, object], state: NavigationState) -> NavigationResult:
    pages = document["pages"]
    page = pages[state.page_index]
    if state.node_index + 1 < len(page["focus_items"]):
        return NavigationResult(state.advanced(node_index=state.node_index + 1, braille_offset=0, math_span_index=0))
    if state.page_index + 1 < len(pages):
        return NavigationResult(state.advanced(
            page_index=state.page_index + 1, node_index=0, braille_offset=0, math_span_index=0,
        ))
    # Boundary: still bump generation so a stale in-flight callback from
    # before this button press cannot be mistaken for the current focus.
    return NavigationResult(state.advanced(), boundary_message="문서의 끝입니다.")


def previous_node(document: dict[str, object], state: NavigationState) -> NavigationResult:
    if state.node_index - 1 >= 0:
        return NavigationResult(state.advanced(node_index=state.node_index - 1, braille_offset=0, math_span_index=0))
    if state.page_index - 1 >= 0:
        previous_page = document["pages"][state.page_index - 1]
        last_index = max(len(previous_page["focus_items"]) - 1, 0)
        return NavigationResult(state.advanced(
            page_index=state.page_index - 1, node_index=last_index, braille_offset=0, math_span_index=0,
        ))
    return NavigationResult(state.advanced(), boundary_message="문서의 시작입니다.")


def handle_command(document: dict[str, object], state: NavigationState, command: NavigationCommand) -> NavigationResult:
    """Dispatch a DOCUMENT-mode button command. Only UP/DOWN SHORT (previous/
    next node) are implemented in this phase; every other command is
    explicitly reported as unsupported rather than silently ignored, since
    LEFT/RIGHT (braille viewport scroll) and the LONG variants (re-read,
    continuous reading) require the TTS/braille wiring built in later phases.
    """
    if command.button == "UP" and command.action == "SHORT":
        return previous_node(document, state)
    if command.button == "DOWN" and command.action == "SHORT":
        return next_node(document, state)
    return NavigationResult(state, boundary_message="이 버튼 입력은 아직 지원되지 않습니다.")


def move_braille_cursor(
    item: dict[str, object] | None,
    state: NavigationState,
    direction: str,
    viewport_size: int,
) -> NavigationResult:
    """LEFT/RIGHT braille handling (좌우 연장, Decision 2): scrolls the
    viewport window within the currently active inline math span, and once
    that span's window is exhausted, continues into the next/previous
    inline math span in the same block. Never rolls over to an adjacent
    top-level focus item -- that stays UP/DOWN's exclusive job. Not wired
    into `handle_command()` above -- `SpeechController` calls this
    directly, since it needs the actual `viewport_size` its
    `BraillePresenter` renders with (see that module for why)."""
    if item is None:
        return NavigationResult(state.advanced(), boundary_message="현재 항목을 찾을 수 없습니다.")

    spans = braille_scrollable_spans(item)
    if not spans:
        return NavigationResult(state.advanced(), boundary_message="이 항목에는 점자로 표시할 수식이 없습니다.")

    span_index = min(max(state.math_span_index, 0), len(spans) - 1)
    cells = math_focus_item_to_braille(spans[span_index])
    frame_id = f"{item.get('id', 'focus')}#{span_index}"
    current_frame = build_frame(frame_id, cells, state.braille_offset, viewport_size)

    if direction == "RIGHT":
        if current_frame["has_next"]:
            new_frame = scroll(frame_id, cells, state.braille_offset, viewport_size, "RIGHT")
            return NavigationResult(state.advanced(braille_offset=new_frame["offset"]))
        if span_index + 1 < len(spans):
            return NavigationResult(state.advanced(math_span_index=span_index + 1, braille_offset=0))
        return NavigationResult(state.advanced(), boundary_message="더 이상 표시할 수식이 없습니다.")

    if direction == "LEFT":
        if current_frame["has_previous"]:
            new_frame = scroll(frame_id, cells, state.braille_offset, viewport_size, "LEFT")
            return NavigationResult(state.advanced(braille_offset=new_frame["offset"]))
        if span_index - 1 >= 0:
            prev_cells = math_focus_item_to_braille(spans[span_index - 1])
            return NavigationResult(state.advanced(
                math_span_index=span_index - 1,
                braille_offset=last_window_offset(len(prev_cells), viewport_size),
            ))
        return NavigationResult(state.advanced(), boundary_message="이전에 표시할 수식이 없습니다.")

    raise ValueError(f"Unknown braille scroll direction: {direction!r}")
