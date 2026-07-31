from __future__ import annotations

from document_parser.ingest import ImageDocument
from document_parser.ocr.base import BBox, OcrPageResult, OcrToken


class FixtureGeneralOcrAdapter:
    """Deterministic adapter for contract tests and hand-authored fixtures."""

    engine_id = "fixture-general-ocr"
    engine_version = "0.1.0"

    def __init__(self, tokens_by_page: dict[str, list[OcrToken]]) -> None:
        self.tokens_by_page = tokens_by_page

    def recognize(self, image: ImageDocument) -> OcrPageResult:
        return OcrPageResult(
            page_id=image.page_id,
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            tokens=self.tokens_by_page.get(image.page_id, []),
            raw_result={"status": "fixture"},
            issues=[],
        )


def token(text: str, x: float, y: float, width: float, height: float, confidence: float = 0.99) -> OcrToken:
    return OcrToken(text=text, bbox=BBox(x=x, y=y, width=width, height=height), confidence=confidence)

