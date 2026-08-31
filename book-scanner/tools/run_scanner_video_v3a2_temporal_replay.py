"""Replay V3-A.2 page-number and visual page-change fusion at three cadences."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import cv2

from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.config import (
    CandidatePolicy,
    IdentityPolicy,
    PageChangePolicy,
    PageNumberPolicy,
)
from book_scanner.video.engine import _page_number_preview_inputs
from book_scanner.video.identity import (
    IdentityFingerprintError,
    IdentityMatchKind,
    OpenCVIdentityFingerprinter,
)
from book_scanner.video.obstruction import EdgeChromaIntrusionObstructionDetector
from book_scanner.video.page_change import HysteresisPageChangeGate
from book_scanner.video.page_number import PageKeyRelation, PageNumberChangeTracker
from book_scanner.video.page_number_provider import OpenCVBottomRoiPageNumberProvider
from book_scanner.video.page_number_recognizer import OpenCVDnnDigitRecognizer
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import FrameId, ReadinessReason
from book_scanner.video.types import (
    ArtifactId,
    PageArtifactRef,
    PageSide,
    SpreadArtifactRef,
    SpreadId,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--baseline-artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cadence-ms", type=int, action="append", default=[])
    args = parser.parse_args()

    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    model_manifest = json.loads(args.model_manifest.read_text(encoding="utf-8"))
    if _sha256(args.video) != labels["source_video"]["sha256"]:
        raise ValueError("source video SHA-256 mismatch")
    cadences = args.cadence_ms or [500, 750, 1000]
    if any(value <= 0 for value in cadences):
        parser.error("cadence must be positive")

    results = [
        _run_cadence(
            args.video,
            labels,
            args.model,
            model_manifest,
            args.baseline_artifact_dir,
            cadence,
        )
        for cadence in cadences
    ]
    release_counts = [len(item["releases"]) for item in results]
    false_release_counts = [item["evaluation"]["false_release_count"] for item in results]
    payload = {
        "schema_version": 1,
        "status": (
            "PROVISIONAL_DATA_INSUFFICIENT"
            if all(item["baseline_armed"] for item in results)
            else "BLOCKED_BASELINE_PAGE_KEY_NOT_OBSERVED"
        ),
        "source_video": labels["source_video"],
        "backend": {
            "model_sha256": model_manifest["asset"]["sha256"],
            "model_bytes": model_manifest["asset"]["bytes"],
            "validated": False,
            "allow_number_only_duplicate": False,
        },
        "cadence_results": results,
        "cross_cadence": {
            "release_counts": release_counts,
            "false_release_counts": false_release_counts,
            "all_user_negative_anchors_excluded_from_number_consensus": all(
                item["evaluation"]["sampled_user_negative_consensus_increment_count"] == 0
                for item in results
            ),
            "recommended_default_change": None,
            "reason": (
                "The stable-run boundaries and p316/p317 labels are diagnostic, so this single "
                "development video cannot justify changing the 750ms default."
            ),
        },
        "limitations": labels["limitations"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**payload, "cadence_results": [_compact(item) for item in results]}, ensure_ascii=False, indent=2))
    return 0


def _run_cadence(
    video: Path,
    labels: dict[str, Any],
    model_path: Path,
    model_manifest: dict[str, Any],
    baseline_artifact_dir: Path,
    cadence_ms: int,
) -> dict[str, Any]:
    fps = float(labels["source_video"]["fps"])
    frame_step = max(1, round(fps * cadence_ms / 1000.0))
    baseline_index = int(labels["baseline_frame_index"])
    anchors = {int(item["frame_index"]): item for item in labels["anchors"]}
    identity_policy = IdentityPolicy()
    page_change_policy = PageChangePolicy(sample_interval_ms=cadence_ms, stable_sample_count=3)
    page_number_policy = PageNumberPolicy(stable_sample_count=3)
    analyzer = OpenCVCandidateAnalyzer(
        CandidatePolicy(sample_interval_ms=cadence_ms),
        obstruction_detector=EdgeChromaIntrusionObstructionDetector(),
    )
    fingerprinter = OpenCVIdentityFingerprinter(identity_policy)
    visual_tracker = HysteresisPageChangeGate(identity_policy, page_change_policy)
    number_tracker = PageNumberChangeTracker(page_number_policy)
    recognizer = OpenCVDnnDigitRecognizer(
        model_path,
        model_manifest["asset"]["sha256"],
        page_number_policy,
        confidence_temperature=model_manifest["confidence_temperature"],
    )
    provider = OpenCVBottomRoiPageNumberProvider(page_number_policy, recognizer)
    baseline_artifact_observation = provider.observe_artifact(
        _artifact_ref(baseline_artifact_dir),
        "v3a2-temporal-pack",
    )
    accepted_baseline_key = baseline_artifact_observation.key
    capture = cv2.VideoCapture(str(video.resolve()))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open video: {video}")
    frame_index = -1
    baseline_key = None
    baseline_visual = None
    baseline_armed = False
    releases: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    started = time.perf_counter()
    try:
        while True:
            ok, image = capture.read()
            if not ok or image is None:
                break
            frame_index += 1
            if frame_index % frame_step != 0 and frame_index != baseline_index:
                continue
            sample = FrameSample(
                FrameId(f"video-frame-{frame_index:06d}"), frame_index / fps, image
            )
            observation = analyzer.analyze(sample)
            reasons = set(observation.candidate.retry_reasons)
            motion_observed = bool(
                reasons & {ReadinessReason.PAGE_MOVING, ReadinessReason.HAND_OR_PAGE_TURN}
            )
            eligible = not reasons
            visual = None
            if eligible:
                try:
                    visual = fingerprinter.fingerprint_preview(
                        observation.gray_preview,
                        observation.mask_preview,
                        observation.seam_proxy_fraction,
                    )
                except IdentityFingerprintError:
                    eligible = False
            page_observation = None
            if eligible:
                number_gray, number_mask = _page_number_preview_inputs(
                    image,
                    observation.mask_preview,
                    page_number_policy.preview_max_dimension,
                )
                page_observation = provider.observe_preview(
                    number_gray,
                    number_mask,
                    observation.seam_proxy_fraction,
                    sample.frame_id,
                    "v3a2-temporal-pack",
                )

            if frame_index < baseline_index:
                continue
            expected_spread = _expected_spread(labels, frame_index)
            anchor = anchors.get(frame_index)
            if not baseline_armed:
                if (
                    frame_index == baseline_index
                    and eligible
                    and visual is not None
                    and accepted_baseline_key is not None
                ):
                    baseline_key = accepted_baseline_key
                    baseline_visual = visual
                    number_tracker.arm(baseline_key)
                    visual_tracker.arm(baseline_visual)
                    baseline_armed = True
                records.append(
                    _record(
                        frame_index,
                        sample.captured_at_monotonic,
                        anchor,
                        expected_spread,
                        reasons,
                        eligible,
                        page_observation,
                        None,
                        None,
                        False,
                        "baseline_armed" if baseline_armed else "baseline_missing",
                    )
                )
                continue

            visual_decision = visual_tracker.observe(
                visual,
                eligible=eligible,
                motion_observed=motion_observed,
            )
            number_decision = None
            if page_observation is not None:
                number_decision = number_tracker.observe(page_observation.key, eligible=True)
            else:
                number_tracker.observe(None, eligible=False)
            changed = visual_decision.changed
            fusion = "visual_fallback"
            if number_decision is not None:
                if number_decision.relation is PageKeyRelation.SAME:
                    changed = False
                    fusion = "number_same_resets_visual"
                    assert baseline_visual is not None
                    visual_tracker.arm(baseline_visual)
                elif number_decision.relation is PageKeyRelation.DIFFERENT:
                    visual_kind = (
                        visual_decision.comparison.kind
                        if visual_decision.comparison is not None
                        else None
                    )
                    if visual_kind in {
                        IdentityMatchKind.EXACT_DUPLICATE,
                        IdentityMatchKind.VISUAL_DUPLICATE,
                    }:
                        changed = False
                        fusion = "identity_conflict"
                    else:
                        changed = number_decision.changed
                        fusion = "number_different_consensus"
            record = _record(
                frame_index,
                sample.captured_at_monotonic,
                anchor,
                expected_spread,
                reasons,
                eligible,
                page_observation,
                visual_decision,
                number_decision,
                changed,
                fusion,
            )
            records.append(record)
            if changed:
                releases.append(
                    {
                        "frame_index": frame_index,
                        "timestamp_seconds": frame_index / fps,
                        "fusion": fusion,
                        "page_key": record["page_key"],
                        "expected_spread": expected_spread,
                    }
                )
                if page_observation is not None and page_observation.key is not None:
                    baseline_key = page_observation.key
                if visual is not None:
                    baseline_visual = visual
                if baseline_key is not None and baseline_visual is not None:
                    number_tracker.arm(baseline_key)
                    visual_tracker.arm(baseline_visual)
    finally:
        capture.release()

    false_releases = [item for item in releases if item["expected_spread"] == "p030_spread"]
    negative_increment = [
        item
        for item in records
        if item.get("human_label") in {"HAND_CONTENT_OCCLUSION", "PAGE_MOVING"}
        and (item.get("number_stable_count") or 0) > 0
    ]
    transition_end = max(
        item["end_frame_inclusive"] for item in labels["excluded_transition_windows"]
    )
    post_transition_releases = [item for item in releases if item["frame_index"] > transition_end]
    return {
        "cadence_ms": cadence_ms,
        "frame_step": frame_step,
        "page_number_stable_sample_count": page_number_policy.stable_sample_count,
        "visual_stable_sample_count": page_change_policy.stable_sample_count,
        "baseline_frame_index": baseline_index,
        "baseline_armed": baseline_armed,
        "baseline_key": _key_record(baseline_key),
        "accepted_corrected_baseline_status": baseline_artifact_observation.status.value,
        "accepted_corrected_baseline_key": _key_record(accepted_baseline_key),
        "sample_count_after_baseline": len(records),
        "recognizer_calls": recognizer.calls,
        "cache_hits": provider.cache.hits,
        "wall_seconds": time.perf_counter() - started,
        "releases": releases,
        "evaluation": {
            "false_release_count": len(false_releases),
            "post_transition_release_count": len(post_transition_releases),
            "first_post_transition_release_delay_ms_from_diagnostic_boundary": (
                (post_transition_releases[0]["frame_index"] - transition_end) / fps * 1000.0
                if post_transition_releases
                else None
            ),
            "sampled_user_negative_consensus_increment_count": len(negative_increment),
            "sampled_user_negative_consensus_increment_frames": [
                item["frame_index"] for item in negative_increment
            ],
            "note": "Delay uses a diagnostic transition envelope, not a human-confirmed boundary.",
        },
        "records": records,
    }


def _record(
    frame_index: int,
    timestamp_seconds: float,
    anchor: dict[str, Any] | None,
    expected_spread: str | None,
    reasons: set[ReadinessReason],
    eligible: bool,
    page_observation: Any,
    visual_decision: Any,
    number_decision: Any,
    changed: bool,
    fusion: str,
) -> dict[str, Any]:
    return {
        "frame_index": frame_index,
        "timestamp_seconds": timestamp_seconds,
        "human_label": anchor.get("label") if anchor else None,
        "expected_spread": expected_spread,
        "eligible": eligible,
        "hard_reasons": [item.value for item in sorted(reasons, key=lambda value: value.value)],
        "page_status": page_observation.status.value if page_observation is not None else None,
        "page_key": _key_record(page_observation.key) if page_observation is not None else None,
        "left_raw_text": page_observation.left.raw_text if page_observation is not None else None,
        "right_raw_text": page_observation.right.raw_text if page_observation is not None else None,
        "number_relation": number_decision.relation.value if number_decision is not None else None,
        "number_stable_count": number_decision.stable_count if number_decision is not None else 0,
        "visual_stable_count": visual_decision.stable_count if visual_decision is not None else 0,
        "visual_match_kind": (
            visual_decision.comparison.kind.value
            if visual_decision is not None and visual_decision.comparison is not None
            else None
        ),
        "changed": changed,
        "fusion": fusion,
    }


def _expected_spread(labels: dict[str, Any], frame_index: int) -> str | None:
    for run in labels["stable_runs"]:
        if run["start_frame_inclusive"] <= frame_index <= run["end_frame_inclusive"]:
            return str(run["page_spread"])
    for transition in labels["excluded_transition_windows"]:
        if transition["start_frame_inclusive"] <= frame_index <= transition["end_frame_inclusive"]:
            return "EXCLUDED_TRANSITION"
    return None


def _key_record(key: Any) -> dict[str, str] | None:
    if key is None:
        return None
    return {
        "data_pack_id": key.data_pack_id,
        "left": key.left_page_label,
        "right": key.right_page_label,
        "recognizer_version": key.recognizer_version,
    }


def _artifact_ref(directory: Path) -> SpreadArtifactRef:
    root = directory.resolve()
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frame_id = FrameId(str(manifest["source_frame_id"]))

    def page(side: PageSide) -> PageArtifactRef:
        record = manifest["pages"][side.value]["files"]["uvdoc"]
        return PageArtifactRef(
            side,
            frame_id,
            str(root / record["path"]),
            str(record["sha256"]),
            int(record["width"]),
            int(record["height"]),
        )

    return SpreadArtifactRef(
        ArtifactId(str(manifest["artifact_id"])),
        SpreadId(str(manifest["spread_id"])),
        frame_id,
        page(PageSide.LEFT),
        page(PageSide.RIGHT),
        str(manifest_path),
        _sha256(manifest_path),
        "scanner-video-v3a2-temporal-replay",
    )


def _compact(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "records"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
