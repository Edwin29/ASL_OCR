from __future__ import annotations

from copy import deepcopy
from typing import Any

PROMOTABLE_STRUCTURE_LABELS = {"TABLE_CANDIDATE", "GRAPH_OR_DIAGRAM_CANDIDATE"}
PROBLEM_BOX_STRUCTURE_LABEL = "PROBLEM_BOX_CANDIDATE"
PROBLEM_CAPTION_STRUCTURE_LABEL = "VISUAL_OR_PROBLEM_CAPTION_CANDIDATE"
MAX_CAPTION_VERTICAL_GAP_RATIO = 0.25
MIN_CAPTION_HORIZONTAL_OVERLAP_RATIO = 0.25


def promote_structure_candidates_to_primary_order(
    page: dict[str, Any],
    promotable_labels: set[str] | None = None,
    order_mode: str = "first-contained",
) -> dict[str, object]:
    promotable_labels = promotable_labels or PROMOTABLE_STRUCTURE_LABELS
    page = deepcopy(page)
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    reading_order = [node_id for node_id in page.get("reading_order", []) if isinstance(node_id, str)]
    if not nodes or not reading_order:
        return page
    geometry = page.get("page_geometry") if isinstance(page.get("page_geometry"), dict) else {}
    page_width = number_value(geometry.get("width")) or max_node_right(nodes)

    node_by_id = {
        str(node["node_id"]): node
        for node in nodes
        if isinstance(node.get("node_id"), str)
    }
    index_by_id = {node_id: index for index, node_id in enumerate(reading_order)}
    promotions = []
    for node_id, node in node_by_id.items():
        layout = node.get("layout")
        if not isinstance(layout, dict) or layout.get("structure_label") not in promotable_labels:
            continue
        contained_text_ids = [
            text_id
            for text_id in node.get("contained_text_nodes", [])
            if isinstance(text_id, str) and text_id in index_by_id
        ]
        if not contained_text_ids:
            continue
        first_index = min(index_by_id[text_id] for text_id in contained_text_ids)
        promotions.append((first_index, node_id, contained_text_ids))

    if not promotions:
        return page

    promotions.sort(key=lambda item: promotion_sort_key(item, node_by_id, order_mode, page_width))
    promoted_structure_ids = {node_id for _, node_id, _ in promotions}
    promoted_text_ids = {text_id for _, _, text_ids in promotions for text_id in text_ids}
    if order_mode == "geometry":
        new_reading_order = geometry_preview_reading_order(reading_order, promotions, promoted_text_ids, promoted_structure_ids)
    else:
        new_reading_order = first_contained_reading_order(reading_order, promotions, promoted_text_ids, promoted_structure_ids)

    for _, structure_id, contained_text_ids in promotions:
        structure_node = node_by_id[structure_id]
        structure_node["embedded_text_nodes"] = contained_text_ids
        layout = ensure_layout(structure_node)
        layout["is_promoted_structure_region"] = True
        layout["promotion_mode"] = "replace_contained_text_in_primary_reading_order"
        layout["promotion_order_mode"] = order_mode
        layout["promoted_text_node_count"] = len(contained_text_ids)
        add_issue(
            structure_node,
            "STRUCTURE_CANDIDATE_PROMOTED",
            "Structure candidate is promoted into primary reading order; contained OCR TEXT nodes are preserved as embedded evidence.",
        )
        for text_id in contained_text_ids:
            text_node = node_by_id.get(text_id)
            if text_node is None:
                continue
            text_node.pop("reading_order_index", None)
            text_node["is_primary_reading_order_candidate"] = False
            text_node["parent_structure_node_id"] = structure_id
            text_layout = ensure_layout(text_node)
            text_layout["promoted_into_structure_node_id"] = structure_id
            add_issue(
                text_node,
                "TEXT_EMBEDDED_IN_PROMOTED_STRUCTURE",
                f"OCR TEXT node is embedded in promoted structure region {structure_id}.",
            )

    caption_link_count = 0
    if PROBLEM_BOX_STRUCTURE_LABEL in promotable_labels:
        caption_link_count = link_problem_captions_to_promoted_boxes(page, node_by_id, promoted_structure_ids)

    page["nodes"] = nodes
    page["reading_order"] = new_reading_order
    reindex_primary_nodes(nodes, new_reading_order)
    page.setdefault("parse_issues", [])
    if isinstance(page["parse_issues"], list):
        page["parse_issues"] = [
            issue
            for issue in page["parse_issues"]
            if not (isinstance(issue, dict) and issue.get("code") == "STRUCTURE_CANDIDATES_PROMOTED")
        ]
        page["parse_issues"].append({
            "code": "STRUCTURE_CANDIDATES_PROMOTED",
            "severity": "info",
            "message": f"{len(promotions)} structure candidates were promoted into primary reading order.",
        })
        page["parse_issues"] = [
            issue
            for issue in page["parse_issues"]
            if not (isinstance(issue, dict) and issue.get("code") == "PROBLEM_BOX_CAPTIONS_LINKED")
        ]
        if caption_link_count:
            page["parse_issues"].append({
                "code": "PROBLEM_BOX_CAPTIONS_LINKED",
                "severity": "info",
                "message": f"{caption_link_count} caption candidates were linked to promoted problem-box regions.",
            })
    return page


