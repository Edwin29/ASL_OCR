from __future__ import annotations

from copy import deepcopy
from statistics import mean
from typing import Any

from document_parser.page_policy import decide_intro_guide_page_exclusion


INTRO_GUIDE_PAGE_VISUAL_TYPE = "INTRO_GUIDE_PAGE_UNSUPPORTED"
INTRO_GUIDE_PAGE_ENGINE_ID = "layout-intro-guide-page-excluder"


def apply_intro_page_exclusions_to_document(
    payload: dict[str, object],
    approved_exclusion_types: set[str] | None = None,
) -> dict[str, object]:
    approved_exclusion_types = approved_exclusion_types or set()
    result = deepcopy(payload)
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result
    result["pages"] = [
        apply_intro_page_exclusion(page, approved_exclusion_types=approved_exclusion_types)
        if isinstance(page, dict)
        else page
        for page in pages
    ]
    return result


def apply_intro_page_exclusion(
    page: dict[str, Any],
    approved_exclusion_types: set[str] | None = None,
) -> dict[str, object]:
    approved_exclusion_types = approved_exclusion_types or set()
    page = deepcopy(page)
    geometry = page.get("page_geometry") if isinstance(page.get("page_geometry"), dict) else {}
    page_width = int(geometry.get("width", 0)) if isinstance(geometry.get("width"), int) else 0
    page_height = int(geometry.get("height", 0)) if isinstance(geometry.get("height"), int) else 0
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    if page_width <= 0 or page_height <= 0:
        return page
    decision = decide_intro_guide_page_exclusion(nodes, page_width, page_height)
    if not decision.should_exclude:
        return page
    if INTRO_GUIDE_PAGE_VISUAL_TYPE not in approved_exclusion_types:
        return page
    if any(node.get("visual_type_candidate") == INTRO_GUIDE_PAGE_VISUAL_TYPE for node in nodes):
        return page

    text_nodes = [node for node in nodes if node.get("content_type") == "TEXT" and isinstance(node.get("node_id"), str)]
    if len(text_nodes) < 10:
        return page

    visual_node_id = f"{page.get('page_id', 'page')}-intro-guide"
    for node in text_nodes:
        mark_embedded_text_node(node, visual_node_id)

    visual_node = intro_guide_page_visual_node(
        visual_node_id=visual_node_id,
        text_nodes=text_nodes,
        page_width=page_width,
        page_height=page_height,
    )
    page["nodes"] = nodes + [visual_node]
    page["reading_order"] = [visual_node_id]
    reindex_primary_reading_order(page["nodes"], page["reading_order"])
    page.setdefault("parse_issues", [])
    if isinstance(page["parse_issues"], list):
        page["parse_issues"].append({
            "code": "INTRO_GUIDE_PAGE_EXCLUDED",
            "severity": "info",
            "message": "Intro/publisher guide page is excluded from supported math-content parsing.",
            "evidence": decision.evidence,
        })
    return page


def intro_guide_page_visual_node(
    visual_node_id: str,
    text_nodes: list[dict[str, Any]],
    page_width: int,
    page_height: int,
) -> dict[str, object]:
    embedded_ids = [str(node["node_id"]) for node in text_nodes if isinstance(node.get("node_id"), str)]
    confidences = [
        float(confidence)
        for node in text_nodes
        if isinstance((confidence := node.get("confidence")), (int, float)) and not isinstance(confidence, bool)
    ]
    return {
        "node_id": visual_node_id,
        "content_type": "UNSUPPORTED_VISUAL",
        "bbox": {"x": 0, "y": 0, "width": page_width, "height": page_height},
        "normalized_bbox": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
        "reading_order_index": 0,
        "confidence": round(mean(confidences), 6) if confidences else 0.0,
        "source_engine": INTRO_GUIDE_PAGE_ENGINE_ID,
        "issues": [{
            "code": "INTRO_GUIDE_PAGE_UNSUPPORTED",
            "severity": "info",
            "message": "Intro/publisher guide page is intentionally excluded from math-content parsing.",
        }],
        "visual_type_candidate": INTRO_GUIDE_PAGE_VISUAL_TYPE,
        "embedded_text_nodes": embedded_ids,
    }


def mark_embedded_text_node(node: dict[str, Any], visual_node_id: str) -> None:
    layout = node.get("layout")
    if not isinstance(layout, dict):
        layout = {}
        node["layout"] = layout
    if isinstance(node.get("reading_order_index"), int):
        layout["original_reading_order_index"] = node["reading_order_index"]
    node.pop("reading_order_index", None)
    node["parent_visual_node_id"] = visual_node_id
    node["is_primary_reading_order_candidate"] = False
    issues = node.get("issues")
    if not isinstance(issues, list):
        issues = []
        node["issues"] = issues
    issues.append({
        "code": "EXCLUDED_INTRO_GUIDE_PAGE_TEXT",
        "severity": "info",
        "message": f"OCR text belongs to excluded intro guide page {visual_node_id}.",
    })


def reindex_primary_reading_order(nodes: list[dict[str, Any]], reading_order: list[str]) -> None:
    index_by_id = {node_id: index for index, node_id in enumerate(reading_order)}
    for node in nodes:
        node_id = node.get("node_id")
        if isinstance(node_id, str) and node_id in index_by_id:
            node["reading_order_index"] = index_by_id[node_id]
