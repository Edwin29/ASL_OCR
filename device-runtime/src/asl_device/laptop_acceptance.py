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

from .adapters.reading_audio import (
    S0SystemAudioResourceHttpAdapter,
    SoundDeviceWavPlayer,
)
from .adapters.stm_serial import _open_serial
from .app_config import DeviceAppConfig
from .local_composition import _default_scanner_factory

Probe = Callable[[DeviceAppConfig], dict[str, Any]]


def run_laptop_preflight(
    config_path: str | Path,
    *,
    probe_overrides: Mapping[str, Probe] | None = None,
    play_audio: bool = True,
) -> dict[str, Any]:
    """Run config-driven Laptop checks without starting a scan session.

    Console/webcam profiles deliberately skip the STM probe.  Both console and
    STM profiles use the authenticated S0 Piper WAV path; the old SAPI smoke is
    no longer an E0-B preflight authority.
    """

    config = DeviceAppConfig.from_toml(config_path)
    overrides = dict(probe_overrides or {})
    probes: list[tuple[str, Probe]] = [
        ("e0b_profile", _probe_e0b_profile),
        ("scanner_models", _probe_scanner_models),
        ("server_health", _probe_server_health),
        ("camera", _probe_camera),
    ]
    if config.controls_mode == "stm_serial":
        probes.append(("stm_serial", _probe_stm_serial))
    probes.append(
        (
            "piper_audio",
            lambda current: _probe_piper_audio(current, play_audio=play_audio),
        )
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
        "packet": "Device Integration E0-B — Conditional Laptop Preflight",
        "test_profile": (
            "hardware" if config.controls_mode == "stm_serial" else "webcam"
        ),
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
    if config.scanner.profile not in {"pc_camera", "android_uvc"}:
        raise ValueError("physical E0-B requires pc_camera or android_uvc")
    if config.controls_mode not in {"console", "stm_serial"}:
        raise ValueError("E0-B controls must be console or stm_serial")
    if config.feedback_mode != "jsonl":
        raise ValueError("Piper E0-B requires local_io.feedback=jsonl")
    if not config.reading_audio.enabled:
        raise ValueError("Piper E0-B requires local_io.reading_audio.enabled=true")
    if config.reading_audio.backend != "sounddevice":
        raise ValueError("Piper E0-B requires the sounddevice playback backend")
    if config.scanner.camera_width is None or config.scanner.camera_height is None:
        raise ValueError("E0-B requires an explicit camera_width and camera_height")
    endpoint = urlsplit(config.connectivity.server_base_url)
    if endpoint.scheme != "https":
        raise ValueError("remote E0-B requires an HTTPS server origin")
    if endpoint.hostname in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("remote E0-B requires a non-loopback server origin")
    detail: dict[str, Any] = {
        "test_profile": (
            "hardware" if config.controls_mode == "stm_serial" else "webcam"
        ),
        "scanner_profile": config.scanner.profile,
        "camera_width": config.scanner.camera_width,
        "camera_height": config.scanner.camera_height,
        "camera_fps": config.scanner.camera_fps,
        "operator_preview_enabled": config.scanner.operator_preview_enabled,
        "operator_preview_max_width": config.scanner.operator_preview_max_width,
        "controls": config.controls_mode,
        "audio_transport": "authenticated_s0_wav",
        "audio_backend": config.reading_audio.backend,
        "server_origin": config.connectivity.server_base_url,
    }
    if config.scanner.profile == "android_uvc":
        detail["camera_selector"] = config.scanner.camera_selector
        detail["camera_backend"] = config.scanner.camera_backend
        detail["camera_fallback_index"] = config.scanner.camera_fallback_index
    else:
        detail["camera_index"] = config.scanner.camera_index
    if config.stm_serial is not None:
        detail["stm_port"] = config.stm_serial.port
        detail["braille_cells"] = config.stm_serial.cell_count
    return detail


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
    if config.scanner.profile == "android_uvc":
        from .android_uvc_probe import run_android_uvc_probe

        report = run_android_uvc_probe(
            config.config_path,
            sample_count=3,
            interval_ms=50,
        )
        return {
            "source_profile": report["source_profile"],
            "camera": report["camera"],
            "samples": report["samples"],
        }

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


def _probe_piper_audio(
    config: DeviceAppConfig,
    *,
    play_audio: bool,
) -> dict[str, Any]:
    if not config.reading_audio.enabled:
        raise ValueError("Piper audio transport is disabled")
    audio = config.reading_audio
    resource_port = S0SystemAudioResourceHttpAdapter(
        config.connectivity.server_base_url,
        config.connectivity.load_api_key(),
        timeout_seconds=audio.request_timeout_seconds,
        max_resource_bytes=audio.max_resource_bytes,
        chunk_bytes=audio.download_chunk_bytes,
    )
    resource = resource_port.fetch(
        config.connectivity.device_id,
        "s0-system-cue:screen.capture_catalog",
        lambda: False,
    )
    if play_audio:
        player = SoundDeviceWavPlayer()
        try:
            player.play(resource, lambda: False)
        finally:
            player.close()
    return {
        "transport": "authenticated_s0_wav",
        "cue": "screen.capture_catalog",
        "content_length": resource.content_length,
        "sample_rate": resource.sample_rate,
        "channels": resource.channels,
        "duration_ms": resource.duration_ms,
        "playback_requested": play_audio,
    }
