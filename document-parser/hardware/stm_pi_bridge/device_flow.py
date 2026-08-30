"""Device-driven datapack selection screen, chained into one continuous
loop with the reading session -- replaces test_client.py's console
input()-based book picker with real button navigation (project decision:
selection screen + reading should be a single flow on the device, not two
separate manual steps). CONFIRM (the new center button, see
accessibility.domain.commands) does double duty: SHORT selects a book on
this screen / replays the current item during reading; LONG returns to
this screen from anywhere inside a reading session.

No server-side state change was needed for this: `DatapackSession`
structurally requires a book_id already chosen (server/session.py), so "no
book picked yet" lives entirely here, client-side -- the same role
test_client.py's console `input()` loop played before, just driven by real
button presses instead of typed numbers.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Callable

from pi_bridge import AudioPlayer, HttpRemoteSession, LineTransport, RemoteSession, emit_response, parse_nav_line

# The shared confirmation cue (see ../../assets/audio/README.md) -- played
# locally by this host, not server-mediated, since selecting a book has no
# NavigationResult/audio_ref of its own to piggyback on the way every other
# TTS trigger in this project does.
CONFIRM_BEEP_PATH = Path(__file__).resolve().parents[2] / "assets" / "audio" / "confirm_beep.wav"

# How many books a LONG press moves at once on the selection screen -- same
# rationale/provisional-ness as speech_controller.py's _BURST_STEP_COUNT
# (firmware reports one SHORT/LONG event per press-release cycle, no "still
# held" signal, so this is a software-side batch move, not true hold-to-repeat).
_BURST_STEP_COUNT = 5


def list_books(server: str, api_key: str) -> list[dict[str, Any]]:
    """GET /datapacks, returning its richer `books` list (book_id/title/
    title_audio_ref) -- see server/combined_server.py."""
    request = urllib.request.Request(f"{server.rstrip('/')}/datapacks", headers={"X-API-Key": api_key})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())["books"]


class SelectionScreen:
    """Client-side-only browsing state -- see module docstring for why this
    can't be a server session. Bounded (clamped) index movement, matching
    `document_navigator.py`'s "stop at the edge, don't wrap" convention."""

    def __init__(self, books: list[dict[str, Any]]):
        if not books:
            raise ValueError("서버에 저장된 데이터팩이 없습니다 -- 먼저 이미지를 업로드하세요.")
        self._books = books
        self.index = 0

    @property
    def current_book(self) -> dict[str, Any]:
        return self._books[self.index]

    def move(self, button: str, steps: int = 1) -> bool:
        """Returns whether the index actually changed (already at the edge
        counts as no-op, matching document_navigator's boundary convention
        -- callers use this to decide whether to re-announce)."""
        before = self.index
        if button == "DOWN":
            self.index = min(self.index + steps, len(self._books) - 1)
        elif button == "UP":
            self.index = max(self.index - steps, 0)
        return self.index != before


def _speak_title(book: dict[str, Any], player: AudioPlayer | None, log: Callable[[str], None]) -> None:
    log(f"[selecting] {book['title']!r} ({book['book_id']})")
    if player is None or book.get("title_audio_ref") is None:
        return
    try:
        player.play(book["title_audio_ref"])
    except Exception as exc:  # noqa: BLE001 -- best-effort, same rationale as emit_response
        log(f"title audio playback failed for {book['title_audio_ref']!r}: {exc}")


def _play_confirm_beep(player: AudioPlayer | None, log: Callable[[str], None]) -> None:
    if player is None:
        return
    try:
        player.play(str(CONFIRM_BEEP_PATH))
    except Exception as exc:  # noqa: BLE001
        log(f"confirm beep playback failed: {exc}")


def run_selecting_screen(
    books: list[dict[str, Any]],
    transport: LineTransport,
    player: AudioPlayer | None,
    log: Callable[[str], None] = print,
) -> str | None:
    """Datapack selection loop: UP/DOWN browse (LONG bursts several books),
    CONFIRM SHORT picks the current one. Everything else is ignored, not
    treated as an error -- LEFT/RIGHT/PAGE_NEXT etc. aren't meaningful here.
    Returns the chosen book_id, or None if the transport closed for good
    (caller should stop entirely)."""
    screen = SelectionScreen(books)
    _speak_title(screen.current_book, player, log)

    while True:
        line = transport.read_line()
        if line is None:
            return None
        line = line.strip()
        if not line:
            continue
        if line == "HELLO":
            # No server state exists yet on this screen -- HELLO just means
            # "re-announce whatever is currently highlighted".
            _speak_title(screen.current_book, player, log)
            continue

        command = parse_nav_line(line)
        if command is None:
            log(f"RX {line!r} -> not HELLO or a valid NAV line, ignored")
            continue

        if command.button in ("UP", "DOWN"):
            steps = _BURST_STEP_COUNT if command.action == "LONG" else 1
            if screen.move(command.button, steps):
                _speak_title(screen.current_book, player, log)
            continue

        if command.button == "CONFIRM" and command.action == "SHORT":
            _play_confirm_beep(player, log)
            return screen.current_book["book_id"]

        log(f"RX {command.button} {command.action} -> not meaningful on the selection screen, ignored")


def run_reading_screen(
    remote: RemoteSession,
    transport: LineTransport,
    player: AudioPlayer | None,
    log: Callable[[str], None] = print,
) -> bool:
    """Normal navigation, mirroring `pi_bridge.run_bridge`'s line loop,
    except CONFIRM LONG returns to the selection screen instead of being
    forwarded to the server. Speaks the session's current item immediately
    on entry -- unlike `run_bridge`, which waits for the STM's own boot-time
    HELLO handshake, this loop is entered repeatedly (every time the user
    returns from the selection screen), and nothing re-sends a fresh HELLO
    on a mere screen transition. Returns True if CONFIRM LONG triggered a
    return to selection, False if the transport closed for good."""
    emit_response(remote.get_current(), transport, player, log)

    while True:
        line = transport.read_line()
        if line is None:
            return False
        line = line.strip()
        if not line:
            continue

        if line == "HELLO":
            emit_response(remote.get_current(), transport, player, log)
            continue

        command = parse_nav_line(line)
        if command is None:
            log(f"RX {line!r} -> not HELLO or a valid NAV line, ignored")
            continue

        if command.button == "CONFIRM" and command.action == "LONG":
            log("RX CONFIRM LONG -> returning to datapack selection")
            return True

        result = remote.send_command(command.button, command.action)
        emit_response(result, transport, player, log)


def run_device_flow(
    server: str,
    api_key: str,
    transport: LineTransport,
    player: AudioPlayer | None,
    session_id: str = "stm-bridge",
    viewport_size: int = 10,
    log: Callable[[str], None] = print,
    list_books_fn: Callable[[str, str], list[dict[str, Any]]] = list_books,
    remote_session_factory: Callable[..., RemoteSession] = HttpRemoteSession,
) -> None:
    """Top-level loop: selection screen -> reading screen -> (CONFIRM LONG)
    -> selection screen -> ..., until the transport closes for good.
    `list_books_fn`/`remote_session_factory` are injected (not hardcoded
    HTTP calls) purely for testability -- see test_device_flow.py."""
    while True:
        books = list_books_fn(server, api_key)
        book_id = run_selecting_screen(books, transport, player, log)
        if book_id is None:
            return

        remote = remote_session_factory(server, api_key, session_id, book_id, viewport_size)
        returned_to_selection = run_reading_screen(remote, transport, player, log)
        if not returned_to_selection:
            return
