from __future__ import annotations

from typing import Any

from document_parser.page_policy import decide_intro_guide_page_exclusion
from document_parser.serialization.visual_regions import INTRO_GUIDE_PAGE_VISUAL_TYPE


def build_support_review_report(
    payload: dict[str, object],
    approved_exclusion_types: set[str] | None = None,
) -> dict[str, object]:
    approved_exclusion_types = approved_exclusion_types or set()
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Page IR payload must contain a pages list.")

    page_reports = [
        page_support_review(page, approved_exclusion_types)
        for page in pages
        if isinstance(page, dict)
    ]
    candidates = [
        candidate
        for page in page_reports
        for candidate in page["exclusion_candidates"]
    ]
    return {
        "report_type": "support_review",
        "page_count": len(page_reports),
        "candidate_count": len(candidates),
        "pending_approval_count": sum(
            1 for candidate in candidates if candidate["approval_status"] == "PENDING_APPROVAL"
        ),
        "approved_candidate_count": sum(
            1 for candidate in candidates if candidate["approval_status"] == "APPROVED"
        ),
        "approved_exclusion_types": sorted(approved_exclusion_types),
        "pages": page_reports,
    }


def page_support_review(
    page: dict[str, Any],
    approved_exclusion_types: set[str],
) -> dict[str, object]:
    page_id = page.get("page_id", "unknown")
    geometry = page.get("page_geometry") if isinstance(page.get("page_geometry"), dict) else {}
    page_width = geometry.get("width") if isinstance(geometry.get("width"), (int, float)) else 0
    page_height = geometry.get("height") if isinstance(geometry.get("height"), (int, float)) else 0
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    candidates = []
    if page_width > 0 and page_height > 0:
        decision = decide_intro_guide_page_exclusion(nodes, page_width, page_height)
        if decision.should_exclude:
            approved = INTRO_GUIDE_PAGE_VISUAL_TYPE in approved_exclusion_types
            candidates.append({
                "candidate_type": INTRO_GUIDE_PAGE_VISUAL_TYPE,
                "reason_code": decision.reason_code,
                "approval_status": "APPROVED" if approved else "PENDING_APPROVAL",
                "recommended_action": "exclude_from_primary_math_parsing",
                "will_apply_with_current_approvals": approved,
                "evidence": decision.evidence,
            })
    return {
        "page_id": page_id,
        "node_count": len(nodes),
        "exclusion_candidate_count": len(candidates),
        "exclusion_candidates": candidates,
    }


def approved_exclusion_types_from_config(config: dict[str, object] | None) -> set[str]:
    if not isinstance(config, dict):
        return set()
    values = config.get("approved_exclusion_types")
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str)}
