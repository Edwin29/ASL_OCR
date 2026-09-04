from __future__ import annotations

import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

import book_scanner.video.operator_preview as operator_preview_module
from book_scanner.video.operator_preview import (
    OpenCVOperatorPreview,
    OperatorPreviewDiagnostics,
    ThreadedPreviewCameraSource,
    _annotate_preview,
)
from book_scanner.video.protocols import FrameSample
from book_scanner.video.sources import (
    CameraUnavailableError,
    FrameDecodeError,
    HttpSnapshotCameraSource,
    ImageSequenceCameraSource,
    OpenCVCameraSource,
    VideoFileCameraSource,
)
from book_scanner.video.types import FrameId

from .fakes import ManualClock


class FakeCapture:
    def __init__(self, frames: list[np.ndarray], *, opened: bool = True, fps: float = 10.0):
        self.frames = frames
        self.opened = opened
        self.fps = fps
        self.index = 0
        self.grabbed: np.ndarray | None = None
        self.released = False
        self.settings: list[tuple[int, float]] = []

    def isOpened(self) -> bool:
        return self.opened

    def read(self):
        if self.index >= len(self.frames):
            return False, None
        frame = self.frames[self.index]
        self.index += 1
        return True, frame

    def grab(self) -> bool:
        if self.index >= len(self.frames):
            return False
        self.grabbed = self.frames[self.index]
        self.index += 1
        return True

    def retrieve(self):
        return (self.grabbed is not None), self.grabbed

    def release(self) -> None:
        self.released = True

    def get(self, _prop_id: int) -> float:
        configured = next((value for prop_id, value in reversed(self.settings) if prop_id == _prop_id), None)
        if configured is not None:
            return configured
        return self.fps

    def set(self, prop_id: int, value: float) -> bool:
        self.settings.append((prop_id, value))
        return True


def _frame(value: int) -> np.ndarray:
    return np.full((20, 30, 3), value, dtype=np.uint8)


def test_live_camera_drains_to_latest_and_releases() -> None:
    capture = FakeCapture([_frame(1), _frame(2), _frame(3)])
    source = OpenCVCameraSource(
        clock=ManualClock(4.0), drain_grabs=2, capture_factory=lambda _device: capture
    )

    source.start()
    sample = source.read()

    assert sample is not None
    assert int(sample.payload[0, 0, 0]) == 2
    assert sample.frame_id.value == "camera-00000001"
    assert capture.settings == [(cv2.CAP_PROP_BUFFERSIZE, 1)]
    source.stop()
    assert capture.released


def test_live_camera_open_failure_is_not_eof() -> None:
    capture = FakeCapture([], opened=False)
    source = OpenCVCameraSource(capture_factory=lambda _device: capture)

    with pytest.raises(CameraUnavailableError):
        source.start()
    assert capture.released
    assert not source.exhausted


def test_live_camera_applies_and_verifies_requested_capture_mode() -> None:
    capture = FakeCapture([_frame(1)])
    source = OpenCVCameraSource(
        width=1920,
        height=1080,
        fps=30.0,
        capture_factory=lambda _device: capture,
    )

    source.start()

    assert (cv2.CAP_PROP_FRAME_WIDTH, 1920.0) in capture.settings
    assert (cv2.CAP_PROP_FRAME_HEIGHT, 1080.0) in capture.settings
    assert (cv2.CAP_PROP_FPS, 30.0) in capture.settings
    source.stop()


def test_live_camera_orients_frame_and_reopens_without_reusing_frame_id() -> None:
    first = FakeCapture([])
    second = FakeCapture([np.arange(18, dtype=np.uint8).reshape(2, 3, 3)])
    captures = iter((first, second))
    source = OpenCVCameraSource(
        drain_grabs=0,
        rotation=90,
        mirror=True,
        reopen_attempts=1,
        capture_factory=lambda _device: next(captures),
        sleep=lambda _seconds: None,
    )

    source.start()
    sample = source.read()

    assert sample is not None
    assert sample.frame_id.value == "camera-00000001"
    assert sample.payload.shape == (3, 2, 3)
    assert first.released
    source.stop()
    assert second.released


def test_live_camera_crops_normalized_bounds_after_rotation() -> None:
    frame = np.arange(4 * 6 * 3, dtype=np.uint8).reshape(4, 6, 3)
    capture = FakeCapture([frame])
    source = OpenCVCameraSource(
        drain_grabs=0,
        rotation=270,
        crop_normalized=(0.0, 0.25, 1.0, 0.75),
        capture_factory=lambda _device: capture,
    )

    source.start()
    sample = source.read()

    assert sample is not None
    rotated = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    assert np.array_equal(sample.payload, rotated[2:4, :])
    source.stop()


