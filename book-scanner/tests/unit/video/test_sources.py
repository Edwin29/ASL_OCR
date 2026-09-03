from __future__ import annotations

import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

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


class RecordingPreview:
    def __init__(self) -> None:
        self.frames: list[np.ndarray] = []
        self.started = False
        self.stopped = False
        self.ready = threading.Event()

    def start(self) -> None:
        self.started = True

    def show(self, frame: np.ndarray) -> None:
        self.frames.append(frame.copy())
        if len(self.frames) >= 2:
            self.ready.set()

    def stop(self) -> None:
        self.stopped = True


class PreviewCamera:
    def __init__(self) -> None:
        self.index = 0
        self.stopped = False

    @property
    def exhausted(self) -> bool:
        return False

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
    assert preview.ready.wait(timeout=1.0)
    sample = source.read()

    assert sample is not None
    assert sample.frame_id.value == "preview-00000002"
    assert int(sample.payload[0, 0, 0]) == 2
    assert source.read() is None
    source.stop()
    assert preview.started
    assert preview.stopped
    assert camera.stopped


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
