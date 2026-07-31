from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.structure import apply_split_ocr_reconciliation_to_document
from document_parser.validation import validate_document_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Attach split OCR reconciliation preview metadata to crossing TEXT nodes.")
    parser.add_argument("--page-ir", type=Path, required=True)
    parser.add_argument("--split-ocr-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--min-token-confidence", type=float, default=0.5)
    args = parser.parse_args(argv)

    page_ir = json.loads(args.page_ir.read_text(encoding="utf-8"))
    split_ocr_manifest = json.loads(args.split_ocr_manifest.read_text(encoding="utf-8"))
    processed, summary = apply_split_ocr_reconciliation_to_document(
        page_ir,
        split_ocr_manifest,
        min_token_confidence=args.min_token_confidence,
    )
    processed["validation_summary"] = validate_document_ir(processed)
    summary["schema_valid"] = processed["validation_summary"]["schema_valid"]
    summary["page_ir"] = str(args.page_ir.resolve())
    summary["split_ocr_manifest"] = str(args.split_ocr_manifest.resolve())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(processed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output.resolve()}")
    print(f"Summary: {args.summary.resolve()}")
    print(f"Candidates: {summary['candidate_count']}")
    print(f"Segments: {summary['segment_count']}")
    print(f"Statuses: {summary['statuses']}")
    print(f"Schema valid: {summary['schema_valid']}")
    return 0 if summary["schema_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
