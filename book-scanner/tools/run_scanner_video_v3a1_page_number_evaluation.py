"""Evaluate V3-A.1 bottom-ROI recognizers on committed V2 artifacts."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path

import cv2

from book_scanner.video.config import PageNumberPolicy
from book_scanner.video.page_number_recognizer import (
    OpenCVHogDigitRecognizer,
    PaddleRoiDigitRecognizer,
    _candidate_regions,
)
from book_scanner.video.page_number_roi import corrected_page_number_roi
from book_scanner.video.types import PageSide


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready-dir", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--backend", choices=("opencv", "paddle", "tesseract-cli"), required=True)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--tesseract-exe", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    policy = PageNumberPolicy()
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    expected = {side: labels["labels"][side]["value"] for side in ("left", "right")}
    load_started = time.perf_counter()
    if args.backend == "paddle":
        if args.model_dir is None:
            parser.error("--model-dir is required for paddle")
        recognizer = PaddleRoiDigitRecognizer(args.model_dir, policy)
    elif args.backend == "opencv":
        recognizer = OpenCVHogDigitRecognizer(policy)
    else:
        if args.tesseract_exe is None or not args.tesseract_exe.is_file():
            parser.error("--tesseract-exe must point to tesseract.exe")
        recognizer = _TesseractCliPilot(args.tesseract_exe, policy)
    load_ms = (time.perf_counter() - load_started) * 1000.0

    results = []
    latencies = []
    for manifest_path in sorted(args.ready_dir.resolve().glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_result = {"artifact_id": manifest_path.parent.name, "sides": {}}
        started = time.perf_counter()
        for side in (PageSide.LEFT, PageSide.RIGHT):
            image = cv2.imread(str(manifest_path.parent / side.value / "uvdoc.jpg"), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"cannot read {side.value} uvdoc for {manifest_path.parent.name}")
            roi, roi_bbox = corrected_page_number_roi(image, side, policy)
            side_started = time.perf_counter()
            recognition = recognizer.recognize(roi, side)
            side_ms = (time.perf_counter() - side_started) * 1000.0
            artifact_result["sides"][side.value] = {
                "expected": expected[side.value],
                "raw_text": recognition.raw_text,
                "correct": recognition.raw_text == expected[side.value],
                "confidence": recognition.confidence,
                "variant_agreement": recognition.variant_agreement,
                "status": recognition.status.value,
                "roi_bbox": roi_bbox,
                "candidate_bbox": recognition.bbox,
                "latency_ms": round(side_ms, 3),
            }
        spread_ms = (time.perf_counter() - started) * 1000.0
        artifact_result["spread_latency_ms"] = round(spread_ms, 3)
        latencies.append(spread_ms)
        results.append(artifact_result)

    checks = [side for item in results for side in item["sides"].values()]
    payload = {
        "schema_version": 1,
        "backend": args.backend,
        "engine_id": recognizer.engine_id,
        "engine_version": recognizer.engine_version,
        "preprocessing_version": recognizer.preprocessing_version,
        "load_count": recognizer.load_count,
        "cold_load_ms": round(load_ms, 3),
        "label_scope": labels,
        "accuracy": {
            "correct": sum(item["correct"] for item in checks),
            "total": len(checks),
            "left_user_confirmed_correct": sum(
                item["sides"]["left"]["correct"] for item in results
            ),
            "left_user_confirmed_total": len(results),
            "right_diagnostic_correct": sum(
                item["sides"]["right"]["correct"] for item in results
            ),
            "right_diagnostic_total": len(results),
        },
        "pc_performance": {
            "spread_latency_ms": [round(value, 3) for value in latencies],
            "median_ms": round(statistics.median(latencies), 3) if latencies else None,
            "max_observed_ms": round(max(latencies), 3) if latencies else None,
            "provisional_median_goal_ms": 50,
            "provisional_p95_goal_ms": 100,
            "raspberry_pi_measured": False,
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


class _TesseractCliPilot:
    engine_id = "tesseract-cli-pilot"
    engine_version = "5.5.3"
    preprocessing_version = "footer-component-roi-cli-v1"

    def __init__(self, executable: Path, policy: PageNumberPolicy) -> None:
        self.executable = executable
        self.policy = policy
        self.load_count = 0

    def recognize(self, roi, side):
        from book_scanner.video.page_number import PageNumberRecognition, PageNumberStatus

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        regions = _candidate_regions(gray, side, self.policy.max_digits)
        if not regions:
            return PageNumberRecognition(None, None, None, 0, PageNumberStatus.NOT_OBSERVED)
        x, y, w, h = regions[0]
        crop = gray[y : y + h, x : x + w]
        pad = max(8, round(h * 0.4))
        crop = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
        crop = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        ok, encoded = cv2.imencode(".png", crop)
        if not ok:
            return PageNumberRecognition(None, None, None, 0, PageNumberStatus.NOT_OBSERVED)
        completed = subprocess.run(
            [
                str(self.executable),
                "stdin",
                "stdout",
                "--psm",
                "7",
                "-l",
                "eng",
                "-c",
                "tessedit_char_whitelist=0123456789",
            ],
            input=encoded.tobytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        text = completed.stdout.decode("utf-8", errors="ignore").strip()
        valid = text if text.isascii() and text.isdigit() else None
        return PageNumberRecognition(
            valid,
            None,
            (x, y, w, h) if valid else None,
            1 if valid else 0,
            PageNumberStatus.OBSERVED if valid else PageNumberStatus.NOT_OBSERVED,
        )


if __name__ == "__main__":
    raise SystemExit(main())
