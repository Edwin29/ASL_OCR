from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class RegionLike(Protocol):
    label: str
    bbox: dict[str, float]


@dataclass(frozen=True)
class DomainStructureLabel:
    domain_label: str
    content_type: str
    reason: str


def map_region_to_ebs_math_domain(
    region: RegionLike,
    page_width: float,
    page_height: float,
) -> DomainStructureLabel:
    raw_label = normalize_label(region.label)
    width_ratio = safe_ratio(region.bbox["width"], page_width)
    height_ratio = safe_ratio(region.bbox["height"], page_height)
    area_ratio = width_ratio * height_ratio

    if raw_label == "table":
        if height_ratio >= 0.12 or area_ratio >= 0.08:
            return DomainStructureLabel(
                domain_label="PROBLEM_BOX_CANDIDATE",
                content_type="UNKNOWN",
                reason="Large table-like layout region is more likely a boxed textbook problem than a strict table.",
            )
        return DomainStructureLabel(
            domain_label="TABLE_CANDIDATE",
            content_type="TABLE",
            reason="Compact ruled region can advance as a table candidate.",
        )

    if raw_label in {"image", "figure", "chart", "graph"}:
        return DomainStructureLabel(
            domain_label="GRAPH_OR_DIAGRAM_CANDIDATE",
            content_type="UNSUPPORTED_VISUAL",
            reason="Image-like layout region should be separated from primary text OCR.",
        )

    if raw_label in {"figure_title", "table_title"}:
        return DomainStructureLabel(
            domain_label="VISUAL_OR_PROBLEM_CAPTION_CANDIDATE",
            content_type="UNKNOWN",
            reason="Caption-like region needs domain review before attaching to a visual, table, or problem box.",
        )

    if raw_label in {"formula", "equation"}:
        return DomainStructureLabel(
            domain_label="DISPLAY_FORMULA_CANDIDATE",
            content_type="MATH",
            reason="Formula-like layout region can advance to the math-detection stage.",
        )

    if raw_label in {"text", "paragraph_title", "title", "header", "footer", "number"}:
        return DomainStructureLabel(
            domain_label="TEXT_LAYOUT_CANDIDATE",
            content_type="UNKNOWN",
            reason="Text-layout region is kept separate from primary text nodes until ordering policy uses it.",
        )

    return DomainStructureLabel(
        domain_label="UNKNOWN_STRUCTURE_CANDIDATE",
        content_type="UNKNOWN",
        reason=f"Unmapped PaddleOCR layout label: {raw_label}.",
    )


def normalize_label(label: str) -> str:
    return label.strip().lower().replace(" ", "_").replace("-", "_")


def safe_ratio(value: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return value / denominator
