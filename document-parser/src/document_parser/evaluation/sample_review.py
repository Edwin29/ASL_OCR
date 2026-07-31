from __future__ import annotations

from typing import Any


def build_sample_review_report(
    page_ir: dict[str, object],
    quality_report: dict[str, object],
    validation_summary: dict[str, object],
    overlay_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    quality_by_page = {
        str(page["page_id"]): page
        for page in quality_report.get("pages", [])
        if isinstance(page, dict) and "page_id" in page
    }
    overlay_by_page = {}
    if isinstance(overlay_summary, dict):
        overlay_by_page = {
            str(item["page_id"]): item
            for item in overlay_summary.get("overlays", [])
            if isinstance(item, dict) and "page_id" in item
        }

    pages = []
    for page in page_ir.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_id = str(page.get("page_id", "unknown"))
        quality = quality_by_page.get(page_id, {})
        overlay = overlay_by_page.get(page_id, {})
        pages.append(page_review(page, quality, overlay))

    pages.sort(key=lambda item: (-int(item["review_priority_score"]), str(item["page_id"])))
    return {
        "report_type": "sample_ocr_review",
        "page_count": len(pages),
        "schema_valid": validation_summary.get("schema_valid"),
        "total_node_count": sum(int(page["node_count"]) for page in pages),
        "total_low_confidence_node_count": sum(int(page["low_confidence_node_count"]) for page in pages),
        "total_reading_order_warning_count": sum(int(page["reading_order_warning_count"]) for page in pages),
        "total_overlap_warning_count": sum(int(page["overlap_warning_count"]) for page in pages),
        "total_suspicious_shape_node_count": sum(int(page["suspicious_shape_node_count"]) for page in pages),
        "total_region_separation_warning_count": sum(int(page["region_separation_warning_count"]) for page in pages),
        "pages": pages,
    }


def page_review(
    page: dict[str, Any],
    quality: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, object]:
    low_confidence_count = int(quality.get("low_confidence_node_count", 0) or 0)
    reading_order_warning_count = int(quality.get("reading_order_warning_count", 0) or 0)
    overlap_warning_count = int(quality.get("overlap_warning_count", 0) or 0)
    suspicious_shape_count = int(quality.get("suspicious_shape_node_count", 0) or 0)
    region_warning_count = int(quality.get("region_separation_warning_count", 0) or 0)
    priority_score = (
        low_confidence_count
        + reading_order_warning_count * 3
        + overlap_warning_count * 3
        + suspicious_shape_count * 2
        + region_warning_count * 4
    )
    nodes = page.get("nodes") if isinstance(page.get("nodes"), list) else []
    return {
        "page_id": page.get("page_id", "unknown"),
        "review_priority_score": priority_score,
        "node_count": len(nodes),
        "mean_confidence": quality.get("mean_confidence"),
        "min_confidence": quality.get("min_confidence"),
        "low_confidence_node_count": low_confidence_count,
        "reading_order_warning_count": reading_order_warning_count,
        "overlap_warning_count": overlap_warning_count,
        "suspicious_shape_node_count": suspicious_shape_count,
        "region_separation_warning_count": region_warning_count,
        "parse_issue_codes": quality.get("parse_issue_codes", []),
        "top_low_confidence_nodes": quality.get("low_confidence_nodes", [])[:5],
        "top_reading_order_warnings": quality.get("reading_order_warnings", [])[:5],
        "top_region_separation_warnings": quality.get("region_separation_warnings", [])[:5],
        "overlay_path": overlay.get("output_path"),
    }
