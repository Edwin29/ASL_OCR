from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.structure import detect_problem_units_in_document, problem_unit_report
from document_parser.validation import validate_document_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect problem units (stem + answer structure) in Page IR from text patterns."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--page-id", action="append", help="Limit detection to one or more page IDs.")
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if args.page_id:
        payload = filter_payload_pages(payload, set(args.page_id))
    processed = detect_problem_units_in_document(payload)
    processed["validation_summary"] = validate_document_ir(processed)
    summary = problem_unit_report(processed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(processed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output.resolve()}")
    print(f"Summary: {args.summary.resolve()}")
    print(f"Problem units detected: {summary['total_problem_count']}")
    print(f"Schema valid: {processed['validation_summary']['schema_valid']}")
    return 0 if processed["validation_summary"]["schema_valid"] else 1


def filter_payload_pages(payload: dict[str, object], page_ids: set[str]) -> dict[str, object]:
    result = dict(payload)
    pages = payload.get("pages")
    if not isinstance(pages, list):
        return result
    filtered = [
        page
        for page in pages
        if isinstance(page, dict) and isinstance(page.get("page_id"), str) and page["page_id"] in page_ids
    ]
    result["pages"] = filtered
    manifest = result.get("document_manifest")
    if isinstance(manifest, dict):
        manifest = dict(manifest)
        manifest["page_count"] = len(filtered)
        result["document_manifest"] = manifest
    return result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
