"""Executable E0-B Laptop preflight checks with secret-safe JSON evidence."""

from __future__ import annotations

import json
import platform
import time
import urllib.request
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .adapters.local_feedback import WindowsAudioBackend
from .adapters.stm_serial import _open_serial
from .app_config import DeviceAppConfig
from .local_composition import _default_scanner_factory

Probe = Callable[[DeviceAppConfig], dict[str, Any]]


def run_laptop_preflight(
    config_path: str | Path,
    *,
    probe_overrides: Mapping[str, Probe] | None = None,
) -> dict[str, Any]:
    """Run bounded hardware/environment checks without starting a scan session."""

    config = DeviceAppConfig.from_toml(config_path)
    overrides = dict(probe_overrides or {})
    probes: tuple[tuple[str, Probe], ...] = (
        ("e0b_profile", _probe_e0b_profile),
        ("scanner_models", _probe_scanner_models),
        ("server_health", _probe_server_health),
        ("camera", _probe_camera),
        ("stm_serial", _probe_stm_serial),
        ("windows_audio", _probe_windows_audio),
    )
    checks: list[dict[str, Any]] = []
    for name, default_probe in probes:
        started = time.monotonic()
        try:
            detail = (overrides.get(name) or default_probe)(config)
            checks.append(
                {
                    "name": name,
                    "status": "passed",
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                    "detail": detail,
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "name": name,
                    "status": "failed",
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                    "error_type": type(exc).__name__,
                    "detail": str(exc),
                }
            )
    return {
        "schema_version": 1,
        "packet": "Device Integration E0-B — Laptop Acceptance",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "python": platform.python_version(),
        },
        "device_id": config.connectivity.device_id.value,
        "passed": all(check["status"] == "passed" for check in checks),
        "checks": checks,
    }


def write_laptop_preflight_report(report: Mapping[str, Any], path: str | Path) -> None:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _probe_e0b_profile(config: DeviceAppConfig) -> dict[str, Any]:
    if config.scanner.profile != "pc_camera":
        raise ValueError("E0-B requires scanner.profile=pc_camera")
    if config.controls_mode != "stm_serial" or config.stm_serial is None:
        raise ValueError("E0-B requires local_io.controls=stm_serial")
    if config.feedback_mode != "windows_audio":
        raise ValueError("E0-B requires local_io.feedback=windows_audio")
    if config.scanner.camera_width is None or config.scanner.camera_height is None:
        raise ValueError("E0-B requires an explicit camera_width and camera_height")
    endpoint = urlsplit(config.connectivity.server_base_url)
    if endpoint.scheme != "https":
        raise ValueError("remote E0-B requires an HTTPS server origin")
    if endpoint.hostname in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("remote E0-B requires a non-loopback server origin")
    return {
        "camera_index": config.scanner.camera_index,
        "camera_width": config.scanner.camera_width,
        "camera_height": config.scanner.camera_height,
        "camera_fps": config.scanner.camera_fps,
        "stm_port": config.stm_serial.port,
        "braille_cells": config.stm_serial.cell_count,
        "server_origin": config.connectivity.server_base_url,
    }


def _probe_scanner_models(config: DeviceAppConfig) -> dict[str, Any]:
    factory = _default_scanner_factory(config.scanner)
    return {"factory": type(factory).__name__, "assets_loaded": True}


def _probe_server_health(config: DeviceAppConfig) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{config.connectivity.server_base_url}/api/v1/health",
        method="GET",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=config.connectivity.connect_timeout_seconds) as response:
        body = response.read(65537)
        if response.status != 200 or len(body) > 65536:
            raise RuntimeError(f"server health returned HTTP {response.status} or an oversized body")
        payload = json.loads(body)
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise RuntimeError("server health response is not an ok JSON object")
    return {"origin": config.connectivity.server_base_url, "http_status": 200}


def _probe_camera(config: DeviceAppConfig) -> dict[str, Any]:
    from book_scanner.video.sources import OpenCVCameraSource

    source = OpenCVCameraSource(
        config.scanner.camera_index,
        width=config.scanner.camera_width,
        height=config.scanner.camera_height,
        fps=config.scanner.camera_fps,
        drain_grabs=0,
    )
    try:
        source.start()
        sample = source.read()
        if sample is None:
            raise RuntimeError("camera returned no frame")
        height, width = sample.payload.shape[:2]
        return {"width": int(width), "height": int(height), "frame_id": sample.frame_id.value}
    finally:
        source.stop()


def _probe_stm_serial(config: DeviceAppConfig) -> dict[str, Any]:
    assert config.stm_serial is not None
    connection = _open_serial(config.stm_serial)
    try:
        return {"port": config.stm_serial.port, "baudrate": config.stm_serial.baudrate}
    finally:
        connection.close()


def _probe_windows_audio(config: DeviceAppConfig) -> dict[str, Any]:
    backend = WindowsAudioBackend(config.laptop_audio.powershell_executable)
    backend.beep(((880, 100),))
    backend.speak("노트북 장치 오디오 확인")
    return {"beep": True, "speech": True}
