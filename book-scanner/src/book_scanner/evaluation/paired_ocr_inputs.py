"""Reproducible image inputs for the staged paired OCR experiment.

This module is deliberately offline.  It does not change the capture session,
quality judge, document-parser production source, or transmission path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from book_scanner.annotations.labelme import load_labelme_pages
from book_scanner.correct.coarse_perspective import warp_from_mask
from book_scanner.correct.postprocess import LuminanceUnsharpPostprocessor
from book_scanner.correct.uvdoc_adapter import UVDocAdapter
from book_scanner.detect.contrast_spatial import ContrastSpatialPageSegmenter
from book_scanner.detect.roi import ROIConfig, PageSide
from book_scanner.detect.spine_seam import LuminanceValleySeamDetector, SpineSeamConfig, apply_seam_ownership
from book_scanner.evaluation.fallback_assessment import assess_fixed_layout_fallback
from book_scanner.evaluation.ocr_ab_experiment import image_quality_metrics
from book_scanner.evaluation.page_masks import read_image, write_image
from book_scanner.evaluation.seam_experiment import extract_full_page_masks
from book_scanner.evaluation.unwarp_experiment import build_oracle_crops


LABELED_CAPTURES = ("20260826_174943", "20260826_174953", "20260826_174958", "20260826_175109")
CONTROL_CAPTURE = "20260826_175110"
FALLBACK_STRESS_CAPTURES = (
    "20260826_175116", "20260826_175119", "20260826_175120", "20260826_175126",
    "20260826_175130", "20260826_175153", "20260826_175200",
)
EXTRACTION_VARIANTS = (
    "oracle", "overlap", "seam_confirmed", "seam_conservative",
)


@dataclass(frozen=True)
class CropResult:
    image: np.ndarray
    mask: np.ndarray
    bbox_full: tuple[int, int, int, int]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_id(capture: str, side: str, extraction: str, geometry: str, postprocess: str) -> str:
    return f"{capture}_{side}_{extraction}_{geometry}_{postprocess}"


def crop_with_mask(frame: np.ndarray, mask: np.ndarray, padding_fraction: float = 0.03) -> CropResult | None:
    """Crop an image and its full-frame mask using one round-trippable bbox."""
    points = cv2.findNonZero(np.where(mask > 0, 255, 0).astype(np.uint8))
    if points is None:
        return None
    x, y, width, height = cv2.boundingRect(points)
    px, py = round(width * padding_fraction), round(height * padding_fraction)
    x0, y0 = max(0, x - px), max(0, y - py)
    x1, y1 = min(frame.shape[1], x + width + px), min(frame.shape[0], y + height + py)
    return CropResult(
        frame[y0:y1, x0:x1].copy(),
        mask[y0:y1, x0:x1].copy(),
        (x0, y0, x1 - x0, y1 - y0),
    )


def _write_artifact(
    output_dir: Path,
    *,
    capture: str,
    side: PageSide,
    extraction: str,
    geometry: str,
    postprocess: str,
    crop: CropResult,
    source: dict[str, object],
    fallback: dict[str, object],
    processing: dict[str, object] | None = None,
) -> dict[str, object]:
    identifier = artifact_id(capture, side.value, extraction, geometry, postprocess)
    image_path = output_dir / "images" / f"{identifier}.png"
    mask_path = output_dir / "masks" / f"{identifier}.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    write_image(image_path, crop.image)
    write_image(mask_path, crop.mask)
    selected = int(np.count_nonzero(crop.mask))
    processing_payload = processing or {"warp_count": 0, "interpolation": "none"}
    direct_round_trip = int(processing_payload.get("warp_count", 0)) == 0
    return {
        "artifact_id": identifier,
        "status": "READY",
        "capture": capture,
        "side": side.value,
        "extraction": extraction,
        "geometry": geometry,
        "postprocess": postprocess,
        "image_path": str(image_path.resolve()),
        "image_sha256": sha256_file(image_path),
        "mask_path": str(mask_path.resolve()),
        "mask_sha256": sha256_file(mask_path),
        "bbox_full": list(crop.bbox_full),
        "full_frame_round_trip": {
            "local_origin_full": list(crop.bbox_full[:2]),
            "source_crop_size": list(crop.bbox_full[2:]),
            "artifact_size": [int(crop.image.shape[1]), int(crop.image.shape[0])],
            "direct_pixel_round_trip": direct_round_trip,
            "note": None if direct_round_trip else "Warped pixels require the recorded transform/grid; bbox is source lineage.",
        },
        "mask_coverage": selected / max(1, crop.mask.size),
        "background_ratio": 1.0 - selected / max(1, crop.mask.size),
        "quality_metrics": image_quality_metrics(crop.image),
        "source": source,
        "fallback": fallback,
        "processing": processing_payload,
    }


def _fallback_payload(assessment) -> dict[str, object]:
    return {
        "accepted": assessment.accepted,
        "reasons": list(assessment.reasons),
        "sides": {key: asdict(value) for key, value in assessment.sides.items()},
        "diagnostics": dict(assessment.diagnostics),
    }


def _automatic_state(frame: np.ndarray):
    masks, _artifacts, extraction = extract_full_page_masks(
        frame,
        ContrastSpatialPageSegmenter(),
        ROIConfig(spine_overlap_fraction=0.06),
    )
    fallback = assess_fixed_layout_fallback(frame, masks)
    detected = LuminanceValleySeamDetector(
        SpineSeamConfig(centerline_fraction=0.5, uncertainty_band_px=8)
    ).detect(frame, masks[PageSide.LEFT], masks[PageSide.RIGHT])
    ownership = (
        apply_seam_ownership(masks[PageSide.LEFT], masks[PageSide.RIGHT], detected.seam, "union-preserving")
        if detected.seam is not None else None
    )
    return masks, extraction, fallback, detected, ownership


def prepare_extraction_manifest(
    image_dir: Path,
    output_dir: Path,
    captures: Iterable[str] = LABELED_CAPTURES,
    padding_fraction: float = 0.03,
    *,
    sides: Iterable[PageSide] = tuple(PageSide),
    extraction_variants: Iterable[str] = EXTRACTION_VARIANTS,
    control_capture: str | None = CONTROL_CAPTURE,
    fallback_stress_captures: Iterable[str] = FALLBACK_STRESS_CAPTURES,
    oracle_independent_of_automatic: bool = False,
    automatic_gate_scope: str = "spread",
) -> dict[str, object]:
    """Generate Phase A artifacts and explicit fallback skip records."""
    image_dir, output_dir = Path(image_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    capture_list = tuple(captures)
    selected_sides = tuple(PageSide(side) for side in sides)
    selected_extractions = tuple(str(value) for value in extraction_variants)
    unknown_extractions = sorted(set(selected_extractions) - set(EXTRACTION_VARIANTS))
    if unknown_extractions:
        raise ValueError(f"unsupported extraction variants: {unknown_extractions}")
    if automatic_gate_scope not in {"spread", "selected_sides"}:
        raise ValueError(f"unsupported automatic gate scope: {automatic_gate_scope}")
    fallback_capture_list = tuple(fallback_stress_captures)
    records: list[dict[str, object]] = []
    fallback_records: list[dict[str, object]] = []
    configs = {
        "padding_fraction": padding_fraction,
        "sides": [side.value for side in selected_sides],
        "extraction_variants": list(selected_extractions),
        "oracle_independent_of_automatic": oracle_independent_of_automatic,
        "automatic_gate_scope": automatic_gate_scope,
        "roi": asdict(ROIConfig(spine_overlap_fraction=0.06)),
        "segmenter": asdict(ContrastSpatialPageSegmenter().config),
        "seam": asdict(SpineSeamConfig(centerline_fraction=0.5, uncertainty_band_px=8)),
        "ownership_policy": "union-preserving",
    }

    for capture in capture_list:
        image_path, label_path = image_dir / f"{capture}.jpg", image_dir / f"{capture}.json"
        frame = read_image(image_path)
        labels = load_labelme_pages(image_path, label_path)
        masks, extraction_diag, fallback, detected, ownership = _automatic_state(frame)
        fallback_payload = _fallback_payload(fallback)
        selected_sides_accepted = all(
            fallback.sides.get(side.value) is not None and fallback.sides[side.value].accepted
            for side in selected_sides
        ) if fallback.sides else fallback.accepted
        fallback_gate_accepted = fallback.accepted if automatic_gate_scope == "spread" else selected_sides_accepted
        automatic_ready = fallback_gate_accepted and detected.seam is not None and ownership is not None
        if not automatic_ready and oracle_independent_of_automatic and "oracle" in selected_extractions:
            for side in selected_sides:
                annotation = labels.pages[side]
                oracle = build_oracle_crops(frame, annotation, padding_fraction)["bbox_original"]
                records.append(_write_artifact(
                    output_dir,
                    capture=capture,
                    side=side,
                    extraction="oracle",
                    geometry="none",
                    postprocess="none",
                    crop=CropResult(oracle.image, oracle.mask, oracle.bbox_full),
                    source={
                        "image_path": str(image_path.resolve()),
                        "image_sha256": sha256_file(image_path),
                        "label_path": str(label_path.resolve()),
                        "label_sha256": sha256_file(label_path),
                        "mask_provenance": "labelme_oracle",
                        "extraction_diagnostics": extraction_diag,
                        "seam_confidence": detected.seam.confidence if detected.seam is not None else None,
                        "seam_method": detected.seam.method if detected.seam is not None else None,
                        "ownership_diagnostics": dict(ownership.diagnostics) if ownership is not None else {},
                        "label_metrics": {
                            "own_page_recall": 1.0,
                            "opposite_page_inclusion_px": 0,
                            "opposite_page_inclusion_ratio": 0.0,
                        },
                    },
                    fallback=fallback_payload,
                ))
        if not fallback_gate_accepted:
            scoped_reasons = list(fallback.reasons)
            if automatic_gate_scope == "selected_sides":
                scoped_reasons = [
                    f"{side.value}:{reason}"
                    for side in selected_sides
                    for reason in fallback.sides[side.value].reasons
                ]
            fallback_records.append({
                "capture": capture,
                "status": "SKIPPED_FALLBACK_" + "__".join(scoped_reasons),
                "automatic_gate_scope": automatic_gate_scope,
                "fallback": fallback_payload,
            })
            continue
        if detected.seam is None or ownership is None:
            fallback_records.append({
                "capture": capture,
                "status": f"SKIPPED_SEAM_{detected.reason or 'UNKNOWN'}",
                "fallback": fallback_payload,
                "seam_diagnostics": dict(detected.diagnostics),
            })
            continue
        for side in selected_sides:
            oracle = build_oracle_crops(frame, labels.pages[side], padding_fraction)["bbox_original"]
            confirmed_mask = ownership.left_mask if side is PageSide.LEFT else ownership.right_mask
            conservative_mask = (
                ownership.left_conservative_mask if side is PageSide.LEFT else ownership.right_conservative_mask
            )
            crop_sources = {
                "oracle": (CropResult(oracle.image, oracle.mask, oracle.bbox_full), labels.pages[side].mask),
                "overlap": (crop_with_mask(frame, masks[side], padding_fraction), masks[side]),
                "seam_confirmed": (crop_with_mask(frame, confirmed_mask, padding_fraction), confirmed_mask),
                "seam_conservative": (crop_with_mask(frame, conservative_mask, padding_fraction), conservative_mask),
            }
            for extraction_name in selected_extractions:
                crop, full_mask = crop_sources[extraction_name]
                if crop is None:
                    records.append({
                        "artifact_id": artifact_id(capture, side.value, extraction_name, "none", "none"),
                        "status": "FAILED_EMPTY_MASK",
                        "capture": capture,
                        "side": side.value,
                        "extraction": extraction_name,
                    })
                    continue
                truth = labels.pages[side].mask > 0
                opposite = labels.pages[PageSide.RIGHT if side is PageSide.LEFT else PageSide.LEFT].mask > 0
                selected = full_mask > 0
                truth_count, selected_count = int(np.count_nonzero(truth)), int(np.count_nonzero(selected))
                source = {
                    "image_path": str(image_path.resolve()),
                    "image_sha256": sha256_file(image_path),
                    "label_path": str(label_path.resolve()) if extraction_name == "oracle" else None,
                    "label_sha256": sha256_file(label_path) if extraction_name == "oracle" else None,
                    "mask_provenance": "labelme_oracle" if extraction_name == "oracle" else "automatic_seam",
                    "extraction_diagnostics": extraction_diag,
                    "seam_confidence": detected.seam.confidence,
                    "seam_method": detected.seam.method,
                    "ownership_diagnostics": dict(ownership.diagnostics),
                    "automatic_gate_scope": automatic_gate_scope,
                    "selected_sides_accepted": selected_sides_accepted,
                    "label_metrics": {
                        "own_page_recall": int(np.count_nonzero(selected & truth)) / max(1, truth_count),
                        "opposite_page_inclusion_px": int(np.count_nonzero(selected & opposite & ~truth)),
                        "opposite_page_inclusion_ratio": (
                            int(np.count_nonzero(selected & opposite & ~truth)) / max(1, selected_count)
                        ),
                    },
                }
                records.append(_write_artifact(
                    output_dir,
                    capture=capture,
                    side=side,
                    extraction=extraction_name,
                    geometry="none",
                    postprocess="none",
                    crop=crop,
                    source=source,
                    fallback=fallback_payload,
                ))

    # Unlabelled images are fallback/control diagnostics only.  They never get
    # silently included in the labeled paired denominator.
    diagnostic_captures = (() if control_capture is None else (control_capture,)) + fallback_capture_list
    for capture in diagnostic_captures:
        image_path = image_dir / f"{capture}.jpg"
        frame = read_image(image_path)
        masks, extraction_diag, fallback, detected, ownership = _automatic_state(frame)
        fallback_payload = _fallback_payload(fallback)
        status = "AUTOMATIC_CONTROL_READY" if fallback.accepted and ownership is not None else (
            "SKIPPED_FALLBACK_" + "__".join(fallback.reasons)
            if not fallback.accepted else f"SKIPPED_SEAM_{detected.reason or 'UNKNOWN'}"
        )
        record: dict[str, object] = {
            "capture": capture,
            "status": status,
            "image_path": str(image_path.resolve()),
            "image_sha256": sha256_file(image_path),
            "fallback": fallback_payload,
            "extraction_diagnostics": extraction_diag,
        }
        if status == "AUTOMATIC_CONTROL_READY":
            record["artifacts"] = []
            for side in selected_sides:
                mask = ownership.left_conservative_mask if side is PageSide.LEFT else ownership.right_conservative_mask
                crop = crop_with_mask(frame, mask, padding_fraction)
                if crop is not None:
                    artifact = _write_artifact(
                        output_dir, capture=capture, side=side, extraction="seam_conservative",
                        geometry="none", postprocess="none", crop=crop,
                        source={"image_path": str(image_path.resolve()), "image_sha256": sha256_file(image_path),
                                "label_path": None, "label_sha256": None,
                                "mask_provenance": "automatic_seam_control"},
                        fallback=fallback_payload,
                    )
                    record["artifacts"].append(artifact)
        fallback_records.append(record)

    manifest = {
        "schema_version": 1,
        "phase": "extraction",
        "status": "PREPARED",
        "configs": configs,
        "labeled_capture_count": len(capture_list),
        "artifacts": records,
        "fallback_records": fallback_records,
    }
    path = output_dir / "extraction_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def prepare_geometry_manifest(
    extraction_manifest_path: Path,
    output_dir: Path,
    uvdoc: UVDocAdapter,
    *,
    sides: Iterable[PageSide] = tuple(PageSide),
    extractions: Iterable[str] = ("oracle", "seam_conservative"),
) -> dict[str, object]:
    """Generate Phase B coarse and UVDoc artifacts from two fixed anchors."""
    extraction_manifest_path, output_dir = Path(extraction_manifest_path), Path(output_dir)
    base = json.loads(extraction_manifest_path.read_text(encoding="utf-8"))
    selected_sides = {PageSide(side).value for side in sides}
    selected_extractions = {str(value) for value in extractions}
    records: list[dict[str, object]] = []
    for source in base.get("artifacts", []):
        if (
            source.get("status") != "READY"
            or source.get("extraction") not in selected_extractions
            or source.get("side") not in selected_sides
        ):
            continue
        image = read_image(Path(source["image_path"]))
        mask = cv2.imread(str(source["mask_path"]), cv2.IMREAD_GRAYSCALE)
        crop = CropResult(image, mask, tuple(int(value) for value in source["bbox_full"]))
        records.append({**source, "phase_b_control_reused": True})

        coarse = warp_from_mask(image, mask)
        if coarse.success:
            records.append(_write_artifact(
                output_dir, capture=source["capture"], side=PageSide(source["side"]),
                extraction=source["extraction"], geometry="coarse", postprocess="none",
                crop=CropResult(coarse.image, coarse.mask, crop.bbox_full), source=source["source"],
                fallback=source["fallback"],
                processing={"warp_count": 1, "interpolation": "INTER_LINEAR(image), INTER_NEAREST(mask)",
                            "coarse": coarse.diagnostics},
            ))
        else:
            records.append({
                "artifact_id": artifact_id(source["capture"], source["side"], source["extraction"], "coarse", "none"),
                "status": f"FAILED_COARSE_{coarse.reason}", "processing": coarse.diagnostics,
            })

        unwarped = uvdoc.unwarp_with_mode(image, "bilinear")
        if unwarped.success and unwarped.image is not None:
            records.append(_write_artifact(
                output_dir, capture=source["capture"], side=PageSide(source["side"]),
                extraction=source["extraction"], geometry="uvdoc_bilinear", postprocess="none",
                crop=CropResult(unwarped.image, mask, crop.bbox_full), source=source["source"],
                fallback=source["fallback"],
                processing={"warp_count": 1, "interpolation": "bilinear", "uvdoc": {
                    "adapter": unwarped.adapter_name, "device": unwarped.device,
                    "processing_ms": unwarped.processing_ms, "input_size": list(unwarped.input_size),
                    "output_size": list(unwarped.output_size or ()), "diagnostics": dict(unwarped.diagnostics),
                }, "mask_coordinate_space": "source_crop_unwarped_lineage_only"},
            ))
        else:
            records.append({
                "artifact_id": artifact_id(source["capture"], source["side"], source["extraction"],
                                           "uvdoc_bilinear", "none"),
                "status": f"FAILED_UVDOC_{unwarped.reason.value if unwarped.reason else 'UNKNOWN'}",
                "processing": dict(unwarped.diagnostics),
            })
    manifest = {
        "schema_version": 1, "phase": "geometry", "status": "PREPARED",
        "source_manifest": str(extraction_manifest_path.resolve()),
        "sides": sorted(selected_sides), "extractions": sorted(selected_extractions),
        "uvdoc_load_count": uvdoc.load_count, "artifacts": records,
    }
    (output_dir / "geometry_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def prepare_postprocess_manifest(
    geometry_manifest_path: Path,
    output_dir: Path,
    selected_artifact_ids: Iterable[str],
    uvdoc: UVDocAdapter,
) -> dict[str, object]:
    """Prepare only the two gated Phase C screening inputs and their controls."""
    geometry_manifest_path, output_dir = Path(geometry_manifest_path), Path(output_dir)
    selected_artifact_ids = list(selected_artifact_ids)
    geometry = json.loads(geometry_manifest_path.read_text(encoding="utf-8"))
    by_id = {str(item.get("artifact_id")): item for item in geometry.get("artifacts", [])}
    records: list[dict[str, object]] = []
    postprocessor = LuminanceUnsharpPostprocessor()
    for identifier in selected_artifact_ids:
        source = by_id.get(str(identifier))
        if not source or source.get("status") != "READY":
            records.append({"artifact_id": str(identifier), "status": "FAILED_SCREENING_SOURCE_NOT_READY"})
            continue
        records.append({**source, "screening_anchor_id": source["artifact_id"], "phase_c_control_reused": True})
        image = read_image(Path(source["image_path"]))
        mask = cv2.imread(str(source["mask_path"]), cv2.IMREAD_GRAYSCALE)
        bbox = tuple(int(value) for value in source["bbox_full"])
        sharpened = postprocessor.apply(image)
        if sharpened.success and sharpened.image is not None:
            record = _write_artifact(
                output_dir, capture=source["capture"], side=PageSide(source["side"]),
                extraction=source["extraction"], geometry=source["geometry"],
                postprocess="luminance_unsharp_fixed",
                crop=CropResult(sharpened.image, mask, bbox), source=source["source"],
                fallback=source["fallback"],
                processing={**source["processing"], "postprocess": dict(sharpened.diagnostics)},
            )
            record["screening_anchor_id"] = source["artifact_id"]
            records.append(record)
        else:
            records.append({
                "artifact_id": artifact_id(source["capture"], source["side"], source["extraction"],
                                           source["geometry"], "luminance_unsharp_fixed"),
                "status": f"FAILED_POSTPROCESS_{sharpened.reason}",
            })

        if source["geometry"] == "uvdoc_bilinear":
            base_id = artifact_id(source["capture"], source["side"], source["extraction"], "none", "none")
            base = by_id.get(base_id)
            if base and base.get("status") == "READY":
                base_image = read_image(Path(base["image_path"]))
                base_mask = cv2.imread(str(base["mask_path"]), cv2.IMREAD_GRAYSCALE)
                bicubic = uvdoc.unwarp_with_mode(base_image, "bicubic")
                if bicubic.success and bicubic.image is not None:
                    record = _write_artifact(
                        output_dir, capture=source["capture"], side=PageSide(source["side"]),
                        extraction=source["extraction"], geometry="uvdoc_bicubic", postprocess="none",
                        crop=CropResult(bicubic.image, base_mask, tuple(base["bbox_full"])),
                        source=base["source"], fallback=base["fallback"],
                        processing={"warp_count": 1, "interpolation": "bicubic",
                                    "mask_coordinate_space": "source_crop_unwarped_lineage_only",
                                    "uvdoc": {"processing_ms": bicubic.processing_ms,
                                              "diagnostics": dict(bicubic.diagnostics)}},
                    )
                    record["screening_anchor_id"] = source["artifact_id"]
                    records.append(record)
    manifest = {
        "schema_version": 1, "phase": "postprocess", "status": "SCREENING_PREPARED",
        "source_manifest": str(geometry_manifest_path.resolve()),
        "selected_artifact_ids": list(selected_artifact_ids),
        "full_batch_allowed": False, "uvdoc_load_count": uvdoc.load_count, "artifacts": records,
    }
    (output_dir / "postprocess_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
