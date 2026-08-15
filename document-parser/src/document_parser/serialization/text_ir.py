from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

from document_parser.assets.constants import BOOK_ID, PROFILE_HINT
from document_parser.ingest import ImageDocument, ImageIngestor
from document_parser.layout import LayoutBuilder, LayoutLine
from document_parser.ocr.base import BBox, GeneralOcrAdapter, OcrPageResult
from document_parser.ocr.cache import OcrResultCache
from document_parser.ocr.noop import NoopGeneralOcrAdapter
from document_parser.preprocess import ImageQualityGate, QualityIssue, QualityReport
from document_parser.serialization.reading_order import apply_two_column_reading_order
from document_parser.serialization.visual_regions import apply_intro_page_exclusion
from document_parser.validation import validate_document_ir


class TextOnlyPageIrBuilder:
    """Build the first vertical Page IR slice from general OCR tokens only."""

    def __init__(self, adapter: GeneralOcrAdapter, cache: OcrResultCache | None = None) -> None:
        self.adapter = adapter
        self.cache = cache
        self.quality_gate = ImageQualityGate()
        self.ingestor = ImageIngestor()
        self.layout_builder = LayoutBuilder()

    def build_document(self, image_paths: Iterable[Path], book_id: str = BOOK_ID) -> dict[str, object]:
        pages = []
        engine_manifest = {
            "general_ocr": {
                "engine_id": self.adapter.engine_id,
                "engine_version": self.adapter.engine_version,
            },
            "pipeline": {
                "mode": "text_only",
                "requires_pdf_text_layer": False,
                "layout_mode": "token_line_block",
                "visual_region_mode": "approval_gated_unsupported_page_candidates",
                "reading_order_mode": "two_column_candidate_postprocess",
            },
        }
        for index, image_path in enumerate(sorted(image_paths), start=1):
            page_id = page_id_from_path(image_path, fallback_index=index)
            image = self.ingestor.load(image_path, page_id=page_id)
            quality = self.quality_gate.evaluate_path(image_path, page_id=page_id)
            result = self.adapter.recognize(image)
            cache_path = self.cache.write(image, result) if self.cache else None
            pages.append(self.build_page(image, quality, result, cache_path=cache_path))

        payload: dict[str, object] = {
            "document_manifest": {
                "book_id": book_id,
                "profile_hint": PROFILE_HINT,
                "page_count": len(pages),
            },
            "pages": pages,
            "engine_manifest": engine_manifest,
            "validation_summary": {},
        }
        payload["validation_summary"] = validate_document_ir(payload)
        return payload

    def build_page(
        self,
        image: ImageDocument,
        quality: QualityReport,
        result: OcrPageResult,
        cache_path: Path | None = None,
    ) -> dict[str, object]:
        lines = self.layout_builder.build_lines(result.tokens, image.page_id)
        blocks = self.layout_builder.build_blocks(lines, image.page_id)
        ordered_lines = self.layout_builder.resolve_reading_order(blocks)
        nodes = [
            text_node_from_line(
                line=line,
                page_id=image.page_id,
                node_index=index,
                image_width=image.width,
                image_height=image.height,
                source_engine=result.engine_id,
            )
            for index, line in enumerate(ordered_lines, start=1)
        ]
        parse_issues = [issue_from_quality(issue) for issue in quality.issues]
        parse_issues.extend(result.issues)
        if cache_path is not None:
            parse_issues.append({
                "code": "OCR_RAW_CACHE_WRITTEN",
                "severity": "info",
                "message": str(cache_path),
            })
        page = {
            "page_id": image.page_id,
            "page_geometry": {
                "width": image.width,
                "height": image.height,
            },
            "nodes": nodes,
            "reading_order": [node["node_id"] for node in nodes],
            "parse_issues": parse_issues,
            "quality_report": quality.to_jsonable(),
        }
        page = apply_intro_page_exclusion(page)
        return apply_two_column_reading_order(page)


def text_node_from_line(
    line: LayoutLine,
    page_id: str,
    node_index: int,
    image_width: int,
    image_height: int,
    source_engine: str,
) -> dict[str, object]:
    node_id = f"{page_id}-n{node_index:03d}"
    return {
        "node_id": node_id,
        "content_type": "TEXT",
        "bbox": line.bbox.to_jsonable(),
        "normalized_bbox": normalize_bbox(line.bbox, image_width, image_height),
        "reading_order_index": node_index - 1,
        "confidence": line.confidence,
        "source_engine": source_engine,
        "issues": [],
        "raw_text": line.text,
        "normalized_text": line.text,
        "spans": [
            {
                "span_type": "TEXT",
                "text": line.text,
            }
        ],
        "layout": {
            "line_id": line.line_id,
            "source_token_count": len(line.tokens),
            "tokens": [
                {"text": token.text, "bbox": token.bbox.to_jsonable()}
                for token in line.tokens
            ],
        },
    }


def normalize_bbox(bbox: BBox, image_width: int, image_height: int) -> dict[str, float]:
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image width and height must be positive for bbox normalization.")
    return {
        "x": round(bbox.x / image_width, 6),
        "y": round(bbox.y / image_height, 6),
        "width": round(bbox.width / image_width, 6),
        "height": round(bbox.height / image_height, 6),
    }


def issue_from_quality(issue: QualityIssue) -> dict[str, str]:
    return {
        "code": issue.code,
        "severity": issue.severity,
        "message": issue.message,
    }


def page_id_from_path(path: Path, fallback_index: int) -> str:
    stem = path.stem
    match = re.search(r"(?:^|[_-])p(\d{1,4})(?:$|[_-])", stem)
    if match:
        return f"p{int(match.group(1)):03d}"
    return f"p{fallback_index:03d}"


def write_page_ir(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a TEXT-only Page IR skeleton from rendered page images.")
    parser.add_argument("--images-dir", type=Path, default=Path("document-parser/data/pages_pdf300"))
    parser.add_argument("--output", type=Path, default=Path("document-parser/data/debug/text_only_page_ir.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("document-parser/data/debug/ocr_cache"))
    args = parser.parse_args(argv)

    image_paths = sorted(args.images_dir.resolve().glob("*.png"))
    builder = TextOnlyPageIrBuilder(
        adapter=NoopGeneralOcrAdapter(),
        cache=OcrResultCache(args.cache_dir.resolve()),
    )
    page_ir = builder.build_document(image_paths)
    write_page_ir(args.output.resolve(), page_ir)
    print(f"Wrote {args.output.resolve()}")
    print(f"Pages: {len(page_ir['pages'])}")
    print("Adapter: noop-general-ocr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
