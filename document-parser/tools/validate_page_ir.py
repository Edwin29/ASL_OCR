from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from document_parser.validation import validate_document_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Page IR invariants and print a summary.")
    parser.add_argument("input", type=Path, help="Path to a Page IR JSON file.")
    parser.add_argument("--write-summary", type=Path, help="Optional path for the validation summary JSON.")
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    summary = validate_document_ir(payload)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.write_summary is not None:
        args.write_summary.parent.mkdir(parents=True, exist_ok=True)
        args.write_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return 0 if summary["schema_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
