from __future__ import annotations

from statistics import mean
from typing import Any

from document_parser.page_policy import decide_intro_guide_page_exclusion, is_compact_lower_text_node


def build_ocr_quality_report(
    payload: dict[str, object],
    low_confidence_threshold: float = 0.5,
    wide_node_ratio: float = 0.72,
    tall_node_ratio: float = 0.08,
    overlap_threshold: float = 0.35,
) -> dict[str, object]:
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Page IR payload must contain a pages list.")

    page_reports = [
        analyze_page(
            page,
            low_confidence_threshold=low_confidence_threshold,
            wide_node_ratio=wide_node_ratio,
            tall_node_ratio=tall_node_ratio,
            overlap_threshold=overlap_threshold,
        )
        for page in pages
        if isinstance(page, dict)
    ]
    total_nodes = sum(int(report["node_count"]) for report in page_reports)
    total_low_confidence = sum(int(report["low_confidence_node_count"]) for report in page_reports)
    total_order_warnings = sum(int(report["reading_order_warning_count"]) for report in page_reports)
    total_region_warnings = sum(int(report["region_separation_warning_count"]) for report in page_reports)
    return {
        "report_type": "ocr_quality",
        "page_count": len(page_reports),
        "total_node_count": total_nodes,
        "total_low_confidence_node_count": total_low_confidence,
        "total_reading_order_warning_count": total_order_warnings,
        "total_region_separation_warning_count": total_region_warnings,
        "low_confidence_threshold": low_confidence_threshold,
        "wide_node_ratio": wide_node_ratio,
        "tall_node_ratio": tall_node_ratio,
        "overlap_threshold": overlap_threshold,
        "pages": page_reports,
    }


def analyze_page(
    page: dict[str, Any],
    low_confidence_threshold: float,
    wide_node_ratio: float,
    tall_node_ratio: float,
    overlap_threshold: float,
) -> dict[str, object]:
    page_geometry = page.get("page_geometry") if isinstance(page.get("page_geometry"), dict) else {}
    page_width = number_value(page_geometry.get("width")) or 1.0
    page_height = number_value(page_geometry.get("height")) or 1.0
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    ordered_nodes = sorted(nodes, key=lambda node: int(node.get("reading_order_index", 0)))
    confidences = [number_value(node.get("confidence")) for node in nodes]
    confidence_values = [value for value in confidences if value is not None]

    low_confidence_nodes = [
        node_summary(node)
        for node in ordered_nodes
        if (number_value(node.get("confidence")) or 0.0) < low_confidence_threshold
    ]
    suspicious_shape_nodes = [
        node_summary(node)
        for node in ordered_nodes
        if is_suspicious_shape(node, page_width, page_height, wide_node_ratio, tall_node_ratio)
    ]
    overlap_warnings = overlapping_node_warnings(ordered_nodes, overlap_threshold)
    order_warnings = reading_order_warnings(ordered_nodes, page_width, page_height)
    region_warnings = region_separation_warnings(ordered_nodes, page_width, page_height)
    return {
        "page_id": page.get("page_id", "unknown"),
        "node_count": len(nodes),
        "mean_confidence": round(mean(confidence_values), 6) if confidence_values else None,
        "min_confidence": round(min(confidence_values), 6) if confidence_values else None,
        "low_confidence_node_count": len(low_confidence_nodes),
        "suspicious_shape_node_count": len(suspicious_shape_nodes),
        "overlap_warning_count": len(overlap_warnings),
        "reading_order_warning_count": len(order_warnings),
        "region_separation_warning_count": len(region_warnings),
        "parse_issue_codes": [
            issue.get("code")
            for issue in page.get("parse_issues", [])
            if isinstance(issue, dict) and isinstance(issue.get("code"), str)
        ],
        "low_confidence_nodes": low_confidence_nodes[:20],
        "suspicious_shape_nodes": suspicious_shape_nodes[:20],
        "overlap_warnings": overlap_warnings[:20],
        "reading_order_warnings": order_warnings[:20],
        "region_separation_warnings": region_warnings[:20],
    }


