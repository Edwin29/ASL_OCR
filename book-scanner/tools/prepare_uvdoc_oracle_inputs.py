"""Prepare one UVDoc variant for every manually labelled left/right page."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from book_scanner.annotations.labelme import load_labelme_pages
from book_scanner.correct.uvdoc_adapter import UVDocAdapter, UVDocConfig
from book_scanner.correct.postprocess import LuminanceUnsharpPostprocessor
from book_scanner.detect.roi import PageSide
from book_scanner.evaluation.ocr_ab_experiment import sha256_file
from book_scanner.evaluation.page_masks import read_image, write_image
from book_scanner.evaluation.unwarp_experiment import build_oracle_crops


DEFAULT_STEMS = (
    "20260826_174943",
    "20260826_174953",
    "20260826_174958",
    "20260826_175109",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-images-dir", type=Path, default=Path("TESTIMAGES"))
    parser.add_argument("--capture-stem", action="append", dest="capture_stems")
    parser.add_argument("--uvdoc-runtime", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cpu")
    parser.add_argument("--sampling-mode", choices=("bilinear", "bicubic"), default="bilinear")
    parser.add_argument("--background-policy", choices=("original", "neutralized"), default="original")
    parser.add_argument("--postprocess", choices=("none", "unsharp"), default="none")
    parser.add_argument("--write-crop-control", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--padding-fraction", type=float, default=0.03)
    args = parser.parse_args()

    stems = tuple(args.capture_stems or DEFAULT_STEMS)
    variant = (
        f"uvdoc_unsharp_{args.background_policy}"
        if args.postprocess == "unsharp"
        else f"uvdoc_{args.sampling_mode}_{args.background_policy}"
    )
    postprocessor = LuminanceUnsharpPostprocessor() if args.postprocess == "unsharp" else None
    adapter = UVDocAdapter(UVDocConfig(
        args.uvdoc_runtime.resolve(),
        args.checkpoint.resolve(),
        device=args.device,
        sampling_mode=args.sampling_mode,
    ))
    records = []
    for stem in stems:
        image_path = args.test_images_dir / f"{stem}.jpg"
        label_path = args.test_images_dir / f"{stem}.json"
        if not image_path.is_file() or not label_path.is_file():
            parser.error(f"missing input pair: {image_path}, {label_path}")
        frame = read_image(image_path)
        labels = load_labelme_pages(image_path, label_path)
        for side in (PageSide.LEFT, PageSide.RIGHT):
            crop_name = f"bbox_{args.background_policy}"
            crop = build_oracle_crops(
                frame,
                labels.pages[side],
                padding_fraction=args.padding_fraction,
            )[crop_name]
            if args.write_crop_control:
                crop_path = args.output_dir / stem / side.value / "variants" / "crop_original_control.png"
                write_image(crop_path, crop.image)
                records.append({
                    "capture": stem,
                    "side": side.value,
                    "variant": "crop_original_control",
                    "source_image_sha256": sha256_file(image_path),
                    "label_sha256": sha256_file(label_path),
                    "success": True,
                    "reason": None,
                    "diagnostics": {"bbox_full": list(crop.bbox_full)},
                    "artifact_path": str(crop_path.resolve()),
                    "artifact_sha256": sha256_file(crop_path),
                })
            result = adapter.unwarp_with_mode(crop.image, args.sampling_mode)
            output_image = result.image
            success = result.success
            failure_reason = result.reason.value if result.reason else None
            postprocess_diagnostics: dict[str, object] = {}
            if result.success and output_image is not None and postprocessor is not None:
                processed = postprocessor.apply(output_image)
                if not processed.success or processed.image is None:
                    success = False
                    failure_reason = processed.reason or "postprocess_failed"
                    output_image = None
                else:
                    output_image = processed.image
                    postprocess_diagnostics = {
                        "postprocessor": processed.processor_name,
                        **processed.diagnostics,
                    }
            artifact_path = args.output_dir / stem / side.value / "variants" / f"{variant}.png"
            record = {
                "capture": stem,
                "side": side.value,
                "variant": variant,
                "source_image_sha256": sha256_file(image_path),
                "label_sha256": sha256_file(label_path),
                "success": success,
                "reason": failure_reason,
                "diagnostics": {**result.diagnostics, **postprocess_diagnostics},
                "artifact_path": str(artifact_path.resolve()),
            }
            if success and output_image is not None:
                write_image(artifact_path, output_image)
                record["artifact_sha256"] = sha256_file(artifact_path)
            records.append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)

    summary = {
        "variant": variant,
        "expected_page_count": len(stems) * 2 * (2 if args.write_crop_control else 1),
        "success_count": sum(bool(record["success"]) for record in records),
        "uvdoc_load_count": adapter.load_count,
        "records": records,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / f"prepare_{variant}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if summary["success_count"] == summary["expected_page_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
