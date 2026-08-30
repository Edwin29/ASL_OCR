"""Oracle-label UVDoc feasibility experiment orchestration."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
import cv2
import numpy as np

from book_scanner.annotations.labelme import LabelMeAnnotationSet, OraclePageAnnotation, load_labelme_pages
from book_scanner.correct.perspective import warp_to_rectangle
from book_scanner.correct.types import Corners
from book_scanner.correct.unwarper import PageUnwarper, UnwarpResult
from book_scanner.detect.corners import geometry_from_mask, order_corners
from book_scanner.detect.roi import PageSide
from book_scanner.evaluation.page_masks import read_image, write_image
from book_scanner.judge.quality_judge import judge_quality


@dataclass(frozen=True)
class OracleCrop:
    side: PageSide
    variant: str
    image: np.ndarray
    mask: np.ndarray
    bbox_full: tuple[int, int, int, int]


@dataclass(frozen=True)
class ArtifactRecord:
    kind: str
    path: str
    sha256: str
    size: tuple[int, int]
    quality_block_reason: str | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_commit(runtime_path: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "-C", str(runtime_path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_oracle_crops(
    frame: np.ndarray,
    annotation: OraclePageAnnotation,
    padding_fraction: float = 0.03,
    neutral_value: int | tuple[int, int, int] = 255,
) -> dict[str, OracleCrop]:
    if padding_fraction < 0:
        raise ValueError("padding_fraction must be non-negative")
    full_h, full_w = frame.shape[:2]
    x, y, width, height = annotation.bbox_full
    pad_x, pad_y = round(width * padding_fraction), round(height * padding_fraction)
    x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
    x1, y1 = min(full_w, x + width + pad_x), min(full_h, y + height + pad_y)
    bbox = (x0, y0, x1 - x0, y1 - y0)
    image = frame[y0:y1, x0:x1].copy()
    mask = annotation.mask[y0:y1, x0:x1].copy()
    neutralized = image.copy()
    neutralized[mask == 0] = neutral_value
    return {
        "bbox_original": OracleCrop(annotation.side, "bbox_original", image, mask, bbox),
        "bbox_neutralized": OracleCrop(annotation.side, "bbox_neutralized", neutralized, mask, bbox),
    }


def _overlay(frame: np.ndarray, annotation: OraclePageAnnotation) -> np.ndarray:
    result = frame.copy()
    color = (0, 200, 255) if annotation.side is PageSide.LEFT else (255, 100, 0)
    fill = np.full_like(result, color)
    selected = annotation.mask > 0
    result[selected] = cv2.addWeighted(result[selected], 0.6, fill[selected], 0.4, 0)
    points = np.rint(annotation.points).astype(np.int32)
    cv2.polylines(result, [points], True, color, 8, cv2.LINE_AA)
    return result


def _quality_reason(path: Path) -> str | None:
    try:
        reason = judge_quality(path)
        return reason.value if reason is not None else None
    except Exception as exc:
        return f"quality_check_error:{type(exc).__name__}:{exc}"


def _artifact(kind: str, path: Path, image: np.ndarray) -> ArtifactRecord:
    write_image(path, image)
    return ArtifactRecord(
        kind=kind,
        path=str(path),
        sha256=_sha256(path),
        size=(int(image.shape[1]), int(image.shape[0])),
        quality_block_reason=_quality_reason(path),
    )


def _serialize_unwarp(result: UnwarpResult) -> dict[str, object]:
    return {
        "success": result.success,
        "adapter_name": result.adapter_name,
        "device": result.device,
        "processing_ms": result.processing_ms,
        "input_size": list(result.input_size),
        "output_size": list(result.output_size) if result.output_size is not None else None,
        "reason": result.reason.value if result.reason is not None else None,
        "diagnostics": dict(result.diagnostics),
    }


def _legacy_homography(frame: np.ndarray, annotation: OraclePageAnnotation) -> np.ndarray | None:
    geometry = geometry_from_mask(annotation.mask)
    if geometry is None:
        return None
    top_left, top_right, bottom_right, bottom_left = order_corners(geometry.corners)
    return warp_to_rectangle(
        frame,
        Corners(top_left, top_right, bottom_right, bottom_left),
    )


def _thumbnail(image: np.ndarray, label: str, size: tuple[int, int] = (460, 600)) -> np.ndarray:
    cell_w, cell_h = size
    canvas = np.full((cell_h, cell_w, 3), 245, dtype=np.uint8)
    available_h = cell_h - 44
    scale = min(cell_w / image.shape[1], available_h / image.shape[0])
    resized = cv2.resize(
        image,
        (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))),
        interpolation=cv2.INTER_AREA,
    )
    y = 40 + (available_h - resized.shape[0]) // 2
    x = (cell_w - resized.shape[1]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    cv2.putText(canvas, label, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (20, 20, 20), 2, cv2.LINE_AA)
    return canvas


def _contact_sheet(rows: list[list[tuple[str, np.ndarray]]]) -> np.ndarray:
    if not rows or not any(rows):
        raise ValueError("contact sheet requires at least one image")
    cell_count = max(len(row) for row in rows)
    blank = np.full((600, 460, 3), 245, dtype=np.uint8)
    rendered_rows = []
    for row in rows:
        cells = [_thumbnail(image, label) for label, image in row]
        cells.extend(blank.copy() for _ in range(cell_count - len(cells)))
        rendered_rows.append(np.hstack(cells))
    return np.vstack(rendered_rows)


def run_oracle_unwarp_experiment(
    image_path: Path,
    label_path: Path,
    output_dir: Path,
    unwarper: PageUnwarper,
    padding_fraction: float = 0.03,
    neutral_value: int | tuple[int, int, int] = 255,
    runtime_path: Path | None = None,
    checkpoint_path: Path | None = None,
) -> dict[str, object]:
    image_path, label_path, output_dir = Path(image_path), Path(label_path), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = read_image(image_path)
    labels: LabelMeAnnotationSet = load_labelme_pages(image_path, label_path)
    raw_record = _artifact("raw", output_dir / "raw.png", frame)

    summary: dict[str, object] = {
        "input": {
            "image_path": str(image_path),
            "image_sha256": _sha256(image_path),
            "label_path": str(label_path),
            "label_sha256": _sha256(label_path),
            "image_size": list(labels.image_size),
        },
        "runtime": {
            "runtime_path": str(runtime_path) if runtime_path is not None else None,
            "runtime_commit": _runtime_commit(Path(runtime_path)) if runtime_path is not None else None,
            "checkpoint_path": str(checkpoint_path) if checkpoint_path is not None else None,
            "checkpoint_sha256": _sha256(Path(checkpoint_path))
            if checkpoint_path is not None and Path(checkpoint_path).is_file()
            else None,
        },
        "annotation_diagnostics": labels.diagnostics,
        "raw_artifact": asdict(raw_record),
        "sides": {},
    }
    contact_rows: list[list[tuple[str, np.ndarray]]] = []

    for side in (PageSide.LEFT, PageSide.RIGHT):
        annotation = labels.pages[side]
        side_dir = output_dir / side.value
        side_dir.mkdir(parents=True, exist_ok=True)
        artifacts: list[ArtifactRecord] = []
        artifacts.append(_artifact("mask", side_dir / "mask.png", annotation.mask))
        artifacts.append(_artifact("overlay", side_dir / "overlay.png", _overlay(frame, annotation)))
        crops = build_oracle_crops(frame, annotation, padding_fraction, neutral_value)
        variant_results: dict[str, object] = {}
        contact_row: list[tuple[str, np.ndarray]] = []
        for variant_name in ("bbox_original", "bbox_neutralized"):
            crop = crops[variant_name]
            crop_path = side_dir / f"{variant_name}.png"
            artifacts.append(_artifact(variant_name, crop_path, crop.image))
            contact_row.append((f"{side.value}: {variant_name}", crop.image))
            result = unwarper.unwarp(crop.image)
            result_payload = _serialize_unwarp(result)
            if result.success and result.image is not None:
                result_path = side_dir / f"uvdoc_{variant_name}.png"
                artifacts.append(_artifact(f"uvdoc_{variant_name}", result_path, result.image))
                result_payload["artifact_path"] = str(result_path)
                result_payload["artifact_sha256"] = _sha256(result_path)
                result_payload["quality_block_reason"] = _quality_reason(result_path)
                contact_row.append((f"{side.value}: uvdoc {variant_name}", result.image))
            variant_results[variant_name] = result_payload

        homography = _legacy_homography(frame, annotation)
        if homography is not None:
            artifacts.append(_artifact("legacy_homography", side_dir / "legacy_homography.png", homography))
            contact_row.append((f"{side.value}: legacy homography", homography))
        contact_rows.append(contact_row)

        side_payload = {
            "annotation": {
                "label": annotation.label,
                "bbox_full": list(annotation.bbox_full),
                "area_px": annotation.area_px,
                "area_ratio": annotation.area_ratio,
                "winding": annotation.winding,
                "touches_frame_edge": annotation.touches_frame_edge,
            },
            "variants": variant_results,
            "artifacts": [asdict(record) for record in artifacts],
        }
        (side_dir / "metadata.json").write_text(
            json.dumps(side_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary["sides"][side.value] = side_payload

    sheet = _contact_sheet(contact_rows)
    sheet_record = _artifact("contact_sheet", output_dir / "contact_sheet.png", sheet)
    summary["contact_sheet"] = asdict(sheet_record)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
