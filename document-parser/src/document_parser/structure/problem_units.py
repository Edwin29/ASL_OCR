from __future__ import annotations

import re
from copy import deepcopy
from statistics import mean
from dataclasses import dataclass, field
from typing import Any


PROBLEM_UNIT_STRUCTURE_LABEL = "PROBLEM_UNIT"
PROBLEM_UNIT_ENGINE_ID = "text-pattern-problem-unit-detector"

# EBS-authored practice problems carry a unique item code such as "[26008-0011]"
# directly above the stem. This is the highest-precision start signal found during
# sample review: it appeared on every EBS-authored problem checked and never on
# plain explanatory/example text.
PROBLEM_CODE_PATTERN = re.compile(r"\[\d{5}-\d{4}\]")

# Reproduced past-exam problems ("대표 기출 문제") do not carry an item code; they are
# introduced by a source tag such as "2023학년도 수능" instead.
EXAM_SOURCE_PATTERN = re.compile(r"\d{4}학년도\s*(수능|모의평가|모평)")

# Circled-number markers are heavily overloaded in this textbook (property lists,
# worked-example numbering, real answer choices, answer-index grids). A line is only
# treated as a real answer-choice row when several markers are packed onto one line,
# which matches how OCR line-grouping joins horizontally laid out choices.
CHOICE_MARKER_PATTERN = re.compile(r"[①②③④⑤]")
CHOICE_LABEL_ORDER = ["①", "②", "③", "④", "⑤"]
MIN_CHOICE_MARKER_COUNT = 4

# Short-answer stems end with an imperative instruction instead of offering choices.
SHORT_ANSWER_END_PATTERN = re.compile(r"(구하시오|나타내시오|고르시오)\s*\.?\s*$")

# "(가)", "(나)", "(다)" condition items and "보기" blocks (그 안의 "ㄱ.", "ㄴ." 항목)
# are optional sub-structures that can appear inside a stem, in bordered or
# borderless form. Detection relies on the label text, not on box borders, since
# sample review found border styling is not consistent.
CONDITION_LABEL_PATTERN = re.compile(r"^\(?[가나다라]\)")
BOGI_HEADER_PATTERN = re.compile(r"^보기\b")
BOGI_ITEM_PATTERN = re.compile(r"^[ㄱㄴㄷㄹ]\s*[.\)]")

# Sub-item extraction patterns. These reuse the same label alphabets as the role
# classifiers above but capture the label and the remaining text separately so each
# choice/condition/보기 item can be addressed individually (e.g. for TTS "①번, 6").
# PaddleOCR-VL sometimes bundles multiple condition or 보기 items onto a single
# physical line inside one block (e.g. "(가) ... (나) ..." with no line break), so
# these patterns find every occurrence in a node's text rather than assuming one
# label per node.
CONDITION_ITEM_SPLIT_PATTERN = re.compile(r"\(([가나다라])\)\s*((?:(?!\([가나다라]\)).)*)")
BOGI_ITEM_SPLIT_PATTERN = re.compile(r"([ㄱㄴㄷㄹ])\s*[.\)]\s*((?:(?!(?:[ㄱㄴㄷㄹ])\s*[.\)]).)*)")
CHOICE_OPTION_SPLIT_PATTERN = re.compile(r"([①②③④⑤])\s*([^①②③④⑤]*)")

# A standard EBS multiple-choice row has exactly 5 options. OCR sometimes garbles the
# last circled digit into a plain digit (observed on a real sample: "...52 5 57"
# instead of "...52 ⑤ 57"), which silently drops an option from the split. This is
# tracked as an explicit issue rather than presented as a clean 5-way split.
EXPECTED_CHOICE_OPTION_COUNT = 5

# PaddleOCR-VL text blocks can bundle several physical lines into one block's
# `normalized_text`, joined with "\n" (verified on real p018 data: a single block
# held a problem's stem, its (가)/(나) conditions, and its ①-⑤ choices together).
# Role classification below assumes one node is one line, so multi-line blocks are
# split into synthetic per-line nodes before classification, purely for detection --
# the split is only kept in the final Page IR for blocks that actually end up inside
# a detected problem unit.
TEXT_LINE_SPLIT_ISSUE_CODE = "TEXT_LINE_SPLIT_FROM_MULTILINE_BLOCK"


