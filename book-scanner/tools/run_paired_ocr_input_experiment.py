"""Prepare and run the approved staged paired OCR input experiment.

No model download is attempted.  This runner stops before TTS, session state,
datapack writes, or transmission.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path


BOOK_SCANNER_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BOOK_SCANNER_ROOT.parent
DOCUMENT_PARSER_ROOT = WORKSPACE_ROOT / "document-parser"
for source_dir in (BOOK_SCANNER_ROOT / "src", DOCUMENT_PARSER_ROOT / "src"):
    if str(source_dir) not in sys.path:
        sys.path.insert(0, str(source_dir))

from book_scanner.correct.uvdoc_adapter import UVDocAdapter, UVDocConfig  # noqa: E402
from book_scanner.evaluation.paired_ocr_inputs import (  # noqa: E402
    LABELED_CAPTURES,
    prepare_extraction_manifest,
    prepare_geometry_manifest,
    prepare_postprocess_manifest,
    sha256_file,
)
from book_scanner.evaluation.paired_page_ir import (  # noqa: E402
    compare_same_source,
    compare_repeated_captures,
    run_ocr_batch,
    select_ready_artifacts,
    select_postprocess_screening,
)


DEFAULT_IMAGES = BOOK_SCANNER_ROOT / "TESTIMAGES"
DEFAULT_OUTPUT = BOOK_SCANNER_ROOT / "experiment_outputs" / "paired_ocr_20260830"
DEFAULT_MODEL_HOME = DOCUMENT_PARSER_ROOT / "data" / "debug" / "model_home_vl"
DEFAULT_UVDOC_RUNTIME = WORKSPACE_ROOT / "tmp" / "uvdoc-runtime"
DEFAULT_UVDOC_CHECKPOINT = DEFAULT_UVDOC_RUNTIME / "model" / "best_model.pkl"
DEFAULT_CACHE_ROOTS = (
    BOOK_SCANNER_ROOT / "experiment_outputs" / "uvdoc_document_parser_20260826",
    BOOK_SCANNER_ROOT / "experiment_outputs" / "uvdoc_document_parser_screen_174958_right",
)


def _preflight_model_home(model_home: Path) -> tuple[bool, list[str]]:
    official = model_home / ".paddlex" / "official_models"
    required = ("PaddleOCR-VL-1.6", "PP-DocLayoutV3")
    missing = [name for name in required if not (official / name).is_dir()]
    return not missing, missing


def _device_available(device: str) -> tuple[bool, str | None]:
    if device == "cpu":
        return True, None
    if device.startswith("gpu"):
        try:
            import paddle
            if not paddle.is_compiled_with_cuda():
                return False, "PaddlePaddle is not compiled with CUDA"
            if paddle.device.cuda.device_count() < 1:
                return False, "No CUDA device is visible to PaddlePaddle"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, None
    return False, f"Unsupported device: {device}"


def _load_records(summary_items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for item in summary_items:
        path = item.get("record_path")
        if item.get("status") != "COMPLETE" or not path:
            continue
        payload = json.loads(Path(str(path)).read_text(encoding="utf-8"))
        records[str(item["artifact_id"])] = payload
    return records


def _phase_a_comparisons(summary_items: list[dict[str, object]]) -> list[dict[str, object]]:
    records = _load_records(summary_items)
    comparisons: list[dict[str, object]] = []
    for capture in LABELED_CAPTURES:
        for side in ("left", "right"):
            anchor_id = f"{capture}_{side}_oracle_none_none"
            anchor = records.get(anchor_id)
            if anchor is None:
                continue
            for extraction in ("oracle", "overlap", "seam_confirmed", "seam_conservative"):
                candidate_id = f"{capture}_{side}_{extraction}_none_none"
                candidate = records.get(candidate_id)
                if candidate is None:
                    continue
                comparisons.append({
                    "capture": capture, "side": side, "extraction": extraction,
                    "anchor_artifact_id": anchor_id, "candidate_artifact_id": candidate_id,
                    "comparison": compare_same_source(anchor["evaluation"], candidate["evaluation"]),
                })
    return comparisons


def _phase_b_comparisons(summary_items: list[dict[str, object]]) -> list[dict[str, object]]:
    records = _load_records(summary_items)
    comparisons: list[dict[str, object]] = []
    for capture in LABELED_CAPTURES:
        for side in ("left", "right"):
            for extraction in ("oracle", "seam_conservative"):
                anchor_id = f"{capture}_{side}_{extraction}_none_none"
                anchor = records.get(anchor_id)
                if anchor is None:
                    continue
                for geometry in ("none", "coarse", "uvdoc_bilinear"):
                    candidate_id = f"{capture}_{side}_{extraction}_{geometry}_none"
                    candidate = records.get(candidate_id)
                    if candidate is None:
                        continue
                    comparisons.append({
                        "capture": capture, "side": side, "extraction": extraction, "geometry": geometry,
                        "anchor_artifact_id": anchor_id, "candidate_artifact_id": candidate_id,
                        "comparison": compare_same_source(anchor["evaluation"], candidate["evaluation"]),
                    })
    return comparisons


def _run_ocr(
    manifest: dict[str, object], output_dir: Path, model_home: Path, device: str, phase: str,
    *, selected_artifacts: list[dict[str, object]] | None = None,
):
    available, missing = _preflight_model_home(model_home)
    if not available:
        return {
            "phase": phase, "status": "BLOCKED_MODEL_ASSETS", "missing_assets": missing,
            "model_download_attempted": False, "results": [], "comparisons": [],
        }
    device_ok, device_reason = _device_available(device)
    if not device_ok:
        return {
            "phase": phase, "status": "BLOCKED_DEVICE", "device": device,
            "reason": device_reason, "model_download_attempted": False,
            "results": [], "comparisons": [],
        }
    from document_parser.ocr.paddleocr_vl_adapter import PaddleOcrVlAdapter
    from document_parser.serialization import build_document_ir_from_vl

    version = importlib.metadata.version("paddleocr")
    signature = (
        f"paddleocr-vl:{version}:device={device}:"
        "use_ocr_for_image_block=true:pipeline=paddleocr_vl_baseline"
    )
    adapter = PaddleOcrVlAdapter(model_home=model_home, device=device)
    artifacts = selected_artifacts or [
        record for record in manifest.get("artifacts", []) if record.get("status") == "READY"
    ]
    results = run_ocr_batch(
        artifacts, output_dir / "ocr" / phase, adapter=adapter, engine_signature=signature,
        build_page_ir=build_document_ir_from_vl,
        cache_roots=(*DEFAULT_CACHE_ROOTS, output_dir / "ocr" / "extraction", output_dir / "ocr" / "geometry"),
    )
    comparisons = (
        _phase_a_comparisons(results) if phase == "extraction"
        else _phase_b_comparisons(results) if phase == "geometry"
        else []
    )
    repeated = compare_repeated_captures(_load_records(results))
    return {
        "phase": phase,
        "status": "COMPLETE" if all(item.get("status") == "COMPLETE" for item in results) else "PARTIAL_FAILURE",
        "engine_signature": signature,
        "model_home": str(model_home.resolve()),
        "model_download_attempted": False,
        "adapter_instance_count": 1,
        "adapter_reused_across_artifacts": True,
        "results": results,
        "comparisons": comparisons,
        "repeated_capture_comparisons": repeated,
        "accuracy_claim_allowed": False,
        "manual_golden_status": "MANUAL_GOLDEN_NOT_VERIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("extraction", "geometry", "postprocess"), required=True)
    parser.add_argument("--image-dir", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model-home", type=Path, default=DEFAULT_MODEL_HOME)
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--uvdoc-runtime", type=Path, default=DEFAULT_UVDOC_RUNTIME)
    parser.add_argument("--uvdoc-checkpoint", type=Path, default=DEFAULT_UVDOC_CHECKPOINT)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--artifact-id", action="append", dest="artifact_ids")
    parser.add_argument(
        "--capture-side", action="append", dest="capture_sides", metavar="CAPTURE:SIDE",
        help="Limit extraction OCR to an exact capture/side pair; repeatable.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    extraction_path = output_dir / "extraction_manifest.json"
    if args.phase == "postprocess":
        safe_device = args.device.replace(":", "_").replace("/", "_")
        geometry_summary_path = output_dir / f"geometry_{safe_device}_ocr_summary.json"
        if not geometry_summary_path.is_file():
            decision = {
                "status": "BLOCKED_PREREQUISITE",
                "reason": f"Missing Phase B summary: {geometry_summary_path}",
                "selected_artifacts": [], "full_batch_allowed": False,
            }
        else:
            decision = select_postprocess_screening(
                json.loads(geometry_summary_path.read_text(encoding="utf-8"))
            )
        screening_path = output_dir / f"postprocess_{safe_device}_screening.json"
        screening_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if decision["status"] != "SCREENING_REQUIRED":
            print(json.dumps({**decision, "summary_path": str(screening_path)}, ensure_ascii=False))
            return 0 if decision["status"] == "NO_POSTPROCESS_EVIDENCE" else 1
        geometry_manifest_path = output_dir / "geometry_manifest.json"
        if not geometry_manifest_path.is_file():
            parser.error(f"Missing Phase B manifest: {geometry_manifest_path}")
        uvdoc = UVDocAdapter(UVDocConfig(
            runtime_path=args.uvdoc_runtime.resolve(), checkpoint_path=args.uvdoc_checkpoint.resolve(), device="auto"
        ))
        manifest = prepare_postprocess_manifest(
            geometry_manifest_path, output_dir, decision["selected_artifacts"], uvdoc
        )
        if args.prepare_only:
            print(json.dumps({"phase": "postprocess", "status": "SCREENING_PREPARED",
                              "artifact_count": len(manifest["artifacts"])}, ensure_ascii=False))
            return 0
        summary = _run_ocr(manifest, output_dir, args.model_home.resolve(), args.device, "postprocess")
        summary["screening_decision"] = decision
        summary_path = output_dir / f"postprocess_{safe_device}_ocr_summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"phase": "postprocess", "status": summary["status"],
                          "summary_path": str(summary_path)}, ensure_ascii=False))
        return 0 if summary["status"] == "COMPLETE" else 1
    if args.phase == "extraction":
        manifest = prepare_extraction_manifest(args.image_dir.resolve(), output_dir)
    else:
        if not extraction_path.is_file():
            parser.error(f"Phase A manifest does not exist: {extraction_path}")
        if not args.uvdoc_runtime.is_dir() or not args.uvdoc_checkpoint.is_file():
            parser.error("UVDoc runtime/checkpoint missing; no download is permitted")
        uvdoc = UVDocAdapter(UVDocConfig(
            runtime_path=args.uvdoc_runtime.resolve(), checkpoint_path=args.uvdoc_checkpoint.resolve(), device="auto"
        ))
        manifest = prepare_geometry_manifest(extraction_path, output_dir, uvdoc)
        manifest["uvdoc_checkpoint_sha256"] = sha256_file(args.uvdoc_checkpoint)
        (output_dir / "geometry_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    if args.prepare_only:
        print(json.dumps({"phase": args.phase, "status": "PREPARED", "artifact_count": len(manifest["artifacts"])},
                         ensure_ascii=False))
        return 0

    parsed_capture_sides: list[tuple[str, str]] = []
    for value in args.capture_sides or []:
        try:
            capture, side = value.rsplit(":", 1)
        except ValueError:
            parser.error(f"invalid --capture-side {value!r}; expected CAPTURE:left|right")
        if side not in {"left", "right"}:
            parser.error(f"invalid --capture-side {value!r}; side must be left or right")
        parsed_capture_sides.append((capture, side))
    if (args.artifact_ids or parsed_capture_sides) and args.phase != "extraction":
        parser.error("--artifact-id/--capture-side are currently restricted to Phase A extraction")
    try:
        selected_artifacts = select_ready_artifacts(
            manifest, artifact_ids=args.artifact_ids or (), capture_sides=parsed_capture_sides
        )
    except ValueError as exc:
        parser.error(str(exc))
    summary = _run_ocr(
        manifest, output_dir, args.model_home.resolve(), args.device, args.phase,
        selected_artifacts=selected_artifacts,
    )
    summary["requested_artifact_ids"] = args.artifact_ids or []
    summary["requested_capture_sides"] = [list(item) for item in parsed_capture_sides]
    summary["selected_artifact_count"] = len(selected_artifacts)
    safe_device = args.device.replace(":", "_").replace("/", "_")
    summary_path = output_dir / f"{args.phase}_{safe_device}_ocr_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "phase": args.phase, "status": summary["status"], "result_count": len(summary["results"]),
        "comparison_count": len(summary["comparisons"]), "summary_path": str(summary_path),
    }, ensure_ascii=False))
    return 0 if summary["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
