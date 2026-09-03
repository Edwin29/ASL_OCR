from __future__ import annotations

import cv2
import numpy as np
import pytest

from book_scanner.video.camera_host import (
    AndroidUvcCameraSource,
    CameraDevice,
    CameraDiscoveryError,
    camera_backend_api,
    default_camera_backend,
    _enumerate_linux_devices,
    resolve_camera_device,
)


class FakeCapture:
    def __init__(self, frame: np.ndarray):
        self.frame = frame
        self.opened = True
        self.released = False
        self.settings: dict[int, float] = {}

    def isOpened(self) -> bool:
        return self.opened

    def read(self):
        return True, self.frame

    def grab(self) -> bool:
        return True

    def retrieve(self):
        return True, self.frame

    def release(self) -> None:
        self.released = True

    def set(self, prop_id: int, value: float) -> bool:
        self.settings[prop_id] = value
        return True

    def get(self, prop_id: int) -> float:
        return self.settings.get(prop_id, 0.0)


def test_resolve_uses_persistent_path_without_index() -> None:
    device = CameraDevice(
        stable_id="/dev/v4l/by-id/android-camera",
        name="Android Webcam",
        backend="v4l2",
        path="/dev/v4l/by-id/android-camera",
    )

    selected = resolve_camera_device([device], "Android Webcam")

    assert selected.open_target == "/dev/v4l/by-id/android-camera"
    assert selected.selection_method == "persistent_path"


def test_backend_mapping_is_platform_explicit() -> None:
    assert default_camera_backend("Windows") == "dshow"
    assert default_camera_backend("Linux") == "v4l2"
    assert camera_backend_api("dshow") == cv2.CAP_DSHOW
    assert camera_backend_api("msmf") == cv2.CAP_MSMF
    assert camera_backend_api("v4l2") == cv2.CAP_V4L2
    with pytest.raises(CameraDiscoveryError, match="unsupported"):
        default_camera_backend("Darwin")


def test_linux_enumeration_reports_v4l2_path_and_sysfs_name(tmp_path) -> None:
    dev_root = tmp_path / "dev"
    sys_root = tmp_path / "sys/class/video4linux"
    dev_root.mkdir(parents=True)
    (dev_root / "video0").touch()
    (sys_root / "video0").mkdir(parents=True)
    (sys_root / "video0/name").write_text("Android UVC Camera\n", encoding="utf-8")

    devices = _enumerate_linux_devices(dev_root=dev_root, sys_video_root=sys_root)

    assert len(devices) == 1
    assert devices[0].name == "Android UVC Camera"
    assert devices[0].path == str(dev_root / "video0")
    assert devices[0].backend == "v4l2"


def test_resolve_windows_identity_requires_explicit_guarded_index() -> None:
    device = CameraDevice("USB\\VID_1234", "Android Webcam", "dshow")

    with pytest.raises(CameraDiscoveryError, match="camera_fallback_index"):
        resolve_camera_device([device], "USB\\VID_1234")

    selected = resolve_camera_device([device], "USB\\VID_1234", fallback_index=2)
    assert selected.open_target == 2
    assert selected.selection_method == "selector_guarded_index"


def test_resolve_rejects_missing_and_ambiguous_selector() -> None:
    devices = [
        CameraDevice("one", "Android Webcam", "dshow"),
        CameraDevice("two", "Android Webcam", "dshow"),
    ]

    with pytest.raises(CameraDiscoveryError, match="did not match"):
        resolve_camera_device(devices, "missing", fallback_index=0)
    with pytest.raises(CameraDiscoveryError, match="multiple"):
        resolve_camera_device(devices, "Android Webcam", fallback_index=0)


def test_android_uvc_source_guards_index_with_identity_and_reports_mode() -> None:
    frame = np.full((4, 6, 3), 20, dtype=np.uint8)
    capture = FakeCapture(frame)
    calls = []
    device = CameraDevice("USB\\VID_1234", "Android Webcam", "dshow")
    source = AndroidUvcCameraSource(
        "USB\\VID_1234",
        backend="dshow",
        fallback_index=1,
        width=1920,
        height=1080,
        fps=30.0,
        fourcc="MJPG",
        warmup_frames=1,
        reopen_attempts=0,
        drain_grabs=0,
        device_provider=lambda backend: [device],
        capture_factory=lambda target, backend: calls.append((target, backend)) or capture,
    )

    source.start()
    sample = source.read()

    assert calls == [(1, cv2.CAP_DSHOW)]
    assert sample is not None and sample.frame_id.value == "android-uvc-00000001"
    assert source.selected_camera is not None
    assert source.selected_camera.selection_method == "selector_guarded_index"
    assert source.effective_mode == {
        "width": 1920.0,
        "height": 1080.0,
        "fps": 30.0,
        "fourcc": "MJPG",
    }
    source.stop()
    assert capture.released
