from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.ocr.cache import OcrResultCache
from document_parser.ocr.easyocr_adapter import EasyOcrGeneralAdapter
from document_parser.serialization.text_ir import TextOnlyPageIrBuilder, write_page_ir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate TEXT-only Page IR with EasyOCR.")
    parser.add_argument("--images-dir", type=Path, default=ROOT / "data" / "pages_pdf300")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "debug" / "easyocr_text_page_ir.json")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "debug" / "ocr_cache")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "data" / "debug" / "model_home" / ".EasyOCR" / "model")
    parser.add_argument("--home-dir", type=Path, default=ROOT / "data" / "debug" / "model_home")
    parser.add_argument("--languages", nargs="+", default=["ko", "en"])
    parser.add_argument("--page-id", action="append", help="Optional page ID filter. Can be passed multiple times.")
    parser.add_argument("--download-enabled", action="store_true")
    parser.add_argument("--gpu", action="store_true")
    args = parser.parse_args(argv)

    configure_process_home(args.home_dir.resolve())
    image_paths = image_paths_for(args.images_dir.resolve(), set(args.page_id) if args.page_id else None)
    adapter = EasyOcrGeneralAdapter(
        languages=tuple(args.languages),
        gpu=args.gpu,
        model_storage_directory=args.model_dir.resolve(),
        download_enabled=args.download_enabled,
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
    print(f"Schema valid: {page_ir['validation_summary']['schema_valid']}")
    return 0 if page_ir["validation_summary"]["schema_valid"] else 1


def configure_process_home(home_dir: Path) -> None:
    home_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(home_dir)
    os.environ["USERPROFILE"] = str(home_dir)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def image_paths_for(images_dir: Path, page_ids: set[str] | None) -> list[Path]:
    image_paths = sorted(images_dir.glob("*.png"))
    if page_ids is None:
        return image_paths
    return [path for path in image_paths if any(f"_{page_id}" in path.stem for page_id in page_ids)]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
