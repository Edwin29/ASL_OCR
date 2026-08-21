"""Scenario B (serving): drives a live navigation session over an already-
loaded `Datapack`, reusing `SpeechController`/`BraillePresenter` unchanged.
See docs/datapack-schema.md for why only navigation stays live (OCR and TTS
are precomputed by `document_parser.datapack.ingest`).

Transport (HTTP/WebSocket/serial to the actual hardware) is not implemented
here yet -- `DatapackSession` is the transport-agnostic core a future
transport layer wraps.
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
