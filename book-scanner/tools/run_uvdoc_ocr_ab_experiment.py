"""Run oracle UVDoc interpolation/postprocess variants through real Document Parser OCR."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from book_scanner.correct.postprocess import LuminanceUnsharpPostprocessor
from book_scanner.correct.uvdoc_adapter import UVDocAdapter, UVDocConfig
from book_scanner.evaluation.ocr_ab_experiment import run_uvdoc_ocr_ab_experiment


DEFAULT_STEMS = (
    "20260826_174943",
    "20260826_174953",
    "20260826_174958",
    "20260826_175109",
)


def _vl_preflight(model_home: Path) -> dict[str, object]:
    official = model_home / ".paddlex" / "official_models"
    candidates = []
    if official.is_dir():
        candidates = sorted(
            str(path)
            for path in official.iterdir()
            if path.is_dir() and "paddleocr-vl" in path.name.casefold()
        )
    return {
        "status": "READY" if candidates else "PADDLEOCR_VL_NOT_VERIFIED",
        "model_home": str(model_home),
        "candidate_model_directories": candidates,
        "automatic_download_attempted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-images-dir", type=Path, default=Path("TESTIMAGES"))
    parser.add_argument("--capture-stem", action="append", dest="capture_stems")
    parser.add_argument("--uvdoc-runtime", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cpu")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-home", type=Path, required=True)
    parser.add_argument("--padding-fraction", type=float, default=0.03)
    args = parser.parse_args()

    stems = tuple(args.capture_stems or DEFAULT_STEMS)
    pairs = [(args.test_images_dir / f"{stem}.jpg", args.test_images_dir / f"{stem}.json") for stem in stems]
    missing = [str(path) for pair in pairs for path in pair if not path.is_file()]
    if missing:
        parser.error(f"missing experiment inputs: {missing}")

    from document_parser.ocr.baseline import (
        DEFAULT_DETECTION_MODEL_NAME,
        DEFAULT_RECOGNITION_MODEL_NAME,
        create_baseline_ocr_adapter,
    )

    official_models = args.model_home / ".paddlex" / "official_models"
    detection_dir = official_models / DEFAULT_DETECTION_MODEL_NAME
    recognition_dir = official_models / DEFAULT_RECOGNITION_MODEL_NAME
    if not detection_dir.is_dir() or not recognition_dir.is_dir():
        parser.error(
            "offline PP-OCRv5 models are missing; automatic model download is disabled: "
            f"detection={detection_dir}, recognition={recognition_dir}"
        )

    ocr_adapter = create_baseline_ocr_adapter(
        model_home=args.model_home,
        text_detection_model_dir=detection_dir,
        text_recognition_model_dir=recognition_dir,
        device="cpu",
    )
    unwarper = UVDocAdapter(UVDocConfig(args.uvdoc_runtime, args.checkpoint, device=args.device))
    summary = run_uvdoc_ocr_ab_experiment(
        pairs,
        args.output_dir,
        unwarper,
        ocr_adapter,
        postprocessor=LuminanceUnsharpPostprocessor(),
        padding_fraction=args.padding_fraction,
    )
    preflight = _vl_preflight(args.model_home)
    (args.output_dir / "paddleocr_vl_preflight.json").write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "expected_page_count": summary["expected_page_count"],
        "uvdoc_load_count": summary["uvdoc_load_count"],
        "automated_postprocess_screen": summary["automated_postprocess_screen"],
        "input_policy": summary["input_policy"]["preferred"],
        "paddleocr_vl": preflight["status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
