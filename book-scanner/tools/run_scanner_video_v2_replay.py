"""Replay manually reviewed clean MP4 frames through the production V2 preparer."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from book_scanner.correct.uvdoc_adapter import UVDocConfig
from book_scanner.video.artifacts import FilesystemArtifactStore
from book_scanner.video.protocols import FrameSample
from book_scanner.video.spread_preparer import SeamUVDocPreparerConfig, SeamUVDocSpreadPreparer
from book_scanner.video.types import FrameId, ProcessingJobId, SpreadId


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--uvdoc-runtime", type=Path, required=True)
    parser.add_argument("--uvdoc-checkpoint", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--timestamp",
        type=float,
        action="append",
        required=True,
        help="Human-reviewed, hand-free stable timestamp in seconds; repeat for each frame.",
    )
    parser.add_argument("--session-id", default="scanner-video-v2-mp4-replay")
    args = parser.parse_args()

    video = args.video.resolve()
    if not video.is_file():
        parser.error(f"video does not exist: {video}")
    if any(value < 0 for value in args.timestamp):
        parser.error("timestamps must be non-negative")
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f"output directory must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    metadata_capture = cv2.VideoCapture(str(video))
    if not metadata_capture.isOpened():
        parser.error(f"could not open video: {video}")
    fps = float(metadata_capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(metadata_capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(metadata_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(metadata_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    metadata_capture.release()
    decoded_frames = _read_frames(video, args.timestamp, fps)

    store = FilesystemArtifactStore(output / "staging", output / "ready")
    preparer = SeamUVDocSpreadPreparer(
        SeamUVDocPreparerConfig(staging_root=store.staging_root),
        UVDocConfig(
            runtime_path=args.uvdoc_runtime,
            checkpoint_path=args.uvdoc_checkpoint,
            device=args.device,
            sampling_mode="bilinear",
        ),
    )

    records: list[dict[str, object]] = []
    for ordinal, requested_timestamp in enumerate(args.timestamp, 1):
        decoded = decoded_frames[ordinal - 1]
        if decoded is None:
            records.append(
                {
                    "requested_timestamp_seconds": requested_timestamp,
                    "status": "BLOCKED_FRAME_DECODE_FAILED",
                }
            )
            continue
        frame_index, image = decoded
        actual_timestamp = frame_index / fps if fps > 0 else requested_timestamp
        frame_id = FrameId(f"video-frame-{frame_index:06d}")
        decision = preparer.prepare(
            FrameSample(frame_id, actual_timestamp, image),
            SpreadId(f"video-spread-{ordinal:02d}"),
            ProcessingJobId(f"video-job-{ordinal:02d}"),
            args.session_id,
        )
        record: dict[str, object] = {
            "requested_timestamp_seconds": requested_timestamp,
            "actual_timestamp_seconds": actual_timestamp,
            "frame_index": frame_index,
            "source_frame_id": frame_id.value,
            "selection_basis": "manual_visual_review_hand_free_stable",
            "state": decision.state.value,
            "reasons": [reason.value for reason in decision.reasons],
            "metrics": dict(decision.metrics),
        }
        if decision.prepared is not None:
            artifact = store.commit(decision.prepared)
            manifest_path = Path(artifact.manifest_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            record.update(
                {
                    "artifact_id": artifact.artifact_id.value,
                    "manifest_path": str(manifest_path.relative_to(output)),
                    "same_source_frame": (
                        artifact.source_frame_id
                        == artifact.left.source_frame_id
                        == artifact.right.source_frame_id
                    ),
                    "left_bbox_full": manifest["pages"]["left"]["bbox_full"],
                    "right_bbox_full": manifest["pages"]["right"]["bbox_full"],
                    "left_uvdoc_sha256": artifact.left.sha256,
                    "right_uvdoc_sha256": artifact.right.sha256,
                    "uvdoc_load_count": manifest["uvdoc_runtime"]["load_count"],
                    "bundle_size_bytes": sum(
                        path.stat().st_size
                        for path in manifest_path.parent.rglob("*")
                        if path.is_file()
                    ),
                }
            )
        records.append(record)
    complete = bool(records) and all(
        record.get("state") == "prepared" and record.get("same_source_frame") is True
        for record in records
    )
    summary = {
        "schema_version": 1,
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "scope": "v2_local_artifact_replay_only",
        "automatic_stable_selection_validated": False,
        "selection_note": (
            "Timestamps were selected by human visual review. This result does not validate "
            "the V1 automatic candidate/stability gate."
        ),
        "source_video": {
            "path": str(video),
            "size_bytes": video.stat().st_size,
            "sha256": _sha256_file(video),
            "width": width,
            "height": height,
            "fps": fps,
            "frame_count": frame_count,
            "duration_seconds": frame_count / fps if fps > 0 else None,
        },
        "sampling_mode": "bilinear",
        "record_count": len(records),
        "final_uvdoc_load_count": getattr(preparer.unwarper, "load_count", None),
        "records": records,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if complete else 1


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_frames(
    path: Path,
    timestamps_seconds: list[float],
    fps: float,
) -> list[tuple[int, np.ndarray] | None]:
    """Decode targets in one forward pass; OpenCV seeking is codec-dependent."""
    target_indices = [max(0, round(timestamp * fps)) for timestamp in timestamps_seconds]
    requested_at: dict[int, list[int]] = {}
    for ordinal, frame_index in enumerate(target_indices):
        requested_at.setdefault(frame_index, []).append(ordinal)
    results: list[tuple[int, np.ndarray] | None] = [None] * len(target_indices)
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            return results
        for frame_index in range(max(target_indices, default=-1) + 1):
            if not capture.grab():
                break
            ordinals = requested_at.get(frame_index)
            if ordinals is None:
                continue
            ok, image = capture.retrieve()
            if not ok or image is None:
                continue
            for ordinal in ordinals:
                results[ordinal] = (frame_index, image.copy())
        return results
    finally:
        capture.release()


if __name__ == "__main__":
    sys.exit(main())
