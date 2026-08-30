"""PC camera and deterministic replay adapters for the sampled runtime."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from .protocols import Clock, FrameSample
from .types import FrameId


class CameraSourceError(RuntimeError):
    """Base class for acquisition errors that are distinct from EOF."""


class CameraUnavailableError(CameraSourceError):
    pass


class FrameDecodeError(CameraSourceError):
    pass


class _Capture(Protocol):
    def isOpened(self) -> bool: ...

    def read(self) -> tuple[bool, np.ndarray | None]: ...

    def grab(self) -> bool: ...

    def retrieve(self) -> tuple[bool, np.ndarray | None]: ...

    def release(self) -> None: ...

    def get(self, prop_id: int) -> float: ...

    def set(self, prop_id: int, value: float) -> bool: ...


CaptureFactory = Callable[[int | str], _Capture]


class SystemClock:
    def monotonic(self) -> float:
        import time

        return time.monotonic()


class OpenCVCameraSource:
    """Live PC camera source that keeps only the most recent grabbed frame.

    The application calls :meth:`read` at its configured sample cadence.  A
    bounded grab/retrieve drain and CAP_PROP_BUFFERSIZE=1 prevent application
    queues from accumulating every camera frame.
    """

    def __init__(
        self,
        device_index: int = 0,
        *,
        clock: Clock | None = None,
        drain_grabs: int = 2,
        capture_factory: CaptureFactory = cv2.VideoCapture,
        frame_prefix: str = "camera",
    ):
        if drain_grabs < 0:
            raise ValueError("drain_grabs must be non-negative")
        self.device_index = device_index
        self.clock = clock or SystemClock()
        self.drain_grabs = drain_grabs
        self.capture_factory = capture_factory
        self.frame_prefix = frame_prefix
        self._capture: _Capture | None = None
        self._counter = 0
        self._lock = threading.Lock()
        self._stopped = True

    @property
    def exhausted(self) -> bool:
        return False

    def start(self) -> None:
        with self._lock:
            if self._capture is not None:
                raise RuntimeError("camera source is already started")
            capture = self.capture_factory(self.device_index)
            if not capture.isOpened():
                capture.release()
                raise CameraUnavailableError(f"could not open camera device {self.device_index}")
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self._capture = capture
            self._counter = 0
            self._stopped = False

    def read(self) -> FrameSample[np.ndarray] | None:
        with self._lock:
            if self._capture is None or self._stopped:
                return None
            capture = self._capture
            frame: np.ndarray | None = None
            ok = False
            if self.drain_grabs > 0:
                for _ in range(self.drain_grabs):
                    if not capture.grab():
                        raise FrameDecodeError("live camera failed while draining buffered frames")
                ok, frame = capture.retrieve()
            else:
                ok, frame = capture.read()
            if not ok or not _valid_frame(frame):
                raise FrameDecodeError("live camera returned an invalid frame")
            return self._sample(np.asarray(frame))

    def stop(self) -> None:
        with self._lock:
            capture, self._capture = self._capture, None
            self._stopped = True
            if capture is not None:
                capture.release()

    def _sample(self, frame: np.ndarray) -> FrameSample[np.ndarray]:
        self._counter += 1
        return FrameSample(
            FrameId(f"{self.frame_prefix}-{self._counter:08d}"),
            self.clock.monotonic(),
            frame.copy(),
        )


class VideoFileCameraSource:
    """Offline MP4/video replay that preserves a configured sample cadence."""

    def __init__(
        self,
        path: Path,
        *,
        sample_interval_ms: int = 500,
        clock: Clock | None = None,
        capture_factory: CaptureFactory = cv2.VideoCapture,
        frame_prefix: str = "video",
    ):
        if sample_interval_ms <= 0:
            raise ValueError("sample_interval_ms must be positive")
        self.path = Path(path)
        self.sample_interval_ms = sample_interval_ms
        self.clock = clock or SystemClock()
        self.capture_factory = capture_factory
        self.frame_prefix = frame_prefix
        self._capture: _Capture | None = None
        self._counter = 0
        self._frame_step = 1
        self._exhausted = False
        self._first = True

    @property
    def exhausted(self) -> bool:
        return self._exhausted

    def start(self) -> None:
        if self._capture is not None:
            raise RuntimeError("video source is already started")
        if not self.path.is_file():
            raise CameraUnavailableError(f"video file does not exist: {self.path}")
        capture = self.capture_factory(str(self.path))
        if not capture.isOpened():
            capture.release()
            raise CameraUnavailableError(f"could not open video file: {self.path}")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            fps = 1.0
        self._frame_step = max(1, round(fps * self.sample_interval_ms / 1000.0))
        self._capture = capture
        self._counter = 0
        self._exhausted = False
        self._first = True

    def read(self) -> FrameSample[np.ndarray] | None:
        if self._capture is None or self._exhausted:
            return None
        if not self._first:
            for _ in range(self._frame_step - 1):
                if not self._capture.grab():
                    self._exhausted = True
                    return None
        self._first = False
        ok, frame = self._capture.read()
        if not ok:
            self._exhausted = True
            return None
        if not _valid_frame(frame):
            raise FrameDecodeError(f"video produced an invalid frame: {self.path}")
        self._counter += 1
        return FrameSample(
            FrameId(f"{self.frame_prefix}-{self._counter:08d}"),
            self.clock.monotonic(),
            np.asarray(frame).copy(),
        )

    def stop(self) -> None:
        capture, self._capture = self._capture, None
        self._exhausted = True
        if capture is not None:
            capture.release()


class ImageSequenceCameraSource:
    """Replay already-sampled image files without altering the legacy source."""

    def __init__(
        self,
        paths: Sequence[Path],
        *,
        clock: Clock | None = None,
        frame_prefix: str = "sequence",
    ):
        self.paths = tuple(Path(path) for path in paths)
        self.clock = clock or SystemClock()
        self.frame_prefix = frame_prefix
        self._index = 0
        self._started = False
        self._stopped = False

    @property
    def exhausted(self) -> bool:
        return self._index >= len(self.paths)

    def start(self) -> None:
        if self._started and not self._stopped:
            raise RuntimeError("image sequence is already started")
        self._index = 0
        self._started = True
        self._stopped = False

    def read(self) -> FrameSample[np.ndarray] | None:
        if not self._started or self._stopped or self.exhausted:
            return None
        path = self.paths[self._index]
        self._index += 1
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if not _valid_frame(frame):
            raise FrameDecodeError(f"could not decode image: {path}")
        return FrameSample(
            FrameId(f"{self.frame_prefix}-{self._index:08d}"),
            self.clock.monotonic(),
            np.asarray(frame),
        )

    def stop(self) -> None:
        self._stopped = True


def _valid_frame(frame: object) -> bool:
    return isinstance(frame, np.ndarray) and frame.ndim == 3 and frame.shape[2] == 3 and frame.size > 0
