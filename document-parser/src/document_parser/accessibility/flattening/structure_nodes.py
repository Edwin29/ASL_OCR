"""Implements the plan document's `AccessibilityTreeFlattener`: turns a
validated Page IR document into an `AccessibleDocument` where every piece of
preserved content is consumed exactly once.

The only navigable unit at the top level is one `reading_order` entry (this
keeps DOCUMENT-mode up/down at block granularity, per the plan document's
recommendation in its "원본 보존과 포커스 항목" section) -- except
`PROBLEM_UNIT` structure nodes, which carry no readable content of their own
and are expanded into one focus item per member, in role order
(problem_code/exam_source_tag -> stem -> condition -> bogi -> choices), never
re-read at the top level. TABLE cells and UNSUPPORTED_VISUAL preserved text
are nested inside their one focus item and are not separately navigable until
a caller enters table/visual mode.
"""

from __future__ import annotations

from typing import Literal

from document_parser.accessibility.adapters.page_ir_adapter import check_compatibility_profile
from document_parser.accessibility.domain.accessible_document import (
    build_accessible_document,
    build_focus_item,
    build_page,
)

AstStatus = Literal["VALID", "PARTIAL", "INVALID"]


def classify_ast_status(unconsumed_tokens: list[object], issues: list[dict[str, object]]) -> AstStatus:
    """Classify a formula's AST per the plan document's §13.1 fallback policy.

    A formula is INVALID if the parser left tokens unconsumed or raised an
    error-severity issue -- braille output must be withheld rather than shown
    as if it were trustworthy. PARTIAL means the parse fully consumed the
    input but preserved an `Unknown` node inside it (signalled by the
    `AST_UNKNOWN_NODE` info issue); the rest of the structure can still be
    presented with an uncertainty notice. Anything else is VALID.
    """
    if any(issue.get("severity") == "error" for issue in issues):
        return "INVALID"
    if unconsumed_tokens:
        return "INVALID"
    if any(issue.get("code") == "AST_UNKNOWN_NODE" for issue in issues):
        return "PARTIAL"
    return "VALID"


def flatten_document(payload: dict[str, object]) -> dict[str, object]:
    """Build an AccessibleDocument from a Page IR payload. Callers should run
    `document_parser.validation.validate_document_ir` first and refuse to
    proceed on `schema_valid: false`; this function only checks the shallow
    compatibility profile (see `adapters.page_ir_adapter`), not the schema.
    """
    check_compatibility_profile(payload)
    document_manifest = payload.get("document_manifest")
    document_id = str(document_manifest.get("book_id", "document")) if isinstance(document_manifest, dict) else "document"
    raw_pages = payload.get("pages")
    pages = [flatten_page(page) for page in raw_pages if isinstance(page, dict)] if isinstance(raw_pages, list) else []
    return build_accessible_document(document_id, pages)


