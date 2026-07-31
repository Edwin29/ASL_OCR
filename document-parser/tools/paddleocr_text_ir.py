from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.ocr.baseline import (
    DEFAULT_DETECTION_MODEL_DIR,
    DEFAULT_DETECTION_MODEL_NAME,
    DEFAULT_MODEL_HOME,
    DEFAULT_RECOGNITION_MODEL_DIR,
    DEFAULT_RECOGNITION_MODEL_NAME,
    create_baseline_ocr_adapter,
)
from document_parser.ocr.cache import OcrResultCache
from document_parser.serialization.text_ir import TextOnlyPageIrBuilder, write_page_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate TEXT-only Page IR with PaddleOCR safe CPU settings.")
    parser.add_argument("--images-dir", type=Path, default=ROOT / "data" / "pages_pdf300")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "debug" / "paddleocr_text_page_ir.json")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "debug" / "ocr_cache")
    parser.add_argument("--model-home", type=Path, default=DEFAULT_MODEL_HOME)
    parser.add_argument("--det-model-dir", type=Path, default=DEFAULT_DETECTION_MODEL_DIR)
    parser.add_argument("--rec-model-dir", type=Path, default=DEFAULT_RECOGNITION_MODEL_DIR)
    parser.add_argument("--text-det-limit-side-len", type=int, default=1600)
    parser.add_argument("--text-det-limit-type", default="max")
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--enable-mkldnn", action="store_true")
    parser.add_argument("--page-id", action="append", help="Optional page ID filter. Can be passed multiple times.")
    args = parser.parse_args(argv)

    image_paths = image_paths_for(args.images_dir.resolve(), set(args.page_id) if args.page_id else None)
    adapter = create_baseline_ocr_adapter(
        model_home=args.model_home.resolve(),
        text_detection_model_dir=args.det_model_dir.resolve(),
        text_recognition_model_dir=args.rec_model_dir.resolve(),
        text_det_limit_side_len=args.text_det_limit_side_len,
        text_det_limit_type=args.text_det_limit_type,
        enable_mkldnn=args.enable_mkldnn,
        cpu_threads=args.cpu_threads,
    )
    page_ir = TextOnlyPageIrBuilder(
        adapter=adapter,
        cache=OcrResultCache(args.cache_dir.resolve()),
    ).build_document(image_paths)
    write_page_ir(args.output.resolve(), page_ir)
    print(f"Wrote {args.output.resolve()}")
    print(f"Pages: {len(page_ir['pages'])}")
    print(f"Nodes: {sum(len(page['nodes']) for page in page_ir['pages'])}")
    print(f"Adapter: {adapter.engine_id} {adapter.engine_version}")
    print(f"Detection model: {DEFAULT_DETECTION_MODEL_NAME}")
    print(f"Recognition model: {DEFAULT_RECOGNITION_MODEL_NAME}")
    print(f"Safe settings: mkldnn={adapter.enable_mkldnn}, side_len={adapter.text_det_limit_side_len}, side_type={adapter.text_det_limit_type}, threads={adapter.cpu_threads}")
    print(f"Schema valid: {page_ir['validation_summary']['schema_valid']}")
    return 0 if page_ir["validation_summary"]["schema_valid"] else 1


def image_paths_for(images_dir: Path, page_ids: set[str] | None) -> list[Path]:
    image_paths = sorted(images_dir.glob("*.png"))
    if page_ids is None:
        return image_paths
    return [path for path in image_paths if any(f"_{page_id}" in path.stem for page_id in page_ids)]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
