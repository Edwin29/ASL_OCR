"""Create the compact auditable V3-A.3 decision summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu-frozen", type=Path, required=True)
    parser.add_argument("--gpu-frozen", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cpu = _read(args.cpu_frozen)
    gpu = _read(args.gpu_frozen)
    replay = _read(args.replay)
    parity = _parity(cpu, gpu, {500, 750})
    policies = [
        _compact_policy(item)
        for item in replay["comparisons"]
    ]
    default_p0 = _policy(replay, 750, "EVERY_ELIGIBLE")
    default_visual = _policy(replay, 750, "VISUAL_TRIGGERED")
    default_reduction = 1.0 - (
        default_visual["paddle_requested_spreads"]
        / default_p0["paddle_requested_spreads"]
    )
    payload = {
        "schema_version": 1,
        "status": "PROVISIONAL_VISUAL_GATE_VALUE_FAIL_AT_DEFAULT_CADENCE",
        "source_video": cpu["source_video"],
        "measurement_contract": {
            "hard_gate_and_visual_gate_reported_separately": True,
            "spread_requests_and_side_roi_calls_reported_separately": True,
            "accepted_baseline_calls_excluded_from_scheduler_reduction": True,
            "frozen_observations_reused_across_policies": True,
        },
        "runtime": {
            "cpu": _runtime(cpu),
            "gpu": _runtime(gpu),
            "cpu_gpu_output_parity": parity,
            "gpu_environment_warning": (
                "Observed at runtime: Paddle was built with cuDNN 9.9 while the machine exposed "
                "cuDNN 9.5; GPU numbers are diagnostic and are not a deployment recommendation."
            ),
        },
        "policy_results": policies,
        "default_750ms_decision": {
            "p0_requested_spreads": default_p0["paddle_requested_spreads"],
            "visual_triggered_requested_spreads": default_visual["paddle_requested_spreads"],
            "visual_incremental_suppression": default_reduction,
            "required_suppression": 0.30,
            "value_gate_pass": False,
            "p0_release_count": default_p0["release_count"],
            "visual_triggered_release_count": default_visual["release_count"],
            "reason": (
                "VisualGate saved only 2 of 9 eligible spread requests (22.2%), below the frozen "
                "30% gate; neither policy obtained three complete new-page keys at 750ms."
            ),
        },
        "diagnostic_500ms_result": {
            "visual_incremental_suppression": _policy(
                replay, 500, "VISUAL_TRIGGERED"
            )["visual_incremental_suppression"],
            "p0_release_frame": _policy(replay, 500, "EVERY_ELIGIBLE")["first_release_frame"],
            "visual_release_frame": _policy(
                replay, 500, "VISUAL_TRIGGERED"
            )["first_release_frame"],
            "release_basis": _policy(
                replay, 500, "VISUAL_TRIGGERED"
            )["first_release_basis"],
            "production_gate_pass": False,
            "reason": (
                "The 37.5% reduction and frame-2220 release are promising, but p316/p317 and the "
                "stable-run boundary are not human golden and a cadence change was not approved."
            ),
        },
        "decision": {
            "selected_default": None,
            "keep_scheduler_default": "EVERY_ELIGIBLE",
            "paddle_backend_status": "PROVISIONAL_RECOGNITION_CANDIDATE",
            "visual_scheduler_status": "VALUE_GATE_FAIL_AT_750MS",
            "validated": False,
            "allow_number_only_duplicate": False,
            "raspberry_pi_4": "NOT_MEASURED",
        },
        "limitations": cpu["limitations"],
        "sources": {
            "cpu_frozen": _source(args.cpu_frozen),
            "gpu_frozen": _source(args.gpu_frozen),
            "scheduler_replay": _source(args.replay),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _runtime(payload: dict[str, Any]) -> dict[str, Any]:
    results = []
    for cadence in payload["cadence_results"]:
        values = [
            float(item["page_observation"]["processing_ms"])
            for item in cadence["records"]
            if item["page_observation"] is not None
        ]
        results.append(
            {
                "cadence_ms": cadence["cadence_ms"],
                "eligible_spreads": cadence["eligible_spreads"],
                "physical_roi_calls": cadence["physical_roi_calls"],
                "cache_hits": cadence["cache_hits"],
                "spread_latency_ms": _latency(values),
            }
        )
    return {
        "device": payload["device"],
        "model_bytes": payload["runtime"]["model_bytes"],
        "verified_asset_count": payload["runtime"]["verified_asset_count"],
        "load_count": payload["runtime"]["load_count"],
        "cold_load_ms": payload["runtime"]["cold_load_ms"],
        "rss_load_delta_bytes": payload["runtime"]["rss_load_delta_bytes"],
        "baseline_processing_ms": payload["baseline"]["processing_ms"],
        "cadences": results,
    }


def _parity(cpu: dict[str, Any], gpu: dict[str, Any], cadences: set[int]) -> dict[str, Any]:
    mismatches = []
    compared = 0
    for cadence_ms in cadences:
        cpu_run = next(item for item in cpu["cadence_results"] if item["cadence_ms"] == cadence_ms)
        gpu_run = next(item for item in gpu["cadence_results"] if item["cadence_ms"] == cadence_ms)
        gpu_records = {item["frame_index"]: item for item in gpu_run["records"]}
        for cpu_record in cpu_run["records"]:
            gpu_record = gpu_records[cpu_record["frame_index"]]
            cpu_page = cpu_record["page_observation"]
            gpu_page = gpu_record["page_observation"]
            if cpu_page is None and gpu_page is None:
                continue
            compared += 1
            cpu_value = (cpu_page or {}).get("key") or (cpu_page or {}).get("status")
            gpu_value = (gpu_page or {}).get("key") or (gpu_page or {}).get("status")
            if cpu_value != gpu_value:
                mismatches.append(
                    {"cadence_ms": cadence_ms, "frame_index": cpu_record["frame_index"]}
                )
    return {
        "compared_eligible_observations": compared,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def _compact_policy(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "cadence_ms",
        "policy",
        "sampled_spreads",
        "hard_gate_rejected_spreads",
        "eligible_spreads",
        "paddle_requested_spreads",
        "paddle_roi_calls",
        "visual_incremental_suppression",
        "total_paddle_suppression",
        "verification_bursts",
        "verification_burst_start_frames",
        "release_producing_bursts",
        "useful_trigger_precision",
        "audit_requests",
        "release_count",
        "false_release_count",
        "first_release_frame",
        "first_release_basis",
        "negative_consensus_increment_count",
    )
    return {key: item[key] for key in keys}


def _policy(payload: dict[str, Any], cadence: int, name: str) -> dict[str, Any]:
    return next(
        item
        for item in payload["comparisons"]
        if item["cadence_ms"] == cadence and item["policy"] == name
    )


def _latency(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "median": None, "observed_p95": None, "max": None}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "median": median(ordered),
        "observed_p95": ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)],
        "max": ordered[-1],
    }


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _source(path: Path) -> dict[str, str]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return {"path": str(path.resolve()), "sha256": digest.hexdigest()}


if __name__ == "__main__":
    raise SystemExit(main())
