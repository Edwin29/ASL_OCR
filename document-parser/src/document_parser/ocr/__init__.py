"""General OCR contracts and adapters."""

from document_parser.ocr.base import BBox, GeneralOcrAdapter, OcrPageResult, OcrToken
from document_parser.ocr.baseline import create_baseline_ocr_adapter
from document_parser.ocr.easyocr_adapter import EasyOcrGeneralAdapter
from document_parser.ocr.noop import NoopGeneralOcrAdapter
from document_parser.ocr.paddleocr_adapter import PaddleOcrGeneralAdapter

__all__ = [
    "BBox",
    "EasyOcrGeneralAdapter",
    "GeneralOcrAdapter",
    "NoopGeneralOcrAdapter",
    "OcrPageResult",
    "OcrToken",
    "PaddleOcrGeneralAdapter",
    "create_baseline_ocr_adapter",
]
