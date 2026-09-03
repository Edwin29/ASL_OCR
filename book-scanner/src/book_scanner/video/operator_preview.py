"""Optional live operator preview without changing Scanner observation cadence."""

from __future__ import annotations

import threading
import time
import warnings
from typing import Protocol

import cv2
import numpy as np

from .protocols import CameraSource, FrameSample


class FramePreview(Protocol):
    def start(self) -> None: ...

    def show(self, frame: np.ndarray) -> None: ...

    def stop(self) -> None: ...


class OpenCVOperatorPreview:
    """Render camera frames in a bounded window; Q/Esc closes only the window."""

    def __init__(
        self,
        *,
        window_name: str = "ASL OCR Camera Preview (Q/Esc: close)",
        max_width: int = 1280,
    ) -> None:
        if isinstance(max_width, bool) or not isinstance(max_width, int) or max_width < 320:
            raise ValueError("operator preview max_width must be an integer >= 320")
        self.window_name = window_name
        self.max_width = max_width
        self._active = False
        self._opened = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self._active = True
            self._opened = False

    def show(self, frame: np.ndarray) -> None:
        with self._lock:
            if not self._active:
                return
            try:
                if self._opened and cv2.getWindowProperty(
                    self.window_name, cv2.WND_PROP_VISIBLE
                ) < 1:
                    self._active = False
                    self._opened = False
                    return
                view = frame
                if frame.shape[1] > self.max_width:
                    scale = self.max_width / frame.shape[1]
                    view = cv2.resize(
                        frame,
                        (self.max_width, max(1, round(frame.shape[0] * scale))),
                        interpolation=cv2.INTER_AREA,
                    )
                if not self._opened:
                    cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
                    cv2.resizeWindow(self.window_name, view.shape[1], view.shape[0])
                    self._opened = True
                cv2.imshow(self.window_name, view)
                key = cv2.waitKey(1) & 0xFF
                if key in {27, ord("q"), ord("Q")}:
                    self._close_window()
                    self._active = False
            except cv2.error as exc:
                self._active = False
                self._opened = False
                warnings.warn(
                    f"operator camera preview disabled after OpenCV GUI error: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )

    def stop(self) -> None:
        with self._lock:
            self._active = False
            self._close_window()

    def _close_window(self) -> None:
        if not self._opened:
            return
        try:
            cv2.destroyWindow(self.window_name)
            cv2.waitKey(1)
        except cv2.error:
            pass
        self._opened = False


class ThreadedPreviewCameraSource:
    """Continuously acquire preview frames while exposing only fresh latest samples.

    The wrapped physical source is owned exclusively by the worker thread. Scanner
    polling therefore keeps its configured observation cadence while the operator
    window updates at the camera's acquisition rate.
    """

    def __init__(
        self,
        source: CameraSource[np.ndarray],
        preview: FramePreview,
        *,
        idle_sleep_seconds: float = 0.005,
    ) -> None:
        if idle_sleep_seconds <= 0:
            raise ValueError("idle_sleep_seconds must be positive")
        self.source = source
        self.preview = preview
        self.idle_sleep_seconds = idle_sleep_seconds
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: FrameSample[np.ndarray] | None = None
        self._latest_generation = 0
        self._delivered_generation = 0
        self._error: Exception | None = None

    @property
    def exhausted(self) -> bool:
        return self.source.exhausted

    @property
    def effective_mode(self):
        return getattr(self.source, "effective_mode", None)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("preview camera source is already started")
        self.source.start()
        try:
            self.preview.start()
            self._stop_event.clear()
            with self._lock:
                self._latest = None
                self._latest_generation = 0
                self._delivered_generation = 0
                self._error = None
            self._thread = threading.Thread(
                target=self._capture_loop,
                name="asl-ocr-camera-preview",
                daemon=True,
            )
            self._thread.start()
        except Exception:
            self._thread = None
            self.preview.stop()
            self.source.stop()
            raise

    def read(self) -> FrameSample[np.ndarray] | None:
        with self._lock:
            if self._error is not None:
                error = self._error
                self._error = None
                raise error
            if self._latest is None or self._latest_generation == self._delivered_generation:
                return None
            self._delivered_generation = self._latest_generation
            sample = self._latest
            return FrameSample(sample.frame_id, sample.captured_at_monotonic, sample.payload.copy())

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        self._stop_event.set()
        self.source.stop()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
            if thread.is_alive():
                warnings.warn(
                    "operator camera preview worker did not stop within 2 seconds",
                    RuntimeWarning,
                    stacklevel=2,
                )

    def _capture_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                sample = self.source.read()
                if sample is None:
                    if self.source.exhausted:
                        return
                    time.sleep(self.idle_sleep_seconds)
                    continue
                self.preview.show(sample.payload)
                with self._lock:
                    self._latest = sample
                    self._latest_generation += 1
        except Exception as exc:
            if not self._stop_event.is_set():
                with self._lock:
                    self._error = exc
        finally:
            self.preview.stop()
