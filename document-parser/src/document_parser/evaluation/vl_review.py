"""Aggregate per-node issues from the PaddleOCR-VL pipeline into a page-ranked
review report (Stage 8-3b).

This adds no new detection. `vl_page_ir.py`, `document_parser.math.latex_ast`,
and `document_parser.reconciliation` already attach issue codes to individual
nodes (choice omissions, AST parse failures, low-confidence tables, graph text
that could not be captured, cross-validation results); without this module
those signals are scattered across however many nodes a document has, with no
way to tell which of, say, 160 pages actually needs a human to look at it. This
is the same "review priority" pattern already used for the legacy pipeline in
`document_parser.evaluation.sample_review`, rebuilt against the VL pipeline's
node-level issue shape instead of the old separate quality-report file.
"""

from __future__ import annotations

from typing import Any

# error/warning/info give a severity floor; a few codes are bumped or lowered
# from that floor because their real-world impact does not match the generic
# severity they were logged at (e.g. a cross-validation-confirmed omission is
# worse than a merely-suspected one, even though both are nominally "error"/
# "warning"; an AST_UNKNOWN_NODE is expected noise for out-of-scope LaTeX and
# should not dominate the ranking the way a missing required AST child does).
SEVERITY_WEIGHT = {"error": 5, "warning": 2, "info": 1}
CODE_WEIGHT_OVERRIDES = {
    "CROSS_VALIDATION_CONFIRMS_OMISSION": 8,
    "VL_POSSIBLE_CHOICE_OMISSION": 3,
    "ANNOUNCE_ONLY_NO_TEXT_CAPTURED": 3,
    "AST_UNKNOWN_NODE": 1,
    "CROSS_VALIDATION_RECORDED": 0,
    "CROSS_VALIDATION_INCONCLUSIVE": 1,
    "VL_TABLE_ROW_COL_NOT_PARSED": 0,
}


def build_vl_review_report(document: dict[str, object]) -> dict[str, object]:
    pages = []
    for page in document.get("pages", []):
        if isinstance(page, dict):
            pages.append(review_page(page))
    pages.sort(key=lambda item: (-int(item["review_priority_score"]), str(item["page_id"])))
    return {
        "report_type": "paddleocr_vl_review",
        "page_count": len(pages),
        "total_node_count": sum(int(page["node_count"]) for page in pages),
        "total_issue_count": sum(int(page["issue_count"]) for page in pages),
        "review_priority_order": [page["page_id"] for page in pages],
        "pages": pages,
    }


def review_page(page: dict[str, Any]) -> dict[str, object]:
    nodes = page.get("nodes") if isinstance(page.get("nodes"), list) else []
    issue_entries: list[dict[str, object]] = []
    priority_score = 0
    issue_code_counts: dict[str, int] = {}

    for node in nodes:
        if not isinstance(node, dict):
            continue
        for issue in node.get("issues", []):
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code", "UNKNOWN"))
            severity = str(issue.get("severity", "info"))
            weight = CODE_WEIGHT_OVERRIDES.get(code, SEVERITY_WEIGHT.get(severity, 1))
            priority_score += weight
            issue_code_counts[code] = issue_code_counts.get(code, 0) + 1
            if weight > 0:
                issue_entries.append({
                    "node_id": node.get("node_id"),
                    "content_type": node.get("content_type"),
                    "code": code,
                    "severity": severity,
                    "weight": weight,
                    "message": issue.get("message"),
                })

    issue_entries.sort(key=lambda item: -int(item["weight"]))
    return {
        "page_id": page.get("page_id", "unknown"),
        "review_priority_score": priority_score,
        "node_count": len(nodes),
        "issue_count": len(issue_entries),
        "issue_code_counts": issue_code_counts,
        "top_issues": issue_entries[:8],
    }
