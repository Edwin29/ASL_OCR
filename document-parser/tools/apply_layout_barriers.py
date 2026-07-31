from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.structure import DEFAULT_BARRIER_LABELS, apply_layout_barriers_to_document
from document_parser.validation import validate_document_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Annotate structure regions as layout barriers in Page IR.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--barrier-label", action="append", help="Structure label to treat as a layout barrier.")
    parser.add_argument("--containment-threshold", type=float, default=0.55)
    parser.add_argument("--page-id", action="append", help="Limit barrier annotation to one or more page IDs.")
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if args.page_id:
        payload = filter_payload_pages(payload, set(args.page_id))
    labels = set(args.barrier_label) if args.barrier_label else set(DEFAULT_BARRIER_LABELS)
    processed = apply_layout_barriers_to_document(
        payload,
        barrier_labels=labels,
        containment_threshold=args.containment_threshold,
    )
    processed["validation_summary"] = validate_document_ir(processed)
    summary = layout_barrier_summary(processed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(processed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output.resolve()}")
    print(f"Summary: {args.summary.resolve()}")
    print(f"Barrier regions: {summary['barrier_count']}")
    print(f"Assigned text nodes: {summary['assigned_text_node_count']}")
    print(f"Crossing warnings: {summary['crossing_warning_count']}")
    print(f"Schema valid: {processed['validation_summary']['schema_valid']}")
    return 0 if processed["validation_summary"]["schema_valid"] else 1


def layout_barrier_summary(payload: dict[str, object]) -> dict[str, object]:
    page_summaries = []
    barrier_count = 0
    assigned_text_node_count = 0
    crossing_warning_count = 0
    for page in payload.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_barriers = []
        page_assigned = 0
        for node in page.get("nodes", []):
            if not isinstance(node, dict):
                continue
            layout = node.get("layout")
            if not isinstance(layout, dict):
                continue
            if layout.get("is_layout_barrier") is True:
                page_barriers.append({
                    "node_id": node.get("node_id"),
                    "structure_label": layout.get("structure_label"),
                    "layout_barrier_role": layout.get("layout_barrier_role"),
                    "assigned_text_node_count": layout.get("layout_barrier_text_node_count", 0),
                })
            if isinstance(layout.get("primary_layout_barrier_node_id"), str):
                page_assigned += 1
        page_crossings = [
            issue
            for issue in page.get("parse_issues", [])
            if isinstance(issue, dict) and issue.get("code") == "LAYOUT_BARRIER_CROSSING_TEXT_CANDIDATE"
        ]
        barrier_count += len(page_barriers)
        assigned_text_node_count += page_assigned
        crossing_warning_count += len(page_crossings)
        page_summaries.append({
            "page_id": page.get("page_id"),
            "barrier_count": len(page_barriers),
            "assigned_text_node_count": page_assigned,
            "crossing_warning_count": len(page_crossings),
            "barriers": page_barriers,
        })
    return {
        "barrier_count": barrier_count,
        "assigned_text_node_count": assigned_text_node_count,
        "crossing_warning_count": crossing_warning_count,
        "pages": page_summaries,
    }


def filter_payload_pages(payload: dict[str, object], page_ids: set[str]) -> dict[str, object]:
    result = dict(payload)
    pages = payload.get("pages")
    if not isinstance(pages, list):
        return result
    filtered = [
        page
        for page in pages
        if isinstance(page, dict) and isinstance(page.get("page_id"), str) and page["page_id"] in page_ids
    ]
    result["pages"] = filtered
    manifest = result.get("document_manifest")
    if isinstance(manifest, dict):
        manifest = dict(manifest)
        manifest["page_count"] = len(filtered)
        result["document_manifest"] = manifest
    return result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
