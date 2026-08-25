"""Where frames come from -- abstracted so session/loop.py doesn't care
whether it's driving a live webcam, a Raspberry Pi camera (not implemented
yet -- needs the actual hardware), or a canned test sequence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import cv2
import numpy as np


class CaptureSource(Protocol):
    def read(self) -> np.ndarray | None:
        """Return the next frame (BGR), or None when the source is
        exhausted / unavailable."""
        ...


class WebcamCaptureSource:
    """PC prototype stand-in for the eventual Pi camera (function 1's
    "프로토타입 개발 시에는 PC로 대체")."""

    def __init__(self, device_index: int = 0):
        self._cap = cv2.VideoCapture(device_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"could not open webcam device {device_index}")

    def read(self) -> np.ndarray | None:
        ok, frame = self._cap.read()
        return frame if ok else None

    def close(self) -> None:
        self._cap.release()


class SequenceCaptureSource:
    """Replays a fixed list of image files as frames, one per `read()`
    call. Used for tests and for manually simulating a capture session
    from real photos without a live camera."""

    def __init__(self, image_paths: list[Path]):
        self._paths = list(image_paths)
        self._index = 0

    def read(self) -> np.ndarray | None:
        if self._index >= len(self._paths):
            return None
        frame = cv2.imread(str(self._paths[self._index]))
        self._index += 1
        return frame
