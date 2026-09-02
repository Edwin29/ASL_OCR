from __future__ import annotations

from pathlib import Path

from asl_device.adapters.local_controls import NullControlSource
from asl_device.adapters.local_feedback import CompositeFeedbackSink, MemoryFeedbackSink
from asl_device.local_composition import build_local_device


class Player:
    def play(self, _resource, _cancelled):
        return None

    def stop(self):
        return None

    def close(self):
        return None


class ScannerFactory:
    def create(self, **_kwargs):
        raise AssertionError("scanner must not start during composition")


def _config(tmp_path: Path) -> Path:
    (tmp_path / "api-key.txt").write_text("secret", encoding="utf-8")
    (tmp_path / "connectivity.toml").write_text(
        '''schema_version = 1
device_id = "device-1"
server_base_url = "http://127.0.0.1:8420"
api_key_file = "api-key.txt"
allow_insecure_http = true''',
        encoding="utf-8",
    )
    path = tmp_path / "device.toml"
    path.write_text(
        '''schema_version = 1
connectivity_config = "connectivity.toml"
viewport_size = 20

[delivery]
outbox_db_path = "state/delivery.sqlite3"
artifact_root = "state/artifacts/ready"

[scanner]
profile = "replay"
staging_root = "state/artifacts/staging"
ready_root = "state/artifacts/ready"
uvdoc_runtime_path = "models/uvdoc"
uvdoc_checkpoint_path = "models/uvdoc.pth"
uvdoc_device = "cpu"
m1_model_dir = "models/paddle"
m1_model_manifest = "models/paddle.json"
replay_path = "inputs/sample.mp4"

[local_io]
feedback = "jsonl"

[local_io.reading_audio]
enabled = true''',
        encoding="utf-8",
    )
    return path


def test_local_composition_routes_feedback_and_reading_to_one_player(
    tmp_path: Path, monkeypatch
) -> None:
    player = Player()
    monkeypatch.setattr(
        "asl_device.local_composition.SoundDeviceWavPlayer", lambda: player
    )
    trace = MemoryFeedbackSink()
    composition = build_local_device(
        _config(tmp_path),
        scanner_factory=ScannerFactory(),
        controls=NullControlSource(),
        feedback=trace,
    )
    try:
        assert composition.reading_audio is not None
        assert composition.reading_audio.playback_port is player
        assert composition.reading_audio.system_resource_port is not None
        assert isinstance(composition.coordinator.feedback, CompositeFeedbackSink)
        assert composition.coordinator.feedback.sinks == (
            trace,
            composition.reading_audio,
        )
    finally:
        composition.application.stop()
