from __future__ import annotations

import argparse
import json
from pathlib import Path

from book_scanner.detect.contrast_spatial import ContrastSpatialPageSegmenter
from book_scanner.detect.roi import ROIConfig
from book_scanner.annotations.labelme import load_labelme_pages
from book_scanner.evaluation.extraction_orders import run_extraction_orders, serialize_order_results
from book_scanner.evaluation.page_masks import read_image, write_image


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare approved A/B/C page extraction orders")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--spine-overlap-fraction", type=float, default=0.06)
    parser.add_argument("--labelme-dir", type=Path)
    args = parser.parse_args()
    images = [args.input] if args.input.is_file() else sorted(args.input.glob("*.jpg"))
    summary = []
    for image_path in images:
        frame = read_image(image_path)
        truth = None
        if args.labelme_dir is not None:
            label_path = args.labelme_dir / f"{image_path.stem}.json"
            if label_path.exists():
                truth = load_labelme_pages(image_path, label_path).pages
                truth = {side: annotation.mask for side, annotation in truth.items()}
        results, artifacts = run_extraction_orders(
            frame,
            ContrastSpatialPageSegmenter(),
            ROIConfig(spine_overlap_fraction=args.spine_overlap_fraction),
            truth_full_masks=truth,
        )
        target = args.output_dir / image_path.stem
        for name, image in artifacts.items():
            write_image(target / f"{name}.png", image)
        payload = {"input": str(image_path), "results": serialize_order_results(results)}
        target.mkdir(parents=True, exist_ok=True)
        (target / "diagnostics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        summary.append(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
