from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from document_parser.debug import render_document_overlays


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Page IR bbox overlays on top of source page images.")
    parser.add_argument("--page-ir", type=Path, default=Path("document-parser/data/debug/text_only_page_ir.json"))
    parser.add_argument("--images-dir", type=Path, default=Path("document-parser/data/pages_pdf300"))
    parser.add_argument("--output-dir", type=Path, default=Path("document-parser/data/debug/overlays"))
    parser.add_argument("--summary", type=Path, default=Path("document-parser/data/debug/overlay_summary.json"))
    parser.add_argument("--page-id", action="append", help="Optional page ID filter. Can be passed multiple times.")
    args = parser.parse_args(argv)

    payload = json.loads(args.page_ir.read_text(encoding="utf-8"))
    page_ids = set(args.page_id) if args.page_id else None
    results = render_document_overlays(
        payload=payload,
        images_dir=args.images_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        page_ids=page_ids,
    )
    summary = {
        "page_ir": str(args.page_ir.resolve()),
        "images_dir": str(args.images_dir.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "overlay_count": len(results),
        "overlays": [result.to_jsonable() for result in results],
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(results)} overlays to {args.output_dir.resolve()}")
    print(f"Summary: {args.summary.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
