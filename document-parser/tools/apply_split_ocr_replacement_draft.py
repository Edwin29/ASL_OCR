from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.structure import apply_split_ocr_replacement_draft_to_document
from document_parser.validation import validate_document_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create draft TEXT segment replacements from split OCR reconciliation previews.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--accepted-status", action="append", default=["REVIEW_REPLACE_CANDIDATE"])
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    processed, summary = apply_split_ocr_replacement_draft_to_document(
        payload,
        accepted_statuses=set(args.accepted_status),
    )
    processed["validation_summary"] = validate_document_ir(processed)
    summary["schema_valid"] = processed["validation_summary"]["schema_valid"]
    summary["input"] = str(args.input.resolve())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(processed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output.resolve()}")
    print(f"Summary: {args.summary.resolve()}")
    print(f"Source candidates: {summary['source_candidate_count']}")
    print(f"Replacement nodes: {summary['replacement_node_count']}")
    print(f"Skipped candidates: {summary['skipped_candidate_count']}")
    print(f"Schema valid: {summary['schema_valid']}")
    return 0 if summary["schema_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
