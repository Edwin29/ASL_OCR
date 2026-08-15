from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.evaluation import build_vl_review_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a page-ranked review report from a (optionally cross-validated) PaddleOCR-VL Page IR document."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    document = json.loads(args.input.read_text(encoding="utf-8"))
    report = build_vl_review_report(document)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output.resolve()}")
    print(f"Pages: {report['page_count']}")
    print(f"Total issues: {report['total_issue_count']}")
    print(f"Review priority order: {report['review_priority_order']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
