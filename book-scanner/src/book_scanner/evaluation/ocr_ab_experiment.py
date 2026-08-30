"""Oracle-page UVDoc, conservative sharpening, and OCR A/B orchestration."""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import time
from dataclasses import asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from book_scanner.annotations.labelme import load_labelme_pages
from book_scanner.correct.postprocess import ImagePostprocessor, LuminanceUnsharpPostprocessor
from book_scanner.correct.uvdoc_adapter import UVDocAdapter
from book_scanner.detect.roi import PageSide
from book_scanner.evaluation.page_masks import read_image, write_image
from book_scanner.evaluation.unwarp_experiment import (
    _contact_sheet,
    _legacy_homography,
    _overlay,
    build_oracle_crops,
)


VARIANT_NAMES = (
    "crop_original_control",
    "legacy_homography_control",
    "uvdoc_bilinear_original",
    "uvdoc_bilinear_neutralized",
    "uvdoc_bicubic_original",
    "uvdoc_bicubic_neutralized",
    "uvdoc_unsharp_original",
    "uvdoc_unsharp_neutralized",
)


class GeneralOcrAdapter(Protocol):
    engine_id: str
    engine_version: str

    @property
    def cache_signature(self) -> str:
        ...

    def recognize(self, image):
        ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_quality_metrics(image: np.ndarray, proxy_long_edge: int = 1600) -> dict[str, object]:
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3 or image.size == 0:
        raise ValueError("quality metrics require a non-empty HxWx3 image")

    def measurements(candidate: np.ndarray) -> dict[str, float]:
        gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY).astype(np.float32)
        laplacian = cv2.Laplacian(gray, cv2.CV_32F)
        sobel_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        return {
            "laplacian_variance": float(np.var(laplacian)),
            "tenengrad_mean": float(np.mean(sobel_x * sobel_x + sobel_y * sobel_y)),
        }

    height, width = image.shape[:2]
    margin_y, margin_x = max(1, round(height * 0.05)), max(1, round(width * 0.05))
    inner = image[margin_y : height - margin_y, margin_x : width - margin_x]
    if inner.size == 0:
        inner = image
    scale = min(1.0, proxy_long_edge / max(width, height))
    proxy = cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    return {
        "size": [width, height],
        "aspect_ratio": width / height,
        "full": measurements(image),
        "inner_5_percent": measurements(inner),
        "proxy_long_edge": max(proxy.shape[:2]),
        "proxy_1600": measurements(proxy),
    }


def ocr_result_metrics(result, page: dict[str, object], processing_ms: float) -> dict[str, object]:
    confidences = [float(token.confidence) for token in result.tokens]
    low_count = sum(value < 0.5 for value in confidences)
    ordered_text = "\n".join(
        str(node.get("normalized_text", ""))
        for node in page.get("nodes", [])
        if isinstance(node, dict)
    )
    normalized_text = normalize_ocr_text(ordered_text)
    return {
        "token_count": len(result.tokens),
        "non_whitespace_character_count": sum(not char.isspace() for char in ordered_text),
        "mean_confidence": statistics.fmean(confidences) if confidences else None,
        "median_confidence": statistics.median(confidences) if confidences else None,
        "min_confidence": min(confidences) if confidences else None,
        "p10_confidence": float(np.percentile(confidences, 10)) if confidences else None,
        "low_confidence_count": low_count,
        "low_confidence_rate": low_count / len(confidences) if confidences else None,
        "ocr_processing_ms": processing_ms,
        "normalized_text": normalized_text,
        "issue_codes": [
            str(issue.get("code"))
            for issue in page.get("parse_issues", [])
            if isinstance(issue, dict) and issue.get("code")
        ],
    }


