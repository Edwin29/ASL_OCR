"""Run the approved same-source p30 extraction/geometry validation.

Use the document-parser CPU environment for ``audit``, ``prepare`` and
``postprocess-prepare``.  Use the existing GPU OCR environment for ``oracle``,
``automatic`` and ``postprocess``.  No model download, TTS, datapack write,
session mutation or transmission is performed.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path

import cv2
import numpy as np


BOOK_SCANNER_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BOOK_SCANNER_ROOT.parent
DOCUMENT_PARSER_ROOT = WORKSPACE_ROOT / "document-parser"
for source_dir in (BOOK_SCANNER_ROOT / "src", DOCUMENT_PARSER_ROOT / "src"):
    if str(source_dir) not in sys.path:
        sys.path.insert(0, str(source_dir))

from book_scanner.annotations.labelme import load_labelme_pages  # noqa: E402
from book_scanner.correct.uvdoc_adapter import UVDocAdapter, UVDocConfig  # noqa: E402
from book_scanner.detect.roi import PageSide  # noqa: E402
from book_scanner.evaluation.p030_reference import (  # noqa: E402
    compare_p030_page_ir,
    select_uvdoc_postprocess_sources,
)
from book_scanner.evaluation.document_parser_braille import compare_braille_evaluations  # noqa: E402
from book_scanner.evaluation.paired_ocr_inputs import (  # noqa: E402
    prepare_extraction_manifest,
    prepare_geometry_manifest,
    prepare_postprocess_manifest,
    sha256_file,
)
from book_scanner.evaluation.paired_page_ir import (  # noqa: E402
    compare_same_source,
    evaluate_paired_page_ir,
    run_ocr_batch,
)


P030_CAPTURES = ("20260830_111919", "20260830_112000", "20260830_112042")
DEFAULT_IMAGES = WORKSPACE_ROOT / "tmp" / "p030-drive-package-20260830-1139" / "testimages"
DEFAULT_OUTPUT = BOOK_SCANNER_ROOT / "experiment_outputs" / "p030_document_parser_20260830"
DEFAULT_MODEL_HOME = DOCUMENT_PARSER_ROOT / "data" / "debug" / "model_home_vl"
DEFAULT_REFERENCE = DOCUMENT_PARSER_ROOT / "tests" / "fixtures" / "accessibility" / "p030.json"
DEFAULT_UVDOC_RUNTIME = WORKSPACE_ROOT / "tmp" / "uvdoc-runtime"
DEFAULT_UVDOC_CHECKPOINT = DEFAULT_UVDOC_RUNTIME / "model" / "best_model.pkl"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def audit_inputs(image_dir: Path, output_dir: Path, package_zip: Path | None = None) -> dict[str, object]:
    records: list[dict[str, object]] = []
    for capture in P030_CAPTURES:
        image_path = image_dir / f"{capture}.jpg"
        label_path = image_dir / f"{capture}.json"
        labels = load_labelme_pages(image_path, label_path)
        pages = {
            side.value: {
                "point_count": len(annotation.points),
                "bbox_full": list(annotation.bbox_full),
                "area_ratio": annotation.area_ratio,
                "winding": annotation.winding,
                "touches_frame_edge": annotation.touches_frame_edge,
            }
            for side, annotation in labels.pages.items()
        }
        records.append({
            "capture": capture,
            "status": "STRICT_VALID",
            "image_path": str(image_path.resolve()),
            "image_sha256": sha256_file(image_path),
            "label_path": str(label_path.resolve()),
            "label_sha256": sha256_file(label_path),
            "image_size": list(labels.image_size),
            "pages": pages,
            "overlap_px": labels.overlap_px,
            "diagnostics": labels.diagnostics,
        })
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "STRICT_VALID",
        "capture_count": len(records),
        "target_side": "left",
        "target_printed_page": 30,
        "records": records,
    }
    if package_zip is not None and package_zip.is_file():
        payload["package"] = {
            "file_name": package_zip.name,
            "size_bytes": package_zip.stat().st_size,
            "sha256": sha256_file(package_zip),
        }
    _write_json(output_dir / "input_manifest.json", payload)
    return payload


def _model_home_ready(model_home: Path) -> tuple[bool, list[str]]:
    official = model_home / ".paddlex" / "official_models"
    required = ("PaddleOCR-VL-1.6", "PP-DocLayoutV3")
    missing = [name for name in required if not (official / name).is_dir()]
    return not missing, missing


def _gpu_ready(device: str) -> tuple[bool, str | None]:
    if not device.startswith("gpu"):
        return False, "p30 production validation requires the approved GPU environment"
    try:
        import paddle

        if not paddle.is_compiled_with_cuda():
            return False, "PaddlePaddle is not compiled with CUDA"
        if paddle.device.cuda.device_count() < 1:
            return False, "No CUDA device is visible to PaddlePaddle"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, None


def _load_reference(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_ocr_phase(
    geometry_manifest_path: Path,
    output_dir: Path,
    model_home: Path,
    reference_path: Path,
    device: str,
    phase: str,
    extraction: str | None,
    *,
    postprocess_manifest_path: Path | None = None,
) -> dict[str, object]:
    ready, missing = _model_home_ready(model_home)
    if not ready:
        return {"phase": phase, "status": "BLOCKED_MODEL_ASSETS", "missing_assets": missing}
    device_ready, reason = _gpu_ready(device)
    if not device_ready:
        return {"phase": phase, "status": "BLOCKED_DEVICE", "device": device, "reason": reason}

    manifest_path = postprocess_manifest_path or geometry_manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if phase == "postprocess":
        artifacts = [
            item for item in manifest.get("artifacts", [])
            if item.get("status") == "READY" and (
                item.get("postprocess") == "luminance_unsharp_fixed"
                or item.get("geometry") == "uvdoc_bicubic"
            )
        ]
        if len(artifacts) > 6:
            raise RuntimeError(f"postprocess queue exceeds approved maximum: {len(artifacts)}")
    else:
        artifacts = [
            item for item in manifest.get("artifacts", [])
            if item.get("status") == "READY" and item.get("extraction") == extraction
        ]
        if len(artifacts) > 9:
            raise RuntimeError(f"{phase} queue exceeds approved maximum: {len(artifacts)}")
    if not artifacts:
        return {"phase": phase, "status": "BLOCKED_PREREQUISITE", "reason": "No READY artifacts"}

    from document_parser.ocr.paddleocr_vl_adapter import PaddleOcrVlAdapter
    from document_parser.serialization import build_document_ir_from_vl

    version = importlib.metadata.version("paddleocr")
    engine_signature = (
        f"paddleocr-vl:{version}:device={device}:"
        "use_ocr_for_image_block=true:pipeline=paddleocr_vl_baseline"
    )
    adapter = PaddleOcrVlAdapter(model_home=model_home, device=device)
    raw_results = run_ocr_batch(
        artifacts,
        output_dir / "ocr" / phase,
        adapter=adapter,
        engine_signature=engine_signature,
        build_page_ir=build_document_ir_from_vl,
        cache_roots=(output_dir / "ocr" / "oracle", output_dir / "ocr" / "automatic"),
    )
    reference = _load_reference(reference_path)
    artifacts_by_id = {str(item["artifact_id"]): item for item in artifacts}
    results: list[dict[str, object]] = []
    for item in raw_results:
        metadata = artifacts_by_id.get(str(item.get("artifact_id")), {})
        enriched = {
            **item,
            "capture": metadata.get("capture"),
            "side": metadata.get("side"),
            "extraction": metadata.get("extraction"),
            "geometry": metadata.get("geometry"),
            "postprocess": metadata.get("postprocess"),
        }
        if item.get("status") == "COMPLETE":
            record_path = Path(str(item["record_path"]))
            record = json.loads(record_path.read_text(encoding="utf-8"))
            comparison = compare_p030_page_ir(record["page_ir"], reference)
            record["p030_reference_comparison"] = comparison
            record["same_printed_source_asserted"] = True
            record["reference_is_human_golden"] = False
            _write_json(record_path, record)
            enriched["comparison"] = comparison
        results.append(enriched)

    status = "COMPLETE" if results and all(item.get("status") == "COMPLETE" for item in results) else "PARTIAL_FAILURE"
    summary = {
        "schema_version": 1,
        "phase": phase,
        "status": status,
        "engine_signature": engine_signature,
        "adapter_instance_count": 1,
        "adapter_reused_across_artifacts": True,
        "model_download_attempted": False,
        "reference_path": str(reference_path.resolve()),
        "reference_sha256": sha256_file(reference_path),
        "reference_is_human_golden": False,
        "absolute_accuracy_claim_allowed": False,
        "results": results,
    }
    _write_json(output_dir / f"{phase}_ocr_summary.json", summary)
    return summary


def _prepare(args) -> dict[str, object]:
    audit = audit_inputs(args.image_dir, args.output_dir, args.package_zip)
    extraction = prepare_extraction_manifest(
        args.image_dir,
        args.output_dir,
        captures=P030_CAPTURES,
        sides=(PageSide.LEFT,),
        extraction_variants=("oracle", "seam_conservative"),
        control_capture=None,
        fallback_stress_captures=(),
        oracle_independent_of_automatic=True,
        automatic_gate_scope="selected_sides",
    )
    uvdoc = UVDocAdapter(UVDocConfig(
        runtime_path=args.uvdoc_runtime,
        checkpoint_path=args.uvdoc_checkpoint,
        device="auto",
    ))
    geometry = prepare_geometry_manifest(
        args.output_dir / "extraction_manifest.json",
        args.output_dir,
        uvdoc,
        sides=(PageSide.LEFT,),
        extractions=("oracle", "seam_conservative"),
    )
    geometry["uvdoc_checkpoint_sha256"] = sha256_file(args.uvdoc_checkpoint)
    geometry["approved_max_ready_artifacts"] = 18
    _write_json(args.output_dir / "geometry_manifest.json", geometry)
    return {
        "stage": "prepare",
        "status": "PREPARED",
        "input_count": audit["capture_count"],
        "extraction_artifact_count": len(extraction["artifacts"]),
        "geometry_artifact_count": len(geometry["artifacts"]),
        "uvdoc_load_count": geometry["uvdoc_load_count"],
    }


def _postprocess_prepare(args) -> dict[str, object]:
    phase_results: list[dict[str, object]] = []
    for phase in ("oracle", "automatic"):
        path = args.output_dir / f"{phase}_ocr_summary.json"
        if not path.is_file():
            return {"stage": "postprocess-prepare", "status": "BLOCKED_PREREQUISITE", "missing": str(path)}
        summary = json.loads(path.read_text(encoding="utf-8"))
        if summary.get("status") != "COMPLETE":
            return {
                "stage": "postprocess-prepare", "status": "BLOCKED_PREREQUISITE",
                "reason": f"{phase} status is {summary.get('status')}",
            }
        phase_results.extend(summary.get("results", []))
    selected = select_uvdoc_postprocess_sources(phase_results, max_sources=3)
    screening = {
        "schema_version": 1,
        "status": "POSTPROCESS_SCREENING_REQUIRED" if selected else "POSTPROCESS_NOT_TRIGGERED",
        "selected_artifact_ids": selected,
        "approved_max_new_ocr": 6,
    }
    _write_json(args.output_dir / "postprocess_screening.json", screening)
    if not selected:
        return screening
    uvdoc = UVDocAdapter(UVDocConfig(
        runtime_path=args.uvdoc_runtime,
        checkpoint_path=args.uvdoc_checkpoint,
        device="auto",
    ))
    manifest = prepare_postprocess_manifest(
        args.output_dir / "geometry_manifest.json", args.output_dir, selected, uvdoc
    )
    screening["prepared_artifact_count"] = len(manifest["artifacts"])
    screening["uvdoc_load_count"] = manifest["uvdoc_load_count"]
    _write_json(args.output_dir / "postprocess_screening.json", screening)
    return screening


def _thumbnail(path: Path, width: int = 640) -> np.ndarray:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"could not read review image: {path}")
    height = max(1, round(image.shape[0] * width / image.shape[1]))
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)


def _generate_review_sheets(output_dir: Path) -> list[str]:
    manifest = json.loads((output_dir / "geometry_manifest.json").read_text(encoding="utf-8"))
    artifacts = {
        (str(item.get("capture")), str(item.get("extraction")), str(item.get("geometry"))): item
        for item in manifest.get("artifacts", []) if item.get("status") == "READY"
    }
    review_dir = output_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []
    for geometry in ("none", "coarse", "uvdoc_bilinear"):
        rows: list[np.ndarray] = []
        for extraction in ("oracle", "seam_conservative"):
            cells: list[np.ndarray] = []
            for capture in P030_CAPTURES:
                record = artifacts[(capture, extraction, geometry)]
                cell = _thumbnail(Path(str(record["image_path"])))
                bar = np.full((52, cell.shape[1], 3), 245, dtype=np.uint8)
                cv2.putText(
                    bar, f"{capture} | {extraction} | {geometry}", (12, 34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.63, (20, 20, 20), 1, cv2.LINE_AA,
                )
                cells.append(np.vstack((bar, cell)))
            row_height = max(cell.shape[0] for cell in cells)
            padded = [
                cv2.copyMakeBorder(cell, 0, row_height - cell.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(235, 235, 235))
                for cell in cells
            ]
            rows.append(np.hstack(padded))
        sheet = np.vstack(rows)
        path = review_dir / f"{geometry}_oracle_vs_seam_conservative.jpg"
        if not cv2.imwrite(str(path), sheet, [cv2.IMWRITE_JPEG_QUALITY, 92]):
            raise OSError(f"could not write review sheet: {path}")
        outputs.append(str(path.relative_to(output_dir)).replace("\\", "/"))
    return outputs


def _final_summary(output_dir: Path) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "INCOMPLETE",
        "reference_is_human_golden": False,
        "absolute_accuracy_claim_allowed": False,
        "phases": {},
    }
    for phase in ("oracle", "automatic", "postprocess"):
        path = output_dir / f"{phase}_ocr_summary.json"
        if path.is_file():
            summary = json.loads(path.read_text(encoding="utf-8"))
            payload["phases"][phase] = {
                "status": summary.get("status"),
                "result_count": len(summary.get("results", [])),
            }
    screening_path = output_dir / "postprocess_screening.json"
    if screening_path.is_file():
        payload["postprocess_screening"] = json.loads(screening_path.read_text(encoding="utf-8"))
    oracle_summary_path = output_dir / "oracle_ocr_summary.json"
    automatic_summary_path = output_dir / "automatic_ocr_summary.json"
    if oracle_summary_path.is_file() and automatic_summary_path.is_file():
        oracle_summary = json.loads(oracle_summary_path.read_text(encoding="utf-8"))
        automatic_summary = json.loads(automatic_summary_path.read_text(encoding="utf-8"))
        oracle_results = {
            (str(item.get("capture")), str(item.get("geometry"))): item
            for item in oracle_summary.get("results", []) if item.get("status") == "COMPLETE"
        }
        automatic_results = {
            (str(item.get("capture")), str(item.get("geometry"))): item
            for item in automatic_summary.get("results", []) if item.get("status") == "COMPLETE"
        }
        paired: list[dict[str, object]] = []
        for key in sorted(set(oracle_results) & set(automatic_results)):
            oracle_item, automatic_item = oracle_results[key], automatic_results[key]
            oracle_record = json.loads(Path(str(oracle_item["record_path"])).read_text(encoding="utf-8"))
            automatic_record = json.loads(Path(str(automatic_item["record_path"])).read_text(encoding="utf-8"))
            oracle_eval = evaluate_paired_page_ir(oracle_record["page_ir"])
            automatic_eval = evaluate_paired_page_ir(automatic_record["page_ir"])
            paired.append({
                "capture": key[0],
                "geometry": key[1],
                "oracle_artifact_id": oracle_item["artifact_id"],
                "automatic_artifact_id": automatic_item["artifact_id"],
                "automatic_vs_oracle": compare_same_source(oracle_eval, automatic_eval),
                "automatic_vs_oracle_braille": compare_braille_evaluations(
                    automatic_eval, oracle_eval, same_content=True
                ),
                "oracle_reference_text_similarity": oracle_item["comparison"]["overall_text_similarity"],
                "automatic_reference_text_similarity": automatic_item["comparison"]["overall_text_similarity"],
                "oracle_reference_cell_similarity": oracle_item["comparison"]["braille"]["cell_similarity"],
                "automatic_reference_cell_similarity": automatic_item["comparison"]["braille"]["cell_similarity"],
            })
        payload["automatic_vs_oracle"] = paired

        geometry_summary: dict[str, object] = {}
        candidates: list[str] = []
        for geometry in ("none", "coarse", "uvdoc_bilinear"):
            oracle_items = [item for item in oracle_results.values() if item.get("geometry") == geometry]
            automatic_items = [item for item in automatic_results.values() if item.get("geometry") == geometry]
            all_items = oracle_items + automatic_items
            hard_passes = sum(bool(item["comparison"]["hard_gate_passed"]) for item in all_items)
            text_values = [float(item["comparison"]["overall_text_similarity"]) for item in all_items]
            cell_values = [float(item["comparison"]["braille"]["cell_similarity"]) for item in all_items]
            geometry_summary[geometry] = {
                "result_count": len(all_items),
                "hard_gate_pass_count": hard_passes,
                "mean_reference_text_similarity": sum(text_values) / len(text_values),
                "mean_reference_cell_similarity": sum(cell_values) / len(cell_values),
                "braille_error_count": sum(int(item["braille_error_count"]) for item in all_items),
            }
            if len(all_items) == 6 and hard_passes == 6:
                candidates.append(geometry)
        payload["geometry_summary"] = geometry_summary
        payload["geometry_candidate"] = candidates[0] if len(candidates) == 1 else None
        payload["geometry_verdict"] = (
            f"ORACLE_AND_AUTOMATIC_GEOMETRY_CANDIDATE_{candidates[0].upper()}"
            if len(candidates) == 1 else "ORACLE_GEOMETRY_INCONCLUSIVE"
        )

        extraction_manifest = json.loads((output_dir / "extraction_manifest.json").read_text(encoding="utf-8"))
        automatic_inputs = [
            item for item in extraction_manifest.get("artifacts", [])
            if item.get("extraction") == "seam_conservative" and item.get("status") == "READY"
        ]
        candidate = payload["geometry_candidate"]
        candidate_pairs = [item for item in paired if item["geometry"] == candidate]
        mask_gate = bool(automatic_inputs) and all(
            float(item["source"]["label_metrics"]["own_page_recall"]) >= 0.99
            and float(item["source"]["label_metrics"]["opposite_page_inclusion_ratio"]) <= 0.01
            for item in automatic_inputs
        )
        no_reference_regression = len(candidate_pairs) == 3 and all(
            float(item["automatic_reference_text_similarity"]) + 0.02
            >= float(item["oracle_reference_text_similarity"])
            and float(item["automatic_reference_cell_similarity"]) + 0.05
            >= float(item["oracle_reference_cell_similarity"])
            for item in candidate_pairs
        )
        automatic_hard_gate = candidate is not None and all(
            bool(item["comparison"]["hard_gate_passed"])
            for item in automatic_results.values() if item.get("geometry") == candidate
        )
        payload["seam_conservative_verdict"] = (
            "SEAM_CONSERVATIVE_NO_CLEAR_REGRESSION_P030"
            if mask_gate and no_reference_regression and automatic_hard_gate
            else "SEAM_CONSERVATIVE_INCONCLUSIVE_P030"
        )
        payload["review_sheets"] = _generate_review_sheets(output_dir)

    phases = payload["phases"]
    if phases.get("oracle", {}).get("status") == "COMPLETE" and phases.get("automatic", {}).get("status") == "COMPLETE":
        screening = payload.get("postprocess_screening", {})
        postprocess_done = (
            screening.get("status") == "POSTPROCESS_NOT_TRIGGERED"
            or phases.get("postprocess", {}).get("status") == "COMPLETE"
        )
        if postprocess_done:
            payload["status"] = "EXECUTION_COMPLETE_NOT_HUMAN_GOLDEN"
    _write_json(output_dir / "final_summary.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=("audit", "prepare", "oracle", "automatic", "postprocess-prepare", "postprocess", "report"),
    )
    parser.add_argument("--image-dir", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--package-zip", type=Path)
    parser.add_argument("--model-home", type=Path, default=DEFAULT_MODEL_HOME)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--uvdoc-runtime", type=Path, default=DEFAULT_UVDOC_RUNTIME)
    parser.add_argument("--uvdoc-checkpoint", type=Path, default=DEFAULT_UVDOC_CHECKPOINT)
    args = parser.parse_args()
    for name in ("image_dir", "output_dir", "model_home", "reference", "uvdoc_runtime", "uvdoc_checkpoint"):
        setattr(args, name, getattr(args, name).resolve())
    if args.package_zip is not None:
        args.package_zip = args.package_zip.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        if args.stage == "audit":
            result = audit_inputs(args.image_dir, args.output_dir, args.package_zip)
        elif args.stage == "prepare":
            result = _prepare(args)
        elif args.stage in {"oracle", "automatic"}:
            result = _run_ocr_phase(
                args.output_dir / "geometry_manifest.json",
                args.output_dir,
                args.model_home,
                args.reference,
                args.device,
                args.stage,
                "oracle" if args.stage == "oracle" else "seam_conservative",
            )
        elif args.stage == "postprocess-prepare":
            result = _postprocess_prepare(args)
        elif args.stage == "postprocess":
            result = _run_ocr_phase(
                args.output_dir / "geometry_manifest.json",
                args.output_dir,
                args.model_home,
                args.reference,
                args.device,
                "postprocess",
                None,
                postprocess_manifest_path=args.output_dir / "postprocess_manifest.json",
            )
        else:
            result = _final_summary(args.output_dir)
    except Exception as exc:
        result = {"stage": args.stage, "status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
        _write_json(args.output_dir / f"{args.stage}_failure.json", result)
        print(json.dumps(result, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if str(result.get("status", "")).startswith(("STRICT_VALID", "PREPARED", "COMPLETE", "POSTPROCESS_", "EXECUTION_")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
