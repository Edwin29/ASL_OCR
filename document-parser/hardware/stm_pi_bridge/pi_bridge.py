"""Host <-> STM32 bridge for the physical braille display.

"Host" here means whatever computer is Bluetooth-paired with the STM
board's HC-05 module -- a real Raspberry Pi eventually, but just as well
any PC (e.g. the same Windows machine a teammate already uses to submit
images via remote_ingest_client.py). See README.md in this folder for
OS-specific pairing/COM port setup (Windows and Linux both covered there).

**The host holds no datapack of its own.** Every "FRAME,..." line sent to
the STM is fetched live, over HTTP, from `document_parser.server.http_server`
running on the GPU machine that actually has the datapacks. This bridge is
a pure protocol translator between two wire formats -- the STM's line
protocol and the server's HTTP/JSON one -- with no navigation/braille
state of its own in between. (An earlier revision of this file read a
locally-downloaded datapack directly; that assumed the host device had its
own storage, which the real demo setup doesn't have -- see git history if
you need that version for offline bench testing.)

Speaks the exact line-based ASCII protocol implemented by the STM32
firmware in this same folder (main.c, unmodified in behavior -- this
bridge conforms to it, not the other way around):
    Host -> STM:  "FRAME,page,node,span,offset,gen,c0,c1,...,c9\\n"
    STM -> Host:  "NAV,<U|D|L|R>,<S|L>\\n"  or  "HELLO\\n"

CRITICAL: the physical display has exactly BRAILLE_CELL_COUNT (10) braille
cells (see main.c). document_parser's BraillePresenter defaults to a
20-cell viewport -- this bridge requests viewport_size=10 when it creates
the remote session (see main() below), or every FRAME line sent would
carry the wrong cell count and main.c's ReceiveFrameFromPi() would reject
it outright (parses exactly 5 + BRAILLE_CELL_COUNT numeric fields).

The HELLO handshake (main.c's TryBluetoothHandshake(), sent once at boot
and on every reconnect attempt) is answered with the session's *current*
state/frame, fetched via GET (no navigation advance) -- it is not a
button press.

**Audio playback is triggered from this same response**, right after the
FRAME line is sent for it (see `_emit()`), never separately -- this is what
guarantees the display and whatever is playing always correspond to the
same content: there is no second code path that could react to a stale or
different state. `audio_ref` in that response is a path on the GPU server's
filesystem (see document_parser/server/wire.py's module docstring on why --
byte-level audio delivery across machines is still an open design
question), so this only actually plays sound today when this host can
reach that path (typically: server and bridge on the same machine, e.g.
local bench testing). On a different machine it just logs and moves on --
see `--no-audio` to silence that log noise, or WinsoundAudioPlayer for the
one playback backend implemented so far (Windows only).

Usage (after pairing the HC-05 so it appears as a serial device -- an
OS-level step this script does not perform itself; README.md covers both
Windows COM ports and Linux rfcomm; the server must already be running,
see ../../src/document_parser/server/http_server.py):
    python pi_bridge.py --port COM5 \\
        --server https://<tunnel-or-LAN-address> --api-key <shared secret> \\
        --book-id my_book
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Protocol

from document_parser.accessibility import NavigationCommand

# Must match BRAILLE_CELL_COUNT in main.c exactly.
BRAILLE_CELL_COUNT = 10

# "N"/"P" (next/previous page) are placeholders for the two dedicated
# page-turn buttons -- swap these for whatever single letters the firmware
# team's NAV,<letter>,<S|L> protocol actually ends up sending once that
# hardware exists; nothing else in this file needs to change to match.
_DIRECTION_TO_BUTTON = {
    "U": "UP", "D": "DOWN", "L": "LEFT", "R": "RIGHT",
    "N": "PAGE_NEXT", "P": "PAGE_PREVIOUS",
}
_LENGTH_TO_ACTION = {"S": "SHORT", "L": "LONG"}


class LineTransport(Protocol):
    """Whatever actually talks to the STM over serial/Bluetooth -- kept as
    a narrow protocol so the line-handling logic below is testable without
    a real serial port or physical board attached (see test_pi_bridge.py's
    FakeTransport)."""

    def read_line(self) -> str | None:
        """One line, without the trailing newline. `None` means the
        transport closed for good (main loop should exit); an empty
        string means "nothing arrived, try again" (e.g. a read timeout),
        which is not the same thing."""
        ...

    def write_line(self, line: str) -> None: ...


class RemoteSession(Protocol):
    """Whatever actually talks to document_parser.server.http_server --
    kept as a narrow protocol (implemented for real by HttpRemoteSession
    below) so the line-handling logic is testable without a real server or
    network connection (see test_pi_bridge.py's FakeRemoteSession)."""

    def get_current(self) -> dict[str, Any]:
        """Current {"state": {...}, "braille_frame": {...}, "audio": {...}
        or None}, no navigation applied -- the HELLO case."""
        ...

    def send_command(self, button: str, action: str) -> dict[str, Any]:
        """Same shape, after the server handles this one button press."""
        ...


class AudioPlayer(Protocol):
    """Plays one WAV file, referenced by local filesystem path. Kept as a
    narrow protocol (like LineTransport/RemoteSession) so run_bridge's
    playback-trigger logic is testable without a real sound device (see
    test_pi_bridge.py's FakeAudioPlayer)."""

    def play(self, wav_path: str) -> None:
        """Start playback and return immediately -- must not block the
        bridge's line loop."""
        ...


class WinsoundAudioPlayer:
    """Real AudioPlayer for Windows hosts -- the only OS this bridge has
    actually been run on so far (see README.md's verification status).
    Uses `winsound` (standard library, no extra install) rather than a
    cross-platform audio package, since every host tested so far is
    Windows; a Linux/real-Raspberry-Pi AudioPlayer is future work.

    Checks the path exists before handing it to `winsound.PlaySound` and
    raises `FileNotFoundError` if not -- verified on this machine that
    `PlaySound` itself does *not* raise for a missing file (with or
    without SND_ASYNC), it just silently plays nothing. Without this
    check, a stale/unreachable `audio_ref` (the common case when the
    bridge and server aren't on the same machine -- see module docstring)
    would fail completely silently instead of being logged by `_emit()`.
    """

    def __init__(self) -> None:
        import winsound  # stdlib, Windows-only -- deferred so import stays optional

        self._winsound = winsound

    def play(self, wav_path: str) -> None:
        if not os.path.isfile(wav_path):
            raise FileNotFoundError(f"no such file: {wav_path!r} (winsound.PlaySound fails silently on this, not loudly)")
        self._winsound.PlaySound(wav_path, self._winsound.SND_FILENAME | self._winsound.SND_ASYNC)


def format_frame_line(state: dict[str, Any], braille_frame: dict[str, Any]) -> str:
    """Build one `FRAME,page,node,span,offset,gen,c0,...,c9` line, exactly
    matching main.c's `ReceiveFrameFromPi()` parser (5 state fields, then
    exactly BRAILLE_CELL_COUNT cell values, comma-separated, no trailing
    comma). `state` is the wire-format dict document_parser.server.wire's
    state_to_wire() produces (this bridge only ever sees state as JSON from
    the HTTP server, never a real NavigationState object). Pads with 0 (a
    blank cell, no dots raised) if the actual content is shorter than
    BRAILLE_CELL_COUNT (e.g. a one-symbol formula) -- always emits exactly
    BRAILLE_CELL_COUNT cells. Never emits *more* than that, but that
    guarantee only holds if the session was actually created with
    viewport_size=10 (see module docstring); this function does not itself
    enforce that.
    """
    cells = list(braille_frame.get("cells") or [])[:BRAILLE_CELL_COUNT]
    cells += [0] * (BRAILLE_CELL_COUNT - len(cells))
    fields = [
        "FRAME",
        str(state["page_index"]),
        str(state["node_index"]),
        str(state["math_span_index"]),
        str(state["braille_offset"]),
        str(state["generation"]),
        *(str(c) for c in cells),
    ]
    return ",".join(fields)


def parse_nav_line(line: str) -> NavigationCommand | None:
    """Parse one `NAV,<U|D|L|R>,<S|L>` line into a NavigationCommand.
    Returns `None` for anything that isn't exactly that shape (including
    "HELLO", which the caller handles separately) -- never guesses at a
    malformed line."""
    parts = line.split(",")
    if len(parts) != 3 or parts[0] != "NAV":
        return None
    button = _DIRECTION_TO_BUTTON.get(parts[1])
    action = _LENGTH_TO_ACTION.get(parts[2])
    if button is None or action is None:
        return None
    return NavigationCommand(button=button, action=action)


def run_bridge(
    remote: RemoteSession,
    transport: LineTransport,
    log: Callable[[str], None] = print,
    player: AudioPlayer | None = None,
) -> None:
    """Main line-protocol loop. `HELLO` -> fetch the current state/frame
    from the server (no navigation advance) and reply. `NAV,...` -> send
    that button press to the server, reply with the resulting state/frame.
    Anything else (including malformed NAV lines) is logged and ignored,
    never guessed at -- main.c never sends anything outside these two
    shapes, so seeing one means something upstream is wrong and should be
    visible in the log, not silently patched over.

    Every response -- HELLO's snapshot or a NAV command's result -- carries
    its own `audio` alongside `state`/`braille_frame` (see wire.py's
    `audio_to_wire`: `None` for a silent braille-only scroll, otherwise the
    text this exact response's braille frame corresponds to). If `player`
    is given, that audio is triggered right here, from that same response,
    right after the FRAME line for it is sent -- this is what guarantees
    "whatever the display just showed is what's playing", per the display/
    audio consistency requirement: there is no separate audio pipeline that
    could end up reacting to a different, later state.
    """
    while True:
        line = transport.read_line()
        if line is None:
            return  # transport closed for good
        line = line.strip()
        if not line:
            continue  # e.g. a read timeout with nothing pending

        if line == "HELLO":
            log(f"RX {line!r} -> fetching current state from server (no advance)")
            current = remote.get_current()
            _emit(current, transport, player, log)
            continue

        command = parse_nav_line(line)
        if command is None:
            log(f"RX {line!r} -> not HELLO or a valid NAV line, ignored")
            continue

        log(f"RX {line!r} -> {command.button} {command.action}")
        result = remote.send_command(command.button, command.action)
        _emit(result, transport, player, log)


def _emit(
    result: dict[str, Any],
    transport: LineTransport,
    player: AudioPlayer | None,
    log: Callable[[str], None],
) -> None:
    frame_line = format_frame_line(result["state"], result["braille_frame"])
    transport.write_line(frame_line)
    log(f"TX {frame_line!r}")
    audio = result.get("audio")
    if audio is None or player is None:
        return
    wav_path = audio["audio_ref"]
    try:
        player.play(wav_path)
    except Exception as exc:  # noqa: BLE001 -- best-effort: audio_ref is a
        # server-local path (see wire.py's module docstring); it only
        # resolves to a real file when this host can reach the server's
        # filesystem. A missing/unplayable file must never stop the
        # braille display (already sent above) from working.
        log(f"audio playback failed for {wav_path!r}: {exc}")


class SerialLineTransport:
    """Real transport: a pyserial connection to the STM's Bluetooth serial
    port. Requires the `pyserial` package (not a core document-parser
    dependency; install it separately: `pip install pyserial`). Pairing
    the HC-05 so it shows up as a serial device at all (a Windows COM
    port or a Linux device like `/dev/rfcomm0` -- see README.md) is an
    OS-level Bluetooth step this class does not perform."""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0) -> None:
        import serial  # deferred: optional dependency, only needed for real hardware use

        self._conn = serial.Serial(port, baudrate=baudrate, timeout=timeout)

    def read_line(self) -> str | None:
        raw = self._conn.readline()  # returns b"" on timeout, not closed
        return raw.decode("utf-8", errors="replace")

    def write_line(self, line: str) -> None:
        self._conn.write((line + "\n").encode("utf-8"))

    def close(self) -> None:
        self._conn.close()