@dataclass(frozen=True)
class ProblemCandidate:
    marker_node_id: str
    start_kind: str
    answer_structure_type: str
    member_roles: dict[str, str] = field(default_factory=dict)

    def member_ids(self) -> list[str]:
        return list(self.member_roles.keys())

    def ids_with_role(self, role: str) -> list[str]:
        return [node_id for node_id, node_role in self.member_roles.items() if node_role == role]


def detect_problem_units_in_document(payload: dict[str, object]) -> dict[str, object]:
    result = deepcopy(payload)
    pages = result.get("pages")
    if not isinstance(pages, list):
        return result
    result["pages"] = [
        detect_problem_units_in_page(page) if isinstance(page, dict) else page
        for page in pages
    ]
    manifest = result.setdefault("engine_manifest", {})
    if isinstance(manifest, dict):
        manifest["problem_unit_detection"] = {
            "mode": "text_pattern_stem_and_answer_structure",
            "engine_id": PROBLEM_UNIT_ENGINE_ID,
        }
    return result


def detect_problem_units_in_page(page: dict[str, Any]) -> dict[str, object]:
    page = deepcopy(page)
    nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
    reading_order = [node_id for node_id in page.get("reading_order", []) if isinstance(node_id, str)]
    if not nodes or not reading_order:
        return page

    node_by_id = {
        node["node_id"]: node
        for node in nodes
        if isinstance(node.get("node_id"), str)
    }
    ordered_text_nodes = [
        node_by_id[node_id]
        for node_id in reading_order
        if node_id in node_by_id and node_by_id[node_id].get("content_type") == "TEXT"
    ]
    if not ordered_text_nodes:
        return page

    starts = find_problem_starts(ordered_text_nodes)
    if not starts:
        return page

    problems: list[ProblemCandidate] = []
    split_replacements: dict[str, list[dict[str, object]]] = {}
    for position, (start_index, start_kind) in enumerate(starts):
        end_index = starts[position + 1][0] if position + 1 < len(starts) else len(ordered_text_nodes)
        scope_nodes = ordered_text_nodes[start_index:end_index]
        flat_scope_nodes, scope_split_map = flatten_scope_nodes(scope_nodes)
        candidate = classify_problem_scope(flat_scope_nodes, start_kind)
        if candidate is not None:
            problems.append(candidate)
            split_replacements.update(scope_split_map)
    if not problems:
        return page

    # Only replace the specific multi-line blocks that ended up inside a detected
    # problem unit -- every other block (including multi-line ones that were part of
    # a scope that failed to classify) is left exactly as PaddleOCR-VL produced it.
    nodes = [
        replacement_node
        for original_node in nodes
        for replacement_node in split_replacements.get(original_node.get("node_id"), [original_node])
    ]
    reading_order = [
        replacement_id
        for original_id in reading_order
        for replacement_id in (
            [split_node["node_id"] for split_node in split_replacements[original_id]]
            if original_id in split_replacements
            else [original_id]
        )
    ]
    node_by_id = {
        node["node_id"]: node
        for node in nodes
        if isinstance(node.get("node_id"), str)
    }

    geometry = page.get("page_geometry") if isinstance(page.get("page_geometry"), dict) else {}
    page_width = number_value(geometry.get("width")) or 1.0
    page_height = number_value(geometry.get("height")) or 1.0
    page_id = str(page.get("page_id", "page"))

    existing_ids = set(node_by_id.keys())
    built: list[tuple[ProblemCandidate, dict[str, object]]] = []
    next_index = 1
    for problem in problems:
        node_id = f"{page_id}-problem-{next_index:03d}"
        while node_id in existing_ids:
            next_index += 1
            node_id = f"{page_id}-problem-{next_index:03d}"
        existing_ids.add(node_id)
        next_index += 1
        problem_node = build_problem_unit_node(node_id, problem, node_by_id, page_width, page_height)
        built.append((problem, problem_node))

    replaced_ids: set[str] = set()
    for problem, _ in built:
        replaced_ids.update(problem.member_ids())

    new_reading_order = rebuild_reading_order(reading_order, built, replaced_ids)
    for problem, problem_node in built:
        mark_member_nodes(node_by_id, problem, str(problem_node["node_id"]))

    page["nodes"] = nodes + [problem_node for _, problem_node in built]
    page["reading_order"] = new_reading_order
    reindex_primary_nodes(page["nodes"], new_reading_order)
    page.setdefault("parse_issues", [])
    if isinstance(page["parse_issues"], list):
        page["parse_issues"] = [
            issue
            for issue in page["parse_issues"]
            if not (isinstance(issue, dict) and issue.get("code") == "PROBLEM_UNITS_DETECTED")
        ]
        page["parse_issues"].append({
            "code": "PROBLEM_UNITS_DETECTED",
            "severity": "info",
            "message": f"{len(built)} problem units were detected and promoted into primary reading order.",
        })
    return page


