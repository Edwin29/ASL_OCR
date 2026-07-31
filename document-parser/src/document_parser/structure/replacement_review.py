from __future__ import annotations

from collections import Counter
from typing import Any


def build_split_ocr_replacement_review_report(payload: dict[str, Any]) -> dict[str, Any]:
    pages = payload.get("pages")
    if not isinstance(pages, list):
        return empty_report()

    page_reports = []
    all_replacements = []
    all_unresolved = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_report = build_page_replacement_review(page)
        page_reports.append(page_report)
        all_replacements.extend(page_report["replacements"])
        all_unresolved.extend(page_report["unresolved_candidates"])

    return {
        "mode": "split_ocr_replacement_review",
        "page_count": len(page_reports),
        "replacement_source_count": len(all_replacements),
        "replacement_segment_count": sum(int(item["replacement_segment_count"]) for item in all_replacements),
        "unresolved_candidate_count": len(all_unresolved),
        "unresolved_statuses": dict(Counter(str(item.get("status", "UNKNOWN")) for item in all_unresolved)),
        "pages": page_reports,
    }


def build_page_replacement_review(page: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    node_by_id = {
        str(node["node_id"]): node
        for node in nodes
        if isinstance(node.get("node_id"), str)
    }
    replacements = []
    unresolved = []
    for node in nodes:
        node_id = node.get("node_id")
        if not isinstance(node_id, str):
            continue
        layout = node.get("layout")
        if not isinstance(layout, dict):
            continue
        replacement_ids = [
            value
            for value in layout.get("split_ocr_replaced_by_node_ids", [])
            if isinstance(value, str)
        ]
        if replacement_ids:
            segment_nodes = [node_by_id[value] for value in replacement_ids if value in node_by_id]
            replacements.append(replacement_entry(node, segment_nodes))
            continue
        preview = layout.get("split_ocr_reconciliation")
        if isinstance(preview, dict):
            status = preview.get("status")
            if status != "REVIEW_REPLACE_CANDIDATE":
                unresolved.append({
                    "source_text_node_id": node_id,
                    "source_text": node.get("normalized_text", ""),
                    "status": status,
                    "segment_count": preview.get("segment_count", 0),
                    "combined_recognized_text": preview.get("combined_recognized_text", ""),
                })

    return {
        "page_id": page.get("page_id"),
        "replacement_source_count": len(replacements),
        "replacement_segment_count": sum(int(item["replacement_segment_count"]) for item in replacements),
        "unresolved_candidate_count": len(unresolved),
        "replacements": replacements,
        "unresolved_candidates": unresolved,
    }


def replacement_entry(source_node: dict[str, Any], segment_nodes: list[dict[str, Any]]) -> dict[str, Any]:
    source_layout = source_node.get("layout") if isinstance(source_node.get("layout"), dict) else {}
    segments = [segment_entry(node) for node in segment_nodes]
    return {
        "source_text_node_id": source_node.get("node_id"),
        "source_text": source_node.get("normalized_text", ""),
        "source_bbox": source_node.get("bbox"),
        "replacement_node_ids": [segment["node_id"] for segment in segments],
        "replacement_text": " ".join(segment["text"] for segment in segments if segment["text"]),
        "replacement_segment_count": len(segments),
        "replacement_segments": segments,
        "source_issue_codes": [
            issue.get("code")
            for issue in source_node.get("issues", [])
            if isinstance(issue, dict) and isinstance(issue.get("code"), str)
        ],
        "replacement_draft_status": source_layout.get("split_ocr_replacement_draft_status"),
    }


def segment_entry(node: dict[str, Any]) -> dict[str, Any]:
    layout = node.get("layout") if isinstance(node.get("layout"), dict) else {}
    return {
        "node_id": node.get("node_id"),
        "text": node.get("normalized_text", ""),
        "bbox": node.get("bbox"),
        "reading_order_index": node.get("reading_order_index"),
        "confidence": node.get("confidence"),
        "barrier_node_id": layout.get("split_ocr_source_barrier_node_id"),
        "crop_path": layout.get("split_ocr_crop_path"),
        "min_confidence": layout.get("split_ocr_min_confidence"),
        "average_confidence": layout.get("split_ocr_average_confidence"),
    }


def empty_report() -> dict[str, Any]:
    return {
        "mode": "split_ocr_replacement_review",
        "page_count": 0,
        "replacement_source_count": 0,
        "replacement_segment_count": 0,
        "unresolved_candidate_count": 0,
        "unresolved_statuses": {},
        "pages": [],
    }
