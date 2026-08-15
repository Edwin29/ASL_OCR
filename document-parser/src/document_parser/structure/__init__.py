"""Structure/layout region extraction adapters."""

from document_parser.structure.domain_mapping import DomainStructureLabel, map_region_to_ebs_math_domain
from document_parser.structure.barriers import (
    DEFAULT_BARRIER_LABELS,
    apply_layout_barriers,
    apply_layout_barriers_to_document,
)
from document_parser.structure.barrier_splits import export_barrier_split_work_units
from document_parser.structure.barrier_split_ocr import recognize_barrier_split_work_units
from document_parser.structure.barrier_reconciliation import apply_split_ocr_reconciliation_to_document
from document_parser.structure.barrier_replacement import apply_split_ocr_replacement_draft_to_document
from document_parser.structure.linking import link_structure_regions_to_text
from document_parser.structure.paddle_structure_adapter import (
    PaddleStructureRegionAdapter,
    StructureRegion,
    apply_structure_regions_to_document,
)
from document_parser.structure.problem_units import (
    PROBLEM_UNIT_STRUCTURE_LABEL,
    ProblemCandidate,
    detect_problem_units_in_document,
    detect_problem_units_in_page,
    problem_unit_report,
)
from document_parser.structure.promotion import (
    PROMOTABLE_STRUCTURE_LABELS,
    promote_structure_candidates_to_primary_order,
    promote_structure_candidates_to_primary_order_for_document,
)
from document_parser.structure.replacement_review import build_split_ocr_replacement_review_report

__all__ = [
    "DomainStructureLabel",
    "DEFAULT_BARRIER_LABELS",
    "PROBLEM_UNIT_STRUCTURE_LABEL",
    "PaddleStructureRegionAdapter",
    "PROMOTABLE_STRUCTURE_LABELS",
    "ProblemCandidate",
    "StructureRegion",
    "apply_layout_barriers",
    "apply_layout_barriers_to_document",
    "apply_split_ocr_replacement_draft_to_document",
    "apply_split_ocr_reconciliation_to_document",
    "apply_structure_regions_to_document",
    "build_split_ocr_replacement_review_report",
    "detect_problem_units_in_document",
    "detect_problem_units_in_page",
    "export_barrier_split_work_units",
    "link_structure_regions_to_text",
    "map_region_to_ebs_math_domain",
    "problem_unit_report",
    "promote_structure_candidates_to_primary_order",
    "promote_structure_candidates_to_primary_order_for_document",
    "recognize_barrier_split_work_units",
]