def reading_order_warnings(
    ordered_nodes: list[dict[str, Any]],
    page_width: float,
    page_height: float,
) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    line_height_reference = typical_node_height(ordered_nodes)
    major_vertical_jump = max(page_height * 0.18, line_height_reference * 8)
    major_x_backtrack = page_width * 0.35
    for previous, current in zip(ordered_nodes, ordered_nodes[1:]):
        previous_box = bbox(previous)
        current_box = bbox(current)
        if previous_box is None or current_box is None:
            continue
        vertical_gap = current_box["y"] - (previous_box["y"] + previous_box["height"])
        x_backtrack = previous_box["x"] - current_box["x"]
        if vertical_gap > major_vertical_jump:
            warnings.append({
                "type": "LARGE_VERTICAL_GAP",
                "from_node_id": previous.get("node_id"),
                "to_node_id": current.get("node_id"),
                "vertical_gap": round(vertical_gap, 3),
            })
        if x_backtrack > major_x_backtrack and abs(current_box["y"] - previous_box["y"]) < line_height_reference * 2:
            warnings.append({
                "type": "SAME_BAND_X_BACKTRACK",
                "from_node_id": previous.get("node_id"),
                "to_node_id": current.get("node_id"),
                "x_backtrack": round(x_backtrack, 3),
            })
    return warnings


def overlapping_node_warnings(nodes: list[dict[str, Any]], overlap_threshold: float) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    for left_index, left in enumerate(nodes):
        left_box = bbox(left)
        if left_box is None:
            continue
        for right in nodes[left_index + 1:]:
            right_box = bbox(right)
            if right_box is None:
                continue
            ratio = intersection_ratio(left_box, right_box)
            if ratio >= overlap_threshold:
                warnings.append({
                    "type": "BBOX_OVERLAP",
                    "left_node_id": left.get("node_id"),
                    "right_node_id": right.get("node_id"),
                    "overlap_ratio": round(ratio, 6),
                })
    return warnings


def region_separation_warnings(
    ordered_nodes: list[dict[str, Any]],
    page_width: float,
    page_height: float,
) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    middle_crossing_nodes = []
    table_like_nodes = []
    for node in ordered_nodes:
        box = bbox(node)
        if box is None:
            continue
        text = str(node.get("normalized_text", ""))
        if crosses_middle(box, page_width) and box["width"] / page_width > 0.45:
            middle_crossing_nodes.append(node)
        if is_table_like_text(text) and box["width"] / page_width > 0.35:
            table_like_nodes.append(node)
        if is_mixed_region_candidate(node, page_width):
            warnings.append({
                "type": "MIXED_REGION_CANDIDATE",
                "node": node_summary(node),
                "reason": "Wide OCR line may have merged body text with an adjacent table, figure, or graph label.",
            })

    if intro_warning := intro_guide_page_exclusion_warning(ordered_nodes, page_width, page_height):
        warnings.append(intro_warning)
    if len(middle_crossing_nodes) >= 3 and has_left_and_right_columns(ordered_nodes, page_width):
        warnings.append({
            "type": "TWO_COLUMN_SPLIT_CANDIDATE",
            "node_count": len(middle_crossing_nodes),
            "reason": "Several nodes cross the page midpoint while left/right column nodes are both present.",
            "sample_nodes": [node_summary(node) for node in middle_crossing_nodes[:5]],
        })
    if table_like_nodes:
        warnings.append({
            "type": "TABLE_LIKE_CANDIDATE",
            "node_count": len(table_like_nodes),
            "reason": "Numeric/list-like OCR lines suggest a table or answer-list region should be separated from body text.",
            "sample_nodes": [node_summary(node) for node in table_like_nodes[:5]],
        })
    return warnings


