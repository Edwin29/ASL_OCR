from __future__ import annotations

import ctypes
import faulthandler
import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import sounddevice as sd

from asl_device.adapters.local_controls import ConsoleControlSource
from asl_device.adapters.local_feedback import (
    CompositeFeedbackSink,
    JsonLineFeedbackSink,
    JsonLineReadingPresenter,
)
from asl_device.app_config import DeviceAppConfig
from asl_device.local_composition import build_local_device
from asl_device.types import DeviceOperatingMode

RUN_ROOT = Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\audio-console-20260908-163539")
CONFIG = RUN_ROOT / "config" / "device-app.h1-camera-console.toml"
LOG = RUN_ROOT / "logs" / "audio-console-events.jsonl"
LIFECYCLE = RUN_ROOT / "evidence" / "interactive-lifecycle.json"
FAULT_LOG = RUN_ROOT / "logs" / "python-faulthandler.log"

_fault_handle = FAULT_LOG.open("a", encoding="utf-8", buffering=1)
_fault_handle.write(f"\n=== {utc_now() if 'utc_now' in globals() else datetime.now(timezone.utc).isoformat()} process={os.getpid()} ===\n")
_fault_handle.flush()
faulthandler.enable(file=_fault_handle, all_threads=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_id() -> int | None:
    value = ctypes.c_ulong()
    if ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(value)):
        return int(value.value)
    return None


def safe_device() -> dict[str, object]:
    default = sd.default.device
    try:
        output_index = int(default[1])
    except (IndexError, TypeError):
        output_index = int(default)
    info = sd.query_devices(output_index)
    host = sd.query_hostapis(int(info["hostapi"]))
    return {
        "output_index": output_index,
        "output_name": str(info["name"]),
        "hostapi_index": int(info["hostapi"]),
        "hostapi_name": str(host["name"]),
        "default_samplerate": float(info["default_samplerate"]),
        "max_output_channels": int(info["max_output_channels"]),
    }


def emit_record(handle, payload: dict[str, object]) -> None:
    line = json.dumps(payload, ensure_ascii=False)
    print(line, flush=True)
    handle.write(line + "\n")
    handle.flush()


class MultiPresenter:
    def __init__(self, *presenters) -> None:
        self.presenters = presenters

    def present(self, snapshot) -> None:
        for presenter in self.presenters:
            presenter.present(snapshot)

    def close(self) -> None:
        for presenter in reversed(self.presenters):
            presenter.close()


cfg = DeviceAppConfig.from_toml(CONFIG)
if cfg.controls_mode != "console":
    raise RuntimeError("1B requires parsed console controls")
if not cfg.reading_audio.enabled or cfg.reading_audio.backend != "sounddevice":
    raise RuntimeError("1B requires production sounddevice reading audio")

with LOG.open("a", encoding="utf-8", buffering=1) as log:
    control_namespace = f"audio-console-{uuid.uuid4().hex}"
    controls = ConsoleControlSource(event_namespace=control_namespace)
    feedback = CompositeFeedbackSink(JsonLineFeedbackSink(sys.stdout), JsonLineFeedbackSink(log))
    presenter = MultiPresenter(JsonLineReadingPresenter(sys.stdout), JsonLineReadingPresenter(log))
    started = utc_now()
    audio_device = safe_device()
    emit_record(log, {
        "type": "audio_console_start",
        "started_at_utc": started,
        "run_id": RUN_ROOT.name,
        "windows_session_id": session_id(),
        "python": sys.executable,
        "source_root": str(Path.cwd()),
        "config": str(CONFIG),
        "initial_mode": "reading",
        "controls": "ConsoleControlSource",
        "control_event_namespace": control_namespace,
        "presenter": "JsonLineReadingPresenter",
        "audio": "ReadingAudioController(SoundDeviceWavPlayer)",
        "audio_device": audio_device,
        "stm_opened": False,
        "camera_started": False,
    })
    if "Realtek(R) Audio" not in str(audio_device["output_name"]):
        emit_record(log, {
            "type": "audio_output_preflight_failed",
            "started_at_utc": started,
            "expected_output": "Realtek(R) Audio",
            "observed_output": audio_device["output_name"],
        })
        raise RuntimeError("1B requires the Laptop Realtek speaker as the default output")
    composition = build_local_device(
        CONFIG,
        controls=controls,
        presenter=presenter,
        feedback=feedback,
        initial_mode=DeviceOperatingMode.READING,
    )
    error = None
    try:
        composition.application.run()
    except KeyboardInterrupt:
        composition.application.stop()
    except BaseException as exc:
        error = {
            "class": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        raise
    finally:
        try:
            composition.application.stop()
        except BaseException as exc:
            if error is None:
                error = {
                    "class": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
        snapshot = composition.coordinator.reading_snapshot
        audio = composition.reading_audio
        lifecycle = {
            "schema_version": 1,
            "run_id": RUN_ROOT.name,
            "started_at_utc": started,
            "completed_at_utc": utc_now(),
            "windows_session_id": session_id(),
            "audio_device": audio_device,
            "coordinator_state": composition.coordinator.state.value,
            "cursor_at_exit": dict(snapshot.cursor) if snapshot is not None else None,
            "application_exit_code": composition.application.exit_code,
            "presentation_failures": composition.application.presentation_failures,
            "audio_worker_alive_after_stop": bool(audio._worker.is_alive()) if audio is not None else None,
            "audio_close_complete": bool(audio._close_complete) if audio is not None else None,
            "error": error,
        }
        LIFECYCLE.write_text(json.dumps(lifecycle, ensure_ascii=False, indent=2), encoding="utf-8")
        emit_record(log, {"type": "audio_console_stop", **lifecycle})
