from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.evaluation import build_ocr_quality_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build OCR and reading-order diagnostics from a Page IR JSON file.")
    parser.add_argument("--page-ir", type=Path, default=ROOT / "data" / "debug" / "easyocr_text_page_ir_p008.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "debug" / "ocr_quality_report_p008.json")
    parser.add_argument("--low-confidence-threshold", type=float, default=0.5)
    parser.add_argument("--wide-node-ratio", type=float, default=0.72)
    parser.add_argument("--tall-node-ratio", type=float, default=0.08)
    parser.add_argument("--overlap-threshold", type=float, default=0.35)
    args = parser.parse_args(argv)

    payload = json.loads(args.page_ir.read_text(encoding="utf-8"))
    report = build_ocr_quality_report(
        payload,
        low_confidence_threshold=args.low_confidence_threshold,
        wide_node_ratio=args.wide_node_ratio,
        tall_node_ratio=args.tall_node_ratio,
        overlap_threshold=args.overlap_threshold,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output.resolve()}")
    print(f"Pages: {report['page_count']}")
    print(f"Nodes: {report['total_node_count']}")
    print(f"Low-confidence nodes: {report['total_low_confidence_node_count']}")
    print(f"Reading-order warnings: {report['total_reading_order_warning_count']}")
    print(f"Region-separation warnings: {report['total_region_separation_warning_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
