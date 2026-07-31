from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.serialization.visual_regions import apply_intro_page_exclusions_to_document
from document_parser.support_review import approved_exclusion_types_from_config
from document_parser.validation import validate_document_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply conservative unsupported-page postprocessing to a Page IR JSON file.")
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "debug" / "easyocr_text_page_ir_samples.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "debug" / "easyocr_visual_page_ir_samples.json")
    parser.add_argument(
        "--approval-config",
        type=Path,
        default=ROOT / "data" / "config" / "support_exclusion_approvals.json",
        help="JSON file containing approved_exclusion_types. Without approval, candidates are not excluded.",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    approval_config = json.loads(args.approval_config.read_text(encoding="utf-8")) if args.approval_config.exists() else {}
    approved_exclusion_types = approved_exclusion_types_from_config(approval_config)
    processed = apply_intro_page_exclusions_to_document(payload, approved_exclusion_types=approved_exclusion_types)
    processed["validation_summary"] = validate_document_ir(processed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(processed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    visual_node_count = sum(
        1
        for page in processed.get("pages", [])
        if isinstance(page, dict)
        for node in page.get("nodes", [])
        if isinstance(node, dict) and node.get("content_type") == "UNSUPPORTED_VISUAL"
    )
    print(f"Wrote {args.output.resolve()}")
    print(f"Pages: {len(processed.get('pages', []))}")
    print(f"Unsupported visual nodes: {visual_node_count}")
    print(f"Approved exclusion types: {', '.join(sorted(approved_exclusion_types)) or '(none)'}")
    print(f"Schema valid: {processed['validation_summary']['schema_valid']}")
    return 0 if processed["validation_summary"]["schema_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
