from __future__ import annotations

import json
from pathlib import Path

import pytest

from asl_device.app_config import DeviceAppConfig
from asl_device.laptop_acceptance import (
    _probe_e0b_profile,
    _probe_piper_audio,
    _probe_server_health,
    run_laptop_preflight,
    write_laptop_preflight_report,
)
from asl_device.types import AudioResource


def _write_laptop_config(root: Path, *, controls: str = "stm_serial") -> Path:
    (root / "secret.txt").write_text("never-report-this", encoding="utf-8")
    (root / "connectivity.toml").write_text(
        '''schema_version = 1
device_id = "laptop-1"
server_base_url = "https://e0b.example.test"
api_key_file = "secret.txt"
allow_insecure_http = false''',
        encoding="utf-8",
    )
    path = root / "device.toml"
    local_io = '''[local_io]
controls = "stm_serial"
feedback = "jsonl"

[local_io.stm_serial]
port = "COM5"
cell_count = 10

[local_io.reading_audio]
enabled = true
backend = "sounddevice"
max_resource_bytes = 4194304
max_cache_bytes = 8388608
max_cache_entries = 4
download_chunk_bytes = 65536
request_timeout_seconds = 10.0'''
    if controls == "console":
        local_io = '''[local_io]
controls = "console"
feedback = "jsonl"

[local_io.reading_audio]
enabled = true
backend = "sounddevice"
max_resource_bytes = 4194304
max_cache_bytes = 8388608
max_cache_entries = 4
download_chunk_bytes = 65536
request_timeout_seconds = 10.0'''
    path.write_text(
        f'''schema_version = 1
connectivity_config = "connectivity.toml"
viewport_size = 10

[delivery]
outbox_db_path = "state/outbox.sqlite3"
artifact_root = "state/ready"

[scanner]
profile = "pc_camera"
staging_root = "state/staging"
ready_root = "state/ready"
uvdoc_runtime_path = "models/uvdoc"
uvdoc_checkpoint_path = "models/uvdoc.pth"
uvdoc_device = "cpu"
m1_model_dir = "models/paddle"
m1_model_manifest = "models/paddle.json"
camera_index = 0
camera_width = 1920
camera_height = 1080
camera_fps = 30.0
operator_preview_enabled = true
operator_preview_max_width = 960

{local_io}''',
        encoding="utf-8",
    )
    return path


def test_laptop_preflight_writes_secret_safe_pass_report(tmp_path: Path) -> None:
    overrides = {
        name: (lambda _config, name=name: {"probe": name})
        for name in (
            "e0b_profile",
            "scanner_models",
            "server_health",
            "camera",
            "stm_serial",
            "piper_audio",
        )
    }
    report = run_laptop_preflight(_write_laptop_config(tmp_path), probe_overrides=overrides)
    destination = tmp_path / "reports/e0b.json"
    write_laptop_preflight_report(report, destination)

    assert report["passed"]
    assert len(report["checks"]) == 6
    serialized = destination.read_text(encoding="utf-8")
    assert "never-report-this" not in serialized
    parsed = json.loads(serialized)
    assert parsed["packet"] == "Device Integration E0-B — Conditional Laptop Preflight"
    assert parsed["test_profile"] == "hardware"


def test_laptop_preflight_records_probe_failure_without_aborting_other_checks(tmp_path: Path) -> None:
    def fail(_config):
        raise OSError("camera unavailable")

    overrides = {
        name: (fail if name == "camera" else (lambda _config: {}))
        for name in (
            "e0b_profile",
            "scanner_models",
            "server_health",
            "camera",
            "stm_serial",
            "piper_audio",
        )
    }

    report = run_laptop_preflight(_write_laptop_config(tmp_path), probe_overrides=overrides)

    assert not report["passed"]
    failed = next(check for check in report["checks"] if check["name"] == "camera")
    assert failed["status"] == "failed"
    assert failed["error_type"] == "OSError"


def test_webcam_profile_skips_stm_probe(tmp_path: Path) -> None:
    observed = []

    def pass_probe(_config):
        observed.append(True)
        return {}

    overrides = {
        name: pass_probe
        for name in (
            "e0b_profile",
            "scanner_models",
            "server_health",
            "camera",
            "piper_audio",
        )
    }

    report = run_laptop_preflight(
        _write_laptop_config(tmp_path, controls="console"),
        probe_overrides=overrides,
        play_audio=False,
    )

    assert report["passed"]
    assert report["test_profile"] == "webcam"
    assert [check["name"] for check in report["checks"]] == list(overrides)
    assert len(observed) == 5