def find_problem_starts(text_nodes: list[dict[str, Any]]) -> list[tuple[int, str]]:
    starts = []
    for index, node in enumerate(text_nodes):
        text = str(node.get("normalized_text", ""))
        if PROBLEM_CODE_PATTERN.search(text):
            starts.append((index, "code"))
        elif EXAM_SOURCE_PATTERN.search(text):
            starts.append((index, "exam_reprint"))
    return starts


def classify_problem_scope(scope_nodes: list[dict[str, Any]], start_kind: str) -> ProblemCandidate | None:
    if len(scope_nodes) < 2:
        return None
    marker_node = scope_nodes[0]
    marker_id = marker_node.get("node_id")
    if not isinstance(marker_id, str):
        return None

    marker_role = "problem_code" if start_kind == "code" else "exam_source_tag"
    roles: dict[str, str] = {marker_id: marker_role}

    choice_id: str | None = None
    short_answer_confirmed = False

    # Consecutive nodes carrying at least one circled-number marker are treated as
    # fragments of a single answer-choice row. PaddleOCR-VL sometimes splits one
    # physical choice line across several sibling blocks (verified on real p018
    # data: choices ①③④⑤② came out as 3 separate blocks, none individually
    # reaching MIN_CHOICE_MARKER_COUNT), so the run is only resolved once it either
    # collects the full expected set or is interrupted by a non-marker line.
    pending_run: list[tuple[str, str]] = []
    pending_markers: set[str] = set()

    def commit_run() -> None:
        nonlocal choice_id
        for pending_id, _ in pending_run:
            roles[pending_id] = "choices"
        choice_id = pending_run[0][0]
        pending_run.clear()
        pending_markers.clear()

    def flush_run_as_stem() -> None:
        nonlocal short_answer_confirmed
        for pending_id, pending_text in pending_run:
            roles[pending_id] = "stem"
            if SHORT_ANSWER_END_PATTERN.search(pending_text):
                short_answer_confirmed = True
        pending_run.clear()
        pending_markers.clear()

    for node in scope_nodes[1:]:
        if choice_id is not None:
            break
        node_id = node.get("node_id")
        if not isinstance(node_id, str):
            continue
        text = str(node.get("normalized_text", "")).strip()
        if not text:
            continue

        marker_set = set(CHOICE_MARKER_PATTERN.findall(text))
        if marker_set:
            pending_run.append((node_id, text))
            pending_markers.update(marker_set)
            if len(pending_markers) >= EXPECTED_CHOICE_OPTION_COUNT:
                commit_run()
            continue

        if len(pending_markers) >= MIN_CHOICE_MARKER_COUNT:
            commit_run()
            break

        if pending_run:
            flush_run_as_stem()

        if BOGI_HEADER_PATTERN.match(text) or BOGI_ITEM_PATTERN.match(text):
            roles[node_id] = "bogi"
            continue

        if CONDITION_LABEL_PATTERN.match(text):
            roles[node_id] = "condition"
            continue

        roles[node_id] = "stem"
        if SHORT_ANSWER_END_PATTERN.search(text):
            short_answer_confirmed = True

    if choice_id is None and len(pending_markers) >= MIN_CHOICE_MARKER_COUNT:
        commit_run()
    elif pending_run:
        flush_run_as_stem()

    if choice_id is None and not short_answer_confirmed:
        return None
    if not any(role == "stem" for role in roles.values()):
        return None

    answer_structure_type = "choices" if choice_id is not None else "short_answer"
    return ProblemCandidate(
        marker_node_id=marker_id,
        start_kind=start_kind,
        answer_structure_type=answer_structure_type,
        member_roles=roles,
    )


def flatten_scope_nodes(
    scope_nodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, object]]]]:
    flat: list[dict[str, Any]] = []
    split_map: dict[str, list[dict[str, object]]] = {}
    for node in scope_nodes:
        node_id = node.get("node_id")
        lines = split_text_node_into_lines(node) if isinstance(node_id, str) else None
        if lines is None:
            flat.append(node)
        else:
            flat.extend(lines)
            split_map[node_id] = lines
    return flat, split_map


