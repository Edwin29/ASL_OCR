"""General OCR contracts and adapters."""

from document_parser.ocr.base import BBox, GeneralOcrAdapter, OcrPageResult, OcrToken
from document_parser.ocr.noop import NoopGeneralOcrAdapter

__all__ = ["BBox", "GeneralOcrAdapter", "NoopGeneralOcrAdapter", "OcrPageResult", "OcrToken"]