def intro_guide_page_exclusion_warning(
    nodes: list[dict[str, Any]],
    page_width: float,
    page_height: float,
) -> dict[str, object] | None:
    decision = decide_intro_guide_page_exclusion(nodes, page_width, page_height)
    if not decision.should_exclude:
        return None

    compact_lower_nodes = [
        node
        for node in nodes
        if is_compact_lower_text_node(node, page_width, page_height)
    ]

    return {
        "type": "INTRO_GUIDE_PAGE_EXCLUSION_CANDIDATE",
        "node_count": int(decision.evidence["compact_lower_text_node_count"]),
        "reason": (
            "Intro/structure page appears to be publisher guide content rather than supported math content. "
            "Exclude this page from primary parsing and preserve OCR only as embedded unsupported visual evidence."
        ),
        "evidence": decision.evidence,
        "sample_nodes": [node_summary(node) for node in compact_lower_nodes[:5]],
    }


def is_mixed_region_candidate(node: dict[str, Any], page_width: float) -> bool:
    box = bbox(node)
    if box is None:
        return False
    text = str(node.get("normalized_text", ""))
    wide = box["width"] / page_width > 0.62
    mixed_text = contains_text_and_symbol_noise(text) or is_table_like_text(text)
    return wide and mixed_text


def crosses_middle(box: dict[str, float], page_width: float) -> bool:
    middle = page_width / 2
    return box["x"] < middle < box["x"] + box["width"]


def has_left_and_right_columns(nodes: list[dict[str, Any]], page_width: float) -> bool:
    left_count = 0
    right_count = 0
    for node in nodes:
        box = bbox(node)
        if box is None:
            continue
        center_x = box["x"] + box["width"] / 2
        if center_x < page_width * 0.42:
            left_count += 1
        elif center_x > page_width * 0.58:
            right_count += 1
    return left_count >= 3 and right_count >= 3


def contains_text_and_symbol_noise(text: str) -> bool:
    has_alpha_or_korean = any(("가" <= char <= "힣") or char.isalpha() for char in text)
    symbol_count = sum(1 for char in text if char in "@#=<>+-^_[](){}|")
    digit_count = sum(1 for char in text if char.isdigit())
    return has_alpha_or_korean and (symbol_count + digit_count) >= 4


def is_table_like_text(text: str) -> bool:
    tokens = [token for token in text.replace("@", " @ ").split() if token]
    if len(tokens) < 6:
        return False
    numeric_or_marker_count = sum(1 for token in tokens if token.isdigit() or token in {"@", "O", "X"})
    return numeric_or_marker_count / len(tokens) >= 0.55


def is_suspicious_shape(
    node: dict[str, Any],
    page_width: float,
    page_height: float,
    wide_node_ratio: float,
    tall_node_ratio: float,
) -> bool:
    box = bbox(node)
    if box is None:
        return False
    return box["width"] / page_width > wide_node_ratio or box["height"] / page_height > tall_node_ratio


def node_summary(node: dict[str, Any]) -> dict[str, object]:
    text = str(node.get("normalized_text", ""))
    return {
        "node_id": node.get("node_id"),
        "reading_order_index": node.get("reading_order_index"),
        "confidence": node.get("confidence"),
        "bbox": node.get("bbox"),
        "text": text[:120],
    }


def bbox(node: dict[str, Any]) -> dict[str, float] | None:
    raw = node.get("bbox")
    if not isinstance(raw, dict):
        return None
    values = {key: number_value(raw.get(key)) for key in ("x", "y", "width", "height")}
    if any(value is None for value in values.values()):
        return None
    return {key: float(value) for key, value in values.items() if value is not None}


def intersection_ratio(left: dict[str, float], right: dict[str, float]) -> float:
    intersection_width = max(0.0, min(left["x"] + left["width"], right["x"] + right["width"]) - max(left["x"], right["x"]))
    intersection_height = max(0.0, min(left["y"] + left["height"], right["y"] + right["height"]) - max(left["y"], right["y"]))
    intersection_area = intersection_width * intersection_height
    denominator = max(min(left["width"] * left["height"], right["width"] * right["height"]), 1.0)
    return intersection_area / denominator


def typical_node_height(nodes: list[dict[str, Any]]) -> float:
    heights = [box["height"] for node in nodes if (box := bbox(node)) is not None and box["height"] > 0]
    return mean(heights) if heights else 1.0


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
