"""Table cell -> "열(column) -> 행(row) -> 값(value)" logical braille buffer
(plan document §9.3) -- the same order the speech layer already uses
(`speech.table_rules.table_cell_announcement`).

Column/row numbers are always safe to encode (digits only). The cell value
goes through `CharacterBrailleTranslator` and will raise `NotImplementedError`
for anything beyond plain digits until more of the 2024 규정 is verified --
that surfaces missing coverage instead of hiding it.
"""

from __future__ import annotations

from typing import Any

from document_parser.accessibility.braille.cell_encoding import (
    BrailleCell,
    CharacterBrailleTranslator,
    RegulationBrailleTranslator,
)

_DEFAULT_TRANSLATOR = RegulationBrailleTranslator()


def table_cell_braille(
    cell_item: dict[str, Any], translator: CharacterBrailleTranslator = _DEFAULT_TRANSLATOR
) -> list[BrailleCell]:
    buffer: list[BrailleCell] = []
    buffer.extend(translator.translate_digit(str(cell_item["column_index"])))
    buffer.extend(translator.translate_digit(str(cell_item["row_index"])))
    for content_node in cell_item.get("content_nodes", []):
        buffer.extend(_content_node_braille(content_node, translator))
    return buffer


def _content_node_braille(node: dict[str, Any], translator: CharacterBrailleTranslator) -> list[BrailleCell]:
    if node.get("kind") == "MATH":
        # Table cell math goes through math_translator.math_focus_item_to_braille,
        # not through this module -- callers with a math cell should route there.
        raise NotImplementedError("MATH table cell content: use math_translator.math_focus_item_to_braille")
    text = str(node.get("text", ""))
    if text.isdigit():
        return translator.translate_digit(text)
    return translator.translate_hangul_syllable(text)