def link_problem_captions_to_promoted_boxes(
    page: dict[str, Any],
    node_by_id: dict[str, dict[str, Any]],
    promoted_structure_ids: set[str],
) -> int:
    problem_boxes = [
        node
        for node_id, node in node_by_id.items()
        if node_id in promoted_structure_ids
        and isinstance(node.get("layout"), dict)
        and node["layout"].get("structure_label") == PROBLEM_BOX_STRUCTURE_LABEL
        and bbox(node) is not None
    ]
    captions = [
        node
        for node in node_by_id.values()
        if isinstance(node.get("layout"), dict)
        and node["layout"].get("structure_label") == PROBLEM_CAPTION_STRUCTURE_LABEL
        and bbox(node) is not None
    ]
    if not problem_boxes or not captions:
        return 0

    linked_count = 0
    for caption in captions:
        match = best_caption_problem_box_match(caption, problem_boxes)
        if match is None:
            continue
        box_node, evidence = match
        caption_id = str(caption["node_id"])
        box_id = str(box_node["node_id"])
        box_layout = ensure_layout(box_node)
        caption_layout = ensure_layout(caption)

        caption_ids = [
            value
            for value in box_layout.get("caption_structure_node_ids", [])
            if isinstance(value, str)
        ]
        if caption_id not in caption_ids:
            caption_ids.append(caption_id)
        box_layout["caption_structure_node_ids"] = caption_ids

        refs = [
            ref
            for ref in box_layout.get("caption_structure_node_refs", [])
            if isinstance(ref, dict) and ref.get("node_id") != caption_id
        ]
        refs.append({
            "node_id": caption_id,
            "vertical_gap": evidence["vertical_gap"],
            "horizontal_overlap_ratio": evidence["horizontal_overlap_ratio"],
        })
        refs.sort(key=lambda ref: str(ref.get("node_id", "")))
        box_layout["caption_structure_node_refs"] = refs

        caption_layout["caption_link_role"] = "problem_box_caption"
        caption_layout["parent_problem_box_structure_node_id"] = box_id
        caption_layout["caption_link_evidence"] = evidence
        add_issue(
            box_node,
            "PROBLEM_CAPTION_LINKED",
            f"Caption candidate {caption_id} is linked to this promoted problem-box region.",
        )
        add_issue(
            caption,
            "PROBLEM_CAPTION_ATTACHED",
            f"Caption candidate is linked to promoted problem-box region {box_id}.",
        )
        linked_count += 1
    return linked_count


def best_caption_problem_box_match(
    caption_node: dict[str, Any],
    problem_boxes: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, float]] | None:
    caption_box = bbox(caption_node)
    if caption_box is None:
        return None

    candidates = []
    for problem_box in problem_boxes:
        box = bbox(problem_box)
        if box is None:
            continue
        vertical_gap = box["y"] - (caption_box["y"] + caption_box["height"])
        max_gap = max(40.0, box["height"] * MAX_CAPTION_VERTICAL_GAP_RATIO)
        if vertical_gap < -10.0 or vertical_gap > max_gap:
            continue
        overlap_ratio = horizontal_overlap_ratio(caption_box, box)
        if overlap_ratio < MIN_CAPTION_HORIZONTAL_OVERLAP_RATIO:
            continue
        caption_center = caption_box["x"] + caption_box["width"] / 2
        box_center = box["x"] + box["width"] / 2
        center_distance = abs(caption_center - box_center)
        candidates.append((
            vertical_gap,
            center_distance,
            str(problem_box.get("node_id", "")),
            problem_box,
            {
                "vertical_gap": round(vertical_gap, 3),
                "horizontal_overlap_ratio": round(overlap_ratio, 6),
                "center_distance": round(center_distance, 3),
            },
        ))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    _, _, _, problem_box, evidence = candidates[0]
    return problem_box, evidence


