from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.evaluation import build_sample_review_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a compact review report for an OCR sample Page IR set.")
    parser.add_argument("--page-ir", type=Path, default=ROOT / "data" / "debug" / "easyocr_text_page_ir_samples.json")
    parser.add_argument("--quality-report", type=Path, default=ROOT / "data" / "debug" / "ocr_quality_report_samples.json")
    parser.add_argument("--validation-summary", type=Path, default=ROOT / "data" / "debug" / "easyocr_page_ir_validation_summary_samples.json")
    parser.add_argument("--overlay-summary", type=Path, default=ROOT / "data" / "debug" / "easyocr_overlay_summary_samples.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "debug" / "sample_ocr_review_report.json")
    args = parser.parse_args(argv)

    page_ir = read_json(args.page_ir)
    quality_report = read_json(args.quality_report)
    validation_summary = read_json(args.validation_summary)
    overlay_summary = read_json(args.overlay_summary) if args.overlay_summary.exists() else None
    report = build_sample_review_report(page_ir, quality_report, validation_summary, overlay_summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.resolve()}")
    print(f"Pages: {report['page_count']}")
    print(f"Nodes: {report['total_node_count']}")
    print(f"Low-confidence nodes: {report['total_low_confidence_node_count']}")
    print(f"Reading-order warnings: {report['total_reading_order_warning_count']}")
    print(f"Region-separation warnings: {report['total_region_separation_warning_count']}")
    return 0


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
