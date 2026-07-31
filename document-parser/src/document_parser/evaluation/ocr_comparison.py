from __future__ import annotations

from typing import Any

from document_parser.evaluation.ocr_quality import build_ocr_quality_report


def build_ocr_comparison_report(
    baseline_payload: dict[str, object],
    candidate_payload: dict[str, object],
    low_confidence_threshold: float = 0.5,
) -> dict[str, object]:
    baseline_quality = build_ocr_quality_report(
        baseline_payload,
        low_confidence_threshold=low_confidence_threshold,
    )
    candidate_quality = build_ocr_quality_report(
        candidate_payload,
        low_confidence_threshold=low_confidence_threshold,
    )
    baseline_pages = pages_by_id(baseline_quality)
    candidate_pages = pages_by_id(candidate_quality)
    page_ids = sorted(set(baseline_pages) | set(candidate_pages))
    page_comparisons = [
        compare_page(page_id, baseline_pages.get(page_id), candidate_pages.get(page_id))
        for page_id in page_ids
    ]
    verdict_counts = count_verdicts(page_comparisons)
    return {
        "report_type": "ocr_comparison",
        "baseline_engine": engine_summary(baseline_payload),
        "candidate_engine": engine_summary(candidate_payload),
        "low_confidence_threshold": low_confidence_threshold,
        "page_count": len(page_comparisons),
        "baseline_totals": totals_summary(baseline_quality),
        "candidate_totals": totals_summary(candidate_quality),
        "deltas": totals_delta(baseline_quality, candidate_quality),
        "verdict_counts": verdict_counts,
        "recommendation": recommendation_from_counts(verdict_counts),
        "pages": page_comparisons,
    }


