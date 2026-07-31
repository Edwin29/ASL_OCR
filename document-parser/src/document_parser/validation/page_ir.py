from __future__ import annotations

from typing import Any


CONTENT_TYPES = {"TEXT", "MATH", "TABLE", "UNSUPPORTED_VISUAL", "UNKNOWN"}
QUALITY_STATUSES = {"PASS", "PASS_WITH_CORRECTION", "LOW_QUALITY", "REJECTED"}
ISSUE_SEVERITIES = {"info", "warning", "error"}


def validate_document_ir(payload: dict[str, object]) -> dict[str, object]:
    """Validate core Page IR invariants without requiring external JSON Schema dependencies."""

    counts = {
        "required_field_missing_count": 0,
        "type_error_count": 0,
        "coordinate_missing_node_count": 0,
        "bbox_invalid_count": 0,
        "normalized_bbox_out_of_range_count": 0,
        "confidence_invalid_count": 0,
        "duplicate_node_id_count": 0,
        "invalid_reading_order_ref_count": 0,
        "missing_reading_order_node_count": 0,
        "reading_order_duplicate_count": 0,
        "reading_order_index_mismatch_count": 0,
        "invalid_embedded_text_ref_count": 0,
        "quality_status_invalid_count": 0,
        "issue_invalid_count": 0,
    }

    pages = payload.get("pages")
    manifest = payload.get("document_manifest")
    if not isinstance(pages, list):
        pages = []
        counts["required_field_missing_count"] += 1
        counts["type_error_count"] += 1
    if not isinstance(manifest, dict):
        manifest = {}
        counts["required_field_missing_count"] += 1
        counts["type_error_count"] += 1

    manifest_page_count = manifest.get("page_count")
    page_count_mismatch = manifest_page_count != len(pages)

    for page in pages:
        if not isinstance(page, dict):
            counts["type_error_count"] += 1
            continue
        _validate_page(page, counts)

    schema_valid = (
        all(value == 0 for value in counts.values())
        and not page_count_mismatch
    )
    return {
        "schema_valid": schema_valid,
        "validation_performed": True,
        "coordinate_missing_node_count": counts["coordinate_missing_node_count"],
        "reading_order_cycle_count": counts["reading_order_duplicate_count"],
        "invalid_reading_order_ref_count": counts["invalid_reading_order_ref_count"],
        "missing_reading_order_node_count": counts["missing_reading_order_node_count"],
        "duplicate_node_id_count": counts["duplicate_node_id_count"],
        "required_field_missing_count": counts["required_field_missing_count"],
        "type_error_count": counts["type_error_count"],
        "bbox_invalid_count": counts["bbox_invalid_count"],
        "normalized_bbox_out_of_range_count": counts["normalized_bbox_out_of_range_count"],
        "confidence_invalid_count": counts["confidence_invalid_count"],
        "reading_order_index_mismatch_count": counts["reading_order_index_mismatch_count"],
        "invalid_embedded_text_ref_count": counts["invalid_embedded_text_ref_count"],
        "quality_status_invalid_count": counts["quality_status_invalid_count"],
        "issue_invalid_count": counts["issue_invalid_count"],
        "page_count_mismatch": page_count_mismatch,
        "page_count": len(pages),
    }


def _validate_page(page: dict[str, Any], counts: dict[str, int]) -> None:
    _require_type(page, "page_id", str, counts)
    geometry = _require_type(page, "page_geometry", dict, counts)
    nodes = _require_type(page, "nodes", list, counts) or []
    reading_order = _require_type(page, "reading_order", list, counts) or []
    parse_issues = _require_type(page, "parse_issues", list, counts) or []
    quality_report = _require_type(page, "quality_report", dict, counts)

    page_width = None
    page_height = None
    if isinstance(geometry, dict):
        page_width = geometry.get("width")
        page_height = geometry.get("height")
        if not _is_positive_int(page_width):
            counts["type_error_count"] += 1
        if not _is_positive_int(page_height):
            counts["type_error_count"] += 1

    if isinstance(quality_report, dict):
        status = quality_report.get("status")
        if status not in QUALITY_STATUSES:
            counts["quality_status_invalid_count"] += 1

    for issue in parse_issues:
        _validate_issue(issue, counts)

    node_ids: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            counts["type_error_count"] += 1
            continue
        node_id = _validate_node(node, page_width, page_height, counts)
        if node_id is not None:
            node_ids.append(node_id)

    node_id_set = set(node_ids)
    counts["duplicate_node_id_count"] += len(node_ids) - len(node_id_set)
    embedded_node_ids = embedded_text_node_ids(nodes, node_id_set, counts)
    replacement_evidence_node_ids = split_ocr_replacement_evidence_node_ids(nodes, node_id_set, counts)
    ordered_ids = [item for item in reading_order if isinstance(item, str)]
    counts["type_error_count"] += len(reading_order) - len(ordered_ids)
    ordered_id_set = set(ordered_ids)
    counts["invalid_reading_order_ref_count"] += sum(1 for item in ordered_ids if item not in node_id_set)
    counts["missing_reading_order_node_count"] += sum(
        1
        for item in node_id_set
        if item not in ordered_id_set and item not in embedded_node_ids and item not in replacement_evidence_node_ids
    )
    counts["reading_order_duplicate_count"] += len(ordered_ids) - len(ordered_id_set)

    order_index_by_id = {node_id: index for index, node_id in enumerate(ordered_ids)}
    for node in nodes:
        if isinstance(node, dict):
            node_id = node.get("node_id")
            reading_order_index = node.get("reading_order_index")
            if (
                isinstance(node_id, str)
                and node_id in order_index_by_id
                and isinstance(reading_order_index, int)
                and reading_order_index != order_index_by_id[node_id]
            ):
                counts["reading_order_index_mismatch_count"] += 1


