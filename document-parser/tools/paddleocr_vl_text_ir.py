from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.ocr.paddleocr_vl_adapter import PaddleOcrVlAdapter
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Page IR using PaddleOCR-VL (project baseline).")
    parser.add_argument("--images-dir", type=Path, default=ROOT / "data" / "pages_pdf300")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "debug" / "paddleocr_vl_page_ir.json")
    parser.add_argument("--model-home", type=Path, default=ROOT / "data" / "debug" / "model_home_vl")
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--book-id", default="ebs-2027-math1")
    parser.add_argument("--page-id", action="append", help="Optional page ID filter. Can be passed multiple times.")
    args = parser.parse_args(argv)

    image_paths = sorted(args.images_dir.resolve().glob("*.png"))
    if args.page_id:
        wanted = set(args.page_id)
        image_paths = [p for p in image_paths if any(f"_{pid}" in p.stem for pid in wanted)]

    adapter = PaddleOcrVlAdapter(model_home=args.model_home.resolve(), device=args.device)
    payload = build_document_ir_from_vl(image_paths, adapter=adapter, book_id=args.book_id)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output.resolve()}")
    print(f"Pages: {len(payload['pages'])}")
    print(f"Nodes: {sum(len(p['nodes']) for p in payload['pages'])}")
    print(f"Schema valid: {payload['validation_summary']['schema_valid']}")
    return 0 if payload["validation_summary"]["schema_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