@pytest.mark.parametrize(
    "controls, expected_profile",
    [("console", "webcam"), ("stm_serial", "hardware")],
)
def test_e0b_profile_classifies_controls_without_changing_camera_contract(
    tmp_path: Path,
    controls: str,
    expected_profile: str,
) -> None:
    config = DeviceAppConfig.from_toml(
        _write_laptop_config(tmp_path, controls=controls)
    )

    detail = _probe_e0b_profile(config)

    assert detail["test_profile"] == expected_profile
    assert detail["scanner_profile"] == "pc_camera"
    assert detail["audio_transport"] == "authenticated_s0_wav"
    assert detail["audio_backend"] == "sounddevice"
    assert detail["operator_preview_enabled"] is True
    assert detail["operator_preview_max_width"] == 960


def test_server_preflight_uses_the_c0_health_endpoint(tmp_path: Path, monkeypatch) -> None:
    requested = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit):
            return b'{"status":"ok"}'

    def open_request(request, *, timeout):
        requested.append((request.full_url, timeout))
        return Response()

    monkeypatch.setattr("asl_device.laptop_acceptance.urllib.request.urlopen", open_request)
    config = DeviceAppConfig.from_toml(_write_laptop_config(tmp_path))

    result = _probe_server_health(config)

    assert requested[0][0] == "https://e0b.example.test/api/v1/health"
    assert result["http_status"] == 200


@pytest.mark.parametrize("play_audio, expected_plays", [(False, 0), (True, 1)])
def test_piper_preflight_fetches_authenticated_system_wav_and_optionally_plays(
    tmp_path: Path,
    monkeypatch,
    play_audio: bool,
    expected_plays: int,
) -> None:
    observed: dict[str, object] = {"plays": 0}
    resource = AudioResource(b"wav", "0" * 64, 3, 16_000, 1, 2, 25)

    class ResourcePort:
        def __init__(self, base_url, api_key, **bounds):
            observed.update(base_url=base_url, api_key=api_key, bounds=bounds)

        def fetch(self, device_id, audio_ref, cancelled):
            observed.update(device_id=device_id.value, audio_ref=audio_ref)
            assert not cancelled()
            return resource

    class Player:
        def play(self, selected, cancelled):
            assert selected is resource
            assert not cancelled()
            observed["plays"] = int(observed["plays"]) + 1

        def close(self):
            observed["closed"] = True

    monkeypatch.setattr(
        "asl_device.laptop_acceptance.S0SystemAudioResourceHttpAdapter",
        ResourcePort,
    )
    monkeypatch.setattr("asl_device.laptop_acceptance.SoundDeviceWavPlayer", Player)
    config = DeviceAppConfig.from_toml(_write_laptop_config(tmp_path))

    result = _probe_piper_audio(config, play_audio=play_audio)

    assert observed["api_key"] == "never-report-this"
    assert observed["device_id"] == "laptop-1"
    assert observed["audio_ref"] == "s0-system-cue:screen.capture_catalog"
    assert observed["plays"] == expected_plays
    assert result["playback_requested"] is play_audio
    assert "never-report-this" not in json.dumps(result)


@pytest.mark.parametrize("origin", ["http://192.168.0.5:8421", "https://127.0.0.1:8421"])
def test_remote_e0b_profile_rejects_insecure_or_loopback_origin(tmp_path: Path, origin: str) -> None:
    path = _write_laptop_config(tmp_path)
    connectivity = tmp_path / "connectivity.toml"
    payload = connectivity.read_text(encoding="utf-8").replace(
        "https://e0b.example.test",
        origin,
    )
    if origin.startswith("http://"):
        payload = payload.replace("allow_insecure_http = false", "allow_insecure_http = true")
    connectivity.write_text(payload, encoding="utf-8")
    config = DeviceAppConfig.from_toml(path)

    with pytest.raises(ValueError, match="HTTPS|non-loopback"):
        _probe_e0b_profile(config)
