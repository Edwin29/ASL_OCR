from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.evaluation import build_ocr_comparison_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare OCR quality diagnostics between two Page IR JSON files.")
    parser.add_argument("--baseline-page-ir", type=Path, required=True)
    parser.add_argument("--candidate-page-ir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "debug" / "ocr_comparison_report.json")
    parser.add_argument("--low-confidence-threshold", type=float, default=0.5)
    args = parser.parse_args(argv)

    baseline_payload = json.loads(args.baseline_page_ir.read_text(encoding="utf-8"))
    candidate_payload = json.loads(args.candidate_page_ir.read_text(encoding="utf-8"))
    report = build_ocr_comparison_report(
        baseline_payload,
        candidate_payload,
        low_confidence_threshold=args.low_confidence_threshold,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.resolve()}")
    print(f"Baseline: {report['baseline_engine']['engine_id']}")
    print(f"Candidate: {report['candidate_engine']['engine_id']}")
    print(f"Pages: {report['page_count']}")
    print(f"Baseline diagnostic score: {report['baseline_totals']['diagnostic_score']}")
    print(f"Candidate diagnostic score: {report['candidate_totals']['diagnostic_score']}")
    print(f"Verdicts: {report['verdict_counts']}")
    print(f"Recommendation: {report['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
