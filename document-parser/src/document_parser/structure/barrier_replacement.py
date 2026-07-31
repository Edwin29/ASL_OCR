from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from document_parser.serialization.reading_order import apply_two_column_reading_order


DEFAULT_ACCEPTED_RECONCILIATION_STATUSES = {"REVIEW_REPLACE_CANDIDATE"}


def apply_split_ocr_replacement_draft_to_document(
    payload: dict[str, Any],
    accepted_statuses: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = deepcopy(payload)
    statuses = accepted_statuses or DEFAULT_ACCEPTED_RECONCILIATION_STATUSES
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result, empty_summary()

    page_summaries = []
    all_source_candidates = []
    all_replacements = []
    all_skipped = []
    result["pages"] = [
        apply_split_ocr_replacement_draft_to_page(page, statuses, page_summaries, all_source_candidates, all_replacements, all_skipped)
        if isinstance(page, dict)
        else page
        for page in pages
    ]
    manifest = result.setdefault("engine_manifest", {})
    if isinstance(manifest, dict):
        manifest["split_ocr_replacement_draft"] = {
            "mode": "draft_primary_text_segments",
            "accepted_reconciliation_statuses": sorted(statuses),
        }
    return result, {
        "mode": "split_ocr_replacement_draft",
        "page_count": len(page_summaries),
        "source_candidate_count": len(all_source_candidates),
        "replacement_node_count": len(all_replacements),
        "skipped_candidate_count": len(all_skipped),
        "skipped_statuses": dict(Counter(str(item["status"]) for item in all_skipped)),
        "pages": page_summaries,
    }


def apply_split_ocr_replacement_draft_to_page(
    page: dict[str, Any],
    accepted_statuses: set[str],
    page_summaries: list[dict[str, Any]],
    all_source_candidates: list[dict[str, Any]],
    all_replacements: list[dict[str, Any]],
    all_skipped: list[dict[str, Any]],
) -> dict[str, Any]:
    page = deepcopy(page)
    page_id = str(page.get("page_id", "page"))
    original_nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    existing_draft_ids = {
        str(node["node_id"])
        for node in original_nodes
        if isinstance(node.get("node_id"), str) and is_existing_split_ocr_replacement(node)
    }
    nodes = [node for node in original_nodes if not is_existing_split_ocr_replacement(node)]
    reading_order = [
        node_id
        for node_id in page.get("reading_order", [])
        if isinstance(node_id, str) and node_id not in existing_draft_ids
    ]
    node_by_id = {
        str(node["node_id"]): node
        for node in nodes
        if isinstance(node.get("node_id"), str)
    }
    geometry = page.get("page_geometry") if isinstance(page.get("page_geometry"), dict) else {}
    page_width = number_value(geometry.get("width"))
    page_height = number_value(geometry.get("height"))

    replacements_by_source: dict[str, list[dict[str, Any]]] = {}
    skipped = []
    for node_id in reading_order:
        source_node = node_by_id.get(node_id)
        if source_node is None:
            continue
        preview = split_ocr_preview(source_node)
        if preview is None:
            continue
        status = str(preview.get("status", ""))
        if status not in accepted_statuses:
            skipped.append({"source_text_node_id": node_id, "status": status})
            continue
        segment_nodes = replacement_nodes_for_preview(source_node, preview, page_width, page_height)
        if not segment_nodes:
            skipped.append({"source_text_node_id": node_id, "status": "NO_SEGMENTS"})
            continue
        replacements_by_source[node_id] = segment_nodes

    new_reading_order = []
    for node_id in reading_order:
        replacements = replacements_by_source.get(node_id)
        if replacements:
            new_reading_order.extend(str(node["node_id"]) for node in replacements)
            continue
        new_reading_order.append(node_id)

    replacement_nodes = [node for nodes_for_source in replacements_by_source.values() for node in nodes_for_source]
    nodes.extend(replacement_nodes)
    for source_id, replacements in replacements_by_source.items():
        source_node = node_by_id.get(source_id)
        if source_node is None:
            continue
        source_node.pop("reading_order_index", None)
        source_node["is_primary_reading_order_candidate"] = False
        layout = ensure_layout(source_node)
        layout["split_ocr_replacement_draft_status"] = "DRAFT_REPLACED_IN_PRIMARY_READING_ORDER"
        layout["split_ocr_replaced_by_node_ids"] = [str(node["node_id"]) for node in replacements]
        add_issue(
            source_node,
            "TEXT_REPLACED_BY_SPLIT_OCR_DRAFT",
            "Original crossing TEXT is preserved as evidence and replaced in draft primary reading order by split OCR segment nodes.",
        )

    reindex_primary_nodes(nodes, new_reading_order)
    page["nodes"] = nodes
    page["reading_order"] = new_reading_order
    source_refs = [
        {"source_text_node_id": source_id, "replacement_node_ids": [str(node["node_id"]) for node in replacements]}
        for source_id, replacements in replacements_by_source.items()
    ]
    resolved_crossing_issue_count, unresolved_crossing_issue_count = cleanup_resolved_crossing_issues(
        page,
        set(replacements_by_source.keys()),
    )
    add_page_issue(page, source_refs, skipped, resolved_crossing_issue_count, unresolved_crossing_issue_count)
    page = apply_two_column_reading_order(page)

    source_candidates = list(source_refs)
    page_replacements = [
        {"node_id": str(node["node_id"]), "source_text_node_id": node["layout"]["split_ocr_source_text_node_id"]}
        for node in replacement_nodes
        if isinstance(node.get("layout"), dict)
    ]
    all_source_candidates.extend(source_candidates)
    all_replacements.extend(page_replacements)
    all_skipped.extend(skipped)
    page_summaries.append({
        "page_id": page_id,
        "source_candidate_count": len(source_candidates),
        "replacement_node_count": len(page_replacements),
        "skipped_candidate_count": len(skipped),
        "resolved_crossing_issue_count": resolved_crossing_issue_count,
        "unresolved_crossing_issue_count": unresolved_crossing_issue_count,
        "skipped_candidates": skipped,
        "source_replacements": source_refs,
    })
    return page


def replacement_nodes_for_preview(
    source_node: dict[str, Any],
    preview: dict[str, Any],
    page_width: float | None,
    page_height: float | None,
) -> list[dict[str, Any]]:
    source_id = str(source_node["node_id"])
    segments = [
        segment
        for segment in preview.get("segments", [])
        if isinstance(segment, dict) and isinstance(segment.get("recognized_text"), str) and segment["recognized_text"].strip()
    ]
    nodes = []
    for index, segment in enumerate(segments, start=1):
        box = valid_bbox(segment.get("intersection_bbox")) or valid_bbox(source_node.get("bbox")) or zero_bbox()
        node_id = f"{source_id}-splitocr-s{index:03d}"
        confidence = confidence_value(segment.get("average_confidence"), source_node.get("confidence"))
        nodes.append({
            "node_id": node_id,
            "content_type": "TEXT",
            "bbox": box,
            "normalized_bbox": normalized_bbox(box, page_width, page_height),
            "confidence": confidence,
            "source_engine": "split-ocr-reconciliation-draft",
            "issues": [
                {
                    "code": "SPLIT_OCR_REPLACEMENT_DRAFT",
                    "severity": "info",
                    "message": f"Draft TEXT segment derived from split OCR reconciliation preview for {source_id}.",
                }
            ],
            "normalized_text": segment["recognized_text"].strip(),
            "layout": {
                "is_split_ocr_replacement_draft": True,
                "split_ocr_source_text_node_id": source_id,
                "split_ocr_source_barrier_node_id": segment.get("barrier_node_id"),
                "split_ocr_segment_index": index,
                "split_ocr_crop_path": segment.get("crop_path"),
                "split_ocr_min_confidence": segment.get("min_confidence"),
                "split_ocr_average_confidence": segment.get("average_confidence"),
            },
        })
    return nodes


def split_ocr_preview(node: dict[str, Any]) -> dict[str, Any] | None:
    layout = node.get("layout")
    if not isinstance(layout, dict):
        return None
    preview = layout.get("split_ocr_reconciliation")
    return preview if isinstance(preview, dict) else None


def is_existing_split_ocr_replacement(node: dict[str, Any]) -> bool:
    layout = node.get("layout")
    return isinstance(layout, dict) and layout.get("is_split_ocr_replacement_draft") is True


def valid_bbox(raw: object) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    values = {key: number_value(raw.get(key)) for key in ("x", "y", "width", "height")}
    if any(value is None for value in values.values()):
        return None
    box = {key: float(value) for key, value in values.items() if value is not None}
    if box["width"] < 0 or box["height"] < 0:
        return None
    return box


def normalized_bbox(box: dict[str, float], page_width: float | None, page_height: float | None) -> dict[str, float]:
    if not page_width or not page_height:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    x = max(0.0, min(1.0, box["x"] / page_width))
    y = max(0.0, min(1.0, box["y"] / page_height))
    width = max(0.0, min(1.0 - x, box["width"] / page_width))
    height = max(0.0, min(1.0 - y, box["height"] / page_height))
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
    }


