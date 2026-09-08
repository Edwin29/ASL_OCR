from __future__ import annotations

import hashlib
import json
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import cv2
from urllib3.exceptions import InsecureRequestWarning

from asl_device.app_config import DeviceAppConfig
from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.composition import (
    PaddleOpaqueIdentityBackendConfig,
    compose_m1_page_number_provider,
)
from book_scanner.video.page_number_roi import preview_page_number_roi
from book_scanner.video.runtime_composition import (
    _effective_scanner_config,
    _model_hashes,
    create_snapshot_source,
)
from book_scanner.video.types import PageSide

run_root = Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447")
evidence_root = run_root / "evidence" / "footer-roi-diagnostic-01"
evidence_root.mkdir()
config = DeviceAppConfig.from_toml(run_root / "config" / "device-app.h1-camera-console.toml")

source = create_snapshot_source(config.scanner)
started = time.monotonic()
try:
    source.start()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InsecureRequestWarning)
        frame = source.read()
finally:
    source.stop()
if frame is None:
    raise SystemExit("diagnostic snapshot returned no frame")
acquisition_ms = (time.monotonic() - started) * 1000.0

scanner_config = _effective_scanner_config(config.scanner)
analyzed = OpenCVCandidateAnalyzer(scanner_config.candidate).analyze(frame)
provider = compose_m1_page_number_provider(
    scanner_config,
    PaddleOpaqueIdentityBackendConfig(
        model_dir=config.scanner.m1_model_dir,
        expected_file_hashes=_model_hashes(config.scanner.m1_model_manifest),
    ),
)
assert provider is not None
recognition = provider.observe_preview(
    analyzed.gray_preview,
    analyzed.mask_preview,
    analyzed.seam_proxy_fraction,
    frame.frame_id,
    "diagnostic-only",
)

source_path = evidence_root / "source-frame.jpg"
if not cv2.imwrite(str(source_path), frame.payload, [cv2.IMWRITE_JPEG_QUALITY, 95]):
    raise SystemExit("failed to write diagnostic source frame")

roi_records = {}
for side in (PageSide.LEFT, PageSide.RIGHT):
    roi, bbox = preview_page_number_roi(
        analyzed.gray_preview,
        analyzed.mask_preview,
        analyzed.seam_proxy_fraction,
        side,
        scanner_config.page_number,
    )
    path = evidence_root / f"{side.value}-footer-roi.png"
    if not cv2.imwrite(str(path), roi):
        raise SystemExit(f"failed to write {side.value} ROI")
    roi_records[side.value] = {
        "bbox": list(bbox),
        "shape": list(roi.shape),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }

def page_record(page):
    return {
        "side": page.side.value,
        "raw_text": page.raw_text,
        "normalized_label": page.normalized_label,
        "status": page.status.value,
        "confidence": page.confidence,
        "variant_agreement": page.variant_agreement,
        "bbox": list(page.bbox) if page.bbox is not None else None,
        "roi_sha256": page.roi_sha256,
        "engine_id": page.engine_id,
        "engine_version": page.engine_version,
        "preprocessing_version": page.preprocessing_version,
    }

result = {
    "kind": "isolated_live_footer_roi_diagnostic",
    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    "python": sys.executable,
    "source_frame_id": frame.frame_id.value,
    "source_shape": list(frame.payload.shape),
    "source_file_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
    "acquisition_ms": round(acquisition_ms, 3),
    "candidate_retry_reasons": [item.value for item in analyzed.candidate.retry_reasons],
    "candidate_metrics": dict(analyzed.candidate.metrics),
    "seam_proxy_fraction": analyzed.seam_proxy_fraction,
    "spread_status": recognition.status.value,
    "spread_key": (
        {
            "left": recognition.key.left,
            "right": recognition.key.right,
        }
        if recognition.key is not None
        else None
    ),
    "recognition_processing_ms": recognition.processing_ms,
    "pages": [page_record(recognition.left), page_record(recognition.right)],
    "roi_files": roi_records,
    "uploads": 0,
    "product_state_changes": 0,
    "threshold_changes": 0,
    "credential_values_recorded": False,
}
(evidence_root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
