from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.serialization.reading_order import apply_two_column_reading_order_to_document
from document_parser.validation import validate_document_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply reading-order postprocessing to a Page IR JSON file.")
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "debug" / "easyocr_text_page_ir_samples.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "debug" / "easyocr_reading_order_page_ir_samples.json")
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    processed = apply_two_column_reading_order_to_document(payload)
    processed["validation_summary"] = validate_document_ir(processed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(processed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    applied_count = sum(
        1
        for page in processed.get("pages", [])
        if isinstance(page, dict)
        for issue in page.get("parse_issues", [])
        if isinstance(issue, dict) and issue.get("code") == "TWO_COLUMN_READING_ORDER_APPLIED"
    )
    print(f"Wrote {args.output.resolve()}")
    print(f"Pages: {len(processed.get('pages', []))}")
    print(f"Two-column reading-order pages: {applied_count}")
    print(f"Schema valid: {processed['validation_summary']['schema_valid']}")
    return 0 if processed["validation_summary"]["schema_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
