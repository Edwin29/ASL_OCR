"""Run corrected page artifacts through the production Document Parser path.

This uses PaddleOCR-VL -> Page IR -> accessibility flattening -> braille.  It
does not synthesize TTS or touch the book-scanner session/transmit paths.
Model download is refused unless ``--allow-model-download`` is explicit.
"""

from __future__ import annotations

import argparse
import hashlib
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

from book_scanner.evaluation.document_parser_braille import (  # noqa: E402
    compare_braille_evaluations,
    evaluate_page_ir_braille,
    load_and_evaluate_page_ir,
)


DEFAULT_REFERENCE = DOCUMENT_PARSER_ROOT / "tests" / "fixtures" / "accessibility" / "p030.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _discover_images(
    experiment_dir: Path,
    variants: list[str],
    capture_stems: set[str] | None = None,
    sides: set[str] | None = None,
) -> list[tuple[str, Path]]:
    discovered: list[tuple[str, Path]] = []
    for variant in variants:
        for path in sorted(experiment_dir.glob(f"*/*/variants/{variant}.png")):
            capture, side = path.parents[2].name, path.parents[1].name
            if capture_stems and capture not in capture_stems:
                continue
            if sides and side not in sides:
                continue
            discovered.append((f"{capture}_{side}_{variant}", path))
    return discovered


def _model_home_has_cached_assets(model_home: Path) -> bool:
    official = model_home / ".paddlex" / "official_models"
    return official.is_dir() and any(path.is_dir() for path in official.iterdir())


def _cached_page_ir(
    record_path: Path,
    image_sha256: str,
    engine_signature: str,
) -> dict[str, object] | None:
    if not record_path.is_file():
        return None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if record.get("image_sha256") != image_sha256 or record.get("engine_signature") != engine_signature:
        return None
    page_ir = record.get("page_ir")
    return page_ir if isinstance(page_ir, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path)
    parser.add_argument("--variant", action="append", dest="variants")
    parser.add_argument("--capture-stem", action="append", dest="capture_stems")
    parser.add_argument("--side", action="append", choices=("left", "right"), dest="sides")
    parser.add_argument("--image", action="append", type=Path, dest="images")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-home", type=Path, required=True)
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--reference-page-ir", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--allow-model-download", action="store_true")
    args = parser.parse_args()

    inputs: list[tuple[str, Path]] = []
    if args.experiment_dir:
        variants = args.variants or ["uvdoc_bilinear_original"]
        inputs.extend(_discover_images(
            args.experiment_dir.resolve(),
            variants,
            set(args.capture_stems or []),
            set(args.sides or []),
        ))
    for image in args.images or []:
        inputs.append((image.stem, image.resolve()))
    if not inputs:
        parser.error("provide --experiment-dir or at least one --image")
    missing = [str(path) for _, path in inputs if not path.is_file()]
    if missing:
        parser.error(f"missing input images: {missing}")
    if not args.reference_page_ir.is_file():
        parser.error(f"missing reference Page IR: {args.reference_page_ir}")

    model_home = args.model_home.resolve()
    if not args.allow_model_download and not _model_home_has_cached_assets(model_home):
        parser.error(
            "PaddleOCR-VL cached model assets were not found and automatic download is disabled. "
            "Re-run only after approval with --allow-model-download, or point --model-home at a complete cache."
        )

    from document_parser.ocr.paddleocr_vl_adapter import PaddleOcrVlAdapter
    from document_parser.serialization import build_document_ir_from_vl

    paddleocr_version = importlib.metadata.version("paddleocr")
    engine_signature = (
        f"paddleocr-vl:{paddleocr_version}:device={args.device}:"
        "use_ocr_for_image_block=true:pipeline=paddleocr_vl_baseline"
    )
    adapter = PaddleOcrVlAdapter(model_home=model_home, device=args.device)
    reference = load_and_evaluate_page_ir(args.reference_page_ir)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for artifact_id, image_path in inputs:
        image_sha = _sha256(image_path)
        record_path = output_dir / f"{artifact_id}.json"
        page_ir = _cached_page_ir(record_path, image_sha, engine_signature)
        cache_hit = page_ir is not None
        if page_ir is None:
            page_ir = build_document_ir_from_vl([image_path], adapter=adapter, book_id=artifact_id)
        evaluation = evaluate_page_ir_braille(page_ir)
        comparison = compare_braille_evaluations(evaluation, reference, same_content=False)
        record = {
            "artifact_id": artifact_id,
            "image_path": str(image_path),
            "image_sha256": image_sha,
            "engine_signature": engine_signature,
            "cache_hit": cache_hit,
            "page_ir": page_ir,
            "braille_evaluation": evaluation,
            "reference_comparison": comparison,
        }
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append({
            "artifact_id": artifact_id,
            "record_path": str(record_path),
            "cache_hit": cache_hit,
            "schema_valid": evaluation["schema_valid"],
            "braille_opportunity_count": evaluation["braille_opportunity_count"],
            "braille_error_count": evaluation["braille_error_count"],
            "verdict": comparison["verdict"],
        })
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)

    summary = {
        "status": "COMPLETE",
        "engine_signature": engine_signature,
        "reference": reference,
        "comparison_scope": (
            "The committed p030 fixture has different source content. Only schema and translation "
            "coverage are compared; exact OCR text and braille cells are not compared."
        ),
        "results": results,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if all(item["schema_valid"] and item["braille_error_count"] == 0 for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
