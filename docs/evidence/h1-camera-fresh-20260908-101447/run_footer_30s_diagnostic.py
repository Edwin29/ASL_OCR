from __future__ import annotations

import hashlib
import json
import sys
import time
import traceback
import warnings
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import cv2
from urllib3.exceptions import InsecureRequestWarning

from asl_device.app_config import DeviceAppConfig
from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.composition import PaddleOpaqueIdentityBackendConfig, compose_m1_page_number_provider
from book_scanner.video.engine import _page_number_preview_inputs
from book_scanner.video.opaque_identity import token_pair_from_page_observation
from book_scanner.video.page_number_roi import preview_page_number_roi
from book_scanner.video.runtime_composition import _effective_scanner_config, _model_hashes, create_snapshot_source
from book_scanner.video.types import PageSide

run_root = Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447")
evidence_root = run_root / "evidence" / "footer-30s-production-input-03"
evidence_root.mkdir()
config = DeviceAppConfig.from_toml(run_root / "config" / "device-app.h1-camera-console.toml")
scanner_config = _effective_scanner_config(config.scanner)
analyzer = OpenCVCandidateAnalyzer(scanner_config.candidate)
provider = compose_m1_page_number_provider(
    scanner_config,
    PaddleOpaqueIdentityBackendConfig(
        model_dir=config.scanner.m1_model_dir,
        expected_file_hashes=_model_hashes(config.scanner.m1_model_manifest),
    ),
)
assert provider is not None
source = create_snapshot_source(config.scanner)
warnings.filterwarnings("ignore", category=InsecureRequestWarning)

result = {
    "kind": "footer_30s_production_input_comparison",
    "started_at_utc": datetime.now(timezone.utc).isoformat(),
    "python": sys.executable,
    "production_config_max_collection_ms": config.scanner.opaque_identity_max_collection_ms,
    "diagnostic_phase_seconds": 30.0,
    "query_sample_count_unchanged": scanner_config.opaque_footer_identity.query_sample_count,
    "input_stage": scanner_config.opaque_footer_identity.input_stage.value,
    "page_number_preview_max_dimension": scanner_config.page_number.preview_max_dimension,
    "threshold_changes": 0,
    "uploads": 0,
    "product_state_changes": 0,
    "credential_values_recorded": False,
    "phases": [],
}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def capture_phase(name: str, pages: str) -> dict:
    input(f"Place pages {pages}, remove hands, hold still, then press Enter: ")
    print(f"Collecting {pages} footer observations for 30 seconds. Do not move the book.", flush=True)
    deadline = time.monotonic() + 30.0
    rows = []
    saved_frame = False
    while time.monotonic() < deadline:
        sample_started = time.monotonic()
        try:
            frame = source.read()
        except Exception as exc:
            rows.append({
                "sample_started": sample_started,
                "elapsed_ms": round((time.monotonic() - sample_started) * 1000.0, 3),
                "error_class": type(exc).__name__,
                "retryable": getattr(exc, "retryable", None),
            })
            continue
        if frame is None:
            rows.append({"sample_started": sample_started, "frame": False})
            continue
        analyzed = analyzer.analyze(frame)
        row = {
            "source_frame_id": frame.frame_id.value,
            "sample_started": sample_started,
            "candidate_retry_reasons": [item.value for item in analyzed.candidate.retry_reasons],
        }
        if not analyzed.candidate.retry_reasons:
            number_gray, number_mask = _page_number_preview_inputs(
                frame.payload,
                analyzed.mask_preview,
                scanner_config.page_number.preview_max_dimension,
            )
            observation = provider.observe_preview(
                number_gray,
                number_mask,
                analyzed.seam_proxy_fraction,
                frame.frame_id,
                "diagnostic-only",
            )
            pair = token_pair_from_page_observation(
                observation,
                captured_at_monotonic=frame.captured_at_monotonic,
                recognition_stage="preview_m1",
            )
            row.update({
                "spread_status": observation.status.value,
                "left_raw": observation.left.raw_text,
                "right_raw": observation.right.raw_text,
                "left_status": observation.left.status.value,
                "right_status": observation.right.status.value,
                "left_roi_sha256": observation.left.roi_sha256,
                "right_roi_sha256": observation.right.roi_sha256,
                "recognition_processing_ms": observation.processing_ms,
                "pair": list(pair.value) if pair is not None else None,
            })
            if not saved_frame:
                frame_path = evidence_root / f"{name}-source-frame.jpg"
                cv2.imwrite(str(frame_path), frame.payload, [cv2.IMWRITE_JPEG_QUALITY, 95])
                row["source_file_sha256"] = sha256(frame_path)
                for side in (PageSide.LEFT, PageSide.RIGHT):
                    roi, _bbox = preview_page_number_roi(
                        number_gray,
                        number_mask,
                        analyzed.seam_proxy_fraction,
                        side,
                        scanner_config.page_number,
                    )
                    roi_path = evidence_root / f"{name}-{side.value}-footer-roi.png"
                    cv2.imwrite(str(roi_path), roi)
                    row[f"{side.value}_roi_file_sha256"] = sha256(roi_path)
                saved_frame = True
        row["elapsed_ms"] = round((time.monotonic() - sample_started) * 1000.0, 3)
        rows.append(row)
    pair_counts = Counter(
        "|".join(row["pair"])
        for row in rows
        if row.get("pair") is not None
    )
    phase = {
        "name": name,
        "pages": pages,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(rows),
        "candidate_eligible_count": sum(not row.get("candidate_retry_reasons", ()) for row in rows if row.get("source_frame_id")),
        "complete_pair_count": sum(row.get("pair") is not None for row in rows),
        "pair_counts": dict(pair_counts),
        "largest_pair_consensus": max(pair_counts.values(), default=0),
        "rows": rows,
    }
    print(json.dumps({key: phase[key] for key in ("pages", "sample_count", "candidate_eligible_count", "complete_pair_count", "pair_counts", "largest_pair_consensus")}, ensure_ascii=False, indent=2), flush=True)
    return phase

try:
    source.start()
    result["phases"].append(capture_phase("reference", "26/27"))
    result["phases"].append(capture_phase("query", "28/29"))
except BaseException as exc:
    result["error"] = {
        "class": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }
    raise
finally:
    try:
        source.stop()
    except BaseException as exc:
        result["stop_error"] = {
            "class": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    result["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    (evidence_root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

print("Footer comparison complete. Leave this window open for evidence collection.", flush=True)
