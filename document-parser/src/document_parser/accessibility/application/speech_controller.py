"""Wires Phase 1 navigation (document/table navigators) to a TtsEngineAdapter:
cancel-then-speak on every focus change, continuous reading driven purely by
completion events (plan document §7.4), and generation-based staleness
filtering (§12.2) so a completion callback for an utterance the user has
already navigated away from is ignored rather than mistaken for current.

No priority queue: at most one utterance is ever in flight, and any new
focus unconditionally cancels it first -- see the plan file for why this is
enough for the DOCUMENT/TABLE navigation built so far.
"""

from __future__ import annotations

from document_parser.accessibility.adapters.tts_engine import TtsEngineAdapter
from document_parser.accessibility.application.document_navigator import current_focus_item
from document_parser.accessibility.application.document_navigator import handle_command as navigate_document
from document_parser.accessibility.application.document_navigator import move_braille_cursor, next_node
from document_parser.accessibility.application.document_navigator import next_page, previous_page
from document_parser.accessibility.application.table_navigator import current_cell, enter_table, exit_table
from document_parser.accessibility.application.table_navigator import move as move_table_cursor
from document_parser.accessibility.application.table_navigator import move_table_braille_cursor
from document_parser.accessibility.braille.braille_presenter import BraillePresenter
from document_parser.accessibility.braille.math_translator import braille_scrollable_spans
from document_parser.accessibility.braille.viewport import clear_frame
from document_parser.accessibility.domain.commands import NavigationCommand
from document_parser.accessibility.domain.events import NavigationResult
from document_parser.accessibility.domain.navigation_state import NavigationState
from document_parser.accessibility.speech import focus_item_announcement, normalize_tts_pronunciation
from document_parser.accessibility.speech.math_rules import math_focus_item_to_speech
from document_parser.accessibility.speech.table_rules import table_cell_announcement

TABLE_ENTRY_BUTTON = "RIGHT"


