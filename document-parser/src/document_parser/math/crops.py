from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image


def export_math_candidate_crops(
    payload: dict[str, object],
    images_dir: Path,
    output_dir: Path,
    padding: int = 8,
    page_ids: set[str] | None = None,
) -> dict[str, object]:
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Page IR payload must contain a pages list.")
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_pages = []
    all_crops = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("page_id")
        if not isinstance(page_id, str):
            continue
        if page_ids is not None and page_id not in page_ids:
            continue
        image_path = find_page_image(images_dir, page_id)
        page_crops = export_page_math_candidate_crops(page, image_path, output_dir, padding)
        manifest_pages.append({
            "page_id": page_id,
            "image_path": str(image_path),
            "candidate_count": len(page_crops),
            "crops": page_crops,
        })
        all_crops.extend(page_crops)

    return {
        "crop_manifest_version": 1,
        "mode": "math_candidate_crops",
        "padding": padding,
        "page_count": len(manifest_pages),
        "crop_count": len(all_crops),
        "pages": manifest_pages,
    }


def export_page_math_candidate_crops(
    page: dict[str, Any],
    image_path: Path,
    output_dir: Path,
    padding: int,
) -> list[dict[str, object]]:
    page_id = str(page.get("page_id", image_path.stem))
    crops = []
    with Image.open(image_path) as image:
        width, height = image.size
        for node in candidate_nodes(page):
            node_id = str(node["node_id"])
            candidate = node.get("layout", {}).get("math_candidate", {})
            spans = math_span_candidates(node)
            if spans:
                for span_index, span in enumerate(spans, start=1):
                    crop = export_one_crop(
                        image=image,
                        image_width=width,
                        image_height=height,
                        box=span["bbox"],
                        padding=padding,
                        crop_path=output_dir / page_id / (
                            f"{safe_filename(node_id)}_span{span_index:02d}_math_candidate.png"
                        ),
                    )
                    if crop is None:
                        continue
                    crops.append({
                        "page_id": page_id,
                        "node_id": node_id,
                        "crop_level": "span",
                        "span_index": span_index,
                        **crop,
                        "score": candidate.get("score"),
                        "candidate_kind": candidate.get("candidate_kind"),
                        "reasons": candidate.get("reasons", []),
                        "text": span.get("text", ""),
                    })
                continue

            # Fallback for nodes without split span data yet (legacy Page IR, or a
            # candidate line the span splitter did not confirm as math): crop the
            # whole line, same as before span-level splitting existed.
            box = bbox(node)
            if box is None:
                continue
            crop = export_one_crop(
                image=image,
                image_width=width,
                image_height=height,
                box=box,
                padding=padding,
                crop_path=output_dir / page_id / f"{safe_filename(node_id)}_math_candidate.png",
            )
            if crop is None:
                continue
            crops.append({
                "page_id": page_id,
                "node_id": node_id,
                "crop_level": "node",
                "span_index": None,
                **crop,
                "score": candidate.get("score"),
                "candidate_kind": candidate.get("candidate_kind"),
                "reasons": candidate.get("reasons", []),
                "text": node.get("normalized_text", ""),
            })
    return crops


def export_one_crop(
    image: Image.Image,
    image_width: int,
    image_height: int,
    box: dict[str, float],
    padding: int,
    crop_path: Path,
) -> dict[str, object] | None:
    crop_box = padded_crop_box(box, image_width=image_width, image_height=image_height, padding=padding)
    if crop_box is None:
        return None
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    image.crop(crop_box).save(crop_path)
    return {
        "crop_path": str(crop_path),
        "bbox": box,
        "crop_bbox": {
            "x": crop_box[0],
            "y": crop_box[1],
            "width": crop_box[2] - crop_box[0],
            "height": crop_box[3] - crop_box[1],
        },
        "image_size": {"width": image_width, "height": image_height},
    }


def math_span_candidates(node: dict[str, Any]) -> list[dict[str, object]]:
    spans = node.get("spans")
    if not isinstance(spans, list):
        return []
    confirmed = []
    for span in spans:
        if not isinstance(span, dict) or span.get("math_span_candidate") is not True:
            continue
        box = bbox_from_dict(span.get("bbox"))
        if box is None:
            continue
        confirmed.append({**span, "bbox": box})
    return confirmed


def candidate_nodes(page: dict[str, Any]) -> list[dict[str, Any]]:
    reading_order_ids = [
        node_id
        for node_id in page.get("reading_order", [])
        if isinstance(node_id, str)
    ]
    index_by_id = {node_id: index for index, node_id in enumerate(reading_order_ids)}
    nodes = [
        node
        for node in page.get("nodes", [])
        if isinstance(node, dict)
        and isinstance(node.get("node_id"), str)
        and node.get("content_type") == "TEXT"
        and node.get("node_id") in index_by_id
        and is_math_candidate(node)
    ]
    return sorted(nodes, key=lambda node: index_by_id[str(node["node_id"])])


def is_math_candidate(node: dict[str, Any]) -> bool:
    layout = node.get("layout")
    if not isinstance(layout, dict):
        return False
    candidate = layout.get("math_candidate")
    return isinstance(candidate, dict) and candidate.get("is_candidate") is True


def bbox(node: dict[str, Any]) -> dict[str, float] | None:
    return bbox_from_dict(node.get("bbox"))


def bbox_from_dict(raw: object) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    values = {key: number_value(raw.get(key)) for key in ("x", "y", "width", "height")}
    if any(value is None for value in values.values()):
        return None
    return {key: float(value) for key, value in values.items() if value is not None}


def padded_crop_box(
    box: dict[str, float],
    image_width: int,
    image_height: int,
    padding: int,
) -> tuple[int, int, int, int] | None:
    left = max(0, int(box["x"]) - padding)
    top = max(0, int(box["y"]) - padding)
    right = min(image_width, int(box["x"] + box["width"]) + padding)
    bottom = min(image_height, int(box["y"] + box["height"]) + padding)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def find_page_image(images_dir: Path, page_id: str) -> Path:
    candidates = sorted(images_dir.glob(f"*_{page_id}.png"))
    if not candidates:
        candidates = sorted(images_dir.glob(f"*{page_id}*.png"))
    if not candidates:
        raise FileNotFoundError(f"No PNG image found for page_id={page_id} in {images_dir}")
    return candidates[0].resolve()


def safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