@pytest.mark.parametrize(
    "crop,error",
    [
        ((0.5, 0.0, 0.5, 1.0), ValueError),
        ((0.0, 0.0, 1.1, 1.0), ValueError),
        ((0.0, 0.0, 1.0), TypeError),
    ],
)
def test_live_camera_rejects_invalid_normalized_crop(crop, error) -> None:
    with pytest.raises(error):
        OpenCVCameraSource(crop_normalized=crop)


class FakeHttpResponse:
    def __init__(self, payload: bytes, *, content_length: int | None = None) -> None:
        self.payload = payload
        self.headers = {} if content_length is None else {"Content-Length": str(content_length)}
        self.closed = False

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.payload), chunk_size):
            yield self.payload[offset : offset + chunk_size]

    def close(self) -> None:
        self.closed = True


def test_http_snapshot_fetches_full_resolution_jpeg_with_bounded_request(tmp_path: Path) -> None:
    frame = np.full((1200, 2000, 3), 73, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    response = FakeHttpResponse(encoded.tobytes())
    calls = []

    def fetcher(url, **kwargs):
        calls.append((url, kwargs))
        return response

    password_file = tmp_path / "phone-camera-password.txt"
    password_file.write_text("private-value\n", encoding="utf-8")
    source = HttpSnapshotCameraSource(
        "https://192.168.42.129:4444/video/snapshot?camera=back",
        username="scanner",
        password_file=password_file,
        allow_insecure_tls=True,
        min_width=1920,
        min_height=1080,
        fetcher=fetcher,
        clock=ManualClock(9.0),
    )

    source.start()
    sample = source.read()

    assert sample is not None
    assert sample.payload.shape == (1200, 2000, 3)
    assert sample.frame_id.value == "phone-snapshot-00000001"
    assert source.effective_mode == {
        "width": 2000.0,
        "height": 1200.0,
        "raw_width": 2000.0,
        "raw_height": 1200.0,
        "rotation": 0.0,
        "transport": "http_snapshot",
    }
    assert calls[0][0].endswith("/video/snapshot?camera=back")
    assert calls[0][1]["auth"] == ("scanner", "private-value")
    assert calls[0][1]["verify"] is False
    assert response.closed
    source.stop()


@pytest.mark.parametrize(
    ("shape", "landscape_rotation", "portrait_rotation", "expected_shape", "expected_rotation"),
    [
        ((1200, 2000, 3), 180, 270, (1200, 2000, 3), 180.0),
        ((2000, 1200, 3), 180, 270, (1200, 2000, 3), 270.0),
    ],
)
def test_http_snapshot_selects_rotation_from_raw_aspect(
    shape, landscape_rotation, portrait_rotation, expected_shape, expected_rotation
) -> None:
    frame = np.zeros(shape, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    source = HttpSnapshotCameraSource(
        "http://192.168.42.129:4444/video/snapshot",
        min_width=1000,
        min_height=1000,
        rotation=0,
        landscape_rotation=landscape_rotation,
        portrait_rotation=portrait_rotation,
        fetcher=lambda _url, **_kwargs: FakeHttpResponse(encoded.tobytes()),
    )
    source.start()

    sample = source.read()

    assert sample is not None
    assert sample.payload.shape == expected_shape
    assert source.effective_mode["rotation"] == expected_rotation


def test_http_snapshot_retries_transient_jpeg_decode_failure() -> None:
    frame = np.zeros((1200, 2000, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    responses = iter(
        (
            FakeHttpResponse(b"not-a-jpeg"),
            FakeHttpResponse(encoded.tobytes()),
        )
    )
    source = HttpSnapshotCameraSource(
        "http://192.168.42.129:4444/video/snapshot",
        min_width=1000,
        min_height=1000,
        fetcher=lambda _url, **_kwargs: next(responses),
    )
    source.start()

    sample = source.read()

    assert sample is not None
    assert sample.payload.shape == frame.shape


def test_http_snapshot_rejects_virtual_camera_resolution() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    source = HttpSnapshotCameraSource(
        "http://192.168.42.129:4444/video/snapshot",
        min_width=1920,
        min_height=1080,
        fetcher=lambda _url, **_kwargs: FakeHttpResponse(encoded.tobytes()),
    )
    source.start()

    with pytest.raises(FrameDecodeError, match="minimum"):
        source.read()


def test_http_snapshot_rejects_credentials_over_plain_http(tmp_path: Path) -> None:
    password_file = tmp_path / "password.txt"
    password_file.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="requires HTTPS"):
        HttpSnapshotCameraSource(
            "http://192.168.42.129:4444/video/snapshot",
            username="scanner",
            password_file=password_file,
        )


class RecordingPreview:
    def __init__(self) -> None:
        self.frames: list[np.ndarray] = []
        self.show_thread_ids: list[int] = []
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def show(self, frame: np.ndarray) -> None:
        self.frames.append(frame.copy())
        self.show_thread_ids.append(threading.get_ident())

    def stop(self) -> None:
        self.stopped = True


class FailingPreview(RecordingPreview):
    def show(self, frame: np.ndarray) -> None:
        raise RuntimeError("preview renderer failed")


class PreviewCamera:
    def __init__(self) -> None:
        self.index = 0
        self.stopped = False

    @property
    def exhausted(self) -> bool:
        return False

    @property
    def effective_mode(self) -> dict[str, float | str]:
        return {"width": 1280.0, "height": 720.0, "fps": 30.0, "fourcc": "MJPG"}

    def start(self) -> None:
        self.stopped = False

    def read(self):
        if self.stopped:
            return None
        self.index += 1
        if self.index > 2:
            time.sleep(0.005)
            return None
        return FrameSample(
            FrameId(f"preview-{self.index:08d}"),
            float(self.index),
            _frame(self.index),
        )

    def stop(self) -> None:
        self.stopped = True


def test_threaded_preview_keeps_live_acquisition_outside_scanner_poll_cadence() -> None:
    camera = PreviewCamera()
    preview = RecordingPreview()
    source = ThreadedPreviewCameraSource(camera, preview)

    source.start()
    assert source.runtime_diagnostics() == {
        "source_label": "camera",
        "source_type": "PreviewCamera",
        "width": 1280.0,
        "height": 720.0,
        "fps": 30.0,
        "fourcc": "MJPG",
    }
    deadline = time.monotonic() + 1.0
    sample = None
    while (
        (sample is None or sample.frame_id.value != "preview-00000002")
        and time.monotonic() < deadline
    ):
        latest = source.read()
        if latest is not None:
            sample = latest
        time.sleep(0.005)
    source.pump_preview()

    assert sample is not None
    assert sample.frame_id.value == "preview-00000002"
    assert int(sample.payload[0, 0, 0]) == 2
    assert source.read() is None
    assert len(preview.frames) == 1
    assert preview.show_thread_ids == [threading.get_ident()]
    source.stop()
    assert preview.started
    assert preview.stopped
    assert camera.stopped


def test_threaded_preview_render_failure_does_not_stop_camera_capture() -> None:
    camera = PreviewCamera()
    preview = FailingPreview()
    source = ThreadedPreviewCameraSource(camera, preview)

    source.start()
    deadline = time.monotonic() + 1.0
    sample = None
    while sample is None and time.monotonic() < deadline:
        sample = source.read()
        time.sleep(0.005)
    with pytest.warns(RuntimeWarning, match="preview disabled after render error"):
        source.pump_preview()

    assert sample is not None
    assert int(sample.payload[0, 0, 0]) in {1, 2}
    assert preview.stopped
    source.stop()


def test_opencv_operator_preview_resizes_and_q_closes_only_preview(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(cv2, "namedWindow", lambda name, mode: calls.append(("named", name)))
    monkeypatch.setattr(
        cv2,
        "resizeWindow",
        lambda name, width, height: calls.append(("size", (width, height))),
    )
    monkeypatch.setattr(
        cv2,
        "imshow",
        lambda name, frame: calls.append(("show", frame.shape)),
    )
    monkeypatch.setattr(cv2, "waitKey", lambda _delay: ord("q"))
    monkeypatch.setattr(cv2, "destroyWindow", lambda name: calls.append(("destroy", name)))

    preview = OpenCVOperatorPreview(max_width=960)
    preview.start()
    preview.show(np.zeros((1080, 1920, 3), dtype=np.uint8))
    preview.show(np.zeros((1080, 1920, 3), dtype=np.uint8))

    assert ("size", (960, 540)) in calls
    assert ("show", (540, 960, 3)) in calls
    assert any(kind == "destroy" for kind, _value in calls)
    assert sum(1 for kind, _value in calls if kind == "show") == 1


def test_opencv_operator_preview_ignores_transient_invisible_window(monkeypatch) -> None:
    calls: list[str] = []
    now = [10.0]
    monkeypatch.setattr(operator_preview_module.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(cv2, "namedWindow", lambda _name, _mode: calls.append("named"))
    monkeypatch.setattr(cv2, "resizeWindow", lambda _name, _width, _height: None)
    monkeypatch.setattr(cv2, "imshow", lambda _name, _frame: calls.append("show"))
    monkeypatch.setattr(cv2, "waitKey", lambda _delay: -1)
    monkeypatch.setattr(cv2, "getWindowProperty", lambda _name, _property: 0.0)
    monkeypatch.setattr(cv2, "destroyWindow", lambda _name: calls.append("destroy"))

    preview = OpenCVOperatorPreview()
    preview.start()
    preview.show(_frame(1))
    now[0] = 10.1
    preview.show(_frame(2))

    assert calls.count("show") == 2
    assert "destroy" not in calls

    now[0] = 11.1
    preview.show(_frame(3))
    preview.show(_frame(4))
    preview.show(_frame(5))

    assert calls.count("show") == 4
    assert calls.count("destroy") == 1

    preview.show(_frame(6))
    assert calls.count("show") == 4


def test_opencv_operator_preview_tolerates_wait_key_none(monkeypatch) -> None:
    shown: list[np.ndarray] = []
    monkeypatch.setattr(cv2, "namedWindow", lambda _name, _mode: None)
    monkeypatch.setattr(cv2, "resizeWindow", lambda _name, _width, _height: None)
    monkeypatch.setattr(cv2, "imshow", lambda _name, frame: shown.append(frame.copy()))
    monkeypatch.setattr(cv2, "waitKey", lambda _delay: None)
    monkeypatch.setattr(cv2, "destroyWindow", lambda _name: None)

    preview = OpenCVOperatorPreview()
    preview.start()
    preview.show(_frame(1))
    preview.show(_frame(2))

    assert len(shown) == 2
    preview.stop()


@pytest.mark.parametrize("mask_shape", [(50, 100), (0, 0)])
def test_operator_preview_overlay_without_detected_pixels(mask_shape) -> None:
    frame = np.full((360, 640, 3), 80, dtype=np.uint8)
    diagnostics = OperatorPreviewDiagnostics(
        state="scanning",
        reason="page_not_found",
        metrics={"page_pair_found": False},
        mask_preview=np.zeros(mask_shape, dtype=np.uint8),
    )

    annotated = _annotate_preview(frame, diagnostics)

    assert annotated.shape == frame.shape
    assert annotated.dtype == frame.dtype
    assert np.all(frame == 80)  # Rendering must not mutate the scanner input.
    assert np.array_equal(annotated[200:], frame[200:])  # No false green tint.
    assert np.any(annotated[:100] != frame[:100])  # Status still renders.


def test_operator_preview_overlay_marks_page_mask_and_obstruction() -> None:
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    mask = np.zeros((50, 100), dtype=np.uint8)
    mask[10:40, 10:90] = 255
    diagnostics = OperatorPreviewDiagnostics(
        state="settling",
        reason="content_occluded",
        metrics={
            "page_pair_found": True,
            "mask_confidence_min": 0.91,
            "preview_width": 100,
            "preview_height": 50,
            "obstruction_bbox_preview": "20,15,10,8",
        },
        mask_preview=mask,
    )

    annotated = _annotate_preview(frame, diagnostics)

    assert annotated.shape == frame.shape
    assert np.any(annotated != frame)
    # Preview bbox is doubled to the full frame coordinate system.
    assert int(annotated[30, 40, 2]) > 0


def test_video_replay_samples_by_frame_stride_and_marks_eof(tmp_path: Path) -> None:
    path = tmp_path / "replay.mp4"
    path.touch()
    capture = FakeCapture([_frame(value) for value in range(7)], fps=10.0)
    clock = ManualClock()
    source = VideoFileCameraSource(
        path,
        sample_interval_ms=500,
        clock=clock,
        capture_factory=lambda _path: capture,
    )

    source.start()
    first = source.read()
    clock.advance(0.5)
    second = source.read()
    third = source.read()

    assert first is not None and int(first.payload[0, 0, 0]) == 0
    assert second is not None and int(second.payload[0, 0, 0]) == 5
    assert third is None
    assert source.exhausted
    source.stop()
    assert capture.released


def test_image_sequence_distinguishes_decode_failure(tmp_path: Path) -> None:
    valid = tmp_path / "valid.jpg"
    missing = tmp_path / "missing.jpg"
    cv2.imwrite(str(valid), _frame(80))
    source = ImageSequenceCameraSource([valid, missing], clock=ManualClock())

    source.start()
    assert source.read() is not None
    with pytest.raises(FrameDecodeError):
        source.read()
    source.stop()
