from __future__ import annotations

from document_parser.ingest import ImageDocument
from document_parser.ocr.base import OcrPageResult


class NoopGeneralOcrAdapter:
    """Adapter used when no real OCR engine has been configured yet."""

    engine_id = "noop-general-ocr"
    engine_version = "0.1.0"

    def recognize(self, image: ImageDocument) -> OcrPageResult:
        return OcrPageResult(
            page_id=image.page_id,
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            tokens=[],
            raw_result={
                "status": "not_configured",
                "message": "No general OCR engine is configured for this milestone.",
            },
            issues=[
                {
                    "code": "OCR_ENGINE_NOT_CONFIGURED",
                    "severity": "warning",
                    "message": "General OCR adapter contract is present, but no real OCR engine is configured.",
                }
            ],
        )

