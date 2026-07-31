from __future__ import annotations

from copy import deepcopy
from typing import Any

from document_parser.page_policy import bbox, decide_two_column_reading_order, is_primary_order_node


def apply_two_column_reading_order_to_document(payload: dict[str, object]) -> dict[str, object]:
    result = deepcopy(payload)
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result
    result["pages"] = [
        apply_two_column_reading_order(page) if isinstance(page, dict) else page
        for page in pages
    ]
    return result


def apply_two_column_reading_order(page: dict[str, Any]) -> dict[str, object]:
    page = deepcopy(page)
    geometry = page.get("page_geometry") if isinstance(page.get("page_geometry"), dict) else {}
    page_width = float(geometry.get("width", 0)) if isinstance(geometry.get("width"), (int, float)) else 0.0
    page_height = float(geometry.get("height", 0)) if isinstance(geometry.get("height"), (int, float)) else 0.0
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    if page_width <= 0 or page_height <= 0:
        return page

    decision = decide_two_column_reading_order(nodes, page_width, page_height)
    if not decision.should_reorder:
        return page

    primary_nodes = [node for node in nodes if is_primary_order_node(node)]
    ordered_nodes = sorted(primary_nodes, key=lambda node: two_column_sort_key(node, page_width, page_height))
    reading_order = [str(node["node_id"]) for node in ordered_nodes if isinstance(node.get("node_id"), str)]
    page["reading_order"] = reading_order
    reindex_reading_order(nodes, reading_order)
    annotate_column_groups(nodes, page_width, page_height)
    page["nodes"] = nodes
    page.setdefault("parse_issues", [])
    if isinstance(page["parse_issues"], list):
        page["parse_issues"] = [
            issue
            for issue in page["parse_issues"]
            if not (isinstance(issue, dict) and issue.get("code") == "TWO_COLUMN_READING_ORDER_APPLIED")
        ]
        page["parse_issues"].append({
            "code": "TWO_COLUMN_READING_ORDER_APPLIED",
            "severity": "info",
            "message": "Primary reading order was reordered by detected left/right page columns.",
            "evidence": decision.evidence,
        })
    return page


def two_column_sort_key(node: dict[str, Any], page_width: float, page_height: float) -> tuple[int, float, float]:
    box = bbox(node)
    if box is None:
        return (1, 0.0, 0.0)
    column = column_group(node, page_width, page_height)
    group_rank = {
        "HEADER": 0,
        "LEFT": 1,
        "RIGHT": 2,
        "FOOTER": 3,
        "MIDDLE": 2,
    }.get(column, 2)
    return (group_rank, box["y"], box["x"])


def annotate_column_groups(nodes: list[dict[str, Any]], page_width: float, page_height: float) -> None:
    for node in nodes:
        if not is_primary_order_node(node):
            continue
        layout = node.get("layout")
        if not isinstance(layout, dict):
            layout = {}
            node["layout"] = layout
        layout["reading_order_group"] = column_group(node, page_width, page_height)


def column_group(node: dict[str, Any], page_width: float, page_height: float) -> str:
    box = bbox(node)
    if box is None:
        return "MIDDLE"
    if box["y"] <= page_height * 0.08:
        return "HEADER"
    if box["y"] >= page_height * 0.94:
        return "FOOTER"
    center_x = box["x"] + box["width"] / 2
    if center_x < page_width / 2:
        return "LEFT"
    if center_x > page_width / 2:
        return "RIGHT"
    return "MIDDLE"


def reindex_reading_order(nodes: list[dict[str, Any]], reading_order: list[str]) -> None:
    index_by_id = {node_id: index for index, node_id in enumerate(reading_order)}
    for node in nodes:
        node_id = node.get("node_id")
        if isinstance(node_id, str) and node_id in index_by_id:
            node["reading_order_index"] = index_by_id[node_id]
