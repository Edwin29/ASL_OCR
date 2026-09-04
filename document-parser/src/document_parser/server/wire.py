"""Wire-format boundary between `DatapackSession`'s Python objects and
whatever transport eventually carries them -- HTTP, WebSocket, serial, none
of that is decided yet, and picking one needs real hardware experiments
first. Every transport experiment should go through `handle_wire_command`
rather than calling `DatapackSession` directly, so trying (or switching, or
running several side by side during testing) a transport never means
touching session/navigation logic again.

The wire format is plain JSON-safe dicts in both directions. Audio is
represented by a reference (`audio_ref`, the wav file's absolute path), not
raw bytes -- how bytes actually reach a client (an HTTP response body, a
WebSocket binary frame, a serial chunk) is exactly the kind of
transport-specific decision this boundary deliberately stays out of.
"""

from __future__ import annotations

from typing import Any

from document_parser.accessibility import NavigationCommand, NavigationState
from document_parser.server.session import DatapackSession

BUTTONS = ("UP", "DOWN", "LEFT", "RIGHT", "PAGE_NEXT", "PAGE_PREVIOUS", "CONFIRM")
ACTIONS = ("SHORT",)


def command_from_wire(payload: dict[str, Any]) -> NavigationCommand:
    """Parse one wire command, e.g. `{"button": "RIGHT", "action": "SHORT"}`.
    Raises `ValueError` (a wire-safe, client-error condition) on malformed
    input -- never lets a bad button string reach `NavigationCommand`
    un-checked, since that's attacker/typo-controlled input once a real
    transport exists."""
    button = payload.get("button")
    action = payload.get("action", "SHORT")
    if button not in BUTTONS:
        raise ValueError(f"Unknown button {button!r}; expected one of {BUTTONS}")
    if action not in ACTIONS:
        raise ValueError(f"Unknown action {action!r}; expected one of {ACTIONS}")
    return NavigationCommand(button=button, action=action)


def state_to_wire(state: NavigationState) -> dict[str, Any]:
    return {
        "document_id": state.document_id,
        "page_index": state.page_index,
        "node_index": state.node_index,
        "mode": state.mode,
        "table_row": state.table_row,
        "table_column": state.table_column,
        "braille_offset": state.braille_offset,
        "math_span_index": state.math_span_index,
        "generation": state.generation,
    }


def audio_to_wire(audio: dict[str, Any] | None) -> dict[str, Any] | None:
    if audio is None:
        return None
    return {
        "text": audio["text"],
        "audio_ref": audio["wav"],
        "duration_ms": audio["duration_ms"],
        "sample_rate": audio["sample_rate"],
    }


def result_to_wire(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": state_to_wire(result["state"]),
        "braille_frame": result["braille_frame"],  # already JSON-safe, see viewport.build_frame/clear_frame
        "audio": audio_to_wire(result["audio"]),
    }


def handle_wire_command(session: DatapackSession, payload: dict[str, Any]) -> dict[str, Any]:
    """THE stable integration point: any transport parses its bytes into a
    `payload` dict, calls this, and serializes the returned dict back out.
    Malformed input produces a wire-safe `{"error": "..."}` dict instead of
    raising, so a transport layer never needs its own try/except around
    this call -- only around getting bytes to and from it.
    """
    try:
        command = command_from_wire(payload)
    except ValueError as exc:
        return {"error": str(exc)}
    result = session.handle_button(command)
    return result_to_wire(result)
