"""Optional live operator preview without changing Scanner observation cadence."""

from __future__ import annotations

import threading
import time
import warnings
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from .protocols import CameraSource, FrameSample
from .candidate import CandidateObservation
from .types import ReadinessReason


@dataclass(frozen=True, slots=True)
class OperatorPreviewDiagnostics:
    state: str
    reason: str | None
    metrics: dict[str, object]
    mask_preview: np.ndarray


class FramePreview(Protocol):
    def start(self) -> None: ...

    def show(self, frame: np.ndarray) -> None: ...

    def stop(self) -> None: ...


class OpenCVOperatorPreview:
    """Render camera frames in a bounded window; Q/Esc closes only the window."""

    _VISIBILITY_GRACE_SECONDS = 1.0
    _INVISIBLE_CHECKS_BEFORE_CLOSE = 3

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
        self._opened_at: float | None = None
        self._invisible_checks = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            self._active = True
            self._opened = False
            self._opened_at = None
            self._invisible_checks = 0

    def show(self, frame: np.ndarray) -> None:
        with self._lock:
            if not self._active:
                return
            try:
                if (
                    self._opened
                    and self._opened_at is not None
                    and time.monotonic() - self._opened_at
                    >= self._VISIBILITY_GRACE_SECONDS
                ):
                    if cv2.getWindowProperty(
                        self.window_name, cv2.WND_PROP_VISIBLE
                    ) < 1:
                        self._invisible_checks += 1
                        if (
                            self._invisible_checks
                            >= self._INVISIBLE_CHECKS_BEFORE_CLOSE
                        ):
                            self._close_window()
                            self._active = False
                            return
                    else:
                        self._invisible_checks = 0
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
                    self._opened_at = time.monotonic()
                    self._invisible_checks = 0
                cv2.imshow(self.window_name, view)
                key = cv2.waitKey(1) & 0xFF
                if key in {27, ord("q"), ord("Q")}:
                    self._close_window()
                    self._active = False
            except cv2.error as exc:
                self._active = False
                self._opened = False
                self._opened_at = None
                self._invisible_checks = 0
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
        self._opened_at = None
        self._invisible_checks = 0


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
        source_label: str = "camera",
        idle_sleep_seconds: float = 0.005,
    ) -> None:
        if idle_sleep_seconds <= 0:
            raise ValueError("idle_sleep_seconds must be positive")
        self.source = source
        self.preview = preview
        self.source_label = source_label
        self.idle_sleep_seconds = idle_sleep_seconds
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: FrameSample[np.ndarray] | None = None
        self._latest_generation = 0
        self._delivered_generation = 0
        self._error: Exception | None = None
        self._diagnostics: OperatorPreviewDiagnostics | None = None

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
                self._diagnostics = None
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

    def update_diagnostics(
        self,
        observation: CandidateObservation,
        *,
        primary_reason: ReadinessReason | None = None,
        state: str = "scanning",
    ) -> None:
        """Publish sampled analysis for the next raw-frame preview render."""

        reason = primary_reason
        if reason is None and observation.candidate.retry_reasons:
            reason = observation.candidate.retry_reasons[0]
        diagnostics = OperatorPreviewDiagnostics(
            state=state,
            reason=reason.value if reason is not None else None,
            metrics=dict(observation.candidate.metrics),
            mask_preview=observation.mask_preview.copy(),
        )
        with self._lock:
            self._diagnostics = diagnostics

    def _capture_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                sample = self.source.read()
                if sample is None:
                    if self.source.exhausted:
                        return
                    time.sleep(self.idle_sleep_seconds)
                    continue
                with self._lock:
                    diagnostics = self._diagnostics
                    self._latest = sample
                    self._latest_generation += 1
                self.preview.show(
                    _annotate_preview(
                        sample.payload,
                        diagnostics,
                        source_label=self.source_label,
                        effective_mode=getattr(self.source, "effective_mode", None),
                    )
                )
        except Exception as exc:
            if not self._stop_event.is_set():
                with self._lock:
                    self._error = exc
        finally:
            self.preview.stop()


