"""Conservative, auditable post-processing for OCR output."""

from document_parser.postprocessing.ocr_dictionary import (
    AppliedCorrection,
    CorrectionResult,
    correct_ocr_text,
    correction_issues,
)

__all__ = [
    "AppliedCorrection",
    "CorrectionResult",
    "correct_ocr_text",
    "correction_issues",
]
