"""Record frame-edge/content-clipping diagnostics for an image directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import cv2

from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import FrameId


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label-manifest", type=Path)
    args = parser.parse_args()

    image_dir = args.image_dir.resolve()
    output = args.output.resolve()
    if not image_dir.is_dir():
        parser.error(f"image directory does not exist: {image_dir}")
    if output.exists():
        parser.error(f"output already exists: {output}")
    paths = sorted(image_dir.glob("*.jpg")) + sorted(image_dir.glob("*.jpeg"))
    if not paths:
        parser.error(f"no JPEG images found: {image_dir}")
    labels = _read_labels(args.label_manifest)

    analyzer = OpenCVCandidateAnalyzer()
    records: list[dict[str, object]] = []
    reason_counts: Counter[str] = Counter()
    for path in paths:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            records.append({"file": path.name, "status": "DECODE_FAILED"})
            continue
        observation = analyzer.analyze(FrameSample(FrameId(path.stem), 0.0, image))
        candidate = observation.candidate.to_dict()
        reason_counts.update(candidate["retry_reasons"])
        records.append(
            {
                "file": path.name,
                "status": "ANALYZED",
                "ground_truth": labels.get(path.name),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
                "candidate": candidate,
            }
        )

    labeled_records = [record for record in records if record.get("ground_truth") is not None]
    clean_false_rejects = [
        str(record["file"])
        for record in labeled_records
        if record["ground_truth"]["label"] == "CLEAN_TRANSFERABLE"
        and bool(record["candidate"]["retry_reasons"])
    ]
    summary = {
        "schema_version": 1,
        "status": (
            "DIAGNOSTIC_WITH_PARTIAL_GROUND_TRUTH"
            if labels
            else "DIAGNOSTIC_NO_EXACT_CLIPPING_GROUND_TRUTH"
        ),
        "scope": "frame_edge_and_content_clipping_probe",
        "image_dir": str(image_dir),
        "candidate_evaluator_version": analyzer.evaluator_version,
        "record_count": len(records),
        "labeled_record_count": len(labeled_records),
        "clean_false_reject_count": len(clean_false_rejects),
        "clean_false_reject_files": clean_false_rejects,
        "reason_counts": dict(sorted(reason_counts.items())),
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _read_labels(path: Path | None) -> dict[str, dict[str, object]]:
    if path is None:
        return {}
    resolved = path.resolve()
    if not resolved.is_file():
        raise SystemExit(f"label manifest does not exist: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return {str(item["file"]): item for item in payload.get("labels", [])}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
