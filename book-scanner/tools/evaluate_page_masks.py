"""Generate raw masks, overlays, crops, diagnostics, and optional metrics.

Examples:
  python tools/evaluate_page_masks.py images/ --output-dir mask_eval
  python tools/evaluate_page_masks.py captures/ --background empty.jpg \
      --segmenter legacy-background --output-dir legacy_eval
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from book_scanner.detect.background import register_background
from book_scanner.detect.contrast_spatial import ContrastSpatialPageSegmenter
from book_scanner.detect.roi import ROIConfig, PageSide, extract_page_rois
from book_scanner.detect.segmenter import BrightnessPageSegmenter, LegacyBackgroundSegmenter
from book_scanner.evaluation.labelme_truth import load_labelme_truth_for_rois
from book_scanner.evaluation.page_masks import evaluate_frame, read_image, write_image


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def _inputs(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES)
    raise ValueError(f"input does not exist: {path}")


def _parse_polygon(value: str | None):
    if value is None:
        return None
    points = json.loads(value)
    return tuple((float(point[0]), float(point[1])) for point in points)


def _contact_sheet(item_dir: Path) -> None:
    names = ("raw.png", "left_overlay.png", "left_comparison.png", "left_crop.png", "right_overlay.png", "right_comparison.png", "right_crop.png")
    images = []
    for name in names:
        path = item_dir / name
        if not path.exists():
            continue
        image = read_image(path)
        scale = min(1.0, 480 / image.shape[1], 360 / image.shape[0])
        images.append(cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA))
    if not images:
        return
    cell_h, cell_w = max(image.shape[0] for image in images), max(image.shape[1] for image in images)
    sheet = np.full((cell_h * 2, cell_w * 4, 3), 245, dtype=np.uint8)
    for index, image in enumerate(images):
        y, x = (index // 4) * cell_h, (index % 4) * cell_w
        sheet[y : y + image.shape[0], x : x + image.shape[1]] = image
    write_image(item_dir / "contact_sheet.jpg", sheet)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="image or a non-recursive image directory")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--segmenter",
        choices=("brightness", "legacy-background", "contrast-spatial"),
        default="brightness",
    )
    parser.add_argument("--background", type=Path, help="empty frame required by legacy-background")
    parser.add_argument("--centerline-fraction", type=float, default=0.5)
    parser.add_argument("--spine-overlap-fraction", type=float, default=0.0)
    parser.add_argument("--left-polygon", help='normalized JSON points, e.g. "[[0,0],[.5,0],[.5,1],[0,1]]"')
    parser.add_argument("--right-polygon", help="normalized JSON points")
    parser.add_argument("--ground-truth-dir", type=Path, help="optional <stem>_<side>.png masks")
    parser.add_argument("--labelme-dir", type=Path, help="optional LabelMe <stem>.json ground truth")
    parser.add_argument("--neutralize-outside", action="store_true")
    args = parser.parse_args()

    roi_config = ROIConfig(
        centerline_fraction=args.centerline_fraction,
        spine_overlap_fraction=args.spine_overlap_fraction,
        left_polygon=_parse_polygon(args.left_polygon),
        right_polygon=_parse_polygon(args.right_polygon),
    )
    if args.segmenter == "legacy-background":
        if args.background is None:
            parser.error("--background is required with --segmenter legacy-background")
        try:
            background_frame = read_image(args.background)
        except ValueError:
            parser.error(f"could not read background image: {args.background}")
        background_rois = extract_page_rois(background_frame, roi_config)
        segmenter = LegacyBackgroundSegmenter(
            {side: register_background(roi.image) for side, roi in background_rois.items()}
        )
    elif args.segmenter == "brightness":
        segmenter = BrightnessPageSegmenter()
    else:
        segmenter = ContrastSpatialPageSegmenter()

    inputs = _inputs(args.input)
    if not inputs:
        parser.error(f"no supported images found in {args.input}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for image_path in inputs:
        frame = read_image(image_path)
        rois = extract_page_rois(frame, roi_config)
        truth_paths = None
        truth_masks = None
        truth_diagnostics = None
        if args.ground_truth_dir is not None:
            truth_paths = {
                side: args.ground_truth_dir / f"{image_path.stem}_{side.value}.png" for side in PageSide
            }
        if args.labelme_dir is not None:
            label_path = args.labelme_dir / f"{image_path.stem}.json"
            if label_path.exists():
                try:
                    truth_masks, truth_diagnostics = load_labelme_truth_for_rois(image_path, label_path, rois)
                except ValueError as exc:
                    truth_diagnostics = {"status": "excluded_invalid_label", "reason": str(exc), "label_path": str(label_path)}
            else:
                truth_diagnostics = {"status": "excluded_missing_label", "reason": "LabelMe JSON not found", "label_path": str(label_path)}
        item_dir = args.output_dir / image_path.stem
        results = evaluate_frame(
            frame,
            item_dir,
            segmenter,
            roi_config=roi_config,
            truth_paths=truth_paths,
            truth_masks=truth_masks,
            neutralize_outside=args.neutralize_outside,
        )
        _contact_sheet(item_dir)
        predicted_full = {}
        for side, roi in rois.items():
            local = read_image(item_dir / f"{side.value}_mask.png", cv2.IMREAD_GRAYSCALE)
            full = np.zeros(frame.shape[:2], dtype=np.uint8)
            ox, oy = roi.origin
            roi_width, roi_height = roi.size
            full[oy : oy + roi_height, ox : ox + roi_width] = local
            predicted_full[side] = full
        prediction_overlap_px = int(np.count_nonzero(
            (predicted_full[PageSide.LEFT] > 0) & (predicted_full[PageSide.RIGHT] > 0)
        ))
        summary.append({
            "input": str(image_path),
            "truth_diagnostics": truth_diagnostics,
            "prediction_overlap_px": prediction_overlap_px,
            "results": [result.__dict__ for result in results],
        })
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=lambda value: value.__dict__), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
