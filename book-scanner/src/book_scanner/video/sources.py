"""PC camera and deterministic replay adapters for the sampled runtime."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

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


class SnapshotTransportError(CameraSourceError):
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


class _HttpResponse(Protocol):
    headers: object

    def raise_for_status(self) -> None: ...

    def iter_content(self, chunk_size: int): ...

    def close(self) -> None: ...


SnapshotFetcher = Callable[..., _HttpResponse]


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
        crop_normalized: tuple[float, float, float, float] | None = None,
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
        if crop_normalized is not None:
            if (
                not isinstance(crop_normalized, tuple)
                or len(crop_normalized) != 4
                or any(
                    isinstance(value, bool) or not isinstance(value, (int, float))
                    for value in crop_normalized
                )
            ):
                raise TypeError("camera crop_normalized must be a four-number tuple")
            left, top, right, bottom = (float(value) for value in crop_normalized)
            if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
                raise ValueError(
                    "camera crop_normalized must satisfy "
                    "0 <= left < right <= 1 and 0 <= top < bottom <= 1"
                )
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
        self.crop_normalized = crop_normalized
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
        return _orient_frame(
            np.asarray(frame),
            rotation=self.rotation,
            mirror=self.mirror,
            crop_normalized=self.crop_normalized,
        )

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


class HttpSnapshotCameraSource:
    """Fetch one full-resolution JPEG for each scanner observation.

    This source is intended for a phone camera server reached over an isolated
    Wi-Fi or USB-tethered IP link.  It deliberately does not fall back to a PC
    webcam when the phone becomes unavailable.
    """

    def __init__(
        self,
        url: str,
        *,
        username: str | None = None,
        password_file: Path | None = None,
        tls_ca_file: Path | None = None,
        allow_insecure_tls: bool = False,
        timeout_seconds: float = 8.0,
        max_response_bytes: int = 32 * 1024 * 1024,
        min_width: int = 1920,
        min_height: int = 1080,
        rotation: int = 0,
        landscape_rotation: int | None = None,
        portrait_rotation: int | None = None,
        mirror: bool = False,
        crop_normalized: tuple[float, float, float, float] | None = None,
        fetcher: SnapshotFetcher | None = None,
        clock: Clock | None = None,
        frame_prefix: str = "phone-snapshot",
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("snapshot URL must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("snapshot credentials must not be embedded in the URL")
        if username is not None and (not isinstance(username, str) or not username.strip()):
            raise ValueError("snapshot username must be non-empty when configured")
        if password_file is not None and username is None:
            raise ValueError("snapshot password_file requires a username")
        if username is not None and password_file is None:
            raise ValueError("snapshot username requires a password_file")
        if parsed.scheme == "http" and username is not None:
            raise ValueError("snapshot authentication requires HTTPS")
        if tls_ca_file is not None and allow_insecure_tls:
            raise ValueError("snapshot TLS CA and insecure TLS cannot both be configured")
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not 0 < timeout_seconds <= 60:
            raise ValueError("snapshot timeout_seconds must be in (0, 60]")
        for name, value, ceiling in (
            ("max_response_bytes", max_response_bytes, 128 * 1024 * 1024),
            ("min_width", min_width, 20_000),
            ("min_height", min_height, 20_000),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= ceiling:
                raise ValueError(f"snapshot {name} must be an integer in [1, {ceiling}]")
        _validate_orientation(rotation, mirror, crop_normalized)
        for name, value in (
            ("landscape_rotation", landscape_rotation),
            ("portrait_rotation", portrait_rotation),
        ):
            if value is not None and value not in {0, 90, 180, 270}:
                raise ValueError(f"snapshot {name} must be 0, 90, 180, or 270")
        self.url = url
        self.username = username
        self.password_file = None if password_file is None else Path(password_file)
        self.tls_ca_file = None if tls_ca_file is None else Path(tls_ca_file)
        self.allow_insecure_tls = allow_insecure_tls
        self.timeout_seconds = float(timeout_seconds)
        self.max_response_bytes = max_response_bytes
        self.min_width = min_width
        self.min_height = min_height
        self.rotation = rotation
        self.landscape_rotation = landscape_rotation
        self.portrait_rotation = portrait_rotation
        self.mirror = mirror
        self.crop_normalized = crop_normalized
        self.fetcher = fetcher
        self.clock = clock or SystemClock()
        self.frame_prefix = frame_prefix
        self._session = None
        self._counter = 0
        self._started = False
        self._effective_mode: dict[str, float | str] | None = None

    @property
    def exhausted(self) -> bool:
        return False

    @property
    def effective_mode(self) -> dict[str, float | str] | None:
        return None if self._effective_mode is None else dict(self._effective_mode)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("snapshot source is already started")
        if self.password_file is not None and not self.password_file.is_file():
            raise CameraUnavailableError("snapshot password file does not exist")
        if self.tls_ca_file is not None and not self.tls_ca_file.is_file():
            raise CameraUnavailableError("snapshot TLS CA file does not exist")
        if self.fetcher is None:
            import requests

            self._session = requests.Session()
            self.fetcher = self._session.get
        self._counter = 0
        self._started = True

    def read(self) -> FrameSample[np.ndarray] | None:
        if not self._started or self.fetcher is None:
            return None
        frame = None
        decode_error: FrameDecodeError | None = None
        for _attempt in range(3):
            try:
                frame = self._fetch_decoded_frame()
                break
            except FrameDecodeError as exc:
                decode_error = exc
        if frame is None:
            assert decode_error is not None
            raise decode_error
        raw_height, raw_width = frame.shape[:2]
        applied_rotation = self.rotation
        if raw_width > raw_height and self.landscape_rotation is not None:
            applied_rotation = self.landscape_rotation
        elif raw_height > raw_width and self.portrait_rotation is not None:
            applied_rotation = self.portrait_rotation
        frame = _orient_frame(
            frame,
            rotation=applied_rotation,
            mirror=self.mirror,
            crop_normalized=self.crop_normalized,
        )
        self._counter += 1
        self._effective_mode = {
            "width": float(frame.shape[1]),
            "height": float(frame.shape[0]),
            "raw_width": float(raw_width),
            "raw_height": float(raw_height),
            "rotation": float(applied_rotation),
            "transport": "http_snapshot",
        }
        return FrameSample(
            FrameId(f"{self.frame_prefix}-{self._counter:08d}"),
            self.clock.monotonic(),
            frame.copy(),
        )

    def _fetch_decoded_frame(self) -> np.ndarray:
        assert self.fetcher is not None
        response = None
        try:
            response = self.fetcher(
                self.url,
                auth=self._auth(),
                timeout=self.timeout_seconds,
                stream=True,
                verify=self._tls_verify(),
                headers={"Accept": "image/jpeg", "Cache-Control": "no-cache"},
            )
            response.raise_for_status()
            content_length = _content_length(response.headers)
            if content_length is not None and content_length > self.max_response_bytes:
                raise FrameDecodeError("snapshot response exceeds configured byte limit")
            payload = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                payload.extend(chunk)
                if len(payload) > self.max_response_bytes:
                    raise FrameDecodeError("snapshot response exceeds configured byte limit")
        except FrameDecodeError:
            raise
        except Exception as exc:
            raise SnapshotTransportError(f"snapshot request failed: {type(exc).__name__}") from exc
        finally:
            if response is not None:
                response.close()
        frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
        if not _valid_frame(frame):
            raise FrameDecodeError("snapshot response is not a decodable color image")
        raw_height, raw_width = frame.shape[:2]
        if raw_width < self.min_width or raw_height < self.min_height:
            raise FrameDecodeError(
                f"snapshot is {raw_width}x{raw_height}; minimum is {self.min_width}x{self.min_height}"
            )
        return frame

    def stop(self) -> None:
        session, self._session = self._session, None
        self._started = False
        if session is not None:
            session.close()

    def _auth(self) -> tuple[str, str] | None:
        if self.username is None or self.password_file is None:
            return None
        try:
            password = self.password_file.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise CameraUnavailableError("snapshot password file is unreadable") from exc
        if not password:
            raise CameraUnavailableError("snapshot password file is empty")
        return self.username, password

    def _tls_verify(self) -> bool | str:
        if self.allow_insecure_tls:
            return False
        return True if self.tls_ca_file is None else str(self.tls_ca_file)


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


def _validate_orientation(
    rotation: int,
    mirror: bool,
    crop_normalized: tuple[float, float, float, float] | None,
) -> None:
    if rotation not in {0, 90, 180, 270}:
        raise ValueError("camera rotation must be 0, 90, 180, or 270")
    if not isinstance(mirror, bool):
        raise TypeError("camera mirror must be a boolean")
    if crop_normalized is None:
        return
    if (
        not isinstance(crop_normalized, tuple)
        or len(crop_normalized) != 4
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in crop_normalized)
    ):
        raise TypeError("camera crop_normalized must be a four-number tuple")
    left, top, right, bottom = (float(value) for value in crop_normalized)
    if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
        raise ValueError("camera crop_normalized bounds are invalid")


def _orient_frame(
    frame: np.ndarray,
    *,
    rotation: int,
    mirror: bool,
    crop_normalized: tuple[float, float, float, float] | None,
) -> np.ndarray:
    result = np.asarray(frame)
    if rotation == 90:
        result = cv2.rotate(result, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        result = cv2.rotate(result, cv2.ROTATE_180)
    elif rotation == 270:
        result = cv2.rotate(result, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if crop_normalized is not None:
        left, top, right, bottom = crop_normalized
        result_height, result_width = result.shape[:2]
        x0 = max(0, min(result_width - 1, round(left * result_width)))
        y0 = max(0, min(result_height - 1, round(top * result_height)))
        x1 = max(x0 + 1, min(result_width, round(right * result_width)))
        y1 = max(y0 + 1, min(result_height, round(bottom * result_height)))
        result = result[y0:y1, x0:x1]
    if mirror:
        result = cv2.flip(result, 1)
    return result


def _content_length(headers: object) -> int | None:
    if not hasattr(headers, "get"):
        return None
    value = headers.get("Content-Length")
    if value is None:
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _decode_fourcc(value: float) -> str:
    if not math.isfinite(value):
        return ""
    encoded = int(value)
    return "".join(chr((encoded >> (8 * index)) & 0xFF) for index in range(4)).rstrip("\x00")
