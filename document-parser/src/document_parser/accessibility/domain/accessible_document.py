"""Builders for the AccessibleDocument shape consumed by TTS/braille presenters.

Kept as plain dict builders (not a parallel dataclass model) to match how the
rest of the Page IR pipeline already represents its output -- see
`document_parser.structure.problem_units.build_problem_unit_node` and
`document_parser.serialization.table_html.build_table_ir` for the same
pattern. This keeps AccessibleDocument trivially JSON-serializable for fixture
comparisons in tests.
"""

from __future__ import annotations

from typing import Any

FOCUS_KINDS = ("TEXT", "MATH", "TABLE", "UNSUPPORTED_VISUAL", "UNKNOWN")


def build_focus_item(
    item_id: str,
    kind: str,
    page_id: str,
    reading_index: int,
    source_node_ids: list[str],
    confidence: float = 0.0,
    issues: list[dict[str, object]] | None = None,
    source_bbox: list[float] | None = None,
    **kind_fields: Any,
) -> dict[str, object]:
    """Build one focus item. `kind_fields` carries kind-specific data (e.g.
    `raw_formula`/`presentation_ast`/`ast_status` for MATH, `row_count`/
    `column_count`/`cells` for TABLE) merged in at the top level, matching the
    plan document's JSON examples.
    """
    if kind not in FOCUS_KINDS:
        raise ValueError(f"Unknown focus item kind: {kind!r}")
    item: dict[str, object] = {
        "id": item_id,
        "kind": kind,
        "page_id": page_id,
        "reading_index": reading_index,
        "confidence": confidence,
        "issues": list(issues) if issues else [],
        "source_node_ids": list(source_node_ids),
    }
    if source_bbox is not None:
        item["source_bbox"] = source_bbox
    item.update(kind_fields)
    return item


def build_page(page_id: str, focus_items: list[dict[str, object]]) -> dict[str, object]:
    return {"page_id": page_id, "focus_items": focus_items}


def build_accessible_document(
    document_id: str,
    pages: list[dict[str, object]],
    issues: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    global_reading_order = [
        str(item["id"])
        for page in pages
        for item in page["focus_items"]
    ]
    return {
        "document_id": document_id,
        "pages": pages,
        "global_reading_order": global_reading_order,
        "issues": list(issues) if issues else [],
    }
