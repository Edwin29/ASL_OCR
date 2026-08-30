"""Opt-in LabelMe draft export; generated polygons are never ground truth."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from book_scanner.detect.page_mask import build_page_mask
from book_scanner.detect.roi import ROIConfig, PageSide, extract_page_rois
from book_scanner.detect.segmenter import PageSegmenter
from book_scanner.evaluation.page_masks import read_image, write_image


def export_labelme_draft(
    image_path: Path,
    output_json: Path,
    segmenter: PageSegmenter,
    roi_config: ROIConfig = ROIConfig(spine_overlap_fraction=0.06),
    overwrite: bool = False,
) -> dict[str, object]:
    image_path, output_json = Path(image_path), Path(output_json)
    if output_json.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing label: {output_json}")
    frame = read_image(image_path)
    height, width = frame.shape[:2]
    shapes, generated_masks = [], {}
    for side, roi in extract_page_rois(frame, roi_config).items():
        page = build_page_mask(roi, segmenter.segment(roi))
        if page is None:
            continue
        contours, _ = cv2.findContours(page.mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contour = max(contours, key=cv2.contourArea)
        tolerance = max(1.0, cv2.arcLength(contour, True) * 0.002)
        polygon = cv2.approxPolyDP(contour, tolerance, True)[:, 0, :]
        ox, oy = roi.origin
        points = [[float(x + ox), float(y + oy)] for x, y in polygon]
        shapes.append({
            "label": f"{side.value}_page",
            "points": points,
            "group_id": None,
            "description": "AUTO-GENERATED DRAFT — requires human review",
            "shape_type": "polygon",
            "flags": {"auto_generated": True, "human_verified": False},
        })
        full_mask = np.zeros((height, width), dtype=np.uint8)
        roi_w, roi_h = roi.size
        full_mask[oy : oy + roi_h, ox : ox + roi_w] = np.maximum(
            full_mask[oy : oy + roi_h, ox : ox + roi_w], page.mask
        )
        generated_masks[side.value] = full_mask
    source_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
    payload = {
        "version": "5.5.0",
        "flags": {},
        "shapes": shapes,
        "imagePath": image_path.name,
        "imageData": None,
        "imageHeight": height,
        "imageWidth": width,
        "_book_scanner_draft": {
            "auto_generated": True,
            "human_verified": False,
            "generator": getattr(segmenter, "name", type(segmenter).__name__),
            "source_sha256": source_hash,
            "roi_config": {
                "centerline_fraction": roi_config.centerline_fraction,
                "spine_overlap_fraction": roi_config.spine_overlap_fraction,
            },
        },
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for side, mask in generated_masks.items():
        write_image(output_json.with_name(f"{output_json.stem}_{side}_draft_mask.png"), mask)
    return payload