class HttpRemoteSession:
    """Real RemoteSession: talks to a running document_parser.server.http_server
    over HTTP. Uses only the standard library (urllib), matching
    remote_ingest_client.py's no-extra-installs philosophy for this file's
    own dependencies -- `pi_bridge.py` as a whole still needs the full
    document_parser package installed (for NavigationCommand and, if you
    swap in SerialLineTransport, pyserial), unlike remote_ingest_client.py.

    Creates the session (POST /sessions) once, at construction time, and
    reuses `session_id` for every subsequent call.
    """

    def __init__(self, server: str, api_key: str, session_id: str, book_id: str, viewport_size: int) -> None:
        self._server = server.rstrip("/")
        self._api_key = api_key
        self._session_id = session_id
        self._request("POST", "/sessions", {"session_id": session_id, "book_id": book_id, "viewport_size": viewport_size})

    def get_current(self) -> dict[str, Any]:
        return self._request("GET", f"/sessions/{self._session_id}")

    def send_command(self, button: str, action: str) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{self._session_id}/command", {"button": button, "action": action})

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self._server}{path}", data=data, method=method,
            headers={"X-API-Key": self._api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {body_text}") from exc


def build_default_audio_player(log: Callable[[str], None]) -> AudioPlayer | None:
    """Best-effort AudioPlayer for whatever this host actually is. Shared
    with test_client.py's console-simulated mode so both entry points pick
    the same backend the same way."""
    try:
        return WinsoundAudioPlayer()
    except ImportError:
        log("winsound unavailable on this OS -- audio playback disabled, braille display continues normally")
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, help="Serial device for the paired HC-05 (e.g. COM5 on Windows, /dev/rfcomm0 on Linux).")
    parser.add_argument("--baudrate", type=int, default=9600, help="Must match HC05_UART_BAUD in main.c.")
    parser.add_argument("--server", required=True, help="URL of a running document_parser.server.http_server (LAN address or tunnel URL).")
    parser.add_argument("--api-key", required=True, help="Must match the running server's --api-key.")
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--session-id", default="stm-bridge", help="Only matters if the server ever serves more than one board.")
    parser.add_argument(
        "--no-audio", action="store_true",
        help="Skip audio playback entirely (braille-only). Useful when the server and this "
             "host are on different machines, since audio_ref then never resolves to a local "
             "file and every turn would otherwise log a playback failure.",
    )
    args = parser.parse_args(argv)

    remote = HttpRemoteSession(args.server, args.api_key, args.session_id, args.book_id, viewport_size=BRAILLE_CELL_COUNT)
    transport = SerialLineTransport(args.port, baudrate=args.baudrate)
    player = None if args.no_audio else build_default_audio_player(print)
    print(
        f"bridging {args.port} <-> {args.server} (book={args.book_id!r}, session={args.session_id!r}, "
        f"viewport_size={BRAILLE_CELL_COUNT}, audio={'off' if player is None else 'on'})",
        flush=True,
    )
    try:
        run_bridge(remote, transport, player=player)
    finally:
        transport.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
