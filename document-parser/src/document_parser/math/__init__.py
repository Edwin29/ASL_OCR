"""Math candidate detection helpers."""

from document_parser.math.candidates import (
    detect_math_candidates_in_document,
    detect_math_candidates_in_page,
    math_candidate_report,
)
from document_parser.math.crops import export_math_candidate_crops
from document_parser.math.formula_ocr import (
    FormulaOcrAdapter,
    FormulaRecognitionResult,
    PaddleFormulaOcrAdapter,
    create_baseline_formula_ocr_adapter,
    recognize_math_candidate_crops,
    validate_formula_output,
)
from document_parser.math.formula_regions import (
    FORMULA_REGION_LABEL,
    export_formula_region_crops,
)
from document_parser.math.latex_ast import AstParseResult, parse_latex_to_ast, validate_ast
from document_parser.math.spans import (
    build_line_spans,
    detect_math_spans_in_document,
    detect_math_spans_in_page,
    math_span_report,
)

__all__ = [
    "FORMULA_REGION_LABEL",
    "AstParseResult",
    "FormulaOcrAdapter",
    "FormulaRecognitionResult",
    "PaddleFormulaOcrAdapter",
    "build_line_spans",
    "create_baseline_formula_ocr_adapter",
    "detect_math_candidates_in_document",
    "detect_math_candidates_in_page",
    "detect_math_spans_in_document",
    "detect_math_spans_in_page",
    "export_formula_region_crops",
    "export_math_candidate_crops",
    "math_candidate_report",
    "math_span_report",
    "parse_latex_to_ast",
    "recognize_math_candidate_crops",
    "validate_ast",
    "validate_formula_output",
]
