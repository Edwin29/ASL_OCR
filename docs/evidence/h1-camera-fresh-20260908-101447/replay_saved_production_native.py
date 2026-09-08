from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2

from asl_device.app_config import DeviceAppConfig
from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.composition import PaddleOpaqueIdentityBackendConfig, compose_m1_page_number_provider
from book_scanner.video.engine import _page_number_preview_inputs
from book_scanner.video.opaque_identity import token_pair_from_page_observation
from book_scanner.video.page_number_roi import preview_page_number_roi
from book_scanner.video.protocols import FrameSample
from book_scanner.video.runtime_composition import _effective_scanner_config, _model_hashes
from book_scanner.video.types import FrameId, PageSide

run_root = Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447")
source_root = run_root / "evidence" / "footer-30s-production-input-03"
evidence_root = run_root / "evidence" / "footer-saved-production-native-02"
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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


rows = []
for phase in ("reference", "query"):
    path = source_root / f"{phase}-source-frame.jpg"
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError(f"failed to decode {path.name}")
    frame_id = FrameId(f"saved-{phase}")
    sample = FrameSample(frame_id, 1.0, frame)
    analyzed = analyzer.analyze(sample)
    maximum = max(frame.shape[:2])
    number_gray, number_mask = _page_number_preview_inputs(
        frame,
        analyzed.mask_preview,
        maximum,
    )
    observation = provider.observe_preview(
        number_gray,
        number_mask,
        analyzed.seam_proxy_fraction,
        frame_id,
        "diagnostic-only",
    )
    pair = token_pair_from_page_observation(
        observation,
        captured_at_monotonic=1.0,
        recognition_stage=scanner_config.opaque_footer_identity.input_stage.value,
    )
    row = {
        "phase": phase,
        "source_file": path.name,
        "source_sha256": digest(path),
        "source_shape": list(frame.shape),
        "input_stage": scanner_config.opaque_footer_identity.input_stage.value,
        "maximum_dimension_argument": maximum,
        "recognition_processing_ms": observation.processing_ms,
        "spread_status": observation.status.value,
        "left_status": observation.left.status.value,
        "left_raw": observation.left.raw_text,
        "right_status": observation.right.status.value,
        "right_raw": observation.right.raw_text,
        "pair": list(pair.value) if pair is not None else None,
        "candidate_retry_reasons": [item.value for item in analyzed.candidate.retry_reasons],
    }
    for side in (PageSide.LEFT, PageSide.RIGHT):
        roi, bbox = preview_page_number_roi(
            number_gray,
            number_mask,
            analyzed.seam_proxy_fraction,
            side,
            scanner_config.page_number,
        )
        roi_path = evidence_root / f"{phase}-{side.value}-footer-roi.png"
        if not cv2.imwrite(str(roi_path), roi):
            raise RuntimeError(f"failed to write {roi_path.name}")
        row[f"{side.value}_roi_bbox"] = list(bbox)
        row[f"{side.value}_roi_sha256"] = digest(roi_path)
    rows.append(row)

result = {
    "kind": "saved_frame_production_native_replay",
    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    "python": sys.executable,
    "uploads": 0,
    "product_state_changes": 0,
    "threshold_changes": 0,
    "scope_limit": "first saved frame from each 30-second phase only",
    "rows": rows,
}
(evidence_root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
