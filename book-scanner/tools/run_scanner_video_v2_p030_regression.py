"""Run the V2 seam-conservative + UVDoc bundle path on p30 captures."""

from __future__ import annotations

import argparse
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

DEFAULT_CAPTURES = ("20260830_111919", "20260830_112000", "20260830_112042")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--uvdoc-runtime", type=Path, required=True)
    parser.add_argument("--uvdoc-checkpoint", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--reference-image-dir", type=Path)
    parser.add_argument("--captures", nargs="+", default=list(DEFAULT_CAPTURES))
    args = parser.parse_args()

    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f"output directory must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
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
    for index, capture in enumerate(args.captures, 1):
        source_path = args.image_dir / f"{capture}.jpg"
        image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
        if image is None:
            records.append({"capture": capture, "status": "BLOCKED_SOURCE_NOT_FOUND"})
            continue
        decision = preparer.prepare(
            FrameSample(FrameId(capture), float(index), image),
            SpreadId(f"p030-spread-{index:02d}"),
            ProcessingJobId(f"p030-job-{index:02d}"),
            "p030-v2-regression",
        )
        record: dict[str, object] = {
            "capture": capture,
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
                    "manifest_path": str(manifest_path),
                    "left_bbox_full": manifest["pages"]["left"]["bbox_full"],
                    "right_bbox_full": manifest["pages"]["right"]["bbox_full"],
                    "left_uvdoc_sha256": artifact.left.sha256,
                    "right_uvdoc_sha256": artifact.right.sha256,
                    "uvdoc_load_count": manifest["uvdoc_runtime"]["load_count"],
                    "bundle_size_bytes": sum(
                        path.stat().st_size for path in manifest_path.parent.rglob("*") if path.is_file()
                    ),
                }
            )
            if args.reference_image_dir:
                reference_path = (
                    args.reference_image_dir
                    / f"{capture}_left_seam_conservative_uvdoc_bilinear_none.png"
                )
                record["left_uvdoc_reference"] = _compare_images(
                    manifest_path.parent / "left" / "uvdoc.jpg", reference_path
                )
        records.append(record)

    status = "COMPLETE" if records and all(item.get("state") == "prepared" for item in records) else "INCOMPLETE"
    summary = {
        "schema_version": 1,
        "status": status,
        "sampling_mode": "bilinear",
        "capture_count": len(records),
        "final_uvdoc_load_count": getattr(preparer.unwarper, "load_count", None),
        "records": records,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if status == "COMPLETE" else 1


def _compare_images(candidate_path: Path, reference_path: Path) -> dict[str, object]:
    candidate = cv2.imread(str(candidate_path), cv2.IMREAD_COLOR)
    reference = cv2.imread(str(reference_path), cv2.IMREAD_COLOR)
    if candidate is None or reference is None:
        return {"status": "BLOCKED_REFERENCE_NOT_FOUND", "reference_path": str(reference_path)}
    if candidate.shape != reference.shape:
        return {
            "status": "FAILED_SIZE_MISMATCH",
            "candidate_shape": list(candidate.shape),
            "reference_shape": list(reference.shape),
        }
    difference = candidate.astype(np.float32) - reference.astype(np.float32)
    mse = float(np.mean(difference * difference))
    return {
        "status": "COMPARED",
        "shape": list(candidate.shape),
        "mean_absolute_error": float(np.mean(np.abs(difference))),
        "max_absolute_error": int(np.max(np.abs(difference))),
        "psnr_db": float("inf") if mse == 0 else float(10.0 * np.log10(255.0**2 / mse)),
        "reference_path": str(reference_path.resolve()),
    }


if __name__ == "__main__":
    sys.exit(main())
