from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.math import create_baseline_formula_ocr_adapter
from document_parser.ocr.baseline import create_baseline_ocr_adapter
from document_parser.reconciliation import cross_validate_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-validate low-confidence PaddleOCR-VL Page IR nodes (AST parse "
            "issues, possible choice omissions) against the legacy PaddleOCR engines."
        )
    )
    parser.add_argument("--input", type=Path, required=True, help="Page IR JSON built from PaddleOCR-VL.")
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-home", type=Path, default=ROOT / "data" / "debug" / "model_home")
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--enable-mkldnn", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    formula_adapter = create_baseline_formula_ocr_adapter(
        model_home=args.model_home.resolve(), cpu_threads=args.cpu_threads, enable_mkldnn=args.enable_mkldnn
    )
    ocr_adapter = create_baseline_ocr_adapter(
        model_home=args.model_home.resolve(), cpu_threads=args.cpu_threads, enable_mkldnn=args.enable_mkldnn
    )

    result = cross_validate_document(
        payload, images_dir=args.images_dir.resolve(), formula_adapter=formula_adapter, ocr_adapter=ocr_adapter
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    total_math = sum(
        1
        for page in result["pages"]
        for node in page["nodes"]
        if node.get("content_type") == "MATH" and "alternative_candidates" in node
    )
    total_choice = sum(
        1
        for page in result["pages"]
        for node in page["nodes"]
        if any(i.get("code", "").startswith("CROSS_VALIDATION_") and i.get("code") != "CROSS_VALIDATION_RECORDED" for i in node.get("issues", []))
    )
    print(f"Wrote {args.output.resolve()}")
    print(f"MATH nodes cross-validated: {total_math}")
    print(f"TEXT nodes cross-validated for choice omission: {total_choice}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