class SpeechController:
    def __init__(
        self,
        document: dict[str, object],
        initial_state: NavigationState,
        engine: TtsEngineAdapter,
        braille_presenter: BraillePresenter | None = None,
    ) -> None:
        self._document = document
        self._state = initial_state
        self._engine = engine
        self._braille_presenter = braille_presenter if braille_presenter is not None else BraillePresenter()
        self._braille_frame: dict[str, object] = clear_frame("none")
        self._continuous_reading = False
        engine.on_complete(self._handle_complete)

    @property
    def state(self) -> NavigationState:
        return self._state

    @property
    def continuous_reading(self) -> bool:
        return self._continuous_reading

    @property
    def braille_frame(self) -> dict[str, object]:
        return self._braille_frame

    def speak_current(self) -> None:
        """Announce the current focus without moving -- call once after
        construction to start the session, or after e.g. a device
        reconnect (plan document §12.3)."""
        self._engine.cancel()
        self._speak_focus(self._state)

    def handle_command(self, command: NavigationCommand) -> None:
        if command.button == "DOWN" and command.action == "LONG":
            self._toggle_continuous_reading()
            return

        if command.button == "CONFIRM" and command.action == "SHORT":
            # Replay is a fresh playback authority even though focus does not
            # move. Advance generation so the device audio arbiter does not
            # deduplicate it against the preceding snapshot/audio reference.
            self._continuous_reading = False
            self._state = self._state.advanced()
            self._engine.cancel()
            self._speak_focus(self._state)
            return

        # Any explicit navigation input interrupts continuous reading (§7.5).
        self._continuous_reading = False

        # PAGE_NEXT/PAGE_PREVIOUS (dedicated page-turn buttons) are handled
        # here, before the TABLE/DOCUMENT mode split below, because they must
        # work the same regardless of current mode -- pressing one while
        # inside a table jumps straight to the next/previous page's first
        # item AND leaves table mode in the same step (see next_page's
        # docstring for why it always resets to DOCUMENT), rather than
        # requiring a separate "exit table" press first.
        if command.button in ("PAGE_NEXT", "PAGE_PREVIOUS") and command.action == "SHORT":
            result = (
                next_page(self._document, self._state) if command.button == "PAGE_NEXT"
                else previous_page(self._document, self._state)
            )
            self._state = result.state
            self._engine.cancel()
            self._speak_result(result)
            return

        # LEFT/RIGHT braille viewport scroll (좌우 연장, Decision 2) is
        # intercepted here, before the generic cancel-then-speak-the-whole-
        # focus flow below, because it needs different TTS semantics: silent
        # on a pure within-span window scroll, announce only the newly
        # entered inline formula on a span-to-span extension -- never a
        # blanket re-read of the whole TEXT block. Excluded when the current
        # item is a TABLE so RIGHT's existing table-entry behavior
        # (TABLE_ENTRY_BUTTON, handled below) is untouched.
        if self._state.mode == "DOCUMENT" and command.button in ("LEFT", "RIGHT") and command.action == "SHORT":
            item = current_focus_item(self._document, self._state)
            if item is None or item.get("kind") != "TABLE":
                self._handle_braille_scroll(item, command.button)
                return

        # LEFT/RIGHT LONG in TABLE mode: within-cell braille scroll, kept on
        # the LONG variant specifically so SHORT's already-tested cell-to-
        # cell movement (`move_table_cursor`) is completely untouched.
        if self._state.mode == "TABLE" and command.button in ("LEFT", "RIGHT") and command.action == "LONG":
            self._handle_table_braille_scroll(command.button)
            return

        if self._state.mode == "TABLE":
            result = self._handle_table_command(command)
        else:
            result = self._handle_document_command(command)

        self._state = result.state
        self._engine.cancel()
        self._speak_result(result)

    def _handle_document_command(self, command: NavigationCommand) -> NavigationResult:
        if command.button == TABLE_ENTRY_BUTTON and command.action == "SHORT":
            item = current_focus_item(self._document, self._state)
            if item is not None and item["kind"] == "TABLE":
                return enter_table(item, self._state)
        return navigate_document(self._document, self._state, command)

    def _handle_table_command(self, command: NavigationCommand) -> NavigationResult:
        if command.button == "UP" and command.action == "LONG":
            return exit_table(self._state)
        if command.action == "SHORT" and command.button in ("UP", "DOWN", "LEFT", "RIGHT"):
            table_item = current_focus_item(self._document, self._state)
            if table_item is None:
                return NavigationResult(self._state, boundary_message="표를 찾을 수 없습니다.")
            return move_table_cursor(table_item, self._state, command.button)
        return NavigationResult(self._state, boundary_message="이 버튼 입력은 아직 지원되지 않습니다.")

    def _handle_braille_scroll(self, item: dict[str, object] | None, button: str) -> None:
        previous_span_index = self._state.math_span_index
        result = move_braille_cursor(item, self._state, button, self._braille_presenter.viewport_size)
        self._state = result.state
        self._refresh_braille_frame(self._state)
        self._engine.cancel()
        if result.boundary_message and result.boundary_is_audible:
            self._engine.speak(result.boundary_message, self._state.generation)
        elif self._state.math_span_index != previous_span_index:
            new_span = braille_scrollable_spans(item)[self._state.math_span_index]
            self._engine.speak(
                normalize_tts_pronunciation(math_focus_item_to_speech(new_span)),
                self._state.generation,
            )
        # else: pure within-span window scroll -- braille frame refreshed
        # above, no new speech (per user decision: silent on scroll-only).

    def _handle_table_braille_scroll(self, button: str) -> None:
        table_item = current_focus_item(self._document, self._state)
        cell = current_cell(table_item, self._state) if table_item is not None else None
        result = move_table_braille_cursor(cell, self._state, button, self._braille_presenter.viewport_size)
        self._state = result.state
        self._refresh_braille_frame(self._state)
        self._engine.cancel()
        if result.boundary_message and result.boundary_is_audible:
            self._engine.speak(result.boundary_message, self._state.generation)
        # else: pure within-cell window scroll -- silent, same rule as
        # DOCUMENT mode's within-span scroll.

    def _toggle_continuous_reading(self) -> None:
        self._continuous_reading = not self._continuous_reading
        self._engine.cancel()
        if self._continuous_reading:
            self._speak_focus(self._state)

    def _handle_complete(self, generation: int) -> None:
        if generation != self._state.generation:
            return  # stale event from an utterance the user already left (§12.2)
        if not self._continuous_reading:
            return
        result = next_node(self._document, self._state)
        self._state = result.state
        if result.boundary_message:
            self._continuous_reading = False
            self._engine.speak(result.boundary_message, self._state.generation)
            self._refresh_braille_frame(self._state)
            return
        self._speak_focus(self._state)

    def _speak_result(self, result: NavigationResult) -> None:
        if result.boundary_message:
            if result.boundary_is_audible:
                self._engine.speak(result.boundary_message, self._state.generation)
            self._refresh_braille_frame(self._state)
            return
        self._speak_focus(self._state)

    def _speak_focus(self, state: NavigationState) -> None:
        self._engine.speak(self._focus_speech(state), state.generation)
        self._refresh_braille_frame(state)

    def _refresh_braille_frame(self, state: NavigationState) -> None:
        if state.mode == "TABLE":
            table_item = current_focus_item(self._document, state)
            cell = current_cell(table_item, state) if table_item is not None else None
            self._braille_frame = (
                self._braille_presenter.present_table_cell(cell, state.braille_offset)
                if cell is not None else clear_frame("none")
            )
            return
        item = current_focus_item(self._document, state)
        self._braille_frame = self._braille_presenter.present_focus(item, state.braille_offset, state.math_span_index)

    def _focus_speech(self, state: NavigationState) -> str:
        if state.mode == "TABLE":
            table_item = current_focus_item(self._document, state)
            cell = current_cell(table_item, state) if table_item is not None else None
            return (
                normalize_tts_pronunciation(table_cell_announcement(cell))
                if cell is not None else "셀을 찾을 수 없습니다."
            )

        item = current_focus_item(self._document, state)
        if item is None:
            return ""
        return focus_item_announcement(item)
