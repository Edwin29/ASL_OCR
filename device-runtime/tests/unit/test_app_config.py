from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from asl_device.app_config import DeviceAppConfig


def _write_config(tmp_path: Path, *, ready_root: str = "state/artifacts/ready", extra: str = "") -> Path:
    (tmp_path / "api-key.txt").write_text("secret", encoding="utf-8")
    (tmp_path / "connectivity.toml").write_text(
        """
schema_version = 1
device_id = "device-1"
server_base_url = "http://127.0.0.1:8080"
api_key_file = "api-key.txt"
allow_insecure_http = true
""".strip(),
        encoding="utf-8",
    )
    config = tmp_path / "device.toml"
    config.write_text(
        f"""
schema_version = 1
connectivity_config = "connectivity.toml"
viewport_size = 20
poll_interval_ms = 25
{extra}

[delivery]
outbox_db_path = "state/delivery.sqlite3"
artifact_root = "state/artifacts/ready"

[scanner]
profile = "replay"
staging_root = "state/artifacts/staging"
ready_root = "{ready_root}"
uvdoc_runtime_path = "models/uvdoc"
uvdoc_checkpoint_path = "models/uvdoc.pth"
uvdoc_device = "cpu"
m1_model_dir = "models/paddle"
m1_model_manifest = "models/paddle.json"
replay_path = "inputs/sample.mp4"

[local_io]
feedback = "jsonl"
""".strip(),
        encoding="utf-8",
    )
    return config


def test_app_config_resolves_paths_from_config_directory(tmp_path: Path) -> None:
    config = DeviceAppConfig.from_toml(_write_config(tmp_path))

    assert config.connectivity.device_id.value == "device-1"
    assert config.delivery.outbox_db_path == (tmp_path / "state/delivery.sqlite3").resolve()
    assert config.scanner.ready_root == config.delivery.artifact_root
    assert config.scanner.replay_path == (tmp_path / "inputs/sample.mp4").resolve()
    assert config.poll_interval_ms == 25
    assert config.scanner.opaque_identity_max_collection_ms is None
    assert not config.reading_audio.enabled


def test_replay_config_accepts_bounded_opaque_identity_collection_timeout(
    tmp_path: Path,
) -> None:
    path = _write_config(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        'replay_path = "inputs/sample.mp4"',
        'replay_path = "inputs/sample.mp4"\nopaque_identity_max_collection_ms = 30000',
    )
    path.write_text(text, encoding="utf-8")

    config = DeviceAppConfig.from_toml(path)

    assert config.scanner.opaque_identity_max_collection_ms == 30000


@pytest.mark.parametrize("value", ["true", "0", "-1", '"30000"', "60001"])
def test_replay_config_rejects_invalid_opaque_identity_collection_timeout(
    tmp_path: Path,
    value: str,
) -> None:
    path = _write_config(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        'replay_path = "inputs/sample.mp4"',
        f'replay_path = "inputs/sample.mp4"\nopaque_identity_max_collection_ms = {value}',
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="opaque_identity_max_collection_ms"):
        DeviceAppConfig.from_toml(path)


