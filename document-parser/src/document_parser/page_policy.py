from __future__ import annotations

from dataclasses import dataclass
from typing import Any


INTRO_GUIDE_PAGE_REASON = "INTRO_GUIDE_PAGE_EXCLUSION_CANDIDATE"


@dataclass(frozen=True)
class IntroGuidePageDecision:
    should_exclude: bool
    reason_code: str | None
    evidence: dict[str, object]


@dataclass(frozen=True)
class TwoColumnReadingOrderDecision:
    should_reorder: bool
    reason_code: str | None
    evidence: dict[str, object]


def decide_intro_guide_page_exclusion(
    nodes: list[dict[str, Any]],
    page_width: float,
    page_height: float,
    min_text_nodes: int = 20,
    min_lower_text_nodes: int = 20,
    min_compact_lower_text_nodes: int = 10,
) -> IntroGuidePageDecision:
    text_nodes = [node for node in nodes if is_text_like_node(node)]
    header_text = intro_header_text(text_nodes, page_height)
    has_intro_header = has_intro_structure_header(header_text)
    lower_text_nodes = [
        node
        for node in text_nodes
        if (box := bbox(node)) is not None and box["y"] > page_height * 0.15
    ]
    compact_lower_text_nodes = [
        node
        for node in lower_text_nodes
        if is_compact_lower_text_node(node, page_width, page_height)
    ]
    evidence = {
        "header_text": header_text[:160],
        "has_intro_header": has_intro_header,
        "text_node_count": len(text_nodes),
        "lower_text_node_count": len(lower_text_nodes),
        "compact_lower_text_node_count": len(compact_lower_text_nodes),
        "min_text_nodes": min_text_nodes,
        "min_lower_text_nodes": min_lower_text_nodes,
        "min_compact_lower_text_nodes": min_compact_lower_text_nodes,
    }
    should_exclude = (
        has_intro_header
        and len(text_nodes) >= min_text_nodes
        and len(lower_text_nodes) >= min_lower_text_nodes
        and len(compact_lower_text_nodes) >= min_compact_lower_text_nodes
    )
    return IntroGuidePageDecision(
        should_exclude=should_exclude,
        reason_code=INTRO_GUIDE_PAGE_REASON if should_exclude else None,
        evidence=evidence,
    )


def decide_two_column_reading_order(
    nodes: list[dict[str, Any]],
    page_width: float,
    page_height: float,
    min_left_nodes: int = 8,
    min_right_nodes: int = 8,
    min_vertical_band_count: int = 4,
) -> TwoColumnReadingOrderDecision:
    if decide_intro_guide_page_exclusion(nodes, page_width, page_height).should_exclude:
        return TwoColumnReadingOrderDecision(
            should_reorder=False,
            reason_code=None,
            evidence={"skip_reason": "intro_guide_page_candidate"},
        )

    primary_nodes = [node for node in nodes if is_primary_order_node(node)]
    body_nodes = [
        node
        for node in primary_nodes
        if (box := bbox(node)) is not None and page_height * 0.08 < box["y"] < page_height * 0.94
    ]
    left_nodes = []
    right_nodes = []
    spanning_nodes = []
    middle_nodes = []
    left_bands: set[int] = set()
    right_bands: set[int] = set()
    for node in body_nodes:
        box = bbox(node)
        if box is None:
            continue
        center_x = box["x"] + box["width"] / 2
        crosses_middle = box["x"] < page_width / 2 < box["x"] + box["width"]
        if crosses_middle and box["width"] / page_width > 0.45:
            spanning_nodes.append(node)
        elif center_x < page_width * 0.46:
            left_nodes.append(node)
            left_bands.add(vertical_band(box["y"], page_height))
        elif center_x > page_width * 0.54:
            right_nodes.append(node)
            right_bands.add(vertical_band(box["y"], page_height))
        else:
            middle_nodes.append(node)

    should_reorder = (
        len(left_nodes) >= min_left_nodes
        and len(right_nodes) >= min_right_nodes
        and len(left_bands) >= min_vertical_band_count
        and len(right_bands) >= min_vertical_band_count
    )
    evidence = {
        "primary_node_count": len(primary_nodes),
        "body_node_count": len(body_nodes),
        "left_node_count": len(left_nodes),
        "right_node_count": len(right_nodes),
        "middle_node_count": len(middle_nodes),
        "spanning_node_count": len(spanning_nodes),
        "left_vertical_band_count": len(left_bands),
        "right_vertical_band_count": len(right_bands),
        "min_left_nodes": min_left_nodes,
        "min_right_nodes": min_right_nodes,
        "min_vertical_band_count": min_vertical_band_count,
    }
    return TwoColumnReadingOrderDecision(
        should_reorder=should_reorder,
        reason_code="TWO_COLUMN_READING_ORDER_CANDIDATE" if should_reorder else None,
        evidence=evidence,
    )


def intro_header_text(nodes: list[dict[str, Any]], page_height: float) -> str:
    header_texts = []
    for node in nodes:
        box = bbox(node)
        if box is None or box["y"] > page_height * 0.2:
            continue
        header_texts.append(str(node.get("normalized_text", "")))
    return " ".join(header_texts).lower()


def has_intro_structure_header(header_text: str) -> bool:
    return ("구성" in header_text and "특징" in header_text) or "structure" in header_text


def is_text_like_node(node: dict[str, Any]) -> bool:
    content_type = node.get("content_type")
    if isinstance(content_type, str) and content_type != "TEXT":
        return False
    return isinstance(node.get("normalized_text"), str)


def vertical_band(y: float, page_height: float, band_count: int = 4) -> int:
    body_top = page_height * 0.08
    body_height = max(page_height * 0.86, 1.0)
    band = int((y - body_top) / (body_height / band_count))
    return max(0, min(band_count - 1, band))


def is_primary_order_node(node: dict[str, Any]) -> bool:
    if not isinstance(node.get("node_id"), str):
        return False
    if node.get("content_type") == "UNSUPPORTED_VISUAL":
        return True
    if node.get("is_primary_reading_order_candidate") is False:
        return False
    return bbox(node) is not None


def is_compact_lower_text_node(node: dict[str, Any], page_width: float, page_height: float) -> bool:
    box = bbox(node)
    if box is None:
        return False
    if box["y"] <= page_height * 0.15:
        return False
    compact_line = box["width"] < page_width * 0.55 and box["height"] < page_height * 0.05
    narrow_text = len(str(node.get("normalized_text", ""))) <= 120
    return compact_line and narrow_text


def bbox(node: dict[str, Any]) -> dict[str, float] | None:
    raw = node.get("bbox")
    if not isinstance(raw, dict):
        return None
    values = {key: number_value(raw.get(key)) for key in ("x", "y", "width", "height")}
    if any(value is None for value in values.values()):
        return None
    return {key: float(value) for key, value in values.items() if value is not None}


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
