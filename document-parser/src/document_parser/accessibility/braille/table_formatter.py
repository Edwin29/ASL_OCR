"""Table cell -> "열(column) -> 행(row) -> 값(value)" logical braille buffer
(plan document §9.3) -- the same order the speech layer already uses
(`speech.table_rules.table_cell_announcement`).

Column/row numbers are always safe to encode (digits only). A TEXT-kind cell
value goes through `CharacterBrailleTranslator` and will raise
`NotImplementedError` for anything beyond plain digits/Hangul syllables until
more of the 2024 규정 is verified -- that surfaces missing coverage instead of
hiding it.

A MATH-kind cell value (VL wrapped the content in `$...$`, e.g. a bare number
or sign in a 함수값/부호표) is only rendered when its AST is a single leaf
node (`Number`/`Operator`/`Identifier`) -- those already have verified,
already-used braille rules (`math_translator._node_to_braille`'s base cases).
Anything with real structure (`Relation`, `Fraction`, ...) still raises
`NotImplementedError`, deliberately: rendering it would need a scoped-scroll
design decision for long formulas inside a cell that hasn't been made yet
(see docs/datapack-schema.md's braille gaps note).
"""

from __future__ import annotations

from typing import Any

from document_parser.accessibility.braille.cell_encoding import (
    BrailleCell,
    CharacterBrailleTranslator,
    RegulationBrailleTranslator,
)
from document_parser.accessibility.braille.math_translator import math_focus_item_to_braille

_DEFAULT_TRANSLATOR = RegulationBrailleTranslator()

# AST node types with no children -- safe to render as a table cell value
# without deciding how a long, structured formula (Fraction, Relation, ...)
# should scroll inside a cell. See math_translator._node_to_braille's base
# cases: these three types are exactly the ones handled without recursion.
_LEAF_MATH_AST_TYPES = frozenset({"Number", "Operator", "Identifier"})


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
        ast = node.get("presentation_ast")
        ast_type = ast.get("type") if isinstance(ast, dict) else None
        if ast_type in _LEAF_MATH_AST_TYPES:
            return math_focus_item_to_braille(node, translator)
        raise NotImplementedError(
            f"MATH table cell content with AST type {ast_type!r} is not a bare number/operator/"
            "identifier -- use math_translator.math_focus_item_to_braille directly, or extend "
            "_LEAF_MATH_AST_TYPES once viewport-scrolling for long formulas inside a table cell "
            "is decided."
        )
    text = str(node.get("text", ""))
    if text.isdigit():
        return translator.translate_digit(text)
    return translator.translate_hangul_syllable(text)
