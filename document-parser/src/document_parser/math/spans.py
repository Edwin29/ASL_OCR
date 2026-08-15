from __future__ import annotations

import re
from copy import deepcopy
from statistics import median
from typing import Any

MATH_SPAN_ENGINE_ID = "token-run-math-span-splitter"

# A line mixes Korean prose and math notation (기획서 §11.4). Splitting on Hangul
# presence per OCR token is a much stronger signal than splitting on the merged line
# string, because OCR word/phrase tokens rarely straddle a script boundary even when
# the merged text does (e.g. "함수y=x^\"의" merges a Korean word directly against a
# formula with no OCR-visible space).
HANGUL_PATTERN = re.compile(r"[가-힣]")
MATH_SIGNAL_PATTERN = re.compile(r"[=+\-*/^_<>≤≥≠≈±√∑∫∞π]")
LATIN_PATTERN = re.compile(r"[A-Za-z]")
DIGIT_PATTERN = re.compile(r"[0-9]")

TOKEN_SPACE_GAP_RATIO = 0.45


def classify_token(text: str) -> str:
    if HANGUL_PATTERN.search(text):
        return "TEXT"
    if MATH_SIGNAL_PATTERN.search(text) or LATIN_PATTERN.search(text) or DIGIT_PATTERN.search(text):
        return "MATH"
    return "OTHER"


