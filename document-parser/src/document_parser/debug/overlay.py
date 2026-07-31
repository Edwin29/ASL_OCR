from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


CONTENT_COLORS = {
    "TEXT": (0, 116, 217),
    "MATH": (177, 13, 201),
    "TABLE": (46, 160, 67),
    "UNSUPPORTED_VISUAL": (255, 133, 27),
    "UNKNOWN": (120, 120, 120),
}
SPLIT_OCR_DRAFT_COLOR = (214, 84, 0)
SPLIT_OCR_EVIDENCE_COLOR = (98, 98, 98)
DEFAULT_COLOR = (220, 20, 60)
LABEL_BACKGROUND = (255, 255, 255)


@dataclass(frozen=True)
class OverlayRenderResult:
    page_id: str
    image_path: str
    output_path: str
    node_count: int
    issue_count: int
    quality_status: str | None

    def to_jsonable(self) -> dict[str, object]:
        return asdict(self)


def render_document_overlays(
    payload: dict[str, object],
    images_dir: Path,
    output_dir: Path,
    page_ids: set[str] | None = None,
) -> list[OverlayRenderResult]:
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Page IR payload must contain a pages list.")

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[OverlayRenderResult] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("page_id")
        if not isinstance(page_id, str):
            continue
        if page_ids is not None and page_id not in page_ids:
            continue
        image_path = find_page_image(images_dir, page_id)
        output_path = output_dir / f"{page_id}_overlay.png"
        results.append(render_page_overlay(page, image_path, output_path))
    return results


def render_page_overlay(page: dict[str, Any], image_path: Path, output_path: Path) -> OverlayRenderResult:
    page_id = str(page.get("page_id", image_path.stem))
    with Image.open(image_path) as image:
        canvas = image.convert("RGBA")

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()

    nodes = page.get("nodes") if isinstance(page.get("nodes"), list) else []
    for index, node in enumerate(nodes, start=1):
        if isinstance(node, dict):
            _draw_node(draw, node, index, font)

    header_text = _header_text(page, len(nodes))
    _draw_label(draw, (12, 12), header_text, font, fill=(0, 0, 0), background=(255, 255, 255, 220))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(canvas, overlay).convert("RGB").save(output_path)
    parse_issues = page.get("parse_issues") if isinstance(page.get("parse_issues"), list) else []
    quality_report = page.get("quality_report") if isinstance(page.get("quality_report"), dict) else {}
    quality_status = quality_report.get("status") if isinstance(quality_report.get("status"), str) else None
    return OverlayRenderResult(
        page_id=page_id,
        image_path=str(image_path),
        output_path=str(output_path),
        node_count=len(nodes),
        issue_count=len(parse_issues),
        quality_status=quality_status,
    )


def find_page_image(images_dir: Path, page_id: str) -> Path:
    candidates = sorted(images_dir.glob(f"*_{page_id}.png"))
    if not candidates:
        candidates = sorted(images_dir.glob(f"*{page_id}*.png"))
    if not candidates:
        raise FileNotFoundError(f"No PNG image found for page_id={page_id} in {images_dir}")
    return candidates[0].resolve()


def _draw_node(draw: ImageDraw.ImageDraw, node: dict[str, Any], index: int, font: ImageFont.ImageFont) -> None:
    bbox = node.get("bbox")
    if not isinstance(bbox, dict):
        return
    box = _bbox_tuple(bbox)
    if box is None:
        return
    content_type = node.get("content_type")
    color = _node_color(node, content_type)
    draw.rectangle(box, outline=color + (255,), width=_node_outline_width(node))
    label_index = _label_index(node, index)
    label = _node_label(node, label_index, content_type)
    _draw_label(draw, (box[0], max(0, box[1] - 16)), label, font, fill=color)


def _node_color(node: dict[str, Any], content_type: object) -> tuple[int, int, int]:
    layout = node.get("layout")
    if isinstance(layout, dict) and layout.get("is_split_ocr_replacement_draft") is True:
        return SPLIT_OCR_DRAFT_COLOR
    if isinstance(layout, dict) and isinstance(layout.get("split_ocr_replaced_by_node_ids"), list):
        return SPLIT_OCR_EVIDENCE_COLOR
    return CONTENT_COLORS.get(content_type, DEFAULT_COLOR)


def _node_outline_width(node: dict[str, Any]) -> int:
    layout = node.get("layout")
    if isinstance(layout, dict) and isinstance(layout.get("split_ocr_replaced_by_node_ids"), list):
        return 2
    return 4


def _node_label(node: dict[str, Any], label_index: int, content_type: object) -> str:
    label_type = content_type if isinstance(content_type, str) else "UNKNOWN"
    layout = node.get("layout")
    if isinstance(layout, dict) and layout.get("is_split_ocr_replacement_draft") is True:
        return f"{label_index}:SPLIT_TEXT"
    if isinstance(layout, dict) and isinstance(layout.get("split_ocr_replaced_by_node_ids"), list):
        return "EVIDENCE"
    return f"{label_index}:{label_type}"


def _draw_label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    background: tuple[int, int, int, int] = (255, 255, 255, 210),
) -> None:
    bbox = draw.textbbox(xy, text, font=font)
    padded = (bbox[0] - 3, bbox[1] - 2, bbox[2] + 3, bbox[3] + 2)
    draw.rectangle(padded, fill=background)
    draw.text(xy, text, fill=fill + (255,), font=font)


def _bbox_tuple(bbox: dict[str, Any]) -> tuple[int, int, int, int] | None:
    try:
        x = round(float(bbox["x"]))
        y = round(float(bbox["y"]))
        width = round(float(bbox["width"]))
        height = round(float(bbox["height"]))
    except (KeyError, TypeError, ValueError):
        return None
    if width < 0 or height < 0:
        return None
    return (x, y, x + width, y + height)


def _label_index(node: dict[str, Any], fallback_index: int) -> int:
    reading_order_index = node.get("reading_order_index")
    if isinstance(reading_order_index, int):
        return reading_order_index + 1
    return fallback_index


def _header_text(page: dict[str, Any], node_count: int) -> str:
    page_id = page.get("page_id", "unknown")
    quality_report = page.get("quality_report") if isinstance(page.get("quality_report"), dict) else {}
    quality_status = quality_report.get("status", "UNKNOWN")
    parse_issues = page.get("parse_issues") if isinstance(page.get("parse_issues"), list) else []
    return f"{page_id} | nodes={node_count} | issues={len(parse_issues)} | quality={quality_status}"
