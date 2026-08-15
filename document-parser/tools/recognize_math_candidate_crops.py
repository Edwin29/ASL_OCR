from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_parser.math import create_baseline_formula_ocr_adapter, recognize_math_candidate_crops


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run baseline formula OCR (PP-FormulaNet_plus-M) on exported math candidate crops."
    )
    parser.add_argument("--crop-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--path-base", type=Path, default=Path("."))
    parser.add_argument("--model-home", type=Path, default=None)
    parser.add_argument("--model-dir", type=Path, default=None)
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--enable-mkldnn", action="store_true")
    args = parser.parse_args(argv)

    manifest = json.loads(args.crop_manifest.read_text(encoding="utf-8"))
    kwargs: dict[str, object] = {"cpu_threads": args.cpu_threads, "enable_mkldnn": args.enable_mkldnn}
    if args.model_home is not None:
        kwargs["model_home"] = args.model_home.resolve()
    if args.model_dir is not None:
        kwargs["model_dir"] = args.model_dir.resolve()
    adapter = create_baseline_formula_ocr_adapter(**kwargs)

    recognized = recognize_math_candidate_crops(manifest, adapter=adapter, path_base=args.path_base.resolve())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(recognized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.output.resolve()}")
    print(f"Crops recognized: {recognized['crop_count']}")
    print(f"Trusted: {recognized['trusted_crop_count']}")
    print(f"Untrusted (flagged): {recognized['untrusted_crop_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
