from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.structure import (
    PROMOTABLE_STRUCTURE_LABELS,
    promote_structure_candidates_to_primary_order_for_document,
)
from document_parser.validation import validate_document_ir

PROMOTION_PROFILES = {
    "safe": PROMOTABLE_STRUCTURE_LABELS,
    "problem-box-preview": {"PROBLEM_BOX_CANDIDATE"},
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote reviewed structure candidates into primary Page IR reading order.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--profile",
        choices=sorted(PROMOTION_PROFILES),
        default="safe",
        help="Promotion label preset. 'safe' promotes table/graph candidates; 'problem-box-preview' promotes problem boxes only.",
    )
    parser.add_argument(
        "--promote-label",
        action="append",
        help="Structure label to promote. Overrides --profile when supplied.",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    labels = selected_labels(args.profile, args.promote_label)
    order_mode = "geometry" if args.profile == "problem-box-preview" else "first-contained"
    processed = promote_structure_candidates_to_primary_order_for_document(
        payload,
        promotable_labels=labels,
        order_mode=order_mode,
    )
    caption_link_count = count_caption_links(processed)
    manifest = processed.setdefault("engine_manifest", {})
    if isinstance(manifest, dict):
        structure_promotion = {
            "profile": args.profile,
            "promote_labels": sorted(labels),
            "mode": "preview" if args.profile == "problem-box-preview" else "safe",
            "order_mode": order_mode,
        }
        if args.profile == "problem-box-preview":
            structure_promotion["caption_link_mode"] = "nearest_above_overlap"
            structure_promotion["caption_link_count"] = caption_link_count
        manifest["structure_promotion"] = structure_promotion
    processed["validation_summary"] = validate_document_ir(processed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(processed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    promoted_count = sum(
        1
        for page in processed.get("pages", [])
        if isinstance(page, dict)
        for node in page.get("nodes", [])
        if isinstance(node, dict)
        and isinstance(node.get("layout"), dict)
        and node["layout"].get("is_promoted_structure_region") is True
    )
    embedded_count = sum(
        len(node.get("embedded_text_nodes", []))
        for page in processed.get("pages", [])
        if isinstance(page, dict)
        for node in page.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("embedded_text_nodes"), list)
    )
    print(f"Wrote {args.output.resolve()}")
    print(f"Profile: {args.profile}")
    print(f"Order mode: {order_mode}")
    print(f"Promote labels: {', '.join(sorted(labels))}")
    print(f"Promoted structure nodes: {promoted_count}")
    print(f"Embedded text refs: {embedded_count}")
    print(f"Caption links: {caption_link_count}")
    print(f"Schema valid: {processed['validation_summary']['schema_valid']}")
    return 0 if processed["validation_summary"]["schema_valid"] else 1


def selected_labels(profile: str, promote_labels: list[str] | None) -> set[str]:
    if promote_labels:
        return set(promote_labels)
    return set(PROMOTION_PROFILES[profile])


def count_caption_links(payload: dict[str, object]) -> int:
    return sum(
        len(layout.get("caption_structure_node_ids", []))
        for page in payload.get("pages", [])
        if isinstance(page, dict)
        for node in page.get("nodes", [])
        if isinstance(node, dict)
        for layout in [node.get("layout")]
        if isinstance(layout, dict) and isinstance(layout.get("caption_structure_node_ids"), list)
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
