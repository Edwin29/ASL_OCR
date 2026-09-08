from __future__ import annotations

import json
import sys
import time
import traceback
import warnings
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from urllib3.exceptions import InsecureRequestWarning

from asl_device.app_config import DeviceAppConfig
from book_scanner.video.candidate import OpenCVCandidateAnalyzer
from book_scanner.video.composition import PaddleOpaqueIdentityBackendConfig, compose_m1_page_number_provider
from book_scanner.video.engine import _page_number_preview_inputs
from book_scanner.video.opaque_identity import token_pair_from_page_observation
from book_scanner.video.operator_preview import ThreadedPreviewCameraSource
from book_scanner.video.runtime_composition import _effective_scanner_config, _model_hashes, create_snapshot_source


class NullPreview:
    def start(self) -> None:
        pass

    def show(self, frame) -> None:
        pass

    def stop(self) -> None:
        pass


run_root = Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h1-camera-fresh-20260908-101447")
evidence_root = run_root / "evidence" / "footer-30s-native-threaded-query-01"
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
camera = ThreadedPreviewCameraSource(
    create_snapshot_source(config.scanner),
    NullPreview(),
    source_label="android_ip_camera:snapshot:diagnostic",
)
warnings.filterwarnings("ignore", category=InsecureRequestWarning)

result = {
    "kind": "threaded_preview_production_native_query",
    "started_at_utc": datetime.now(timezone.utc).isoformat(),
    "python": sys.executable,
    "expected_operator_pages": "28/29 retained after completed two-phase diagnostic",
    "duration_seconds": 30.0,
    "input_stage": scanner_config.opaque_footer_identity.input_stage.value,
    "maximum_dimension_rule": "max(frame.payload.shape[:2])",
    "query_sample_count_unchanged": scanner_config.opaque_footer_identity.query_sample_count,
    "max_collection_ms_unchanged": scanner_config.opaque_footer_identity.max_collection_ms,
    "threshold_changes": 0,
    "uploads": 0,
    "product_state_changes": 0,
    "credential_values_recorded": False,
    "rows": [],
}

try:
    camera.start()
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        sample = camera.read()
        if sample is None:
            time.sleep(0.01)
            continue
        started = time.monotonic()
        analyzed = analyzer.analyze(sample)
        row = {
            "source_frame_id": sample.frame_id.value,
            "observed_at_monotonic": started,
            "candidate_retry_reasons": [item.value for item in analyzed.candidate.retry_reasons],
        }
        if not analyzed.candidate.retry_reasons:
            maximum = max(sample.payload.shape[:2])
            gray, mask = _page_number_preview_inputs(sample.payload, analyzed.mask_preview, maximum)
            observation = provider.observe_preview(
                gray,
                mask,
                analyzed.seam_proxy_fraction,
                sample.frame_id,
                "diagnostic-only",
            )
            pair = token_pair_from_page_observation(
                observation,
                captured_at_monotonic=sample.captured_at_monotonic,
                recognition_stage=scanner_config.opaque_footer_identity.input_stage.value,
            )
            row.update({
                "left_raw": observation.left.raw_text,
                "right_raw": observation.right.raw_text,
                "left_status": observation.left.status.value,
                "right_status": observation.right.status.value,
                "pair": list(pair.value) if pair is not None else None,
                "recognition_processing_ms": observation.processing_ms,
            })
        row["elapsed_ms"] = round((time.monotonic() - started) * 1000.0, 3)
        result["rows"].append(row)
except BaseException as exc:
    result["error"] = {
        "class": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }
    raise
finally:
    camera.stop()
    pairs = Counter(
        "|".join(row["pair"])
        for row in result["rows"]
        if row.get("pair") is not None
    )
    result["sample_count"] = len(result["rows"])
    result["candidate_eligible_count"] = sum(
        not row.get("candidate_retry_reasons") for row in result["rows"]
    )
    result["complete_pair_count"] = sum(row.get("pair") is not None for row in result["rows"])
    result["pair_counts"] = dict(pairs)
    result["largest_pair_consensus"] = max(pairs.values(), default=0)
    result["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    (evidence_root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

print(json.dumps({key: result[key] for key in (
    "sample_count",
    "candidate_eligible_count",
    "complete_pair_count",
    "pair_counts",
    "largest_pair_consensus",
)}, indent=2))
