"""Summarize V3-A.4 replay without turning diagnostic evidence into activation."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from book_scanner.evaluation.footer_identity_statistics import zero_error_upper_bound


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    replay = _read_json(args.replay)
    observations = _read_json(args.observations)
    manifest = _read_json(args.manifest)

    timings = _descriptor_timings(observations)
    candidates = []
    for setting in replay["settings"]:
        if setting["status"] != "MEASURED" or int(setting["n"]) > int(manifest["candidate_gate"]["max_nominal_n"]):
            continue
        if not setting["p_same_gt_p_different"] or not setting["every_relation_separated"]:
            continue
        if setting["method"] in {"semantic_key", "full_page_visual_gate_baseline"}:
            continue
        for threshold in setting["thresholds"]:
            if threshold["false_duplicate_count"] == 0 and threshold["false_different_count"] == 0:
                candidates.append(
                    {
                        "cadence_ms": setting["cadence_ms"],
                        "n": setting["n"],
                        "stage": setting["stage"],
                        "method": setting["method"],
                        "k_different": threshold["k_different"],
                        "k_same": threshold["k_same"],
                        "unknown_count": threshold["unknown_count"],
                        "p_same": setting["same_statistics"]["point_estimate"],
                        "p_different": setting["different_statistics"]["point_estimate"],
                        "same_effective_n": setting["same_statistics"]["effective_sample_size"],
                        "different_effective_n": setting["different_statistics"]["effective_sample_size"],
                        "median_first_decision_samples": statistics.median(
                            item["first_decision_sample"] for item in threshold["decisions"]
                        ),
                        "median_first_decision_delay_ms": statistics.median(
                            item["first_decision_sample"] for item in threshold["decisions"]
                        ) * setting["cadence_ms"],
                    }
                )
    candidates.sort(
        key=lambda item: (
            item["unknown_count"],
            -item["n"],
            item["cadence_ms"],
            0 if item["k_different"] == 0 and item["k_same"] == 1 else 1,
            -(item["p_same"] - item["p_different"]),
            item["method"],
        )
    )
    max_descriptor = float(manifest["candidate_gate"]["max_visual_descriptor_median_ms_per_side"])
    timing_pass = all(value["median_ms_per_side"] <= max_descriptor for value in timings.values())
    status = "PROVISIONAL_CANDIDATE_DATA_INSUFFICIENT" if candidates and timing_pass else "NO_PROVISIONAL_CANDIDATE"
    payload = {
        "schema_version": 1,
        "status": status,
        "production_activation_allowed": False,
        "best_candidate": candidates[0] if candidates else None,
        "candidate_count": len(candidates),
        "top_candidates": candidates[:20],
        "descriptor_timings": timings,
        "descriptor_timing_gate_passed": timing_pass,
        "observed_different_relations": 2,
        "zero_false_duplicate_relation_level_95_upper_bound": zero_error_upper_bound(2),
        "interpretation": (
            "Two spread identities can rank candidates but cannot validate a general duplicate error rate. "
            "No scanner runtime or delivery behavior was activated."
        ),
        "limitations": manifest["limitations"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _descriptor_timings(observations: dict[str, Any]) -> dict[str, dict[str, float | int]]:
    by_stage: dict[str, list[float]] = {}
    for record in observations["records"]:
        if not record.get("eligible"):
            continue
        for stage, value in record.get("stages", {}).items():
            for side in value.get("sides", {}).values():
                timing = side.get("visual_descriptor_ms")
                if isinstance(timing, (int, float)):
                    by_stage.setdefault(stage, []).append(float(timing))
    return {
        stage: {
            "samples": len(values),
            "median_ms_per_side": statistics.median(values),
            "p95_ms_per_side": sorted(values)[min(len(values) - 1, int(0.95 * len(values)))],
        }
        for stage, values in by_stage.items()
        if values
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
