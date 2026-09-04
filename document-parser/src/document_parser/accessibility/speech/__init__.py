"""Pure functions converting flattened focus items into Korean utterance
strings. No TTS engine dependency -- see `accessibility.adapters.tts_engine`
for that boundary."""

from typing import Any

from document_parser.accessibility.speech.math_rules import math_ast_to_speech, math_focus_item_to_speech
from document_parser.accessibility.speech.pronunciation import normalize_tts_pronunciation
from document_parser.accessibility.speech.table_rules import table_cell_announcement, table_entry_announcement
from document_parser.accessibility.speech.text_rules import (
    describe_content_nodes,
    text_focus_item_to_speech,
    visual_focus_item_to_speech,
)


def focus_item_announcement(item: dict[str, Any]) -> str:
    """Kind -> announcement text dispatch for a focus item (item must not be
    None -- callers resolve "no current item" themselves, since that's a
    navigation-state concern, not a per-item one).

    Pulled out of `SpeechController` so the live controller and the datapack
    ingest job (which pre-synthesizes every item's TTS audio, see
    docs/datapack-schema.md) call the exact same dispatch instead of risking
    two copies drifting apart.
    """
    kind = item["kind"]
    if kind == "TEXT":
        spoken = text_focus_item_to_speech(item)
    elif kind == "MATH":
        spoken = math_focus_item_to_speech(item)
    elif kind == "TABLE":
        spoken = table_entry_announcement(item)
    elif kind == "UNSUPPORTED_VISUAL":
        spoken = visual_focus_item_to_speech(item)
    else:
        spoken = str(item.get("text", ""))
    return normalize_tts_pronunciation(spoken)


__all__ = [
    "describe_content_nodes",
    "focus_item_announcement",
    "math_ast_to_speech",
    "math_focus_item_to_speech",
    "normalize_tts_pronunciation",
    "table_cell_announcement",
    "table_entry_announcement",
    "text_focus_item_to_speech",
    "visual_focus_item_to_speech",
]