def normalize_ocr_text(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def text_similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def _unwarp_payload(result) -> dict[str, object]:
    return {
        "success": result.success,
        "reason": result.reason.value if result.reason is not None else None,
        "processing_ms": result.processing_ms,
        "input_size": list(result.input_size),
        "output_size": list(result.output_size) if result.output_size else None,
        "diagnostics": dict(result.diagnostics),
    }


def build_page_variants(
    frame: np.ndarray,
    annotation,
    unwarper: UVDocAdapter,
    postprocessor: ImagePostprocessor | None = None,
    padding_fraction: float = 0.03,
) -> dict[str, dict[str, object]]:
    postprocessor = postprocessor or LuminanceUnsharpPostprocessor()
    crops = build_oracle_crops(frame, annotation, padding_fraction=padding_fraction)
    variants: dict[str, dict[str, object]] = {
        "crop_original_control": {
            "success": True,
            "image": crops["bbox_original"].image,
            "source": "bbox_original",
            "diagnostics": {"bbox_full": list(crops["bbox_original"].bbox_full)},
        }
    }
    homography = _legacy_homography(frame, annotation)
    variants["legacy_homography_control"] = {
        "success": homography is not None,
        "image": homography,
        "source": "oracle_mask_min_area_rect",
        "reason": None if homography is not None else "homography_failed",
        "diagnostics": {},
    }

    bilinear_results: dict[str, object] = {}
    for background_policy, crop_name in (
        ("original", "bbox_original"),
        ("neutralized", "bbox_neutralized"),
    ):
        crop = crops[crop_name]
        for sampling_mode in ("bilinear", "bicubic"):
            name = f"uvdoc_{sampling_mode}_{background_policy}"
            result = unwarper.unwarp_with_mode(crop.image, sampling_mode)
            variants[name] = {
                "success": result.success,
                "image": result.image,
                "source": crop_name,
                "reason": result.reason.value if result.reason else None,
                "diagnostics": _unwarp_payload(result),
            }
            if sampling_mode == "bilinear":
                bilinear_results[background_policy] = result

    for background_policy, result in bilinear_results.items():
        name = f"uvdoc_unsharp_{background_policy}"
        if not result.success or result.image is None:
            variants[name] = {
                "success": False,
                "image": None,
                "source": f"uvdoc_bilinear_{background_policy}",
                "reason": "upstream_unwarp_failed",
                "diagnostics": {},
            }
            continue
        processed = postprocessor.apply(result.image)
        variants[name] = {
            "success": processed.success,
            "image": processed.image,
            "source": f"uvdoc_bilinear_{background_policy}",
            "reason": processed.reason,
            "diagnostics": {
                "processor_name": processed.processor_name,
                "processing_ms": processed.processing_ms,
                **dict(processed.diagnostics),
            },
        }
    return variants


def _engine_signature(adapter: GeneralOcrAdapter) -> str:
    signature = getattr(adapter, "cache_signature", "")
    return f"{adapter.engine_id}:{adapter.engine_version}:{signature}"


def _cached_record(path: Path, image_sha256: str, engine_signature: str) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("image_sha256") != image_sha256 or payload.get("engine_signature") != engine_signature:
        return None
    payload["cache_hit"] = True
    return payload


def run_ocr_for_artifact(
    image_path: Path,
    page_id: str,
    record_path: Path,
    adapter: GeneralOcrAdapter,
    builder=None,
) -> dict[str, object]:
    from document_parser.ingest import ImageIngestor
    from document_parser.serialization.text_ir import TextOnlyPageIrBuilder

    ingestor = ImageIngestor()
    image_document = ingestor.load(image_path, page_id=page_id)
    signature = _engine_signature(adapter)
    cached = _cached_record(record_path, image_document.sha256, signature)
    if cached is not None:
        return cached

    builder = builder or TextOnlyPageIrBuilder(adapter=adapter)
    quality = builder.quality_gate.evaluate_path(image_path, page_id=page_id)
    started = time.perf_counter()
    result = adapter.recognize(image_document)
    elapsed = (time.perf_counter() - started) * 1000.0
    page = builder.build_page(image_document, quality, result)
    payload = {
        "page_id": page_id,
        "image_path": str(image_path),
        "image_sha256": image_document.sha256,
        "engine_signature": signature,
        "engine_id": result.engine_id,
        "engine_version": result.engine_version,
        "cache_hit": False,
        "ocr_result": result.to_jsonable(),
        "page_ir_page": page,
        "metrics": ocr_result_metrics(result, page, elapsed),
    }
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def draw_ocr_overlay(image: np.ndarray, record: dict[str, object]) -> np.ndarray:
    overlay = image.copy()
    ocr_result = record.get("ocr_result")
    tokens = ocr_result.get("tokens", []) if isinstance(ocr_result, dict) else []
    for token in tokens:
        if not isinstance(token, dict) or not isinstance(token.get("bbox"), dict):
            continue
        bbox = token["bbox"]
        x = round(float(bbox.get("x", 0)))
        y = round(float(bbox.get("y", 0)))
        width = round(float(bbox.get("width", 0)))
        height = round(float(bbox.get("height", 0)))
        confidence = float(token.get("confidence", 0))
        color = (0, 180, 0) if confidence >= 0.5 else (0, 0, 255)
        cv2.rectangle(overlay, (x, y), (x + width, y + height), color, max(1, round(image.shape[1] / 800)))
    return overlay


def aggregate_variant(records: list[dict[str, object]]) -> dict[str, object]:
    successful = [record for record in records if isinstance(record.get("metrics"), dict)]
    confidences = []
    total_tokens = total_chars = low_count = 0
    total_ocr_ms = 0.0
    for record in successful:
        result = record.get("ocr_result", {})
        tokens = result.get("tokens", []) if isinstance(result, dict) else []
        confidences.extend(float(token["confidence"]) for token in tokens if isinstance(token, dict))
        metrics = record["metrics"]
        total_tokens += int(metrics["token_count"])
        total_chars += int(metrics["non_whitespace_character_count"])
        low_count += int(metrics["low_confidence_count"])
        total_ocr_ms += float(metrics["ocr_processing_ms"])
    return {
        "page_count": len(successful),
        "token_count": total_tokens,
        "non_whitespace_character_count": total_chars,
        "mean_confidence": statistics.fmean(confidences) if confidences else None,
        "median_confidence": statistics.median(confidences) if confidences else None,
        "p10_confidence": float(np.percentile(confidences, 10)) if confidences else None,
        "low_confidence_count": low_count,
        "low_confidence_rate": low_count / total_tokens if total_tokens else None,
        "ocr_processing_ms": total_ocr_ms,
        "cache_hit_count": sum(bool(record.get("cache_hit")) for record in successful),
    }


def paired_capture_similarities(records_by_variant: dict[str, list[dict[str, object]]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for variant, records in records_by_variant.items():
        by_page = {str(record.get("page_id")): record for record in records}
        sides = {}
        for side in ("left", "right"):
            left = by_page.get(f"20260826_174943_{side}")
            right = by_page.get(f"20260826_174953_{side}")
            if left is None or right is None:
                continue
            left_text = str(left.get("metrics", {}).get("normalized_text", ""))
            right_text = str(right.get("metrics", {}).get("normalized_text", ""))
            sides[side] = text_similarity(left_text, right_text)
        result[variant] = sides
    return result


def screen_candidate(
    candidate_records: list[dict[str, object]],
    control_records: list[dict[str, object]],
) -> dict[str, object]:
    candidate = aggregate_variant(candidate_records)
    control = aggregate_variant(control_records)
    by_candidate = {str(item.get("page_id")): item for item in candidate_records}
    by_control = {str(item.get("page_id")): item for item in control_records}
    page_char_drops = []
    for page_id in sorted(set(by_candidate) & set(by_control)):
        candidate_chars = int(by_candidate[page_id].get("metrics", {}).get("non_whitespace_character_count", 0))
        control_chars = int(by_control[page_id].get("metrics", {}).get("non_whitespace_character_count", 0))
        drop = (control_chars - candidate_chars) / control_chars if control_chars else 0.0
        page_char_drops.append({"page_id": page_id, "drop_ratio": drop})

    candidate_chars = int(candidate["non_whitespace_character_count"])
    control_chars = int(control["non_whitespace_character_count"])
    char_ratio = candidate_chars / control_chars if control_chars else 1.0
    candidate_low = candidate["low_confidence_rate"]
    control_low = control["low_confidence_rate"]
    low_delta = (
        float(candidate_low) - float(control_low)
        if candidate_low is not None and control_low is not None
        else None
    )
    candidate_mean = candidate["mean_confidence"]
    control_mean = control["mean_confidence"]
    mean_delta = (
        float(candidate_mean) - float(control_mean)
        if candidate_mean is not None and control_mean is not None
        else None
    )
    checks = {
        "all_pages_succeeded": candidate["page_count"] == control["page_count"] == 8,
        "character_ratio_at_least_0_95": char_ratio >= 0.95,
        "low_confidence_not_worse_by_over_0_01": low_delta is not None and low_delta <= 0.01,
        "confidence_or_low_rate_improved": (
            (mean_delta is not None and mean_delta >= 0.01)
            or (low_delta is not None and low_delta <= -0.02)
        ),
        "no_page_character_drop_over_0_20": all(item["drop_ratio"] <= 0.20 for item in page_char_drops),
    }
    return {
        "metric_pass": all(checks.values()),
        "visual_review_required": True,
        "checks": checks,
        "deltas": {
            "character_ratio": char_ratio,
            "mean_confidence": mean_delta,
            "low_confidence_rate": low_delta,
        },
        "page_character_drops": page_char_drops,
    }


def select_input_policy(records_by_variant: dict[str, list[dict[str, object]]]) -> dict[str, object]:
    original = {str(item["page_id"]): item for item in records_by_variant["uvdoc_bilinear_original"]}
    neutral = {str(item["page_id"]): item for item in records_by_variant["uvdoc_bilinear_neutralized"]}
    original_wins = neutral_wins = ties = 0
    page_results = []
    for page_id in sorted(set(original) & set(neutral)):
        left = original[page_id]["metrics"]
        right = neutral[page_id]["metrics"]
        left_conf = left.get("mean_confidence")
        right_conf = right.get("mean_confidence")
        if left_conf is None or right_conf is None or abs(float(left_conf) - float(right_conf)) < 0.002:
            winner = "tie"
            ties += 1
        elif float(left_conf) > float(right_conf):
            winner = "original"
            original_wins += 1
        else:
            winner = "neutralized"
            neutral_wins += 1
        page_results.append({"page_id": page_id, "winner": winner, "mean_confidence_delta_neutralized": float(right_conf or 0) - float(left_conf or 0)})
    preferred = "original" if original_wins >= 5 else "neutralized" if neutral_wins >= 5 else "undecided"
    return {
        "preferred": preferred,
        "original_wins": original_wins,
        "neutralized_wins": neutral_wins,
        "ties": ties,
        "pages": page_results,
    }


def run_uvdoc_ocr_ab_experiment(
    input_pairs: list[tuple[Path, Path]],
    output_dir: Path,
    unwarper: UVDocAdapter,
    ocr_adapter: GeneralOcrAdapter,
    postprocessor: ImagePostprocessor | None = None,
    padding_fraction: float = 0.03,
) -> dict[str, object]:
    from document_parser.evaluation.ocr_quality import build_ocr_quality_report
    from document_parser.serialization.text_ir import TextOnlyPageIrBuilder

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    postprocessor = postprocessor or LuminanceUnsharpPostprocessor()
    builder = TextOnlyPageIrBuilder(adapter=ocr_adapter)
    records_by_variant: dict[str, list[dict[str, object]]] = {name: [] for name in VARIANT_NAMES}
    inputs = []

    for image_path, label_path in input_pairs:
        image_path, label_path = Path(image_path), Path(label_path)
        frame = read_image(image_path)
        labels = load_labelme_pages(image_path, label_path)
        capture_dir = output_dir / image_path.stem
        capture_rows = []
        inputs.append({
            "capture": image_path.stem,
            "image_path": str(image_path),
            "image_sha256": sha256_file(image_path),
            "label_path": str(label_path),
            "label_sha256": sha256_file(label_path),
            "annotation_diagnostics": labels.diagnostics,
        })
        for side in (PageSide.LEFT, PageSide.RIGHT):
            annotation = labels.pages[side]
            page_id = f"{image_path.stem}_{side.value}"
            page_dir = capture_dir / side.value
            write_image(page_dir / "mask.png", annotation.mask)
            write_image(page_dir / "annotation_overlay.jpg", _overlay(frame, annotation))
            variants = build_page_variants(
                frame,
                annotation,
                unwarper,
                postprocessor=postprocessor,
                padding_fraction=padding_fraction,
            )
            contact_row = []
            page_metadata = {"page_id": page_id, "annotation": {"bbox_full": list(annotation.bbox_full)}, "variants": {}}
            for variant_name in VARIANT_NAMES:
                variant = variants[variant_name]
                variant_payload = {
                    "success": bool(variant["success"]),
                    "source": variant.get("source"),
                    "reason": variant.get("reason"),
                    "diagnostics": variant.get("diagnostics", {}),
                }
                image = variant.get("image")
                if not variant["success"] or not isinstance(image, np.ndarray):
                    page_metadata["variants"][variant_name] = variant_payload
                    continue
                image_path_out = page_dir / "variants" / f"{variant_name}.png"
                write_image(image_path_out, image)
                image_sha = sha256_file(image_path_out)
                variant_payload.update({
                    "artifact_path": str(image_path_out),
                    "artifact_sha256": image_sha,
                    "image_metrics": image_quality_metrics(image),
                })
                record_path = page_dir / "ocr" / f"{variant_name}.json"
                try:
                    record = run_ocr_for_artifact(image_path_out, page_id, record_path, ocr_adapter, builder=builder)
                    overlay = draw_ocr_overlay(image, record)
                    overlay_path = page_dir / "ocr_overlays" / f"{variant_name}.jpg"
                    write_image(overlay_path, overlay)
                    record["variant"] = variant_name
                    record["ocr_overlay_path"] = str(overlay_path)
                    records_by_variant[variant_name].append(record)
                    variant_payload["ocr_record_path"] = str(record_path)
                    variant_payload["ocr_metrics"] = record["metrics"]
                    variant_payload["ocr_cache_hit"] = record["cache_hit"]
                except Exception as exc:
                    variant_payload["ocr_error"] = f"{type(exc).__name__}: {exc}"
                page_metadata["variants"][variant_name] = variant_payload
                contact_row.append((variant_name, image))
            capture_rows.append(contact_row)
            (page_dir / "metadata.json").write_text(
                json.dumps(page_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        write_image(capture_dir / "contact_sheet.jpg", _contact_sheet(capture_rows))

    variant_summaries = {name: aggregate_variant(records) for name, records in records_by_variant.items()}
    ocr_quality_reports = {}
    for name, records in records_by_variant.items():
        payload = {
            "pages": [record["page_ir_page"] for record in records],
            "engine_manifest": {"general_ocr": {"engine_id": ocr_adapter.engine_id, "engine_version": ocr_adapter.engine_version}},
        }
        ocr_quality_reports[name] = build_ocr_quality_report(payload)

    candidate_screens = {
        "uvdoc_bicubic_original": screen_candidate(records_by_variant["uvdoc_bicubic_original"], records_by_variant["uvdoc_bilinear_original"]),
        "uvdoc_bicubic_neutralized": screen_candidate(records_by_variant["uvdoc_bicubic_neutralized"], records_by_variant["uvdoc_bilinear_neutralized"]),
        "uvdoc_unsharp_original": screen_candidate(records_by_variant["uvdoc_unsharp_original"], records_by_variant["uvdoc_bilinear_original"]),
        "uvdoc_unsharp_neutralized": screen_candidate(records_by_variant["uvdoc_unsharp_neutralized"], records_by_variant["uvdoc_bilinear_neutralized"]),
    }
    metric_passes = [name for name, screen in candidate_screens.items() if screen["metric_pass"]]
    automated_postprocess = (
        "BICUBIC" if any("bicubic" in name for name in metric_passes)
        else "UNSHARP" if any("unsharp" in name for name in metric_passes)
        else "POSTPROCESS_NONE"
    )
    summary = {
        "inputs": inputs,
        "variant_names": list(VARIANT_NAMES),
        "expected_page_count": len(input_pairs) * 2,
        "engine": {
            "engine_id": ocr_adapter.engine_id,
            "engine_version": ocr_adapter.engine_version,
            "signature": _engine_signature(ocr_adapter),
        },
        "uvdoc_load_count": unwarper.load_count,
        "variant_summaries": variant_summaries,
        "ocr_quality_reports": ocr_quality_reports,
        "paired_capture_similarity": paired_capture_similarities(records_by_variant),
        "input_policy": select_input_policy(records_by_variant),
        "candidate_screens": candidate_screens,
        "automated_postprocess_screen": automated_postprocess,
        "visual_review_required": True,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary
