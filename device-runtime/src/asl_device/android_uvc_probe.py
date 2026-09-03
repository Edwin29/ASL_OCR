"""Read-only Android UVC enumeration and live-frame probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .app_config import DeviceAppConfig, ScannerHostConfig


class ProbeSource(Protocol):
    selected_camera: Any
    effective_mode: dict[str, float | str] | None

    def start(self) -> None: ...

    def read(self) -> Any: ...

    def stop(self) -> None: ...


ProbeSourceFactory = Callable[[ScannerHostConfig], ProbeSource]


def list_android_uvc_devices(backend: str = "auto") -> dict[str, Any]:
    from book_scanner.video.camera_host import enumerate_camera_devices

    devices = enumerate_camera_devices(backend)
    return {
        "schema_version": 1,
        "kind": "android_uvc_camera_list",
        "host": {"system": platform.system(), "release": platform.release()},
        "backend_requested": backend,
        "device_count": len(devices),
        "devices": [device.as_report() for device in devices],
    }


def run_android_uvc_probe(
    config_path: str | Path,
    *,
    sample_count: int = 10,
    interval_ms: int = 100,
    source_factory: ProbeSourceFactory | None = None,
) -> dict[str, Any]:
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or not 1 <= sample_count <= 100:
        raise ValueError("sample_count must be an integer in [1, 100]")
    if isinstance(interval_ms, bool) or not isinstance(interval_ms, int) or not 0 <= interval_ms <= 5_000:
        raise ValueError("interval_ms must be an integer in [0, 5000]")
    config = DeviceAppConfig.from_toml(config_path)
    if config.scanner.profile != "android_uvc":
        raise ValueError("Android UVC probe requires scanner.profile=android_uvc")
    factory = source_factory or _default_probe_source
    source = factory(config.scanner)
    started = time.monotonic()
    try:
        source.start()
        digests: list[str] = []
        arrivals: list[float] = []
        shapes: list[list[int]] = []
        frame_ids: list[str] = []
        for index in range(sample_count):
            sample = source.read()
            if sample is None:
                raise RuntimeError("Android UVC camera returned no frame")
            payload = np.ascontiguousarray(sample.payload)
            digests.append(hashlib.sha256(payload.tobytes()).hexdigest())
            arrivals.append(float(sample.captured_at_monotonic))
            shapes.append([int(value) for value in payload.shape])
            frame_ids.append(sample.frame_id.value)
            if index + 1 < sample_count and interval_ms:
                time.sleep(interval_ms / 1000.0)
        selected = source.selected_camera
        if selected is None:
            raise RuntimeError("Android UVC source did not expose its selected device")
        stable_id = selected.device.stable_id
        intervals = [
            round((current - previous) * 1000.0, 3)
            for previous, current in zip(arrivals, arrivals[1:])
        ]
        return {
            "schema_version": 1,
            "kind": "android_uvc_camera_probe",
            "status": "passed",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_profile": config.scanner.profile,
            "replay_path_used": False,
            "host": {"system": platform.system(), "release": platform.release()},
            "camera": {
                "name": selected.device.name,
                "identity_digest": hashlib.sha256(stable_id.encode("utf-8")).hexdigest()[:16],
                "backend": selected.device.backend,
                "selection_method": selected.selection_method,
                "open_target_kind": "index" if isinstance(selected.open_target, int) else "path",
                "requested_mode": {
                    "width": config.scanner.camera_width,
                    "height": config.scanner.camera_height,
                    "fps": config.scanner.camera_fps,
                    "fourcc": config.scanner.camera_fourcc,
                    "rotation": config.scanner.camera_rotation,
                    "mirror": config.scanner.camera_mirror,
                },
                "effective_mode": source.effective_mode,
            },
            "samples": {
                "count": len(digests),
                "unique_frame_digests": len(set(digests)),
                "liveness_observed": len(set(digests)) > 1,
                "frame_ids_monotonic": frame_ids
                == [f"android-uvc-{index:08d}" for index in range(1, sample_count + 1)],
                "shapes": shapes,
                "arrival_intervals_ms": intervals,
            },
            "elapsed_ms": round((time.monotonic() - started) * 1000.0, 3),
        }
    finally:
        source.stop()


def write_android_uvc_report(report: dict[str, Any], path: str | Path) -> None:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _default_probe_source(config: ScannerHostConfig) -> ProbeSource:
    from book_scanner.video.camera_host import AndroidUvcCameraSource

    assert config.camera_selector is not None
    return AndroidUvcCameraSource(
        config.camera_selector,
        backend=config.camera_backend,
        fallback_index=config.camera_fallback_index,
        width=config.camera_width,
        height=config.camera_height,
        fps=config.camera_fps,
        fourcc=config.camera_fourcc,
        rotation=config.camera_rotation,
        mirror=config.camera_mirror,
        warmup_frames=config.camera_warmup_frames,
        reopen_attempts=config.camera_reopen_attempts,
        reopen_initial_ms=config.camera_reopen_initial_ms,
        drain_grabs=0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="List OS camera identities")
    mode.add_argument("--config", help="Probe the android_uvc profile in this Device TOML")
    parser.add_argument("--backend", default="auto", help="auto, dshow, msmf, or v4l2")
    parser.add_argument("--report", help="Write the JSON result to this path")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--interval-ms", type=int, default=100)
    args = parser.parse_args()
    try:
        report = (
            list_android_uvc_devices(args.backend)
            if args.list
            else run_android_uvc_probe(
                args.config,
                sample_count=args.samples,
                interval_ms=args.interval_ms,
            )
        )
    except Exception as exc:
        report = {
            "schema_version": 1,
            "kind": "android_uvc_camera_probe",
            "status": "failed",
            "error_type": type(exc).__name__,
            "failure": str(exc),
        }
        exit_code = 2
    else:
        exit_code = 0
    if args.report:
        write_android_uvc_report(report, args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
