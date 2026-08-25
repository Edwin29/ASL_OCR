"""Run document-parser's actual OCR/structure pipeline (PaddleOCR-VL ->
Page IR) on one or more page images, and print a structural summary.

Purpose: compare a photographed-and-perspective-corrected page against
document-parser's existing reference render for the same page_id, to check
whether the pipeline produces "the same pattern" of output (node kinds,
counts, problem-unit structure) -- not pixel-identical, but structurally
equivalent. Deliberately skips Piper/TTS synthesis: that's a downstream
concern, not what this comparison is about.

Usage:
    python tools/run_page_ir.py p030 path/to/photo_corrected.png --out result.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# document_parser is not installed as a package in the dedicated GPU OCR venv
# (see document-parser/docs/gpu-inference-setup.md) -- add its src/ directly,
# matching that doc's own tool pattern.
_DOCUMENT_PARSER_SRC = Path(__file__).resolve().parents[2] / "document-parser" / "src"
if str(_DOCUMENT_PARSER_SRC) not in sys.path:
    sys.path.insert(0, str(_DOCUMENT_PARSER_SRC))

from document_parser.ocr.paddleocr_vl_adapter import PaddleOcrVlAdapter
from document_parser.serialization import build_document_ir_from_vl


def summarize(payload: dict) -> dict:
    kind_counts: dict[str, int] = {}
    problem_unit_count = 0
    item_count = 0
    for page in payload.get("pages", []):
        for item in page.get("focus_items", []):
            item_count += 1
            kind = item.get("kind", "UNKNOWN")
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            if kind == "PROBLEM_UNIT":
                problem_unit_count += 1
    return {
        "page_count": len(payload.get("pages", [])),
        "focus_item_count": item_count,
        "kind_counts": kind_counts,
        "problem_unit_count": problem_unit_count,
        "validation_summary": payload.get("validation_summary", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book_id")
    parser.add_argument("images", nargs="+", help="page image paths")
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument(
        "--model-home",
        default=None,
        help="ASCII-only cache dir for PaddleX model files -- required on Windows when the user "
        "profile path contains non-ASCII characters (paddle_inference's file-open call cannot "
        "read files under such a path even though they exist; same class of bug documented for "
        "Piper TTS's espeak-ng-data path in this project's memory).",
    )
    parser.add_argument("--out", default=None, help="path to write the full Page IR JSON")
    args = parser.parse_args()

    image_paths = [Path(p) for p in args.images]
    model_home = Path(args.model_home) if args.model_home else None
    adapter = PaddleOcrVlAdapter(model_home=model_home, device=args.device)

    print(f"running OCR on {len(image_paths)} image(s), device={args.device} ...")
    payload = build_document_ir_from_vl(image_paths, adapter, args.book_id)
    print("OCR complete")

    summary = summarize(payload)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote full Page IR to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
