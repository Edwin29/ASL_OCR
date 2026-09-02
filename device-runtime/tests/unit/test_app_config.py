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


def test_e0b_replay_example_has_no_physical_input_authority() -> None:
    example = Path(__file__).resolve().parents[2] / "device-app.e0b.replay.example.toml"
    payload = tomllib.loads(example.read_text(encoding="utf-8"))

    assert payload["scanner"]["profile"] == "replay"
    assert payload["scanner"]["replay_path"] == "inputs/scanner-replay.mp4"
    assert payload["scanner"]["sample_interval_ms"] == 100
    assert payload["scanner"]["opaque_identity_max_collection_ms"] == 30000
    assert "camera_index" not in payload["scanner"]
    assert payload["local_io"] == {"controls": "console", "feedback": "jsonl"}
