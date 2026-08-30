"""Aggregate the completed 8-side Phase A extraction experiment."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


EXTRACTIONS = ("oracle", "overlap", "seam_confirmed", "seam_conservative")


def _aggregate(items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "count": len(items),
        "mean_text_similarity": statistics.fmean(float(item["text_similarity"]) for item in items),
        "min_text_similarity": min(float(item["text_similarity"]) for item in items),
        "max_character_drop_fraction": max(float(item["character_count_drop_fraction"]) for item in items),
        "mean_node_sequence_similarity": statistics.fmean(
            float(item["node_sequence_similarity"]) for item in items
        ),
        "min_node_sequence_similarity": min(float(item["node_sequence_similarity"]) for item in items),
    }


def evaluate(summary: dict[str, object], extraction_manifest: dict[str, object]) -> dict[str, object]:
    comparison_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in summary.get("comparisons", []):
        comparison_groups[str(item["extraction"])].append(item["comparison"])
    aggregate = {key: _aggregate(comparison_groups[key]) for key in EXTRACTIONS}

    repeat_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in summary.get("repeated_capture_comparisons", []):
        identifier = str(item["first_artifact_id"])
        extraction = next(key for key in EXTRACTIONS if f"_{key}_none_none" in identifier)
        repeat_groups[extraction].append(item["comparison"])
    repeat = {
        key: {
            "count": len(repeat_groups[key]),
            "mean_text_similarity": statistics.fmean(
                float(item["text_similarity"]) for item in repeat_groups[key]
            ),
            "mean_node_sequence_similarity": statistics.fmean(
                float(item["node_sequence_similarity"]) for item in repeat_groups[key]
            ),
            "details": repeat_groups[key],
        }
        for key in EXTRACTIONS
    }

    mask_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in extraction_manifest.get("artifacts", []):
        metrics = item.get("source", {}).get("label_metrics")
        if isinstance(metrics, dict):
            mask_groups[str(item["extraction"])].append(metrics)
    mask = {
        key: {
            "mean_own_page_recall": statistics.fmean(float(item["own_page_recall"]) for item in mask_groups[key]),
            "min_own_page_recall": min(float(item["own_page_recall"]) for item in mask_groups[key]),
            "mean_opposite_page_inclusion_ratio": statistics.fmean(
                float(item["opposite_page_inclusion_ratio"]) for item in mask_groups[key]
            ),
        }
        for key in EXTRACTIONS
    }

    results = list(summary.get("results", []))
    criteria = {
        "phase_a_32_complete": len(results) == 32 and all(item.get("status") == "COMPLETE" for item in results),
        "schema_valid_32_of_32": len(results) == 32 and all(bool(item.get("schema_valid")) for item in results),
        "seam_conservative_character_drop_at_most_20_percent": (
            aggregate["seam_conservative"]["max_character_drop_fraction"] <= 0.20
        ),
        "seam_conservative_reduces_opposite_page_inclusion": (
            mask["seam_conservative"]["mean_opposite_page_inclusion_ratio"]
            < mask["overlap"]["mean_opposite_page_inclusion_ratio"]
        ),
        "repeat_text_stability_not_below_overlap": (
            repeat["seam_conservative"]["mean_text_similarity"]
            >= repeat["overlap"]["mean_text_similarity"]
        ),
        "repeat_node_stability_not_below_overlap": (
            repeat["seam_conservative"]["mean_node_sequence_similarity"]
            >= repeat["overlap"]["mean_node_sequence_similarity"]
        ),
        "manual_golden_verified": False,
    }
    if not criteria["phase_a_32_complete"] or not criteria["schema_valid_32_of_32"]:
        verdict = "TECHNICAL_FAILURE"
    elif not criteria["seam_conservative_character_drop_at_most_20_percent"]:
        verdict = "OVERLAP_FALLBACK"
    elif all(criteria.values()):
        verdict = "SEAM_OCR_CANDIDATE"
    else:
        verdict = "EXTRACTION_INCONCLUSIVE_NO_GROUND_TRUTH"
    return {
        "schema_version": 1,
        "verdict": verdict,
        "criteria": criteria,
        "oracle_relative_metrics": aggregate,
        "repeat_capture_metrics": repeat,
        "mask_metrics": mask,
        "accuracy_claim_allowed": False,
        "manual_golden_status": "MANUAL_GOLDEN_NOT_VERIFIED",
        "interpretation": (
            "Seam-conservative is the leading automatic crop candidate, but repeat node segmentation "
            "is less stable than overlap and exact golden transcription is absent."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--extraction-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.summary.read_text(encoding="utf-8")),
        json.loads(args.extraction_manifest.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": result["verdict"], "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if result["verdict"] != "TECHNICAL_FAILURE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
