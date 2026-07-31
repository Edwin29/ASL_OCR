from __future__ import annotations

from copy import deepcopy
from typing import Any

from document_parser.structure.linking import area, bbox, center, intersection_ratio, point_inside


DEFAULT_BARRIER_LABELS = {
    "TABLE_CANDIDATE",
    "GRAPH_OR_DIAGRAM_CANDIDATE",
    "PROBLEM_BOX_CANDIDATE",
}


def apply_layout_barriers_to_document(
    payload: dict[str, object],
    barrier_labels: set[str] | None = None,
    containment_threshold: float = 0.55,
) -> dict[str, object]:
    result = deepcopy(payload)
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result
    result["pages"] = [
        apply_layout_barriers(
            page,
            barrier_labels=barrier_labels,
            containment_threshold=containment_threshold,
        )
        if isinstance(page, dict)
        else page
        for page in pages
    ]
    manifest = result.setdefault("engine_manifest", {})
    if isinstance(manifest, dict):
        manifest["layout_barriers"] = {
            "mode": "structure_region_containment",
            "barrier_labels": sorted(barrier_labels or DEFAULT_BARRIER_LABELS),
            "containment_threshold": containment_threshold,
        }
    return result


def apply_layout_barriers(
    page: dict[str, Any],
    barrier_labels: set[str] | None = None,
    containment_threshold: float = 0.55,
) -> dict[str, object]:
    page = deepcopy(page)
    labels = barrier_labels or DEFAULT_BARRIER_LABELS
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    barriers = [node for node in nodes if is_barrier_node(node, labels)]
    text_nodes = [node for node in nodes if is_primary_text_node(page, node)]
    if not barriers or not text_nodes:
        return page

    barrier_refs_by_text_id: dict[str, list[dict[str, object]]] = {}
    for barrier in barriers:
        barrier_box = bbox(barrier)
        barrier_id = barrier.get("node_id")
        if barrier_box is None or not isinstance(barrier_id, str):
            continue
        barrier_layout = ensure_layout(barrier)
        barrier_layout["is_layout_barrier"] = True
        barrier_layout["layout_barrier_role"] = barrier_role(barrier)
        contained_refs = []
        for text_node in text_nodes:
            text_id = text_node.get("node_id")
            text_box = bbox(text_node)
            if not isinstance(text_id, str) or text_box is None:
                continue
            overlap = intersection_ratio(text_box, barrier_box)
            center_inside = point_inside(center(text_box), barrier_box)
            if overlap < containment_threshold and not (center_inside and overlap >= 0.25):
                continue
            ref = {
                "node_id": text_id,
                "overlap_ratio": round(overlap, 6),
                "center_inside": center_inside,
            }
            contained_refs.append(ref)
            barrier_refs_by_text_id.setdefault(text_id, []).append({
                "barrier_node_id": barrier_id,
                "structure_label": barrier_layout.get("structure_label"),
                "layout_barrier_role": barrier_layout["layout_barrier_role"],
                "overlap_ratio": round(overlap, 6),
                "barrier_area": round(area(barrier_box), 3),
            })
        if contained_refs:
            contained_refs.sort(key=lambda item: str(item["node_id"]))
            barrier_layout["layout_barrier_text_node_refs"] = contained_refs
            barrier_layout["layout_barrier_text_node_count"] = len(contained_refs)

    annotated_count = 0
    for text_node in text_nodes:
        text_id = text_node.get("node_id")
        if not isinstance(text_id, str) or text_id not in barrier_refs_by_text_id:
            continue
        refs = sorted(
            barrier_refs_by_text_id[text_id],
            key=lambda item: (-float(item["overlap_ratio"]), float(item["barrier_area"]), str(item["barrier_node_id"])),
        )
        layout = ensure_layout(text_node)
        layout["layout_barrier_node_ids"] = [str(ref["barrier_node_id"]) for ref in refs]
        layout["primary_layout_barrier_node_id"] = str(refs[0]["barrier_node_id"])
        layout["layout_barrier_matches"] = refs
        annotated_count += 1

    crossing_warnings = detect_barrier_crossing_text_nodes(text_nodes, barriers)
    page.setdefault("parse_issues", [])
    if isinstance(page["parse_issues"], list):
        page["parse_issues"] = [
            issue
            for issue in page["parse_issues"]
            if not (
                isinstance(issue, dict)
                and issue.get("code") in {"LAYOUT_BARRIERS_APPLIED", "LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE"}
            )
        ]
        page["parse_issues"].append({
            "code": "LAYOUT_BARRIERS_APPLIED",
            "severity": "info",
            "message": f"{len(barriers)} structure regions were marked as layout barriers; {annotated_count} TEXT nodes were assigned.",
        })
        for warning in crossing_warnings:
            page["parse_issues"].append(warning)
    page["nodes"] = nodes
    return page


def detect_barrier_crossing_text_nodes(
    text_nodes: list[dict[str, Any]],
    barriers: list[dict[str, Any]],
) -> list[dict[str, object]]:
    warnings = []
    barrier_boxes = [
        (str(node["node_id"]), bbox(node))
        for node in barriers
        if isinstance(node.get("node_id"), str) and bbox(node) is not None
    ]
    for text_node in text_nodes:
        text_id = text_node.get("node_id")
        text_box = bbox(text_node)
        if not isinstance(text_id, str) or text_box is None:
            continue
        strong_overlaps = [
            barrier_id
            for barrier_id, barrier_box in barrier_boxes
            if barrier_box is not None and intersection_ratio(text_box, barrier_box) >= 0.25
        ]
        if len(strong_overlaps) <= 1:
            continue
        ensure_layout(text_node)["layout_barrier_crossing_candidate"] = strong_overlaps
        warnings.append({
            "code": "LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE",
            "severity": "warning",
            "message": f"TEXT node {text_id} overlaps multiple layout barriers and may need splitting before final reconciliation.",
            "node_id": text_id,
            "barrier_node_ids": strong_overlaps,
        })
    return warnings


def is_barrier_node(node: dict[str, Any], barrier_labels: set[str]) -> bool:
    layout = node.get("layout")
    if not isinstance(layout, dict):
        return False
    return layout.get("is_structure_region_candidate") is True and layout.get("structure_label") in barrier_labels


def is_primary_text_node(page: dict[str, Any], node: dict[str, Any]) -> bool:
    node_id = node.get("node_id")
    reading_order = {item for item in page.get("reading_order", []) if isinstance(item, str)}
    return (
        node.get("content_type") == "TEXT"
        and isinstance(node_id, str)
        and (not reading_order or node_id in reading_order)
        and isinstance(node.get("bbox"), dict)
    )


def barrier_role(node: dict[str, Any]) -> str:
    layout = node.get("layout")
    label = layout.get("structure_label") if isinstance(layout, dict) else None
    if label == "PROBLEM_BOX_CANDIDATE":
        return "problem_region_boundary"
    if label == "GRAPH_OR_DIAGRAM_CANDIDATE":
        return "visual_region_boundary"
    if label == "TABLE_CANDIDATE":
        return "table_region_boundary"
    return "structure_region_boundary"


def ensure_layout(node: dict[str, Any]) -> dict[str, object]:
    layout = node.get("layout")
    if not isinstance(layout, dict):
        layout = {}
        node["layout"] = layout
    return layout
