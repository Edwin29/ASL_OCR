from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.ocr.baseline import DEFAULT_MODEL_HOME
from document_parser.pipeline import run_math_recognition_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the full, correctly-ordered math recognition pipeline: OCR -> structure "
            "detection -> promotion -> math candidates -> spans -> crops -> formula OCR."
        )
    )
    parser.add_argument("--images-dir", type=Path, default=ROOT / "data" / "pages_pdf300")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--page-id", action="append", help="Optional page ID filter. Can be passed multiple times.")
    parser.add_argument("--model-home", type=Path, default=DEFAULT_MODEL_HOME)
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--enable-mkldnn", action="store_true")
    parser.add_argument("--layout-threshold", type=float, default=0.35)
    parser.add_argument("--crop-padding", type=int, default=8)
    args = parser.parse_args(argv)

    summary = run_math_recognition_pipeline(
        images_dir=args.images_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        page_ids=set(args.page_id) if args.page_id else None,
        model_home=args.model_home.resolve(),
        cpu_threads=args.cpu_threads,
        enable_mkldnn=args.enable_mkldnn,
        layout_threshold=args.layout_threshold,
        crop_padding=args.crop_padding,
    )

    print(f"Output dir: {args.output_dir.resolve()}")
    print(f"Pages: {summary['page_count']}")
    print(f"Schema valid: {summary['schema_valid']}")
    print(f"Math candidates: {summary['math_candidate_count']}")
    print(f"Math span split nodes: {summary['math_span_split_node_count']} "
          f"(span candidates: {summary['math_span_candidate_count']})")
    print(f"Formula-region fallback crops (unsplit lines): {summary['formula_region_crop_count']} "
          f"(trusted: {summary['formula_region_trusted_count']}, "
          f"untrusted: {summary['formula_region_untrusted_count']})")
    print(f"Standard crops: {summary['crop_count']} "
          f"(trusted: {summary['formula_ocr_trusted_count']}, "
          f"untrusted: {summary['formula_ocr_untrusted_count']})")
    print(f"Total: {summary['total_trusted_count']} trusted, {summary['total_untrusted_count']} untrusted")
    return 0 if summary["schema_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
