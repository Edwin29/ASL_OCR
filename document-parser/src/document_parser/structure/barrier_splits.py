from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from document_parser.structure.linking import bbox


def export_barrier_split_work_units(
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
    all_units = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_id = page.get("page_id")
        if not isinstance(page_id, str):
            continue
        if page_ids is not None and page_id not in page_ids:
            continue
        image_path = find_page_image(images_dir, page_id)
        page_units = export_page_barrier_split_work_units(page, image_path, output_dir, padding)
        manifest_pages.append({
            "page_id": page_id,
            "image_path": str(image_path),
            "work_unit_count": len(page_units),
            "work_units": page_units,
        })
        all_units.extend(page_units)

    return {
        "split_manifest_version": 1,
        "mode": "layout_barrier_crossing_split_crops",
        "padding": padding,
        "page_count": len(manifest_pages),
        "work_unit_count": len(all_units),
        "pages": manifest_pages,
    }


def export_page_barrier_split_work_units(
    page: dict[str, Any],
    image_path: Path,
    output_dir: Path,
    padding: int,
) -> list[dict[str, object]]:
    page_id = str(page.get("page_id", image_path.stem))
    node_by_id = {
        str(node["node_id"]): node
        for node in page.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("node_id"), str)
    }
    crossing_nodes = sorted(
        [node for node in node_by_id.values() if is_crossing_text_node(node)],
        key=lambda node: reading_order_key(page, node),
    )
    work_units = []
    with Image.open(image_path) as image:
        image_width, image_height = image.size
        for text_node in crossing_nodes:
            text_id = str(text_node["node_id"])
            text_box = bbox(text_node)
            if text_box is None:
                continue
            barrier_ids = crossing_barrier_ids(text_node)
            barrier_ids.sort(key=lambda barrier_id: barrier_sort_key(node_by_id.get(barrier_id, {})))
            for barrier_id in barrier_ids:
                barrier_node = node_by_id.get(barrier_id)
                barrier_box = bbox(barrier_node or {})
                if barrier_node is None or barrier_box is None:
                    continue
                intersection_box = intersection_bbox(text_box, barrier_box)
                if intersection_box is None:
                    continue
                crop_box = padded_crop_box(intersection_box, image_width, image_height, padding)
                if crop_box is None:
                    continue
                crop_path = output_dir / page_id / f"{safe_filename(text_id)}__{safe_filename(barrier_id)}_split.png"
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                image.crop(crop_box).save(crop_path)
                layout = barrier_node.get("layout") if isinstance(barrier_node.get("layout"), dict) else {}
                work_units.append({
                    "page_id": page_id,
                    "source_text_node_id": text_id,
                    "barrier_node_id": barrier_id,
                    "structure_label": layout.get("structure_label"),
                    "layout_barrier_role": layout.get("layout_barrier_role"),
                    "crop_path": str(crop_path),
                    "source_text_bbox": text_box,
                    "barrier_bbox": barrier_box,
                    "intersection_bbox": intersection_box,
                    "crop_bbox": {
                        "x": crop_box[0],
                        "y": crop_box[1],
                        "width": crop_box[2] - crop_box[0],
                        "height": crop_box[3] - crop_box[1],
                    },
                    "image_size": {"width": image_width, "height": image_height},
                    "source_text": text_node.get("normalized_text", ""),
                })
    return work_units


def is_crossing_text_node(node: dict[str, Any]) -> bool:
    if node.get("content_type") != "TEXT":
        return False
    layout = node.get("layout")
    if not isinstance(layout, dict):
        return False
    return len(crossing_barrier_ids(node)) >= 2


def crossing_barrier_ids(node: dict[str, Any]) -> list[str]:
    layout = node.get("layout")
    if not isinstance(layout, dict):
        return []
    return [
        barrier_id
        for barrier_id in layout.get("layout_barrier_crossing_candidate", [])
        if isinstance(barrier_id, str)
    ]


def intersection_bbox(left: dict[str, float], right: dict[str, float]) -> dict[str, float] | None:
    left_x = max(left["x"], right["x"])
    top_y = max(left["y"], right["y"])
    right_x = min(left["x"] + left["width"], right["x"] + right["width"])
    bottom_y = min(left["y"] + left["height"], right["y"] + right["height"])
    if right_x <= left_x or bottom_y <= top_y:
        return None
    return {
        "x": round(left_x, 3),
        "y": round(top_y, 3),
        "width": round(right_x - left_x, 3),
        "height": round(bottom_y - top_y, 3),
    }


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


def reading_order_key(page: dict[str, Any], node: dict[str, Any]) -> tuple[int, str]:
    node_id = node.get("node_id")
    order = [
        item
        for item in page.get("reading_order", [])
        if isinstance(item, str)
    ]
    try:
        return (order.index(node_id), str(node_id))
    except ValueError:
        return (len(order), str(node_id))


def barrier_sort_key(node: dict[str, Any]) -> tuple[float, float, str]:
    box = bbox(node)
    if box is None:
        return (0.0, 0.0, str(node.get("node_id", "")))
    return (box["x"], box["y"], str(node.get("node_id", "")))


def find_page_image(images_dir: Path, page_id: str) -> Path:
    candidates = sorted(images_dir.glob(f"*_{page_id}.png"))
    if not candidates:
        candidates = sorted(images_dir.glob(f"*{page_id}*.png"))
    if not candidates:
        raise FileNotFoundError(f"No PNG image found for page_id={page_id} in {images_dir}")
    return candidates[0].resolve()


def safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
