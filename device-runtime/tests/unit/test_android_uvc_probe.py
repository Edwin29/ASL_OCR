from __future__ import annotations

from pathlib import Path
import numpy as np

from asl_device.android_uvc_probe import run_android_uvc_probe, write_android_uvc_report
from book_scanner.video.camera_host import CameraDevice, SelectedCamera
from book_scanner.video.protocols import FrameSample
from book_scanner.video.types import FrameId


def _write_config(root: Path) -> Path:
    (root / "secret.txt").write_text("do-not-report", encoding="utf-8")
    (root / "connectivity.toml").write_text(
        '''schema_version = 1
device_id = "desktop-1"
server_base_url = "http://127.0.0.1:8421"
api_key_file = "secret.txt"
allow_insecure_http = true''',
        encoding="utf-8",
    )
    path = root / "device.toml"
    path.write_text(
        '''schema_version = 1
connectivity_config = "connectivity.toml"

[delivery]
outbox_db_path = "state/outbox.sqlite3"
artifact_root = "state/ready"

[scanner]
profile = "android_uvc"
staging_root = "state/staging"
ready_root = "state/ready"
uvdoc_runtime_path = "models/uvdoc"
uvdoc_checkpoint_path = "models/uvdoc.pth"
uvdoc_device = "cpu"
m1_model_dir = "models/paddle"
m1_model_manifest = "models/paddle.json"
camera_selector = "Android Webcam"
camera_backend = "dshow"
camera_fallback_index = 1
camera_width = 6
camera_height = 4
camera_fps = 30.0
camera_fourcc = "MJPG"

[local_io]
controls = "console"
feedback = "jsonl"''',
        encoding="utf-8",
    )
    return path


class FakeSource:
    def __init__(self) -> None:
        device = CameraDevice("USB\\SERIAL-PRIVATE", "Android Webcam", "dshow")
        self.selected_camera = SelectedCamera(device, 1, "selector_guarded_index")
        self.effective_mode = {"width": 6.0, "height": 4.0, "fps": 30.0, "fourcc": "MJPG"}
        self.index = 0
        self.stopped = False

    def start(self) -> None:
        pass

    def read(self):
        self.index += 1
        return FrameSample(
            FrameId(f"android-uvc-{self.index:08d}"),
            self.index / 10.0,
            np.full((4, 6, 3), self.index, dtype=np.uint8),
        )

    def stop(self) -> None:
        self.stopped = True


def test_probe_records_liveness_and_redacts_stable_identity(tmp_path: Path) -> None:
    source = FakeSource()
    report = run_android_uvc_probe(
        _write_config(tmp_path),
        sample_count=3,
        interval_ms=0,
        source_factory=lambda _config: source,
    )
    destination = tmp_path / "reports/probe.json"
    write_android_uvc_report(report, destination)

    assert report["status"] == "passed"
    assert report["source_profile"] == "android_uvc"
    assert not report["replay_path_used"]
    assert report["samples"]["unique_frame_digests"] == 3
    assert report["samples"]["liveness_observed"]
    assert report["samples"]["frame_ids_monotonic"]
    assert report["camera"]["selection_method"] == "selector_guarded_index"
    assert "SERIAL-PRIVATE" not in destination.read_text(encoding="utf-8")
    assert source.stopped
