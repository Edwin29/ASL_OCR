"""Pure functions converting flattened focus items into Korean utterance
strings. No TTS engine dependency -- see `accessibility.adapters.tts_engine`
for that boundary."""

from document_parser.accessibility.speech.math_rules import math_ast_to_speech, math_focus_item_to_speech
from document_parser.accessibility.speech.table_rules import table_cell_announcement, table_entry_announcement
from document_parser.accessibility.speech.text_rules import (
    describe_content_nodes,
    text_focus_item_to_speech,
    visual_focus_item_to_speech,
)

__all__ = [
    "describe_content_nodes",
    "math_ast_to_speech",
    "math_focus_item_to_speech",
    "table_cell_announcement",
    "table_entry_announcement",
    "text_focus_item_to_speech",
    "visual_focus_item_to_speech",
]
