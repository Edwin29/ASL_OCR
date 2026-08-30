"""Strict LabelMe polygon loader for oracle page experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from book_scanner.detect.roi import PageSide
from book_scanner.evaluation.page_masks import read_image


_LABELS = {PageSide.LEFT: "left_page", PageSide.RIGHT: "right_page"}


@dataclass(frozen=True)
class OraclePageAnnotation:
    side: PageSide
    label: str
    points: tuple[tuple[float, float], ...]
    mask: np.ndarray
    bbox_full: tuple[int, int, int, int]
    area_px: int
    area_ratio: float
    winding: str
    touches_frame_edge: bool


@dataclass(frozen=True)
class LabelMeAnnotationSet:
    image_path: Path
    label_path: Path
    image_size: tuple[int, int]
    pages: dict[PageSide, OraclePageAnnotation]
    overlap_px: int
    diagnostics: dict[str, object]


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(a, b, c, d) -> bool:
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


def _self_intersections(points: tuple[tuple[float, float], ...]) -> list[tuple[int, int]]:
    count = len(points)
    intersections: list[tuple[int, int]] = []
    for first in range(count):
        for second in range(first + 1, count):
            if second in (first, (first + 1) % count):
                continue
            if first in (second, (second + 1) % count):
                continue
            if first == 0 and second == count - 1:
                continue
            if _segments_cross(
                points[first], points[(first + 1) % count], points[second], points[(second + 1) % count]
            ):
                intersections.append((first, second))
    return intersections


def _parse_polygon(shape: dict, width: int, height: int) -> tuple[tuple[float, float], ...]:
    if shape.get("shape_type") != "polygon":
        raise ValueError(f"label {shape.get('label')!r} must use shape_type='polygon'")
    raw_points = shape.get("points")
    if not isinstance(raw_points, list) or len(raw_points) < 3:
        raise ValueError(f"label {shape.get('label')!r} needs at least three polygon points")
    points: list[tuple[float, float]] = []
    for raw in raw_points:
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError(f"invalid point in label {shape.get('label')!r}: {raw!r}")
        x, y = float(raw[0]), float(raw[1])
        if not np.isfinite((x, y)).all() or not (0.0 <= x < width and 0.0 <= y < height):
            raise ValueError(f"point {(x, y)} in label {shape.get('label')!r} is outside {width}x{height}")
        points.append((x, y))
    parsed = tuple(points)
    intersections = _self_intersections(parsed)
    if intersections:
        raise ValueError(f"label {shape.get('label')!r} polygon self-intersects at {intersections}")
    return parsed


def load_labelme_pages(image_path: Path, label_path: Path) -> LabelMeAnnotationSet:
    image_path, label_path = Path(image_path), Path(label_path)
    image = read_image(image_path)
    height, width = image.shape[:2]
    try:
        payload = json.loads(label_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read LabelMe JSON: {label_path}") from exc

    if (int(payload.get("imageWidth", -1)), int(payload.get("imageHeight", -1))) != (width, height):
        raise ValueError(
            f"LabelMe image size {(payload.get('imageWidth'), payload.get('imageHeight'))} "
            f"does not match actual {(width, height)}"
        )
    annotated_name = Path(str(payload.get("imagePath", ""))).name
    if annotated_name and annotated_name != image_path.name:
        raise ValueError(f"LabelMe imagePath {annotated_name!r} does not match {image_path.name!r}")

    shapes_by_label: dict[str, dict] = {}
    for shape in payload.get("shapes", []):
        label = shape.get("label")
        if label in _LABELS.values():
            if label in shapes_by_label:
                raise ValueError(f"duplicate required LabelMe label: {label}")
            shapes_by_label[label] = shape

    missing = [label for label in _LABELS.values() if label not in shapes_by_label]
    if missing:
        raise ValueError(f"missing required LabelMe labels: {missing}")

    pages: dict[PageSide, OraclePageAnnotation] = {}
    total_px = width * height
    for side, label in _LABELS.items():
        points = _parse_polygon(shapes_by_label[label], width, height)
        rounded = np.rint(points).astype(np.int32)
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillPoly(mask, [rounded], 255)
        area_px = int(np.count_nonzero(mask))
        x, y, bbox_width, bbox_height = cv2.boundingRect(rounded)
        signed_area = float(cv2.contourArea(rounded.astype(np.float32), oriented=True))
        touches = bool(
            x <= 0 or y <= 0 or x + bbox_width >= width or y + bbox_height >= height
        )
        pages[side] = OraclePageAnnotation(
            side=side,
            label=label,
            points=points,
            mask=mask,
            bbox_full=(x, y, bbox_width, bbox_height),
            area_px=area_px,
            area_ratio=area_px / total_px,
            winding="counterclockwise" if signed_area > 0 else "clockwise",
            touches_frame_edge=touches,
        )

    overlap_px = int(np.count_nonzero((pages[PageSide.LEFT].mask > 0) & (pages[PageSide.RIGHT].mask > 0)))
    diagnostics = {
        "overlap_px": overlap_px,
        "overlap_ratio_full_frame": overlap_px / total_px,
        "winding_mismatch": pages[PageSide.LEFT].winding != pages[PageSide.RIGHT].winding,
        "unknown_labels": sorted(
            {str(shape.get("label")) for shape in payload.get("shapes", [])} - set(_LABELS.values())
        ),
    }
    return LabelMeAnnotationSet(
        image_path=image_path,
        label_path=label_path,
        image_size=(width, height),
        pages=pages,
        overlap_px=overlap_px,
        diagnostics=diagnostics,
    )