def _annotate_preview(
    frame: np.ndarray,
    diagnostics: OperatorPreviewDiagnostics | None,
    *,
    source_label: str = "camera",
    effective_mode: dict[str, float | str] | None = None,
) -> np.ndarray:
    view = frame.copy()
    height, width = view.shape[:2]
    if diagnostics is None:
        _draw_status_lines(
            view,
            (
                f"source={source_label}  {_mode_text(effective_mode, width, height)}",
                "Waiting for scanner analysis...",
            ),
            (0, 190, 255),
        )
        return view

    metrics = diagnostics.metrics
    mask = diagnostics.mask_preview
    if mask.size:
        resized_mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST) > 0
        tint = np.zeros_like(view)
        tint[:, :, 1] = 180
        view[resized_mask] = cv2.addWeighted(
            view[resized_mask], 0.78, tint[resized_mask], 0.22, 0
        )

    bbox = _obstruction_bbox(metrics, width=width, height=height)
    if bbox is not None:
        left, top, box_width, box_height = bbox
        cv2.rectangle(
            view,
            (left, top),
            (left + box_width, top + box_height),
            (0, 0, 255),
            max(2, round(min(width, height) / 320)),
        )

    reason = diagnostics.reason or "ready"
    status_color = (0, 190, 0) if reason == "ready" else (0, 140, 255)
    if reason == "content_occluded":
        status_color = (0, 0, 255)
    confidence = metrics.get("mask_confidence_min")
    confidence_text = (
        f"{float(confidence):.3f}"
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
        else "n/a"
    )
    lines = (
        f"source={source_label}  {_mode_text(effective_mode, width, height)}",
        f"state={diagnostics.state}",
        f"reason={reason}",
        (
            "page_pair="
            f"{'yes' if metrics.get('page_pair_found') is True else 'no'}"
            f"  mask_confidence={confidence_text}"
        ),
        "Green=detected pages  Red=hand/obstruction",
    )
    _draw_status_lines(view, lines, status_color)
    return view


def _obstruction_bbox(
    metrics: dict[str, object],
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int] | None:
    value = metrics.get("obstruction_bbox_preview")
    preview_width = metrics.get("preview_width")
    preview_height = metrics.get("preview_height")
    if not isinstance(value, str) or not value:
        return None
    if not isinstance(preview_width, int) or not isinstance(preview_height, int):
        return None
    if preview_width <= 0 or preview_height <= 0:
        return None
    try:
        left, top, box_width, box_height = (int(item) for item in value.split(","))
    except (TypeError, ValueError):
        return None
    scale_x = width / preview_width
    scale_y = height / preview_height
    return (
        max(0, round(left * scale_x)),
        max(0, round(top * scale_y)),
        max(1, round(box_width * scale_x)),
        max(1, round(box_height * scale_y)),
    )


def _draw_status_lines(
    image: np.ndarray,
    lines: tuple[str, ...],
    color: tuple[int, int, int],
) -> None:
    scale = max(0.45, min(0.85, image.shape[1] / 1280 * 0.7))
    thickness = 1 if scale < 0.7 else 2
    line_height = max(20, round(30 * scale / 0.7))
    panel_height = 12 + line_height * len(lines)
    overlay = image.copy()
    cv2.rectangle(overlay, (0, 0), (image.shape[1], panel_height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.62, image, 0.38, 0, image)
    for index, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (10, 8 + line_height * (index + 1) - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color if line.startswith("reason=") else (240, 240, 240),
            thickness,
            cv2.LINE_AA,
        )


def _mode_text(
    effective_mode: dict[str, float | str] | None,
    width: int,
    height: int,
) -> str:
    if effective_mode is None:
        return f"frame={width}x{height}"
    mode_width = effective_mode.get("width", width)
    mode_height = effective_mode.get("height", height)
    fps = effective_mode.get("fps", "n/a")
    fourcc = effective_mode.get("fourcc", "")
    try:
        mode = f"mode={float(mode_width):g}x{float(mode_height):g}@{float(fps):g}"
    except (TypeError, ValueError):
        mode = f"frame={width}x{height}"
    return f"{mode} {fourcc}".strip()
