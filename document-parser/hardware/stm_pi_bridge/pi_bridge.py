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
import urllib.error
import urllib.request
from typing import Any, Callable, Protocol

from document_parser.accessibility import NavigationCommand

# Must match BRAILLE_CELL_COUNT in main.c exactly.
BRAILLE_CELL_COUNT = 10

_DIRECTION_TO_BUTTON = {"U": "UP", "D": "DOWN", "L": "LEFT", "R": "RIGHT"}
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
        """Current {"state": {...}, "braille_frame": {...}}, no navigation
        applied -- the HELLO case."""
        ...

    def send_command(self, button: str, action: str) -> dict[str, Any]:
        """Same shape, after the server handles this one button press."""
        ...


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


def run_bridge(remote: RemoteSession, transport: LineTransport, log: Callable[[str], None] = print) -> None:
    """Main line-protocol loop. `HELLO` -> fetch the current state/frame
    from the server (no navigation advance) and reply. `NAV,...` -> send
    that button press to the server, reply with the resulting state/frame.
    Anything else (including malformed NAV lines) is logged and ignored,
    never guessed at -- main.c never sends anything outside these two
    shapes, so seeing one means something upstream is wrong and should be
    visible in the log, not silently patched over.
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
            transport.write_line(format_frame_line(current["state"], current["braille_frame"]))
            continue

        command = parse_nav_line(line)
        if command is None:
            log(f"RX {line!r} -> not HELLO or a valid NAV line, ignored")
            continue

        log(f"RX {line!r} -> {command.button} {command.action}")
        result = remote.send_command(command.button, command.action)
        transport.write_line(format_frame_line(result["state"], result["braille_frame"]))


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, help="Serial device for the paired HC-05 (e.g. COM5 on Windows, /dev/rfcomm0 on Linux).")
    parser.add_argument("--baudrate", type=int, default=9600, help="Must match HC05_UART_BAUD in main.c.")
    parser.add_argument("--server", required=True, help="URL of a running document_parser.server.http_server (LAN address or tunnel URL).")
    parser.add_argument("--api-key", required=True, help="Must match the running server's --api-key.")
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--session-id", default="stm-bridge", help="Only matters if the server ever serves more than one board.")
    args = parser.parse_args(argv)

    remote = HttpRemoteSession(args.server, args.api_key, args.session_id, args.book_id, viewport_size=BRAILLE_CELL_COUNT)
    transport = SerialLineTransport(args.port, baudrate=args.baudrate)
    print(f"bridging {args.port} <-> {args.server} (book={args.book_id!r}, session={args.session_id!r}, viewport_size={BRAILLE_CELL_COUNT})", flush=True)
    try:
        run_bridge(remote, transport)
    finally:
        transport.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
