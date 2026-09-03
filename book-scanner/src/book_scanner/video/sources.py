"""PC camera and deterministic replay adapters for the sampled runtime."""

from __future__ import annotations

import math
import threading
import time
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


CaptureFactory = Callable[..., _Capture]


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
        device_index: int | str = 0,
        *,
        clock: Clock | None = None,
        drain_grabs: int = 2,
        width: int | None = None,
        height: int | None = None,
        fps: float | None = None,
        backend_api: int | None = None,
        fourcc: str | None = None,
        rotation: int = 0,
        mirror: bool = False,
        warmup_frames: int = 0,
        reopen_attempts: int = 0,
        reopen_initial_ms: int = 250,
        capture_factory: CaptureFactory = cv2.VideoCapture,
        frame_prefix: str = "camera",
        sleep: Callable[[float], None] = time.sleep,
    ):
        if drain_grabs < 0:
            raise ValueError("drain_grabs must be non-negative")
        for name, value in (("width", width), ("height", height), ("fps", fps)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
                raise ValueError(f"camera {name} must be positive when configured")
        if fourcc is not None and (
            not isinstance(fourcc, str) or len(fourcc) != 4 or not fourcc.isascii()
        ):
            raise ValueError("camera fourcc must contain exactly four ASCII characters")
        if rotation not in {0, 90, 180, 270}:
            raise ValueError("camera rotation must be 0, 90, 180, or 270")
        if not isinstance(mirror, bool):
            raise TypeError("camera mirror must be a boolean")
        for name, value, ceiling in (
            ("warmup_frames", warmup_frames, 120),
            ("reopen_attempts", reopen_attempts, 10),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= ceiling:
                raise ValueError(f"camera {name} must be an integer in [0, {ceiling}]")
        if (
            isinstance(reopen_initial_ms, bool)
            or not isinstance(reopen_initial_ms, int)
            or not 1 <= reopen_initial_ms <= 10_000
        ):
            raise ValueError("camera reopen_initial_ms must be an integer in [1, 10000]")
        self.device_index = device_index
        self.clock = clock or SystemClock()
        self.drain_grabs = drain_grabs
        self.width = width
        self.height = height
        self.fps = fps
        self.backend_api = backend_api
        self.fourcc = fourcc
        self.rotation = rotation
        self.mirror = mirror
        self.warmup_frames = warmup_frames
        self.reopen_attempts = reopen_attempts
        self.reopen_initial_ms = reopen_initial_ms
        self.capture_factory = capture_factory
        self.frame_prefix = frame_prefix
        self.sleep = sleep
        self._capture: _Capture | None = None
        self._counter = 0
        self._lock = threading.Lock()
        self._stopped = True
        self._effective_mode: dict[str, float | str] | None = None

    @property
    def exhausted(self) -> bool:
        return False

    @property
    def effective_mode(self) -> dict[str, float | str] | None:
        return None if self._effective_mode is None else dict(self._effective_mode)

    def start(self) -> None:
        with self._lock:
            if self._capture is not None:
                raise RuntimeError("camera source is already started")
            self._capture = self._open_with_retries()
            self._counter = 0
            self._stopped = False

    def read(self) -> FrameSample[np.ndarray] | None:
        with self._lock:
            if self._capture is None or self._stopped:
                return None
            for attempt in range(self.reopen_attempts + 1):
                try:
                    return self._sample(self._read_frame(self._capture))
                except FrameDecodeError:
                    if attempt >= self.reopen_attempts or self._stopped:
                        raise
                    self._capture.release()
                    self._capture = None
                    self.sleep((self.reopen_initial_ms / 1000.0) * (2**attempt))
                    self._capture = self._open_capture()
            raise AssertionError("unreachable camera retry state")

    def stop(self) -> None:
        with self._lock:
            capture, self._capture = self._capture, None
            self._stopped = True
            if capture is not None:
                capture.release()

    def _open_with_retries(self) -> _Capture:
        last_error: CameraUnavailableError | None = None
        for attempt in range(self.reopen_attempts + 1):
            try:
                return self._open_capture()
            except CameraUnavailableError as exc:
                last_error = exc
                if attempt >= self.reopen_attempts:
                    break
                self.sleep((self.reopen_initial_ms / 1000.0) * (2**attempt))
        assert last_error is not None
        raise last_error

    def _open_capture(self) -> _Capture:
        capture = (
            self.capture_factory(self.device_index)
            if self.backend_api is None
            else self.capture_factory(self.device_index, self.backend_api)
        )
        try:
            if not capture.isOpened():
                raise CameraUnavailableError(f"could not open camera device {self.device_index}")
            if self.fourcc is not None:
                capture.set(cv2.CAP_PROP_FOURCC, float(cv2.VideoWriter_fourcc(*self.fourcc)))
            if self.width is not None:
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.width))
            if self.height is not None:
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.height))
            if self.fps is not None:
                capture.set(cv2.CAP_PROP_FPS, float(self.fps))
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            observed: dict[str, float | str] = {
                "width": capture.get(cv2.CAP_PROP_FRAME_WIDTH),
                "height": capture.get(cv2.CAP_PROP_FRAME_HEIGHT),
                "fps": capture.get(cv2.CAP_PROP_FPS),
                "fourcc": _decode_fourcc(capture.get(cv2.CAP_PROP_FOURCC)),
            }
            requested = {"width": self.width, "height": self.height, "fps": self.fps}
            for name, expected in requested.items():
                if expected is not None and abs(float(observed[name]) - float(expected)) > 1.0:
                    raise CameraUnavailableError(
                        f"camera {name} is {observed[name]:g}; requested {expected:g}"
                    )
            if self.fourcc is not None and observed["fourcc"].upper() != self.fourcc.upper():
                raise CameraUnavailableError(
                    f"camera fourcc is {observed['fourcc']!s}; requested {self.fourcc}"
                )
            for _ in range(self.warmup_frames):
                ok, frame = capture.read()
                if not ok or not _valid_frame(frame):
                    raise CameraUnavailableError("camera failed while warming up")
            self._effective_mode = observed
            return capture
        except Exception:
            capture.release()
            raise

    def _read_frame(self, capture: _Capture) -> np.ndarray:
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
        result = np.asarray(frame)
        if self.rotation == 90:
            result = cv2.rotate(result, cv2.ROTATE_90_CLOCKWISE)
        elif self.rotation == 180:
            result = cv2.rotate(result, cv2.ROTATE_180)
        elif self.rotation == 270:
            result = cv2.rotate(result, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if self.mirror:
            result = cv2.flip(result, 1)
        return result

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


def _decode_fourcc(value: float) -> str:
    if not math.isfinite(value):
        return ""
    encoded = int(value)
    return "".join(chr((encoded >> (8 * index)) & 0xFF) for index in range(4)).rstrip("\x00")
