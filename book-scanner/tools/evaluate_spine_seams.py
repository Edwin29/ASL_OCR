from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from book_scanner.annotations.labelme import load_labelme_pages
from book_scanner.detect.contrast_spatial import ContrastSpatialPageSegmenter
from book_scanner.detect.roi import ROIConfig, PageSide
from book_scanner.detect.spine_seam import (
    FixedCenterlineSeamDetector,
    LuminanceValleySeamDetector,
    MaskAwareSpineSeamDetector,
    SpineSeamConfig,
)
from book_scanner.evaluation.page_masks import read_image, write_image
from book_scanner.evaluation.fallback_assessment import assess_fixed_layout_fallback
from book_scanner.evaluation.seam_experiment import SeamMethodSpec, run_seam_experiment, serialize_evaluations


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def _inputs(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(item for item in path.iterdir() if item.suffix.lower() in IMAGE_SUFFIXES)
    raise ValueError(f"input does not exist: {path}")


def _specs(include_grid: bool) -> list[SeamMethodSpec]:
    specs: list[SeamMethodSpec] = []
    selected = SpineSeamConfig(centerline_fraction=0.5, uncertainty_band_px=8)
    for policy in ("hard", "union-preserving", "uncertainty-band"):
        specs.append(SeamMethodSpec("fixed-f0.500-b8", FixedCenterlineSeamDetector(selected), policy, policy != "hard"))
    for detector_type, key in (
        (LuminanceValleySeamDetector, "luminance-valley"),
        (MaskAwareSpineSeamDetector, "mask-aware"),
    ):
        for policy in ("union-preserving", "uncertainty-band"):
            specs.append(SeamMethodSpec(key, detector_type(selected), policy, True))
    if include_grid:
        for fraction in (0.49, 0.50, 0.51, 0.52):
            for band in (0, 4, 8, 16):
                config = SpineSeamConfig(centerline_fraction=fraction, uncertainty_band_px=band)
                for policy in ("hard", "union-preserving", "uncertainty-band"):
                    key = f"grid-fixed-f{fraction:.3f}-b{band}"
                    specs.append(SeamMethodSpec(key, FixedCenterlineSeamDetector(config), policy, False))
    return specs


def _contact_sheet(item_dir: Path, frame: np.ndarray) -> None:
    preferred = [
        "fixed-f0.500-b8_union-preserving_overlay.png",
        "luminance-valley_union-preserving_overlay.png",
        "mask-aware_union-preserving_overlay.png",
        "mask-aware_uncertainty-band_overlay.png",
    ]
    images = [frame]
    for name in preferred:
        path = item_dir / name
        if path.exists():
            images.append(read_image(path))
    cell_w, cell_h = 600, 450
    sheet = np.full((cell_h * 2, cell_w * 3, 3), 245, dtype=np.uint8)
    for index, image in enumerate(images[:6]):
        scale = min(cell_w / image.shape[1], cell_h / image.shape[0])
        resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        y, x = (index // 3) * cell_h, (index % 3) * cell_w
        sheet[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    write_image(item_dir / "contact_sheet.jpg", sheet)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate fixed and adaptive spine seam ownership")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--labelme-dir", type=Path)
    parser.add_argument("--include-fixed-grid", action="store_true")
    parser.add_argument("--spine-overlap-fraction", type=float, default=0.06)
    parser.add_argument("--stems", nargs="*", help="optional image stems to include")
    args = parser.parse_args()
    summary = []
    inputs = _inputs(args.input)
    if args.stems:
        requested = set(args.stems)
        inputs = [path for path in inputs if path.stem in requested]
    if not inputs:
        parser.error("no matching input images")
    for image_path in inputs:
        frame = read_image(image_path)
        truth = None
        truth_diagnostics: dict[str, object] | None = None
        if args.labelme_dir is not None:
            label_path = args.labelme_dir / f"{image_path.stem}.json"
            if label_path.exists():
                try:
                    labels = load_labelme_pages(image_path, label_path)
                    truth = {side: annotation.mask for side, annotation in labels.pages.items()}
                    truth_diagnostics = {"status": "loaded", "label_path": str(label_path), **labels.diagnostics}
                except ValueError as exc:
                    truth_diagnostics = {"status": "excluded_invalid_label", "reason": str(exc)}
            else:
                truth_diagnostics = {"status": "excluded_missing_label", "reason": "LabelMe JSON not found"}
        evaluations, artifacts, extraction = run_seam_experiment(
            frame,
            ContrastSpatialPageSegmenter(),
            _specs(args.include_fixed_grid),
            truth_masks=truth,
            roi_config=ROIConfig(spine_overlap_fraction=args.spine_overlap_fraction),
        )
        fallback_masks = {
            side: artifacts.get(
                f"{side.value}_page_mask_full",
                np.zeros(frame.shape[:2], dtype=np.uint8),
            )
            for side in PageSide
        }
        fallback = assess_fixed_layout_fallback(frame, fallback_masks)
        item_dir = args.output_dir / image_path.stem
        item_dir.mkdir(parents=True, exist_ok=True)
        for name, artifact in artifacts.items():
            write_image(item_dir / f"{name}.png", artifact)
        _contact_sheet(item_dir, frame)
        payload = {
            "input": str(image_path),
            "truth_diagnostics": truth_diagnostics,
            "extraction": extraction,
            "fallback_assessment": asdict(fallback),
            "results": serialize_evaluations(evaluations),
        }
        (item_dir / "diagnostics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        summary.append(payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
