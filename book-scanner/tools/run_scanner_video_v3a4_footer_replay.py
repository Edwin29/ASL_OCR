"""Replay frozen V3-A.4 observations across cadence, N, method and thresholds."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from book_scanner.evaluation.footer_identity import FooterIdentityMethod, FooterVisualPolicy, query_match_indicators
from book_scanner.evaluation.footer_identity_replay import sample_block, score_threshold, threshold_grid
from book_scanner.evaluation.footer_identity_statistics import (
    block_bootstrap_mean_interval,
    effective_sample_size,
    lag_autocorrelations,
    wilson_interval,
)
from book_scanner.video.config import IdentityPolicy
from book_scanner.video.identity import (
    IdentityMatchKind,
    SpreadVisualFingerprint,
    VisualFingerprint,
    compare_visual_spreads,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    observations = _read_json(args.observations)
    manifest = _read_json(args.manifest)
    if observations.get("manifest_sha256") != _sha256(args.manifest):
        raise ValueError("observation/manifest SHA-256 mismatch")
    records = observations["records"]
    fps = float(manifest["source_video"]["fps"])
    policy = FooterVisualPolicy(**{key: value for key, value in manifest["visual_policy"].items() if key != "threshold_status"})
    bootstrap = manifest["statistics"]
    results: list[dict[str, Any]] = []
    for cadence_ms in manifest["cadence_ms"]:
        banks = {
            block_id: sample_block(records, block, fps=fps, cadence_ms=int(cadence_ms))
            for block_id, block in manifest["blocks"].items()
        }
        for nominal_n in manifest["nominal_n"]:
            n = int(nominal_n)
            for stage_name in manifest["capture"]["preview_stages"]:
                for method_name in manifest["methods"]:
                    method = FooterIdentityMethod(method_name)
                    relation_results: list[dict[str, Any]] = []
                    for relation in manifest["relations"]:
                        reference = banks[relation["reference_block"]]
                        query = banks[relation["query_block"]]
                        base = {
                            "relation_id": relation["relation_id"],
                            "expected": relation["expected"],
                            "reference_available": len(reference),
                            "query_available": len(query),
                        }
                        if len(reference) < n or len(query) < n:
                            relation_results.append({**base, "status": "NOT_MEASURED_INSUFFICIENT_WINDOW"})
                            continue
                        indicators = query_match_indicators(
                            reference[:n], query[:n], method, policy, stage_name=stage_name
                        )
                        relation_results.append(
                            {
                                **base,
                                "status": "MEASURED",
                                "reference_frame_indices": [int(item["frame_index"]) for item in reference[:n]],
                                "query_frame_indices": [int(item["frame_index"]) for item in query[:n]],
                                "indicators": [bool(item) for item in indicators],
                                "match_count": sum(indicators),
                                "match_rate": sum(indicators) / n,
                            }
                        )
                    results.append(
                        _setting_result(
                            cadence_ms=int(cadence_ms),
                            n=n,
                            stage_name=str(stage_name),
                            method=method,
                            relations=relation_results,
                            block_duration_ms=int(bootstrap["block_duration_ms"]),
                            iterations=int(bootstrap["block_bootstrap_iterations"]),
                            seed=int(bootstrap["seed"]),
                        )
                    )
            full_relations: list[dict[str, Any]] = []
            for relation in manifest["relations"]:
                reference = banks[relation["reference_block"]]
                query = banks[relation["query_block"]]
                base = {
                    "relation_id": relation["relation_id"],
                    "expected": relation["expected"],
                    "reference_available": len(reference),
                    "query_available": len(query),
                }
                if len(reference) < n or len(query) < n:
                    full_relations.append({**base, "status": "NOT_MEASURED_INSUFFICIENT_WINDOW"})
                    continue
                indicators = tuple(
                    any(_full_page_visual_match(ref, item) for ref in reference[:n]) for item in query[:n]
                )
                full_relations.append(
                    {
                        **base,
                        "status": "MEASURED",
                        "reference_frame_indices": [int(item["frame_index"]) for item in reference[:n]],
                        "query_frame_indices": [int(item["frame_index"]) for item in query[:n]],
                        "indicators": list(indicators),
                        "match_count": sum(indicators),
                        "match_rate": sum(indicators) / n,
                    }
                )
            results.append(
                _setting_result(
                    cadence_ms=int(cadence_ms),
                    n=n,
                    stage_name="full_preview",
                    method="full_page_visual_gate_baseline",
                    relations=full_relations,
                    block_duration_ms=int(bootstrap["block_duration_ms"]),
                    iterations=int(bootstrap["block_bootstrap_iterations"]),
                    seed=int(bootstrap["seed"]),
                )
            )

    payload = {
        "schema_version": 1,
        "status": "DIAGNOSTIC_REPLAY_COMPLETE",
        "manifest_path": str(args.manifest.resolve()),
        "manifest_sha256": _sha256(args.manifest),
        "observations_path": str(args.observations.resolve()),
        "observations_sha256": _sha256(args.observations),
        "trial_unit": "one_query_observation",
        "n_squared_pair_counted_as_independent": False,
        "settings": results,
        "limitations": manifest["limitations"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    measured = sum(item["status"] == "MEASURED" for item in results)
    print(json.dumps({"settings": len(results), "measured": measured, "not_measured": len(results) - measured}, indent=2))
    return 0


def _setting_result(
    *,
    cadence_ms: int,
    n: int,
    stage_name: str,
    method: FooterIdentityMethod | str,
    relations: list[dict[str, Any]],
    block_duration_ms: int,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    base = {
        "cadence_ms": cadence_ms,
        "n": n,
        "stage": stage_name,
        "method": method.value if isinstance(method, FooterIdentityMethod) else method,
        "relations": relations,
    }
    if any(item["status"] != "MEASURED" for item in relations):
        return {**base, "status": "NOT_MEASURED_INSUFFICIENT_WINDOW", "thresholds": []}
    same = [flag for item in relations if item["expected"] == "same" for flag in item["indicators"]]
    different = [flag for item in relations if item["expected"] == "different" for flag in item["indicators"]]
    block_size = max(1, round(block_duration_ms / cadence_ms))
    relation_counts = [
        {
            "relation_id": item["relation_id"],
            "expected": item["expected"],
            "match_count": item["match_count"],
            "indicators": item["indicators"],
        }
        for item in relations
    ]
    thresholds = [
        score_threshold(relation_counts, n=n, k_different=k_different, k_same=k_same)
        for k_different, k_same in threshold_grid(n)
    ]
    return {
        **base,
        "status": "MEASURED",
        "same_statistics": _statistics(same, block_size, iterations, seed),
        "different_statistics": _statistics(different, block_size, iterations, seed + 1),
        "p_same_gt_p_different": sum(same) / len(same) > sum(different) / len(different),
        "every_relation_separated": min(
            item["match_rate"] for item in relations if item["expected"] == "same"
        ) > max(item["match_rate"] for item in relations if item["expected"] == "different"),
        "thresholds": thresholds,
    }


def _full_page_visual_match(reference: dict[str, Any], query: dict[str, Any]) -> bool:
    try:
        candidate = _spread_visual(query["full_visual"])
        baseline = _spread_visual(reference["full_visual"])
    except (KeyError, TypeError, ValueError):
        return False
    return compare_visual_spreads(candidate, baseline, IdentityPolicy()).kind is IdentityMatchKind.VISUAL_DUPLICATE


def _spread_visual(value: dict[str, Any]) -> SpreadVisualFingerprint:
    left = _visual(value["left"])
    right = _visual(value["right"])
    return SpreadVisualFingerprint(left.algorithm_version, left, right)


def _visual(value: dict[str, Any]) -> VisualFingerprint:
    return VisualFingerprint(
        str(value["algorithm_version"]),
        str(value["perceptual_hash"]),
        tuple(int(item) for item in value["horizontal_projection"]),
        tuple(int(item) for item in value["vertical_projection"]),
        int(value["normalized_width"]),
        int(value["normalized_height"]),
        tuple(bytes.fromhex(str(item)) for item in value["orb_descriptors_hex"]),
    )


def _statistics(values: list[bool], block_size: int, iterations: int, seed: int) -> dict[str, Any]:
    successes = sum(values)
    return {
        "successes": successes,
        "trials": len(values),
        "point_estimate": successes / len(values),
        "wilson_95": list(wilson_interval(successes, len(values))),
        "block_bootstrap_95": list(
            block_bootstrap_mean_interval(values, block_size=block_size, iterations=iterations, seed=seed)
        ),
        "block_size_observations": min(block_size, len(values)),
        "lag_autocorrelations": list(lag_autocorrelations(values)),
        "effective_sample_size": effective_sample_size(values),
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
