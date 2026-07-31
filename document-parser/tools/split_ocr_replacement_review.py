from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.structure import build_split_ocr_replacement_review_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a before/after review report for split OCR replacement drafts.")
    parser.add_argument("--page-ir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    payload = json.loads(args.page_ir.read_text(encoding="utf-8"))
    report = build_split_ocr_replacement_review_report(payload)
    report["page_ir"] = str(args.page_ir.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output.resolve()}")
    print(f"Replacement sources: {report['replacement_source_count']}")
    print(f"Replacement segments: {report['replacement_segment_count']}")
    print(f"Unresolved candidates: {report['unresolved_candidate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
