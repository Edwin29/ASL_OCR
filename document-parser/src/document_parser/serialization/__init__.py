"""Page IR serialization helpers."""

from document_parser.serialization.reading_order import (
    apply_two_column_reading_order,
    apply_two_column_reading_order_to_document,
)
from document_parser.serialization.table_html import build_table_ir, parse_table_html
from document_parser.serialization.text_ir import TextOnlyPageIrBuilder
from document_parser.serialization.visual_regions import (
    apply_intro_page_exclusion,
    apply_intro_page_exclusions_to_document,
)
from document_parser.serialization.vl_page_ir import build_document_ir_from_vl, build_page_ir_from_vl_result

__all__ = [
    "TextOnlyPageIrBuilder",
    "apply_two_column_reading_order",
    "apply_two_column_reading_order_to_document",
    "apply_intro_page_exclusion",
    "apply_intro_page_exclusions_to_document",
    "build_document_ir_from_vl",
    "build_page_ir_from_vl_result",
    "build_table_ir",
    "parse_table_html",
]
