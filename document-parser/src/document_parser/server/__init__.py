"""Scenario B (serving): drives a live navigation session over an already-
loaded `Datapack`, reusing `SpeechController`/`BraillePresenter` unchanged.
See docs/datapack-schema.md for why only navigation stays live (OCR and TTS
are precomputed by `document_parser.datapack.ingest`).

`http_server.py` is the real transport: an HTTP server wrapping
`handle_wire_command()`/`SessionStore` so a host device with no local
datapack storage (e.g. hardware/stm_pi_bridge/pi_bridge.py) can drive a
session over the network. Not imported here (like `cli.py`) to avoid the
`python -m document_parser.server.http_server` double-import warning --
import it directly, `from document_parser.server.http_server import ...`.
"""

from __future__ import annotations

from document_parser.server.session import DatapackSession, DatapackTtsEngineAdapter
from document_parser.server.store import SessionStore
from document_parser.server.wire import (
    audio_to_wire,
    command_from_wire,
    handle_wire_command,
    result_to_wire,
    state_to_wire,
)

__all__ = [
    "DatapackSession",
    "DatapackTtsEngineAdapter",
    "SessionStore",
    "audio_to_wire",
    "command_from_wire",
    "handle_wire_command",
    "result_to_wire",
    "state_to_wire",
]
