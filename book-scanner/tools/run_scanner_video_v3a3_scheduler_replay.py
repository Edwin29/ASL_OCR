"""Compare V3-A.3 Paddle call policies on frozen observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any

from book_scanner.video.config import (
    PageNumberPolicy,
    PageNumberSchedulerMode,
    PageNumberSchedulerPolicy,
)
from book_scanner.video.identity import IdentityMatchKind
from book_scanner.video.page_number import PageKeyRelation, PageNumberChangeTracker, SpreadPageKey
from book_scanner.video.page_number_scheduler import PageNumberVerificationScheduler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    frozen = json.loads(args.frozen.read_text(encoding="utf-8"))
    baseline_key = _parse_key(frozen["baseline"]["key"])
    if baseline_key is None:
        raise ValueError("accepted corrected baseline key is incomplete")
    comparisons = []
    for cadence in frozen["cadence_results"]:
        if cadence["cadence_ms"] == 1500:
            modes = (("LOW_RATE_CONTROL", PageNumberSchedulerMode.EVERY_ELIGIBLE),)
        else:
            modes = (
                ("EVERY_ELIGIBLE", PageNumberSchedulerMode.EVERY_ELIGIBLE),
                ("VISUAL_TRIGGERED", PageNumberSchedulerMode.VISUAL_TRIGGERED),
                ("HYBRID_AUDITED", PageNumberSchedulerMode.HYBRID_AUDITED),
            )
        for name, mode in modes:
            comparisons.append(_replay(cadence, baseline_key, name, mode))

    by_cadence: dict[int, dict[str, dict[str, Any]]] = {}
    for item in comparisons:
        by_cadence.setdefault(item["cadence_ms"], {})[item["policy"]] = item
    value_assessments = []
    for cadence_ms, policies in sorted(by_cadence.items()):
        baseline = policies.get("EVERY_ELIGIBLE")
        if baseline is None:
            continue
        for name in ("VISUAL_TRIGGERED", "HYBRID_AUDITED"):
            candidate = policies[name]
            reduction = _reduction(
                candidate["paddle_requested_spreads"],
                baseline["paddle_requested_spreads"],
            )
            baseline_release = baseline["first_release_frame"]
            candidate_release = candidate["first_release_frame"]
            delay_ms = None
            if baseline_release is not None and candidate_release is not None:
                delay_ms = (candidate_release - baseline_release) / frozen["source_video"]["fps"] * 1000.0
            value_assessments.append(
                {
                    "cadence_ms": cadence_ms,
                    "policy": name,
                    "p0_request_reduction": reduction,
                    "same_release_count_as_p0": candidate["release_count"] == baseline["release_count"],
                    "additional_release_delay_ms": delay_ms,
                    "provisional_value_gate_pass": bool(
                        reduction is not None
                        and reduction >= 0.30
                        and candidate["false_release_count"] == 0
                        and candidate["release_count"] == baseline["release_count"]
                        and delay_ms is not None
                        and delay_ms <= 750.0
                    ),
                }
            )

    payload = {
        "schema_version": 1,
        "status": "PROVISIONAL_DATA_INSUFFICIENT",
        "source_video": frozen["source_video"],
        "frozen_observation_source": str(args.frozen.resolve()),
        "frozen_observation_sha256": _sha256(args.frozen),
        "comparisons": comparisons,
        "value_assessments": value_assessments,
        "decision": {
            "selected_default": None,
            "validated": False,
            "allow_number_only_duplicate": False,
            "reason": (
                "p316/p317 labels and stable-run boundaries are diagnostic rather than human golden; "
                "the value gate is informative but cannot promote a production default."
            ),
        },
        "limitations": frozen["limitations"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                **payload,
                "comparisons": [
                    {key: value for key, value in item.items() if key != "records"}
                    for item in comparisons
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _replay(
    cadence: dict[str, Any],
    baseline_key: SpreadPageKey,
    policy_name: str,
    mode: PageNumberSchedulerMode,
) -> dict[str, Any]:
    scheduler = PageNumberVerificationScheduler(
        PageNumberSchedulerPolicy(
            mode=mode,
            audit_interval_eligible_samples=4,
            burst_max_eligible_samples=5,
        )
    )
    tracker = PageNumberChangeTracker(PageNumberPolicy(stable_sample_count=3))
    tracker.arm(baseline_key)
    releases: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    roi_cache: set[tuple[str, str]] = set()
    roi_calls = 0
    cache_hits = 0
    requested_latencies: list[float] = []
    negative_consensus_increments = 0
    burst_start_frames: list[int] = []
    for record in cadence["records"]:
        if record["baseline"]:
            continue
        kind = (
            IdentityMatchKind(record["visual_match_kind"])
            if record["visual_match_kind"] is not None
            else None
        )
        bursts_before = scheduler.diagnostics.verification_bursts
        decision = scheduler.observe(
            eligible=bool(record["eligible"]),
            visual_match_kind=kind,
            visual_stable_count=int(record["visual_stable_count"]),
        )
        if scheduler.diagnostics.verification_bursts > bursts_before:
            burst_start_frames.append(int(record["frame_index"]))
        page = record["page_observation"] if decision.requested else None
        if page is not None:
            requested_latencies.append(float(page["processing_ms"]))
            for side in ("left", "right"):
                digest = str(page[side]["roi_sha256"])
                key = (side, digest)
                if key in roi_cache:
                    cache_hits += 1
                else:
                    roi_cache.add(key)
                    roi_calls += 1
        key = _parse_key(page["key"]) if page is not None else None
        number_decision = tracker.observe(key, eligible=page is not None)
        changed = bool(record["visual_changed"])
        fusion = "visual_fallback"
        if page is not None:
            if number_decision.relation is PageKeyRelation.SAME:
                changed = False
                fusion = "number_same_resets_visual"
            elif number_decision.relation is PageKeyRelation.DIFFERENT:
                if kind in {
                    IdentityMatchKind.EXACT_DUPLICATE,
                    IdentityMatchKind.VISUAL_DUPLICATE,
                }:
                    changed = False
                    fusion = "identity_conflict"
                else:
                    changed = number_decision.changed
                    fusion = "number_different_consensus"
        if (
            record.get("human_label") in {"HAND_CONTENT_OCCLUSION", "PAGE_MOVING"}
            and number_decision.stable_count > 0
        ):
            negative_consensus_increments += 1
        item = {
            "frame_index": record["frame_index"],
            "expected_spread": record["expected_spread"],
            "eligible": record["eligible"],
            "visual_match_kind": record["visual_match_kind"],
            "visual_stable_count": record["visual_stable_count"],
            "paddle_requested": decision.requested,
            "request_reason": decision.reason.value,
            "page_status": page["status"] if page is not None else None,
            "page_key": page["key"] if page is not None else None,
            "number_relation": number_decision.relation.value,
            "number_stable_count": number_decision.stable_count,
            "changed": changed,
            "fusion": fusion,
        }
        records.append(item)
        if changed:
            releases.append(item)
            break
    diagnostics = scheduler.diagnostics
    false_releases = [item for item in releases if item["expected_spread"] == "p030_spread"]
    eligible = diagnostics.eligible_spreads
    return {
        "cadence_ms": cadence["cadence_ms"],
        "policy": policy_name,
        "sampled_spreads": diagnostics.sampled_spreads,
        "hard_gate_rejected_spreads": diagnostics.hard_gate_rejected_spreads,
        "eligible_spreads": eligible,
        "visual_same_spreads": diagnostics.visual_same_spreads,
        "visual_changed_spreads": diagnostics.visual_changed_spreads,
        "visual_ambiguous_spreads": diagnostics.visual_ambiguous_spreads,
        "visual_error_spreads": diagnostics.visual_error_spreads,
        "paddle_requested_spreads": diagnostics.requested_spreads,
        "paddle_skipped_spreads": diagnostics.skipped_spreads,
        "paddle_roi_calls": roi_calls,
        "paddle_cache_hits": cache_hits,
        "audit_requests": diagnostics.audit_requests,
        "verification_bursts": diagnostics.verification_bursts,
        "verification_burst_start_frames": burst_start_frames,
        "release_producing_bursts": (
            1 if releases and diagnostics.verification_bursts > 0 else 0
        ),
        "useful_trigger_precision": (
            1.0 / diagnostics.verification_bursts
            if releases and diagnostics.verification_bursts > 0
            else (0.0 if diagnostics.verification_bursts > 0 else None)
        ),
        "burst_timeouts": diagnostics.burst_timeouts,
        "hard_gate_rejection": _ratio(diagnostics.hard_gate_rejected_spreads, diagnostics.sampled_spreads),
        "visual_incremental_suppression": _reduction(diagnostics.requested_spreads, eligible),
        "total_paddle_suppression": _reduction(diagnostics.requested_spreads, diagnostics.sampled_spreads),
        "requested_latency_ms": _latency(requested_latencies),
        "release_count": len(releases),
        "false_release_count": len(false_releases),
        "first_release_frame": releases[0]["frame_index"] if releases else None,
        "first_release_basis": releases[0]["fusion"] if releases else None,
        "negative_consensus_increment_count": negative_consensus_increments,
        "records": records,
    }


def _parse_key(payload: dict[str, str] | None) -> SpreadPageKey | None:
    if payload is None:
        return None
    return SpreadPageKey(
        str(payload["data_pack_id"]),
        str(payload["left"]),
        str(payload["right"]),
        str(payload["recognizer_version"]),
    )


def _latency(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "median": None, "observed_p95": None, "max": None}
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "count": len(ordered),
        "median": median(ordered),
        "observed_p95": ordered[index],
        "max": ordered[-1],
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _reduction(candidate: int, baseline: int) -> float | None:
    return 1.0 - candidate / baseline if baseline else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
