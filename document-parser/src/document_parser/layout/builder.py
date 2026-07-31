from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from document_parser.ocr.base import BBox, OcrToken


@dataclass(frozen=True)
class LayoutLine:
    line_id: str
    tokens: list[OcrToken]
    bbox: BBox
    text: str
    confidence: float


@dataclass(frozen=True)
class LayoutBlock:
    block_id: str
    lines: list[LayoutLine]
    bbox: BBox


class LayoutBuilder:
    """Group OCR tokens into line and block structures."""

    def __init__(
        self,
        line_y_tolerance_ratio: float = 0.65,
        line_x_gap_ratio: float = 8.0,
        token_space_gap_ratio: float = 0.45,
        block_gap_ratio: float = 1.35,
    ) -> None:
        self.line_y_tolerance_ratio = line_y_tolerance_ratio
        self.line_x_gap_ratio = line_x_gap_ratio
        self.token_space_gap_ratio = token_space_gap_ratio
        self.block_gap_ratio = block_gap_ratio

    def build_lines(self, tokens: list[OcrToken], page_id: str) -> list[LayoutLine]:
        if not tokens:
            return []
        sorted_tokens = sorted(tokens, key=lambda token: (center_y(token.bbox), token.bbox.x))
        groups: list[list[OcrToken]] = []
        for token_item in sorted_tokens:
            target_index = self._matching_line_index(groups, token_item)
            if target_index is None:
                groups.append([token_item])
            else:
                groups[target_index].append(token_item)

        lines: list[LayoutLine] = []
        for index, group in enumerate(groups, start=1):
            line_tokens = sorted(group, key=lambda token: token.bbox.x)
            bbox = union_bbox([token.bbox for token in line_tokens])
            lines.append(LayoutLine(
                line_id=f"{page_id}-l{index:03d}",
                tokens=line_tokens,
                bbox=bbox,
                text=join_line_text(line_tokens, gap_ratio=self.token_space_gap_ratio),
                confidence=average_confidence(line_tokens),
            ))
        return sorted(lines, key=lambda line: (line.bbox.y, line.bbox.x))

    def build_blocks(self, lines: list[LayoutLine], page_id: str) -> list[LayoutBlock]:
        if not lines:
            return []
        sorted_lines = sorted(lines, key=lambda line: (line.bbox.y, line.bbox.x))
        typical_height = median([line.bbox.height for line in sorted_lines])
        blocks: list[list[LayoutLine]] = []
        for line in sorted_lines:
            target_index = self._matching_block_index(blocks, line, typical_height)
            if target_index is None:
                blocks.append([line])
            else:
                blocks[target_index].append(line)

        return [
            LayoutBlock(
                block_id=f"{page_id}-b{index:03d}",
                lines=block_lines,
                bbox=union_bbox([line.bbox for line in block_lines]),
            )
            for index, block_lines in enumerate(blocks, start=1)
        ]

    def resolve_reading_order(self, blocks: list[LayoutBlock]) -> list[LayoutLine]:
        ordered_lines: list[LayoutLine] = []
        for block in sorted(blocks, key=lambda item: (item.bbox.y, item.bbox.x)):
            ordered_lines.extend(sorted(block.lines, key=lambda line: (line.bbox.y, line.bbox.x)))
        return ordered_lines

    def _matching_line_index(self, groups: list[list[OcrToken]], token: OcrToken) -> int | None:
        token_height = max(token.bbox.height, 1)
        token_center_y = center_y(token.bbox)
        for index, group in enumerate(groups):
            group_center = median([center_y(item.bbox) for item in group])
            group_height = median([max(item.bbox.height, 1) for item in group])
            tolerance = max(token_height, group_height) * self.line_y_tolerance_ratio
            if (
                abs(token_center_y - group_center) <= tolerance
                and self._is_horizontally_continuous(group, token)
            ):
                return index
        return None

    def _matching_block_index(
        self,
        blocks: list[list[LayoutLine]],
        line: LayoutLine,
        typical_height: float,
    ) -> int | None:
        candidates: list[tuple[float, int]] = []
        for index, block in enumerate(blocks):
            previous = block[-1]
            vertical_gap = line.bbox.y - (previous.bbox.y + previous.bbox.height)
            same_column = horizontal_overlap_ratio(previous.bbox, line.bbox) >= 0.2
            if 0 <= vertical_gap <= typical_height * self.block_gap_ratio and same_column:
                candidates.append((vertical_gap, index))
        if not candidates:
            return None
        return min(candidates)[1]

    def _is_horizontally_continuous(self, group: list[OcrToken], token: OcrToken) -> bool:
        group_bbox = union_bbox([item.bbox for item in group])
        group_height = median([max(item.bbox.height, 1) for item in group])
        token_height = max(token.bbox.height, 1)
        max_gap = max(group_height, token_height) * self.line_x_gap_ratio
        gap = horizontal_gap(group_bbox, token.bbox)
        return gap <= max_gap


def center_y(bbox: BBox) -> float:
    return bbox.y + bbox.height / 2


def center_x(bbox: BBox) -> float:
    return bbox.x + bbox.width / 2


def union_bbox(boxes: list[BBox]) -> BBox:
    if not boxes:
        raise ValueError("Cannot union an empty bbox list.")
    min_x = min(box.x for box in boxes)
    min_y = min(box.y for box in boxes)
    max_x = max(box.x + box.width for box in boxes)
    max_y = max(box.y + box.height for box in boxes)
    return BBox(x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y)


def average_confidence(tokens: list[OcrToken]) -> float:
    if not tokens:
        return 0.0
    return round(sum(token.confidence for token in tokens) / len(tokens), 6)


def join_line_text(tokens: list[OcrToken], gap_ratio: float) -> str:
    if not tokens:
        return ""
    ordered = sorted(tokens, key=lambda token: token.bbox.x)
    typical_height = median([max(token.bbox.height, 1) for token in ordered])
    pieces = [ordered[0].text]
    previous = ordered[0]
    for token in ordered[1:]:
        gap = token.bbox.x - (previous.bbox.x + previous.bbox.width)
        if gap > typical_height * gap_ratio:
            pieces.append(" ")
        pieces.append(token.text)
        previous = token
    return "".join(pieces)


def horizontal_overlap_ratio(left: BBox, right: BBox) -> float:
    overlap = max(0.0, min(left.x + left.width, right.x + right.width) - max(left.x, right.x))
    denominator = max(min(left.width, right.width), 1)
    return overlap / denominator


def horizontal_gap(left: BBox, right: BBox) -> float:
    if left.x + left.width < right.x:
        return right.x - (left.x + left.width)
    if right.x + right.width < left.x:
        return left.x - (right.x + right.width)
    return 0.0
