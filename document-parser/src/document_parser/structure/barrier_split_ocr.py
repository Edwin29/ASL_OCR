from __future__ import annotations

from pathlib import Path
from typing import Any

from document_parser.ingest import ImageIngestor
from document_parser.ocr.base import GeneralOcrAdapter, OcrToken


def recognize_barrier_split_work_units(
    split_manifest: dict[str, Any],
    adapter: GeneralOcrAdapter,
    path_base: Path,
) -> dict[str, Any]:
    pages = split_manifest.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Split manifest must contain a pages list.")

    ingestor = ImageIngestor()
    recognized_pages = []
    recognized_units = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("page_id")
        if not isinstance(page_id, str):
            continue
        work_units = page.get("work_units")
        if not isinstance(work_units, list):
            work_units = []

        page_units = []
        for index, unit in enumerate(work_units):
            if not isinstance(unit, dict):
                continue
            crop_path = resolve_crop_path(unit.get("crop_path"), path_base)
            crop_page_id = split_crop_page_id(page_id, unit, index)
            image = ingestor.load(crop_path, page_id=crop_page_id)
            ocr_result = adapter.recognize(image)
            recognized = recognized_work_unit(unit, crop_path, ocr_result.tokens, ocr_result.issues)
            page_units.append(recognized)
            recognized_units.append(recognized)

        recognized_pages.append({
            "page_id": page_id,
            "work_unit_count": len(page_units),
            "recognized_work_units": page_units,
        })

    return {
        "split_ocr_manifest_version": 1,
        "mode": "layout_barrier_split_crop_reocr",
        "source_split_manifest_mode": split_manifest.get("mode"),
        "engine_manifest": {
            "ocr_engine": adapter.engine_id,
            "ocr_engine_version": adapter.engine_version,
        },
        "page_count": len(recognized_pages),
        "work_unit_count": len(recognized_units),
        "recognized_work_unit_count": len(recognized_units),
        "pages": recognized_pages,
    }


def recognized_work_unit(
    unit: dict[str, Any],
    crop_path: Path,
    tokens: list[OcrToken],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    token_payloads = [token.to_jsonable() for token in tokens]
    return {
        "page_id": unit.get("page_id"),
        "source_text_node_id": unit.get("source_text_node_id"),
        "barrier_node_id": unit.get("barrier_node_id"),
        "structure_label": unit.get("structure_label"),
        "layout_barrier_role": unit.get("layout_barrier_role"),
        "crop_path": str(crop_path),
        "source_text": unit.get("source_text", ""),
        "recognized_text": join_token_text(tokens),
        "token_count": len(tokens),
        "tokens": token_payloads,
        "issues": issues,
        "source_text_bbox": unit.get("source_text_bbox"),
        "barrier_bbox": unit.get("barrier_bbox"),
        "intersection_bbox": unit.get("intersection_bbox"),
        "crop_bbox": unit.get("crop_bbox"),
    }


def join_token_text(tokens: list[OcrToken]) -> str:
    return " ".join(token.text.strip() for token in tokens if token.text.strip())


def resolve_crop_path(raw_path: object, path_base: Path) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("Split work unit is missing crop_path.")
    crop_path = Path(raw_path)
    if not crop_path.is_absolute():
        crop_path = path_base / crop_path
    return crop_path.resolve()


def split_crop_page_id(page_id: str, unit: dict[str, Any], index: int) -> str:
    text_id = unit.get("source_text_node_id")
    barrier_id = unit.get("barrier_node_id")
    if isinstance(text_id, str) and isinstance(barrier_id, str):
        return f"{page_id}-{text_id}-{barrier_id}"
    return f"{page_id}-split-{index + 1:03d}"
