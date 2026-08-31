"""Capture frozen Paddle bottom-ROI observations for paired V3-A.3 replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import cv2

from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.config import CandidatePolicy, IdentityPolicy, PageChangePolicy, PageNumberPolicy
from book_scanner.video.engine import _page_number_preview_inputs
from book_scanner.video.identity import IdentityFingerprintError, OpenCVIdentityFingerprinter
from book_scanner.video.obstruction import EdgeChromaIntrusionObstructionDetector
from book_scanner.video.page_change import HysteresisPageChangeGate
from book_scanner.video.page_number_provider import OpenCVBottomRoiPageNumberProvider
from book_scanner.video.page_number_recognizer import PaddleRoiDigitRecognizer
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import (
    ArtifactId,
    FrameId,
    PageArtifactRef,
    PageSide,
    ReadinessReason,
    SpreadArtifactRef,
    SpreadId,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--baseline-artifact-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "gpu:0"), default="cpu")
    parser.add_argument("--cadence-ms", type=int, action="append", default=[])
    args = parser.parse_args()

    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    manifest = json.loads(args.model_manifest.read_text(encoding="utf-8"))
    if _sha256(args.video) != labels["source_video"]["sha256"]:
        raise ValueError("source video SHA-256 mismatch")
    _verify_model_manifest(args.model_dir, manifest)
    cadences = args.cadence_ms or [500, 750, 1000, 1500]
    if any(value <= 0 for value in cadences):
        parser.error("cadence must be positive")

    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    import paddle

    paddle.set_device(args.device)
    rss_before = _rss_bytes()
    load_started = time.perf_counter()
    recognizer = PaddleRoiDigitRecognizer(
        args.model_dir,
        PageNumberPolicy(),
        expected_file_hashes=manifest["files"],
        device=args.device,
    )
    cold_load_ms = (time.perf_counter() - load_started) * 1000.0
    rss_after_load = _rss_bytes()
    provider = OpenCVBottomRoiPageNumberProvider(PageNumberPolicy(), recognizer)
    calls_before_baseline = recognizer.calls
    baseline = provider.observe_artifact(
        _artifact_ref(args.baseline_artifact_dir),
        "v3a3-temporal-pack",
    )
    baseline_roi_calls = recognizer.calls - calls_before_baseline

    cadence_results = []
    for cadence in cadences:
        before_calls = recognizer.calls
        before_hits = provider.cache.hits
        cadence_results.append(
            _capture_cadence(
                args.video,
                labels,
                cadence,
                provider,
            )
        )
        cadence_results[-1]["physical_roi_calls"] = recognizer.calls - before_calls
        cadence_results[-1]["cache_hits"] = provider.cache.hits - before_hits

    payload = {
        "schema_version": 1,
        "status": "PROVISIONAL_DATA_INSUFFICIENT",
        "source_video": labels["source_video"],
        "device": args.device,
        "runtime": {
            "paddle_version": paddle.__version__,
            "cuda_compiled": bool(paddle.is_compiled_with_cuda()),
            "cuda_device_count": int(paddle.device.cuda.device_count()),
            "model_name": manifest["model_name"],
            "model_dir": str(args.model_dir.resolve()),
            "model_bytes": recognizer.model_bytes,
            "verified_asset_count": len(recognizer.verified_file_hashes),
            "load_count": recognizer.load_count,
            "cold_load_ms": cold_load_ms,
            "rss_before_bytes": rss_before,
            "rss_after_load_bytes": rss_after_load,
            "rss_load_delta_bytes": _delta(rss_before, rss_after_load),
            "runtime_download_allowed": False,
        },
        "baseline": {
            "artifact_dir": str(args.baseline_artifact_dir.resolve()),
            "status": baseline.status.value,
            "key": _key_record(baseline.key),
            "processing_ms": baseline.processing_ms,
            "roi_calls": baseline_roi_calls,
        },
        "cadence_results": cadence_results,
        "limitations": labels["limitations"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**payload, "cadence_results": [_compact(item) for item in cadence_results]}, ensure_ascii=False, indent=2))
    return 0


def _capture_cadence(
    video: Path,
    labels: dict[str, Any],
    cadence_ms: int,
    provider: OpenCVBottomRoiPageNumberProvider,
) -> dict[str, Any]:
    fps = float(labels["source_video"]["fps"])
    frame_step = max(1, round(fps * cadence_ms / 1000.0))
    baseline_index = int(labels["baseline_frame_index"])
    anchors = {int(item["frame_index"]): item for item in labels["anchors"]}
    analyzer = OpenCVCandidateAnalyzer(
        CandidatePolicy(sample_interval_ms=cadence_ms),
        obstruction_detector=EdgeChromaIntrusionObstructionDetector(),
    )
    identity_policy = IdentityPolicy()
    fingerprinter = OpenCVIdentityFingerprinter(identity_policy)
    visual_tracker = HysteresisPageChangeGate(
        identity_policy,
        PageChangePolicy(sample_interval_ms=cadence_ms, stable_sample_count=3),
    )
    capture = cv2.VideoCapture(str(video.resolve()))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open video: {video}")
    frame_index = -1
    baseline_visual = None
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
            if frame_index < baseline_index:
                continue
            sample = FrameSample(FrameId(f"video-frame-{frame_index:06d}"), frame_index / fps, image)
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
                    provider.policy.preview_max_dimension,
                )
                page_observation = provider.observe_preview(
                    number_gray,
                    number_mask,
                    observation.seam_proxy_fraction,
                    sample.frame_id,
                    "v3a3-temporal-pack",
                )

            if frame_index == baseline_index and visual is not None:
                baseline_visual = visual
                visual_tracker.arm(visual)
                visual_decision = None
            elif baseline_visual is not None:
                visual_decision = visual_tracker.observe(
                    visual,
                    eligible=eligible,
                    motion_observed=motion_observed,
                )
            else:
                visual_decision = None
            anchor = anchors.get(frame_index)
            records.append(
                {
                    "frame_index": frame_index,
                    "timestamp_seconds": frame_index / fps,
                    "human_label": anchor.get("label") if anchor else None,
                    "expected_spread": _expected_spread(labels, frame_index),
                    "eligible": eligible,
                    "hard_reasons": [item.value for item in sorted(reasons, key=lambda item: item.value)],
                    "baseline": frame_index == baseline_index,
                    "visual_match_kind": (
                        visual_decision.comparison.kind.value
                        if visual_decision is not None and visual_decision.comparison is not None
                        else None
                    ),
                    "visual_stable_count": visual_decision.stable_count if visual_decision else 0,
                    "visual_changed": visual_decision.changed if visual_decision else False,
                    "page_observation": _page_record(page_observation),
                }
            )
    finally:
        capture.release()
    return {
        "cadence_ms": cadence_ms,
        "frame_step": frame_step,
        "sampled_spreads": len(records),
        "hard_gate_rejected_spreads": sum(not item["eligible"] for item in records),
        "eligible_spreads": sum(item["eligible"] for item in records),
        "wall_seconds": time.perf_counter() - started,
        "records": records,
    }


def _page_record(observation: Any) -> dict[str, Any] | None:
    if observation is None:
        return None

    def side(item: Any) -> dict[str, Any]:
        return {
            "raw_text": item.raw_text,
            "normalized_label": item.normalized_label,
            "confidence": item.confidence,
            "status": item.status.value,
            "roi_sha256": item.roi_sha256,
            "cache_hit": item.cache_hit,
        }

    return {
        "status": observation.status.value,
        "key": _key_record(observation.key),
        "processing_ms": observation.processing_ms,
        "left": side(observation.left),
        "right": side(observation.right),
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


def _verify_model_manifest(model_dir: Path, manifest: dict[str, Any]) -> None:
    root = model_dir.resolve()
    for name, expected in manifest["files"].items():
        path = root / name
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"Paddle model manifest mismatch: {name}")


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
        "scanner-video-v3a3-paddle-capture",
    )


def _rss_bytes() -> int | None:
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        return None


def _delta(before: int | None, after: int | None) -> int | None:
    return after - before if before is not None and after is not None else None


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
