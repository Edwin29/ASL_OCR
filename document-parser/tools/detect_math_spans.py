from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.math import detect_math_spans_in_document, math_span_report
from document_parser.validation import validate_document_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Split mixed Korean/math TEXT node lines into text and math span candidates."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    processed = detect_math_spans_in_document(payload)
    processed["validation_summary"] = validate_document_ir(processed)
    summary = math_span_report(processed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(processed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output.resolve()}")
    print(f"Summary: {args.summary.resolve()}")
    print(f"Nodes split: {summary['total_split_node_count']}")
    print(f"Math span candidates: {summary['total_math_span_count']}")
    print(f"Schema valid: {processed['validation_summary']['schema_valid']}")
    return 0 if processed["validation_summary"]["schema_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
