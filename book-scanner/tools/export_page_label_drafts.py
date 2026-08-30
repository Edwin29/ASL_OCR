from __future__ import annotations

import argparse
from pathlib import Path

from book_scanner.detect.contrast_spatial import ContrastSpatialPageSegmenter
from book_scanner.evaluation.label_drafts import export_labelme_draft


def main() -> int:
    parser = argparse.ArgumentParser(description="Export human-review-only LabelMe page polygon drafts")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    images = [args.input] if args.input.is_file() else sorted(args.input.glob("*.jpg"))
    for image_path in images:
        target = args.output_dir / f"{image_path.stem}.json"
        try:
            export_labelme_draft(image_path, target, ContrastSpatialPageSegmenter(), overwrite=args.overwrite)
        except FileExistsError as exc:
            print(f"SKIP: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
