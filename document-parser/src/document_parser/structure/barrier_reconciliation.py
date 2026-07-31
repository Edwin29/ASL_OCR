from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any


def apply_split_ocr_reconciliation_to_document(
    payload: dict[str, Any],
    split_ocr_manifest: dict[str, Any],
    min_token_confidence: float = 0.5,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = deepcopy(payload)
    groups = split_ocr_groups(split_ocr_manifest)
    summary_pages = []
    candidates = []

    pages = result.get("pages")
    if not isinstance(pages, list):
        return result, empty_summary()

    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("page_id")
        if not isinstance(page_id, str):
            continue
        page_groups = groups.get(page_id, {})
        page_candidates = []
        for node in page.get("nodes", []):
            if not isinstance(node, dict):
                continue
            node_id = node.get("node_id")
            if not isinstance(node_id, str) or node_id not in page_groups:
                continue
            units = sorted(page_groups[node_id], key=unit_sort_key)
            preview = reconciliation_preview_for_node(node, units, min_token_confidence)
            ensure_layout(node)["split_ocr_reconciliation"] = preview
            page_candidates.append(preview)
            candidates.append(preview)

        if page_candidates:
            add_page_issue(page, page_candidates)
        summary_pages.append({
            "page_id": page_id,
            "candidate_count": len(page_candidates),
            "segment_count": sum(int(candidate["segment_count"]) for candidate in page_candidates),
            "statuses": dict(Counter(str(candidate["status"]) for candidate in page_candidates)),
            "candidates": [
                {
                    "source_text_node_id": candidate["source_text_node_id"],
                    "status": candidate["status"],
                    "segment_count": candidate["segment_count"],
                    "combined_recognized_text": candidate["combined_recognized_text"],
                }
                for candidate in page_candidates
            ],
        })

    manifest = result.setdefault("engine_manifest", {})
    if isinstance(manifest, dict):
        manifest["split_ocr_reconciliation"] = {
            "mode": "review_metadata_only",
            "min_token_confidence": min_token_confidence,
            "source_split_ocr_mode": split_ocr_manifest.get("mode"),
        }
    summary = {
        "mode": "split_ocr_reconciliation_preview",
        "page_count": len(summary_pages),
        "candidate_count": len(candidates),
        "segment_count": sum(int(candidate["segment_count"]) for candidate in candidates),
        "statuses": dict(Counter(str(candidate["status"]) for candidate in candidates)),
        "pages": summary_pages,
    }
    return result, summary


def split_ocr_groups(split_ocr_manifest: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    pages = split_ocr_manifest.get("pages")
    if not isinstance(pages, list):
        return {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("page_id")
        if not isinstance(page_id, str):
            continue
        units = page.get("recognized_work_units")
        if not isinstance(units, list):
            continue
        for unit in units:
            if not isinstance(unit, dict):
                continue
            node_id = unit.get("source_text_node_id")
            if not isinstance(node_id, str):
                continue
            groups[page_id][node_id].append(unit)
    return {page_id: dict(node_groups) for page_id, node_groups in groups.items()}


def reconciliation_preview_for_node(
    node: dict[str, Any],
    units: list[dict[str, Any]],
    min_token_confidence: float,
) -> dict[str, Any]:
    segments = [segment_from_unit(unit) for unit in units]
    low_confidence_count = sum(
        1
        for segment in segments
        if segment["min_confidence"] is not None and float(segment["min_confidence"]) < min_token_confidence
    )
    empty_segment_count = sum(1 for segment in segments if not segment["recognized_text"])
    status = "REVIEW_REPLACE_CANDIDATE"
    if empty_segment_count:
        status = "REVIEW_REQUIRED_EMPTY_SEGMENT"
    elif low_confidence_count:
        status = "REVIEW_REQUIRED_LOW_CONFIDENCE"

    source_text = node.get("normalized_text", "")
    if not isinstance(source_text, str):
        source_text = ""
    combined_text = " ".join(segment["recognized_text"] for segment in segments if segment["recognized_text"])
    return {
        "mode": "split_ocr_reconciliation_preview",
        "status": status,
        "source_text_node_id": node.get("node_id"),
        "source_text": source_text,
        "combined_recognized_text": combined_text,
        "segment_count": len(segments),
        "empty_segment_count": empty_segment_count,
        "low_confidence_segment_count": low_confidence_count,
        "segments": segments,
    }


def segment_from_unit(unit: dict[str, Any]) -> dict[str, Any]:
    tokens = [token for token in unit.get("tokens", []) if isinstance(token, dict)]
    confidences = [
        float(token["confidence"])
        for token in tokens
        if isinstance(token.get("confidence"), (int, float))
    ]
    recognized_text = unit.get("recognized_text", "")
    if not isinstance(recognized_text, str):
        recognized_text = ""
    return {
        "barrier_node_id": unit.get("barrier_node_id"),
        "structure_label": unit.get("structure_label"),
        "layout_barrier_role": unit.get("layout_barrier_role"),
        "recognized_text": recognized_text,
        "token_count": int(unit.get("token_count", len(tokens)) or 0),
        "min_confidence": round(min(confidences), 6) if confidences else None,
        "average_confidence": round(sum(confidences) / len(confidences), 6) if confidences else None,
        "crop_path": unit.get("crop_path"),
        "intersection_bbox": unit.get("intersection_bbox"),
        "crop_bbox": unit.get("crop_bbox"),
    }


def unit_sort_key(unit: dict[str, Any]) -> tuple[float, float, str]:
    box = unit.get("barrier_bbox")
    if not isinstance(box, dict):
        box = unit.get("intersection_bbox")
    if isinstance(box, dict):
        try:
            return (float(box.get("x", 0.0)), float(box.get("y", 0.0)), str(unit.get("barrier_node_id", "")))
        except (TypeError, ValueError):
            pass
    return (0.0, 0.0, str(unit.get("barrier_node_id", "")))


def add_page_issue(page: dict[str, Any], previews: list[dict[str, Any]]) -> None:
    issues = page.setdefault("parse_issues", [])
    if not isinstance(issues, list):
        page["parse_issues"] = issues = []
    issues[:] = [
        issue
        for issue in issues
        if not (
            isinstance(issue, dict)
            and issue.get("code") in {"SPLIT_OCR_RECONCILIATION_PREVIEW_APPLIED"}
        )
    ]
    issues.append({
        "code": "SPLIT_OCR_RECONCILIATION_PREVIEW_APPLIED",
        "severity": "info",
        "message": f"{len(previews)} crossing TEXT nodes have split OCR reconciliation preview metadata.",
    })


def ensure_layout(node: dict[str, Any]) -> dict[str, Any]:
    layout = node.get("layout")
    if not isinstance(layout, dict):
        layout = {}
        node["layout"] = layout
    return layout


def empty_summary() -> dict[str, Any]:
    return {
        "mode": "split_ocr_reconciliation_preview",
        "page_count": 0,
        "candidate_count": 0,
        "segment_count": 0,
        "statuses": {},
        "pages": [],
    }