def embedded_text_node_ids(
    nodes: list[object],
    node_id_set: set[str],
    counts: dict[str, int],
) -> set[str]:
    embedded_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or node.get("content_type") not in {"TABLE", "MATH", "UNSUPPORTED_VISUAL", "UNKNOWN"}:
            continue
        raw_embedded_ids = node.get("embedded_text_nodes")
        if raw_embedded_ids is None:
            continue
        if not isinstance(raw_embedded_ids, list):
            counts["type_error_count"] += 1
            continue
        for embedded_id in raw_embedded_ids:
            if not isinstance(embedded_id, str):
                counts["type_error_count"] += 1
            elif embedded_id not in node_id_set:
                counts["invalid_embedded_text_ref_count"] += 1
            else:
                embedded_ids.add(embedded_id)
    return embedded_ids


def split_ocr_replacement_evidence_node_ids(
    nodes: list[object],
    node_id_set: set[str],
    counts: dict[str, int],
) -> set[str]:
    evidence_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or node.get("content_type") != "TEXT":
            continue
        if node.get("is_primary_reading_order_candidate") is not False:
            continue
        node_id = node.get("node_id")
        layout = node.get("layout")
        if not isinstance(node_id, str) or not isinstance(layout, dict):
            continue
        refs = layout.get("split_ocr_replaced_by_node_ids")
        if refs is None:
            continue
        if not isinstance(refs, list) or not refs:
            counts["type_error_count"] += 1
            continue
        valid_refs = True
        for ref in refs:
            if not isinstance(ref, str):
                counts["type_error_count"] += 1
                valid_refs = False
            elif ref not in node_id_set:
                counts["invalid_reading_order_ref_count"] += 1
                valid_refs = False
        if valid_refs:
            evidence_ids.add(node_id)
    return evidence_ids


def _validate_node(
    node: dict[str, Any],
    page_width: object,
    page_height: object,
    counts: dict[str, int],
) -> str | None:
    node_id = _require_type(node, "node_id", str, counts)
    content_type = _require_type(node, "content_type", str, counts)
    if isinstance(content_type, str) and content_type not in CONTENT_TYPES:
        counts["type_error_count"] += 1

    bbox = _require_type(node, "bbox", dict, counts)
    normalized_bbox = _require_type(node, "normalized_bbox", dict, counts)
    if not isinstance(bbox, dict) or not isinstance(normalized_bbox, dict):
        counts["coordinate_missing_node_count"] += 1
    else:
        if not _valid_bbox(bbox):
            counts["bbox_invalid_count"] += 1
        elif _is_positive_int(page_width) and _is_positive_int(page_height):
            if bbox["x"] + bbox["width"] > page_width or bbox["y"] + bbox["height"] > page_height:
                counts["bbox_invalid_count"] += 1
        if not _valid_normalized_bbox(normalized_bbox):
            counts["normalized_bbox_out_of_range_count"] += 1

    confidence = _require_number(node, "confidence", counts)
    if confidence is not None and not 0 <= confidence <= 1:
        counts["confidence_invalid_count"] += 1

    _require_type(node, "source_engine", str, counts)
    issues = _require_type(node, "issues", list, counts)
    if isinstance(issues, list):
        for issue in issues:
            _validate_issue(issue, counts)
    return node_id if isinstance(node_id, str) else None


def _validate_issue(issue: object, counts: dict[str, int]) -> None:
    if not isinstance(issue, dict):
        counts["issue_invalid_count"] += 1
        return
    if not isinstance(issue.get("code"), str):
        counts["issue_invalid_count"] += 1
    severity = issue.get("severity")
    if severity not in ISSUE_SEVERITIES:
        counts["issue_invalid_count"] += 1


def _require_type(
    payload: dict[str, Any],
    key: str,
    expected_type: type,
    counts: dict[str, int],
) -> object | None:
    if key not in payload:
        counts["required_field_missing_count"] += 1
        return None
    value = payload[key]
    if not isinstance(value, expected_type):
        counts["type_error_count"] += 1
        return None
    return value


def _require_number(payload: dict[str, Any], key: str, counts: dict[str, int]) -> float | None:
    if key not in payload:
        counts["required_field_missing_count"] += 1
        return None
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        counts["type_error_count"] += 1
        return None
    return float(value)


def _valid_bbox(bbox: dict[str, Any]) -> bool:
    values = [_number_value(bbox.get(key)) for key in ("x", "y", "width", "height")]
    if any(value is None for value in values):
        return False
    x, y, width, height = values
    return bool(x is not None and y is not None and x >= 0 and y >= 0 and width >= 0 and height >= 0)


def _valid_normalized_bbox(bbox: dict[str, Any]) -> bool:
    values = [_number_value(bbox.get(key)) for key in ("x", "y", "width", "height")]
    if any(value is None for value in values):
        return False
    x, y, width, height = values
    if x is None or y is None or width is None or height is None:
        return False
    return x >= 0 and y >= 0 and width >= 0 and height >= 0 and x + width <= 1 and y + height <= 1


def _number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0
