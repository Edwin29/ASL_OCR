"""Validate a prepared E0-B replay video and write a secret-safe report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from book_scanner.video.sources import VideoFileCameraSource


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    video = args.video.resolve()
    source = VideoFileCameraSource(video, sample_interval_ms=500)
    try:
        source.start()
        sample = source.read()
        if sample is None:
            raise RuntimeError("replay video contains no decodable frame")
        height, width = sample.payload.shape[:2]
    finally:
        source.stop()

    report = {
        "schema_version": 1,
        "kind": "e0b_replay_input",
        "file_name": video.name,
        "size_bytes": video.stat().st_size,
        "sha256": _sha256(video),
        "first_frame": {"width": int(width), "height": int(height)},
        "status": "passed",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
