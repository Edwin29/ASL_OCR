"""Evaluate the V3-A.2 OpenCV-DNN backend on real corrected and preview inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import psutil

from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.config import CandidatePolicy, PageNumberPolicy
from book_scanner.video.engine import _page_number_preview_inputs
from book_scanner.video.obstruction import EdgeChromaIntrusionObstructionDetector
from book_scanner.video.page_number_provider import OpenCVBottomRoiPageNumberProvider
from book_scanner.video.page_number_recognizer import OpenCVDnnDigitRecognizer
from book_scanner.video.page_number_roi import corrected_page_number_roi
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import FrameId, PageSide


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--p030-ready-dir", type=Path, required=True)
    parser.add_argument("--video-ready-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    model_manifest = json.loads(args.model_manifest.read_text(encoding="utf-8"))
    _verify_video(args.video, labels)
    process = psutil.Process()
    rss_before = process.memory_info().rss
    cold_started = time.perf_counter()
    recognizer = OpenCVDnnDigitRecognizer(
        args.model,
        model_manifest["asset"]["sha256"],
        confidence_temperature=model_manifest["confidence_temperature"],
    )
    cold_load_ms = (time.perf_counter() - cold_started) * 1000.0
    rss_after_load = process.memory_info().rss
    policy = PageNumberPolicy()
    provider = OpenCVBottomRoiPageNumberProvider(policy, recognizer)

    corrected: list[dict[str, Any]] = []
    warm_inputs: list[tuple[np.ndarray, PageSide]] = []
    for manifest_path in sorted(args.p030_ready_dir.resolve().glob("*/manifest.json")):
        corrected.append(
            _evaluate_corrected_artifact(
                manifest_path,
                recognizer,
                policy,
                "p030_spread",
                labels,
                warm_inputs,
            )
        )
    for manifest_path in sorted(args.video_ready_dir.resolve().glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        frame_index = _frame_index(str(manifest["source_frame_id"]))
        spread = "p030_spread" if frame_index == 780 else "p316_spread" if frame_index == 2220 else None
        corrected.append(
            _evaluate_corrected_artifact(
                manifest_path,
                recognizer,
                policy,
                spread,
                labels,
                warm_inputs,
            )
        )

    warm_latencies: list[float] = []
    for _ordinal in range(20):
        for offset in range(0, len(warm_inputs), 2):
            started = time.perf_counter()
            for roi, side in warm_inputs[offset : offset + 2]:
                recognizer.recognize(roi, side)
            warm_latencies.append((time.perf_counter() - started) * 1000.0)
    rss_after_warm = process.memory_info().rss

    analyzer = OpenCVCandidateAnalyzer(
        CandidatePolicy(), obstruction_detector=EdgeChromaIntrusionObstructionDetector()
    )
    anchor_map = {int(item["frame_index"]): item for item in labels["anchors"]}
    frames = _decode_frames(args.video, set(anchor_map))
    preview: list[dict[str, Any]] = []
    for frame_index in sorted(anchor_map):
        image = frames[frame_index]
        sample = FrameSample(FrameId(f"video-frame-{frame_index:06d}"), frame_index / labels["source_video"]["fps"], image)
        observation = analyzer.analyze(sample)
        hard_reasons = [item.value for item in observation.candidate.retry_reasons]
        before_calls = recognizer.calls
        spread_observation = None
        if not hard_reasons:
            number_gray, number_mask = _page_number_preview_inputs(
                image,
                observation.mask_preview,
                policy.preview_max_dimension,
            )
            spread_observation = provider.observe_preview(
                number_gray,
                number_mask,
                observation.seam_proxy_fraction,
                sample.frame_id,
                "v3a2-evaluation-pack",
            )
        record: dict[str, Any] = {
            "frame_index": frame_index,
            "human_label": anchor_map[frame_index]["label"],
            "hard_gate_reasons": hard_reasons,
            "recognizer_calls": recognizer.calls - before_calls,
        }
        if spread_observation is not None:
            expected = _expected(labels, anchor_map[frame_index].get("page_spread"))
            record.update(_spread_record(spread_observation, expected))
        else:
            record["status"] = "excluded_before_recognizer"
        preview.append(record)

    hard_negative_rois = _hard_negative_probes()
    hard_negatives = []
    for name, roi, side in hard_negative_rois:
        result = recognizer.recognize(roi, side)
        hard_negatives.append(
            {
                "name": name,
                "raw_text": result.raw_text,
                "status": result.status.value,
                "confidence": result.confidence,
                "high_confidence_complete": (
                    result.status.value == "observed"
                    and result.confidence is not None
                    and result.confidence >= policy.min_confidence
                    and result.variant_agreement >= policy.required_variant_agreement
                ),
            }
        )

    user_corrected = [
        side
        for artifact in corrected
        for side in artifact["sides"]
        if side["label_status"] == "USER_CONFIRMED"
    ]
    wrong_complete = [
        item
        for group in (corrected, preview)
        for record in group
        for item in ([record] if "sides" not in record else [])
        if item.get("spread_complete") and item.get("expected_complete") and not item.get("spread_exact")
    ]
    payload = {
        "schema_version": 1,
        "status": "PROVISIONAL_DATA_INSUFFICIENT",
        "backend": {
            "engine_id": recognizer.engine_id,
            "engine_version": recognizer.engine_version,
            "preprocessing_version": recognizer.preprocessing_version,
            "model_sha256": recognizer.model_sha256,
            "model_bytes": recognizer.model_bytes,
            "load_count": recognizer.load_count,
            "runtime_downloads": 0,
        },
        "source_video": labels["source_video"],
        "corrected": corrected,
        "preview_anchors": preview,
        "hard_negative_probes": hard_negatives,
        "accuracy": {
            "user_confirmed_corrected_exact": sum(item["exact"] for item in user_corrected),
            "user_confirmed_corrected_total": len(user_corrected),
            "wrong_complete_count": len(wrong_complete),
            "hard_negative_high_confidence_complete_count": sum(
                item["high_confidence_complete"] for item in hard_negatives
            ),
        },
        "pc_performance": {
            "cold_load_ms": cold_load_ms,
            "warm_spread_input_count": len(warm_inputs) // 2,
            "warm_batch_latency_ms": warm_latencies,
            "warm_median_ms": statistics.median(warm_latencies),
            "warm_observed_p95_ms": float(np.percentile(warm_latencies, 95)),
            "p95_duty_cycle_at_750ms": float(np.percentile(warm_latencies, 95)) / 750.0,
            "rss_load_delta_bytes": max(0, rss_after_load - rss_before),
            "rss_warm_delta_bytes": max(0, rss_after_warm - rss_before),
            "raspberry_pi_measured": False,
        },
        "selection_gate": {
            "human_confirmed_corrected_100_percent": bool(user_corrected) and all(item["exact"] for item in user_corrected),
            "user_confirmed_clean_anchor_wrong_complete_zero": not wrong_complete,
            "real_stable_preview_wrong_complete_zero": None,
            "different_page_same_key_zero": None,
            "reason": "different-page labels and stable-run boundaries are not human-confirmed",
            "validated": False,
            "allow_number_only_duplicate": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key not in {"corrected", "preview_anchors"}}, ensure_ascii=False, indent=2))
    return 0


def _evaluate_corrected_artifact(
    manifest_path: Path,
    recognizer: OpenCVDnnDigitRecognizer,
    policy: PageNumberPolicy,
    spread_name: str | None,
    labels: dict[str, Any],
    warm_inputs: list[tuple[np.ndarray, PageSide]],
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = _expected(labels, spread_name)
    sides = []
    for side in (PageSide.LEFT, PageSide.RIGHT):
        image = cv2.imread(str(manifest_path.parent / side.value / "uvdoc.jpg"), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"cannot read corrected page: {manifest_path.parent / side.value}")
        roi, roi_bbox = corrected_page_number_roi(image, side, policy)
        warm_inputs.append((roi, side))
        started = time.perf_counter()
        recognition = recognizer.recognize(roi, side)
        expected_side = expected.get(side.value) if expected else None
        sides.append(
            {
                "side": side.value,
                "expected": expected_side["value"] if expected_side else None,
                "label_status": expected_side["status"] if expected_side else "UNLABELED",
                "raw_text": recognition.raw_text,
                "exact": expected_side is not None and recognition.raw_text == expected_side["value"],
                "status": recognition.status.value,
                "confidence": recognition.confidence,
                "variant_agreement": recognition.variant_agreement,
                "roi_bbox": roi_bbox,
                "candidate_bbox": recognition.bbox,
                "latency_ms": (time.perf_counter() - started) * 1000.0,
            }
        )
    return {
        "artifact_id": manifest_path.parent.name,
        "source_frame_id": manifest.get("source_frame_id"),
        "page_spread": spread_name,
        "sides": sides,
    }


def _spread_record(observation: Any, expected: dict[str, Any] | None) -> dict[str, Any]:
    expected_labels = (
        (expected["left"]["value"], expected["right"]["value"])
        if expected is not None
        else None
    )
    actual = (
        (observation.key.left_page_label, observation.key.right_page_label)
        if observation.key is not None
        else None
    )
    return {
        "status": observation.status.value,
        "spread_complete": observation.key is not None,
        "expected_complete": expected_labels is not None,
        "spread_exact": expected_labels is not None and actual == expected_labels,
        "expected_labels": expected_labels,
        "actual_labels": actual,
        "left_raw_text": observation.left.raw_text,
        "right_raw_text": observation.right.raw_text,
        "left_status": observation.left.status.value,
        "right_status": observation.right.status.value,
        "processing_ms": observation.processing_ms,
    }


def _expected(labels: dict[str, Any], spread: str | None) -> dict[str, Any] | None:
    return labels["page_label_scope"].get(spread) if spread else None


def _decode_frames(video: Path, wanted: set[int]) -> dict[int, np.ndarray]:
    capture = cv2.VideoCapture(str(video.resolve()))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open video: {video}")
    result: dict[int, np.ndarray] = {}
    index = -1
    try:
        while wanted - result.keys():
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            index += 1
            if index in wanted:
                result[index] = frame.copy()
    finally:
        capture.release()
    missing = wanted - result.keys()
    if missing:
        raise RuntimeError(f"video frames missing: {sorted(missing)}")
    return result


def _hard_negative_probes() -> list[tuple[str, np.ndarray, PageSide]]:
    probes = []
    for name, text in (("footer_year_only", "2026"), ("chapter_number_only", "11.4"), ("text_only", "Level EBS")):
        roi = np.full((360, 520), 238, dtype=np.uint8)
        cv2.putText(roi, text, (24, 318), cv2.FONT_HERSHEY_SIMPLEX, 0.55, 80, 1, cv2.LINE_AA)
        probes.append((name, roi, PageSide.LEFT))
    return probes


def _verify_video(path: Path, labels: dict[str, Any]) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    if _sha256(path) != labels["source_video"]["sha256"]:
        raise ValueError("source video SHA-256 mismatch")


def _frame_index(frame_id: str) -> int:
    return int(frame_id.rsplit("-", 1)[1])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
