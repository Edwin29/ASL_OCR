"""Pure navigation logic over an AccessibleDocument -- document-mode and
table-mode movement, independent of any TTS/braille/hardware wiring."""

from document_parser.accessibility.application.document_navigator import (
    current_focus_item,
    handle_command as handle_document_command,
    move_braille_cursor,
    next_node,
    previous_node,
)
from document_parser.accessibility.application.table_navigator import (
    can_enter_table,
    current_cell,
    enter_table,
    exit_table,
    move as move_table_cursor,
    move_table_braille_cursor,
)
from document_parser.accessibility.application.speech_controller import SpeechController

__all__ = [
    "SpeechController",
    "can_enter_table",
    "current_cell",
    "current_focus_item",
    "enter_table",
    "exit_table",
    "handle_document_command",
    "move_braille_cursor",
    "move_table_braille_cursor",
    "move_table_cursor",
    "next_node",
    "previous_node",
]
