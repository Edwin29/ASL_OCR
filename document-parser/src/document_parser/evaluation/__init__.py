"""Evaluation and diagnostic reports for parser outputs."""

from document_parser.evaluation.ocr_quality import build_ocr_quality_report
from document_parser.evaluation.ocr_comparison import build_ocr_comparison_report
from document_parser.evaluation.sample_review import build_sample_review_report

__all__ = ["build_ocr_comparison_report", "build_ocr_quality_report", "build_sample_review_report"]