def horizontal_overlap_ratio(first: dict[str, float], second: dict[str, float]) -> float:
    overlap = max(
        0.0,
        min(first["x"] + first["width"], second["x"] + second["width"])
        - max(first["x"], second["x"]),
    )
    denominator = min(first["width"], second["width"])
    if denominator <= 0:
        return 0.0
    return overlap / denominator


def promote_structure_candidates_to_primary_order_for_document(
    payload: dict[str, object],
    promotable_labels: set[str] | None = None,
    order_mode: str = "first-contained",
) -> dict[str, object]:
    result = deepcopy(payload)
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result
    result["pages"] = [
        promote_structure_candidates_to_primary_order(
            page,
            promotable_labels=promotable_labels,
            order_mode=order_mode,
        )
        if isinstance(page, dict)
        else page
        for page in pages
    ]
    return result


def first_contained_reading_order(
    reading_order: list[str],
    promotions: list[tuple[int, str, list[str]]],
    promoted_text_ids: set[str],
    promoted_structure_ids: set[str],
) -> list[str]:
    insertion_by_index: dict[int, list[str]] = {}
    for first_index, node_id, _ in promotions:
        insertion_by_index.setdefault(first_index, []).append(node_id)

    new_reading_order = []
    seen = set()
    for index, node_id in enumerate(reading_order):
        for structure_id in insertion_by_index.get(index, []):
            if structure_id not in seen:
                new_reading_order.append(structure_id)
                seen.add(structure_id)
        if node_id in promoted_text_ids or node_id in promoted_structure_ids or node_id in seen:
            continue
        new_reading_order.append(node_id)
        seen.add(node_id)
    return new_reading_order


def geometry_preview_reading_order(
    reading_order: list[str],
    promotions: list[tuple[int, str, list[str]]],
    promoted_text_ids: set[str],
    promoted_structure_ids: set[str],
) -> list[str]:
    promoted_ids = [node_id for _, node_id, _ in promotions]
    first_index = min((index for index, _, _ in promotions), default=len(reading_order))
    prefix = [
        node_id
        for index, node_id in enumerate(reading_order)
        if index < first_index and node_id not in promoted_text_ids and node_id not in promoted_structure_ids
    ]
    suffix = [
        node_id
        for index, node_id in enumerate(reading_order)
        if index >= first_index and node_id not in promoted_text_ids and node_id not in promoted_structure_ids
    ]
    return dedupe(prefix + promoted_ids + suffix)


def promotion_sort_key(
    item: tuple[int, str, list[str]],
    node_by_id: dict[str, dict[str, Any]],
    order_mode: str,
    page_width: float,
) -> tuple[float, float, str] | tuple[int, str]:
    first_index, node_id, _ = item
    if order_mode != "geometry":
        return (first_index, node_id)
    node = node_by_id.get(node_id, {})
    box = bbox(node)
    if box is None:
        return (float(first_index), 0.0, node_id)
    page_midpoint = page_width / 2
    column_rank = 0 if box["x"] + box["width"] / 2 < page_midpoint else 1
    return (float(column_rank), box["y"], node_id)


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def bbox(node: dict[str, Any]) -> dict[str, float] | None:
    raw = node.get("bbox")
    if not isinstance(raw, dict):
        return None
    values = {key: number_value(raw.get(key)) for key in ("x", "y", "width", "height")}
    if any(value is None for value in values.values()):
        return None
    return {key: float(value) for key, value in values.items() if value is not None}


def max_node_right(nodes: list[dict[str, Any]]) -> float:
    rights = []
    for node in nodes:
        box = bbox(node)
        if box is not None:
            rights.append(box["x"] + box["width"])
    return max(rights) if rights else 1.0


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def ensure_layout(node: dict[str, Any]) -> dict[str, object]:
    layout = node.get("layout")
    if not isinstance(layout, dict):
        layout = {}
        node["layout"] = layout
    return layout


def add_issue(node: dict[str, Any], code: str, message: str) -> None:
    issues = node.get("issues")
    if not isinstance(issues, list):
        issues = []
        node["issues"] = issues
    if any(isinstance(issue, dict) and issue.get("code") == code for issue in issues):
        return
    issues.append({
        "code": code,
        "severity": "info",
        "message": message,
    })


def reindex_primary_nodes(nodes: list[dict[str, Any]], reading_order: list[str]) -> None:
    index_by_id = {node_id: index for index, node_id in enumerate(reading_order)}
    for node in nodes:
        node_id = node.get("node_id")
        if isinstance(node_id, str) and node_id in index_by_id:
            node["reading_order_index"] = index_by_id[node_id]