def flatten_page(page: dict[str, object]) -> dict[str, object]:
    node_by_id = {
        node["node_id"]: node
        for node in page.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
    page_id = str(page.get("page_id", ""))
    reading_order = page.get("reading_order", [])

    visited: set[str] = set()
    focus_items: list[dict[str, object]] = []
    for reading_index, node_id in enumerate(reading_order if isinstance(reading_order, list) else []):
        node = node_by_id.get(node_id) if isinstance(node_id, str) else None
        if node is None:
            continue
        focus_items.extend(_flatten_node(node, node_by_id, page_id, reading_index, visited))
    return build_page(page_id, focus_items)


def _flatten_node(
    node: dict[str, object],
    node_by_id: dict[str, dict[str, object]],
    page_id: str,
    reading_index: int,
    visited: set[str],
) -> list[dict[str, object]]:
    node_id = node.get("node_id")
    if not isinstance(node_id, str) or node_id in visited:
        return []

    content_type = node.get("content_type")
    layout = node.get("layout") if isinstance(node.get("layout"), dict) else {}

    if content_type == "UNKNOWN" and layout.get("structure_label") == "PROBLEM_UNIT":
        return _flatten_problem_unit(node, node_by_id, page_id, reading_index, visited)

    visited.add(node_id)
    confidence = node.get("confidence", 0.0)
    issues = node.get("issues") if isinstance(node.get("issues"), list) else []

    if content_type == "TEXT":
        spans = node.get("spans") if isinstance(node.get("spans"), list) else []
        return [build_focus_item(
            node_id, "TEXT", page_id, reading_index, [node_id],
            confidence=confidence, issues=issues,
            spans=_flatten_spans(spans),
        )]

    if content_type == "MATH":
        unconsumed = node.get("unconsumed_tokens") if isinstance(node.get("unconsumed_tokens"), list) else []
        return [build_focus_item(
            node_id, "MATH", page_id, reading_index, [node_id],
            confidence=confidence, issues=issues,
            raw_formula=node.get("raw_formula", ""),
            presentation_ast=node.get("presentation_ast"),
            unconsumed_tokens=unconsumed,
            ast_status=classify_ast_status(unconsumed, issues),
        )]

    if content_type == "TABLE":
        cells = node.get("cells") if isinstance(node.get("cells"), list) else []
        return [build_focus_item(
            node_id, "TABLE", page_id, reading_index, [node_id],
            confidence=confidence, issues=issues,
            row_count=node.get("row_count", 0),
            column_count=node.get("column_count", 0),
            structure_confidence=node.get("structure_confidence", 0.0),
            cells=_flatten_table_cells(cells),
        )]

    if content_type == "UNSUPPORTED_VISUAL":
        embedded = node.get("embedded_content_nodes") if isinstance(node.get("embedded_content_nodes"), list) else []
        return [build_focus_item(
            node_id, "UNSUPPORTED_VISUAL", page_id, reading_index, [node_id],
            confidence=confidence, issues=issues,
            handling=node.get("handling", "ANNOUNCE_ONLY_NO_TEXT_CAPTURED"),
            preserved_content=[_describe_content_node(item) for item in embedded if isinstance(item, dict)],
        )]

    # UNKNOWN (non-PROBLEM_UNIT) or any other content type this adapter does
    # not have a dedicated branch for: preserve whatever text exists rather
    # than dropping the node, per the project's no-silent-loss rule.
    text = node.get("normalized_text") or node.get("raw_text") or ""
    return [build_focus_item(
        node_id, "UNKNOWN", page_id, reading_index, [node_id],
        confidence=confidence, issues=issues,
        text=text,
    )]


def _flatten_problem_unit(
    node: dict[str, object],
    node_by_id: dict[str, dict[str, object]],
    page_id: str,
    reading_index: int,
    visited: set[str],
) -> list[dict[str, object]]:
    layout = node["layout"]
    role_order: list[str] = []
    marker_id = layout.get("problem_marker_node_id")
    if isinstance(marker_id, str):
        role_order.append(marker_id)
    for role_field in ("stem_node_ids", "condition_node_ids", "bogi_node_ids", "choice_node_ids"):
        role_order.extend(nid for nid in layout.get(role_field, []) if isinstance(nid, str))

    # The Parser also records membership independently via `embedded_text_nodes`.
    # If the two ever disagree, prefer completeness: append anything the role
    # lists missed rather than silently dropping it.
    embedded = node.get("embedded_text_nodes")
    if isinstance(embedded, list):
        role_order.extend(nid for nid in embedded if isinstance(nid, str) and nid not in role_order)

    seen: set[str] = set()
    ordered_unique = [nid for nid in role_order if not (nid in seen or seen.add(nid))]

    items: list[dict[str, object]] = []
    for member_id in ordered_unique:
        member = node_by_id.get(member_id)
        if member is None:
            continue  # dangling reference; validate_document_ir flags this upstream
        items.extend(_flatten_node(member, node_by_id, page_id, reading_index, visited))
    return items


def _flatten_spans(spans: list[object]) -> list[dict[str, object]]:
    fragments: list[dict[str, object]] = []
    for span in spans:
        if not isinstance(span, dict):
            continue
        is_math = span.get("math_span_candidate") is True or span.get("span_type") == "MATH"
        if is_math:
            unconsumed = span.get("unconsumed_tokens") if isinstance(span.get("unconsumed_tokens"), list) else []
            ast_issues = span.get("ast_issues") if isinstance(span.get("ast_issues"), list) else []
            fragments.append({
                "kind": "MATH",
                "text": span.get("text", ""),
                "presentation_ast": span.get("presentation_ast"),
                "unconsumed_tokens": unconsumed,
                "ast_status": classify_ast_status(unconsumed, ast_issues),
            })
        else:
            fragments.append({"kind": "TEXT", "text": span.get("text", "")})
    return fragments


def _flatten_table_cells(cells: list[object]) -> list[dict[str, object]]:
    flattened: list[dict[str, object]] = []
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        content_nodes = cell.get("content_nodes") if isinstance(cell.get("content_nodes"), list) else []
        flattened.append({
            "id": cell.get("cell_id"),
            "row_index": cell.get("row_index"),
            "column_index": cell.get("column_index"),
            "row_span": cell.get("row_span", 1),
            "column_span": cell.get("column_span", 1),
            "content_nodes": [_describe_content_node(cn) for cn in content_nodes if isinstance(cn, dict)],
        })
    return flattened


def _describe_content_node(node: dict[str, object]) -> dict[str, object]:
    """Describe an inline content node (table cell content or preserved
    visual text) -- these are TEXT/MATH objects, not string values, and are
    never registered in a page's `reading_order`."""
    if node.get("content_type") == "MATH":
        unconsumed = node.get("unconsumed_tokens") if isinstance(node.get("unconsumed_tokens"), list) else []
        issues = node.get("issues") if isinstance(node.get("issues"), list) else []
        return {
            "kind": "MATH",
            "raw_formula": node.get("raw_formula", ""),
            "presentation_ast": node.get("presentation_ast"),
            "unconsumed_tokens": unconsumed,
            "ast_status": classify_ast_status(unconsumed, issues),
        }
    return {
        "kind": "TEXT",
        "text": node.get("normalized_text") or node.get("raw_text") or "",
    }
