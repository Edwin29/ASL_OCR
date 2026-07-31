from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.support_review import (
    approved_exclusion_types_from_config,
    build_support_review_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report unsupported-page candidates that require approval before exclusion.")
    parser.add_argument("--page-ir", type=Path, default=ROOT / "data" / "debug" / "easyocr_text_page_ir_samples.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "debug" / "support_review_report_samples.json")
    parser.add_argument(
        "--approval-config",
        type=Path,
        default=ROOT / "data" / "config" / "support_exclusion_approvals.json",
        help="Optional JSON file containing approved_exclusion_types.",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.page_ir.read_text(encoding="utf-8"))
    approval_config = json.loads(args.approval_config.read_text(encoding="utf-8")) if args.approval_config.exists() else {}
    approved_exclusion_types = approved_exclusion_types_from_config(approval_config)
    report = build_support_review_report(payload, approved_exclusion_types=approved_exclusion_types)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.resolve()}")
    print(f"Pages: {report['page_count']}")
    print(f"Candidates: {report['candidate_count']}")
    print(f"Pending approval: {report['pending_approval_count']}")
    print(f"Approved candidates: {report['approved_candidate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
