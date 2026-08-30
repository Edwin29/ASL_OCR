"""Export an unverified, same-full-frame ROI across Phase A extraction inputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2


BOOK_SCANNER_ROOT = Path(__file__).resolve().parents[1]
if str(BOOK_SCANNER_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(BOOK_SCANNER_ROOT / "src"))

from book_scanner.evaluation.ocr_ab_experiment import sha256_file  # noqa: E402
from book_scanner.evaluation.page_masks import read_image, write_image  # noqa: E402


def _labeled_cell(image, label: str):
    top = 42
    canvas = cv2.copyMakeBorder(image, top, 0, 0, 0, cv2.BORDER_CONSTANT, value=(245, 245, 245))
    cv2.putText(canvas, label, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (20, 20, 20), 2, cv2.LINE_AA)
    return canvas


def unverified_checklist() -> dict[str, dict[str, object | None]]:
    checks = [
        "giyeok_item", "nieun_item", "digeut_item", "rieul_item",
        "choice_1", "choice_2", "choice_3", "choice_4",
        "answer_label_and_value", "explanation_label_and_text", "table_structure",
        "important_formula",
    ]
    return {
        key: {"verified_presence": None, "verified_transcription": None, "reviewer": None, "reviewed_at": None}
        for key in checks
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--capture", default="20260826_174958")
    parser.add_argument("--side", choices=("left", "right"), default="right")
    parser.add_argument("--roi-full", type=int, nargs=4, metavar=("X", "Y", "WIDTH", "HEIGHT"), required=True)
    parser.add_argument("--roi-source-record", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.extraction_manifest.read_text(encoding="utf-8"))
    selected = [
        item for item in manifest.get("artifacts", [])
        if item.get("capture") == args.capture and item.get("side") == args.side
        and item.get("geometry") == "none" and item.get("postprocess") == "none"
    ]
    if len(selected) != 4:
        parser.error(f"expected four Phase A extraction artifacts, found {len(selected)}")
    x, y, width, height = args.roi_full
    if width <= 0 or height <= 0:
        parser.error("ROI width and height must be positive")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    cells = []

    source_path = Path(selected[0]["source"]["image_path"])
    source = read_image(source_path)
    if x < 0 or y < 0 or x + width > source.shape[1] or y + height > source.shape[0]:
        parser.error("full-frame ROI is outside the source image")
    raw_roi = source[y : y + height, x : x + width].copy()
    raw_path = output_dir / "raw_frame_roi.png"
    write_image(raw_path, raw_roi)
    cells.append(_labeled_cell(raw_roi, "raw_frame"))
    records.append({
        "variant": "raw_frame", "artifact_id": None, "path": str(raw_path),
        "sha256": sha256_file(raw_path), "full_frame_bbox": [x, y, width, height],
    })

    for artifact in sorted(selected, key=lambda item: str(item["extraction"])):
        bx, by, bw, bh = (int(value) for value in artifact["bbox_full"])
        if not (bx <= x and by <= y and x + width <= bx + bw and y + height <= by + bh):
            parser.error(f"ROI is not fully covered by {artifact['artifact_id']}")
        image = read_image(Path(artifact["image_path"]))
        lx, ly = x - bx, y - by
        roi = image[ly : ly + height, lx : lx + width].copy()
        path = output_dir / f"{artifact['extraction']}_roi.png"
        write_image(path, roi)
        cells.append(_labeled_cell(roi, str(artifact["extraction"])))
        records.append({
            "variant": artifact["extraction"], "artifact_id": artifact["artifact_id"],
            "path": str(path), "sha256": sha256_file(path),
            "artifact_bbox_full": artifact["bbox_full"],
            "local_bbox": [lx, ly, width, height], "full_frame_bbox": [x, y, width, height],
        })

    contact_sheet = cv2.vconcat(cells)
    contact_path = output_dir / "contact_sheet.png"
    write_image(contact_path, contact_sheet)
    verification = unverified_checklist()
    payload = {
        "schema_version": 1,
        "status": "MANUAL_GOLDEN_NOT_VERIFIED",
        "capture": args.capture,
        "side": args.side,
        "source_image_path": str(source_path.resolve()),
        "source_image_sha256": sha256_file(source_path),
        "roi_full_frame_bbox": [x, y, width, height],
        "roi_selection_provenance": {
            "method": "prior_oracle_page_ir_table_bbox_with_fixed_context_padding",
            "source_record": str(args.roi_source_record.resolve()) if args.roi_source_record else None,
            "source_record_sha256": sha256_file(args.roi_source_record) if args.roi_source_record else None,
            "is_transcription_truth": False,
        },
        "artifacts": records,
        "contact_sheet_path": str(contact_path),
        "contact_sheet_sha256": sha256_file(contact_path),
        "verification": verification,
        "verification_policy": (
            "Null fields are unverified. OCR output and prior report observations must not be copied as truth."
        ),
    }
    manifest_path = output_dir / "golden_roi_manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "manifest": str(manifest_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
