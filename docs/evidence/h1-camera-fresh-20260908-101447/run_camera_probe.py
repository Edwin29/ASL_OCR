from __future__ import annotations

import hashlib
import json
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

run_root = Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447")
config_path = run_root / "config" / "device-app.h1-camera-console.toml"

from asl_device.app_config import DeviceAppConfig
from book_scanner.video.runtime_composition import create_snapshot_source

config = DeviceAppConfig.from_toml(config_path)
source = create_snapshot_source(config.scanner)
rows = []
started = datetime.now(timezone.utc).isoformat()
try:
    source.start()
    for attempt in range(1, 4):
        before = time.monotonic()
        try:
            with warnings.catch_warnings(record=True) as caught:
                frame = source.read()
            row = {
                "attempt": attempt,
                "elapsed_seconds": round(time.monotonic() - before, 3),
                "frame": frame is not None,
                "warning_types": sorted({type(item.message).__name__ for item in caught}),
            }
            if frame is not None:
                row.update(
                    {
                        "shape": list(frame.payload.shape),
                        "frame_id": frame.frame_id.value,
                        "pixel_sha256": hashlib.sha256(frame.payload.tobytes()).hexdigest(),
                    }
                )
            rows.append(row)
        except Exception as exc:
            rows.append(
                {
                    "attempt": attempt,
                    "elapsed_seconds": round(time.monotonic() - before, 3),
                    "error_class": type(exc).__name__,
                    "retryable": getattr(exc, "retryable", None),
                    "http_status": getattr(exc, "status_code", None),
                }
            )
            break
        time.sleep(0.6)
finally:
    source.stop()

result = {
    "kind": "strict_read_only_snapshot_probe",
    "started_at_utc": started,
    "completed_at_utc": datetime.now(timezone.utc).isoformat(),
    "python": sys.executable,
    "asl_device_import": sys.modules["asl_device"].__file__,
    "book_scanner_import": sys.modules["book_scanner"].__file__,
    "profile": config.scanner.profile,
    "source_class": type(source).__name__,
    "operator_preview_enabled_in_h1": config.scanner.operator_preview_enabled,
    "snapshot_timeout_seconds": config.scanner.camera_snapshot_timeout_seconds,
    "minimum_dimensions": [
        config.scanner.camera_snapshot_min_width,
        config.scanner.camera_snapshot_min_height,
    ],
    "results": rows,
    "images_saved": 0,
    "uploads": 0,
    "serial_packets": 0,
    "credential_values_recorded": False,
}
(run_root / "evidence" / "camera-probe.json").write_text(
    json.dumps(result, indent=2), encoding="utf-8"
)
print(json.dumps(result, indent=2))