def build_line_spans(tokens: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Group ordered OCR tokens into contiguous TEXT/MATH runs.

    Punctuation-only ("OTHER") tokens never start or break a run; they attach to
    whichever run they fall inside so a comma or period doesn't fragment a formula
    or a sentence into extra spans.
    """
    runs: list[tuple[str, list[dict[str, Any]]]] = []
    current_class: str | None = None
    current_tokens: list[dict[str, Any]] = []

    for token in tokens:
        text = str(token.get("text", ""))
        cls = classify_token(text)
        if cls == "OTHER":
            if current_tokens:
                current_tokens.append(token)
            else:
                current_class = "TEXT"
                current_tokens = [token]
            continue
        if current_class is None:
            current_class = cls
            current_tokens = [token]
        elif cls == current_class:
            current_tokens.append(token)
        else:
            runs.append((current_class, current_tokens))
            current_class = cls
            current_tokens = [token]
    if current_tokens:
        runs.append((current_class or "TEXT", current_tokens))

    return merge_unconfirmed_math_runs(runs)


def merge_unconfirmed_math_runs(
    runs: list[tuple[str, list[dict[str, Any]]]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    demoted = [
        ("TEXT" if cls == "MATH" and not is_confirmed_math_run(run_tokens) else cls, run_tokens)
        for cls, run_tokens in runs
    ]
    merged: list[tuple[str, list[dict[str, Any]]]] = []
    for cls, run_tokens in demoted:
        if merged and merged[-1][0] == cls:
            merged[-1] = (cls, merged[-1][1] + run_tokens)
        else:
            merged.append((cls, run_tokens))
    return merged


def is_confirmed_math_run(tokens: list[dict[str, Any]]) -> bool:
    """Guard against flagging a lone plain number (page counts, item counts) as math."""
    combined = "".join(str(token.get("text", "")) for token in tokens)
    if MATH_SIGNAL_PATTERN.search(combined):
        return True
    if len(tokens) >= 2:
        return True
    if LATIN_PATTERN.search(combined):
        return True
    return len(combined) >= 3


def spans_from_runs(runs: list[tuple[str, list[dict[str, Any]]]]) -> list[dict[str, object]]:
    spans: list[dict[str, object]] = []
    for cls, run_tokens in runs:
        text = join_run_text(run_tokens)
        if not text:
            continue
        if cls == "MATH":
            spans.append({
                "span_type": "UNKNOWN",
                "text": text,
                "bbox": union_bbox([token["bbox"] for token in run_tokens]),
                "math_span_candidate": True,
            })
        else:
            spans.append({"span_type": "TEXT", "text": text})
    return spans


def join_run_text(tokens: list[dict[str, Any]]) -> str:
    if not tokens:
        return ""
    typical_height = median([max(number_value(token["bbox"].get("height")) or 1.0, 1.0) for token in tokens])
    pieces = [str(tokens[0].get("text", ""))]
    previous_bbox = tokens[0]["bbox"]
    for token in tokens[1:]:
        bbox_ = token["bbox"]
        gap = number_value(bbox_.get("x")) - (
            number_value(previous_bbox.get("x")) + number_value(previous_bbox.get("width"))
        )
        if gap is not None and gap > typical_height * TOKEN_SPACE_GAP_RATIO:
            pieces.append(" ")
        pieces.append(str(token.get("text", "")))
        previous_bbox = bbox_
    return "".join(pieces).strip()


def detect_math_spans_in_document(payload: dict[str, object]) -> dict[str, object]:
    result = deepcopy(payload)
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result
    result["pages"] = [
        detect_math_spans_in_page(page) if isinstance(page, dict) else page
        for page in pages
    ]
    manifest = result.setdefault("engine_manifest", {})
    if isinstance(manifest, dict):
        manifest["math_span_detection"] = {
            "mode": "token_run_classification",
            "engine_id": MATH_SPAN_ENGINE_ID,
        }
    return result


def detect_math_spans_in_page(page: dict[str, Any]) -> dict[str, object]:
    page = deepcopy(page)
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    reading_order = {node_id for node_id in page.get("reading_order", []) if isinstance(node_id, str)}
    split_count = 0
    skipped_candidate_count = 0
    for node in nodes:
        if node.get("content_type") != "TEXT":
            continue
        node_id = node.get("node_id")
        if isinstance(node_id, str) and reading_order and node_id not in reading_order:
            continue
        layout = node.get("layout")
        tokens = layout.get("tokens") if isinstance(layout, dict) else None
        was_math_candidate = (
            isinstance(layout, dict)
            and isinstance(layout.get("math_candidate"), dict)
            and layout["math_candidate"].get("is_candidate") is True
        )
        if not isinstance(tokens, list) or not tokens:
            if was_math_candidate:
                skipped_candidate_count += 1
                add_issue(
                    node,
                    "MATH_SPAN_SPLIT_UNAVAILABLE_NO_TOKEN_DATA",
                    "Node was flagged as a math candidate but has no per-token bbox data to split spans from.",
                )
            continue

        runs = build_line_spans(tokens)
        if not any(cls == "MATH" for cls, _ in runs):
            continue

        node["spans"] = spans_from_runs(runs)
        math_span_count = sum(1 for cls, _ in runs if cls == "MATH")
        ensure_layout(node)["math_span_count"] = math_span_count
        split_count += 1
        add_issue(
            node,
            "MATH_SPAN_CANDIDATE_SPLIT",
            f"Line text was split into {len(runs)} span(s); {math_span_count} flagged as math span candidate(s).",
        )

    page["nodes"] = nodes
    page.setdefault("parse_issues", [])
    if isinstance(page["parse_issues"], list):
        page["parse_issues"] = [
            issue
            for issue in page["parse_issues"]
            if not (isinstance(issue, dict) and issue.get("code") == "MATH_SPANS_DETECTED")
        ]
        if split_count or skipped_candidate_count:
            page["parse_issues"].append({
                "code": "MATH_SPANS_DETECTED",
                "severity": "info",
                "message": (
                    f"{split_count} TEXT node(s) were split into text/math spans; "
                    f"{skipped_candidate_count} known math-candidate node(s) had no token data to split."
                ),
            })
    return page


def math_span_report(payload: dict[str, object]) -> dict[str, object]:
    page_reports = []
    total_span_nodes = 0
    total_math_spans = 0
    for page in payload.get("pages", []):
        if not isinstance(page, dict):
            continue
        entries = []
        for node in page.get("nodes", []):
            if not isinstance(node, dict):
                continue
            layout = node.get("layout")
            if not isinstance(layout, dict) or "math_span_count" not in layout:
                continue
            spans = node.get("spans") if isinstance(node.get("spans"), list) else []
            math_spans = [span for span in spans if isinstance(span, dict) and span.get("math_span_candidate")]
            entries.append({
                "node_id": node.get("node_id"),
                "span_count": len(spans),
                "math_span_count": len(math_spans),
                "math_span_texts": [span.get("text") for span in math_spans],
            })
        total_span_nodes += len(entries)
        total_math_spans += sum(entry["math_span_count"] for entry in entries)
        page_reports.append({
            "page_id": page.get("page_id"),
            "split_node_count": len(entries),
            "nodes": entries,
        })
    return {
        "total_split_node_count": total_span_nodes,
        "total_math_span_count": total_math_spans,
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
    issues.append({"code": code, "severity": "info", "message": message})


def union_bbox(boxes: list[dict[str, float]]) -> dict[str, float]:
    min_x = min(number_value(box.get("x")) or 0.0 for box in boxes)
    min_y = min(number_value(box.get("y")) or 0.0 for box in boxes)
    max_x = max((number_value(box.get("x")) or 0.0) + (number_value(box.get("width")) or 0.0) for box in boxes)
    max_y = max((number_value(box.get("y")) or 0.0) + (number_value(box.get("height")) or 0.0) for box in boxes)
    return {
        "x": round(min_x, 3),
        "y": round(min_y, 3),
        "width": round(max_x - min_x, 3),
        "height": round(max_y - min_y, 3),
    }


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
