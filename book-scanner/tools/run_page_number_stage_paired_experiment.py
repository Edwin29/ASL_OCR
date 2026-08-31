"""Compare page-number recognition at four points in the scanner pipeline.

The experiment deliberately keeps the ROI fractions, Paddle recognition model,
confidence threshold, and variant-agreement rule fixed.  Only the image stage
presented to the bottom-ROI recognizer changes.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from book_scanner.correct.uvdoc_adapter import UVDocAdapter, UVDocConfig
from book_scanner.detect.spread_extraction import SeamConservativeSpreadExtractor
from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.config import CandidatePolicy, PageNumberPolicy
from book_scanner.video.engine import _page_number_preview_inputs
from book_scanner.video.obstruction import EdgeChromaIntrusionObstructionDetector
from book_scanner.video.page_number import PageNumberSource
from book_scanner.video.page_number_provider import OpenCVBottomRoiPageNumberProvider, _spread
from book_scanner.video.page_number_recognizer import (
    PaddleRoiDigitRecognizer,
    _candidate_clusters,
)
from book_scanner.video.page_number_roi import (
    corrected_page_number_roi,
    preview_page_number_roi,
)
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import FrameId, PageSide


DEFAULT_FRAMES = (720, 750, 765, 780, 810, 2190, 2220, 2250)


class TracingPaddleRecognizer(PaddleRoiDigitRecognizer):
    """Capture the two predictions already made by the production recognizer."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.last_predictions: list[dict[str, Any]] = []

    def recognize(self, roi: np.ndarray, side: PageSide):  # type: ignore[override]
        self.last_predictions = []
        return super().recognize(roi, side)

    def _predict(self, image: np.ndarray) -> tuple[str, float]:
        text, score = super()._predict(image)
        self.last_predictions.append({"text": text, "score": score})
        return text, score


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--uvdoc-runtime", type=Path, required=True)
    parser.add_argument("--uvdoc-checkpoint", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frame-index", type=int, action="append", default=[])
    parser.add_argument("--device", choices=("cpu", "gpu:0"), default="cpu")
    args = parser.parse_args()

    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    manifest = json.loads(args.model_manifest.read_text(encoding="utf-8"))
    if _sha256(args.video) != labels["source_video"]["sha256"]:
        raise ValueError("source video SHA-256 mismatch")
    _verify_model_manifest(args.model_dir, manifest)
    frame_indices = sorted(set(args.frame_index or DEFAULT_FRAMES))
    frames = _read_frames(args.video, frame_indices)
    missing = sorted(set(frame_indices) - set(frames))
    if missing:
        raise ValueError(f"video frames were not decoded: {missing}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    import torch
    import paddle

    paddle.set_device(args.device)
    policy = PageNumberPolicy()
    recognizer = TracingPaddleRecognizer(
        args.model_dir,
        policy,
        expected_file_hashes=manifest["files"],
        device=args.device,
    )
    provider = OpenCVBottomRoiPageNumberProvider(policy, recognizer)
    analyzer = OpenCVCandidateAnalyzer(
        CandidatePolicy(sample_interval_ms=500),
        obstruction_detector=EdgeChromaIntrusionObstructionDetector(),
    )
    extractor = SeamConservativeSpreadExtractor()
    uvdoc = UVDocAdapter(
        UVDocConfig(
            runtime_path=args.uvdoc_runtime.resolve(),
            checkpoint_path=args.uvdoc_checkpoint.resolve(),
            device="cpu",
            sampling_mode="bilinear",
        )
    )

    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    for frame_index in frame_indices:
        print(f"frame {frame_index}: preparing four stages", flush=True)
        records.append(
            _evaluate_frame(
                frame_index,
                frames[frame_index],
                float(labels["source_video"]["fps"]),
                labels,
                policy,
                analyzer,
                extractor,
                uvdoc,
                provider,
                recognizer,
                args.output_dir,
            )
        )

    payload = {
        "schema_version": 1,
        "experiment": "page_number_recognition_stage_paired_v1",
        "status": "DIAGNOSTIC_NOT_PRODUCTION_SELECTION",
        "invariant_controls": {
            "model_name": manifest["model_name"],
            "model_asset_sha256": manifest["files"],
            "device": args.device,
            "page_number_policy": {
                "left_x": [policy.left_x_min, policy.left_x_max],
                "right_x": [policy.right_x_min, policy.right_x_max],
                "y": [policy.y_min, policy.y_max],
                "min_confidence": policy.min_confidence,
                "required_variant_agreement": policy.required_variant_agreement,
                "min_digits": policy.min_digits,
                "max_digits": policy.max_digits,
            },
            "sampling_mode": "bilinear",
            "threshold_tuning_per_stage": False,
        },
        "stages": {
            "preview_1920": "current ACK-after path: raw frame resized to max 1920, preview mask, no crop/warp",
            "preview_native": "raw frame at native resolution, preview mask, no crop/warp",
            "seam_crop": "full-resolution seam-conservative page crop, before UVDoc",
            "seam_crop_uvdoc": "full-resolution seam-conservative page crop, after UVDoc bilinear",
            "adaptive_preview_fallback": "use native preview only for a side not observed at 1920; never replace an observed 1920 side",
        },
        "source_video": labels["source_video"],
        "runtime": {
            "paddle_version": paddle.__version__,
            "torch_version": torch.__version__,
            "opencv_version": cv2.__version__,
            "recognizer_load_count": recognizer.load_count,
            "recognizer_calls": recognizer.calls,
            "uvdoc_load_count": uvdoc.load_count,
            "wall_seconds": time.perf_counter() - started,
        },
        "summary": _summarize(records),
        "records": records,
        "limitations": [
            "Only p30 left=30 is explicit user golden; p30 right=309 and p316/p317 remain diagnostic labels.",
            "Stable-window boundaries are automated diagnostic windows, not human-confirmed frame-by-frame labels.",
            "This experiment identifies stage effects on one fixed-view video; it does not validate production thresholds.",
            "UVDoc runs on the development PC CPU and does not measure Raspberry Pi latency.",
        ],
    }
    output = args.output_dir / "summary.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2), flush=True)
    return 0


def _evaluate_frame(
    frame_index: int,
    frame: np.ndarray,
    fps: float,
    labels: dict[str, Any],
    policy: PageNumberPolicy,
    analyzer: OpenCVCandidateAnalyzer,
    extractor: SeamConservativeSpreadExtractor,
    uvdoc: UVDocAdapter,
    provider: OpenCVBottomRoiPageNumberProvider,
    recognizer: TracingPaddleRecognizer,
    output_dir: Path,
) -> dict[str, Any]:
    frame_id = FrameId(f"video-frame-{frame_index:06d}")
    sample = FrameSample(frame_id, frame_index / fps, frame)
    candidate = analyzer.analyze(sample)
    frame_dir = output_dir / f"frame_{frame_index:06d}"
    frame_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(frame_dir / "source.jpg"), frame)

    stages: dict[str, dict[str, Any]] = {}
    for name, max_dimension in (("preview_1920", policy.preview_max_dimension), ("preview_native", max(frame.shape[:2]))):
        gray, mask = _page_number_preview_inputs(frame, candidate.mask_preview, max_dimension)
        rois: dict[PageSide, tuple[np.ndarray, tuple[int, int, int, int]]] = {}
        errors: dict[str, str] = {}
        for side in PageSide:
            try:
                rois[side] = preview_page_number_roi(
                    gray,
                    mask,
                    candidate.seam_proxy_fraction,
                    side,
                    policy,
                )
            except ValueError as exc:
                errors[side.value] = str(exc)
        stages[name] = _evaluate_stage(
            name,
            rois,
            errors,
            frame_id,
            PageNumberSource.PREVIEW,
            policy,
            provider,
            recognizer,
            frame_dir,
        )

    extraction_started = time.perf_counter()
    extraction = extractor.extract(frame)
    extraction_ms = (time.perf_counter() - extraction_started) * 1000.0
    crop_rois: dict[PageSide, tuple[np.ndarray, tuple[int, int, int, int]]] = {}
    crop_errors: dict[str, str] = {}
    uvdoc_rois: dict[PageSide, tuple[np.ndarray, tuple[int, int, int, int]]] = {}
    uvdoc_errors: dict[str, str] = {}
    uvdoc_records: dict[str, Any] = {}
    if extraction.success and extraction.left is not None and extraction.right is not None:
        for side, page in ((PageSide.LEFT, extraction.left), (PageSide.RIGHT, extraction.right)):
            cv2.imwrite(str(frame_dir / f"{side.value}_seam_crop.jpg"), page.crop)
            crop_rois[side] = corrected_page_number_roi(page.crop, side, policy)
            result = uvdoc.unwarp_with_mode(page.crop, "bilinear")
            uvdoc_records[side.value] = {
                "success": result.success,
                "elapsed_ms": result.processing_ms,
                "failure_reason": result.reason.value if result.reason else None,
                "diagnostics": dict(result.diagnostics),
            }
            if result.success and result.image is not None:
                cv2.imwrite(str(frame_dir / f"{side.value}_uvdoc.jpg"), result.image)
                uvdoc_rois[side] = corrected_page_number_roi(result.image, side, policy)
            else:
                uvdoc_errors[side.value] = str(result.diagnostics.get("message", "UVDoc failed"))
    else:
        reason = extraction.reason or "spread extraction failed"
        crop_errors = {side.value: reason for side in PageSide}
        uvdoc_errors = dict(crop_errors)

    stages["seam_crop"] = _evaluate_stage(
        "seam_crop",
        crop_rois,
        crop_errors,
        frame_id,
        PageNumberSource.CORRECTED,
        policy,
        provider,
        recognizer,
        frame_dir,
    )
    stages["seam_crop_uvdoc"] = _evaluate_stage(
        "seam_crop_uvdoc",
        uvdoc_rois,
        uvdoc_errors,
        frame_id,
        PageNumberSource.CORRECTED,
        policy,
        provider,
        recognizer,
        frame_dir,
    )
    stages["adaptive_preview_fallback"] = _adaptive_preview_fallback(
        stages["preview_1920"],
        stages["preview_native"],
    )
    expected = _expected(labels, frame_index)
    for stage in stages.values():
        stage["comparison"] = _compare(stage, expected)
    return {
        "frame_index": frame_index,
        "timestamp_seconds": frame_index / fps,
        "expected": expected,
        "candidate_hard_reasons": [item.value for item in candidate.candidate.retry_reasons],
        "seam_fraction": candidate.seam_proxy_fraction,
        "spread_extraction": {
            "success": extraction.success,
            "reason": extraction.reason,
            "elapsed_ms": extraction_ms,
            "diagnostics": dict(extraction.diagnostics),
        },
        "uvdoc": uvdoc_records,
        "stages": stages,
    }


def _evaluate_stage(
    name: str,
    rois: dict[PageSide, tuple[np.ndarray, tuple[int, int, int, int]]],
    errors: dict[str, str],
    frame_id: FrameId,
    source: PageNumberSource,
    policy: PageNumberPolicy,
    provider: OpenCVBottomRoiPageNumberProvider,
    recognizer: TracingPaddleRecognizer,
    frame_dir: Path,
) -> dict[str, Any]:
    observations = []
    sides: dict[str, Any] = {}
    for side in PageSide:
        if side not in rois:
            sides[side.value] = {"status": "stage_error", "error": errors.get(side.value, "ROI unavailable")}
            continue
        roi, bbox = rois[side]
        roi_path = frame_dir / f"{name}_{side.value}_roi.png"
        cv2.imwrite(str(roi_path), roi)
        binary, clusters = _candidate_clusters(roi, side, policy.max_digits)
        boxes = [_union(cluster) for cluster in clusters]
        cv2.imwrite(str(frame_dir / f"{name}_{side.value}_binary.png"), binary)
        overlay = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR) if roi.ndim == 2 else roi.copy()
        for index, (x, y, width, height) in enumerate(boxes):
            cv2.rectangle(overlay, (x, y), (x + width, y + height), (0, 0, 255), 2)
            cv2.putText(overlay, str(index), (x, max(12, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
        cv2.imwrite(str(frame_dir / f"{name}_{side.value}_candidates.png"), overlay)
        recognition_started = time.perf_counter()
        observation = provider._observe_roi(  # diagnostic runner intentionally uses the production gate
            roi,
            bbox,
            side,
            source,
            frame_id,
            None,
        )
        recognition_ms = (time.perf_counter() - recognition_started) * 1000.0
        predictions = list(recognizer.last_predictions)
        candidates = []
        for index, candidate_bbox in enumerate(boxes[:4]):
            start = index * 2
            candidates.append(
                {
                    "bbox": list(candidate_bbox),
                    "original": predictions[start] if start < len(predictions) else None,
                    "clahe": predictions[start + 1] if start + 1 < len(predictions) else None,
                }
            )
        cause = _failure_cause(observation.status.value, observation.normalized_label, boxes, predictions)
        sides[side.value] = {
            "status": observation.status.value,
            "raw_text": observation.raw_text,
            "normalized_label": observation.normalized_label,
            "confidence": observation.confidence,
            "variant_agreement": observation.variant_agreement,
            "roi_bbox": list(bbox),
            "roi_shape": list(roi.shape),
            "candidate_count": len(boxes),
            "candidates": candidates,
            "failure_cause": cause,
            "recognition_ms": recognition_ms,
            "roi_path": str(roi_path.resolve()),
        }
        observations.append(observation)
    if len(observations) == 2:
        spread = _spread(observations[0], observations[1], "paired-stage-experiment", policy, 0.0)
        status = spread.status.value
        key = (
            {"left": spread.key.left_page_label, "right": spread.key.right_page_label}
            if spread.key is not None
            else None
        )
    else:
        status, key = "stage_error", None
    return {
        "status": status,
        "key": key,
        "sides": sides,
        "recognition_ms": sum(float(item.get("recognition_ms", 0.0)) for item in sides.values()),
    }


def _failure_cause(status: str, normalized: str | None, boxes: list[tuple[int, int, int, int]], predictions: list[dict[str, Any]]) -> str | None:
    if status == "observed" and normalized is not None:
        return None
    if not boxes:
        return "candidate_locator_empty"
    valid = [item for item in predictions if str(item.get("text", "")).isdigit()]
    if not valid:
        return "paddle_no_numeric_prediction"
    if status == "conflict":
        texts = {str(item["text"]) for item in valid}
        return "variant_disagreement" if len(texts) > 1 else "only_one_valid_variant_or_low_confidence"
    if status == "invalid":
        return "numeric_prediction_failed_page_label_normalization"
    return "candidate_not_selected_as_valid"


def _adaptive_preview_fallback(primary: dict[str, Any], native: dict[str, Any]) -> dict[str, Any]:
    """Fuse an already-computed native result without overriding 1920 observations."""

    fused_sides: dict[str, Any] = {}
    consulted: list[str] = []
    for side in ("left", "right"):
        primary_side = primary["sides"].get(side, {})
        if primary_side.get("status") == "observed":
            selected = copy.deepcopy(primary_side)
            selected["selected_from"] = "preview_1920"
        else:
            consulted.append(side)
            native_side = native["sides"].get(side, {})
            if native_side.get("status") == "observed":
                selected = copy.deepcopy(native_side)
                selected["selected_from"] = "preview_native_fallback"
                selected["failure_cause"] = None
            else:
                selected = copy.deepcopy(primary_side)
                selected["selected_from"] = "preview_1920_unresolved"
        fused_sides[side] = selected
    statuses = [fused_sides[side].get("status") for side in ("left", "right")]
    observed = sum(status == "observed" for status in statuses)
    if observed == 2:
        status = "complete"
        key = {
            "left": fused_sides["left"]["normalized_label"],
            "right": fused_sides["right"]["normalized_label"],
        }
    elif any(status in {"conflict", "invalid"} for status in statuses):
        status, key = "conflict", None
    elif observed == 1:
        status, key = "partial", None
    else:
        status, key = "missing", None
    return {
        "status": status,
        "key": key,
        "sides": fused_sides,
        "native_sides_consulted": consulted,
        "recognition_ms": float(primary.get("recognition_ms", 0.0)) + sum(
            float(native["sides"].get(side, {}).get("recognition_ms", 0.0))
            for side in consulted
        ),
        "estimated_roi_calls": 2 + len(consulted),
        "derived_from_frozen_stage_outputs": True,
    }


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    stage_names = (
        "preview_1920",
        "preview_native",
        "seam_crop",
        "seam_crop_uvdoc",
        "adaptive_preview_fallback",
    )
    summary: dict[str, Any] = {}
    for name in stage_names:
        evaluated = [record for record in records if record["stages"][name]["status"] != "stage_error"]
        p30 = [record for record in evaluated if record["expected"].get("spread") == "p030_spread"]
        summary[name] = {
            "evaluated_frames": len(evaluated),
            "complete_frames": sum(record["stages"][name]["status"] == "complete" for record in evaluated),
            "exact_spread_frames_diagnostic": sum(record["stages"][name]["comparison"]["spread_exact"] is True for record in evaluated),
            "p30_frames": len(p30),
            "p30_left_user_golden_correct": sum(record["stages"][name]["comparison"]["left_exact"] is True for record in p30),
            "p30_spread_exact_diagnostic": sum(record["stages"][name]["comparison"]["spread_exact"] is True for record in p30),
            "failure_causes": _cause_counts(evaluated, name),
            "median_recognition_ms": (
                statistics.median(float(record["stages"][name].get("recognition_ms", 0.0)) for record in evaluated)
                if evaluated
                else None
            ),
        }
        if name == "adaptive_preview_fallback":
            summary[name]["native_side_consults"] = sum(
                len(record["stages"][name]["native_sides_consulted"])
                for record in evaluated
            )
    baseline = summary["preview_1920"]
    for name in stage_names[1:]:
        summary[name]["delta_vs_preview_1920"] = {
            "p30_left_user_golden_correct": summary[name]["p30_left_user_golden_correct"] - baseline["p30_left_user_golden_correct"],
            "p30_spread_exact_diagnostic": summary[name]["p30_spread_exact_diagnostic"] - baseline["p30_spread_exact_diagnostic"],
        }
    return summary


def _compare(stage: dict[str, Any], expected: dict[str, Any]) -> dict[str, bool | None]:
    left_expected, right_expected = expected.get("left"), expected.get("right")
    left_actual = stage["sides"].get("left", {}).get("normalized_label")
    right_actual = stage["sides"].get("right", {}).get("normalized_label")
    left_exact = left_actual == left_expected if left_expected is not None else None
    right_exact = right_actual == right_expected if right_expected is not None else None
    spread_exact = left_exact and right_exact if left_exact is not None and right_exact is not None else None
    return {"left_exact": left_exact, "right_exact": right_exact, "spread_exact": spread_exact}


def _cause_counts(records: list[dict[str, Any]], stage: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for side in ("left", "right"):
            cause = record["stages"][stage]["sides"].get(side, {}).get("failure_cause")
            if cause:
                counts[cause] = counts.get(cause, 0) + 1
    return counts


def _expected(labels: dict[str, Any], frame_index: int) -> dict[str, Any]:
    for run in labels["stable_runs"]:
        if run["start_frame_inclusive"] <= frame_index <= run["end_frame_inclusive"]:
            spread = run["page_spread"]
            scope = labels["page_label_scope"][spread]
            return {
                "spread": spread,
                "left": scope["left"]["value"],
                "left_status": scope["left"]["status"],
                "right": scope["right"]["value"],
                "right_status": scope["right"]["status"],
            }
    return {"spread": None, "left": None, "right": None}


def _read_frames(video: Path, indices: list[int]) -> dict[int, np.ndarray]:
    wanted = set(indices)
    result: dict[int, np.ndarray] = {}
    capture = cv2.VideoCapture(str(video.resolve()))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open video: {video}")
    try:
        frame_index = -1
        while wanted:
            ok, frame = capture.read()
            if not ok or frame is None:
                break
            frame_index += 1
            if frame_index in wanted:
                result[frame_index] = frame.copy()
                wanted.remove(frame_index)
    finally:
        capture.release()
    return result


def _union(cluster: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    x0 = min(item[0] for item in cluster)
    y0 = min(item[1] for item in cluster)
    x1 = max(item[0] + item[2] for item in cluster)
    y1 = max(item[1] + item[3] for item in cluster)
    return x0, y0, x1 - x0, y1 - y0


def _verify_model_manifest(model_dir: Path, manifest: dict[str, Any]) -> None:
    for relative, expected in manifest["files"].items():
        path = model_dir / relative
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"model asset mismatch: {relative}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
