from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import cv2

from asl_device.app_config import DeviceAppConfig
from book_scanner.video.composition import PaddleOpaqueIdentityBackendConfig, compose_m1_page_number_provider
from book_scanner.video.runtime_composition import _effective_scanner_config, _model_hashes
from book_scanner.video.types import PageSide

run_root = Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447")
roi_root = run_root / "evidence" / "footer-30s-comparison-01"
config = DeviceAppConfig.from_toml(run_root / "config" / "device-app.h1-camera-console.toml")
scanner_config = _effective_scanner_config(config.scanner)
provider = compose_m1_page_number_provider(
    scanner_config,
    PaddleOpaqueIdentityBackendConfig(
        model_dir=config.scanner.m1_model_dir,
        expected_file_hashes=_model_hashes(config.scanner.m1_model_manifest),
    ),
)
assert provider is not None
recognizer = provider.recognizer

rows = []
for phase in ("reference", "query"):
    for side in (PageSide.LEFT, PageSide.RIGHT):
        path = roi_root / f"{phase}-{side.value}-footer-roi.png"
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise SystemExit(f"cannot read {path}")
        for scale in (1, 2, 3, 4):
            scaled = image if scale == 1 else cv2.resize(
                image, None, fx=float(scale), fy=float(scale), interpolation=cv2.INTER_CUBIC
            )
            observation = recognizer.recognize(scaled, side)
            rows.append({
                "phase": phase,
                "expected_page": {("reference", "left"): "26", ("reference", "right"): "27", ("query", "left"): "28", ("query", "right"): "29"}[(phase, side.value)],
                "side": side.value,
                "scale": scale,
                "input_shape": list(scaled.shape),
                "raw_text": observation.raw_text,
                "confidence": observation.confidence,
                "variant_agreement": observation.variant_agreement,
                "status": observation.status.value,
                "bbox": list(observation.bbox) if observation.bbox is not None else None,
            })

result = {
    "kind": "saved_footer_roi_scaled_m1_replay",
    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    "preprocessing_only": True,
    "product_files_modified": 0,
    "rows": rows,
}
path = run_root / "evidence" / "footer-scaled-m1-replay.json"
path.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
