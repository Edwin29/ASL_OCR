"""Math candidate detection helpers."""

from document_parser.math.candidates import (
    detect_math_candidates_in_document,
    detect_math_candidates_in_page,
    math_candidate_report,
)
from document_parser.math.crops import export_math_candidate_crops

__all__ = [
    "detect_math_candidates_in_document",
    "detect_math_candidates_in_page",
    "export_math_candidate_crops",
    "math_candidate_report",
]
