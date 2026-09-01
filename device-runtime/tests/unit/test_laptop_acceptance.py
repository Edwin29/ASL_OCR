from __future__ import annotations

import json
from pathlib import Path

import pytest

from asl_device.app_config import DeviceAppConfig
from asl_device.laptop_acceptance import (
    _probe_e0b_profile,
    _probe_server_health,
    run_laptop_preflight,
    write_laptop_preflight_report,
)


def _write_laptop_config(root: Path) -> Path:
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
    path.write_text(
        '''schema_version = 1
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

[local_io]
controls = "stm_serial"
feedback = "windows_audio"

[local_io.stm_serial]
port = "COM5"
cell_count = 10

[local_io.windows_audio]
jsonl_trace = false''',
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
            "windows_audio",
        )
    }
    report = run_laptop_preflight(_write_laptop_config(tmp_path), probe_overrides=overrides)
    destination = tmp_path / "reports/e0b.json"
    write_laptop_preflight_report(report, destination)

    assert report["passed"]
    assert len(report["checks"]) == 6
    serialized = destination.read_text(encoding="utf-8")
    assert "never-report-this" not in serialized
    assert json.loads(serialized)["packet"] == "Device Integration E0-B — Laptop Acceptance"


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
            "windows_audio",
        )
    }

    report = run_laptop_preflight(_write_laptop_config(tmp_path), probe_overrides=overrides)

    assert not report["passed"]
    failed = next(check for check in report["checks"] if check["name"] == "camera")
    assert failed["status"] == "failed"
    assert failed["error_type"] == "OSError"


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
