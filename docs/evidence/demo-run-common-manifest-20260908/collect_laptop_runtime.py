"""Read-only, credential-safe Laptop runtime inventory for the run manifest."""
import importlib.util
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
helper_path = HERE.parent / "software-diagnostic-20260908" / "collect_identity.py"
spec = importlib.util.spec_from_file_location("identity_helper", helper_path)
helper = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(helper)

code = r'''
import ctypes
import hashlib
import json
import os
import pathlib
import subprocess
import sys

import serial
import serial.tools.list_ports
import sounddevice

from asl_device.app_config import DeviceAppConfig

ROOT = pathlib.Path(r"C:\ASL_OCR_INTEGRATION")
RUNTIME = pathlib.Path(r"C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905")
configs = {
    "h1_console_live_camera": RUNTIME / r"hardware-integration\h1-20260907-231944\config\device-app.h1-camera-console.toml",
    "h2_console_stm_output": RUNTIME / r"hardware-integration\h2-20260907-234639\config\device-app.h2-console-stm.toml",
    "h3_production_physical": RUNTIME / r"hardware-integration\h3-20260908-001800\config\device-app.stm-reading.toml",
}

def digest_tree():
    rows = []
    for sub in ["device-runtime/src", "book-scanner/src", "document-parser/src", "hardware/stm32/kitel2026final/Core"]:
        for path in sorted((ROOT / sub).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".c", ".h"}:
                data = path.read_bytes().replace(b"\r\n", b"\n")
                rows.append((path.relative_to(ROOT).as_posix(), hashlib.sha256(data).hexdigest()))
    joined = "\n".join(f"{name} {sha}" for name, sha in rows).encode()
    return {"algorithm": "sha256-of-sorted-lf-file-hashes", "file_count": len(rows), "digest": hashlib.sha256(joined).hexdigest()}

def safe_config(path):
    config = DeviceAppConfig.from_toml(path)
    scanner = config.scanner
    stm = config.stm_serial
    endpoint = scanner.camera_snapshot_url
    # The endpoint has no embedded credentials by config contract. Password content and file path are excluded.
    return {
        "config_path": str(path),
        "config_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "device_id": config.connectivity.device_id.value,
        "server_base_url": config.connectivity.server_base_url,
        "connectivity": {
            "connect_timeout_seconds": config.connectivity.connect_timeout_seconds,
            "request_timeout_seconds": config.connectivity.request_timeout_seconds,
            "heartbeat_interval_seconds": config.connectivity.heartbeat_interval_seconds,
            "allow_insecure_http": config.connectivity.allow_insecure_http,
            "api_key_file_present": config.connectivity.api_key_file.is_file(),
        },
        "scanner": {
            "profile": scanner.profile,
            "sample_interval_ms": scanner.sample_interval_ms,
            "opaque_identity_max_collection_ms": scanner.opaque_identity_max_collection_ms,
            "operator_preview_enabled": scanner.operator_preview_enabled,
            "snapshot_endpoint": endpoint,
            "snapshot_auth_configured": scanner.camera_snapshot_username is not None and scanner.camera_snapshot_password_file is not None,
            "snapshot_password_file_present": scanner.camera_snapshot_password_file.is_file() if scanner.camera_snapshot_password_file else False,
            "snapshot_allow_insecure_tls": scanner.camera_snapshot_allow_insecure_tls,
            "snapshot_tls_ca_configured": scanner.camera_snapshot_tls_ca_file is not None,
            "snapshot_timeout_seconds": scanner.camera_snapshot_timeout_seconds,
            "snapshot_min_width": scanner.camera_snapshot_min_width,
            "snapshot_min_height": scanner.camera_snapshot_min_height,
        },
        "local_io": {
            "controls": config.controls_mode,
            "feedback": config.feedback_mode,
            "presenter": "StmSerialControlSource" if config.controls_mode == "stm_serial" else "JsonLineReadingPresenter",
            "reading_audio": {
                "enabled": config.reading_audio.enabled,
                "backend": config.reading_audio.backend,
                "request_timeout_seconds": config.reading_audio.request_timeout_seconds,
            },
            "stm_serial": None if stm is None else {
                "port": stm.port,
                "baudrate": stm.baudrate,
                "read_timeout_ms": stm.read_timeout_ms,
                "reconnect_initial_ms": stm.reconnect_initial_ms,
                "reconnect_max_ms": stm.reconnect_max_ms,
                "debounce_ms": stm.debounce_ms,
                "cell_count": stm.cell_count,
            },
            "hold_repeat": {
                "initial_delay_ms": config.hold_repeat.initial_delay_ms,
                "interval_ms": config.hold_repeat.interval_ms,
            },
        },
        "device_loop": {"viewport_size": config.viewport_size, "poll_interval_ms": config.poll_interval_ms},
        "durable_paths_present": {
            "outbox_parent": config.delivery.outbox_db_path.parent.is_dir(),
            "artifact_root": config.delivery.artifact_root.is_dir(),
            "scanner_staging_root": scanner.staging_root.is_dir(),
            "scanner_ready_root": scanner.ready_root.is_dir(),
        },
    }

session_id = ctypes.c_ulong()
ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session_id))
default_output = int(sounddevice.default.device[1])
device = dict(sounddevice.query_devices(default_output)) if default_output >= 0 else None
output = None if device is None else {
    "index": default_output,
    "name": device.get("name"),
    "hostapi": device.get("hostapi"),
    "max_output_channels": device.get("max_output_channels"),
    "default_samplerate": device.get("default_samplerate"),
}
process_text = subprocess.check_output(
    ["powershell", "-NoProfile", "-Command",
     "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\\.exe$' } | Select-Object ProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Compress"],
    text=True, encoding="utf-8-sig",
)
process_rows = json.loads(process_text) if process_text.strip() else []
if isinstance(process_rows, dict):
    process_rows = [process_rows]
device_processes = []
for row in process_rows:
    if row.get("ProcessId") == os.getpid():
        continue
    command = row.pop("CommandLine", "") or ""
    if "-m asl_device" in command:
        device_processes.append({
            "process_id": row.get("ProcessId"),
            "name": row.get("Name"),
            "executable": row.get("ExecutablePath"),
            "production_module_entrypoint": "-m asl_device" in command,
        })

result = {
    "python": sys.executable,
    "python_version": sys.version.split()[0],
    "imports": {name: __import__(name).__file__ for name in ["asl_device", "book_scanner", "document_parser"]},
    "source_identity": digest_tree(),
    "environment_manifest": {
        "path": str(RUNTIME / "integration-environment-manifest.json"),
        "sha256": hashlib.sha256((RUNTIME / "integration-environment-manifest.json").read_bytes()).hexdigest(),
    },
    "parsed_configs": {name: safe_config(path) for name, path in configs.items()},
    "environment_override_names_present": sorted(name for name in os.environ if name.startswith("ASL_")),
    "audio": {
        "sounddevice_version": sounddevice.__version__,
        "collector_windows_session_id": session_id.value,
        "default_output": output,
        "interactive_playback_session_required": True,
    },
    "device_runtime_processes": device_processes,
    "serial": {
        "pyserial_version": serial.__version__,
        "ports": [{"device": port.device, "description": port.description} for port in serial.tools.list_ports.comports()],
        "ports_opened": 0,
    },
    "firmware": {
        "source_main_c_sha256": hashlib.sha256((ROOT / r"hardware\stm32\kitel2026final\Core\Src\main.c").read_bytes()).hexdigest(),
        "flashed_binary_identity": "unverified",
        "rollback_image": "unverified",
    },
}
print(json.dumps(result))
'''

result = json.loads(helper.remote_python(code))
(HERE / "laptop-runtime.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({
    "python": result["python"],
    "source_identity": result["source_identity"],
    "profiles": list(result["parsed_configs"]),
    "audio": result["audio"],
    "serial": result["serial"],
    "firmware": result["firmware"],
}, indent=2))
