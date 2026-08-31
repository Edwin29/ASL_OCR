"""Capture frozen OCR tokens and visual descriptors for V3-A.4 replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from book_scanner.evaluation.footer_identity import build_footer_visual_descriptor
from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.config import CandidatePolicy, PageNumberPolicy
from book_scanner.video.engine import _page_number_preview_inputs
from book_scanner.video.identity import IdentityFingerprintError, OpenCVIdentityFingerprinter
from book_scanner.video.obstruction import EdgeChromaIntrusionObstructionDetector
from book_scanner.video.page_number import PageNumberSource
from book_scanner.video.page_number_provider import OpenCVBottomRoiPageNumberProvider, _spread
from book_scanner.video.page_number_recognizer import PaddleRoiDigitRecognizer, _candidate_clusters
from book_scanner.video.page_number_roi import preview_page_number_roi
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import FrameId, PageSide


class TracingPaddleRecognizer(PaddleRoiDigitRecognizer):
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
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "gpu:0"), default="cpu")
    args = parser.parse_args()

    manifest = _read_json(args.manifest)
    model_manifest = _read_json(args.model_manifest)
    expected_video_hash = str(manifest["source_video"]["sha256"])
    actual_video_hash = _sha256(args.video)
    if actual_video_hash != expected_video_hash:
        raise ValueError("source video SHA-256 mismatch")

    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    import paddle

    paddle.set_device(args.device)
    policy = PageNumberPolicy()
    recognizer = TracingPaddleRecognizer(
        args.model_dir,
        policy,
        expected_file_hashes=model_manifest["files"],
        device=args.device,
    )
    provider = OpenCVBottomRoiPageNumberProvider(policy, recognizer)
    analyzer = OpenCVCandidateAnalyzer(
        CandidatePolicy(sample_interval_ms=100),
        obstruction_detector=EdgeChromaIntrusionObstructionDetector(),
    )
    fingerprinter = OpenCVIdentityFingerprinter()
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    save_frames = {int(item) for item in manifest["capture"]["save_image_frame_indices"]}
    blocks = _blocks(manifest)
    minimum_frame = min(item["start_frame_inclusive"] for item in blocks.values())
    maximum_frame = max(item["end_frame_inclusive"] for item in blocks.values())

    capture = cv2.VideoCapture(str(args.video.resolve()))
    if not capture.isOpened():
        raise RuntimeError(f"cannot open video: {args.video}")
    records: list[dict[str, Any]] = []
    frame_index = -1
    started = time.perf_counter()
    try:
        while True:
            ok, image = capture.read()
            if not ok or image is None:
                break
            frame_index += 1
            if frame_index < minimum_frame:
                continue
            if frame_index > maximum_frame:
                break
            matching_blocks = [name for name, block in blocks.items() if block["start_frame_inclusive"] <= frame_index <= block["end_frame_inclusive"]]
            if not matching_blocks:
                continue
            frame_id = FrameId(f"video-frame-{frame_index:06d}")
            sample = FrameSample(frame_id, frame_index / float(manifest["source_video"]["fps"]), image)
            analyzed = analyzer.analyze(sample)
            reasons = [item.value for item in analyzed.candidate.retry_reasons]
            record: dict[str, Any] = {
                "frame_index": frame_index,
                "timestamp_seconds": sample.captured_at_monotonic,
                "block_ids": matching_blocks,
                "spread_label": blocks[matching_blocks[0]]["spread_label"],
                "eligible": not reasons,
                "hard_reasons": reasons,
                "seam_fraction": analyzed.seam_proxy_fraction,
                "stages": {},
                "full_visual": None,
            }
            if reasons:
                records.append(record)
                continue
            try:
                full_visual = fingerprinter.fingerprint_preview(
                    analyzed.gray_preview,
                    analyzed.mask_preview,
                    analyzed.seam_proxy_fraction,
                )
                record["full_visual"] = {
                    "left": _full_visual(full_visual.left),
                    "right": _full_visual(full_visual.right),
                }
            except IdentityFingerprintError as exc:
                record["eligible"] = False
                record["hard_reasons"] = ["IDENTITY_FINGERPRINT_ERROR"]
                record["error"] = str(exc)
                records.append(record)
                continue

            for stage_name, max_dimension in (
                ("preview_1920", policy.preview_max_dimension),
                ("preview_native", max(image.shape[:2])),
            ):
                gray, mask = _page_number_preview_inputs(image, analyzed.mask_preview, max_dimension)
                record["stages"][stage_name] = _capture_stage(
                    stage_name,
                    gray,
                    mask,
                    analyzed.seam_proxy_fraction,
                    frame_id,
                    policy,
                    provider,
                    recognizer,
                    args.artifact_dir if frame_index in save_frames else None,
                    frame_index,
                )
            records.append(record)
            if frame_index % 30 == 0:
                print(f"captured frame {frame_index}", flush=True)
    finally:
        capture.release()

    payload = {
        "schema_version": 1,
        "status": "FROZEN_DIAGNOSTIC_OBSERVATIONS",
        "manifest_path": str(args.manifest.resolve()),
        "manifest_sha256": _sha256(args.manifest),
        "source_video": {**manifest["source_video"], "path": str(args.video.resolve())},
        "recognition_model": {
            "model_dir": str(args.model_dir.resolve()),
            "model_manifest_path": str(args.model_manifest.resolve()),
            "model_manifest_sha256": _sha256(args.model_manifest),
            "verified_file_hashes": recognizer.verified_file_hashes,
            "model_bytes": recognizer.model_bytes,
        },
        "runtime": {
            "device": args.device,
            "paddle_version": paddle.__version__,
            "opencv_version": cv2.__version__,
            "recognizer_load_count": recognizer.load_count,
            "recognizer_calls": recognizer.calls,
            "cache_hits": provider.cache.hits,
            "wall_seconds": time.perf_counter() - started,
            "runtime_download_allowed": False,
        },
        "counts": {
            "records": len(records),
            "eligible": sum(bool(item["eligible"]) for item in records),
            "rejected": sum(not bool(item["eligible"]) for item in records),
        },
        "records": records,
        "limitations": manifest["limitations"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": payload["counts"], "runtime": payload["runtime"]}, ensure_ascii=False, indent=2))
    return 0


def _capture_stage(
    stage_name: str,
    gray: np.ndarray,
    mask: np.ndarray,
    seam_fraction: float | None,
    frame_id: FrameId,
    policy: PageNumberPolicy,
    provider: OpenCVBottomRoiPageNumberProvider,
    recognizer: TracingPaddleRecognizer,
    artifact_dir: Path | None,
    frame_index: int,
) -> dict[str, Any]:
    sides: dict[str, Any] = {}
    observations = []
    for side in PageSide:
        try:
            roi, bbox = preview_page_number_roi(gray, mask, seam_fraction, side, policy)
        except ValueError as exc:
            sides[side.value] = {"status": "stage_error", "error": str(exc)}
            continue
        _binary, clusters = _candidate_clusters(roi, side, policy.max_digits)
        boxes = [_union(cluster) for cluster in clusters]
        recognizer.last_predictions = []
        recognition_started = time.perf_counter()
        observation = provider._observe_roi(
            roi,
            bbox,
            side,
            PageNumberSource.PREVIEW,
            frame_id,
            None,
        )
        recognition_ms = (time.perf_counter() - recognition_started) * 1000.0
        descriptor_started = time.perf_counter()
        descriptor = build_footer_visual_descriptor(roi)
        descriptor_ms = (time.perf_counter() - descriptor_started) * 1000.0
        predictions = list(recognizer.last_predictions)
        local_observation_bbox = (
            (
                observation.bbox[0] - bbox[0],
                observation.bbox[1] - bbox[1],
                observation.bbox[2],
                observation.bbox[3],
            )
            if observation.bbox is not None
            else None
        )
        selected_index = boxes.index(local_observation_bbox) if local_observation_bbox in boxes else None
        selected_candidate_predictions = (
            predictions[selected_index * 2 : selected_index * 2 + 2]
            if selected_index is not None
            else []
        )
        variant_tokens = [
            str(item["text"]).strip()
            for item in selected_candidate_predictions
            if str(item.get("text", "")).strip()
        ]
        roi_path = None
        if artifact_dir is not None:
            frame_dir = artifact_dir / f"frame_{frame_index:06d}"
            frame_dir.mkdir(parents=True, exist_ok=True)
            roi_path = frame_dir / f"{stage_name}_{side.value}_roi.png"
            cv2.imwrite(str(roi_path), roi)
            overlay = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
            for index, (x, y, width, height) in enumerate(boxes):
                cv2.rectangle(overlay, (x, y), (x + width, y + height), (0, 0, 255), 2)
                cv2.putText(overlay, str(index), (x, max(12, y - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
            cv2.imwrite(str(frame_dir / f"{stage_name}_{side.value}_candidates.png"), overlay)
        sides[side.value] = {
            "status": observation.status.value,
            "selected_raw": observation.raw_text,
            "normalized_label": observation.normalized_label,
            "confidence": observation.confidence,
            "variant_agreement": observation.variant_agreement,
            "variant_tokens": variant_tokens,
            "variant_predictions": selected_candidate_predictions,
            "selected_candidate_index": selected_index,
            "candidate_count": len(boxes),
            "candidate_bboxes": [list(item) for item in boxes],
            "roi_bbox": list(bbox),
            "roi_shape": list(roi.shape),
            "roi_sha256": observation.roi_sha256,
            "recognition_ms": recognition_ms,
            "visual_descriptor_ms": descriptor_ms,
            "visual": descriptor,
            "roi_path": str(roi_path.resolve()) if roi_path is not None else None,
        }
        observations.append(observation)
    if len(observations) == 2:
        spread = _spread(observations[0], observations[1], "v3a4-footer-experiment", policy, 0.0)
        status = spread.status.value
        key = (
            {"left": spread.key.left_page_label, "right": spread.key.right_page_label}
            if spread.key is not None
            else None
        )
    else:
        status, key = "stage_error", None
    return {"status": status, "semantic_key": key, "sides": sides}


def _full_visual(value: Any) -> dict[str, Any]:
    return {
        "algorithm_version": value.algorithm_version,
        "perceptual_hash": value.perceptual_hash,
        "horizontal_projection": list(value.horizontal_projection),
        "vertical_projection": list(value.vertical_projection),
        "normalized_width": value.normalized_width,
        "normalized_height": value.normalized_height,
        "orb_descriptors_hex": [item.hex() for item in value.orb_descriptors],
    }


def _blocks(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(name): dict(value) for name, value in manifest["blocks"].items()}


def _union(cluster: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    x0 = min(item[0] for item in cluster)
    y0 = min(item[1] for item in cluster)
    x1 = max(item[0] + item[2] for item in cluster)
    y1 = max(item[1] + item[3] for item in cluster)
    return x0, y0, x1 - x0, y1 - y0


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
