"""Host <-> STM32 bridge for the physical braille display.

"Host" here means whatever computer is Bluetooth-paired with the STM
board's HC-05 module -- a real Raspberry Pi eventually, but just as well
any PC (e.g. the same Windows machine a teammate already uses to submit
images via remote_ingest_client.py, no file transfer needed since it's
one machine). See README.md in this folder for OS-specific pairing/COM
port setup (Windows and Linux both covered there).

Speaks the exact line-based ASCII protocol implemented by the STM32
firmware in this same folder (main.c, unmodified in behavior -- this
bridge conforms to it, not the other way around):
    Pi -> STM:  "FRAME,page,node,span,offset,gen,c0,c1,...,c9\\n"
    STM -> Pi:  "NAV,<U|D|L|R>,<S|L>\\n"  or  "HELLO\\n"

Wraps document_parser.server's existing session/navigation logic
(DatapackSession via SessionStore) completely unchanged -- this file only
translates between that Python API and the STM's line protocol. No new
navigation/braille/audio logic lives here.

CRITICAL: the physical display has exactly BRAILLE_CELL_COUNT (10) braille
cells (see main.c). document_parser.accessibility.BraillePresenter's own
default viewport size is 20 (DEFAULT_VIEWPORT_SIZE) -- this bridge MUST
request viewport_size=10 when creating the session (see main() below), or
every FRAME line sent will carry the wrong cell count and main.c's
ReceiveFrameFromPi() will reject it outright (it parses exactly
5 + BRAILLE_CELL_COUNT numeric fields, no more, no fewer).

The HELLO handshake (main.c's TryBluetoothHandshake(), sent once at boot
and on every reconnect attempt) must be answered with the session's
*current* state/frame, without advancing navigation -- it is not a button
press. That is exactly session.state / session.braille_frame, unmodified.

Usage (after pairing the HC-05 so it appears as a serial device -- an
OS-level step this script does not perform itself; README.md covers both
Windows COM ports and Linux rfcomm):
    python pi_bridge.py --port COM5 \\
        --datapacks-dir /path/to/datapacks --book-id my_book
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable, Protocol

from document_parser.accessibility import BraillePresenter, NavigationCommand
from document_parser.server import DatapackSession, SessionStore

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


def format_frame_line(state: Any, braille_frame: dict[str, Any]) -> str:
    """Build one `FRAME,page,node,span,offset,gen,c0,...,c9` line, exactly
    matching main.c's `ReceiveFrameFromPi()` parser (5 state fields, then
    exactly BRAILLE_CELL_COUNT cell values, comma-separated, no trailing
    comma). Pads with 0 (a blank cell, no dots raised) if the actual
    content is shorter than BRAILLE_CELL_COUNT (e.g. a one-symbol formula)
    -- always emits exactly BRAILLE_CELL_COUNT cells. Never emits *more*
    than that, but that guarantee only holds if the session's
    BraillePresenter was actually constructed with viewport_size=10 (see
    module docstring); this function does not itself enforce that.
    """
    cells = list(braille_frame.get("cells") or [])[:BRAILLE_CELL_COUNT]
    cells += [0] * (BRAILLE_CELL_COUNT - len(cells))
    fields = [
        "FRAME",
        str(state.page_index),
        str(state.node_index),
        str(state.math_span_index),
        str(state.braille_offset),
        str(state.generation),
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


def run_bridge(session: DatapackSession, transport: LineTransport, log: Callable[[str], None] = print) -> None:
    """Main line-protocol loop. `HELLO` -> reply with the current
    state/frame, no navigation advance. `NAV,...` -> handle_button, then
    reply with the resulting state/frame. Anything else (including
    malformed NAV lines) is logged and ignored, never guessed at --
    main.c never sends anything outside these two shapes, so seeing one
    means something upstream is wrong and should be visible in the log,
    not silently patched over.
    """
    while True:
        line = transport.read_line()
        if line is None:
            return  # transport closed for good
        line = line.strip()
        if not line:
            continue  # e.g. a read timeout with nothing pending

        if line == "HELLO":
            log(f"RX {line!r} -> replying with current state (no advance)")
            transport.write_line(format_frame_line(session.state, session.braille_frame))
            continue

        command = parse_nav_line(line)
        if command is None:
            log(f"RX {line!r} -> not HELLO or a valid NAV line, ignored")
            continue

        log(f"RX {line!r} -> {command.button} {command.action}")
        result = session.handle_button(command)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", required=True, help="Serial device for the paired HC-05 (e.g. COM5 on Windows, /dev/rfcomm0 on Linux).")
    parser.add_argument("--baudrate", type=int, default=9600, help="Must match HC05_UART_BAUD in main.c.")
    parser.add_argument("--datapacks-dir", type=Path, required=True)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--session-id", default="stm-bridge", help="Only matters if this bridge ever serves more than one board.")
    args = parser.parse_args(argv)

    store = SessionStore(args.datapacks_dir)
    session = store.get_or_create_session(
        args.session_id,
        args.book_id,
        braille_presenter=BraillePresenter(viewport_size=BRAILLE_CELL_COUNT),
    )

    transport = SerialLineTransport(args.port, baudrate=args.baudrate)
    print(f"listening on {args.port} @ {args.baudrate} baud, book={args.book_id!r}, viewport_size={BRAILLE_CELL_COUNT}", flush=True)
    try:
        run_bridge(session, transport)
    finally:
        transport.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
