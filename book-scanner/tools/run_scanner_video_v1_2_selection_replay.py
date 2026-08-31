"""Forward-decode a video and record reproducible V1.2 selection decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from book_scanner.video.candidate import CandidateWindow, OpenCVCandidateAnalyzer, StableWindowAssessor
from book_scanner.video.config import CandidatePolicy
from book_scanner.video.obstruction import (
    DiagnosticChromaContourObstructionDetector,
    EdgeChromaIntrusionObstructionDetector,
    MediaPipeHandConfig,
    MediaPipeHandObstructionDetector,
)
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import FrameId


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--anchor-manifest", type=Path)
    parser.add_argument("--sample-interval-ms", type=int, default=500)
    parser.add_argument("--stable-sample-count", type=int, default=3)
    parser.add_argument("--sample-window-size", type=int, default=5)
    parser.add_argument("--mediapipe-model", type=Path)
    parser.add_argument("--mediapipe-model-sha256")
    parser.add_argument(
        "--obstruction-detector",
        choices=("edge-chroma", "diagnostic-chroma", "mediapipe"),
        default="edge-chroma",
    )
    parser.add_argument(
        "--reject-content-edge-clipping",
        action="store_true",
        help="Opt into the provisional edge-strip clipping hard gate for comparison only.",
    )
    args = parser.parse_args()

    video = args.video.resolve()
    output = args.output_dir.resolve()
    if not video.is_file():
        parser.error(f"video does not exist: {video}")
    if args.sample_interval_ms <= 0:
        parser.error("sample interval must be positive")
    if args.stable_sample_count <= 0:
        parser.error("stable sample count must be positive")
    if args.sample_window_size < args.stable_sample_count:
        parser.error("sample window size must be at least stable sample count")
    if output.exists() and any(output.iterdir()):
        parser.error(f"output directory must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    anchors = _read_anchor_manifest(args.anchor_manifest)
    anchors_by_index = {int(item["frame_index"]): item for item in anchors}
    anchor_dir = output / "anchors"
    selected_dir = output / "selected"
    anchor_dir.mkdir()
    selected_dir.mkdir()

    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        parser.error(f"could not open video: {video}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0:
        capture.release()
        parser.error("video FPS is unavailable")
    frame_step = max(1, round(fps * args.sample_interval_ms / 1000.0))

    if bool(args.mediapipe_model) != bool(args.mediapipe_model_sha256):
        parser.error("MediaPipe model path and SHA-256 must be supplied together")
    if args.obstruction_detector == "mediapipe" and args.mediapipe_model is None:
        parser.error("the mediapipe detector requires a model path and SHA-256")
    if args.obstruction_detector != "mediapipe" and args.mediapipe_model is not None:
        parser.error("MediaPipe model arguments require --obstruction-detector mediapipe")
    if args.obstruction_detector == "mediapipe":
        obstruction_detector = MediaPipeHandObstructionDetector(
            MediaPipeHandConfig(
                model_path=args.mediapipe_model,
                expected_sha256=args.mediapipe_model_sha256,
            )
        )
    elif args.obstruction_detector == "diagnostic-chroma":
        obstruction_detector = DiagnosticChromaContourObstructionDetector()
    else:
        obstruction_detector = EdgeChromaIntrusionObstructionDetector()
    policy = CandidatePolicy(
        sample_interval_ms=args.sample_interval_ms,
        stable_sample_count=args.stable_sample_count,
        sample_window_size=args.sample_window_size,
        reject_confirmed_content_clipping=args.reject_content_edge_clipping,
    )
    analyzer = OpenCVCandidateAnalyzer(policy, obstruction_detector=obstruction_detector)
    assessor = StableWindowAssessor(policy)
    window = CandidateWindow(policy.sample_window_size)
    samples: list[dict[str, Any]] = []
    selected_indices: list[int] = []
    anchor_records: list[dict[str, Any]] = []
    frame_index = -1
    replay_started = time.perf_counter()
    candidate_analysis_seconds = 0.0
    try:
        while True:
            ok, image = capture.read()
            if not ok or image is None:
                break
            frame_index += 1
            anchor = anchors_by_index.get(frame_index)
            if anchor is not None:
                filename = f"frame-{frame_index:06d}-{_safe_label(str(anchor['label']))}.jpg"
                _write_image(anchor_dir / filename, image)
                anchor_records.append(
                    {
                        **anchor,
                        "actual_timestamp_seconds": frame_index / fps,
                        "image_path": str(Path("anchors") / filename),
                    }
                )
            if frame_index % frame_step != 0:
                continue

            frame = FrameSample(
                FrameId(f"video-frame-{frame_index:06d}"), frame_index / fps, image.copy()
            )
            analysis_started = time.perf_counter()
            observation = analyzer.analyze(frame)
            candidate_analysis_seconds += time.perf_counter() - analysis_started
            window.append(observation)
            assessment = assessor.assess(window.snapshot())
            selected = assessment.best
            selected_index = None
            if assessment.stable and selected is not None:
                selected_index = int(selected.frame.frame_id.value.rsplit("-", 1)[1])
                if selected_index not in selected_indices:
                    selected_indices.append(selected_index)
                    _write_image(
                        selected_dir / f"frame-{selected_index:06d}.jpg",
                        selected.frame.payload,
                    )
            samples.append(
                {
                    "frame_index": frame_index,
                    "timestamp_seconds": frame_index / fps,
                    "candidate": observation.candidate.to_dict(),
                    "assessment": {
                        "stable": assessment.stable,
                        "reasons": [item.value for item in assessment.reasons],
                        "metrics": dict(assessment.metrics),
                        "selected_frame_index": selected_index,
                    },
                }
            )
    finally:
        capture.release()
        close = getattr(obstruction_detector, "close", None)
        if close is not None:
            close()

    label_by_index = {int(item["frame_index"]): str(item["label"]) for item in anchor_records}
    samples_by_index = {int(item["frame_index"]): item for item in samples}
    predictions = {}
    for index in sorted(label_by_index):
        sample_record = samples_by_index.get(index)
        assessment = sample_record["assessment"] if sample_record is not None else None
        predictions[str(index)] = {
            "anchor_label": label_by_index[index],
            "sampled_by_v1": sample_record is not None,
            "window_ending_at_anchor_is_stable": (
                bool(assessment["stable"]) if assessment is not None else None
            ),
            "window_selected_frame_index": (
                assessment["selected_frame_index"] if assessment is not None else None
            ),
            "anchor_frame_selected_by_any_window": index in selected_indices,
        }
    confirmed = [item for item in anchor_records if item.get("label_status") == "USER_CONFIRMED"]
    confirmed_positive = [item for item in confirmed if item["label"] == "CLEAN_TRANSFERABLE"]
    confirmed_negative = [item for item in confirmed if item["label"] != "CLEAN_TRANSFERABLE"]
    positive_recovered = [
        int(item["frame_index"])
        for item in confirmed_positive
        if predictions[str(item["frame_index"])]["window_ending_at_anchor_is_stable"]
        or predictions[str(item["frame_index"])]["anchor_frame_selected_by_any_window"]
    ]
    negative_false_accepts = [
        int(item["frame_index"])
        for item in confirmed_negative
        if predictions[str(item["frame_index"])]["window_ending_at_anchor_is_stable"]
        or predictions[str(item["frame_index"])]["anchor_frame_selected_by_any_window"]
    ]
    labels_pending = len(confirmed) != len(anchor_records)
    replay_wall_seconds = time.perf_counter() - replay_started
    if labels_pending:
        status = "PROVISIONAL_AWAITING_ANCHOR_LABELS_AND_HELD_OUT_VIDEO"
    elif len(positive_recovered) != len(confirmed_positive):
        status = "PROVISIONAL_CONFIRMED_POSITIVE_NOT_RECOVERED"
    elif negative_false_accepts:
        status = "PROVISIONAL_CONFIRMED_NEGATIVE_FALSE_ACCEPT"
    else:
        status = "PROVISIONAL_AWAITING_HELD_OUT_VIDEO"
    reason_counts = Counter(
        reason
        for sample in samples
        for reason in sample["assessment"]["reasons"]
    )
    first_stable = next(
        (sample for sample in samples if bool(sample["assessment"]["stable"])),
        None,
    )
    summary = {
        "schema_version": 1,
        "status": status,
        "source_video": {
            "path": str(video),
            "size_bytes": video.stat().st_size,
            "sha256": _sha256_file(video),
            "width": width,
            "height": height,
            "fps": fps,
            "frame_count": frame_count,
            "duration_seconds": frame_count / fps,
        },
        "sampling": {
            "interval_ms": args.sample_interval_ms,
            "frame_step": frame_step,
            "decode_mode": "single_forward_pass",
            "stable_sample_count": policy.stable_sample_count,
            "sample_window_size": policy.sample_window_size,
        },
        "policy": {
            "reject_outer_frame_contacts": policy.reject_outer_frame_contacts,
            "reject_confirmed_content_clipping": policy.reject_confirmed_content_clipping,
            "validated": policy.validated,
            "provenance": policy.provenance,
        },
        "candidate_evaluator_version": analyzer.evaluator_version,
        "obstruction_detector": getattr(
            obstruction_detector,
            "runtime_provenance",
            getattr(obstruction_detector, "provenance", obstruction_detector.name),
        ),
        "sample_count": len(samples),
        "runtime": {
            "wall_seconds": replay_wall_seconds,
            "candidate_analysis_seconds_total": candidate_analysis_seconds,
            "candidate_analysis_ms_per_sample": (
                candidate_analysis_seconds * 1000.0 / len(samples) if samples else None
            ),
            "note": "Single-run PC prototype timing; forward 4K decode is included only in wall_seconds.",
        },
        "stable_window_count": sum(bool(item["assessment"]["stable"]) for item in samples),
        "selected_frame_indices": selected_indices,
        "first_selection": (
            {
                "window_ending_frame_index": first_stable["frame_index"],
                "selected_frame_index": first_stable["assessment"]["selected_frame_index"],
            }
            if first_stable is not None
            else None
        ),
        "assessment_reason_counts": dict(sorted(reason_counts.items())),
        "anchor_predictions": predictions,
        "anchor_evaluation": {
            "confirmed_positive_count": len(confirmed_positive),
            "confirmed_negative_count": len(confirmed_negative),
            "positive_recovered_count": len(positive_recovered),
            "positive_recovered_frame_indices": positive_recovered,
            "negative_false_accept_count": len(negative_false_accepts),
            "negative_false_accept_frame_indices": negative_false_accepts,
        },
        "anchors": anchor_records,
        "samples": samples,
    }
    if anchor_records:
        _write_contact_sheet(output, anchor_records)
        summary["anchor_contact_sheet"] = "anchor_contact_sheet.jpg"
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "samples"}, ensure_ascii=False, indent=2))
    return 0


def _read_anchor_manifest(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.resolve().read_text(encoding="utf-8"))
    anchors = payload.get("anchors")
    if not isinstance(anchors, list):
        raise ValueError("anchor manifest must contain an anchors array")
    result: list[dict[str, Any]] = []
    for item in anchors:
        if not isinstance(item, dict) or not isinstance(item.get("frame_index"), int):
            raise ValueError("each anchor must have an integer frame_index")
        if not isinstance(item.get("label"), str) or not item["label"].strip():
            raise ValueError("each anchor must have a non-empty label")
        result.append(dict(item))
    return result


def _safe_label(label: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in label).strip("-")


def _write_image(path: Path, image: Any) -> None:
    if not cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 94]):
        raise RuntimeError(f"could not write image: {path}")


def _write_contact_sheet(output: Path, anchor_records: list[dict[str, Any]]) -> None:
    columns = 3
    tile_width, tile_height = 640, 400
    rows = (len(anchor_records) + columns - 1) // columns
    sheet = np.full((rows * tile_height, columns * tile_width, 3), 24, dtype=np.uint8)
    for ordinal, record in enumerate(anchor_records):
        image = cv2.imread(str(output / str(record["image_path"])), cv2.IMREAD_COLOR)
        if image is None:
            continue
        target_height = tile_height - 54
        scale = min(tile_width / image.shape[1], target_height / image.shape[0])
        resized = cv2.resize(
            image,
            (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
        row, column = divmod(ordinal, columns)
        x0 = column * tile_width + (tile_width - resized.shape[1]) // 2
        y0 = row * tile_height + 42
        sheet[y0 : y0 + resized.shape[0], x0 : x0 + resized.shape[1]] = resized
        label = f"{record['frame_index']}  {record['label']}"
        cv2.putText(
            sheet,
            label,
            (column * tile_width + 12, row * tile_height + 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.63,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    _write_image(output / "anchor_contact_sheet.jpg", sheet)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