def split_text_node_into_lines(node: dict[str, Any]) -> list[dict[str, object]] | None:
    """Split a TEXT node whose normalized_text bundles multiple physical lines into
    line-level synthetic nodes. Returns None when the node is not a multi-line TEXT
    block, so the caller can leave it untouched.
    """
    if node.get("content_type") != "TEXT":
        return None
    raw_text = str(node.get("normalized_text", ""))
    if "\n" not in raw_text:
        return None
    lines = raw_text.split("\n")
    non_empty_line_indices = [index for index, line in enumerate(lines) if line.strip()]
    if len(non_empty_line_indices) < 2:
        return None

    spans = node.get("spans")
    if not isinstance(spans, list) or not spans:
        spans = [{"span_type": "TEXT", "text": raw_text}]

    line_spans: list[list[dict[str, object]]] = [[] for _ in lines]
    current_line = 0
    for span in spans:
        if not isinstance(span, dict):
            continue
        if span.get("span_type") == "TEXT":
            parts = str(span.get("text", "")).split("\n")
            for part_index, part in enumerate(parts):
                if part:
                    line_spans[current_line].append({"span_type": "TEXT", "text": part})
                if part_index < len(parts) - 1:
                    current_line = min(current_line + 1, len(lines) - 1)
        else:
            line_spans[current_line].append(span)

    parent_id = node.get("node_id")
    parent_bbox = node.get("bbox")
    parent_normalized_bbox = node.get("normalized_bbox")
    parent_confidence = node.get("confidence", 0.0)
    parent_source_engine = node.get("source_engine", "")

    synthetic_nodes: list[dict[str, object]] = []
    for line_number, line_index in enumerate(non_empty_line_indices, start=1):
        line_text = lines[line_index].strip()
        spans_for_line = [
            span for span in line_spans[line_index] if str(span.get("text", "")).strip()
        ] or [{"span_type": "TEXT", "text": line_text}]
        synthetic_nodes.append({
            "node_id": f"{parent_id}-L{line_number:02d}",
            "content_type": "TEXT",
            "bbox": deepcopy(parent_bbox) if isinstance(parent_bbox, dict) else
                {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
            "normalized_bbox": deepcopy(parent_normalized_bbox) if isinstance(parent_normalized_bbox, dict) else
                {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
            "bbox_is_estimated": True,
            "confidence": parent_confidence,
            "source_engine": parent_source_engine,
            "raw_text": line_text,
            "normalized_text": line_text,
            "spans": spans_for_line,
            "split_from_node_id": parent_id,
            "issues": [{
                "code": TEXT_LINE_SPLIT_ISSUE_CODE,
                "severity": "info",
                "message": (
                    f"Split from multi-line block {parent_id} for problem-unit structure "
                    "detection; bbox is inherited from the parent block, not measured per line."
                ),
            }],
            "layout": {},
        })
    return synthetic_nodes


def build_problem_unit_node(
    node_id: str,
    problem: ProblemCandidate,
    node_by_id: dict[str, dict[str, Any]],
    page_width: float,
    page_height: float,
) -> dict[str, object]:
    member_nodes = [node_by_id[member_id] for member_id in problem.member_ids() if member_id in node_by_id]
    boxes = [box for box in (bbox(node) for node in member_nodes) if box is not None]
    box = union_bbox(boxes) if boxes else {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    confidences = [
        float(node["confidence"])
        for node in member_nodes
        if isinstance(node.get("confidence"), (int, float)) and not isinstance(node.get("confidence"), bool)
    ]

    stem_node_ids = problem.ids_with_role("stem")
    condition_node_ids = problem.ids_with_role("condition")
    bogi_node_ids = problem.ids_with_role("bogi")
    choice_node_ids = problem.ids_with_role("choices")
    choice_node_id = choice_node_ids[0] if choice_node_ids else None

    stem_text = " ".join(
        text
        for node_id_ in stem_node_ids
        if (text := node_text(node_by_id.get(node_id_)))
    )
    condition_items = [
        item
        for node_id_ in condition_node_ids
        for item in parse_condition_items(node_by_id.get(node_id_))
    ]
    bogi_items = [
        item
        for node_id_ in bogi_node_ids
        for item in parse_bogi_items(node_by_id.get(node_id_))
    ]

    issues = [{
        "code": "PROBLEM_UNIT_DETECTED",
        "severity": "info",
        "message": "Text-pattern evidence (stem start marker + answer structure) indicates a problem unit.",
    }]

    choice_options: list[dict[str, object]] = []
    choice_raw_text = None
    if choice_node_ids:
        choice_raw_text = " ".join(
            text
            for node_id_ in choice_node_ids
            if (text := node_text(node_by_id.get(node_id_)))
        )
        choice_options = parse_choice_options(choice_raw_text)
        encountered_labels = [option["label"] for option in choice_options]
        choice_options = sorted(
            choice_options,
            key=lambda option: CHOICE_LABEL_ORDER.index(option["label"])
            if option["label"] in CHOICE_LABEL_ORDER
            else len(CHOICE_LABEL_ORDER),
        )
        if [option["label"] for option in choice_options] != encountered_labels:
            issues.append({
                "code": "VL_CHOICE_OPTIONS_REORDERED",
                "severity": "info",
                "message": (
                    "Choice options were not encountered in ①-⑤ order across the source "
                    "blocks (a choice row split across multiple OCR blocks with scrambled "
                    "reading order); reordered here by label. Original block order is "
                    "preserved in choice_node_ids."
                ),
            })
        if len(choice_options) < EXPECTED_CHOICE_OPTION_COUNT:
            issues.append({
                "code": "CHOICE_OPTION_SPLIT_INCOMPLETE",
                "severity": "warning",
                "message": (
                    f"Only {len(choice_options)} of {EXPECTED_CHOICE_OPTION_COUNT} expected choice "
                    "options were split from OCR text; a circled-digit marker may have been misread."
                ),
            })

    return {
        "node_id": node_id,
        "content_type": "UNKNOWN",
        "bbox": box,
        "normalized_bbox": normalize_bbox(box, page_width, page_height),
        "reading_order_index": 0,
        "confidence": round(mean(confidences), 6) if confidences else 0.0,
        "source_engine": PROBLEM_UNIT_ENGINE_ID,
        "issues": issues,
        "embedded_text_nodes": problem.member_ids(),
        "layout": {
            "structure_label": PROBLEM_UNIT_STRUCTURE_LABEL,
            "is_problem_unit": True,
            "problem_start_kind": problem.start_kind,
            "problem_marker_node_id": problem.marker_node_id,
            "answer_structure_type": problem.answer_structure_type,
            "stem_node_ids": stem_node_ids,
            "stem_text": stem_text,
            "condition_node_ids": condition_node_ids,
            "condition_items": condition_items,
            "bogi_node_ids": bogi_node_ids,
            "bogi_items": bogi_items,
            "choice_node_id": choice_node_id,
            "choice_node_ids": choice_node_ids,
            "choice_raw_text": choice_raw_text,
            "choice_options": choice_options,
        },
    }


def node_text(node: dict[str, Any] | None) -> str:
    if node is None:
        return ""
    return str(node.get("normalized_text", "")).strip()


def parse_condition_items(node: dict[str, Any] | None) -> list[dict[str, object]]:
    if node is None:
        return []
    text = node_text(node)
    matches = CONDITION_ITEM_SPLIT_PATTERN.findall(text)
    if not matches:
        return [{"node_id": node.get("node_id"), "label": None, "text": text}]
    return [
        {"node_id": node.get("node_id"), "label": f"({label})", "text": item_text.strip()}
        for label, item_text in matches
    ]


def parse_bogi_items(node: dict[str, Any] | None) -> list[dict[str, object]]:
    if node is None:
        return []
    text = node_text(node)
    matches = BOGI_ITEM_SPLIT_PATTERN.findall(text)
    if not matches:
        return [{"node_id": node.get("node_id"), "label": None, "text": text}]
    return [
        {"node_id": node.get("node_id"), "label": label, "text": item_text.strip()}
        for label, item_text in matches
    ]


def parse_choice_options(text: str) -> list[dict[str, object]]:
    options = []
    for label, rest in CHOICE_OPTION_SPLIT_PATTERN.findall(text):
        options.append({"label": label, "text": rest.strip()})
    return options


def mark_member_nodes(
    node_by_id: dict[str, dict[str, Any]],
    problem: ProblemCandidate,
    problem_node_id: str,
) -> None:
    for member_id, role in problem.member_roles.items():
        node = node_by_id.get(member_id)
        if node is None:
            continue
        node.pop("reading_order_index", None)
        node["is_primary_reading_order_candidate"] = False
        node["parent_structure_node_id"] = problem_node_id
        layout = ensure_layout(node)
        layout["problem_unit_role"] = role
        layout["promoted_into_structure_node_id"] = problem_node_id
        issues = node.get("issues")
        if not isinstance(issues, list):
            issues = []
            node["issues"] = issues
        issues.append({
            "code": "TEXT_EMBEDDED_IN_PROBLEM_UNIT",
            "severity": "info",
            "message": f"OCR TEXT node is embedded in detected problem unit {problem_node_id} with role '{role}'.",
        })


def rebuild_reading_order(
    reading_order: list[str],
    built: list[tuple[ProblemCandidate, dict[str, object]]],
    replaced_ids: set[str],
) -> list[str]:
    index_by_id = {node_id: index for index, node_id in enumerate(reading_order)}
    insertion_by_index: dict[int, list[str]] = {}
    for problem, problem_node in built:
        first_index = index_by_id.get(problem.marker_node_id, len(reading_order))
        insertion_by_index.setdefault(first_index, []).append(str(problem_node["node_id"]))

    new_order: list[str] = []
    seen: set[str] = set()
    for index, node_id in enumerate(reading_order):
        for new_id in insertion_by_index.get(index, []):
            if new_id not in seen:
                new_order.append(new_id)
                seen.add(new_id)
        if node_id in replaced_ids or node_id in seen:
            continue
        new_order.append(node_id)
        seen.add(node_id)
    return new_order


def reindex_primary_nodes(nodes: list[dict[str, Any]], reading_order: list[str]) -> None:
    index_by_id = {node_id: index for index, node_id in enumerate(reading_order)}
    for node in nodes:
        node_id = node.get("node_id")
        if isinstance(node_id, str) and node_id in index_by_id:
            node["reading_order_index"] = index_by_id[node_id]


def problem_unit_report(payload: dict[str, object]) -> dict[str, object]:
    page_reports = []
    total_problem_count = 0
    for page in payload.get("pages", []):
        if not isinstance(page, dict):
            continue
        problems = []
        for node in page.get("nodes", []):
            if not isinstance(node, dict):
                continue
            layout = node.get("layout")
            if not isinstance(layout, dict) or layout.get("structure_label") != PROBLEM_UNIT_STRUCTURE_LABEL:
                continue
            problems.append({
                "node_id": node.get("node_id"),
                "start_kind": layout.get("problem_start_kind"),
                "answer_structure_type": layout.get("answer_structure_type"),
                "stem_text": layout.get("stem_text"),
                "condition_item_count": len(layout.get("condition_items") or []),
                "bogi_item_count": len(layout.get("bogi_items") or []),
                "has_choices": layout.get("choice_node_id") is not None,
                "choice_option_count": len(layout.get("choice_options") or []),
                "choice_option_split_incomplete": any(
                    isinstance(issue, dict) and issue.get("code") == "CHOICE_OPTION_SPLIT_INCOMPLETE"
                    for issue in (node.get("issues") or [])
                ),
            })
        total_problem_count += len(problems)
        page_reports.append({
            "page_id": page.get("page_id"),
            "problem_count": len(problems),
            "problems": problems,
        })
    return {
        "total_problem_count": total_problem_count,
        "page_count": len(page_reports),
        "pages": page_reports,
    }


def ensure_layout(node: dict[str, Any]) -> dict[str, object]:
    layout = node.get("layout")
    if not isinstance(layout, dict):
        layout = {}
        node["layout"] = layout
    return layout


def bbox(node: dict[str, Any]) -> dict[str, float] | None:
    raw = node.get("bbox")
    if not isinstance(raw, dict):
        return None
    values = {key: number_value(raw.get(key)) for key in ("x", "y", "width", "height")}
    if any(value is None for value in values.values()):
        return None
    return {key: float(value) for key, value in values.items() if value is not None}


def union_bbox(boxes: list[dict[str, float]]) -> dict[str, float]:
    min_x = min(box["x"] for box in boxes)
    min_y = min(box["y"] for box in boxes)
    max_x = max(box["x"] + box["width"] for box in boxes)
    max_y = max(box["y"] + box["height"] for box in boxes)
    return {
        "x": round(min_x, 3),
        "y": round(min_y, 3),
        "width": round(max_x - min_x, 3),
        "height": round(max_y - min_y, 3),
    }


def normalize_bbox(box: dict[str, float], page_width: float, page_height: float) -> dict[str, float]:
    if page_width <= 0 or page_height <= 0:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    return {
        "x": round(box["x"] / page_width, 6),
        "y": round(box["y"] / page_height, 6),
        "width": round(box["width"] / page_width, 6),
        "height": round(box["height"] / page_height, 6),
    }


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