def confidence_value(primary: object, fallback: object) -> float:
    value = number_value(primary)
    if value is None:
        value = number_value(fallback)
    if value is None:
        return 0.0
    return max(0.0, min(1.0, value))


def zero_bbox() -> dict[str, float]:
    return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}


def ensure_layout(node: dict[str, Any]) -> dict[str, Any]:
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
    issues[:] = [issue for issue in issues if not (isinstance(issue, dict) and issue.get("code") == code)]
    issues.append({"code": code, "severity": "info", "message": message})


def cleanup_resolved_crossing_issues(page: dict[str, Any], replaced_source_ids: set[str]) -> tuple[int, int]:
    issues = page.setdefault("parse_issues", [])
    if not isinstance(issues, list):
        page["parse_issues"] = []
        return (0, 0)

    cleaned = []
    resolved = 0
    unresolved = 0
    for issue in issues:
        if not isinstance(issue, dict) or issue.get("code") != "LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE":
            cleaned.append(issue)
            continue
        node_id = issue.get("node_id")
        if isinstance(node_id, str) and node_id in replaced_source_ids:
            resolved += 1
            continue
        unresolved += 1
        cleaned.append(issue)
    page["parse_issues"] = cleaned
    return (resolved, unresolved)


def add_page_issue(
    page: dict[str, Any],
    source_refs: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    resolved_crossing_issue_count: int,
    unresolved_crossing_issue_count: int,
) -> None:
    issues = page.setdefault("parse_issues", [])
    if not isinstance(issues, list):
        page["parse_issues"] = issues = []
    issues[:] = [
        issue
        for issue in issues
        if not (
            isinstance(issue, dict)
            and issue.get("code") in {"SPLIT_OCR_REPLACEMENT_DRAFT_APPLIED"}
        )
    ]
    issues.append({
        "code": "SPLIT_OCR_REPLACEMENT_DRAFT_APPLIED",
        "severity": "info",
        "message": (
            f"{len(source_refs)} crossing TEXT nodes were replaced by split OCR draft segments; "
            f"{len(skipped)} candidates were left unchanged; "
            f"{resolved_crossing_issue_count} stale crossing warnings were resolved and "
            f"{unresolved_crossing_issue_count} remain."
        ),
        "resolved_crossing_issue_count": resolved_crossing_issue_count,
        "unresolved_crossing_issue_count": unresolved_crossing_issue_count,
    })


def reindex_primary_nodes(nodes: list[dict[str, Any]], reading_order: list[str]) -> None:
    index_by_id = {node_id: index for index, node_id in enumerate(reading_order)}
    for node in nodes:
        node.pop("reading_order_index", None)
        node_id = node.get("node_id")
        if isinstance(node_id, str) and node_id in index_by_id:
            node["reading_order_index"] = index_by_id[node_id]


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def empty_summary() -> dict[str, Any]:
    return {
        "mode": "split_ocr_replacement_draft",
        "page_count": 0,
        "source_candidate_count": 0,
        "replacement_node_count": 0,
        "skipped_candidate_count": 0,
        "skipped_statuses": {},
        "pages": [],
    }
