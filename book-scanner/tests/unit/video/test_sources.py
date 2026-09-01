from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from book_scanner.video.sources import (
    CameraUnavailableError,
    FrameDecodeError,
    ImageSequenceCameraSource,
    OpenCVCameraSource,
    VideoFileCameraSource,
)

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
