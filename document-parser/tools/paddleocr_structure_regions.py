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
    PaddleStructureRegionAdapter,
    apply_structure_regions_to_document,
    map_region_to_ebs_math_domain,
)
from document_parser.structure.paddle_structure_adapter import DEFAULT_LAYOUT_MODEL_DIR
from document_parser.validation import validate_document_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add experimental PaddleOCR PP-StructureV3 region candidates to Page IR.")
    parser.add_argument("--page-ir", type=Path, default=ROOT / "data" / "debug" / "paddleocr_baseline_page_ir_samples.json")
    parser.add_argument("--images-dir", type=Path, default=ROOT / "data" / "pages_pdf300")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "debug" / "paddleocr_structure_page_ir_samples.json")
    parser.add_argument("--raw-output", type=Path, default=ROOT / "data" / "debug" / "paddleocr_structure_regions_samples.json")
    parser.add_argument("--model-home", type=Path, default=ROOT / "data" / "debug" / "model_home")
    parser.add_argument("--layout-model-dir", type=Path, default=DEFAULT_LAYOUT_MODEL_DIR)
    parser.add_argument("--backend", choices=["layout_detection", "pp_structurev3"], default="layout_detection")
    parser.add_argument("--layout-threshold", type=float, default=0.35)
    parser.add_argument("--page-id", action="append", help="Optional page ID filter. Can be passed multiple times.")
    parser.add_argument(
        "--include-label",
        action="append",
        help="Layout labels to add to Page IR. Defaults to table/image/figure/chart/graph labels.",
    )
    parser.add_argument("--include-formula", action="store_true", help="Also add formula/equation candidates.")
    parser.add_argument("--include-text-layout", action="store_true", help="Also add text/title/header/footer layout candidates.")
    parser.add_argument("--use-table-recognition", action="store_true")
    parser.add_argument("--use-formula-recognition", action="store_true")
    parser.add_argument("--use-chart-recognition", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(args.page_ir.read_text(encoding="utf-8"))
    page_ids = set(args.page_id) if args.page_id else {
        str(page.get("page_id"))
        for page in payload.get("pages", [])
        if isinstance(page, dict) and isinstance(page.get("page_id"), str)
    }
    adapter = PaddleStructureRegionAdapter(
        model_home=args.model_home.resolve(),
        layout_detection_model_dir=args.layout_model_dir.resolve() if args.layout_model_dir else None,
        layout_threshold=args.layout_threshold,
        backend=args.backend,
        use_table_recognition=args.use_table_recognition,
        use_formula_recognition=args.use_formula_recognition,
        use_chart_recognition=args.use_chart_recognition,
    )
    regions_by_page_id = {}
    for page_id in sorted(page_ids):
        image_path = image_path_for(args.images_dir.resolve(), page_id)
        if image_path is None:
            regions_by_page_id[page_id] = []
            continue
        regions_by_page_id[page_id] = filter_regions(
            adapter.detect_regions(image_path),
            include_labels=selected_labels(args),
        )

    processed = apply_structure_regions_to_document(payload, regions_by_page_id)
    processed["validation_summary"] = validate_document_ir(processed)
    raw_payload = {
        "engine_id": adapter.engine_id,
        "engine_version": adapter.engine_version,
        "layout_detection_model_name": adapter.layout_detection_model_name,
        "layout_threshold": adapter.layout_threshold,
        "pages": [
            raw_page_summary(payload, page_id, regions)
            for page_id, regions in sorted(regions_by_page_id.items())
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(processed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output.resolve()}")
    print(f"Raw regions: {args.raw_output.resolve()}")
    print(f"Pages: {len(regions_by_page_id)}")
    print(f"Regions: {sum(len(regions) for regions in regions_by_page_id.values())}")
    print(f"Domain labels: {domain_label_counts(raw_payload)}")
    print(f"Schema valid: {processed['validation_summary']['schema_valid']}")
    return 0 if processed["validation_summary"]["schema_valid"] else 1


def raw_page_summary(payload: dict[str, object], page_id: str, regions) -> dict[str, object]:
    page_width, page_height = page_size(payload, page_id)
    raw_regions = []
    for region in regions:
        domain_label = map_region_to_ebs_math_domain(region, page_width, page_height)
        raw_regions.append({
            "label": region.label,
            "domain_label": domain_label.domain_label,
            "content_type": domain_label.content_type,
            "mapping_reason": domain_label.reason,
            "bbox": region.bbox,
            "confidence": region.confidence,
            "raw": region.raw,
        })
    return {
        "page_id": page_id,
        "region_count": len(regions),
        "regions": raw_regions,
    }


def page_size(payload: dict[str, object], page_id: str) -> tuple[float, float]:
    for page in payload.get("pages", []):
        if not isinstance(page, dict) or page.get("page_id") != page_id:
            continue
        geometry = page.get("page_geometry")
        if not isinstance(geometry, dict):
            continue
        width = geometry.get("width")
        height = geometry.get("height")
        if isinstance(width, (int, float)) and isinstance(height, (int, float)):
            return float(width), float(height)
    return 1.0, 1.0


def domain_label_counts(raw_payload: dict[str, object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for page in raw_payload.get("pages", []):
        if not isinstance(page, dict):
            continue
        for region in page.get("regions", []):
            if not isinstance(region, dict):
                continue
            label = region.get("domain_label")
            if isinstance(label, str):
                counts[label] = counts.get(label, 0) + 1
    return counts


def selected_labels(args: argparse.Namespace) -> set[str]:
    labels = {normalize_label(label) for label in (args.include_label or [])}
    if not labels:
        labels = {"table", "image", "figure", "chart", "graph"}
    if args.include_formula:
        labels.update({"formula", "equation"})
    if args.include_text_layout:
        labels.update({"text", "paragraph_title", "title", "header", "footer", "number"})
    return labels


def filter_regions(regions, include_labels: set[str]):
    return [
        region
        for region in regions
        if label_matches(normalize_label(region.label), include_labels)
    ]


def label_matches(label: str, include_labels: set[str]) -> bool:
    if label in include_labels:
        return True
    tokens = set(label.split("_"))
    return bool(tokens & include_labels)


def normalize_label(label: str) -> str:
    return label.strip().lower().replace(" ", "_").replace("-", "_")


def image_path_for(images_dir: Path, page_id: str) -> Path | None:
    matches = sorted(images_dir.glob(f"*_{page_id}.png"))
    return matches[0] if matches else None


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
