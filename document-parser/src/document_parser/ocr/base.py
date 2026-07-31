from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from document_parser.ingest import ImageDocument


@dataclass(frozen=True)
class BBox:
    x: float
    y: float
    width: float
    height: float

    def to_jsonable(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class OcrToken:
    text: str
    bbox: BBox
    confidence: float
    token_id: str | None = None
    line_hint: str | None = None
    raw: dict[str, Any] | None = None

    def to_jsonable(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bbox"] = self.bbox.to_jsonable()
        return payload


@dataclass(frozen=True)
class OcrPageResult:
    page_id: str
    engine_id: str
    engine_version: str
    tokens: list[OcrToken]
    raw_result: dict[str, Any]
    issues: list[dict[str, Any]]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "tokens": [token.to_jsonable() for token in self.tokens],
            "raw_result": self.raw_result,
            "issues": self.issues,
        }


class GeneralOcrAdapter(Protocol):
    engine_id: str
    engine_version: str

    def recognize(self, image: ImageDocument) -> OcrPageResult:
        """Run OCR and return normalized OCR tokens."""

