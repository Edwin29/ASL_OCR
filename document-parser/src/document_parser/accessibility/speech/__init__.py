"""Pure functions converting flattened focus items into Korean utterance
strings. No TTS engine dependency -- see `accessibility.adapters.tts_engine`
for that boundary."""

from typing import Any

from document_parser.accessibility.speech.math_rules import math_ast_to_speech, math_focus_item_to_speech
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
        return text_focus_item_to_speech(item)
    if kind == "MATH":
        return math_focus_item_to_speech(item)
    if kind == "TABLE":
        return table_entry_announcement(item)
    if kind == "UNSUPPORTED_VISUAL":
        return visual_focus_item_to_speech(item)
    return str(item.get("text", ""))


__all__ = [
    "describe_content_nodes",
    "focus_item_announcement",
    "math_ast_to_speech",
    "math_focus_item_to_speech",
    "table_cell_announcement",
    "table_entry_announcement",
    "text_focus_item_to_speech",
    "visual_focus_item_to_speech",
]
