"""Incremental one-page parser boundary used by Server S1 workers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any, Protocol

from document_parser.accessibility.flattening import flatten_page
from document_parser.serialization.vl_page_ir import build_page_ir_from_vl_result
from document_parser.structure.problem_units import detect_problem_units_in_document
from document_parser.validation import validate_document_ir


class FragmentParserPort(Protocol):
    def parse(self, image_path: Path, page_id: str, document_id: str) -> "ParsedFragment": ...


class ParserRejectError(RuntimeError):
    def __init__(self, code: str, message: str, validation: dict[str, object] | None = None):
        super().__init__(message)
        self.code = code
        self.validation = validation or {}


@dataclass(frozen=True, slots=True)
class ParsedFragment:
    page_ir: dict[str, object]
    accessible_page: dict[str, object]
    engine_manifest: dict[str, object]
    validation: dict[str, object]


class PaddleVlFragmentParser:
    """Reuses one injected PaddleOCR-VL adapter and the established Page IR path."""

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter

    def parse(self, image_path: Path, page_id: str, document_id: str) -> ParsedFragment:
        raw = self.adapter.parse_page(image_path)
        page = build_page_ir_from_vl_result(raw, page_id=page_id)
        payload: dict[str, object] = {
            "document_manifest": {"book_id": document_id, "page_count": 1},
            "engine_manifest": {
                "general_ocr": {
                    "engine_id": str(getattr(self.adapter, "engine_id", "paddleocr-vl")),
                    "engine_version": str(getattr(self.adapter, "engine_version", "unknown")),
                },
                "pipeline": {"mode": "incremental_paddleocr_vl"},
            },
            "pages": [page],
            "validation_summary": {},
        }
        payload = detect_problem_units_in_document(payload)
        validation = validate_document_ir(payload)
        payload["validation_summary"] = validation
        if validation.get("schema_valid") is not True:
            raise ParserRejectError(
                "PAGE_IR_INVALID",
                "Document Parser produced an invalid one-page IR",
                validation,
            )
        pages = payload.get("pages")
        if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], dict):
            raise ParserRejectError("PAGE_IR_PAGE_COUNT", "fragment parser must produce exactly one page")
        accessible = flatten_page(pages[0])
        items = accessible.get("focus_items")
        if not isinstance(items, list) or not items:
            raise ParserRejectError(
                "EMPTY_ACCESSIBLE_PAGE",
                "parsed page contains no accessible focus items",
                validation,
            )
        engine = payload.get("engine_manifest")
        return ParsedFragment(
            page_ir=pages[0],
            accessible_page=accessible,
            engine_manifest=engine if isinstance(engine, dict) else {},
            validation=validation,
        )


class SerializedPageAdapter:
    """Serializes parse_page calls shared by legacy and S1 GPU workers."""

    def __init__(self, adapter: Any, lock: threading.Lock | None = None) -> None:
        self.adapter = adapter
        self.lock = lock or threading.Lock()
        self.engine_id = getattr(adapter, "engine_id", "unknown")
        self.engine_version = getattr(adapter, "engine_version", "unknown")

    def parse_page(self, image_path: Path):
        with self.lock:
            return self.adapter.parse_page(image_path)


class SerializedSynthesizer:
    def __init__(self, synthesize: Any, lock: threading.Lock | None = None) -> None:
        self.synthesize = synthesize
        self.lock = lock or threading.Lock()

    def __call__(self, text: str):
        with self.lock:
            return self.synthesize(text)
