from __future__ import annotations

from typing import Any


def link_structure_regions_to_text(
    page: dict[str, Any],
    containment_threshold: float = 0.55,
) -> dict[str, object]:
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    structure_nodes = [node for node in nodes if is_structure_region_node(node)]
    text_nodes = [node for node in nodes if is_linkable_text_node(node)]
    if not structure_nodes or not text_nodes:
        return page

    matches_by_text_id: dict[str, list[dict[str, object]]] = {}
    for structure_node in structure_nodes:
        structure_box = bbox(structure_node)
        if structure_box is None:
            continue
        contained = []
        for text_node in text_nodes:
            text_box = bbox(text_node)
            text_id = text_node.get("node_id")
            if text_box is None or not isinstance(text_id, str):
                continue
            overlap = intersection_ratio(text_box, structure_box)
            center_inside = point_inside(center(text_box), structure_box)
            if overlap < containment_threshold and not (center_inside and overlap >= 0.25):
                continue
            contained.append({
                "node_id": text_id,
                "overlap_ratio": round(overlap, 6),
                "center_inside": center_inside,
            })
            matches_by_text_id.setdefault(text_id, []).append({
                "structure_node_id": structure_node["node_id"],
                "structure_label": structure_node.get("layout", {}).get("structure_label"),
                "overlap_ratio": round(overlap, 6),
                "structure_area": round(area(structure_box), 3),
            })
        contained.sort(key=lambda item: str(item["node_id"]))
        structure_node["contained_text_nodes"] = [str(item["node_id"]) for item in contained]
        layout = ensure_layout(structure_node)
        layout["contained_text_node_count"] = len(contained)
        layout["contained_text_node_refs"] = contained

    for text_node in text_nodes:
        text_id = text_node.get("node_id")
        if not isinstance(text_id, str) or text_id not in matches_by_text_id:
            continue
        matches = sorted(
            matches_by_text_id[text_id],
            key=lambda item: (-float(item["overlap_ratio"]), float(item["structure_area"]), str(item["structure_node_id"])),
        )
        layout = ensure_layout(text_node)
        layout["parent_structure_node_ids"] = [str(item["structure_node_id"]) for item in matches]
        layout["primary_parent_structure_node_id"] = str(matches[0]["structure_node_id"])
        layout["parent_structure_matches"] = matches
    page["nodes"] = nodes
    page.setdefault("parse_issues", [])
    if isinstance(page["parse_issues"], list) and any_structure_links_added(structure_nodes):
        page["parse_issues"] = [
            issue
            for issue in page["parse_issues"]
            if not (isinstance(issue, dict) and issue.get("code") == "STRUCTURE_TEXT_LINKS_ADDED")
        ]
        page["parse_issues"].append({
            "code": "STRUCTURE_TEXT_LINKS_ADDED",
            "severity": "info",
            "message": "Structure region candidates were linked to overlapping OCR TEXT nodes.",
        })
    return page


def any_structure_links_added(structure_nodes: list[dict[str, Any]]) -> bool:
    return any(node.get("contained_text_nodes") for node in structure_nodes)


def is_structure_region_node(node: dict[str, Any]) -> bool:
    layout = node.get("layout")
    return isinstance(layout, dict) and layout.get("is_structure_region_candidate") is True


def is_linkable_text_node(node: dict[str, Any]) -> bool:
    return (
        node.get("content_type") == "TEXT"
        and isinstance(node.get("node_id"), str)
        and isinstance(node.get("bbox"), dict)
    )


def ensure_layout(node: dict[str, Any]) -> dict[str, object]:
    layout = node.get("layout")
    if not isinstance(layout, dict):
        layout = {}
        node["layout"] = layout
    return layout


def bbox(node: dict[str, Any]) -> dict[str, float] | None:
    raw = node.get("bbox")
    if not isinstance(raw, dict):
        return None
    values = {key: number_value(raw.get(key)) for key in ("x", "y", "width", "height")}
    if any(value is None for value in values.values()):
        return None
    return {key: float(value) for key, value in values.items() if value is not None}


def intersection_ratio(inner: dict[str, float], outer: dict[str, float]) -> float:
    intersection_area = intersection(inner, outer)
    denominator = max(area(inner), 1.0)
    return intersection_area / denominator


def intersection(left: dict[str, float], right: dict[str, float]) -> float:
    width = max(0.0, min(left["x"] + left["width"], right["x"] + right["width"]) - max(left["x"], right["x"]))
    height = max(0.0, min(left["y"] + left["height"], right["y"] + right["height"]) - max(left["y"], right["y"]))
    return width * height


def area(box: dict[str, float]) -> float:
    return max(0.0, box["width"]) * max(0.0, box["height"])


def center(box: dict[str, float]) -> tuple[float, float]:
    return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def point_inside(point: tuple[float, float], box: dict[str, float]) -> bool:
    x, y = point
    return box["x"] <= x <= box["x"] + box["width"] and box["y"] <= y <= box["y"] + box["height"]


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
