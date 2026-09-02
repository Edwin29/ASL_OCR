"""Run one bounded production OCR diagnostic for the verified p030 MP4 frame."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BOOK_SCANNER_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BOOK_SCANNER_ROOT.parent
DOCUMENT_PARSER_ROOT = WORKSPACE_ROOT / "document-parser"
for source_dir in (BOOK_SCANNER_ROOT / "src", DOCUMENT_PARSER_ROOT / "src"):
    if str(source_dir) not in sys.path:
        sys.path.insert(0, str(source_dir))


EXPECTED_VIDEO_SHA256 = "16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8"
DEFAULT_FRAME_INDEX = 780


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def model_tree_snapshot(root: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]


def speech_diagnostic(page_ir: dict[str, object]) -> dict[str, object]:
    from document_parser.accessibility.flattening import flatten_document
    from document_parser.accessibility.speech import focus_item_announcement

    accessible = flatten_document(page_ir)
    items = [
        item
        for page in accessible.get("pages", [])
        if isinstance(page, dict)
        for item in page.get("focus_items", [])
        if isinstance(item, dict)
    ]
    utterances = [focus_item_announcement(item) for item in items]
    uncertain = [text for text in utterances if "수식 인식이 불확실" in text]
    math_spans = [
        span
        for item in items
        for span in item.get("spans", [])
        if isinstance(span, dict) and span.get("kind") == "MATH"
    ]
    math_statuses: dict[str, int] = {}
    for span in math_spans:
        status = str(span.get("ast_status", "UNKNOWN"))
        math_statuses[status] = math_statuses.get(status, 0) + 1
    kinds: dict[str, int] = {}
    for item in items:
        kind = str(item.get("kind", "UNKNOWN"))
        kinds[kind] = kinds.get(kind, 0) + 1
    return {
        "focus_item_count": len(items),
        "focus_item_kinds": kinds,
        "utterance_count": len(utterances),
        "uncertain_math_utterance_count": len(uncertain),
        "uncertain_math_ratio": len(uncertain) / len(utterances) if utterances else 0.0,
        "inline_math_span_count": len(math_spans),
        "inline_math_ast_statuses": math_statuses,
        "semantic_accuracy_proven_by_ast_status": False,
        "representative_utterances": utterances[:20],
    }


def comparison_summary(comparison: dict[str, object], speech: dict[str, object]) -> dict[str, object]:
    braille = comparison.get("braille") if isinstance(comparison.get("braille"), dict) else {}
    math = (
        comparison.get("math_braille_alignment")
        if isinstance(comparison.get("math_braille_alignment"), dict)
        else {}
    )
    return {
        "status": "diagnostic_complete",
        "verdict": comparison.get("verdict"),
        "hard_gate_passed": comparison.get("hard_gate_passed"),
        "overall_text_similarity": comparison.get("overall_text_similarity"),
        "problem_order": comparison.get("anchors", {}).get("problem_order") if isinstance(comparison.get("anchors"), dict) else [],
        "choice_counts": comparison.get("anchors", {}).get("choice_counts") if isinstance(comparison.get("anchors"), dict) else [],
        "braille_cell_similarity": braille.get("cell_similarity"),
        "math_reference_span_coverage": math.get("reference_span_coverage"),
        "math_common_cell_similarity": math.get("common_cell_similarity"),
        "math_reference_only_span_count": math.get("reference_only_span_count"),
        "math_candidate_added_span_count": math.get("candidate_added_span_count"),
        "math_reference_only_examples": math.get("reference_only_spans", [])[:3],
        "math_candidate_added_examples": math.get("candidate_added_spans", [])[:3],
        "uncertain_math_utterance_count": speech.get("uncertain_math_utterance_count"),
        "inline_math_span_count": speech.get("inline_math_span_count"),
        "inline_math_ast_statuses": speech.get("inline_math_ast_statuses"),
        "semantic_accuracy_proven_by_ast_status": False,
        "utterance_count": speech.get("utterance_count"),
    }


def prepare(args: argparse.Namespace) -> None:
    import cv2

    from book_scanner.correct.uvdoc_adapter import UVDocAdapter, UVDocConfig
    from book_scanner.detect.spread_extraction import SeamConservativeSpreadExtractor

    video = args.prepared_root / "inputs" / "scanner-replay.mp4"
    if not video.is_file() or sha256_file(video) != EXPECTED_VIDEO_SHA256:
        raise SystemExit(f"Pinned scanner-replay.mp4 is missing or has the wrong SHA-256: {video}")
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise SystemExit(f"Could not open video: {video}")
    capture.set(cv2.CAP_PROP_POS_FRAMES, args.frame_index)
    ok, frame = capture.read()
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    capture.release()
    if not ok or frame is None:
        raise SystemExit(f"Could not decode frame {args.frame_index}")

    extraction = SeamConservativeSpreadExtractor().extract(frame)
    if not extraction.success or extraction.left is None:
        raise SystemExit(f"p030 left extraction failed: {extraction.reason}: {extraction.diagnostics}")
    uvdoc = UVDocAdapter(UVDocConfig(
        runtime_path=args.prepared_root / "models" / "uvdoc" / "runtime",
        checkpoint_path=args.prepared_root / "models" / "uvdoc" / "checkpoint.pth",
        device="auto",
    )).unwarp(extraction.left.crop)
    if not uvdoc.success or uvdoc.image is None:
        reason = uvdoc.reason.value if uvdoc.reason is not None else "unknown"
        raise SystemExit(f"p030 UVDoc failed: {reason}: {dict(uvdoc.diagnostics)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    crop_path = args.output_dir / "p030_frame000780_left_crop.jpg"
    page_path = args.output_dir / "p030_frame000780_left_uvdoc.jpg"
    if not cv2.imwrite(str(crop_path), extraction.left.crop) or not cv2.imwrite(str(page_path), uvdoc.image):
        raise SystemExit("Could not persist p030 diagnostic images")
    manifest = {
        "schema_version": 1,
        "source_kind": "pinned_mp4_user_confirmed_frame",
        "source_video": str(video.resolve()),
        "source_video_sha256": EXPECTED_VIDEO_SHA256,
        "frame_index": args.frame_index,
        "timestamp_seconds": args.frame_index / fps,
        "target_printed_page": 30,
        "target_side": "left",
        "right_page_excluded": True,
        "crop": {"path": str(crop_path.resolve()), "sha256": sha256_file(crop_path), "bbox_full": list(extraction.left.bbox_full)},
        "uvdoc": {"path": str(page_path.resolve()), "sha256": sha256_file(page_path), "device": uvdoc.device, "processing_ms": uvdoc.processing_ms},
        "extraction_diagnostics": extraction.diagnostics,
    }
    write_json(args.output_dir / "input-manifest.json", manifest)
    print(json.dumps({"status": "prepared", "output_dir": str(args.output_dir)}, ensure_ascii=False))


def run_ocr(args: argparse.Namespace) -> None:
    from book_scanner.evaluation.p030_reference import compare_p030_page_ir
    from document_parser.ocr.paddleocr_vl_adapter import PaddleOcrVlAdapter
    from document_parser.serialization.vl_page_ir import build_document_ir_from_vl

    page_path = args.output_dir / "p030_frame000780_left_uvdoc.jpg"
    reference_path = DOCUMENT_PARSER_ROOT / "tests" / "fixtures" / "accessibility" / "p030.json"
    model_home = args.prepared_root / "models" / "paddleocr-vl"
    before = model_tree_snapshot(model_home)
    adapter = PaddleOcrVlAdapter(model_home=model_home, device=args.device)
    page_ir = build_document_ir_from_vl([page_path], adapter, "p030-mp4-production-diagnostic")
    after = model_tree_snapshot(model_home)
    if before != after:
        write_json(args.output_dir / "model-tree-before.json", before)
        write_json(args.output_dir / "model-tree-after.json", after)
        raise SystemExit("PaddleOCR-VL model tree changed; possible runtime download or mutation")
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    comparison = compare_p030_page_ir(page_ir, reference)
    speech = speech_diagnostic(page_ir)
    report = comparison_summary(comparison, speech)
    report.update({
        "engine_id": adapter.engine_id,
        "engine_version": adapter.engine_version,
        "device": args.device,
        "reference": str(reference_path.resolve()),
        "reference_sha256": sha256_file(reference_path),
        "model_tree_unchanged": True,
        "output_dir": str(args.output_dir.resolve()),
    })
    write_json(args.output_dir / "page-ir.json", page_ir)
    write_json(args.output_dir / "p030-comparison.json", comparison)
    write_json(args.output_dir / "speech-diagnostic.json", speech)
    write_json(args.output_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prepared_root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--scanner-python", type=Path)
    parser.add_argument("--device", default="gpu:0")
    parser.add_argument("--frame-index", type=int, default=DEFAULT_FRAME_INDEX)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    args.prepared_root = args.prepared_root.resolve()
    if args.output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.output_dir = WORKSPACE_ROOT / "tmp" / "p030-production-runs" / f"p030-{stamp}-{os.getpid()}"
    args.output_dir = args.output_dir.resolve()
    if args.frame_index != DEFAULT_FRAME_INDEX:
        raise SystemExit("Only the user-confirmed p030 frame 780 is accepted")
    if args.prepare_only:
        prepare(args)
        return 0
    if args.scanner_python is None or not args.scanner_python.is_file():
        raise SystemExit("--scanner-python must name the prepared scanner environment")
    command = [
        str(args.scanner_python), str(Path(__file__).resolve()), str(args.prepared_root),
        "--output-dir", str(args.output_dir), "--frame-index", str(args.frame_index), "--prepare-only",
    ]
    subprocess.run(command, check=True, env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    run_ocr(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
