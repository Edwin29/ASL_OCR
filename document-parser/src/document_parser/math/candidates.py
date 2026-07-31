from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

MATH_CANDIDATE_THRESHOLD = 3

RELATION_PATTERN = re.compile(r"[A-Za-z0-9)\]}]\s*(?:=|<|>|<=|>=|<=|>=)\s*")
UNICODE_RELATION_PATTERN = re.compile(r"[≤≥≠≈]")
FUNCTION_PATTERN = re.compile(r"\b(?:f|g|h)\s*\(|\b(?:sin|cos|tan|log|ln)\b", re.IGNORECASE)
FRACTION_PATTERN = re.compile(r"(?:\d+|[A-Za-z])\s*/\s*(?:\d+|[A-Za-z])")
POWER_OR_SUBSCRIPT_PATTERN = re.compile(r"[A-Za-z0-9]\s*[\^_]\s*[A-Za-z0-9]")
ROOT_OR_SIGMA_PATTERN = re.compile(r"[√∑∫∞π]")
MATH_SYMBOL_PATTERN = re.compile(r"[=+\-*/^<>≤≥≠≈±√∑∫∞π]")
LATIN_OR_DIGIT_PATTERN = re.compile(r"[A-Za-z0-9]")
OPTION_MARKER_PATTERN = re.compile(r"[①②③④⑤]|\([1-5]\)|\b[1-5][.)]")


def detect_math_candidates_in_document(payload: dict[str, object]) -> dict[str, object]:
    result = deepcopy(payload)
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result
    result["pages"] = [
        detect_math_candidates_in_page(page)
        if isinstance(page, dict)
        else page
        for page in pages
    ]
    manifest = result.setdefault("engine_manifest", {})
    if isinstance(manifest, dict):
        manifest["math_candidate_detection"] = {
            "mode": "text_node_metadata",
            "threshold": MATH_CANDIDATE_THRESHOLD,
            "creates_math_nodes": False,
        }
    return result


def detect_math_candidates_in_page(page: dict[str, Any]) -> dict[str, object]:
    page = deepcopy(page)
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    primary_node_ids = {
        node_id
        for node_id in page.get("reading_order", [])
        if isinstance(node_id, str)
    }
    candidate_count = 0
    for node in nodes:
        if node.get("content_type") != "TEXT":
            continue
        node_id = node.get("node_id")
        if isinstance(node_id, str) and primary_node_ids and node_id not in primary_node_ids:
            continue
        text = str(node.get("normalized_text", ""))
        candidate = score_math_candidate_text(text)
        if not candidate["is_candidate"]:
            continue
        layout = ensure_layout(node)
        layout["math_candidate"] = candidate
        add_issue(
            node,
            "MATH_CANDIDATE_DETECTED",
            "TEXT node is marked as a math candidate for later formula OCR and AST parsing.",
        )
        candidate_count += 1

    page["nodes"] = nodes
    page.setdefault("parse_issues", [])
    if isinstance(page["parse_issues"], list):
        page["parse_issues"] = [
            issue
            for issue in page["parse_issues"]
            if not (isinstance(issue, dict) and issue.get("code") == "MATH_CANDIDATES_DETECTED")
        ]
        if candidate_count:
            page["parse_issues"].append({
                "code": "MATH_CANDIDATES_DETECTED",
                "severity": "info",
                "message": f"{candidate_count} TEXT nodes were marked as math candidates.",
            })
    return page


def score_math_candidate_text(text: str) -> dict[str, object]:
    normalized = " ".join(text.strip().split())
    if not normalized:
        return candidate_result(False, 0, "none", [])

    reasons = []
    score = 0
    option_marker_count = len(OPTION_MARKER_PATTERN.findall(normalized))
    symbol_count = len(MATH_SYMBOL_PATTERN.findall(normalized))
    latin_or_digit_count = len(LATIN_OR_DIGIT_PATTERN.findall(normalized))

    if option_marker_count >= 2 and symbol_count <= 1:
        return candidate_result(False, 0, "excluded_answer_list", ["answer_list_like"])

    if RELATION_PATTERN.search(normalized) or UNICODE_RELATION_PATTERN.search(normalized):
        score += 4
        reasons.append("relation_operator")
    if FUNCTION_PATTERN.search(normalized):
        score += 3
        reasons.append("function_notation")
    if FRACTION_PATTERN.search(normalized):
        score += 3
        reasons.append("fraction_like")
    if POWER_OR_SUBSCRIPT_PATTERN.search(normalized):
        score += 2
        reasons.append("power_or_subscript")
    if ROOT_OR_SIGMA_PATTERN.search(normalized):
        score += 3
        reasons.append("math_symbol")

    symbol_density = symbol_count / max(len(normalized), 1)
    if symbol_count >= 2 and symbol_density >= 0.08:
        score += 2
        reasons.append("symbol_dense")
    if len(normalized) <= 45 and symbol_count >= 1 and latin_or_digit_count >= 2:
        score += 2
        reasons.append("short_symbolic_line")

    is_candidate = score >= MATH_CANDIDATE_THRESHOLD
    kind = "display_or_expression" if is_candidate and len(normalized) <= 60 else "inline_or_mixed"
    return candidate_result(is_candidate, score, kind, reasons)


def candidate_result(is_candidate: bool, score: int, kind: str, reasons: list[str]) -> dict[str, object]:
    return {
        "is_candidate": is_candidate,
        "score": score,
        "candidate_kind": kind,
        "reasons": reasons,
    }


def math_candidate_report(payload: dict[str, object]) -> dict[str, object]:
    pages = payload.get("pages")
    if not isinstance(pages, list):
        pages = []
    page_reports = []
    total_candidates = 0
    for page in pages:
        if not isinstance(page, dict):
            continue
        candidates = []
        for node in page.get("nodes", []):
            if not isinstance(node, dict):
                continue
            layout = node.get("layout")
            if not isinstance(layout, dict):
                continue
            candidate = layout.get("math_candidate")
            if not isinstance(candidate, dict) or candidate.get("is_candidate") is not True:
                continue
            candidates.append({
                "node_id": node.get("node_id"),
                "text": node.get("normalized_text", ""),
                "score": candidate.get("score"),
                "candidate_kind": candidate.get("candidate_kind"),
                "reasons": candidate.get("reasons", []),
            })
        total_candidates += len(candidates)
        page_reports.append({
            "page_id": page.get("page_id"),
            "candidate_count": len(candidates),
            "candidates": candidates,
        })
    return {
        "total_candidate_count": total_candidates,
        "page_count": len(page_reports),
        "pages": page_reports,
    }


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
