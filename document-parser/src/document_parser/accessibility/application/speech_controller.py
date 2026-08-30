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
from document_parser.accessibility.application.document_navigator import move_braille_cursor, next_node, previous_node
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
from document_parser.accessibility.speech import focus_item_announcement
from document_parser.accessibility.speech.math_rules import math_focus_item_to_speech
from document_parser.accessibility.speech.table_rules import table_cell_announcement

TABLE_ENTRY_BUTTON = "RIGHT"

# How many single steps a LONG press moves at once (project decision: the
# firmware reports exactly one SHORT/LONG event per press-release cycle --
# there is no "still held" signal -- so "hold to keep moving" is a software-
# side batch of steps taken all at once when the LONG event arrives, not a
# true continuous repeat while the button stays down). Provisional, not yet
# measured against real hardware feel.
_BURST_STEP_COUNT = 5


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
        # Any explicit navigation input interrupts continuous reading (§7.5).
        # Continuous reading is no longer reachable from a button (DOWN LONG
        # is now burst node movement, below) but the mechanism itself is
        # left in place rather than deleted -- nothing else in the codebase
        # depends on removing it, and disconnecting is easily reversed.
        self._continuous_reading = False

        # CONFIRM SHORT: replay the current focus's TTS without moving --
        # mode-agnostic (works identically in DOCUMENT and TABLE mode, since
        # _speak_focus already branches on state.mode), so handled before
        # the mode split below. CONFIRM LONG ("return to datapack selection
        # screen") is not this class's concern -- it's intercepted by the
        # orchestration layer above SpeechController before a command ever
        # reaches here, since it means abandoning this session entirely.
        if command.button == "CONFIRM" and command.action == "SHORT":
            self._engine.cancel()
            self._speak_focus(self._state)
            return

        # PAGE_NEXT/PAGE_PREVIOUS (dedicated page-turn buttons) are handled
        # here, before the TABLE/DOCUMENT mode split below, because they must
        # work the same regardless of current mode -- pressing one while
        # inside a table jumps straight to the next/previous page's first
        # item AND leaves table mode in the same step (see next_page's
        # docstring for why it always resets to DOCUMENT), rather than
        # requiring a separate "exit table" press first. Page crossing is
        # exclusively these buttons' job -- plain node navigation
        # (next_node/previous_node) stops at page boundaries instead of
        # rolling over (project decision).
        if command.button in ("PAGE_NEXT", "PAGE_PREVIOUS") and command.action == "SHORT":
            result = (
                next_page(self._document, self._state) if command.button == "PAGE_NEXT"
                else previous_page(self._document, self._state)
            )
            self._state = result.state
            self._engine.cancel()
            self._speak_result(result)
            return

        # UP/DOWN LONG in DOCUMENT mode: burst node movement (see
        # _BURST_STEP_COUNT). Excluded in TABLE mode -- UP LONG there still
        # means "exit table" (handled below, untouched).
        if self._state.mode == "DOCUMENT" and command.button in ("UP", "DOWN") and command.action == "LONG":
            self._handle_burst_node_move(command.button)
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

        # LEFT/RIGHT LONG in DOCUMENT mode, non-TABLE item: burst braille
        # scroll, same exclusion as the SHORT version above so TABLE mode's
        # own LEFT/RIGHT LONG meaning (within-cell scroll, below) is
        # untouched.
        if self._state.mode == "DOCUMENT" and command.button in ("LEFT", "RIGHT") and command.action == "LONG":
            item = current_focus_item(self._document, self._state)
            if item is None or item.get("kind") != "TABLE":
                self._handle_burst_braille_scroll(item, command.button)
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

    def _handle_burst_node_move(self, button: str) -> None:
        """Repeats the SHORT step's node movement up to _BURST_STEP_COUNT
        times, speaking only once at the end. `boundary_message` doubles as
        this project's "this step made no progress" signal (see
        `document_navigator.py`: a boundary result never changes
        page_index/node_index) -- so a boundary only reached *after* the
        burst already advanced means the probe past the last valid step
        failed, not that the node actually landed on IS the boundary. In
        that case the landed node's own announcement is spoken, exactly
        like a normal SHORT press there would -- the boundary message is
        only surfaced when the very first step of the burst is already a
        dead end (nothing moved at all)."""
        move = previous_node if button == "UP" else next_node
        made_progress = False
        result = None
        for _ in range(_BURST_STEP_COUNT):
            result = move(self._document, self._state)
            self._state = result.state
            if result.boundary_message:
                break
            made_progress = True
        self._engine.cancel()
        if made_progress:
            self._speak_focus(self._state)
        else:
            self._engine.speak(result.boundary_message, self._state.generation)
            self._refresh_braille_frame(self._state)

    def _handle_burst_braille_scroll(self, item: dict[str, object] | None, button: str) -> None:
        """LEFT/RIGHT LONG in DOCUMENT mode: repeats the SHORT step's
        braille scroll up to _BURST_STEP_COUNT times. Same silent/announce
        rule as `_handle_braille_scroll`, aggregated over the whole burst
        (see `_handle_burst_node_move`'s docstring for why a boundary reached
        after progress was already made doesn't override the announcement
        the burst actually earned): if the final span differs from where
        the burst started, speak that new span; if it never left the
        starting span, stay silent; a boundary is only spoken if the very
        first step is already a dead end."""
        starting_span_index = self._state.math_span_index
        made_progress = False
        result = None
        for _ in range(_BURST_STEP_COUNT):
            result = move_braille_cursor(item, self._state, button, self._braille_presenter.viewport_size)
            self._state = result.state
            if result.boundary_message:
                break
            made_progress = True
        self._refresh_braille_frame(self._state)
        self._engine.cancel()
        if not made_progress:
            self._engine.speak(result.boundary_message, self._state.generation)
        elif self._state.math_span_index != starting_span_index:
            new_span = braille_scrollable_spans(item)[self._state.math_span_index]
            self._engine.speak(math_focus_item_to_speech(new_span), self._state.generation)
        # else: silent, matching the SHORT version's within-span-only rule.

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
        if result.boundary_message:
            self._engine.speak(result.boundary_message, self._state.generation)
        elif self._state.math_span_index != previous_span_index:
            new_span = braille_scrollable_spans(item)[self._state.math_span_index]
            self._engine.speak(math_focus_item_to_speech(new_span), self._state.generation)
        # else: pure within-span window scroll -- braille frame refreshed
        # above, no new speech (per user decision: silent on scroll-only).

    def _handle_table_braille_scroll(self, button: str) -> None:
        table_item = current_focus_item(self._document, self._state)
        cell = current_cell(table_item, self._state) if table_item is not None else None
        result = move_table_braille_cursor(cell, self._state, button, self._braille_presenter.viewport_size)
        self._state = result.state
        self._refresh_braille_frame(self._state)
        self._engine.cancel()
        if result.boundary_message:
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
            return table_cell_announcement(cell) if cell is not None else "셀을 찾을 수 없습니다."

        item = current_focus_item(self._document, state)
        if item is None:
            return ""
        return focus_item_announcement(item)