def test_physical_config_rejects_replay_only_opaque_identity_timeout(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    text = path.read_text(encoding="utf-8")
    text = text.replace('profile = "replay"', 'profile = "pc_camera"')
    text = text.replace(
        'replay_path = "inputs/sample.mp4"',
        'opaque_identity_max_collection_ms = 30000',
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="allowed only for replay"):
        DeviceAppConfig.from_toml(path)


def test_app_config_rejects_scanner_delivery_root_split(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ready_root"):
        DeviceAppConfig.from_toml(_write_config(tmp_path, ready_root="different/ready"))


def test_app_config_rejects_unknown_top_level_field(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown Device app"):
        DeviceAppConfig.from_toml(_write_config(tmp_path, extra='unexpected = "value"'))


def test_app_config_loads_laptop_stm_and_audio_settings(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    text = path.read_text(encoding="utf-8")
    text = text.replace("viewport_size = 20", "viewport_size = 10")
    text = text.replace(
        '[local_io]\nfeedback = "jsonl"',
        '''[local_io]
controls = "stm_serial"
feedback = "windows_audio"

[local_io.stm_serial]
port = "COM5"
cell_count = 10
reconnect_initial_ms = 250
reconnect_max_ms = 2000

[local_io.windows_audio]
jsonl_trace = false
speak_catalog_titles = true''',
    )
    path.write_text(text, encoding="utf-8")

    config = DeviceAppConfig.from_toml(path)

    assert config.controls_mode == "stm_serial"
    assert config.feedback_mode == "windows_audio"
    assert config.stm_serial is not None
    assert config.stm_serial.port == "COM5"
    assert config.stm_serial.reconnect_initial_ms == 250
    assert not config.laptop_audio.jsonl_trace


def test_app_config_rejects_stm_cell_count_viewport_mismatch(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        '[local_io]\nfeedback = "jsonl"',
        '''[local_io]
controls = "stm_serial"

[local_io.stm_serial]
port = "COM5"
cell_count = 10''',
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="viewport_size"):
        DeviceAppConfig.from_toml(path)


def test_app_config_loads_bounded_reading_audio_settings(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        '[local_io]\nfeedback = "jsonl"',
        '''[local_io]
feedback = "jsonl"

[local_io.reading_audio]
enabled = true
max_resource_bytes = 1048576
max_cache_bytes = 2097152
max_cache_entries = 2
download_chunk_bytes = 32768
request_timeout_seconds = 5.0''',
    )
    path.write_text(text, encoding="utf-8")

    config = DeviceAppConfig.from_toml(path)

    assert config.reading_audio.enabled
    assert config.reading_audio.max_cache_entries == 2
    assert config.reading_audio.download_chunk_bytes == 32768


def test_app_config_rejects_sapi_and_piper_transport_together(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        '[local_io]\nfeedback = "jsonl"',
        '''[local_io]
feedback = "windows_audio"

[local_io.reading_audio]
enabled = true''',
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="legacy SAPI"):
        DeviceAppConfig.from_toml(path)


def test_app_config_rejects_reading_audio_above_hard_ceiling(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        '[local_io]\nfeedback = "jsonl"',
        '''[local_io]
feedback = "jsonl"

[local_io.reading_audio]
max_resource_bytes = 4194305''',
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="max_resource_bytes"):
        DeviceAppConfig.from_toml(path)


def test_e0b_replay_example_has_no_physical_input_authority() -> None:
    example = Path(__file__).resolve().parents[2] / "device-app.e0b.replay.example.toml"
    payload = tomllib.loads(example.read_text(encoding="utf-8"))

    assert payload["scanner"]["profile"] == "replay"
    assert payload["scanner"]["replay_path"] == "inputs/scanner-replay.mp4"
    assert payload["scanner"]["sample_interval_ms"] == 100
    assert payload["scanner"]["opaque_identity_max_collection_ms"] == 30000
    assert "camera_index" not in payload["scanner"]
    assert payload["local_io"] == {"controls": "console", "feedback": "jsonl"}


@pytest.mark.parametrize(
    "filename, controls",
    [
        ("device-app.e0b.laptop.example.toml", "stm_serial"),
        ("device-app.e0b.webcam.example.toml", "console"),
    ],
)
def test_physical_e0b_examples_use_piper_audio_transport(
    filename: str,
    controls: str,
) -> None:
    example = Path(__file__).resolve().parents[2] / filename
    payload = tomllib.loads(example.read_text(encoding="utf-8"))

    assert payload["viewport_size"] == 10
    assert payload["scanner"]["profile"] == "pc_camera"
    assert payload["local_io"]["controls"] == controls
    assert payload["local_io"]["feedback"] == "jsonl"
    assert payload["local_io"]["reading_audio"]["enabled"] is True
    assert payload["local_io"]["reading_audio"]["backend"] == "sounddevice"
    assert "windows_audio" not in payload["local_io"]


def test_app_config_loads_android_uvc_camera_contract(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    text = path.read_text(encoding="utf-8")
    text = text.replace('profile = "replay"', 'profile = "android_uvc"')
    text = text.replace(
        'replay_path = "inputs/sample.mp4"',
        '''camera_selector = "Android Webcam"
camera_backend = "dshow"
camera_fallback_index = 1
camera_width = 3840
camera_height = 2160
camera_fps = 30.0
camera_fourcc = "MJPG"
camera_rotation = 90
camera_mirror = true
camera_warmup_frames = 5
camera_reopen_attempts = 2
camera_reopen_initial_ms = 300''',
    )
    path.write_text(text, encoding="utf-8")

    config = DeviceAppConfig.from_toml(path)

    assert config.scanner.profile == "android_uvc"
    assert config.scanner.camera_selector == "Android Webcam"
    assert config.scanner.camera_fallback_index == 1
    assert config.scanner.camera_fourcc == "MJPG"
    assert config.scanner.camera_rotation == 90
    assert config.scanner.camera_mirror
    assert config.scanner.camera_reopen_attempts == 2


def test_app_config_rejects_android_uvc_without_selector(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    text = path.read_text(encoding="utf-8")
    text = text.replace('profile = "replay"', 'profile = "android_uvc"')
    text = text.replace('replay_path = "inputs/sample.mp4"', "")
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="camera_selector"):
        DeviceAppConfig.from_toml(path)


@pytest.mark.parametrize(
    "line, message",
    [
        ('camera_fourcc = "MJPEG"', "camera_fourcc"),
        ("camera_rotation = 45", "camera_rotation"),
        ("camera_fallback_index = -1", "camera_fallback_index"),
        ("camera_reopen_attempts = 11", "camera_reopen_attempts"),
    ],
)
def test_app_config_rejects_invalid_android_uvc_fields(
    tmp_path: Path, line: str, message: str
) -> None:
    path = _write_config(tmp_path)
    text = path.read_text(encoding="utf-8")
    text = text.replace('profile = "replay"', 'profile = "android_uvc"')
    text = text.replace(
        'replay_path = "inputs/sample.mp4"',
        f'camera_selector = "Android Webcam"\n{line}',
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises((TypeError, ValueError), match=message):
        DeviceAppConfig.from_toml(path)
