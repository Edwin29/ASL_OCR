from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.ocr.baseline import (
    DEFAULT_DETECTION_MODEL_DIR,
    DEFAULT_MODEL_HOME,
    DEFAULT_RECOGNITION_MODEL_DIR,
    create_baseline_ocr_adapter,
)
from document_parser.structure import recognize_barrier_split_work_units


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run baseline OCR on layout barrier split work-unit crops.")
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--path-base", type=Path, default=ROOT)
    parser.add_argument("--model-home", type=Path, default=DEFAULT_MODEL_HOME)
    parser.add_argument("--det-model-dir", type=Path, default=DEFAULT_DETECTION_MODEL_DIR)
    parser.add_argument("--rec-model-dir", type=Path, default=DEFAULT_RECOGNITION_MODEL_DIR)
    parser.add_argument("--text-det-limit-side-len", type=int, default=960)
    parser.add_argument("--text-det-limit-type", default="max")
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--enable-mkldnn", action="store_true")
    args = parser.parse_args(argv)

    split_manifest = json.loads(args.split_manifest.read_text(encoding="utf-8"))
    adapter = create_baseline_ocr_adapter(
        model_home=args.model_home.resolve(),
        text_detection_model_dir=args.det_model_dir.resolve(),
        text_recognition_model_dir=args.rec_model_dir.resolve(),
        text_det_limit_side_len=args.text_det_limit_side_len,
        text_det_limit_type=args.text_det_limit_type,
        enable_mkldnn=args.enable_mkldnn,
        cpu_threads=args.cpu_threads,
    )
    ocr_manifest = recognize_barrier_split_work_units(
        split_manifest,
        adapter=adapter,
        path_base=args.path_base.resolve(),
    )
    ocr_manifest["source_split_manifest"] = str(args.split_manifest.resolve())
    ocr_manifest["path_base"] = str(args.path_base.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ocr_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote split OCR manifest: {args.output.resolve()}")
    print(f"Work units: {ocr_manifest['work_unit_count']}")
    print(f"Adapter: {adapter.engine_id} {adapter.engine_version}")
    print(f"Safe settings: mkldnn={adapter.enable_mkldnn}, side_len={adapter.text_det_limit_side_len}, side_type={adapter.text_det_limit_type}, threads={adapter.cpu_threads}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