def compare_page(
    page_id: str,
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> dict[str, object]:
    if baseline is None:
        return {
            "page_id": page_id,
            "status": "CANDIDATE_ONLY",
            "verdict": "REVIEW",
            "baseline": None,
            "candidate": page_metrics(candidate),
            "deltas": None,
            "reasons": ["Baseline result is missing for this page."],
        }
    if candidate is None:
        return {
            "page_id": page_id,
            "status": "BASELINE_ONLY",
            "verdict": "BASELINE_PREFERRED",
            "baseline": page_metrics(baseline),
            "candidate": None,
            "deltas": None,
            "reasons": ["Candidate result is missing for this page."],
        }

    baseline_metrics = page_metrics(baseline)
    candidate_metrics = page_metrics(candidate)
    deltas = page_deltas(baseline_metrics, candidate_metrics)
    verdict, reasons = page_verdict(baseline_metrics, candidate_metrics, deltas)
    return {
        "page_id": page_id,
        "status": "COMPARED",
        "verdict": verdict,
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
        "deltas": deltas,
        "reasons": reasons,
    }


def page_verdict(
    baseline: dict[str, object],
    candidate: dict[str, object],
    deltas: dict[str, object],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    baseline_score = float(baseline["diagnostic_score"])
    candidate_score = float(candidate["diagnostic_score"])
    score_delta = float(deltas["diagnostic_score"])
    mean_confidence_delta = numeric_delta(baseline.get("mean_confidence"), candidate.get("mean_confidence"))
    node_count_delta_ratio = ratio_delta(int(baseline["node_count"]), int(candidate["node_count"]))

    if score_delta <= -2:
        reasons.append("Candidate has materially fewer low-confidence or layout-warning diagnostics.")
    elif score_delta >= 2:
        reasons.append("Candidate has materially more low-confidence or layout-warning diagnostics.")

    if mean_confidence_delta is not None:
        if mean_confidence_delta >= 0.05:
            reasons.append("Candidate mean confidence is higher.")
        elif mean_confidence_delta <= -0.05:
            reasons.append("Candidate mean confidence is lower.")

    if abs(node_count_delta_ratio) >= 0.45:
        reasons.append("Node count changed sharply and needs visual review.")
        return "REVIEW", reasons

    if candidate_score < baseline_score and (mean_confidence_delta is None or mean_confidence_delta >= -0.08):
        return "CANDIDATE_PREFERRED", reasons or ["Candidate diagnostic score is lower."]
    if candidate_score > baseline_score and (mean_confidence_delta is None or mean_confidence_delta <= 0.08):
        return "BASELINE_PREFERRED", reasons or ["Baseline diagnostic score is lower."]
    if mean_confidence_delta is not None and mean_confidence_delta >= 0.08 and candidate_score <= baseline_score + 1:
        return "CANDIDATE_PREFERRED", reasons or ["Candidate confidence is higher without a diagnostic penalty."]
    if mean_confidence_delta is not None and mean_confidence_delta <= -0.08 and baseline_score <= candidate_score + 1:
        return "BASELINE_PREFERRED", reasons or ["Baseline confidence is higher without a diagnostic penalty."]
    return "TIE_OR_REVIEW", reasons or ["Metrics are close enough to require overlay review."]


def page_metrics(page: dict[str, Any] | None) -> dict[str, object] | None:
    if page is None:
        return None
    node_count = int(page["node_count"])
    low_confidence_node_count = int(page["low_confidence_node_count"])
    reading_order_warning_count = int(page["reading_order_warning_count"])
    region_separation_warning_count = int(page["region_separation_warning_count"])
    overlap_warning_count = int(page["overlap_warning_count"])
    suspicious_shape_node_count = int(page["suspicious_shape_node_count"])
    return {
        "node_count": node_count,
        "mean_confidence": page.get("mean_confidence"),
        "min_confidence": page.get("min_confidence"),
        "low_confidence_node_count": low_confidence_node_count,
        "low_confidence_rate": round(low_confidence_node_count / node_count, 6) if node_count else None,
        "reading_order_warning_count": reading_order_warning_count,
        "region_separation_warning_count": region_separation_warning_count,
        "overlap_warning_count": overlap_warning_count,
        "suspicious_shape_node_count": suspicious_shape_node_count,
        "diagnostic_score": diagnostic_score(page),
        "parse_issue_codes": page.get("parse_issue_codes", []),
    }


def page_deltas(
    baseline: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    return {
        "node_count": int(candidate["node_count"]) - int(baseline["node_count"]),
        "mean_confidence": numeric_delta(baseline.get("mean_confidence"), candidate.get("mean_confidence")),
        "min_confidence": numeric_delta(baseline.get("min_confidence"), candidate.get("min_confidence")),
        "low_confidence_node_count": int(candidate["low_confidence_node_count"]) - int(baseline["low_confidence_node_count"]),
        "reading_order_warning_count": int(candidate["reading_order_warning_count"]) - int(baseline["reading_order_warning_count"]),
        "region_separation_warning_count": int(candidate["region_separation_warning_count"]) - int(baseline["region_separation_warning_count"]),
        "overlap_warning_count": int(candidate["overlap_warning_count"]) - int(baseline["overlap_warning_count"]),
        "suspicious_shape_node_count": int(candidate["suspicious_shape_node_count"]) - int(baseline["suspicious_shape_node_count"]),
        "diagnostic_score": round(float(candidate["diagnostic_score"]) - float(baseline["diagnostic_score"]), 6),
    }


def diagnostic_score(page: dict[str, Any]) -> float:
    return float(
        int(page["low_confidence_node_count"])
        + int(page["reading_order_warning_count"])
        + int(page["region_separation_warning_count"])
        + int(page["overlap_warning_count"])
    )


def totals_summary(report: dict[str, object]) -> dict[str, object]:
    total_nodes = int(report["total_node_count"])
    total_low_confidence = int(report["total_low_confidence_node_count"])
    total_reading_order = int(report["total_reading_order_warning_count"])
    total_region = int(report["total_region_separation_warning_count"])
    pages = [page for page in report["pages"] if isinstance(page, dict)]
    total_overlap = sum(int(page["overlap_warning_count"]) for page in pages)
    diagnostic_total = total_low_confidence + total_reading_order + total_region + total_overlap
    return {
        "page_count": int(report["page_count"]),
        "node_count": total_nodes,
        "low_confidence_node_count": total_low_confidence,
        "low_confidence_rate": round(total_low_confidence / total_nodes, 6) if total_nodes else None,
        "reading_order_warning_count": total_reading_order,
        "region_separation_warning_count": total_region,
        "overlap_warning_count": total_overlap,
        "diagnostic_score": diagnostic_total,
    }


def totals_delta(
    baseline: dict[str, object],
    candidate: dict[str, object],
) -> dict[str, object]:
    baseline_totals = totals_summary(baseline)
    candidate_totals = totals_summary(candidate)
    return {
        key: numeric_delta(baseline_totals.get(key), candidate_totals.get(key))
        for key in (
            "node_count",
            "low_confidence_node_count",
            "low_confidence_rate",
            "reading_order_warning_count",
            "region_separation_warning_count",
            "overlap_warning_count",
            "diagnostic_score",
        )
    }


def pages_by_id(report: dict[str, object]) -> dict[str, dict[str, Any]]:
    return {
        str(page["page_id"]): page
        for page in report["pages"]
        if isinstance(page, dict) and isinstance(page.get("page_id"), str)
    }


def engine_summary(payload: dict[str, object]) -> dict[str, object]:
    manifest = payload.get("engine_manifest")
    if not isinstance(manifest, dict):
        return {"engine_id": "unknown", "engine_version": "unknown"}
    general_ocr = manifest.get("general_ocr")
    if not isinstance(general_ocr, dict):
        return {"engine_id": "unknown", "engine_version": "unknown"}
    return {
        "engine_id": general_ocr.get("engine_id", "unknown"),
        "engine_version": general_ocr.get("engine_version", "unknown"),
    }


def count_verdicts(page_comparisons: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for comparison in page_comparisons:
        verdict = str(comparison.get("verdict", "UNKNOWN"))
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def recommendation_from_counts(counts: dict[str, int]) -> str:
    candidate = counts.get("CANDIDATE_PREFERRED", 0)
    baseline = counts.get("BASELINE_PREFERRED", 0)
    review = counts.get("REVIEW", 0) + counts.get("TIE_OR_REVIEW", 0)
    if candidate > baseline and review <= candidate:
        return "CANDIDATE_CAN_ADVANCE_TO_OVERLAY_REVIEW"
    if baseline > candidate:
        return "KEEP_BASELINE_PENDING_ENGINE_TUNING"
    return "REVIEW_REQUIRED_BEFORE_DEFAULT_SWITCH"


def numeric_delta(left: object, right: object) -> float | None:
    if isinstance(left, bool) or isinstance(right, bool):
        return None
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return None
    return round(float(right) - float(left), 6)


def ratio_delta(baseline: int, candidate: int) -> float:
    if baseline == 0:
        return 1.0 if candidate else 0.0
    return (candidate - baseline) / baseline
