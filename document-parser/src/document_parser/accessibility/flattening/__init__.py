"""Turns a validated Page IR document into an AccessibleDocument with
exactly-once content consumption (the plan document's AccessibilityTreeFlattener)."""

from document_parser.accessibility.flattening.structure_nodes import (
    classify_ast_status,
    flatten_document,
    flatten_page,
)

__all__ = [
    "classify_ast_status",
    "flatten_document",
    "flatten_page",
]
